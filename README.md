# ATIV — Artwork + Tracks Into Video

[![Native builds](https://github.com/tlolabs/ativ/actions/workflows/native-release.yml/badge.svg)](https://github.com/tlolabs/ativ/actions/workflows/native-release.yml)
[![Latest release](https://img.shields.io/github/v/release/tlolabs/ativ)](https://github.com/tlolabs/ativ/releases/latest)

ATIV combines one still image and one audio track into an H.264/AAC MP4. Choose artwork and audio, select one of 27 format presets, preview the composition, and export. Horizontal/vertical flips, frame rate, audio bitrate, progress and safe cancellation are available on every platform.

**[Download the latest stable release](https://github.com/tlolabs/ativ/releases/latest)** · [Development builds](https://github.com/tlolabs/ativ/releases/tag/development)

ATIV processes media locally. No accounts, analytics, hosted crash reports, uploads, cloud processing, or project format. Network access is used for application updates; automatic checks can be disabled in native preferences.

| Platform | Architectures | Minimum | Distribution |
| --- | --- | --- | --- |
| macOS | Apple Silicon, Intel | macOS 13 | DMG, ZIP; Sparkle updates |
| Windows | x64, ARM64 | Windows 10 1809 | Per-user installer, portable ZIP |
| Linux | x64, ARM64 | GTK 4.10, libadwaita 1.4; Ubuntu 24.04 package baseline | AppImage, `.deb`, archive |

All distribution packages contain the Rust engine, FFmpeg and ffprobe. End users do not install media tools separately. Package availability depends on which targets passed the release pipeline. The release notes identify incomplete builds.

The interfaces use SwiftUI/AppKit, WinUI 3 and GTK/libadwaita, respectively. They follow native appearance and control conventions, default to the system theme, and offer Light/Dark/System preferences. The same Rust media implementation powers every platform.

## Documentation

- [Installation and updates](docs/installation.md)
- [Building and testing](docs/building.md)
- [Native architecture and AVID Core boundary](docs/architecture.md)
- [Packaging, signing and release operations](docs/releasing.md)
- [Accessibility and troubleshooting](docs/accessibility.md)
- [Cross-platform acceptance matrix](docs/acceptance-matrix.md)
- [Migration decisions and reference review](docs/native-distribution-plan.md)
- [Release readiness checklist](docs/release-checklist.md)

## Development

Clone `tlolabs/avid-core` beside ATIV as `AVID Core`, at the revision pinned in the workflow. Run `cargo test --workspace --locked`. On macOS, `./script/build_and_run.sh` builds and launches the native app. See the build guide for prerequisites and all platforms.

Completed exports are staged beside the destination and published only after successful rendering. Failed or cancelled exports preserve existing output and never change the selected source files.

## License

ATIV host code is GPL-3.0-or-later. The combined engine includes GPL-3.0-only AVID Core. Redistributed components retain their own licenses; see [third-party notices](THIRD_PARTY_NOTICES.md).
