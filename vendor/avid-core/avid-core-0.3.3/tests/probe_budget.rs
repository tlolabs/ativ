//! Process-count regression tests using immutable shell fixtures and file barriers.
#![cfg(unix)]

use avid_core::*;
use std::{
    fs,
    os::unix::fs::symlink,
    path::{Path, PathBuf},
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

const CLIPS: usize = 9;

fn setup(root: &Path) -> (Renderer, RenderRequest) {
    let fixtures = Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/lifecycle");
    // Do not write executable inodes while other tests may be spawning them.
    let ffmpeg = root.join("ffmpeg");
    let ffprobe = root.join("ffprobe");
    symlink(fixtures.join("ffmpeg.sh"), &ffmpeg).unwrap();
    symlink(fixtures.join("probe-budget.sh"), &ffprobe).unwrap();
    fs::write(root.join("fixture-mode"), "ok").unwrap();
    let tools = MediaTools::from_paths(ffmpeg, ffprobe, &CancellationToken::default()).unwrap();
    let renderer = Renderer::new(tools).with_options(OperationOptions {
        probe_timeout: Some(Duration::from_secs(10)),
        ..Default::default()
    });
    let audio = root.join("audio.wav");
    fs::write(&audio, b"audio").unwrap();
    let clips = (0..CLIPS)
        .map(|index| {
            let image = root.join(format!("art-{index}.png"));
            fs::write(&image, b"art").unwrap();
            Clip {
                id: index.to_string(),
                image,
                audio: audio.clone(),
                duration_seconds: 1.0,
            }
        })
        .collect();
    let output = root.join("result.mp4");
    fs::write(&output, b"old output").unwrap();
    let request = RenderRequest {
        input: Input::Timeline(Timeline::new(clips).unwrap()),
        settings: RenderSettings::default(),
        output,
        protected_paths: vec![],
    };
    (renderer, request)
}

fn events(root: &Path) -> Vec<String> {
    fs::read_to_string(root.join("probe-events"))
        .unwrap_or_default()
        .lines()
        .map(str::to_owned)
        .collect()
}

fn wait_for_events(root: &Path, prefix: &str, count: usize) -> bool {
    let deadline = Instant::now() + Duration::from_secs(5);
    while Instant::now() < deadline {
        if events(root)
            .iter()
            .filter(|line| line.starts_with(prefix))
            .count()
            >= count
        {
            return true;
        }
        thread::sleep(Duration::from_millis(5));
    }
    false
}

fn start(
    renderer: Renderer,
    request: RenderRequest,
    token: CancellationToken,
) -> JoinHandle<Result<PathBuf>> {
    thread::spawn(move || renderer.render(&request, &token, &()))
}

fn no_stages(root: &Path) {
    assert!(!fs::read_dir(root).unwrap().any(|entry| entry
        .unwrap()
        .file_name()
        .to_string_lossy()
        .starts_with(".avid-")));
}

#[test]
fn timeline_probes_at_most_four_images_at_once() {
    let root = tempfile::tempdir().unwrap();
    let (renderer, request) = setup(root.path());
    let output = request.output.clone();
    let worker = start(renderer, request, CancellationToken::default());
    let started = wait_for_events(root.path(), "start ", 4);
    // Hold all probes at the barrier while the initial workers start. The
    // previous implementation launched all nine probes into this same barrier.
    thread::sleep(Duration::from_millis(150));
    fs::write(root.path().join("release-all"), b"").unwrap();
    let result = worker.join().unwrap();
    assert!(started, "the initial probe batch did not reach the barrier");
    result.unwrap();

    let mut active = 0;
    let mut peak = 0;
    let mut total = 0;
    for event in events(root.path()) {
        if event.starts_with("start ") {
            active += 1;
            total += 1;
            peak = peak.max(active);
        } else if event.starts_with("end ") {
            assert!(active > 0);
            active -= 1;
        }
    }
    assert_eq!(total, CLIPS);
    assert_eq!(active, 0);
    assert_eq!(peak, 4, "concurrent artwork probes exceeded the budget");
    assert_eq!(fs::read(output).unwrap(), b"completed");
    no_stages(root.path());
}

#[test]
fn artwork_probe_error_joins_its_batch_and_preserves_destination() {
    let root = tempfile::tempdir().unwrap();
    let (renderer, request) = setup(root.path());
    let output = request.output.clone();
    fs::write(root.path().join("fail-art-0.png"), b"").unwrap();
    let worker = start(renderer, request, CancellationToken::default());
    let started = wait_for_events(root.path(), "start ", 4);
    fs::write(root.path().join("release-art-0.png"), b"").unwrap();
    let failed = wait_for_events(root.path(), "end art-0.png", 1);
    let waited_for_batch = !worker.is_finished();
    fs::write(root.path().join("release-all"), b"").unwrap();
    let result = worker.join().unwrap();
    assert!(started && failed, "the probe error fixture did not run");
    assert!(waited_for_batch, "the other probes must be joined on error");
    assert!(matches!(result, Err(Error::Process { .. })));
    let recorded = events(root.path());
    assert_eq!(
        recorded
            .iter()
            .filter(|line| line.starts_with("start "))
            .count(),
        4
    );
    assert_eq!(
        recorded
            .iter()
            .filter(|line| line.starts_with("end "))
            .count(),
        4
    );
    assert_eq!(fs::read(output).unwrap(), b"old output");
    no_stages(root.path());
}

#[test]
fn artwork_probe_cancellation_stops_before_the_next_batch() {
    let root = tempfile::tempdir().unwrap();
    let (renderer, request) = setup(root.path());
    let output = request.output.clone();
    let token = CancellationToken::default();
    let worker = start(renderer, request, token.clone());
    let started = wait_for_events(root.path(), "start ", 4);
    let cancelled = Instant::now();
    token.cancel();
    let result = worker.join().unwrap();
    assert!(started, "the initial probe batch did not reach the barrier");
    assert!(matches!(result, Err(Error::Cancelled)));
    assert!(cancelled.elapsed() < Duration::from_secs(5));
    assert_eq!(
        events(root.path())
            .iter()
            .filter(|line| line.starts_with("start "))
            .count(),
        4
    );
    assert_eq!(fs::read(output).unwrap(), b"old output");
    no_stages(root.path());
}
