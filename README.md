# ATIV

**Artwork + Tracks Into Video**

ATIV turns one still image and one audio track into a polished H.264/AAC MP4. It is a focused, local-first desktop app for musicians, podcasters, creators, and anyone who needs a shareable video built from artwork and sound.

## How it works

1. Choose your artwork and audio track.
2. Pick a platform-ready size or a general video format.
3. Preview the composition, then export an MP4.

ATIV keeps the workflow deliberately simple: no timeline, account, upload, or project format is required.

## What you get

- Native desktop interfaces for macOS, Windows, and Linux.
- Platform-ready portrait, landscape, square, and 4:5 presets.
- A styled image preview with horizontal and vertical flip controls.
- H.264 video and AAC audio output in a single MP4.
- Progress reporting, safe cancellation, and atomic output replacement.
- Fully local processing with no telemetry, analytics, hosted crash reporting, or automatic uploads.

## Platforms

ATIV supports macOS 12 or later on Apple Silicon and Intel, Windows 10 version 1809 or later on x64 and ARM64, and current Linux distributions with GTK 4 and libadwaita 1.5 or later.

Release packages bundle the ATIV engine with FFmpeg and ffprobe. See [building and packaging](docs/building.md) for development and release instructions.

## Build from source

```bash
cargo build --workspace
cargo test --workspace
cargo run -p ativ-engine -- check
```

On macOS, build and launch the complete local app bundle with:

```bash
./script/build_and_run.sh
```

For architecture, validation, and release details, see the [architecture](docs/architecture.md), [acceptance matrix](docs/acceptance-matrix.md), and [release checklist](docs/release-checklist.md).

## Privacy and file safety

ATIV never modifies your source artwork or audio. Completed output is staged beside the destination and published only after a successful render. If rendering fails or is cancelled, partial output is cleaned up and an existing destination file is preserved.

## License

ATIV is licensed under GPL-3.0-or-later. FFmpeg and other redistributed components retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
