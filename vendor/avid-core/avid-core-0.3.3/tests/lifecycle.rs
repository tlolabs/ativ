//! Deterministic process tests. Fake executable scripts require a POSIX shell, not FFmpeg.
#![cfg(unix)]
use avid_core::*;
use std::{fs, os::unix::fs::symlink, path::Path, sync::Mutex, time::Duration};
fn script(path: &Path, fixture: &str) {
    let source = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/lifecycle")
        .join(fixture);
    if path.symlink_metadata().is_ok() {
        fs::remove_file(path).unwrap();
    }
    // Never open an executable inode for writing while parallel tests spawn.
    // A fork can inherit that writable descriptor until exec, causing Linux
    // ETXTBSY even after fs::write has closed the parent's descriptor.
    symlink(source, path).unwrap();
}
fn renderer(root: &Path, mode: &str) -> Renderer {
    let ffmpeg = root.join("ffmpeg");
    let ffprobe = root.join("ffprobe");
    fs::write(root.join("fixture-mode"), mode).unwrap();
    script(&ffprobe, "ffprobe.sh");
    script(&ffmpeg, "ffmpeg.sh");
    let tools = MediaTools::from_paths(ffmpeg, ffprobe, &CancellationToken::default()).unwrap();
    Renderer::new(tools)
}
fn request(root: &Path) -> RenderRequest {
    let image = root.join("art ü.png");
    let audio = root.join("source audio.wav");
    fs::write(&image, b"art").unwrap();
    fs::write(&audio, b"audio").unwrap();
    let output = root.join("result.mp4");
    fs::write(&output, b"old output").unwrap();
    RenderRequest {
        input: Input::Single { image, audio },
        settings: RenderSettings::default(),
        output,
        protected_paths: vec![],
    }
}
fn no_stages(root: &Path) {
    assert!(!fs::read_dir(root).unwrap().any(|e| e
        .unwrap()
        .file_name()
        .to_string_lossy()
        .starts_with(".avid-")));
}
#[derive(Default)]
struct Events {
    stages: Mutex<Vec<Stage>>,
    progress: Mutex<Vec<Progress>>,
}
impl EventSink for Events {
    fn stage(&self, stage: Stage) {
        self.stages.lock().unwrap().push(stage);
    }
    fn progress(&self, p: Progress) {
        self.progress.lock().unwrap().push(p);
    }
}
#[test]
fn automatic_fallback_and_progress_share_a_guarded_stage() {
    let root = tempfile::tempdir().unwrap();
    let renderer = renderer(root.path(), "ok");
    let mut request = request(root.path());
    request.settings.encoding = Encoding::Automatic;
    let events = Events::default();
    renderer
        .render(&request, &CancellationToken::default(), &events)
        .unwrap();
    assert_eq!(fs::read(&request.output).unwrap(), b"completed");
    no_stages(root.path());
    let stages = events.stages.lock().unwrap();
    assert_eq!(stages.iter().filter(|s| **s == Stage::Encoding).count(), 2);
    assert_eq!(stages.last(), Some(&Stage::Complete));
    assert!(events
        .progress
        .lock()
        .unwrap()
        .iter()
        .any(|p| p.fraction == Some(1.0)));
}
#[test]
fn failed_fallback_retains_both_errors_and_old_output() {
    let root = tempfile::tempdir().unwrap();
    let renderer = renderer(root.path(), "fail");
    let mut request = request(root.path());
    request.settings.encoding = Encoding::Automatic;
    match renderer
        .render(&request, &CancellationToken::default(), &())
        .unwrap_err()
    {
        Error::Fallback { hardware, software } => {
            assert!(hardware.to_string().contains("deliberate encoder failure"));
            assert!(software.to_string().contains("deliberate encoder failure"));
        }
        e => panic!("{e:?}"),
    }
    assert_eq!(fs::read(request.output).unwrap(), b"old output");
    no_stages(root.path());
}
#[test]
fn explicit_hardware_failure_does_not_fall_back() {
    let root = tempfile::tempdir().unwrap();
    let renderer = renderer(root.path(), "ok");
    let mut request = request(root.path());
    request.settings.encoding = Encoding::Hardware;
    assert!(matches!(
        renderer.render(&request, &CancellationToken::default(), &()),
        Err(Error::Process { .. })
    ));
    assert_eq!(fs::read(request.output).unwrap(), b"old output");
    no_stages(root.path());
}
#[test]
fn render_timeout_preserves_destination_and_removes_partial() {
    let root = tempfile::tempdir().unwrap();
    let renderer = renderer(root.path(), "slow").with_options(OperationOptions {
        render_timeout: Some(Duration::from_millis(80)),
        ..Default::default()
    });
    let request = request(root.path());
    assert!(matches!(
        renderer.render(&request, &CancellationToken::default(), &()),
        Err(Error::Timeout(_))
    ));
    assert_eq!(fs::read(request.output).unwrap(), b"old output");
    no_stages(root.path());
}
struct CancelAtPublication(CancellationToken);
impl EventSink for CancelAtPublication {
    fn stage(&self, stage: Stage) {
        if stage == Stage::Publishing {
            self.0.cancel();
        }
    }
}
#[test]
fn cancellation_after_encoding_prevents_publication() {
    let root = tempfile::tempdir().unwrap();
    let renderer = renderer(root.path(), "ok");
    let request = request(root.path());
    let token = CancellationToken::default();
    assert!(matches!(
        renderer.render(&request, &token, &CancelAtPublication(token.clone())),
        Err(Error::Cancelled)
    ));
    assert_eq!(fs::read(request.output).unwrap(), b"old output");
    no_stages(root.path());
}
#[test]
fn cancellation_during_encode_reaps_and_cleans() {
    let root = tempfile::tempdir().unwrap();
    let renderer = renderer(root.path(), "slow");
    let request = request(root.path());
    let output = request.output.clone();
    let token = CancellationToken::default();
    let worker_token = token.clone();
    let worker = std::thread::spawn(move || renderer.render(&request, &worker_token, &()));
    std::thread::sleep(Duration::from_millis(200));
    token.cancel();
    assert!(matches!(worker.join().unwrap(), Err(Error::Cancelled)));
    assert_eq!(fs::read(output).unwrap(), b"old output");
    no_stages(root.path());
}
#[test]
fn preview_protects_original_and_cleans_failed_output() {
    let root = tempfile::tempdir().unwrap();
    let renderer = renderer(root.path(), "fail");
    let request = request(root.path());
    let image = match request.input {
        Input::Single { image, .. } => image,
        _ => unreachable!(),
    };
    let mut preview = PreviewRequest {
        image: image.clone(),
        output: image.clone(),
        settings: RenderSettings::default(),
        protected_paths: vec![],
    };
    assert!(matches!(
        renderer.preview(&preview, &CancellationToken::default(), &()),
        Err(Error::InvalidInput(_))
    ));
    assert_eq!(fs::read(&image).unwrap(), b"art");
    preview.output = root.path().join("preview.png");
    fs::write(&preview.output, b"old preview").unwrap();
    assert!(renderer
        .preview(&preview, &CancellationToken::default(), &())
        .is_err());
    assert_eq!(fs::read(&preview.output).unwrap(), b"old preview");
    no_stages(root.path());
}
#[test]
fn extra_protected_paths_cover_unselected_sources_and_project() {
    let root = tempfile::tempdir().unwrap();
    let renderer = renderer(root.path(), "ok");
    let mut request = request(root.path());
    request.protected_paths.push(request.output.clone());
    assert!(matches!(
        renderer.render(&request, &CancellationToken::default(), &()),
        Err(Error::InvalidInput(_))
    ));
    assert_eq!(fs::read(request.output).unwrap(), b"old output");
}
#[test]
fn probe_and_preview_timeouts_are_cancellable() {
    let root = tempfile::tempdir().unwrap();
    let renderer = renderer(root.path(), "slow").with_options(OperationOptions {
        probe_timeout: Some(Duration::from_millis(50)),
        preview_timeout: Some(Duration::from_millis(50)),
        ..Default::default()
    });
    let request = request(root.path());
    let Input::Single { image, audio } = request.input else {
        unreachable!()
    };
    let preview = PreviewRequest {
        image,
        output: root.path().join("preview.png"),
        settings: RenderSettings::default(),
        protected_paths: vec![],
    };
    assert!(matches!(
        renderer.preview(&preview, &CancellationToken::default(), &()),
        Err(Error::Timeout(_))
    ));
    no_stages(root.path());
    script(renderer.tools().ffprobe(), "slow.sh");
    assert!(matches!(
        renderer.probe_audio_duration(&audio, &CancellationToken::default()),
        Err(Error::Timeout(_))
    ));
}

#[test]
fn concurrent_operations_have_independent_cancellation_and_staging() {
    let root = tempfile::tempdir().unwrap();
    let renderer = renderer(root.path(), "ok");
    let first = request(root.path());
    let mut second = first.clone();
    second.output = root.path().join("second.mp4");
    let first_output = first.output.clone();
    let second_output = second.output.clone();
    let other = renderer.clone();
    let a = std::thread::spawn(move || {
        let token = CancellationToken::default();
        other.render(&first, &token, &CancelAtPublication(token.clone()))
    });
    let b =
        std::thread::spawn(move || renderer.render(&second, &CancellationToken::default(), &()));
    assert!(matches!(a.join().unwrap(), Err(Error::Cancelled)));
    b.join().unwrap().unwrap();
    assert_eq!(fs::read(first_output).unwrap(), b"old output");
    assert_eq!(fs::read(second_output).unwrap(), b"completed");
    no_stages(root.path());
}

#[test]
fn simple_mode_keeps_fallback_timeout_and_publication_guards() {
    for mode in ["ok", "fail", "slow", "cancel"] {
        let root = tempfile::tempdir().unwrap();
        let renderer = renderer(root.path(), mode).with_options(OperationOptions {
            // Only the slow fixture tests the deadline. Do not impose an 80 ms
            // process-startup budget on success/fallback/publication assertions.
            render_timeout: Some(if mode == "slow" {
                Duration::from_millis(80)
            } else {
                Duration::from_secs(5)
            }),
            ..Default::default()
        });
        let mut request = request(root.path());
        request.settings.encoding = Encoding::Automatic;
        let token = CancellationToken::default();
        let cancel = CancelAtPublication(token.clone());
        let events = Events::default();
        let sink: &dyn EventSink = if mode == "cancel" { &cancel } else { &events };
        let result = renderer.render_with_mode(&request, RenderMode::Simple, &token, sink);
        match mode {
            "ok" => {
                result.unwrap();
                assert_eq!(fs::read(&request.output).unwrap(), b"completed");
                assert_eq!(
                    events
                        .stages
                        .lock()
                        .unwrap()
                        .iter()
                        .filter(|s| **s == Stage::Encoding)
                        .count(),
                    2
                );
            }
            "fail" => assert!(matches!(result, Err(Error::Fallback { .. }))),
            "slow" => assert!(matches!(result, Err(Error::Timeout(_)))),
            "cancel" => assert!(matches!(result, Err(Error::Cancelled))),
            _ => unreachable!(),
        }
        if mode != "ok" {
            assert_eq!(fs::read(&request.output).unwrap(), b"old output");
        }
        no_stages(root.path());
    }
}

#[test]
fn artwork_normalization_capabilities_are_cached_and_unsupported_tools_fail_safely() {
    for mode in ["setsar", "scale", "unsupported"] {
        let root = tempfile::tempdir().unwrap();
        let renderer = renderer(root.path(), "ok");
        let request = request(root.path());
        fs::write(root.path().join("normalization-mode"), mode).unwrap();
        let result = renderer.render(&request, &CancellationToken::default(), &());
        if mode == "unsupported" {
            assert!(matches!(result, Err(Error::InvalidInput(_))));
            assert_eq!(fs::read(&request.output).unwrap(), b"old output");
        } else {
            result.unwrap();
            // Changing the fixture after discovery must not probe again for
            // clones of the same validated immutable tool identity.
            fs::write(root.path().join("normalization-mode"), "unsupported").unwrap();
            renderer
                .clone()
                .render(&request, &CancellationToken::default(), &())
                .unwrap();
        }
        let probes = fs::read_to_string(root.path().join("normalization-probes")).unwrap();
        assert_eq!(probes.lines().count(), if mode == "setsar" { 1 } else { 2 });
        no_stages(root.path());
    }
}

#[test]
fn artwork_normalization_probe_obeys_timeout_and_cancellation() {
    for cancellation in [false, true] {
        let root = tempfile::tempdir().unwrap();
        let renderer = renderer(root.path(), "ok").with_options(OperationOptions {
            probe_timeout: Some(Duration::from_millis(if cancellation { 5000 } else { 30 })),
            ..Default::default()
        });
        let request = request(root.path());
        fs::write(root.path().join("normalization-mode"), "slow").unwrap();
        let token = CancellationToken::default();
        let other = token.clone();
        let marker = root.path().join("normalization-probes");
        let cancel_worker = std::thread::spawn(move || {
            if cancellation {
                let start = std::time::Instant::now();
                while !marker.exists() && start.elapsed() < Duration::from_secs(3) {
                    std::thread::sleep(Duration::from_millis(5));
                }
                other.cancel();
            }
        });
        let result = renderer.render(&request, &token, &());
        cancel_worker.join().unwrap();
        if cancellation {
            assert!(matches!(result, Err(Error::Cancelled)));
        } else {
            assert!(matches!(result, Err(Error::Timeout(_))));
        }
        assert_eq!(fs::read(&request.output).unwrap(), b"old output");
        no_stages(root.path());
    }
}
