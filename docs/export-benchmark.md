# Static export benchmark

Measured locally on September 13, 2026 on an Apple M5 Max (18 logical CPUs, 128 GiB), macOS 26.6.2, using ATIV's bundled FFmpeg 9.0.1 arm64 build. The test uses a generated detailed 2400×1600 image, mono 44.1 kHz PCM audio, 30 fps, software libx264 with its existing stillimage tune, AAC 128k, yuv420p and faststart. No encoder preset, quality or hardware-encoding changes were made. These are synthetic-media results on this machine, not a guarantee for every artwork file or computer.

## Results

Medians of three runs after one excluded warmup per variant. Run order rotates; exports are sequential. Saved-PNG times include creating the composite on every run.

| Equal-duration FFmpeg workload | Per-frame composition | Saved composite PNG | Cached YUV composite | Speedup vs per-frame |
|---|---:|---:|---:|---:|
| 60-second 1920×1080 video | 10.268 s | 3.530 s | **1.848 s** | **5.56×** |
| 10-second 3840×2160 video | 4.668 s | 2.378 s | **1.325 s** | **3.52×** |

The real ATIV engine benchmark also includes tool discovery, validation, probing, staging and publication:

| 60-second 1080p engine export | Median wall time |
|---|---:|
| Preserved original release binary | 11.953 s |
| Updated engine with `--render-mode current` | 12.136 s |
| Updated engine with `--render-mode simple` | **2.025 s** |

Simple mode is **5.90× faster** than the preserved build in this end-to-end test (83.1% less wall time). The equal-duration experiment separately isolates the compositor improvement. Some development checks ran during the engine benchmark; use the reproducible scripts below for an idle-machine rerun. The preserved baseline comes from ATIV `2d3a3a46f1f651599dc5a1d37eb9b595c2316b6f` and AVID Core `0cce6ba838827d0bed540efc98731e74a1014456`. [Raw trial times, binary hashes, media hashes and output stream evidence](export-benchmark-results.json) are checked in; full logs, media and the baseline binary are in ignored `build/export-benchmark/`.

## Selected implementation

AVID Core exposes `RenderMode::Simple` through `Renderer::render_with_mode`. It trims each artwork input to its first frame, performs the existing composition and YUV conversion once, and loops the completed frame in memory. No intermediate image encode, disk I/O, repeated decode, repeated blur or repeated overlay is needed. [FFmpeg's loop filter](https://ffmpeg.org/ffmpeg-filters.html#loop) caches one frame per clip. Artwork and background blur remain static. Both visual treatments, flips, frame rate, H.264/HEVC choice, audio behavior, timeline hard cuts, cancellation, staging and fallback remain available. Existing Core `render()` callers keep their original behavior without source changes.

ATIV selects Simple by default; `--render-mode current` remains available for A/B testing. The engine emits an additive `timing` event with `wall_seconds`, `render_mode`, and `success` after a renderer operation returns, including failures/cancellation. Early argument/tool-discovery failures still use the existing error event alone. This wall time is distinct from progress `elapsed_seconds`, which measures the media timeline. The macOS completion message and diagnostics show elapsed wall time measured through the complete host operation.

## Duration and quality checks

The original FFmpeg `-shortest` path produced 62.133 seconds of video for 60 seconds of audio in the preserved-build run. Simple mode additionally bounds known-duration single exports to the probed audio duration; unknown duration continues to use `-shortest`. All equal-duration benchmark variants use the same explicit endpoint, so the compositor comparison does not benefit from fewer output frames.

All 1,800 decoded video frames and timestamps at 1080p, and all 300 at 4K, match exactly between the cached-frame and per-frame equal-duration outputs. The actual integrated Simple output also matches the equal-duration per-frame control exactly. The unbounded original's last 37 frames within the audio interval differ because x264 lookahead/rate control sees a different endpoint; those are not claimed to be bit-identical. The PNG candidate is timed but is not the pixel-equivalent winner because its RGB/YUV round trip can change pixels.

AVID Core tests cover asymmetric artwork, both compositions, landscape/portrait, every flip combination, 1/24/60/240 fps, exact decoded audio, fractional timeline hard cuts, stereo/48 kHz timeline audio, progress, fallback, timeout, cancellation, and preservation of an existing destination. All 37 default Core tests and 5 real FFmpeg tests passed, along with clippy, Rust 1.85 compatibility and the doc example. ATIV workspace checks, its media contract suite (27 presets, 20 previews, 3 exports and lifecycle cases), and both native Swift integration tests passed. The macOS app was built and launched via `script/build_and_run.sh --verify`; visual UI inspection was unavailable because the native computer-use connection closed. Windows/Linux packaged runtime benchmarks were not run.

## Reproduce

Keep a release engine built before these changes as `build/export-benchmark/ativ-engine-baseline`, then build the candidate with `cargo build --release --locked -p ativ-engine`. Use a disposable output directory. From the ATIV repository:

```sh
python3 script/benchmark_export.py --ffmpeg build/ffmpeg-macos-arm64/ffmpeg --ffprobe build/ffmpeg-macos-arm64/ffprobe --directory build/export-benchmark/1080p-60s --seconds 60 --rounds 3
python3 script/benchmark_export.py --ffmpeg build/ffmpeg-macos-arm64/ffmpeg --ffprobe build/ffmpeg-macos-arm64/ffprobe --directory build/export-benchmark/4k --seconds 10 --width 3840 --height 2160 --rounds 3
python3 script/benchmark_engine_export.py --baseline build/export-benchmark/ativ-engine-baseline --candidate target/release/ativ-engine --ffmpeg build/ffmpeg-macos-arm64/ffmpeg --ffprobe build/ffmpeg-macos-arm64/ffprobe --image build/export-benchmark/1080p-60s/artwork.png --audio build/export-benchmark/1080p-60s/audio.wav --directory build/export-benchmark/engine-60s --reference-video build/export-benchmark/1080p-60s/current.mp4
```

The equal-duration control must use the same artwork/audio/settings as the engine comparison. `--validate-only` on the engine script rechecks existing outputs without replacing timing measurements. Media fixtures and generated videos are intentionally excluded from Git. Both experiment branches are local; publish the Core commit before running ATIV CI against its updated Core revision pin.
