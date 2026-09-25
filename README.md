# ATIV — Artwork + Tracks Into Video

[![Native builds](https://github.com/tlolabs/ativ/actions/workflows/native-release.yml/badge.svg)](https://github.com/tlolabs/ativ/actions/workflows/native-release.yml)
[![Latest release](https://img.shields.io/github/v/release/tlolabs/ativ)](https://github.com/tlolabs/ativ/releases/latest)

ATIV combines one still image and one audio track into an H.264/AAC MP4. Choose artwork and audio, select one of 27 format presets, preview the composition, and export. Horizontal/vertical flips, frame rate, audio bitrate, progress and safe cancellation are available on every platform.

A TLO Labs open-source project maintained by Thomas Lothian.

**[Download the latest stable release](https://github.com/tlolabs/ativ/releases/latest)** · [Development builds](https://github.com/tlolabs/ativ/releases/tag/development)

ATIV processes media locally. No accounts, analytics, hosted crash reports, uploads, cloud processing, or project format. Network access is used for application updates; automatic checks can be disabled in native preferences.

| CI build/test target | Minimum | Current release packaging |
| --- | --- | --- |
| macOS (ARM64/x64) | macOS 13 | DMG and ZIP; Sparkle updates |
| Windows (x64/ARM64) | Windows 10 1809 | Per-user installer and portable ZIP |
| Linux (x64/ARM64) | GTK 4.10, libadwaita 1.4; Ubuntu 24.04 package baseline | AppImage and `.deb` |

Thomas Lothian personally tests primarily macOS (ARM64). Other entries describe configured CI build and test targets, not personal hands-on testing. Check each release's notes for artifacts omitted because a platform job failed. The intended future direct-distribution formats are ZIP on macOS and Windows, and AppImage on Linux; see [release operations](docs/RELEASING.md) for the current transition status.

All distribution packages contain the Rust engine, FFmpeg and ffprobe. End users do not install media tools separately. Package availability depends on which targets passed the release pipeline. The release notes identify incomplete builds.

The interfaces use SwiftUI/AppKit, WinUI 3 and GTK/libadwaita, respectively. They follow native appearance and control conventions, default to the system theme, and offer Light/Dark/System preferences. The same Rust media implementation powers every platform.

## Documentation

- [Installation and updates](docs/installation.md)
- [Building and testing](docs/BUILDING.md)
- [Test scope and platform evidence](docs/TESTING.md)
- [Direct dependencies and inventory](docs/DEPENDENCIES.md)
- [Simple export benchmark and timing](docs/export-benchmark.md)
- [Native architecture and AVID Core boundary](docs/ARCHITECTURE.md)
- [Packaging, signing and release operations](docs/RELEASING.md)
- [Accessibility and troubleshooting](docs/accessibility.md)
- [Cross-platform acceptance matrix](docs/acceptance-matrix.md)
- [Migration decisions and reference review](docs/native-distribution-plan.md)
- [Migration validation report and remaining gates](docs/native-distribution-report.md)
- [Release readiness checklist](docs/release-checklist.md)

## Project policies

- [Privacy](PRIVACY.md) and [security reporting](SECURITY.md)
- [Support](SUPPORT.md), [contributing](CONTRIBUTING.md) and [code of conduct](CODE_OF_CONDUCT.md)
- [Code signing policy](CODE_SIGNING_POLICY.md), [changelog](CHANGELOG.md) and [third-party notices](THIRD_PARTY_NOTICES.md)

## Development

Cargo fetches the AVID Core 0.3.0 at its pinned commit; no sibling checkout is needed. ATIV builds and bundles its own [verified FFmpeg source runtime](docs/ffmpeg-source-runtime.md). Run `cargo test --workspace --locked`. On macOS, `./script/build_and_run.sh` builds and launches the native app. See the build guide for prerequisites and all platforms. Run the bundled `ativ-engine build-info` to identify the compiled Core version and commit.

Completed exports are staged beside the destination and published only after successful rendering. Failed or cancelled exports preserve existing output and never change the selected source files.

## License

Original ATIV code and artwork are licensed under GPL-3.0-or-later. The combined engine includes GPL-3.0-only AVID Core, so the combined work cannot be offered under a later GPL version solely on ATIV's authority. Redistributed components retain their own licenses; see [the licensing review](LICENSING_REVIEW.md) and [third-party notices](THIRD_PARTY_NOTICES.md). Copyright © Thomas Lothian.
