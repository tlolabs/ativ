#[cfg(unix)]
use avid_core::FFMPEG_RUNTIME_SPECIFICATION;
use avid_core::{CancellationToken, MediaTools};
#[cfg(unix)]
use serde_json::json;
use serde_json::Value;
#[cfg(unix)]
use sha2::{Digest, Sha256};
#[cfg(unix)]
use std::{fs, path::Path};

#[cfg(unix)]
fn digest(path: &Path) -> String {
    use std::fmt::Write;
    let mut hex = String::with_capacity(64);
    for byte in Sha256::digest(fs::read(path).unwrap()) {
        write!(&mut hex, "{byte:02x}").unwrap();
    }
    hex
}

#[cfg(unix)]
fn checksums(root: &Path) {
    let mut names: Vec<_> = fs::read_dir(root)
        .unwrap()
        .map(|entry| entry.unwrap().file_name().into_string().unwrap())
        .filter(|name| name != "SHA256SUMS")
        .collect();
    names.sort();
    let text = names
        .iter()
        .map(|name| format!("{}  {name}\n", digest(&root.join(name))))
        .collect::<String>();
    fs::write(root.join("SHA256SUMS"), text).unwrap();
}

#[cfg(unix)]
#[test]
fn core_pair_is_atomic_and_rejects_missing_or_changed_probe() {
    use std::os::unix::fs::PermissionsExt;
    let root = tempfile::tempdir().unwrap();
    let directory = root.path();
    let spec: Value = serde_json::from_str(FFMPEG_RUNTIME_SPECIFICATION).unwrap();
    fs::write(directory.join("spec.json"), FFMPEG_RUNTIME_SPECIFICATION).unwrap();
    for tool in ["ffmpeg", "ffprobe"] {
        let path = directory.join(tool);
        fs::write(&path, format!("#!/bin/sh\necho '{tool} version 9.0.1'\n")).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o755)).unwrap();
    }
    let target = format!(
        "{}-{}",
        std::env::consts::OS,
        if cfg!(target_arch = "aarch64") {
            "arm64"
        } else {
            std::env::consts::ARCH
        }
    );
    let ffmpeg_hash = digest(&directory.join("ffmpeg"));
    let ffprobe_hash = digest(&directory.join("ffprobe"));
    let hashes = json!({"ffmpeg":ffmpeg_hash, "ffprobe":ffprobe_hash});
    let repeats = json!({"ffmpeg":{"first":ffmpeg_hash,"second":ffmpeg_hash},
                         "ffprobe":{"first":ffprobe_hash,"second":ffprobe_hash}});
    fs::write(directory.join("build.json"), json!({
        "target":target, "recipe":spec["recipe"], "version":spec["source"]["version"],
        "source_revision":spec["source"]["revision"], "spec_sha256":digest(&directory.join("spec.json")),
        "core_revision":"test-revision"}).to_string()).unwrap();
    fs::write(
        directory.join("source-provenance.json"),
        json!({
        "status":"passed", "source_revision":spec["source"]["revision"],
        "archive_sha256":spec["source"]["sha256"]})
        .to_string(),
    )
    .unwrap();
    fs::write(
        directory.join("validation.json"),
        json!({
        "target":target, "baseline":false, "smoke":{"media":"passed"}, "linkage":"system",
        "binary_sha256":hashes, "ffmpeg_version":"ffmpeg version 9.0.1",
        "ffprobe_version":"ffprobe version 9.0.1"})
        .to_string(),
    )
    .unwrap();
    fs::write(
        directory.join("repeat-build.json"),
        json!({
        "status":"passed", "target":target, "core_revision":"test-revision",
        "binary_sha256":repeats})
        .to_string(),
    )
    .unwrap();
    fs::write(directory.join("core-tests-passed.txt"), "passed\n").unwrap();
    checksums(directory);
    let token = CancellationToken::default();
    let tools = MediaTools::from_core_directory(directory, &token).unwrap();
    let info = tools.core_runtime().unwrap();
    assert_eq!(info.ffmpeg_sha256, ffmpeg_hash);
    assert_eq!(info.ffprobe_sha256, ffprobe_hash);
    fs::remove_file(directory.join("ffprobe")).unwrap();
    assert!(MediaTools::from_core_directory(directory, &token).is_err());
    fs::write(directory.join("ffprobe"), b"different build").unwrap();
    checksums(directory);
    assert!(MediaTools::from_core_directory(directory, &token).is_err());
}

#[test]
fn empty_core_directory_does_not_search_path() {
    let root = tempfile::tempdir().unwrap();
    assert!(MediaTools::from_core_directory(root.path(), &CancellationToken::default()).is_err());
}

#[test]
#[ignore = "requires a packaged AVID_RUNTIME_DIRECTORY from the Core native build"]
fn packaged_core_pair_executes_and_inspects_media() {
    use std::process::Command;
    let directory = std::path::PathBuf::from(std::env::var_os("AVID_RUNTIME_DIRECTORY").unwrap());
    let tools = MediaTools::from_core_directory(&directory, &CancellationToken::default()).unwrap();
    let info = tools.core_runtime().unwrap();
    assert_eq!(info.version, "9.0.1");
    let output = tempfile::tempdir().unwrap();
    let wav = output.path().join("tone.wav");
    let encoded = Command::new(tools.ffmpeg())
        .args([
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:a",
            "pcm_s16le",
        ])
        .arg(&wav)
        .output()
        .unwrap();
    assert!(
        encoded.status.success(),
        "{}",
        String::from_utf8_lossy(&encoded.stderr)
    );
    let probed = Command::new(tools.ffprobe())
        .args([
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
        ])
        .arg(&wav)
        .output()
        .unwrap();
    assert!(
        probed.status.success(),
        "{}",
        String::from_utf8_lossy(&probed.stderr)
    );
    let metadata: Value = serde_json::from_slice(&probed.stdout).unwrap();
    let stream = &metadata["streams"][0];
    assert_eq!(stream["codec_type"], "audio");
    assert_eq!(stream["codec_name"], "pcm_s16le");
    assert_eq!(stream["sample_rate"], "44100");
    assert_eq!(stream["channels"], 1);
    assert!(
        (metadata["format"]["duration"]
            .as_str()
            .unwrap()
            .parse::<f64>()
            .unwrap()
            - 1.0)
            .abs()
            < 0.01
    );
}
