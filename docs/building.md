# Build and package ATIV

## Prerequisites

- Rust 1.85 or later.
- FFmpeg and ffprobe 9.0.1 for local development; release scripts use checksum-verified binaries.
- macOS: Xcode command-line tools with Swift 5.9 or later.
- Windows: Visual Studio 2026 Build Tools, .NET 8 SDK, and Windows App SDK tooling.
- Linux: a C17 compiler, Meson, Ninja, GTK 4, and libadwaita 1.5 or later.

## Shared engine

Run the workspace checks from the repository root:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace --locked
./script/test_engine_integration.sh
```

Build the release engine with:

```bash
cargo build --release --locked -p ativ-engine
```

ATIV uses no third-party Rust dependencies and no unsafe Rust. Set `ATIV_LOG_PATH` to select a local diagnostics file during development or test automation; logs are rotated and never uploaded.

## macOS

`./script/build_and_run.sh` is the canonical local build and launch command. It assembles `dist/ATIV.app` with the native SwiftUI app, the Rust engine, and the locally available media tools.

```bash
./script/build_and_run.sh --verify
```

The script also supports `--debug`, `--logs`, and `--telemetry`.

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
