# Building and testing

## Checkouts and toolchains

Clone `tlolabs/ativ`. Cargo fetches the AVID Core 0.3.0 API at the immutable revision recorded in Cargo.toml and Cargo.lock. No sibling Core or EnCAP checkout is required or modified.

Use a current stable Rust toolchain and the checked-in Cargo.lock. AVID Core remains compatible with its own declared toolchain; the independent ATIV updater includes TLS dependencies with newer toolchain requirements. macOS builds need full Xcode. The shared Avalonia UI targets .NET 8 and requires the .NET 10 SDK compiler for Avalonia 12.1.3. Windows and Linux publish self-contained .NET 8 applications; Linux AppImage creation still uses linuxdeploy and appimagetool. The optional .NET LTTng trace provider is omitted from AppImages because its legacy SONAME is unavailable on the packaging baseline; application logging and media processing are unaffected. Full Xcode is needed for native macOS. CI installs each platform's requirements.

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
python3 -m venv build/release-tools
build/release-tools/bin/pip install -r script/requirements-build.txt
build/release-tools/bin/python script/test_release_infrastructure.py
python3 script/avalonia_dependencies.py --check
dotnet run --project platform/avalonia/Tests/PresentationTests.csproj -c Release -warnaserror
```

Python is build/test tooling only; no Python runtime ships in ATIV. The maintained scripts live in `script/` and use the disposable `build/release-tools` environment. Root-level `.venv` / `.venv-x86_64` environments, PyInstaller outputs, and old AVID app bundles are obsolete and should not be kept in this checkout. The former Python application is preserved only as a [remote archive branch](https://github.com/tlolabs/ativ/tree/archive/avid-python); do not restore it into the native source tree.

## Media tools

AVID Core owns source selection and builds for FFmpeg and ffprobe. ATIV acquires its exact matched runtime from the published `ffmpeg-9.0.1-r7.1` release through the shared authenticated verifier. Install GitHub CLI and authenticate it before provisioning; the verifier checks the release manifest's artifact attestation. See [runtime acquisition](ffmpeg-source-runtime.md). No FFmpeg compiler toolchain or sibling Core checkout is required.

```sh
python3 script/ffmpeg_runtime.py provision macos-arm64
./script/build_and_run.sh --verify
./script/package_macos.sh arm64
./script/package_windows.ps1 -Architecture x64
./script/package_linux.sh x86_64
./script/package_avalonia_reference.sh  # Apple Silicon only; internal artifact under build/
```

Packaging verifies Core's runtime and corresponding source before signing and verifies the packaged binaries afterward. There is no system/PATH production fallback. Both explicit engine `--ffmpeg`/`--ffprobe` paths remain available for deliberate development tests. Candidate qualification remains available only through explicit local/manual `AVID_CORE_QUALIFICATION=1` builds; ordinary builds acquire the published release.

ATIV retains native SwiftUI/AppKit for production macOS and uses shared Avalonia for Windows/Linux. Its final package signing remains: a signed/notarized macOS ZIP, an Azure Authenticode Windows portable ZIP, and a GPG-signed Linux AppImage. All native package validators run bundled discovery with an empty PATH and representative exports/previews through the actual packaged engine.

## Icons and contributor workflow

`assets/icons/ATIV-light.png`, `ATIV-dark.png`, and the editable Icon Composer document are authoritative. `build/release-tools/bin/python script/generate_icons.py` performs deterministic format/resolution conversion. Do not redraw the identity. Generated small native resources are tracked; FFmpeg, frameworks, packages and caches are ignored.

Use a feature branch, run the relevant native and Rust tests, then dispatch `native-release.yml` on that branch. Manual dispatches build and validate but do not publish. Pushes and PRs run quality checks; the candidate qualification workflow does not publish. Record actual platform evidence in the acceptance matrix; never equate a cross-compile with native runtime verification.
