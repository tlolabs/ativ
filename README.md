# A.V.I.D. — Audio Visual Integration & Distribution

A.V.I.D. turns a still image and an audio recording into a polished H.264/AAC MP4. Version 0.2 replaces the media engine with Rust and provides native SwiftUI/AppKit, WinUI 3, and GTK 4/libadwaita applications.

The original Python/Tk application remains available in [`legacy-python/`](legacy-python/) for comparison until the native replacement is manually approved.

## Architecture

- `crates/avid-core`: shared presets, validation, FFmpeg/ffprobe orchestration, progress, cancellation, and atomic output publication.
- `crates/avid-engine`: stable newline-delimited process API used by every native UI.
- `platform/macos`: SwiftUI/AppKit application for Apple Silicon and Intel.
- `platform/windows`: WinUI 3 application for x64 and ARM64.
- `platform/linux`: GTK 4/libadwaita application.
- `docs`: behavior, architecture, protocol, build, and packaging references.

FFmpeg 9.0.1 and ffprobe are required architectural dependencies and are bundled in release packages. Development builds may use compatible tools from `PATH`.

## Build the shared engine

```bash
cargo build --workspace
cargo test --workspace
cargo run -p avid-engine -- check
```

## Run the macOS application

```bash
./script/build_and_run.sh
```

The script builds the Rust engine and SwiftUI application, stages a proper local `.app` bundle, includes FFmpeg/ffprobe, and launches it. See [`docs/building.md`](docs/building.md) for all platforms and release packaging.

## Safety and privacy

A.V.I.D. never alters input files, writes completed output atomically, and cleans up partial renders after errors or cancellation. It does not include telemetry, analytics, hosted crash reporting, or automatic diagnostic uploads.

## License

A.V.I.D. is GPL-3.0-or-later. FFmpeg builds and other redistributed components retain their own licenses; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
