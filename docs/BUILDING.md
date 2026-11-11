# Building and testing

## Checkouts and toolchains

Clone `tlolabs/ativ`. Cargo uses AVID Core 0.3.3 at immutable revision `8e27a86ec106028d93130de35a35c0eeda7a9ce3`, recorded in Cargo.toml and Cargo.lock. The unmodified source snapshot in `vendor/avid-core` replaces that exact Git source through `.cargo/config.toml`, so this local Core release does not need to be published upstream first. Run Cargo from this checkout root; see [snapshot verification](../vendor/avid-core/README.md). No sibling Core or EnCAP checkout is required or modified. See the [integration record](core-0.3.3-integration.md) for verification scope.

Use a Rust toolchain satisfying the workspace minimum (Rust 1.88+) and the checked-in Cargo.lock. AVID Core remains compatible with its own declared toolchain; the independent ATIV updater includes TLS dependencies with newer toolchain requirements (Rust 1.88 minimum). macOS production builds need Xcode for SwiftUI/AppKit. Core's source-built image codecs also require a target C compiler and CMake on every platform; the selected scalar libjpeg-turbo build does not require NASM. The shared Windows and Linux presentation layer uses Qt 6 Widgets and C++17 via CMake. On Windows, MSVC or clang-cl with CMake is used alongside windeployqt. On Linux, `qt6-base-dev` and standard C++ build tools are used, and Linux AppImage creation uses linuxdeploy and appimagetool. The archived CI recipes document each platform's requirements; install them locally for native qualification.

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
python3 -m venv build/release-tools
build/release-tools/bin/pip install --require-hashes -r script/requirements-build.lock
build/release-tools/bin/python script/test_release_infrastructure.py
python3 script/dependency_inventory.py --check
```

Python is build/test tooling only; no Python runtime ships in ATIV. The maintained scripts live in `script/` and use the disposable `build/release-tools` environment. For reproducible build verification, `script/requirements-build.lock` provides pinned SHA-256 hashes for all wheels and source distributions of build dependencies. For ordinary nonblocking local development, unhashed installation from `script/requirements-build.txt` remains supported. Root-level `.venv` / `.venv-x86_64` environments, PyInstaller outputs, and old AVID app bundles are obsolete and should not be kept in this checkout. The former Python application is preserved only as a [remote archive branch](https://github.com/tlolabs/ativ/tree/archive/avid-python); do not restore it into the native source tree.

## Media tools

AVID Core owns source selection and builds for FFmpeg and ffprobe. ATIV defaults to the authenticated per-platform releases pinned in `runtime/platform-runtimes.json`, acquired through `script/platform_runtime.py` and the shared Core verifier. Install GitHub CLI and authenticate it before provisioning; acquisition verifies the pinned release, provider attestation, archive, metadata, executable and corresponding-source identities. See [runtime acquisition](ffmpeg-source-runtime.md). No FFmpeg compiler toolchain or sibling Core checkout is required.

The Rust source pin and media-runtime publication have independent identities. Updating Core's Rust API does not replace the authenticated FFmpeg runtime. The older `ffmpeg-9.0.1-r7.1` pin remains an explicit compatibility path selected with `ATIV_CORE_RUNTIME_SOURCE=legacy`; ordinary builds use the platform default and never fall back silently.

```sh
python3 script/ffmpeg_runtime.py provision macos-arm64
./script/build_and_run.sh --verify
./script/package_macos.sh arm64
./script/package_windows.ps1 -Architecture x64
./script/package_linux.sh x86_64
./script/package_qt_reference.sh  # Apple Silicon only; internal artifact under build/
```

Packaging verifies Core's runtime and corresponding source before signing and verifies the packaged binaries afterward. There is no system/PATH production fallback. Both explicit engine `--ffmpeg`/`--ffprobe` paths remain available for deliberate development tests. Candidate qualification remains available only through explicit local/manual `AVID_CORE_QUALIFICATION=1` builds; ordinary builds acquire the published release.

ATIV retains native SwiftUI/AppKit for production macOS and uses shared Qt 6 Widgets for Windows/Linux. Package formats are macOS ZIP, Windows portable ZIP and Linux AppImage. macOS distributable app packages require Developer ID signing and notarization; other platforms retain their existing signing policy. Before publication, qualify each artifact with native build, package integrity, architecture, runtime dependency, launch and functional checks. Package validators check bundled discovery with an empty PATH; run representative exports/previews through the actual packaged engine as well. A source-release tag or scheduled smoke result does not establish artifact qualification.

## Optional Apple transcription helper

Apple silicon native builds additionally compile the isolated transcription helper
with Swift 6.3+, Xcode, and the Apple Metal toolchain. The base UI continues to
target macOS 13; the helper targets macOS 14 and is not linked into that UI or
packaged in Intel builds. If Xcode lacks Metal, install its component with
`xcodebuild -downloadComponent MetalToolchain`.

Select a local Apple silicon Xcode toolchain supplying Swift 6.3 or later and
the Metal compiler. The archived build recipe predates this helper and is retained
unchanged as historical evidence; it does not establish toolchain compatibility
for the current candidate. The application still targets macOS 13 and the
optional helper macOS 14. Verify the actual compiler and deployment targets
locally before packaging.

The exact reviewed Core Apple source is included as a small attributed archive in
`vendor/avid-transcription`; build tooling verifies its archive and file hashes
before extracting to `build/transcription-core`. No sibling checkout or root
SwiftPM package URL is required. The helper's nested package paths and resolved
dependencies are explicit. See [integration and limitations](transcription-integration.md).

```sh
python3 script/transcription_runtime.py acquire
swift test --package-path build/transcription-core/apple/AVIDTranscription --scratch-path build/transcription-contract-tests
swift test --package-path build/transcription-core/apple/AVIDTranscriptionEngines --scratch-path build/transcription-engine-tests --force-resolved-versions
python3 -B build/transcription-core/script/test_transcription_catalog.py
swift test --package-path platform/transcription-helper --scratch-path build/transcription-helper-tests --force-resolved-versions
python3 script/transcription_runtime.py validate build/package-macos-arm64/ATIV.app macos-arm64
```

The standard native build/package scripts stage the helper, resource/Metal bundles,
required libraries, and SDK/model notices. Package checks include helper identity,
integrity, resources, and a relocated catalog invocation without developer PATH
or an existing model cache. Model weights remain optional downloads after app
installation. Actual packaged inference requires separately installed verified
models and must be recorded independently of catalog/package discovery.

With installed test models and a short known recording, run the offline packaged
smoke check explicitly (no models are downloaded by this command):

```sh
python3 script/smoke_transcription.py \
  --helper build/package-macos-arm64/ATIV.app/Contents/Helpers/ATIVTranscriptionHelper.app/Contents/MacOS/ATIVTranscriptionHelper \
  --cache /absolute/test-model-cache --audio /absolute/known-recording.m4a \
  --output build/transcription-smoke
```

## Icons and contributor workflow

`assets/icons/ATIV-light.png`, `ATIV-dark.png`, and the editable Icon Composer document are authoritative. `build/release-tools/bin/python script/generate_icons.py` performs deterministic format/resolution conversion. Do not redraw the identity. Generated small native resources are tracked; FFmpeg, frameworks, packages and caches are ignored.

Run the relevant native and Rust tests locally. Legacy workflows are inactive under `.github/workflow-archive/2026-11-08/`; do not dispatch or restore them. The weekly tagged-release smoke policy in AGENTS.md supersedes older CI descriptions. Direct commits are permitted. Record actual platform evidence in the acceptance matrix; never equate a cross-compile with native runtime verification.

### Standard local macOS packaging

Set `APPLE_SIGN_IDENTITY` to the existing Developer ID Application identity and
`APPLE_NOTARY_PROFILE` to an existing Keychain profile, then run
`./script/package_macos.sh arm64` (or `x86_64` on that native host). The command
requires Apple acceptance, staples the app, rebuilds the ZIP, and verifies the
extracted bundle. No profile is enrolled automatically.

`./script/package_macos.sh arm64 --development` explicitly produces an ad-hoc,
unnotarized `-development-unnotarized.zip`, unsuitable for distribution or an
authenticated update feed. Ordinary `build_and_run.sh` debug/test use is unchanged.
