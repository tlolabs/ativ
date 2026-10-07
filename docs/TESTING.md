# Testing

Run the checks that match the changed area. For the shared engine:

```sh
cargo fmt --all -- --check
cargo check --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
python3 script/test_runtime_ownership.py
python3 script/dependency_inventory.py --check
python3 script/test_engine_fixtures.py build/native-fixtures
```

The release infrastructure tests use the pinned Python requirements and `script/test_release_infrastructure.py`. Run `./script/test_engine_integration.sh macos-arm64` to test the acquired Core runtime, media operations, cancellation and rejection of missing or damaged package files. ATIV has no independent FFmpeg source-builder tests. Native CI runs the same package and media tests on each target when `owner_testing=false`. Owner build mode skips acceptance tests; a build result alone does not establish that they passed. Record platform-specific validation in [the acceptance matrix](acceptance-matrix.md).

The main personally tested platform is macOS (ARM64). GitHub CI currently builds and tests macOS (ARM64/x64), Windows (x64/ARM64) and Linux (x64/ARM64), subject to the actual status of each run. A release may omit a platform whose required jobs failed; check its release notes and checksums.

For native Mac process tests, select full Xcode so XCTest is available, create the fixtures, and point the client tests at the packaged engine:

```sh
python3 script/create_smoke_media.py build/native-fixtures
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
ATIV_TEST_MEDIA="$PWD/build/native-fixtures" \
ATIV_ENGINE_PATH="$PWD/build/package-macos-arm64/ATIV.app/Contents/MacOS/ativ-engine" \
swift test --package-path platform/macos --scratch-path build/native-tests
```

Shared Qt smoke checks start the application bundle and decode 27 engine presets. The native Python integration harness (`script/test_engine_fixtures.py`) probes, previews and exports through the packaged engine. The Qt test suite (`ativ-qt-tests`) verifies missing engine detection, INI migration, preferences roundtrip, preview scaling, destination path validation, render export, cancellation, and smoke reports. CI runs native tests on both Windows and Linux; the internal Mac reference is an additional build and launch gate, never a production release artifact. Manual Narrator/Orca checks remain necessary.
