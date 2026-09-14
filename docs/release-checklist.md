# ATIV release checklist

## Prepare the release

- Confirm the sibling `AVID Core` revision matches the CI pin; rerun its format/check/test/clippy and ignored FFmpeg tests with the release pair.
- Confirm `cargo fmt --all --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace --locked`, and `./script/test_engine_integration.sh` pass.
- Launch the macOS app with `./script/build_and_run.sh --verify` and exercise artwork selection, track selection, every preset family, preview flips, rendering, cancellation, output replacement, and error recovery.
- Confirm the Windows x64/ARM64 and Linux x86_64/ARM64 package jobs pass on their native runners.
- Test representative portrait, landscape, square, and 4:5 exports; verify dimensions, H.264/AAC codecs, duration, and artwork composition.
- Confirm `verify_ffmpeg_distribution.py` passes for each actual bundle, with libx264/libx265/AAC/libmp3lame and macOS AudioToolbox from the same build. Include `AVID_CORE_LICENSE.txt`.
- Review FFmpeg version, SHA-256 pins, build configuration, license, third-party notices, and package contents.
- Check accessibility labels and keyboard traversal, dark/high-contrast appearance, long and Unicode paths, read-only destinations, corrupt media, and low-disk behavior.
- Review process invocation, path handling, media limits, cancellation, update policy, and release credentials.

## Sign and publish

- Create a `vX.Y.Z` tag only after approving the release build.
- Supply Apple Developer ID/notarization and Windows code-signing credentials; tagged CI intentionally fails if required secrets are absent.
- Verify macOS signatures, notarization, stapling, and Gatekeeper assessment.
- Verify Windows Authenticode signatures, Linux package metadata, and checksums for every artifact.
- Install each artifact on a clean supported OS without development tools or system FFmpeg, then complete a short end-to-end render and inspect it with ffprobe.
- Publish release notes that list supported OS versions, known limitations, and FFmpeg source/build information.

## Withdraw a release

If a release must be withdrawn, remove the affected artifact, document the reason, and direct users to the most recent approved release.
