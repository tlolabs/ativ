# Build and package ATIV

## Prerequisites

- Rust 1.85 or later and Python 3.9+ for contract tests and packaging checks.
- The independently built `tlolabs/avid-core` checkout beside ATIV, named `AVID Core`.
- FFmpeg and ffprobe 9.0.1 for local development; release scripts use checksum-verified binaries.
- macOS: Xcode command-line tools with Swift 5.9 or later.
- Windows: Visual Studio 2026 Build Tools, .NET 8 SDK, and Windows App SDK tooling.
- Linux: a C17 compiler, Meson, Ninja, GTK 4, and libadwaita 1.5 or later.

## Shared engine

The workspace consumes `avid-core = { path = "../AVID Core" }`. Use this layout:

```text
Projects/
  ATIV/
  AVID Core/
```

The tested shared revision is `0cce6ba838827d0bed540efc98731e74a1014456`; CI checks out that exact revision as a sibling of ATIV. The shared repository is independently versioned. Updating it requires rerunning its tests and ATIV compatibility tests; do not copy its source into ATIV.

Run the workspace checks from the repository root (put the approved pair at the front of PATH):

```bash
cargo fmt --all -- --check
cargo check --locked --all-targets
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --workspace --locked --all-targets
./script/test_engine_integration.sh
```

Build the release engine with:

```bash
cargo build --release --locked -p ativ-engine
```

ATIV delegates media processing to `avid-core`, which uses serde/serde_json, tempfile, and same-file. Cargo.lock pins their transitive dependencies. ATIV adds no unsafe Rust. The shared GPL-3.0-only license is included in application bundles as `AVID_CORE_LICENSE.txt`; see the notices. Set `ATIV_LOG_PATH` to select a local diagnostics file during development or test automation; logs are rotated and never uploaded.

## macOS

`./script/build_and_run.sh` is the canonical local build and launch command. It assembles `dist/ATIV.app` with the native SwiftUI app, the Rust engine, and the locally available media tools.

```bash
./script/build_and_run.sh --verify
```

The script also supports `--debug`, `--logs`, and `--telemetry`. Set `FFMPEG_BIN` and `FFPROBE_BIN` to the approved matching pair. After moving/renaming a checkout, clear stale Swift caches with `swift package --package-path platform/macos --scratch-path build/native-swift clean` (use `build/swift-release-arm64` or `build/swift-release-x86_64` for release caches).

To make distribution artifacts, fetch the pinned media tools, then package on the matching native architecture:

```bash
./script/fetch_ffmpeg.sh macos <aarch64|x86_64> build/ffmpeg-macos-<arch>
FFMPEG_BIN=build/ffmpeg-macos-<arch>/ffmpeg \
FFPROBE_BIN=build/ffmpeg-macos-<arch>/ffprobe \
./script/package_macos.sh <arm64|x86_64>
```

The packaging script produces signed `.zip` and `.dmg` artifacts in `packages/`. Provide `APPLE_SIGN_IDENTITY` and `APPLE_NOTARY_PROFILE` for Developer ID signing and notarization.

## Windows

On a matching Windows runner, fetch the verified tools and package the desired architecture:

```powershell
./script/fetch_ffmpeg.sh windows <x86_64|aarch64> build/ffmpeg-windows-<arch>
./script/package_windows.ps1 -Architecture <x64|ARM64> -FfmpegDirectory build/ffmpeg-windows-<arch>
```

The WinUI project is `platform/windows/ATIV/ATIV.csproj`, and the solution is `platform/windows/ATIV.slnx`. Packaging publishes a self-contained application and creates a `.zip` artifact in `packages/`. Set the Windows certificate environment variables used by the script to sign release executables.

## Linux

For local UI development:

```bash
cargo build --release --locked -p ativ-engine
meson setup build/linux platform/linux -Dengine_path="$PWD/target/release/ativ-engine"
meson compile -C build/linux
meson test -C build/linux
```

For release packages, fetch the pinned media tools and run:

```bash
./script/fetch_ffmpeg.sh linux <x86_64|aarch64> build/ffmpeg-linux-<arch>
./script/package_linux.sh <x86_64|aarch64> build/ffmpeg-linux-<arch>
```

The script produces a Debian package and a portable `tar.gz` staging archive in `packages/`. They contain the native GTK application, ATIV engine, FFmpeg/ffprobe, desktop metadata, license, and third-party notices.

## Verification and the one-build rule

`script/test_engine_integration.sh` retains the original smoke assertions and runs `script/test_engine_contract.py`: all 27 preset previews, five aspect families with all flip combinations, H.264/AAC/yuv420p/faststart, original mono/stereo rates, 1/240 fps, legacy bitrates, private error events, source aliases, cancellation, and cleanup. POSIX fake-tool checks also exercise unknown duration, version mismatch, structured failure and the default probe timeout. Generated media lives in temporary directories.

For a direct comparison, preserve an original engine outside tracked sources and run `python3 script/test_engine_contract.py --reference /absolute/path/to/original-engine` with the same approved tools. Decoded preview/video/audio must match.

Release scripts run `verify_ffmpeg_distribution.py` against their actual bundled pair. This is a packaging capability gate, not runtime discovery or a fallback: avid-core still owns discovery and matching. The required union includes libx264, libx265, AAC, libmp3lame, PNG and the composition/timeline filters; macOS also requires AudioToolbox AAC. Shared real-media tests in each packaging job use that same pair. No system FFmpeg is installed by the workflow.

This ATIV migration does not standardize untested artifacts or modify EnCAP. Its separate macOS recipe still needs the video encoders added to the one common build. See [migration verification](migration-avid-core.md) for actual results and pending native checks.
