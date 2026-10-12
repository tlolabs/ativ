# Releasing ATIV

Every push to `main` builds, tests, packages and smoke-tests the six supported native targets. The dedicated publisher creates an immutable `development-<version>-dev.<run number>` prerelease and adds each target after its own successful native verification. No manual tag, signing credential or other platform is required for a development direct download. To publish a stable version, create and push an annotated `vMAJOR.MINOR.PATCH` tag matching `Cargo.toml`; stable packages also require their provenance attestations. The publisher verifies each source job, artifact digest, package identity, host evidence, release asset digest and public download. Failed or unverified targets are omitted and remain visible in GitHub Actions and the consolidated CI/CD issue. Do not move tags or replace published assets. Unsigned direct downloads never enter the signed automatic-update feed.

Direct-download ZIPs and AppImages may be unsigned or unnotarized. Record their actual signing state and platform limitations in release notes. Apple Developer ID, notarization, and Windows Authenticode workflows remain optional until configured. An unsigned package is never enrolled in the authenticated updater feed.

The runtime is acquired from AVID Core through the pinned, authenticated source. Preserve package validation, exact runtime identity, updater signature checks, installed verification keys, and rollback behavior. Signing or update-feed publication requires the applicable target verification; a passing build alone does not authorize a signed update.

The prior all-target qualification procedure is retained as [historical evidence](historical/release-integration-before-nonblocking.md).
