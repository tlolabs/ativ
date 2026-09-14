# Building and testing

## Checkouts and toolchains

Clone `tlolabs/ativ` and `tlolabs/avid-core` into sibling directories named `ATIV` and `AVID Core`. The tested shared revision is `0cce6ba838827d0bed540efc98731e74a1014456`. ENcap is a read-only architectural reference and is not a build dependency. See [the migration plan](native-distribution-plan.md) for the exact reference revision.

Use a current stable Rust toolchain and the checked-in Cargo.lock. AVID Core remains compatible with its own declared toolchain; the independent ATIV updater includes TLS dependencies with newer toolchain requirements. macOS builds need full Xcode, Windows needs .NET 8+ and Windows App SDK build tools, and Linux needs GTK 4.10+, libadwaita 1.4+, json-glib, Meson and Ninja. CI installs each platform's requirements.

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
python3 -m venv build/release-tools
build/release-tools/bin/pip install -r script/requirements-build.txt
build/release-tools/bin/python script/test_release_infrastructure.py
```

Python is build/test tooling only; no Python runtime ships in ATIV. The maintained scripts live in `script/` and use the disposable `build/release-tools` environment. Root-level `.venv` / `.venv-x86_64` environments, PyInstaller outputs, and old AVID app bundles are obsolete and should not be kept in this checkout. The former Python application is preserved only as a [remote archive branch](https://github.com/tlolabs/ativ/tree/archive/avid-python); do not restore it into the native source tree.

## Media tools

`script/fetch_ffmpeg.sh <macos|windows|linux> <x86_64|aarch64> <destination>` downloads the exact same SHA-256-pinned FFmpeg 9.0.1 pairs as ENcap. Put that directory on PATH for `script/test_engine_integration.sh`. That suite generates local test media, verifies all presets, previews, H.264/AAC exports, cancellation, failure cleanup and input preservation. Packaging additionally checks the union of required capabilities through `verify_ffmpeg_distribution.py`.

Update the pinned URL and digest together only after validating the matching pair on each architecture. Do not commit tool binaries. Keep upstream license/build notices and the shared-core license with the package.

## macOS

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export FFMPEG_BIN="$PWD/build/ffmpeg-macos-arm64/ffmpeg"
export FFPROBE_BIN="$PWD/build/ffmpeg-macos-arm64/ffprobe"
./script/build_and_run.sh --verify
ATIV_ENGINE_PATH="$PWD/target/debug/ativ-engine" swift test --package-path platform/macos
./script/package_macos.sh arm64
python3 script/validate_package.py build/package-macos-arm64/ATIV.app macos-arm64
```

Use `x86_64` on an Intel runner. The run script supports `--debug`, `--logs`, `--telemetry` (local OS logs), and `--verify`. It downloads checksum-pinned Sparkle into ignored build storage, stages a proper app bundle, and launches through Launch Services. Package scripts use macOS 13 as the deployment target.

## Windows

Use a native x64 or ARM64 runner. Install Inno Setup 6.7.1 for installer generation.

```powershell
./script/package_windows.ps1 -Architecture x64 -FfmpegDirectory build/ffmpeg-windows-x64
./script/test_windows_native.ps1 -Architecture x64
```

The smoke suite exercises the actual C# engine client, WinUI startup, installer deployment, an upgrade over an existing install, and uninstall. ARM64 uses the same path with `-Architecture ARM64`. Build scripts stop on native compiler, signer or validator failures.

## Linux

```sh
./script/package_linux.sh x86_64 build/ffmpeg-linux-x86_64
./script/test_linux_native.sh x86_64
```

Use `aarch64` on ARM64. AppImage tooling is checksum-pinned and the GTK plugin is pinned to an immutable commit. The smoke tests use Xvfb and a D-Bus session, launch the staged GTK app and actual AppImage, and require the native client to decode all presets. CI also installs the actual `.deb`, launches it using its compiled engine path, reinstalls it, and removes it. `.deb` structure, desktop entries, icons, machine types and bundled discovery are validated before artifacts are uploaded.

## Icons and contributor workflow

`assets/icons/ATIV-light.png`, `ATIV-dark.png`, and the editable Icon Composer document are authoritative. `build/release-tools/bin/python script/generate_icons.py` performs deterministic format/resolution conversion. Do not redraw the identity. Generated small native resources are tracked; FFmpeg, frameworks, packages and caches are ignored.

Use a feature branch, run the relevant native and Rust tests, then dispatch `native-release.yml` on that branch. Manual dispatches build and validate but do not publish. Pushes to main publish development builds. Record actual platform evidence in the acceptance matrix; never equate a cross-compile with native runtime verification.
