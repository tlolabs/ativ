# Releasing ATIV

Create an annotated `vMAJOR.MINOR.PATCH` tag matching the version in `Cargo.toml` and push it. The native workflow builds, tests, packages, and smoke-tests the six supported targets. A successful target uploads its package at the end of its job. The release job checks the tagged source, package identity and integrity, provenance attestation, and downloaded bytes, then publishes verified targets independently. Failed or unverified targets are omitted and remain visible in GitHub Actions and the consolidated CI/CD issue. Do not move tags or replace published assets.

Direct-download ZIPs and AppImages may be unsigned or unnotarized. Record their actual signing state and platform limitations in release notes. Apple Developer ID, notarization, and Windows Authenticode workflows remain optional until configured. An unsigned package is never enrolled in the authenticated updater feed.

The runtime is acquired from AVID Core through the pinned, authenticated source. Preserve package validation, exact runtime identity, updater signature checks, installed verification keys, and rollback behavior. Signing or update-feed publication requires the applicable target verification; a passing build alone does not authorize a signed update.

The prior all-target qualification procedure is retained as [historical evidence](historical/release-integration-before-nonblocking.md).
