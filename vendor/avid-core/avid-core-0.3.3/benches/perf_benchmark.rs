use avid_core::*;
use std::{
    path::{Path, PathBuf},
    process::Command,
    time::{Duration, Instant},
};

fn run_cmd(program: &Path, args: &[&str]) {
    let out = Command::new(program).args(args).output().unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
}

fn create_fixtures(renderer: &Renderer, root: &Path) -> (Vec<PathBuf>, PathBuf) {
    let mut images = Vec::new();
    for i in 0..5 {
        let art = root.join(format!("art_{i}.png"));
        run_cmd(
            renderer.tools().ffmpeg(),
            &[
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=640x480",
                "-frames:v",
                "1",
                "-y",
                art.to_str().unwrap(),
            ],
        );
        images.push(art);
    }
    let audio = root.join("track.wav");
    run_cmd(
        renderer.tools().ffmpeg(),
        &[
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1:sample_rate=44100",
            "-c:a",
            "pcm_s16le",
            "-y",
            audio.to_str().unwrap(),
        ],
    );
    (images, audio)
}

struct Stats {
    runs: Vec<Duration>,
}

impl Stats {
    fn record<F: FnMut()>(mut f: F, iterations: usize) -> Self {
        let mut runs = Vec::with_capacity(iterations);
        for _ in 0..iterations {
            let start = Instant::now();
            f();
            runs.push(start.elapsed());
        }
        runs.sort();
        Self { runs }
    }

    // Exclude construction/validation from the operation under measurement.
    fn record_with_setup<T>(
        mut setup: impl FnMut() -> T,
        mut operation: impl FnMut(T),
        iterations: usize,
    ) -> Self {
        let mut runs = Vec::with_capacity(iterations);
        for _ in 0..iterations {
            let input = setup();
            let start = Instant::now();
            operation(input);
            runs.push(start.elapsed());
        }
        runs.sort();
        Self { runs }
    }

    fn median_ms(&self) -> f64 {
        let mid = self.runs.len() / 2;
        if self.runs.len() % 2 == 0 {
            (self.runs[mid - 1].as_secs_f64() + self.runs[mid].as_secs_f64()) / 2.0 * 1000.0
        } else {
            self.runs[mid].as_secs_f64() * 1000.0
        }
    }

    fn mean_ms(&self) -> f64 {
        let total: f64 = self.runs.iter().map(|d| d.as_secs_f64()).sum();
        (total / self.runs.len() as f64) * 1000.0
    }

    fn min_ms(&self) -> f64 {
        self.runs.first().unwrap().as_secs_f64() * 1000.0
    }

    fn max_ms(&self) -> f64 {
        self.runs.last().unwrap().as_secs_f64() * 1000.0
    }
}

fn print_metric(name: &str, stats: &Stats) {
    println!(
        "{:<55} | n: {} | min: {:.6}ms | median: {:.6}ms | mean: {:.6}ms | max: {:.6}ms",
        name,
        stats.runs.len(),
        stats.min_ms(),
        stats.median_ms(),
        stats.mean_ms(),
        stats.max_ms()
    );
}

fn main() {
    if std::env::var("AVID_RUN_PERF_BENCH").as_deref() != Ok("1") {
        println!("Performance benchmark skipped; set AVID_RUN_PERF_BENCH=1 to run it.");
        return;
    }
    println!("=== AVID Core Performance Benchmark ===");
    let token = CancellationToken::default();
    let tools = match (
        std::env::var_os("AVID_TEST_FFMPEG"),
        std::env::var_os("AVID_TEST_FFPROBE"),
    ) {
        (Some(ffmpeg), Some(ffprobe)) => MediaTools::from_paths(ffmpeg, ffprobe, &token),
        (None, None) => MediaTools::discover(ToolDiscovery::default(), &token),
        _ => panic!("Set both AVID_TEST_FFMPEG and AVID_TEST_FFPROBE, or neither"),
    }
    .expect("FFmpeg and ffprobe must be available");
    println!(
        "ffmpeg: {} ({})",
        tools.ffmpeg().display(),
        tools.ffmpeg_version()
    );
    println!(
        "ffprobe: {} ({})",
        tools.ffprobe().display(),
        tools.ffprobe_version()
    );
    println!("Optimized benchmark; OS caches uncontrolled. Cold means empty application cache.");
    println!("Exports use explicit software H.264; fixture creation is outside measurements.");
    println!("Probe caching is Unix-only; warm renderer queries still probe on other platforms.");
    let ffmpeg_path = tools.ffmpeg().to_path_buf();
    let ffprobe_path = tools.ffprobe().to_path_buf();

    // 1. Tool discovery and validation
    let stats_from_paths = Stats::record(
        || {
            let _ = MediaTools::from_paths(&ffmpeg_path, &ffprobe_path, &token).unwrap();
        },
        10,
    );
    print_metric("MediaTools::from_paths (2x -version)", &stats_from_paths);

    let discovery = ToolDiscovery {
        ffmpeg: Some(ffmpeg_path.clone()),
        ffprobe: Some(ffprobe_path.clone()),
        search_path: false,
        ..ToolDiscovery::default()
    };
    let stats_discover = Stats::record(
        || {
            let _ = MediaTools::discover(discovery.clone(), &token).unwrap();
        },
        10,
    );
    print_metric(
        "MediaTools::discover (explicit pair + 2x -version)",
        &stats_discover,
    );

    let fresh_renderer =
        || Renderer::new(MediaTools::from_paths(&ffmpeg_path, &ffprobe_path, &token).unwrap());
    // 2. Measure both a fresh tool capability cache and shared cache hits.
    print_metric(
        "Renderer::capabilities (cold tool cache)",
        &Stats::record_with_setup(
            &fresh_renderer,
            |renderer| {
                renderer.capabilities(&token).unwrap();
            },
            10,
        ),
    );
    let renderer = Renderer::new(tools.clone());
    renderer.capabilities(&token).unwrap();
    let stats_capabilities = Stats::record(
        || {
            let _ = renderer.capabilities(&token).unwrap();
        },
        10,
    );
    print_metric(
        "Renderer::capabilities (warm shared cache)",
        &stats_capabilities,
    );

    // Set up temp fixtures
    let temp_dir = tempfile::tempdir().unwrap();
    let (images, audio) = create_fixtures(&renderer, temp_dir.path());

    // 3. Probing image: Cold vs Cached
    let single_image = &images[0];
    let stats_inspect_cold = Stats::record(
        || {
            let r = Renderer::new(tools.clone());
            let _ = r.inspect_image(single_image, &token).unwrap();
        },
        10,
    );
    print_metric(
        "Renderer::inspect_image (cold/uncached)",
        &stats_inspect_cold,
    );

    renderer.inspect_image(single_image, &token).unwrap();
    let stats_inspect_cached = Stats::record(
        || {
            let _ = renderer.inspect_image(single_image, &token).unwrap();
        },
        10,
    );
    print_metric("Renderer::inspect_image (cached)", &stats_inspect_cached);

    // 4. Probing audio: Cold vs Cached
    let stats_probe_cold = Stats::record(
        || {
            let r = Renderer::new(tools.clone());
            let _ = r.probe_audio_duration(&audio, &token).unwrap();
        },
        10,
    );
    print_metric(
        "Renderer::probe_audio_duration (cold/uncached)",
        &stats_probe_cold,
    );

    renderer.probe_audio_duration(&audio, &token).unwrap();
    let stats_probe_cached = Stats::record(
        || {
            let _ = renderer.probe_audio_duration(&audio, &token).unwrap();
        },
        10,
    );
    print_metric(
        "Renderer::probe_audio_duration (cached)",
        &stats_probe_cached,
    );

    // 5. Distinguish serial cold probes from the warm lookup batch. Cold
    // timeline rendering below exercises the bounded concurrent probe workers.
    print_metric(
        "Inspect 5 images (cold renderer, serial)",
        &Stats::record_with_setup(
            || Renderer::new(tools.clone()),
            |renderer| {
                for img in &images {
                    renderer.inspect_image(img, &token).unwrap();
                }
            },
            10,
        ),
    );
    for img in &images {
        renderer.inspect_image(img, &token).unwrap();
    }
    let stats_inspect_5 = Stats::record(
        || {
            for img in &images {
                let _ = renderer.inspect_image(img, &token).unwrap();
            }
        },
        10,
    );
    print_metric(
        "Inspect 5 images (warm application cache)",
        &stats_inspect_5,
    );

    // 6. Preview rendering
    let preview_out = temp_dir.path().join("preview.png");
    let preview_req = PreviewRequest {
        image: single_image.clone(),
        output: preview_out.clone(),
        settings: RenderSettings {
            width: 320,
            height: 240,
            ..Default::default()
        },
        protected_paths: vec![],
    };
    print_metric(
        "Renderer::preview (cold probes + filter detection)",
        &Stats::record_with_setup(
            &fresh_renderer,
            |renderer| {
                renderer.preview(&preview_req, &token, &()).unwrap();
            },
            5,
        ),
    );
    renderer.preview(&preview_req, &token, &()).unwrap();
    let stats_preview = Stats::record(
        || {
            let _ = renderer.preview(&preview_req, &token, &()).unwrap();
        },
        5,
    );
    print_metric(
        "Renderer::preview (warm caches, 320x240 PNG)",
        &stats_preview,
    );

    // 7. Video export - Simple mode
    let video_out_simple = temp_dir.path().join("out_simple.mp4");
    let render_req_simple = RenderRequest {
        input: Input::Single {
            image: single_image.clone(),
            audio: audio.clone(),
        },
        settings: RenderSettings {
            width: 320,
            height: 240,
            fps: 30,
            encoding: Encoding::Software,
            ..Default::default()
        },
        output: video_out_simple.clone(),
        protected_paths: vec![],
    };
    renderer
        .render_with_mode(&render_req_simple, RenderMode::Simple, &token, &())
        .unwrap();
    let stats_render_simple = Stats::record(
        || {
            let _ = renderer
                .render_with_mode(&render_req_simple, RenderMode::Simple, &token, &())
                .unwrap();
        },
        5,
    );
    print_metric(
        "Renderer::render Simple (1s audio 320x240)",
        &stats_render_simple,
    );

    // 8. Timeline export (3 clips)
    let timeline_clips = vec![
        Clip {
            id: "1".into(),
            image: images[0].clone(),
            audio: audio.clone(),
            duration_seconds: 0.5,
        },
        Clip {
            id: "2".into(),
            image: images[1].clone(),
            audio: audio.clone(),
            duration_seconds: 0.5,
        },
        Clip {
            id: "3".into(),
            image: images[2].clone(),
            audio: audio.clone(),
            duration_seconds: 0.5,
        },
    ];
    let timeline_out = temp_dir.path().join("timeline.mp4");
    let timeline_req = RenderRequest {
        input: Input::Timeline(Timeline::new(timeline_clips).unwrap()),
        settings: RenderSettings {
            width: 320,
            height: 240,
            fps: 30,
            encoding: Encoding::Software,
            ..Default::default()
        },
        output: timeline_out.clone(),
        protected_paths: vec![],
    };
    print_metric(
        "Timeline 3-clips Simple (cold probes/capabilities)",
        &Stats::record_with_setup(
            &fresh_renderer,
            |renderer| {
                renderer
                    .render_with_mode(&timeline_req, RenderMode::Simple, &token, &())
                    .unwrap();
            },
            5,
        ),
    );
    renderer
        .render_with_mode(&timeline_req, RenderMode::Simple, &token, &())
        .unwrap();
    let stats_timeline = Stats::record(
        || {
            let _ = renderer
                .render_with_mode(&timeline_req, RenderMode::Simple, &token, &())
                .unwrap();
        },
        5,
    );
    print_metric(
        "Renderer::render Timeline 3-clips Simple (warm caches)",
        &stats_timeline,
    );

    println!("=== Benchmark Complete ===");
}
