//! Windows filesystem contract using a separate reader process, not a mock.
#![cfg(windows)]
use avid_core::{move_runtime_directory, remove_runtime_directory};
use std::{
    fs,
    io::{BufRead, BufReader, Read, Write},
    os::windows::fs::OpenOptionsExt,
    path::Path,
    process::{Child, ChildStdout, Command, Stdio},
    time::{Duration, Instant},
};

#[test]
#[ignore = "internal subprocess fixture invoked only by the lock tests"]
fn held_runtime_reader() {
    let Some(path) = std::env::var_os("AVID_TEST_LOCK_FILE") else {
        return;
    };
    let share: u32 = std::env::var("AVID_TEST_LOCK_SHARE")
        .unwrap()
        .parse()
        .unwrap();
    let file = fs::OpenOptions::new()
        .read(true)
        .share_mode(share)
        .open(path)
        .unwrap();
    println!("runtime-reader-ready");
    std::io::stdout().flush().unwrap();
    let mut release = Vec::new();
    std::io::stdin().read_to_end(&mut release).unwrap();
    drop(file);
}
struct Reader {
    child: Child,
    _output: BufReader<ChildStdout>,
}
impl Reader {
    fn start(path: &Path, share: u32) -> Self {
        let mut child = Command::new(std::env::current_exe().unwrap())
            .args(["--ignored", "--exact", "held_runtime_reader", "--nocapture"])
            .env("AVID_TEST_LOCK_FILE", path)
            .env("AVID_TEST_LOCK_SHARE", share.to_string())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let output = BufReader::new(child.stdout.take().unwrap());
        let mut reader = Self {
            child,
            _output: output,
        };
        let mut line = String::new();
        loop {
            line.clear();
            assert!(
                reader._output.read_line(&mut line).unwrap() > 0,
                "reader exited before acquiring lock"
            );
            if line.contains("runtime-reader-ready") {
                break;
            }
        }
        reader
    }
    fn release(&mut self) {
        drop(self.child.stdin.take());
    }
    fn wait(&mut self) {
        assert!(self.child.wait().unwrap().success());
    }
}
impl Drop for Reader {
    fn drop(&mut self) {
        self.release();
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
#[test]
fn move_rejects_persistent_reader_then_succeeds_after_release() {
    let root = tempfile::tempdir().unwrap();
    let source = root.path().join("runtime");
    let destination = root.path().join("backup");
    fs::create_dir(&source).unwrap();
    let file = source.join("ffmpeg.exe");
    fs::write(&file, b"controlled runtime fixture").unwrap();
    // Same read/write/delete sharing as an ordinary cooperative external reader.
    let mut reader = Reader::start(&file, 7);
    assert_eq!(
        fs::rename(&source, &destination)
            .unwrap_err()
            .raw_os_error(),
        Some(5)
    );
    assert_eq!(
        move_runtime_directory(&source, &destination, Duration::ZERO)
            .unwrap_err()
            .raw_os_error(),
        Some(5)
    );
    let began = Instant::now();
    assert_eq!(
        move_runtime_directory(&source, &destination, Duration::from_millis(100))
            .unwrap_err()
            .raw_os_error(),
        Some(5)
    );
    assert!(began.elapsed() < Duration::from_secs(5));
    assert_eq!(fs::read(&file).unwrap(), b"controlled runtime fixture");
    assert!(!destination.exists());
    // Signal asynchronous cleanup; do not wait for the reader before attempting move.
    reader.release();
    move_runtime_directory(&source, &destination, Duration::from_secs(2)).unwrap();
    reader.wait();
    assert_eq!(
        fs::read(destination.join("ffmpeg.exe")).unwrap(),
        b"controlled runtime fixture"
    );
    remove_runtime_directory(&destination, Duration::ZERO).unwrap();
}
#[test]
fn removal_rejects_persistent_reader_and_nontransient_errors_are_preserved() {
    let root = tempfile::tempdir().unwrap();
    let directory = root.path().join("runtime");
    fs::create_dir(&directory).unwrap();
    let file = directory.join("ffmpeg.exe");
    fs::write(&file, b"controlled runtime fixture").unwrap();
    let mut reader = Reader::start(&file, 1); // Explicitly deny delete sharing.
    assert!(remove_runtime_directory(&directory, Duration::from_millis(100)).is_err());
    assert!(file.exists());
    reader.release();
    remove_runtime_directory(&directory, Duration::from_secs(2)).unwrap();
    reader.wait();
    let error = move_runtime_directory(
        &directory,
        &root.path().join("missing"),
        Duration::from_secs(2),
    )
    .unwrap_err();
    assert_eq!(error.kind(), std::io::ErrorKind::NotFound);
}
