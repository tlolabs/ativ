use avid_core::*;
use std::{path::Path, process::Command, time::Duration};

fn run_cmd(program: &Path, args: &[&str]) {
    let out = Command::new(program).args(args).output().unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
}

fn create_art(renderer: &Renderer, path: &Path, color: &str, dims: &str) {
    run_cmd(
        renderer.tools().ffmpeg(),
        &[
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            &format!("color=c={color}:s={dims}"),
            "-frames:v",
            "1",
            "-y",
            path.to_str().unwrap(),
        ],
    );
}

fn create_audio(renderer: &Renderer, path: &Path, duration: f64) {
    run_cmd(
        renderer.tools().ffmpeg(),
        &[
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            &format!("sine=frequency=440:duration={duration}:sample_rate=44100"),
            "-c:a",
            "pcm_s16le",
            "-y",
            path.to_str().unwrap(),
        ],
    );
}

#[test]
fn probe_cache_serves_repeated_queries_and_invalidates_on_file_modification() {
    let token = CancellationToken::default();
    let tools = match (
        std::env::var_os("AVID_TEST_FFMPEG"),
        std::env::var_os("AVID_TEST_FFPROBE"),
    ) {
        (Some(ffmpeg), Some(ffprobe)) => MediaTools::from_paths(ffmpeg, ffprobe, &token).ok(),
        _ => MediaTools::discover(ToolDiscovery::default(), &token).ok(),
    };
    let Some(tools) = tools else {
        return;
    };
    let renderer = Renderer::new(tools);
    let temp = tempfile::tempdir().unwrap();

    let art = temp.path().join("art.png");
    create_art(&renderer, &art, "red", "320x240");

    // First inspection: fills cache
    let dims1 = renderer.inspect_image(&art, &token).unwrap();
    assert_eq!(dims1, (320, 240));

    // Second inspection: served from cache
    let dims2 = renderer.inspect_image(&art, &token).unwrap();
    assert_eq!(dims2, (320, 240));

    // Modify file: changes size/mtime, must invalidate cache and return new dimensions
    std::thread::sleep(Duration::from_millis(50));
    create_art(&renderer, &art, "blue", "640x480");

    let dims3 = renderer.inspect_image(&art, &token).unwrap();
    assert_eq!(dims3, (640, 480));

    // Replace file atomically with same byte size and preserved mtime:
    // inode change must still invalidate the probe cache on Unix.
    #[cfg(unix)]
    {
        let replacement = temp.path().join("replacement.png");
        create_art(&renderer, &replacement, "yellow", "200x150");
        let art_bytes = std::fs::read(&art).unwrap();
        let mut replacement_bytes = std::fs::read(&replacement).unwrap();
        assert!(replacement_bytes.len() <= art_bytes.len());
        replacement_bytes.resize(art_bytes.len(), 0);
        std::fs::write(&replacement, &replacement_bytes).unwrap();
        assert_eq!(
            std::fs::metadata(&replacement).unwrap().len(),
            art_bytes.len() as u64
        );
        let mtime = std::fs::metadata(&art).unwrap().modified().unwrap();
        let file = std::fs::OpenOptions::new()
            .write(true)
            .open(&replacement)
            .unwrap();
        file.set_modified(mtime).unwrap();
        drop(file);
        std::fs::rename(&replacement, &art).unwrap();
        assert_eq!(renderer.inspect_image(&art, &token).unwrap(), (200, 150));
    }

    // Audio duration cache test
    let audio = temp.path().join("audio.wav");
    create_audio(&renderer, &audio, 1.0);

    let dur1 = renderer.probe_audio_duration(&audio, &token).unwrap();
    assert!(dur1.is_some());
    let val1 = dur1.unwrap();
    assert!((val1 - 1.0).abs() < 0.1);

    // Repeated audio duration query: served from cache
    let dur2 = renderer.probe_audio_duration(&audio, &token).unwrap();
    assert_eq!(dur1, dur2);

    // Modify audio: invalidate cache
    std::thread::sleep(Duration::from_millis(50));
    create_audio(&renderer, &audio, 2.0);

    let dur3 = renderer.probe_audio_duration(&audio, &token).unwrap();
    assert!(dur3.is_some());
    let val3 = dur3.unwrap();
    assert!((val3 - 2.0).abs() < 0.1);
}

#[test]
fn capabilities_cache_is_consistent_and_cancellable() {
    let token = CancellationToken::default();
    let tools = match (
        std::env::var_os("AVID_TEST_FFMPEG"),
        std::env::var_os("AVID_TEST_FFPROBE"),
    ) {
        (Some(ffmpeg), Some(ffprobe)) => MediaTools::from_paths(ffmpeg, ffprobe, &token).ok(),
        _ => MediaTools::discover(ToolDiscovery::default(), &token).ok(),
    };
    let Some(tools) = tools else {
        return;
    };
    let renderer = Renderer::new(tools);

    let caps1 = renderer.capabilities(&token).unwrap();
    let caps2 = renderer.capabilities(&token).unwrap();
    assert_eq!(caps1, caps2);

    // Cancelled token check
    let cancel = CancellationToken::default();
    cancel.cancel();
    assert!(matches!(
        renderer.capabilities(&cancel),
        Err(Error::Cancelled)
    ));
}

#[test]
fn concurrent_timeline_probing_handles_multiple_unique_images() {
    let token = CancellationToken::default();
    let tools = match (
        std::env::var_os("AVID_TEST_FFMPEG"),
        std::env::var_os("AVID_TEST_FFPROBE"),
    ) {
        (Some(ffmpeg), Some(ffprobe)) => MediaTools::from_paths(ffmpeg, ffprobe, &token).ok(),
        _ => MediaTools::discover(ToolDiscovery::default(), &token).ok(),
    };
    let Some(tools) = tools else {
        return;
    };
    let renderer = Renderer::new(tools);
    let temp = tempfile::tempdir().unwrap();

    let mut clips = Vec::new();
    for i in 0..4 {
        let art = temp.path().join(format!("art_{i}.png"));
        let audio = temp.path().join(format!("audio_{i}.wav"));
        create_art(&renderer, &art, "green", "160x120");
        create_audio(&renderer, &audio, 0.5);
        clips.push(Clip {
            id: format!("clip_{i}"),
            image: art,
            audio,
            duration_seconds: 0.5,
        });
    }

    let out = temp.path().join("timeline_test.mp4");
    let req = RenderRequest {
        input: Input::Timeline(Timeline::new(clips).unwrap()),
        settings: RenderSettings {
            width: 160,
            height: 120,
            fps: 30,
            ..Default::default()
        },
        output: out,
        protected_paths: vec![],
    };

    let result = renderer.render_with_mode(&req, RenderMode::Simple, &token, &());
    assert!(result.is_ok());
    assert!(result.unwrap().is_file());
}
