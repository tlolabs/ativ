use crate::{Error, Result};
use std::{
    fs,
    path::{Path, PathBuf},
};
use tempfile::NamedTempFile;
pub(crate) fn absolute(path: &Path) -> Result<PathBuf> {
    std::path::absolute(path).map_err(|e| Error::io("resolve path", path, e))
}
fn resolve_target(path: &Path) -> Result<PathBuf> {
    use std::{collections::VecDeque, path::Component};
    let abs = absolute(path)?;
    let mut resolved = PathBuf::new();
    let mut pending: VecDeque<_> = abs
        .components()
        .map(|component| component.as_os_str().to_owned())
        .collect();
    let mut symlinks = 0usize;
    while let Some(part) = pending.pop_front() {
        let component_path = Path::new(&part);
        let mut components = component_path.components();
        match components.next() {
            Some(Component::Prefix(_) | Component::RootDir) => {
                resolved.push(&part);
            }
            Some(Component::CurDir) | None => {}
            Some(Component::ParentDir) => {
                resolved.pop();
            }
            Some(Component::Normal(_)) => {
                let candidate = resolved.join(&part);
                if let Ok(meta) = fs::symlink_metadata(&candidate) {
                    if meta.file_type().is_symlink() && symlinks < 40 {
                        if let Ok(target) = fs::read_link(&candidate) {
                            symlinks += 1;
                            if target.is_absolute() {
                                resolved.clear();
                            }
                            for item in target.components().rev() {
                                pending.push_front(item.as_os_str().to_owned());
                            }
                            continue;
                        }
                    }
                }
                if let Ok(canonical) = fs::canonicalize(&candidate) {
                    resolved = canonical;
                } else {
                    resolved = candidate;
                }
            }
        }
    }
    Ok(resolved)
}
pub(crate) fn file(path: &Path) -> Result<()> {
    if path.is_file() {
        Ok(())
    } else {
        Err(Error::InvalidInput(format!(
            "Source is missing or is not a file: {}",
            path.display()
        )))
    }
}
pub(crate) fn protect(
    output: &Path,
    inputs: impl IntoIterator<Item = impl AsRef<Path>>,
) -> Result<()> {
    let resolved_output = resolve_target(output)?;
    if output.file_name().is_none()
        || resolved_output.file_name().is_none()
        || (output.exists() && !output.is_file())
        || (resolved_output.exists() && !resolved_output.is_file())
    {
        return Err(Error::InvalidInput(
            "Destination must be a file path".into(),
        ));
    }
    let abs_output = absolute(output)?;
    // Resolve each exact input spelling once per call; publication rechecks
    // start with a fresh set so changed aliases are still detected.
    let mut seen = std::collections::HashSet::new();
    for input in inputs {
        let input = input.as_ref();
        if seen.contains(input.as_os_str()) {
            continue;
        }
        seen.insert(input.as_os_str().to_owned());
        let resolved_input = resolve_target(input)?;
        let aliases = absolute(input)? == abs_output
            || resolved_input == resolved_output
            || (output.exists()
                && input.exists()
                && same_file::is_same_file(input, output)
                    .map_err(|e| Error::io("compare destination and source", output, e))?)
            || (resolved_output.exists()
                && resolved_input.exists()
                && same_file::is_same_file(&resolved_input, &resolved_output)
                    .map_err(|e| Error::io("compare destination and source", output, e))?);
        if aliases {
            return Err(Error::InvalidInput(format!(
                "Destination must not replace a source or protected file: {}",
                input.display()
            )));
        }
    }
    Ok(())
}
pub(crate) struct StagedOutput {
    file: NamedTempFile,
}
impl StagedOutput {
    pub fn new(destination: &Path, suffix: &str) -> Result<Self> {
        let parent = destination
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        fs::create_dir_all(parent).map_err(|e| Error::io("create output folder", parent, e))?;
        let mut builder = tempfile::Builder::new();
        builder.prefix(".avid-").suffix(suffix);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            // Match FFmpeg's ordinary output creation mode, respecting the process umask.
            builder.permissions(fs::Permissions::from_mode(0o666));
        }
        let file = builder
            .tempfile_in(parent)
            .map_err(|e| Error::io("stage output", destination, e))?;
        Ok(Self { file })
    }
    pub fn path(&self) -> &Path {
        self.file.path()
    }
    pub fn publish(self, destination: &Path) -> Result<()> {
        // Sync the actual pathname written by FFmpeg before publication.
        let file = fs::OpenOptions::new()
            .read(true)
            .write(true)
            .open(self.path())
            .map_err(|e| Error::io("open completed output", self.path(), e))?;
        if file
            .metadata()
            .map_err(|e| Error::io("inspect completed output", self.path(), e))?
            .len()
            == 0
        {
            return Err(Error::InvalidInput(
                "Media tool produced an empty output".into(),
            ));
        }
        file.sync_all()
            .map_err(|e| Error::io("flush completed output", self.path(), e))?;
        // Release our completed-output handle before attempting the Windows rename.
        drop(file);
        // tempfile uses POSIX rename / Windows MoveFileExW(REPLACE_EXISTING).
        // Retain ownership across transient Windows locks so failure still cleans the stage.
        #[cfg(windows)]
        let result = persist_with_retry(self.file, std::time::Duration::from_secs(2), |file| {
            file.persist(destination)
        });
        #[cfg(not(windows))]
        let result = self
            .file
            .persist(destination)
            .map(|_| ())
            .map_err(|error| error.error);
        result.map_err(|error| Error::io("publish completed output", destination, error))
    }
}

#[cfg(any(windows, test))]
fn persist_with_retry(
    mut file: NamedTempFile,
    max_wait: std::time::Duration,
    mut persist: impl FnMut(NamedTempFile) -> std::result::Result<fs::File, tempfile::PersistError>,
) -> std::io::Result<()> {
    use std::time::{Duration, Instant};
    let started = Instant::now();
    let mut interval = Duration::from_millis(5);
    loop {
        match persist(file) {
            Ok(_) => return Ok(()),
            Err(error) => {
                if !matches!(error.error.raw_os_error(), Some(5 | 32 | 33)) {
                    return Err(error.error);
                }
                let Some(remaining) = max_wait.checked_sub(started.elapsed()) else {
                    return Err(error.error);
                };
                if remaining.is_zero() {
                    return Err(error.error);
                }
                std::thread::sleep(interval.min(remaining));
                // The budget bounds retries; never rename again after it has elapsed.
                if started.elapsed() >= max_wait {
                    return Err(error.error);
                }
                file = error.file;
                interval = (interval * 2).min(Duration::from_millis(50));
            }
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn repeated_protected_inputs_preserve_distinct_alias_checks_and_fresh_validation() {
        let root = tempfile::tempdir().unwrap();
        let output = root.path().join("output.mp4");
        let source = root.path().join("source.wav");
        let later = root.path().join("later.wav");
        fs::write(&output, b"existing output").unwrap();
        fs::write(&source, b"source").unwrap();
        fs::write(&later, b"later source").unwrap();
        let inputs = [&source, &source, &later, &source];
        protect(&output, inputs).unwrap();

        // Distinct paths must keep their identity checks even after duplicates.
        fs::remove_file(&later).unwrap();
        fs::hard_link(&output, &later).unwrap();
        assert!(protect(&output, inputs).is_err());
        assert_eq!(fs::read(&output).unwrap(), b"existing output");
    }

    #[cfg(unix)]
    #[test]
    fn repeated_protection_does_not_cache_symlink_targets_across_calls() {
        use std::os::unix::fs::symlink;
        let root = tempfile::tempdir().unwrap();
        let output = root.path().join("output.mp4");
        let source = root.path().join("source.wav");
        let alias = root.path().join("source-alias.wav");
        fs::write(&output, b"existing output").unwrap();
        fs::write(&source, b"source").unwrap();
        symlink(&source, &alias).unwrap();
        let inputs = [&alias, &alias, &source];
        protect(&output, inputs).unwrap();
        fs::remove_file(&alias).unwrap();
        symlink(&output, &alias).unwrap();
        assert!(protect(&output, inputs).is_err());
        assert_eq!(fs::read(&output).unwrap(), b"existing output");
    }

    #[test]
    fn stage_cleanup_publish_and_protection() {
        let root = tempfile::tempdir().unwrap();
        let destination = root.path().join("final.mp4");
        fs::write(&destination, b"old").unwrap();
        let path = {
            let staged = StagedOutput::new(&destination, ".mp4").unwrap();
            staged.path().to_owned()
        };
        assert!(!path.exists());
        let staged = StagedOutput::new(&destination, ".mp4").unwrap();
        fs::write(staged.path(), b"new").unwrap();
        staged.publish(&destination).unwrap();
        assert_eq!(fs::read(&destination).unwrap(), b"new");
        let alias = root.path().join("alias.mp4");
        fs::hard_link(&destination, &alias).unwrap();
        assert!(protect(&alias, [&destination]).is_err());
        let staged = StagedOutput::new(&destination, ".mp4").unwrap();
        assert!(staged.publish(&destination).is_err());
        assert_eq!(fs::read(&destination).unwrap(), b"new");
    }
    #[test]
    fn failed_publication_cleans_stage() {
        let root = tempfile::tempdir().unwrap();
        let destination = root.path().join("folder");
        fs::create_dir(&destination).unwrap();
        let stage = StagedOutput::new(&destination, ".mp4").unwrap();
        let path = stage.path().to_owned();
        fs::write(&path, b"video").unwrap();
        assert!(stage.publish(&destination).is_err());
        assert!(!path.exists());
        assert!(destination.is_dir());
    }

    #[test]
    fn transient_windows_locks_retain_stage_until_successful_publication() {
        let root = tempfile::tempdir().unwrap();
        let destination = root.path().join("final.mp4");
        fs::write(&destination, b"previous output").unwrap();
        let stage = StagedOutput::new(&destination, ".mp4").unwrap();
        let path = stage.path().to_owned();
        fs::write(&path, b"completed output").unwrap();
        let mut attempts = 0;
        persist_with_retry(stage.file, std::time::Duration::from_secs(1), |file| {
            assert_eq!(file.path(), path);
            assert_eq!(fs::read(&path).unwrap(), b"completed output");
            attempts += 1;
            if let Some(code) = [5, 32, 33].get(attempts - 1) {
                assert_eq!(fs::read(&destination).unwrap(), b"previous output");
                Err(tempfile::PersistError {
                    error: std::io::Error::from_raw_os_error(*code),
                    file,
                })
            } else {
                file.persist(&destination)
            }
        })
        .unwrap();
        assert_eq!(attempts, 4);
        assert!(!path.exists());
        assert_eq!(fs::read(destination).unwrap(), b"completed output");
    }

    #[test]
    fn permanent_publication_error_does_not_retry_and_cleans_stage() {
        let root = tempfile::tempdir().unwrap();
        let destination = root.path().join("final.mp4");
        fs::write(&destination, b"previous output").unwrap();
        let stage = StagedOutput::new(&destination, ".mp4").unwrap();
        let path = stage.path().to_owned();
        fs::write(&path, b"completed output").unwrap();
        let mut attempts = 0;
        let error = persist_with_retry(stage.file, std::time::Duration::from_secs(1), |file| {
            attempts += 1;
            Err(tempfile::PersistError {
                error: std::io::Error::from_raw_os_error(2),
                file,
            })
        })
        .unwrap_err();
        assert_eq!(attempts, 1);
        assert_eq!(error.raw_os_error(), Some(2));
        assert!(!path.exists());
        assert_eq!(fs::read(destination).unwrap(), b"previous output");
    }

    #[test]
    fn persistent_windows_lock_exhausts_budget_and_cleans_stage() {
        let root = tempfile::tempdir().unwrap();
        let destination = root.path().join("final.mp4");
        fs::write(&destination, b"previous output").unwrap();
        let stage = StagedOutput::new(&destination, ".mp4").unwrap();
        let path = stage.path().to_owned();
        fs::write(&path, b"completed output").unwrap();
        let max_wait = std::time::Duration::from_millis(15);
        let started = std::time::Instant::now();
        let mut attempts = 0;
        let error = persist_with_retry(stage.file, max_wait, |file| {
            attempts += 1;
            Err(tempfile::PersistError {
                error: std::io::Error::from_raw_os_error(32),
                file,
            })
        })
        .unwrap_err();
        assert!(attempts >= 1);
        assert!(started.elapsed() >= max_wait);
        assert_eq!(error.raw_os_error(), Some(32));
        assert!(!path.exists());
        assert_eq!(fs::read(destination).unwrap(), b"previous output");
    }

    #[test]
    fn zero_retry_budget_still_attempts_publication_once() {
        let root = tempfile::tempdir().unwrap();
        let destination = root.path().join("final.mp4");
        let stage = StagedOutput::new(&destination, ".mp4").unwrap();
        let path = stage.path().to_owned();
        fs::write(&path, b"completed output").unwrap();
        let mut attempts = 0;
        let error = persist_with_retry(stage.file, std::time::Duration::ZERO, |file| {
            attempts += 1;
            Err(tempfile::PersistError {
                error: std::io::Error::from_raw_os_error(33),
                file,
            })
        })
        .unwrap_err();
        assert_eq!(attempts, 1);
        assert_eq!(error.raw_os_error(), Some(33));
        assert!(!path.exists());
        assert!(!destination.exists());
    }

    #[test]
    fn protect_rejects_nonexistent_parent_dotdot_and_directory_targets() {
        let root = tempfile::tempdir().unwrap();
        let source = root.path().join("source.png");
        fs::write(&source, b"source").unwrap();
        let missing_sub = root.path().join("missing-sub");
        let dotdot_alias = missing_sub.join("..").join("source.png");
        assert!(protect(&dotdot_alias, [&source]).is_err());
        assert!(!missing_sub.exists());

        let reserved = root.path().join("reserved.mp4");
        let reserved_alias = missing_sub.join("..").join("reserved.mp4");
        assert!(protect(&reserved_alias, [&reserved]).is_err());

        let dir_target = missing_sub.join("..");
        assert!(protect(&dir_target, [&source]).is_err());
    }
}

#[cfg(all(test, unix))]
mod permission_tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    #[test]
    fn output_creation_mode_matches_normal_files_without_changing_umask() {
        let root = tempfile::tempdir().unwrap();
        let ordinary = root.path().join("ordinary");
        fs::write(&ordinary, b"ordinary").unwrap();
        let stage = StagedOutput::new(&root.path().join("output.mp4"), ".mp4").unwrap();
        assert_eq!(
            fs::metadata(stage.path()).unwrap().permissions().mode() & 0o777,
            fs::metadata(ordinary).unwrap().permissions().mode() & 0o777
        );
    }
}
