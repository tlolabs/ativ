//! Core owns the media pair; ATIV binds platform-signed copies to its pinned artifact.
use ativ_core::AtivError;
use ativ_core::{CancellationToken, MediaTools};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    fs,
    io::Read,
    path::{Path, PathBuf},
};

const LEGACY_PIN: &str = include_str!("../../../runtime/core-runtime.json");
const PLATFORM_PINS: &str = include_str!("../../../runtime/platform-runtimes.json");

static LEGACY: std::sync::LazyLock<Value> = std::sync::LazyLock::new(|| {
    serde_json::from_str(LEGACY_PIN).expect("checked-in legacy Core runtime pins")
});
static PLATFORMS: std::sync::LazyLock<Value> = std::sync::LazyLock::new(|| {
    serde_json::from_str(PLATFORM_PINS).expect("checked-in platform Core runtime pins")
});
static CORE_SPEC: std::sync::LazyLock<Value> = std::sync::LazyLock::new(|| {
    serde_json::from_str(ativ_core::FFMPEG_RUNTIME_SPECIFICATION).expect("Core specification")
});

fn unavailable() -> AtivError {
    AtivError::RuntimeUnavailable
}
fn read_json(path: &Path) -> ativ_core::Result<Value> {
    serde_json::from_slice(&fs::read(path).map_err(|_| unavailable())?).map_err(|_| unavailable())
}
fn hash(path: &Path) -> ativ_core::Result<String> {
    if !fs::symlink_metadata(path)
        .map_err(|_| unavailable())?
        .is_file()
    {
        return Err(unavailable());
    }
    let mut file = fs::File::open(path).map_err(|_| unavailable())?;
    let mut digest = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let count = file.read(&mut buffer).map_err(|_| unavailable())?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    let bytes: [u8; 32] = digest.finalize().into();
    Ok(hex_digest(&bytes))
}

fn hex_digest(hash_bytes: &[u8; 32]) -> String {
    const HEX_CHARS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(64);
    for &b in hash_bytes {
        out.push(HEX_CHARS[(b >> 4) as usize] as char);
        out.push(HEX_CHARS[(b & 0x0f) as usize] as char);
    }
    out
}
fn check_tree(
    root: &Path,
    directory: &Path,
    files: &HashMap<String, String>,
) -> ativ_core::Result<()> {
    for entry in fs::read_dir(directory).map_err(|_| unavailable())? {
        let entry = entry.map_err(|_| unavailable())?;
        let file_type = entry.file_type().map_err(|_| unavailable())?;
        let path = entry.path();
        if file_type.is_dir() {
            check_tree(root, &path, files)?;
        } else if !file_type.is_file() {
            return Err(unavailable());
        } else {
            let name = path
                .strip_prefix(root)
                .map_err(|_| unavailable())?
                .to_string_lossy()
                .replace('\\', "/");
            if !files.contains_key(&name)
                && ![
                    "SHA256SUMS",
                    "signed-payload.json",
                    "ativ-runtime.json",
                    "corresponding-source.tar.gz",
                ]
                .contains(&name.as_str())
            {
                return Err(unavailable());
            }
        }
    }
    Ok(())
}
// Join both workers before propagating either result: an unjoined panic would
// otherwise escape scope() and bypass the engine's structured IPC error.
fn hash_pair(
    ffmpeg: impl FnOnce() -> ativ_core::Result<String> + Send,
    ffprobe: impl FnOnce() -> ativ_core::Result<String> + Send,
) -> ativ_core::Result<(String, String)> {
    std::thread::scope(|scope| {
        let first = std::thread::Builder::new().spawn_scoped(scope, ffmpeg);
        let second = std::thread::Builder::new().spawn_scoped(scope, ffprobe);
        let first = first
            .map_err(|_| unavailable())
            .and_then(|worker| worker.join().map_err(|_| unavailable()))
            .and_then(|result| result);
        let second = second
            .map_err(|_| unavailable())
            .and_then(|worker| worker.join().map_err(|_| unavailable()))
            .and_then(|result| result);
        Ok((first?, second?))
    })
}

fn packaged_pair() -> ativ_core::Result<(PathBuf, PathBuf, String)> {
    let executable = std::env::current_exe().map_err(|_| unavailable())?;
    let binary = executable.parent().ok_or_else(unavailable)?;
    let metadata = if cfg!(target_os = "macos") && binary.file_name().is_some_and(|n| n == "MacOS")
    {
        binary.join("../Resources/FFmpeg")
    } else {
        binary.join("ffmpeg-runtime")
    };
    let os = if cfg!(target_os = "macos") {
        "macos"
    } else {
        std::env::consts::OS
    };
    let arch = if cfg!(target_arch = "aarch64") {
        "arm64"
    } else {
        std::env::consts::ARCH
    };
    let target = format!("{os}-{arch}");
    let legacy = &*LEGACY;
    let platforms = &*PLATFORMS;
    let signed = read_json(&metadata.join("signed-payload.json"))?;
    let platform = &platforms["targets"][&target];
    let archive = format!(
        "avid-ffmpeg-{}-r{}-{target}.tar.gz",
        platform["version"].as_str().ok_or_else(unavailable)?,
        platform["recipe"].as_u64().ok_or_else(unavailable)?
    );
    let source = format!(
        "avid-ffmpeg-{}-r{}-{target}-sources.tar.gz",
        platform["version"].as_str().ok_or_else(unavailable)?,
        platform["recipe"].as_u64().ok_or_else(unavailable)?
    );
    let legacy_record = &legacy["targets"][&target];
    let platform_archive = &platform["assets"][&archive]["sha256"];
    let (record, build_revision, source_sha256) =
        if signed["original_runtime_archive_sha256"] == *platform_archive {
            (
                platform,
                &platform["build_revision"],
                &platform["assets"][&source]["sha256"],
            )
        } else if signed["original_runtime_archive_sha256"] == legacy_record["sha256"] {
            (
                legacy_record,
                &legacy["build_revision"],
                &legacy_record["source_sha256"],
            )
        } else {
            return Err(unavailable());
        };
    if hash(&metadata.join("SHA256SUMS"))?
        != record["checksums_sha256"]
            .as_str()
            .ok_or_else(unavailable)?
    {
        return Err(unavailable());
    }
    let mut files = HashMap::new();
    for line in fs::read_to_string(metadata.join("SHA256SUMS"))
        .map_err(|_| unavailable())?
        .lines()
    {
        let (digest, name) = line.split_once("  ").ok_or_else(unavailable)?;
        if digest.len() != 64
            || !digest.bytes().all(|b| b.is_ascii_hexdigit())
            || Path::new(name).is_absolute()
            || name.contains('\\')
            || name
                .split('/')
                .any(|p| p.is_empty() || p == "." || p == "..")
            || files.insert(name.to_owned(), digest.to_owned()).is_some()
        {
            return Err(unavailable());
        }
    }
    check_tree(&metadata, &metadata, &files)?;
    let ffmpeg_name = format!("ffmpeg{}", std::env::consts::EXE_SUFFIX);
    let ffprobe_name = format!("ffprobe{}", std::env::consts::EXE_SUFFIX);
    for (name, expected) in &files {
        if name != &ffmpeg_name && name != &ffprobe_name && hash(&metadata.join(name))? != *expected
        {
            return Err(unavailable());
        }
    }
    let spec = read_json(&metadata.join("spec.json"))?;
    let core_spec = &*CORE_SPEC;
    let build = read_json(&metadata.join("build.json"))?;
    let provenance = read_json(&metadata.join("ativ-runtime.json"))?;
    if spec != *core_spec
        || build["target"] != target
        || build["core_revision"] != *build_revision
        || build["core_worktree_modified"] != false
        || provenance
            != serde_json::json!({"schema":1,"owner":"AVID Core","ativ_version":ativ_core::VERSION,"avid_core":{"version":ativ_core::CORE_VERSION,"revision":ativ_core::CORE_REVISION,"source":ativ_core::CORE_SOURCE},"target":target})
        || signed["schema"] != 1
        || signed["target"] != target
        || hash(&metadata.join("corresponding-source.tar.gz"))?
            != source_sha256.as_str().ok_or_else(unavailable)?
    {
        return Err(unavailable());
    }
    let ffmpeg_expected = signed["signed_binary_sha256"][&ffmpeg_name]
        .as_str()
        .ok_or_else(unavailable)?;
    let ffprobe_expected = signed["signed_binary_sha256"][&ffprobe_name]
        .as_str()
        .ok_or_else(unavailable)?;
    if signed["original_binary_sha256"][&ffmpeg_name]
        != *files.get(&ffmpeg_name).ok_or_else(unavailable)?
        || signed["original_binary_sha256"][&ffprobe_name]
            != *files.get(&ffprobe_name).ok_or_else(unavailable)?
    {
        return Err(unavailable());
    }
    let (ffmpeg_hash, ffprobe_hash) = hash_pair(
        || hash(&binary.join(&ffmpeg_name)),
        || hash(&binary.join(&ffprobe_name)),
    )?;
    if ffmpeg_hash != ffmpeg_expected || ffprobe_hash != ffprobe_expected {
        return Err(unavailable());
    }
    Ok((
        binary.join(ffmpeg_name),
        binary.join(ffprobe_name),
        core_spec["source"]["version"]
            .as_str()
            .ok_or_else(unavailable)?
            .to_owned(),
    ))
}

pub fn resolve(
    ffmpeg: Option<PathBuf>,
    ffprobe: Option<PathBuf>,
    token: &CancellationToken,
) -> ativ_core::Result<MediaTools> {
    if token.is_cancelled() {
        return Err(AtivError::cancelled());
    }
    let (ffmpeg, ffprobe, version) = match (ffmpeg, ffprobe) {
        (Some(ffmpeg), Some(ffprobe)) if ffmpeg.is_absolute() && ffprobe.is_absolute() => {
            (ffmpeg, ffprobe, None)
        }
        (None, None) => {
            let (ffmpeg, ffprobe, version) = packaged_pair()?;
            (ffmpeg, ffprobe, Some(version))
        }
        _ => {
            return Err(AtivError::InvalidInput(
                "Development overrides require both --ffmpeg and --ffprobe absolute paths.".into(),
            ));
        }
    };
    // Complete installed Core runtimes retain Core's qualification metadata.
    // Signed application packages deliberately split metadata and executables;
    // packaged_pair() verifies that derivative before its explicit pair is loaded.
    let tools = load_pair(&ffmpeg, &ffprobe, token)?;
    if let Some(version) = version
        && (tools.ffmpeg_version().split_whitespace().nth(2) != Some(version.as_str())
            || tools.ffprobe_version().split_whitespace().nth(2) != Some(version.as_str()))
    {
        return Err(unavailable());
    }
    Ok(tools)
}

fn has_core_metadata(directory: &Path) -> ativ_core::Result<bool> {
    for name in [
        "SHA256SUMS",
        "spec.json",
        "build.json",
        "validation.json",
        "repeat-build.json",
        "source-provenance.json",
        "core-tests-passed.txt",
    ] {
        match fs::symlink_metadata(directory.join(name)) {
            Ok(_) => return Ok(true),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err(unavailable()),
        }
    }
    Ok(false)
}

fn load_pair(
    ffmpeg: &Path,
    ffprobe: &Path,
    token: &CancellationToken,
) -> ativ_core::Result<MediaTools> {
    let expected_ffmpeg = format!("ffmpeg{}", std::env::consts::EXE_SUFFIX);
    let expected_ffprobe = format!("ffprobe{}", std::env::consts::EXE_SUFFIX);
    if let Some(directory) = ffmpeg.parent()
        && ffprobe.parent() == Some(directory)
        && ffmpeg
            .file_name()
            .is_some_and(|name| name == expected_ffmpeg.as_str())
        && ffprobe
            .file_name()
            .is_some_and(|name| name == expected_ffprobe.as_str())
        && has_core_metadata(directory)?
    {
        // A damaged complete runtime must fail closed, never retry as an
        // unqualified pair. The host acquisition authenticates its origin.
        return Ok(MediaTools::from_core_directory(directory, token)?);
    }
    Ok(MediaTools::from_paths(ffmpeg, ffprobe, token)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_is_fixed_lowercase_and_preserves_leading_zeros() {
        for seed in 0..=255u8 {
            let bytes = std::array::from_fn(|i| seed.wrapping_add(i as u8));
            assert_eq!(
                hex_digest(&bytes),
                bytes.iter().map(|b| format!("{b:02x}")).collect::<String>()
            );
            assert_eq!(hex_digest(&bytes).len(), 64);
        }
        assert_eq!(hex_digest(&[0; 32]), "0".repeat(64));
    }

    #[test]
    fn both_workers_finish_even_when_either_fails_or_panics() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        for failed in 0..2 {
            for panics in [false, true] {
                let count = AtomicUsize::new(0);
                let worker = |index| {
                    count.fetch_add(1, Ordering::SeqCst);
                    if index == failed {
                        if panics {
                            panic!("injected hash failure");
                        }
                        return Err(unavailable());
                    }
                    Ok("digest".into())
                };
                assert!(hash_pair(|| worker(0), || worker(1)).is_err());
                assert_eq!(count.load(Ordering::SeqCst), 2);
            }
        }
        assert_eq!(
            hash_pair(|| Ok("first".into()), || Ok("second".into())).unwrap(),
            ("first".into(), "second".into())
        );
    }

    #[test]
    fn tree_rejects_unlisted_entries_and_symlinks() {
        let directory = std::env::temp_dir().join(format!(
            "ativ-tree-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(directory.join("nested")).unwrap();
        fs::write(directory.join("nested/known"), b"payload").unwrap();
        let files = HashMap::from([("nested/known".into(), "hash".into())]);
        assert!(check_tree(&directory, &directory, &files).is_ok());
        fs::write(directory.join("unknown"), b"payload").unwrap();
        assert!(check_tree(&directory, &directory, &files).is_err());
        fs::remove_file(directory.join("unknown")).unwrap();
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(directory.join("nested"), directory.join("link")).unwrap();
            assert!(check_tree(&directory, &directory, &files).is_err());
            fs::remove_file(directory.join("link")).unwrap();
            std::os::unix::fs::symlink(directory.join("missing"), directory.join("broken"))
                .unwrap();
            assert!(check_tree(&directory, &directory, &files).is_err());
        }
        assert!(check_tree(&directory, &directory.join("absent"), &files).is_err());
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn damaged_complete_runtime_does_not_fall_back_to_unqualified_pair() {
        let directory = std::env::temp_dir().join(format!(
            "ativ-core-runtime-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&directory).unwrap();
        fs::write(directory.join("SHA256SUMS"), b"damaged manifest\n").unwrap();
        // No executable exists: reaching ordinary from_paths would produce an
        // executable lookup error instead of Core's manifest validation error.
        let error = load_pair(
            &directory.join(format!("ffmpeg{}", std::env::consts::EXE_SUFFIX)),
            &directory.join(format!("ffprobe{}", std::env::consts::EXE_SUFFIX)),
            &CancellationToken::default(),
        )
        .unwrap_err();
        assert_eq!(error.code(), "media_tools_unavailable");
        assert!(format!("{error:?}").contains("Invalid checksum entry"));
        // Removing a damaged manifest must not turn an installed runtime into
        // a development pair while Core metadata remains.
        fs::remove_file(directory.join("SHA256SUMS")).unwrap();
        fs::write(directory.join("spec.json"), b"{}").unwrap();
        let error = load_pair(
            &directory.join(format!("ffmpeg{}", std::env::consts::EXE_SUFFIX)),
            &directory.join(format!("ffprobe{}", std::env::consts::EXE_SUFFIX)),
            &CancellationToken::default(),
        )
        .unwrap_err();
        assert!(format!("{error:?}").contains("read Core runtime checksums"));
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn cancellation_before_resolution_retains_cancelled_error() {
        let token = CancellationToken::default();
        token.cancel();
        let error = match resolve(None, None, &token) {
            Err(error) => error,
            Ok(_) => panic!("A cancelled request must not resolve media tools"),
        };
        assert_eq!(error.code(), "cancelled");
    }
}
