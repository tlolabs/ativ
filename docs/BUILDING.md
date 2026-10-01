# Building and testing

## Checkouts and toolchains

Clone `tlolabs/ativ`. Cargo fetches the AVID Core 0.3.0 API at the immutable revision recorded in Cargo.toml and Cargo.lock. No sibling Core or EnCAP checkout is required or modified.

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

AVID Core owns source selection and builds for FFmpeg and ffprobe. ATIV acquires its exact matched runtime through the shared authenticated verifier. See [runtime acquisition](ffmpeg-source-runtime.md). Production acquisition remains blocked until the durable Core release is published and pinned. For unpublished host qualification, explicitly set `AVID_CORE_QUALIFICATION=1` and dispatch the reviewed candidate workflow.

```sh
python3 script/ffmpeg_runtime.py provision macos-arm64
./script/build_and_run.sh --verify
./script/package_macos.sh arm64
./script/package_windows.ps1 -Architecture x64
./script/package_linux.sh x86_64
```

Packaging verifies ATIV's source payload before signing and verifies the packaged binaries afterward. There is no system/PATH production fallback. Both explicit engine `--ffmpeg`/`--ffprobe` paths remain available for deliberate development tests. Manual workflow dispatch supports `clean_ffmpeg=true` for a fresh source qualification.

ATIV owns its native UI and final package signing: a signed/notarized macOS ZIP, an Azure Authenticode Windows portable ZIP, and a GPG-signed Linux AppImage. All native package validators run bundled discovery with an empty PATH and representative exports/previews through the actual packaged engine.

## Icons and contributor workflow

`assets/icons/ATIV-light.png`, `ATIV-dark.png`, and the editable Icon Composer document are authoritative. `build/release-tools/bin/python script/generate_icons.py` performs deterministic format/resolution conversion. Do not redraw the identity. Generated small native resources are tracked; FFmpeg, frameworks, packages and caches are ignored.

Use a feature branch, run the relevant native and Rust tests, then dispatch `native-release.yml` on that branch. Manual dispatches build and validate but do not publish. Pushes and PRs run quality checks; the candidate qualification workflow does not publish. Record actual platform evidence in the acceptance matrix; never equate a cross-compile with native runtime verification.
