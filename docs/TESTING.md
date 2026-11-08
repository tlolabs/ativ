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

The release infrastructure tests use the pinned Python requirements and `script/test_release_infrastructure.py`. Run `./script/test_engine_integration.sh macos-arm64` to test the acquired Core runtime, media operations, cancellation and rejection of missing or damaged package files. ATIV has no independent FFmpeg source-builder tests. The archived native workflow describes the same package and media tests for each target when `owner_testing=false`. Owner build mode skips acceptance tests; a build result alone does not establish that they passed. Record platform-specific validation in [the acceptance matrix](acceptance-matrix.md).

The main personally tested platform is macOS (ARM64). Archived recipes cover macOS (ARM64/x64), Windows (x64/ARM64) and Linux (x64/ARM64). Legacy workflows are inactive; the weekly tagged-release smoke policy in AGENTS.md is authoritative. Run applicable archived commands locally, without re-enabling or dispatching the workflows. A release may omit a platform whose required jobs failed; check its release notes and checksums.

For native Mac process tests, select full Xcode so XCTest is available, create the fixtures, and point the client tests at the packaged engine:

```sh
python3 script/create_smoke_media.py build/native-fixtures
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
ATIV_TEST_MEDIA="$PWD/build/native-fixtures" \
ATIV_ENGINE_PATH="$PWD/build/package-macos-arm64/ATIV.app/Contents/MacOS/ativ-engine" \
swift test --package-path platform/macos --scratch-path build/native-tests
```

Shared Qt smoke checks start the application bundle and decode 27 engine presets. The native Python integration harness (`script/test_engine_fixtures.py`) probes, previews and exports through the packaged engine. The Qt test suite (`ativ-qt-tests`) verifies missing engine detection, INI migration, preferences roundtrip, preview scaling, destination path validation, render export, cancellation, and smoke reports. Native tests require their respective Windows and Linux hosts; the internal Mac reference is an additional build and launch check, never a production release artifact. Manual Narrator/Orca checks remain necessary.

Both Qt test suites set `ATIV_PREFERENCES_DIR` to a temporary directory so they do not read or overwrite personal application settings. The application uses its standard settings location when this override is absent.
