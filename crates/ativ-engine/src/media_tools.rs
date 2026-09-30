//! ATIV owns runtime identity and layout; the existing Core API executes the selected pair.
use ativ_core::{AtivError, CancellationToken, MediaTools};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::LazyLock;

const DEPENDENCY: &str = include_str!("../../../runtime/ffmpeg/dependency.json");

static RECIPE_HASH: LazyLock<String> = LazyLock::new(|| {
    let mut hash = Sha256::new();
    hash.update(DEPENDENCY.as_bytes());
    hash.update(include_bytes!("../../../runtime/ffmpeg/release-key.asc"));
    hash.update(include_bytes!("../../../script/ffmpeg_build.py"));
    hash.update(include_bytes!("../../../script/ffmpeg_runtime.py"));
    format!("{:x}", hash.finalize())
});

fn unavailable() -> AtivError {
    AtivError::RuntimeUnavailable
}

fn read_json(path: &Path) -> ativ_core::Result<Value> {
    serde_json::from_slice(&fs::read(path).map_err(|_| unavailable())?).map_err(|_| unavailable())
}

fn stream_sha256(path: &Path) -> ativ_core::Result<String> {
    use std::io::Read;
    let mut file = fs::File::open(path).map_err(|_| unavailable())?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let n = file.read(&mut buffer).map_err(|_| unavailable())?;
        if n == 0 {
            break;
        }
        hasher.update(&buffer[..n]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

pub fn resolve(
    ffmpeg: Option<PathBuf>,
    ffprobe: Option<PathBuf>,
    token: &CancellationToken,
) -> ativ_core::Result<MediaTools> {
    // Both explicit CLI paths are required for a deliberate development/test override.
    // No environment override or PATH search can affect packaged discovery.
    let packaged = ffmpeg.is_none() && ffprobe.is_none();
    let expected: Value =
        serde_json::from_str(DEPENDENCY).expect("embedded FFmpeg dependency record");
    let (ffmpeg, ffprobe) = match (ffmpeg, ffprobe) {
        (Some(ffmpeg), Some(ffprobe)) => (ffmpeg, ffprobe),
        (None, None) => {
            let executable = std::env::current_exe().map_err(|_| unavailable())?;
            let directory = executable.parent().ok_or_else(unavailable)?;
            let metadata = if cfg!(target_os = "macos")
                && directory.file_name().is_some_and(|n| n == "MacOS")
                && directory
                    .parent()
                    .and_then(|p| p.file_name())
                    .is_some_and(|n| n == "Contents")
            {
                directory.join("../Resources/FFmpeg")
            } else {
                directory.to_owned()
            };
            if fs::read(metadata.join("dependency.json")).map_err(|_| unavailable())?
                != DEPENDENCY.as_bytes()
            {
                return Err(unavailable());
            }
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
            let build_bytes = fs::read(metadata.join("build.json")).map_err(|_| unavailable())?;
            let build_hash = format!("{:x}", Sha256::digest(&build_bytes));
            let build: Value = serde_json::from_slice(&build_bytes).map_err(|_| unavailable())?;
            let manifest = read_json(&metadata.join("payload.json"))?;
            let signed = read_json(&metadata.join("signed-payload.json"))?;
            let provenance = read_json(&metadata.join("ativ-runtime.json"))?;
            if build["recipe_sha256"] != *RECIPE_HASH
                || provenance["recipe_sha256"] != build["recipe_sha256"]
                || provenance["architecture"] != arch
                || build["owner"] != "ATIV"
                || build["target"] != target
                || signed["target"] != target
                || provenance["owner"] != "ATIV"
                || provenance["avid_core"]["version"] != ativ_core::CORE_VERSION
                || provenance["avid_core"]["revision"] != ativ_core::CORE_REVISION
                || provenance["avid_core"]["source"] != ativ_core::CORE_SOURCE
                || provenance["target"] != target
                || provenance["ffmpeg_version"] != expected["source"]["version"]
                || manifest["build.json"] != build_hash
                || signed["original_binary_sha256"] != build["binary_sha256"]
            {
                return Err(unavailable());
            }
            let check_binary = |name: &str| -> ativ_core::Result<PathBuf> {
                let filename = format!("{name}{}", std::env::consts::EXE_SUFFIX);
                let path = directory.join(&filename);
                let actual_hash = stream_sha256(&path)?;
                if manifest[&filename] != build["binary_sha256"][&filename]
                    || signed["signed_binary_sha256"][&filename] != actual_hash
                {
                    return Err(unavailable());
                }
                Ok(path)
            };
            std::thread::scope(|s| {
                let ffmpeg_handle = s.spawn(|| check_binary("ffmpeg"));
                let ffprobe_handle = s.spawn(|| check_binary("ffprobe"));
                let p1 = ffmpeg_handle.join().map_err(|_| unavailable())??;
                let p2 = ffprobe_handle.join().map_err(|_| unavailable())??;
                Ok::<_, AtivError>((p1, p2))
            })?
        }
        _ => {
            return Err(AtivError::InvalidInput(
                "Development overrides require both --ffmpeg and --ffprobe paths.".into(),
            ));
        }
    };
    let tools = MediaTools::from_paths(ffmpeg, ffprobe, token)?;
    if packaged
        && tools.ffmpeg_version().split_whitespace().nth(2)
            != expected["source"]["version"].as_str()
    {
        return Err(unavailable());
    }
    Ok(tools)
}
