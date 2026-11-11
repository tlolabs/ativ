//! Core runtime identity and filesystem lifecycle helpers.
use crate::{CancellationToken, Error, MediaTools, Result};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
    time::Duration,
};

/// Recipe and hashes of one validated Core source build.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CoreRuntimeInfo {
    pub version: String,
    pub source_revision: String,
    pub recipe: u64,
    pub target: String,
    pub core_revision: String,
    pub ffmpeg_sha256: String,
    pub ffprobe_sha256: String,
}

/// The pinned source and recipe shipped with this Core revision.
pub const FFMPEG_RUNTIME_SPECIFICATION: &str = include_str!("../runtime/ffmpeg/spec.json");

fn invalid(detail: impl Into<String>) -> Error {
    Error::ToolUnavailable {
        tool: "Core FFmpeg runtime",
        detail: detail.into(),
    }
}

fn read_json(path: &Path) -> Result<Value> {
    let bytes = fs::read(path).map_err(|e| Error::io("read Core runtime metadata", path, e))?;
    serde_json::from_slice(&bytes).map_err(|e| invalid(format!("Invalid {}: {e}", path.display())))
}

fn hash(path: &Path) -> Result<String> {
    let mut file =
        fs::File::open(path).map_err(|e| Error::io("read Core runtime file", path, e))?;
    let mut digest = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let n = file
            .read(&mut buffer)
            .map_err(|e| Error::io("read Core runtime file", path, e))?;
        if n == 0 {
            break;
        }
        digest.update(&buffer[..n]);
    }
    use std::fmt::Write;
    let mut hex = String::with_capacity(64);
    for byte in digest.finalize() {
        write!(&mut hex, "{byte:02x}").expect("writing to a String cannot fail");
    }
    Ok(hex)
}

fn native_target() -> String {
    let os = if cfg!(target_os = "macos") {
        "macos"
    } else if cfg!(windows) {
        "windows"
    } else {
        "linux"
    };
    let arch = if cfg!(target_arch = "aarch64") {
        "arm64"
    } else {
        std::env::consts::ARCH
    };
    format!("{os}-{arch}")
}

fn checked_file(root: &Path, relative: &str, expected: &str) -> Result<PathBuf> {
    if relative.is_empty()
        || relative
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
        || relative.contains('\\')
    {
        return Err(invalid("Unsafe runtime checksum path"));
    }
    let path = root.join(relative);
    let metadata = fs::symlink_metadata(&path)
        .map_err(|e| Error::io("inspect Core runtime file", &path, e))?;
    if !metadata.is_file() || hash(&path)? != expected {
        return Err(invalid(format!(
            "Runtime file changed or is not regular: {relative}"
        )));
    }
    Ok(path)
}

fn verify_checksums(root: &Path) -> Result<std::collections::HashMap<String, String>> {
    let path = root.join("SHA256SUMS");
    let lines = fs::read_to_string(&path)
        .map_err(|e| Error::io("read Core runtime checksums", &path, e))?;
    let mut verified = std::collections::HashMap::new();
    for line in lines.lines() {
        let (expected, relative) = line
            .split_once("  ")
            .ok_or_else(|| invalid("Invalid checksum entry"))?;
        if expected.len() != 64
            || !expected.bytes().all(|b| b.is_ascii_hexdigit())
            || verified.contains_key(relative)
            || relative == "SHA256SUMS"
        {
            return Err(invalid("Invalid or duplicate checksum entry"));
        }
        checked_file(root, relative, expected)?;
        verified.insert(relative.to_owned(), expected.to_ascii_lowercase());
    }
    fn visit(
        root: &Path,
        directory: &Path,
        listed: &std::collections::HashMap<String, String>,
    ) -> Result<()> {
        for entry in
            fs::read_dir(directory).map_err(|e| Error::io("list Core runtime", directory, e))?
        {
            let entry = entry.map_err(|e| Error::io("list Core runtime", directory, e))?;
            let path = entry.path();
            let meta = fs::symlink_metadata(&path)
                .map_err(|e| Error::io("inspect Core runtime", &path, e))?;
            if meta.is_dir() {
                visit(root, &path, listed)?;
            } else if !meta.is_file() {
                return Err(invalid("Runtime contains a link or special file"));
            } else if path != root.join("SHA256SUMS") {
                let relative = path
                    .strip_prefix(root)
                    .map_err(|_| invalid("Invalid runtime path"))?
                    .to_string_lossy()
                    .replace('\\', "/");
                if !listed.contains_key(&relative) {
                    return Err(invalid(format!("Unlisted runtime file: {relative}")));
                }
            }
        }
        Ok(())
    }
    visit(root, root, &verified)?;
    Ok(verified)
}

impl MediaTools {
    /// Load the complete Core-built pair from a single validated directory.
    /// No PATH or application bundle discovery occurs. The caller must obtain
    /// the archive through a trusted channel; internal checksums detect changes
    /// after acquisition, not the authenticity of the channel itself.
    pub fn from_core_directory(directory: &Path, token: &CancellationToken) -> Result<Self> {
        token.check()?;
        let root = fs::canonicalize(directory)
            .map_err(|e| Error::io("resolve Core runtime", directory, e))?;
        let verified_hashes = verify_checksums(&root)?;
        let spec: Value = serde_json::from_str(FFMPEG_RUNTIME_SPECIFICATION)
            .expect("checked-in FFmpeg specification");
        if read_json(&root.join("spec.json"))? != spec {
            return Err(invalid("Runtime specification differs from Core"));
        }
        let spec_hash = verified_hashes
            .get("spec.json")
            .ok_or_else(|| invalid("Missing spec.json checksum"))?;
        let build = read_json(&root.join("build.json"))?;
        let validation = read_json(&root.join("validation.json"))?;
        let provenance = read_json(&root.join("source-provenance.json"))?;
        let repeat = read_json(&root.join("repeat-build.json"))?;
        let target = native_target();
        if build["target"] != target
            || build["recipe"] != spec["recipe"]
            || build["version"] != spec["source"]["version"]
            || build["source_revision"] != spec["source"]["revision"]
            || build["spec_sha256"] != *spec_hash
            || provenance["status"] != "passed"
            || provenance["source_revision"] != spec["source"]["revision"]
            || provenance["archive_sha256"] != spec["source"]["sha256"]
            || validation["target"] != target
            || validation["baseline"] != false
            || !validation["smoke"].is_object()
            || !validation["linkage"].is_string()
            || repeat["status"] != "passed"
            || repeat["target"] != target
            || repeat["core_revision"] != build["core_revision"]
        {
            return Err(invalid(
                "Runtime source, target, build or qualification evidence differs from Core",
            ));
        }
        if !root.join("core-tests-passed.txt").is_file() {
            return Err(invalid("Core test evidence missing"));
        }
        let suffix = if cfg!(windows) { ".exe" } else { "" };
        let ffmpeg_name = format!("ffmpeg{suffix}");
        let ffprobe_name = format!("ffprobe{suffix}");
        let ffmpeg_hash = verified_hashes
            .get(&ffmpeg_name)
            .ok_or_else(|| invalid("Missing ffmpeg checksum"))?;
        let ffprobe_hash = verified_hashes
            .get(&ffprobe_name)
            .ok_or_else(|| invalid("Missing ffprobe checksum"))?;
        for (name, actual) in [(&ffmpeg_name, ffmpeg_hash), (&ffprobe_name, ffprobe_hash)] {
            if validation["binary_sha256"][name] != *actual
                || repeat["binary_sha256"][name]["first"] != *actual
                || repeat["binary_sha256"][name]["second"] != *actual
            {
                return Err(invalid(format!(
                    "{name} does not match the validated Core build"
                )));
            }
        }
        let mut tools = Self::from_paths(root.join(&ffmpeg_name), root.join(&ffprobe_name), token)?;
        if tools.ffmpeg_version().split_whitespace().nth(2) != spec["source"]["version"].as_str()
            || tools.ffprobe_version().split_whitespace().nth(2)
                != spec["source"]["version"].as_str()
            || validation["ffmpeg_version"] != tools.ffmpeg_version()
            || validation["ffprobe_version"] != tools.ffprobe_version()
        {
            return Err(invalid("Executable version differs from validated source"));
        }
        let info = CoreRuntimeInfo {
            version: spec["source"]["version"].as_str().unwrap().to_owned(),
            source_revision: spec["source"]["revision"].as_str().unwrap().to_owned(),
            recipe: spec["recipe"].as_u64().unwrap(),
            target,
            core_revision: build["core_revision"]
                .as_str()
                .ok_or_else(|| invalid("Missing Core revision"))?
                .to_owned(),
            ffmpeg_sha256: ffmpeg_hash.clone(),
            ffprobe_sha256: ffprobe_hash.clone(),
        };
        tools.attach_core_runtime(info);
        Ok(tools)
    }
}

/// Move a caller-owned runtime directory, allowing transient Windows readers to close.
///
/// Before calling, the host must stop new operations, cancel or finish active ones,
/// join its worker threads, and serialize runtime updates. This does not stop users
/// of the runtime, authenticate a package, or replace an application's update transaction.
/// The destination should be a new path on the same volume (for example a rollback
/// directory). Rename remains atomic; no copy/delete fallback is performed.
///
/// The first attempt is immediate. On Windows only, access-denied, sharing-violation
/// and lock-violation errors can be retried for at most `max_wait` between attempts.
/// Other errors fail immediately. A persistent lock still fails. `Duration::ZERO`
/// requests one attempt. Two seconds accommodates the measured sub-second hosted
/// runner executable reads; applications may choose a different bounded policy.
/// Other operating systems perform one ordinary filesystem rename.
pub fn move_runtime_directory(
    source: &Path,
    destination: &Path,
    max_wait: Duration,
) -> std::io::Result<()> {
    runtime_directory_operation(|| std::fs::rename(source, destination), max_wait)
}

/// Remove a caller-owned obsolete runtime, with the same Windows wait policy as
/// [`move_runtime_directory`]. Removal is not atomic and can be partial on error;
/// keep the active runtime and any required rollback copy in separate directories.
pub fn remove_runtime_directory(directory: &Path, max_wait: Duration) -> std::io::Result<()> {
    runtime_directory_operation(|| std::fs::remove_dir_all(directory), max_wait)
}

fn runtime_directory_operation(
    mut operation: impl FnMut() -> std::io::Result<()>,
    max_wait: Duration,
) -> std::io::Result<()> {
    #[cfg(not(windows))]
    {
        let _ = max_wait;
        operation()
    }
    #[cfg(windows)]
    {
        let started = std::time::Instant::now();
        let mut interval = Duration::from_millis(5);
        #[cfg(feature = "lifecycle-diagnostics")]
        let mut retries = 0u32;
        loop {
            match operation() {
                Ok(()) => {
                    #[cfg(feature = "lifecycle-diagnostics")]
                    if retries > 0 {
                        eprintln!(
                            "runtime_directory_recovered retries={retries} elapsed_ms={}",
                            started.elapsed().as_millis()
                        );
                    }
                    return Ok(());
                }
                Err(error) => {
                    if !matches!(error.raw_os_error(), Some(5 | 32 | 33)) {
                        return Err(error);
                    }
                    let Some(remaining) = max_wait.checked_sub(started.elapsed()) else {
                        return Err(error);
                    };
                    if remaining.is_zero() {
                        return Err(error);
                    }
                    #[cfg(feature = "lifecycle-diagnostics")]
                    {
                        retries += 1;
                        eprintln!(
                            "runtime_directory_retry attempt={retries} os_error={}",
                            error.raw_os_error().unwrap()
                        );
                    }
                    std::thread::sleep(interval.min(remaining));
                    // Never issue another filesystem operation after the wait budget.
                    if started.elapsed() >= max_wait {
                        return Err(error);
                    }
                    interval = (interval * 2).min(Duration::from_millis(50));
                }
            }
        }
    }
}
