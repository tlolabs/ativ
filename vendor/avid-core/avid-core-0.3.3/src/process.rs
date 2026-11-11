use crate::{Error, EventSink, ProcessFailure, Progress, Result};
use std::{
    collections::VecDeque,
    ffi::OsString,
    io::{self, Read},
    path::Path,
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc,
    },
    thread,
    time::{Duration, Instant},
};

#[derive(Clone, Debug, Default)]
pub struct CancellationToken(Arc<AtomicBool>);
impl CancellationToken {
    pub fn cancel(&self) {
        self.0.store(true, Ordering::Release);
    }
    pub fn is_cancelled(&self) -> bool {
        self.0.load(Ordering::Acquire)
    }
    pub(crate) fn check(&self) -> Result<()> {
        if self.is_cancelled() {
            Err(Error::Cancelled)
        } else {
            Ok(())
        }
    }
}
impl From<Arc<AtomicBool>> for CancellationToken {
    fn from(flag: Arc<AtomicBool>) -> Self {
        Self(flag)
    }
}
pub(crate) struct RunOptions<'a> {
    pub operation: &'static str,
    pub timeout: Option<Duration>,
    pub progress_duration: Option<f64>,
    pub parse_progress: bool,
    pub events: &'a dyn EventSink,
}
#[cfg(feature = "lifecycle-diagnostics")]
struct ChildTrace(u32);
#[cfg(feature = "lifecycle-diagnostics")]
impl Drop for ChildTrace {
    fn drop(&mut self) {
        // Declared before OwnedChild; Child and its OS handle have dropped first.
        eprintln!("core_child_resources_dropped pid={}", self.0);
    }
}
struct OwnedChild(Child);
impl Drop for OwnedChild {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let result = self.0.wait();
        #[cfg(feature = "lifecycle-diagnostics")]
        eprintln!(
            "core_child_final_wait pid={} result={result:?}",
            self.0.id()
        );
        let _ = result;
    }
}
// Declared before OwnedChild so unwinding first kills/reaps the child, then
// closes both reader threads. A dropped JoinHandle alone would detach a reader.
#[derive(Default)]
struct OutputReaders {
    stdout: Option<thread::JoinHandle<io::Result<Capture>>>,
    stderr: Option<thread::JoinHandle<io::Result<Capture>>>,
}
impl Drop for OutputReaders {
    fn drop(&mut self) {
        for reader in [&mut self.stdout, &mut self.stderr] {
            if let Some(reader) = reader.take() {
                let _ = reader.join();
            }
        }
    }
}
struct Capture {
    bytes: Vec<u8>,
    truncated: bool,
}
const STDOUT_LIMIT: usize = 4 * 1024 * 1024;
const STDERR_LIMIT: usize = 64 * 1024;
// Drain concurrently without blocking on events, even when a tool emits a line without a newline.
fn drain(
    mut reader: impl Read,
    limit: usize,
    progress: Option<(mpsc::SyncSender<Progress>, Option<f64>)>,
) -> io::Result<Capture> {
    // Retain the diagnostic tail without shifting it on every overflow read.
    let mut bytes = VecDeque::new();
    let mut truncated = false;
    let mut buffer = [0u8; 8192];
    let mut line = Vec::with_capacity(256);
    let mut tracker = crate::progress::ProgressTracker::default();
    loop {
        let n = match reader.read(&mut buffer) {
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            other => other?,
        };
        if n == 0 {
            break;
        }
        if bytes.len() + n > limit {
            truncated = true;
            let remove = (bytes.len() + n - limit).min(bytes.len());
            bytes.drain(..remove);
        }
        bytes.extend(&buffer[..n]);
        if let Some((sender, duration)) = &progress {
            for byte in &buffer[..n] {
                if *byte == b'\n' {
                    if let Ok(text) = std::str::from_utf8(&line) {
                        if let Some((key, value)) = text.trim().split_once('=') {
                            let key = key.trim();
                            let value = value.trim();
                            tracker.update(key, value);
                            if key == "progress" {
                                let _ = sender.try_send(tracker.progress(*duration));
                                tracker = crate::progress::ProgressTracker::default();
                            }
                        }
                    }
                    line.clear();
                } else if line.len() < 4096 {
                    line.push(*byte);
                }
            }
        }
    }
    Ok(Capture {
        bytes: bytes.into(),
        truncated,
    })
}
pub(crate) fn run(
    executable: &Path,
    args: &[OsString],
    token: &CancellationToken,
    options: RunOptions<'_>,
) -> Result<Vec<u8>> {
    token.check()?;
    let context = |status, stderr| {
        Box::new(ProcessFailure {
            operation: options.operation,
            executable: executable.to_path_buf(),
            arguments: args.to_vec(),
            status,
            stderr,
        })
    };
    let child = Command::new(executable)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|source| Error::Process {
            failure: context(None, String::new()),
            source: Some(source),
        })?;
    #[cfg(feature = "lifecycle-diagnostics")]
    let _trace = {
        eprintln!(
            "core_child_spawn pid={} executable={}",
            child.id(),
            match executable.file_name().and_then(|n| n.to_str()) {
                Some("ffmpeg" | "ffmpeg.exe") => "ffmpeg",
                Some("ffprobe" | "ffprobe.exe") => "ffprobe",
                _ => "<test-tool>",
            }
        );
        ChildTrace(child.id())
    };
    let mut readers = OutputReaders::default();
    let mut child = OwnedChild(child);
    let stdout = child.0.stdout.take().ok_or_else(|| Error::Process {
        failure: context(None, "stdout pipe unavailable".into()),
        source: None,
    })?;
    let stderr = child.0.stderr.take().ok_or_else(|| Error::Process {
        failure: context(None, "stderr pipe unavailable".into()),
        source: None,
    })?;
    let (sender, receiver) = mpsc::sync_channel(64);
    let progress = options
        .parse_progress
        .then_some((sender, options.progress_duration));
    let stdout_limit = if options.parse_progress {
        STDERR_LIMIT
    } else {
        STDOUT_LIMIT
    };
    readers.stdout = Some(thread::spawn(move || drain(stdout, stdout_limit, progress)));
    readers.stderr = Some(thread::spawn(move || drain(stderr, STDERR_LIMIT, None)));
    let started = Instant::now();
    let mut interrupted = None;
    let mut poll_interval = Duration::from_millis(1);
    let status = loop {
        // A continuously replenished queue must not starve child polling,
        // cancellation or deadlines. Delivery is deliberately coalesced/bounded.
        for progress in receiver.try_iter().take(64) {
            options.events.progress(progress);
        }
        if token.is_cancelled() {
            interrupted = Some(false);
            let _ = child.0.kill();
            break child.0.wait();
        }
        if options
            .timeout
            .is_some_and(|timeout| started.elapsed() >= timeout)
        {
            interrupted = Some(true);
            let _ = child.0.kill();
            break child.0.wait();
        }
        match child.0.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) => {
                thread::sleep(poll_interval);
                poll_interval = (poll_interval * 2).min(Duration::from_millis(20));
            }
            Err(source) => {
                let _ = child.0.kill();
                let _ = child.0.wait();
                break Err(source);
            }
        }
    };
    let joined = |handle: thread::JoinHandle<io::Result<Capture>>| {
        handle
            .join()
            .unwrap_or_else(|_| Err(io::Error::other("Output reader panicked")))
    };
    let stderr =
        joined(readers.stderr.take().expect("stderr reader spawned")).map_err(|source| {
            Error::Process {
                failure: context(status.as_ref().ok().copied(), String::new()),
                source: Some(source),
            }
        })?;
    let stderr = String::from_utf8_lossy(&stderr.bytes).into_owned();
    for line in stderr.lines() {
        options.events.diagnostic(line);
    }
    let stdout =
        joined(readers.stdout.take().expect("stdout reader spawned")).map_err(|source| {
            Error::Process {
                failure: context(status.as_ref().ok().copied(), stderr.clone()),
                source: Some(source),
            }
        })?;
    for progress in receiver.try_iter() {
        options.events.progress(progress);
    }
    #[cfg(feature = "lifecycle-diagnostics")]
    eprintln!(
        "core_child_readers_joined pid={} status={status:?}",
        child.0.id()
    );
    if interrupted == Some(false) || token.is_cancelled() {
        return Err(Error::Cancelled);
    }
    if interrupted == Some(true) {
        return Err(Error::Timeout(context(status.ok(), stderr)));
    }
    let status = status.map_err(|source| Error::Process {
        failure: context(None, stderr.clone()),
        source: Some(source),
    })?;
    if !status.success() {
        return Err(Error::Process {
            failure: context(Some(status), stderr),
            source: None,
        });
    }
    if stdout.truncated && !options.parse_progress {
        return Err(Error::CaptureLimit(context(Some(status), stderr)));
    }
    Ok(stdout.bytes)
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    fn execute(
        script: &str,
        token: &CancellationToken,
        timeout: Option<Duration>,
    ) -> Result<Vec<u8>> {
        run(
            Path::new("/bin/sh"),
            &["-c".into(), script.into()],
            token,
            RunOptions {
                operation: "test",
                timeout,
                progress_duration: None,
                parse_progress: false,
                events: &(),
            },
        )
    }
    #[test]
    fn cancellation_reaps_owned_child() {
        let token = CancellationToken::default();
        let other = token.clone();
        let start = Instant::now();
        let worker = thread::spawn(move || execute("exec sleep 10", &other, None));
        thread::sleep(Duration::from_millis(100));
        token.cancel();
        assert!(matches!(worker.join().unwrap(), Err(Error::Cancelled)));
        assert!(start.elapsed() < Duration::from_secs(2));
    }
    #[test]
    fn timeout_and_diagnostic_context() {
        assert!(matches!(
            execute(
                "exec sleep 10",
                &CancellationToken::default(),
                Some(Duration::from_millis(50))
            ),
            Err(Error::Timeout(_))
        ));
        match execute(
            "printf 'specific failure' >&2; exit 7",
            &CancellationToken::default(),
            None,
        )
        .unwrap_err()
        {
            Error::Process { failure, .. } => {
                assert_eq!(failure.status.unwrap().code(), Some(7));
                assert!(failure.stderr.contains("specific failure"));
                assert_eq!(failure.arguments.len(), 2);
            }
            e => panic!("{e:?}"),
        }
    }
    #[test]
    fn pipe_flood_is_bounded_and_does_not_deadlock() {
        let bytes = vec![b'x'; STDOUT_LIMIT + 8192];
        let capture = drain(&bytes[..], STDOUT_LIMIT, None).unwrap();
        assert_eq!(capture.bytes.len(), STDOUT_LIMIT);
        assert!(capture.truncated);
        let script="i=0; while [ $i -lt 2000 ]; do printf 'diagnostic diagnostic diagnostic diagnostic diagnostic diagnostic diagnostic diagnostic\\n' >&2; i=$((i+1)); done; printf ok";
        assert_eq!(
            execute(
                script,
                &CancellationToken::default(),
                Some(Duration::from_secs(5))
            )
            .unwrap(),
            b"ok"
        );
    }
    #[test]
    fn precancel_does_not_spawn() {
        let token = CancellationToken::default();
        token.cancel();
        assert!(matches!(
            execute("exit 7", &token, None),
            Err(Error::Cancelled)
        ));
    }
    #[test]
    fn continuous_progress_cannot_starve_cancellation_or_timeout() {
        struct SlowProgress(Option<CancellationToken>);
        impl EventSink for SlowProgress {
            fn progress(&self, _: Progress) {
                if let Some(token) = &self.0 {
                    token.cancel();
                }
                thread::sleep(Duration::from_millis(2));
            }
        }
        for cancellation in [true, false] {
            let token = CancellationToken::default();
            let root = tempfile::tempdir().unwrap();
            let completed = root.path().join("producer-completed");
            let result = run(
                Path::new("/bin/sh"),
                &[
                    "-c".into(),
                    "i=0; while [ $i -lt 1000000 ]; do printf 'progress=continue\\n'; i=$((i+1)); done; printf done > \"$1\"".into(),
                    "progress-producer".into(),
                    completed.as_os_str().to_owned(),
                ],
                &token,
                RunOptions {
                    operation: "continuous progress",
                    timeout: Some(Duration::from_millis(if cancellation { 5000 } else { 20 })),
                    progress_duration: None,
                    parse_progress: true,
                    events: &SlowProgress(cancellation.then(|| token.clone())),
                },
            );
            if cancellation {
                assert!(matches!(result, Err(Error::Cancelled)));
            } else {
                assert!(matches!(result, Err(Error::Timeout(_))));
            }
            assert!(
                !completed.exists(),
                "progress delivery postponed interruption until the producer finished"
            );
        }
    }

    #[test]
    fn progress_blocks_do_not_leak_stale_fields_across_updates() {
        let stream = b"out_time_us=1000000\nspeed= 2x\nprogress=continue\nout_time_ms=3000000\nprogress=end\n";
        let (sender, receiver) = mpsc::sync_channel(8);
        drain(&stream[..], STDERR_LIMIT, Some((sender, Some(10.0)))).unwrap();
        let events: Vec<_> = receiver.try_iter().collect();
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].elapsed_seconds, Some(1.0));
        assert_eq!(events[0].eta_seconds, Some(4.5));
        assert_eq!(events[1].elapsed_seconds, Some(3.0));
        assert_eq!(events[1].eta_seconds, None);
    }
}

#[cfg(all(test, unix))]
mod capture_limit_tests {
    use super::*;
    #[test]
    fn excessive_probe_stdout_fails_explicitly() {
        let result = run(
            Path::new("/bin/sh"),
            &[
                "-c".into(),
                "exec dd if=/dev/zero bs=1048576 count=5 2>/dev/null".into(),
            ],
            &CancellationToken::default(),
            RunOptions {
                operation: "large probe",
                timeout: Some(Duration::from_secs(5)),
                progress_duration: None,
                parse_progress: false,
                events: &(),
            },
        );
        assert!(matches!(result, Err(Error::CaptureLimit(_))));
    }
}

#[cfg(test)]
mod capture_tests {
    use super::*;
    struct Chunked<'a> {
        remaining: &'a [u8],
        reads: usize,
    }
    impl Read for Chunked<'_> {
        fn read(&mut self, output: &mut [u8]) -> io::Result<usize> {
            self.reads += 1;
            if self.reads % 7 == 0 {
                return Err(io::ErrorKind::Interrupted.into());
            }
            let size = [1, 17, 8192, 31, 4093][self.reads % 5]
                .min(output.len())
                .min(self.remaining.len());
            output[..size].copy_from_slice(&self.remaining[..size]);
            self.remaining = &self.remaining[size..];
            Ok(size)
        }
    }
    #[test]
    fn capture_retains_the_exact_tail_across_short_and_interrupted_reads() {
        for limit in [STDERR_LIMIT, STDOUT_LIMIT] {
            let input: Vec<_> = (0..3 * limit + 19).map(|i| (i % 251) as u8).collect();
            for len in [0, limit - 1, limit, limit + 1, input.len()] {
                let capture = drain(
                    Chunked {
                        remaining: &input[..len],
                        reads: 0,
                    },
                    limit,
                    None,
                )
                .unwrap();
                assert_eq!(capture.truncated, len > limit);
                assert_eq!(capture.bytes, input[len.saturating_sub(limit)..len]);
            }
        }
    }
    #[test]
    fn short_reads_preserve_progress_records_and_tail_capture_together() {
        let record = b"out_time_us=1000000\nspeed=2x\nprogress=continue\n";
        let stream: Vec<_> = record
            .iter()
            .copied()
            .cycle()
            .take(STDERR_LIMIT + 31)
            .collect();
        let (sender, receiver) = mpsc::sync_channel(64);
        let capture = drain(
            Chunked {
                remaining: &stream,
                reads: 0,
            },
            STDERR_LIMIT,
            Some((sender, Some(10.0))),
        )
        .unwrap();
        assert!(capture.truncated);
        assert_eq!(capture.bytes, stream[stream.len() - STDERR_LIMIT..]);
        let progress: Vec<_> = receiver.try_iter().collect();
        assert_eq!(progress.len(), 64);
        for update in progress {
            assert_eq!(update.elapsed_seconds, Some(1.0));
            assert_eq!(update.fraction, Some(0.1));
            assert_eq!(update.eta_seconds, Some(4.5));
        }
    }
}
