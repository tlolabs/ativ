# Simple export mode

`Renderer::render_with_mode(&request, RenderMode::Simple, &token, &events)` caches the first fully composed YUV frame per clip. The existing `render()` method and `RenderMode::PerFrame` retain the original behavior. This is an additive API; no stored settings or request fields change.

The source is trimmed before scaling, crop, blur and overlay. The completed frame is looped after YUV conversion, with explicit timestamps at the requested fps. Timeline duration trimming occurs after the loop so concat advances correctly. Artwork and blur are static; clip changes remain hard cuts. There are no intermediate files. Cache memory is roughly width × height × 1.5 bytes per clip, plus FFmpeg's existing decode/encode buffers.

Known-duration single exports also pass an output duration to avoid the old `-shortest` encoder-buffered tail. Unknown duration retains `-shortest`. Stage::Compositing prepares the command; actual compositing occurs inside the Encoding process. Cancellation, timeouts, progress, staging, protected paths, hardware fallback, codecs and audio handling use the existing shared runner.

## Benchmark evidence

The sibling ATIV experiment (`codex/simple-export-benchmark`) contains reproducible `script/benchmark_export.py`, `script/benchmark_engine_export.py`, `docs/export-benchmark.md`, and `docs/export-benchmark-results.json`. All use ATIV's approved FFmpeg 9.0.1 arm64 build. Measurements on an Apple M5 Max, 128 GiB, macOS 26.6.2, software libx264 / AAC 128k / 30 fps:

| Equal-duration export | Per-frame | Saved PNG including preparation | Cached frame |
|---|---:|---:|---:|
| 60 seconds, 1080p | 10.268 s | 3.530 s | 1.848 s |
| 10 seconds, 4K | 4.668 s | 2.378 s | 1.325 s |

Medians of three rotated runs after one excluded warmup per variant. Generated detailed 2400×1600 artwork and mono 44.1 kHz audio; encoder settings held constant. Cached output decoded pixels and timestamps exactly match the per-frame control at the same output duration. A saved PNG is slower and adds a color-conversion round trip. End-to-end ATIV engine timing was 11.953 s for the preserved build and 2.025 s for Simple (5.90×); the original build also emitted an extra frozen video tail. The detailed ATIV report distinguishes equal-duration controls from this real-engine comparison and records measurement limits.

## Verification

37 default Core tests, five real FFmpeg tests, clippy, Rust 1.85 all-target compatibility, and the doc example passed. Added coverage checks both visual treatments, asymmetric artwork/flips, portrait/landscape, frame counts and cadence at 1/24/60/240 fps, decoded audio equivalence, fractional timeline hard cuts, cancellation/publication safety, timeout and automatic fallback. Existing legacy command graph snapshots still pass unchanged.

```sh
cargo test --locked --all-targets
cargo test --locked --test ffmpeg -- --ignored --test-threads=1
cargo clippy --locked --all-targets -- -D warnings
cargo +1.85.0 check --locked --all-targets
```

Real-media tests require the approved FFmpeg/ffprobe directory on PATH. Runtime performance evidence is macOS only. Existing callers can opt in independently; ATIV's experiment branch defaults to Simple while retaining a current-mode CLI option.
