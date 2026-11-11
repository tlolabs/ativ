use avid_core::{CancellationToken, MediaTools};

fn captured(command: &mut std::process::Command) -> std::process::Output {
    use std::process::Stdio;
    let child = command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let pid = child.id();
    eprintln!("fixture_child_spawn pid={pid}");
    let output = child.wait_with_output().unwrap();
    eprintln!(
        "fixture_child_wait_and_drop pid={pid} status={:?}",
        output.status
    );
    output
}

fn external_pair(directory: &std::path::Path) -> avid_core::Result<MediaTools> {
    MediaTools::from_paths(
        directory.join(format!("ffmpeg{}", std::env::consts::EXE_SUFFIX)),
        directory.join(format!("ffprobe{}", std::env::consts::EXE_SUFFIX)),
        &CancellationToken::default(),
    )
}

/// Native coverage, including Windows: installed executables must release their
/// handles on cancellation/timeout so replacement, rollback and cleanup work.
#[test]
#[ignore = "requires AVID_RUNTIME_DIRECTORY containing an externally supplied relocatable FFmpeg/ffprobe pair"]
fn installed_runtime_render_replacement_rollback_and_cleanup() {
    use avid_core::*;
    use std::{fs, path::Path, process::Command, time::Duration};
    fn stage(source: &Path, destination: &Path) {
        fs::create_dir(destination).unwrap();
        for name in [
            format!("ffmpeg{}", std::env::consts::EXE_SUFFIX),
            format!("ffprobe{}", std::env::consts::EXE_SUFFIX),
        ] {
            fs::copy(source.join(&name), destination.join(&name)).unwrap();
            assert_eq!(
                fs::read(source.join(&name)).unwrap(),
                fs::read(destination.join(&name)).unwrap()
            );
        }
    }
    struct CancelAtPublication(CancellationToken);
    impl EventSink for CancelAtPublication {
        fn stage(&self, stage: Stage) {
            if stage == Stage::Publishing {
                self.0.cancel();
            }
        }
    }
    let source = std::path::PathBuf::from(std::env::var_os("AVID_RUNTIME_DIRECTORY").unwrap());
    let root = tempfile::tempdir().unwrap();
    let staged = root.path().join("staged ü runtime");
    let installed = root.path().join("installed ü runtime");
    let backup = root.path().join("previous runtime");
    stage(&source, &staged);
    move_runtime_directory(&staged, &installed, Duration::from_secs(2)).unwrap();
    let tools = external_pair(&installed).unwrap();
    let image = root.path().join("artwork ü.png");
    let audio = root.path().join("track ü.wav");
    for (input, extra, output) in [
        ("testsrc2=s=192x128", vec!["-frames:v", "1"], &image),
        (
            "sine=frequency=523:duration=1",
            vec!["-c:a", "pcm_s16le"],
            &audio,
        ),
    ] {
        let result = captured(
            Command::new(tools.ffmpeg())
                .args(["-nostdin", "-v", "error", "-f", "lavfi", "-i", input])
                .args(extra)
                .arg(output),
        );
        assert!(result.status.success(), "{result:?}");
    }
    let renderer = Renderer::new(tools);
    let request = RenderRequest {
        input: Input::Single { image, audio },
        settings: RenderSettings {
            width: 160,
            height: 90,
            fps: 24,
            ..Default::default()
        },
        output: root.path().join("result.mp4"),
        protected_paths: vec![],
    };
    fs::write(&request.output, b"previous output").unwrap();
    renderer
        .render(&request, &CancellationToken::default(), &())
        .unwrap();
    let completed = fs::read(&request.output).unwrap();
    assert_ne!(completed, b"previous output");
    let result = captured(
        Command::new(renderer.tools().ffprobe())
            .args(["-v", "error", "-show_streams", "-of", "json"])
            .arg(&request.output),
    );
    assert!(result.status.success(), "{result:?}");
    let probe: serde_json::Value = serde_json::from_slice(&result.stdout).unwrap();
    assert!(probe["streams"]
        .as_array()
        .unwrap()
        .iter()
        .any(|s| s["codec_name"] == "h264"));
    let token = CancellationToken::default();
    assert!(matches!(
        renderer.render(&request, &token, &CancelAtPublication(token.clone())),
        Err(Error::Cancelled)
    ));
    assert_eq!(fs::read(&request.output).unwrap(), completed);
    let renderer = renderer.with_options(OperationOptions {
        render_timeout: Some(Duration::ZERO),
        ..Default::default()
    });
    assert!(matches!(
        renderer.render(&request, &CancellationToken::default(), &()),
        Err(Error::Timeout(_))
    ));
    assert_eq!(fs::read(&request.output).unwrap(), completed);
    assert!(!fs::read_dir(root.path()).unwrap().any(|entry| entry
        .unwrap()
        .file_name()
        .to_string_lossy()
        .starts_with(".avid-")));
    stage(&source, &staged);
    external_pair(&staged).unwrap();
    eprintln!(
        "runtime_rename_begin test_pid={} cwd_inside_runtime={}",
        std::process::id(),
        std::env::current_dir().unwrap().starts_with(&installed)
    );
    move_runtime_directory(&installed, &backup, Duration::from_secs(2)).unwrap();
    move_runtime_directory(&staged, &installed, Duration::from_secs(2)).unwrap();
    external_pair(&installed).unwrap();
    // A missing executable must fail instead of selecting another pair.
    fs::remove_file(installed.join(format!("ffprobe{}", std::env::consts::EXE_SUFFIX))).unwrap();
    assert!(external_pair(&installed).is_err());
    remove_runtime_directory(&installed, Duration::from_secs(2)).unwrap();
    move_runtime_directory(&backup, &installed, Duration::from_secs(2)).unwrap();
    external_pair(&installed).unwrap();
    // Exercise removal of the final restored runtime through the same host API.
    // Keep the independent temporary-workspace close assertion as well.
    remove_runtime_directory(&installed, Duration::from_secs(2)).unwrap();
    assert!(!installed.exists());
    root.close().unwrap();
}

/// A host stops active work and joins its operation thread before updating tools.
/// This supplements the existing publication-cancel and startup-timeout cases.
#[test]
#[ignore = "requires AVID_RUNTIME_DIRECTORY containing an externally supplied relocatable FFmpeg/ffprobe pair"]
fn active_native_render_cancellation_releases_runtime_after_worker_join() {
    use avid_core::*;
    use std::{
        fs,
        process::Command,
        sync::{
            atomic::{AtomicBool, Ordering},
            mpsc,
        },
        time::Duration,
    };
    struct NotifyProgress {
        sender: mpsc::Sender<()>,
        sent: AtomicBool,
    }
    impl EventSink for NotifyProgress {
        fn progress(&self, progress: Progress) {
            if progress
                .elapsed_seconds
                .is_some_and(|elapsed| elapsed < 120.0)
                && !self.sent.swap(true, Ordering::SeqCst)
            {
                let _ = self.sender.send(());
            }
        }
    }
    let source = std::path::PathBuf::from(std::env::var_os("AVID_RUNTIME_DIRECTORY").unwrap());
    let root = tempfile::tempdir().unwrap();
    let installed = root.path().join("installed runtime");
    fs::create_dir(&installed).unwrap();
    for name in [
        format!("ffmpeg{}", std::env::consts::EXE_SUFFIX),
        format!("ffprobe{}", std::env::consts::EXE_SUFFIX),
    ] {
        fs::copy(source.join(&name), installed.join(&name)).unwrap();
    }
    let tools = external_pair(&installed).unwrap();
    let image = root.path().join("image.png");
    let audio = root.path().join("audio.wav");
    for (input, extra, output) in [
        ("testsrc2=s=640x360", vec!["-frames:v", "1"], &image),
        (
            "sine=frequency=523:duration=120",
            vec!["-c:a", "pcm_s16le"],
            &audio,
        ),
    ] {
        let result = captured(
            Command::new(tools.ffmpeg())
                .args(["-nostdin", "-v", "error", "-f", "lavfi", "-i", input])
                .args(extra)
                .arg(output),
        );
        assert!(
            result.status.success(),
            "fixture generation failed: {}",
            result.status
        );
    }
    let output = root.path().join("cancelled.mp4");
    fs::write(&output, b"previous output").unwrap();
    let request = RenderRequest {
        input: Input::Single { image, audio },
        output: output.clone(),
        protected_paths: vec![],
        settings: RenderSettings {
            width: 640,
            height: 360,
            fps: 30,
            encoding: Encoding::Software,
            ..Default::default()
        },
    };
    let (sender, receiver) = mpsc::channel();
    let token = CancellationToken::default();
    let worker_token = token.clone();
    let worker = std::thread::spawn(move || {
        let renderer = Renderer::new(tools);
        renderer.render(
            &request,
            &worker_token,
            &NotifyProgress {
                sender,
                sent: AtomicBool::new(false),
            },
        )
    });
    let progress = receiver.recv_timeout(Duration::from_secs(30));
    token.cancel();
    let result = worker.join().unwrap();
    assert!(
        progress.is_ok(),
        "native child did not report active progress"
    );
    assert!(matches!(result, Err(Error::Cancelled)));
    assert_eq!(fs::read(&output).unwrap(), b"previous output");
    assert!(!fs::read_dir(root.path()).unwrap().any(|entry| entry
        .unwrap()
        .file_name()
        .to_string_lossy()
        .starts_with(".avid-")));
    eprintln!(
        "runtime_rename_begin test_pid={} cwd_inside_runtime={}",
        std::process::id(),
        std::env::current_dir().unwrap().starts_with(&installed)
    );
    let moved = root.path().join("released runtime");
    move_runtime_directory(&installed, &moved, Duration::from_secs(2)).unwrap();
    remove_runtime_directory(&moved, Duration::from_secs(2)).unwrap();
    root.close().unwrap();
}
