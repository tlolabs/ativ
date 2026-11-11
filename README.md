# ATIV — Artwork + Tracks Into Video

[![Weekly release smoke](https://github.com/tlolabs/ativ/actions/workflows/weekly-release-smoke.yml/badge.svg)](https://github.com/tlolabs/ativ/actions/workflows/weekly-release-smoke.yml)
[![Latest release](https://img.shields.io/github/v/release/tlolabs/ativ)](https://github.com/tlolabs/ativ/releases/latest)

ATIV combines one still image and one audio track into an H.264/AAC MP4. Choose artwork and audio, select one of 27 format presets, preview the composition, and export. Horizontal/vertical flips, frame rate, audio bitrate, progress and safe cancellation are available on every platform.

A TLO Labs open-source project maintained by Thomas Lothian.

**[Download the latest stable release](https://github.com/tlolabs/ativ/releases/latest)** · [All releases](https://github.com/tlolabs/ativ/releases)

ATIV processes media locally. No accounts, analytics, hosted crash reports, uploads, cloud processing, or project format. Network access is used for application updates; automatic checks can be disabled in native preferences.

| Supported native target | Minimum | Package format |
| --- | --- | --- |
| macOS (ARM64/x64) | macOS 13 | ZIP; Sparkle updates |
| Windows (x64/ARM64) | Windows 10 1809 | Portable ZIP |
| Linux (x64/ARM64) | Ubuntu 24.04 packaging baseline | AppImage |

Thomas Lothian personally tests primarily macOS (ARM64). Other entries describe supported native targets, not personal hands-on testing or current release qualification. Check each release's assets and notes for available platforms and actual verification. Automatic CI runs a weekly Linux/Windows smoke check for a new stable source-release tag; it does not publish packages. See [release operations](docs/RELEASING.md) for target verification and publication rules.

All distribution packages contain the Rust engine, FFmpeg and ffprobe. End users do not install media tools separately. Package availability depends on which targets passed native verification.

The interfaces use SwiftUI/AppKit on production macOS and one shared Qt 6 Widgets UI on Windows and Linux, respectively. An internal Qt macOS ARM64 build is available for development and parity testing. They follow native appearance and control conventions, default to the system theme, and offer Light/Dark/System preferences. The same Rust media implementation powers every platform.

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
- [Historical native distribution plan and report](docs/native-distribution-plan.md)
- [Release readiness checklist](docs/release-checklist.md)

## Project policies

- [Privacy](PRIVACY.md) and [security reporting](SECURITY.md)
- [Support](SUPPORT.md), [contributing](CONTRIBUTING.md) and [code of conduct](CODE_OF_CONDUCT.md)
- [Code signing policy](CODE_SIGNING_POLICY.md), [changelog](CHANGELOG.md) and [third-party notices](THIRD_PARTY_NOTICES.md)

## Development

Cargo uses AVID Core 0.3.3 at its immutable commit through the checked-in, unmodified source snapshot; no sibling checkout or upstream publication is needed. ATIV embeds the matched, authenticated [AVID Core runtime](docs/ffmpeg-source-runtime.md), whose release identity is independent of the Rust source pin. Run `cargo test --workspace --locked`. On macOS, `./script/build_and_run.sh` builds and launches the native app. See the build guide for prerequisites and all platforms, and the [Core integration record](docs/core-0.3.3-integration.md) for source identity and verification. Run the bundled `ativ-engine build-info` to identify the compiled Core version and commit.

Completed exports are staged beside the destination and published only after successful rendering. Failed or cancelled exports preserve existing output and never change the selected source files.

## License

Original ATIV code and artwork and the pinned AVID Core library are licensed under GPL-3.0-or-later. Redistributed components retain their own licenses; see [the licensing review](LICENSING_REVIEW.md) and [third-party notices](THIRD_PARTY_NOTICES.md). Copyright © Thomas Lothian.
