# Building A.V.I.D.

## Prerequisites

- Rust 1.85 or later.
- FFmpeg and ffprobe 9.0.1 for development. Release packaging supplies verified binaries.
- macOS: Xcode command-line tools with Swift 5.9 or later.
- Windows: Visual Studio 2026 Build Tools, .NET 8 SDK, and Windows App SDK tooling.
- Linux: a C17 compiler, Meson, Ninja, GTK 4, and libadwaita 1.5 or later.

## Shared engine

```bash
cargo test --workspace
cargo build --release -p avid-engine
```

The engine has no third-party Rust dependencies and does not use unsafe Rust.

Local diagnostics are appended to the platform log directory and rotated at 1 MiB. Set `AVID_LOG_PATH` to use an explicit location during development or test automation. Logs remain on the device and are never uploaded by A.V.I.D.

## macOS

`./script/build_and_run.sh` is the canonical local kill/build/package/run entrypoint. It supports `--debug`, `--logs`, `--telemetry`, and `--verify`. The Codex Run action calls the same script.

Local bundles use ad-hoc signing. For distribution, first run `script/fetch_ffmpeg.sh macos <aarch64|x86_64> <destination>`, then provide that destination's `ffmpeg` and `ffprobe` through `FFMPEG_BIN` and `FFPROBE_BIN` to `script/package_macos.sh`. The fetch step uses immutable architecture-specific URLs and repository-pinned SHA-256 values; packaging also rejects non-system dynamic-library dependencies. The resulting bundle is signed with a Developer ID Application identity when configured, notarized, stapled, and assessed before release. Apple Silicon and Intel artifacts are built separately.

## Windows

Build the Rust engine for `x86_64-pc-windows-msvc` or `aarch64-pc-windows-msvc`, then build `platform/windows/AVID.sln` with the matching platform. Release automation places `avid-engine.exe`, `ffmpeg.exe`, and `ffprobe.exe` beside the packaged WinUI executable.

## Linux

Build the Rust engine, then configure the native UI with Meson:

```bash
meson setup build/linux platform/linux -Dengine_path="$PWD/target/release/avid-engine"
meson compile -C build/linux
meson test -C build/linux
```

The release AppImage staging tree includes the native GTK executable, Rust engine, FFmpeg/ffprobe, desktop metadata, license, and notices.
