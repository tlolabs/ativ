# Testing

Run the checks that match the changed area. For the shared engine:

```sh
cargo fmt --all -- --check
cargo check --workspace --all-targets --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --all-targets --locked
python3 script/test_runtime_ownership.py
python3 script/test_ffmpeg_build.py
python3 script/dependency_inventory.py --check
```

The release infrastructure tests use the pinned Python requirements and `script/test_release_infrastructure.py`. The native CI workflow runs the Rust suite, an actual source-built FFmpeg contract suite, native UI/process integration and package smoke tests for each configured target. A passing cross-compile is not a native runtime test. Record platform-specific validation in [the acceptance matrix](acceptance-matrix.md).

The main personally tested platform is macOS (ARM64). GitHub CI currently builds and tests macOS (ARM64/x64), Windows (x64/ARM64) and Linux (x64/ARM64), subject to the actual status of each run. A release may omit a platform whose required jobs failed; check its release notes and checksums.
