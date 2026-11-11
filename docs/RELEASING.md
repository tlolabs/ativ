# Releasing ATIV

To publish a stable source release, create and push an annotated `vMAJOR.MINOR.PATCH` tag matching `Cargo.toml` and the exact tested commit. A source release identifies code; it does not qualify native packages. Direct commits and pushes to `main` are allowed without mandatory review or status checks. Do not move published tags or replace published assets.

Automatic CI runs once weekly on Sunday at 16:17 UTC (08:17 PST / 09:17 PDT). It attempts only a new stable source-release tag, once, and runs native Linux/Windows x86_64/arm64 compilation and basic smoke tests. There are no automatic push, PR or tag builds, macOS CI, release publication jobs or retries. Scheduled smoke artifacts are not verified releases. Legacy workflows remain inactive under `.github/workflow-archive/2026-11-08/`; do not enable or dispatch them without a new explicit owner instruction. [AGENTS.md](../AGENTS.md) is authoritative.

Build and qualify native artifacts deliberately on their respective hosts. Each artifact must pass its native build, package integrity, target identity, runtime dependency, launch and functional checks before publication. Successful targets may publish independently; leave failed or unverified targets absent and record their limitations. Preserve applicable source-job, artifact-digest, provenance, package-byte and public-download verification in retained publication tools. Record the exact source revision and package checksum with each target's evidence. Existing verification from another revision or another target does not qualify new bytes.

Standard macOS app ZIPs require Developer ID signing, accepted notarization, and validated stapled tickets. Explicit development packages are unnotarized and not distributable. Windows/Linux packages retain their existing optional signing policy. Record actual signing state and platform limitations in release notes. An unsigned package is never enrolled in the authenticated updater feed.

The runtime is acquired from AVID Core through the authenticated platform releases pinned in `runtime/platform-runtimes.json`. The Rust Core source pin is independent of those runtime identities. Preserve package validation, exact runtime identity, updater signature checks, installed verification keys, and rollback behavior. Signing or update-feed publication requires the applicable target verification; a passing build alone does not authorize a signed update.

The prior all-target qualification procedure is retained as [historical evidence](historical/release-integration-before-nonblocking.md).
