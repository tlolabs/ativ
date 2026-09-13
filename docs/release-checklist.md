# Release checklist

## Before tagging

- Confirm `cargo fmt --all --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace --locked`, and `script/test_engine_integration.sh` pass.
- Confirm the native macOS app launches through `script/build_and_run.sh --verify` and exercise image selection, audio selection, all preset families, preview flips, rendering, cancellation, output replacement, and error recovery.
- Confirm Windows x64/ARM64 and Linux x86_64/ARM64 CI package jobs pass on native runners.
- Compare output dimensions, codecs, duration, and foreground/background composition against the legacy Python reference.
- Review bundled FFmpeg version, SHA-256 pins, build configuration, license, third-party notices, and package contents.
- Review accessibility names, keyboard traversal, high-contrast/dark mode, long paths, Unicode paths, read-only folders, corrupt media, and low-disk behavior.
- Complete a security review of process invocation, path handling, media limits, cancellation, update policy, and release credentials.

## Signed release

- Create a `vX.Y.Z` tag only after manually approving the native replacement.
- Supply Apple Developer ID/notarization and Windows code-signing secrets. Tagged CI intentionally fails when signing credentials are absent.
- Verify macOS signatures, notarization ticket, Gatekeeper assessment, Windows Authenticode signatures, Linux package metadata, and checksums of every published artifact.
- Install each artifact on a clean supported OS without development tools or system FFmpeg.
- Run a short end-to-end render on each supported architecture and confirm output with ffprobe.
- Publish release notes with supported OS versions, known limitations, and FFmpeg source/build information.

## Rollback

The Python/Tk application and its prior packages remain unchanged under `legacy-python/`. If a native release must be withdrawn, remove the affected release artifact, document the reason, and direct users to the last approved package. Do not delete the legacy implementation until explicit manual approval records parity across all target platforms.
