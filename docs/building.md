# Building and testing

## Checkouts and toolchains

Clone `tlolabs/ativ` and `tlolabs/avid-core` into sibling directories named `ATIV` and `AVID Core`. Check out the exact shared commit in `runtime/core-revision`; the Rust build and CI enforce that pin. ENcap is a read-only architectural reference and is not a build dependency. See [the migration plan](native-distribution-plan.md) for the exact reference revision.

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

Normal local, CI, development and release builds consume only AVID Core's authenticated runtime. Python 3.11+ and an authenticated GitHub CLI are required for acquisition. Core owns the version, recipe, checksums, signatures, corresponding source, notices and target mapping.

```sh
python3 script/core_runtime.py provision macos-arm64
./script/build_and_run.sh --verify
./script/package_macos.sh arm64
./script/package_windows.ps1 -Architecture x64
./script/package_linux.sh x86_64
```

Packaging chooses the target and validates the complete Core payload before signing. Its cache is `build/core-runtime/<Core commit>/<target>`; existing entries are revalidated. There is no independent FFmpeg URL, version selector, arbitrary-binary input or PATH fallback. Explicit engine `--ffmpeg`/`--ffprobe` options remain available for deliberate development tests, but packaging does not use them.

Core's selected runtime is currently a candidate without published production assets. Normal acquisition therefore fails clearly before overwriting any working package. See [the audit and blockers](core-runtime-migration.md). The separate qualification harness accepts an explicit validated Core candidate and uses the same staging, provenance and packaged-media checks as production:

```sh
bash script/package_core_candidate_macos.sh '/absolute/path/to/Core/dist/runtime-directory'
```

macOS packaging retains ATIV's signing, notarization, Sparkle and installer ownership. Windows packaging retains its .NET build, Authenticode signing and Inno Setup installer. Linux retains its GTK, AppImage and Debian packaging. All native package validators run bundled discovery with an empty PATH and representative exports/previews through the actual packaged engine.

## Icons and contributor workflow

`assets/icons/ATIV-light.png`, `ATIV-dark.png`, and the editable Icon Composer document are authoritative. `build/release-tools/bin/python script/generate_icons.py` performs deterministic format/resolution conversion. Do not redraw the identity. Generated small native resources are tracked; FFmpeg, frameworks, packages and caches are ignored.

Use a feature branch, run the relevant native and Rust tests, then dispatch `native-release.yml` on that branch. Manual dispatches build and validate but do not publish. Pushes to main publish development builds. Record actual platform evidence in the acceptance matrix; never equate a cross-compile with native runtime verification.
