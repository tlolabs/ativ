# Repository development and CI/CD policy

ATIV uses a nonblocking development and CI/CD model. Direct commits and pushes to `main` are allowed. No mandatory pull request, review, approval, DCO check, signed commit, branch protection, ruleset, or required status check may be introduced. Voluntary `git commit -s` DCO trailers remain the convention.

Preserve unit, integration, functional, regression, accessibility, security, dependency, and platform checks for deliberate local use. Scheduled CI follows the owner-directed smoke policy below. A diagnostic failure must not stop unrelated development or another verified platform.

Each release artifact must pass its own native build, package integrity, target identity, runtime dependency, launch, and functional checks before publication. Successful targets may publish independently. Never publish a failed or unverified artifact. Code signing and notarization are optional for direct downloads until configured. Signed update feeds retain their existing cryptographic signature and upgrade verification requirements; unsigned downloads must never be added to an authenticated update feed. Do not weaken runtime acquisition or update-signature checks.

Do not automatically retry the same release tag in scheduled CI. Preserve tests and future signing workflows. Do not reintroduce blocking gates without explicit owner authorization.

## Owner-directed weekly smoke CI

Automatic CI runs once weekly on Sunday mornings Pacific time (16:17 UTC, 08:17 PST / 09:17 PDT), and native work runs only for a new stable `vMAJOR.MINOR.PATCH` source-release tag that has not already been attempted. Run only native Linux and Windows x86_64/arm64 compilation and basic smoke tests. Do not run macOS CI, push/PR/tag-triggered CI, automatic retries, full diagnostic suites, or release/publication jobs on the scheduled path. Retain broader test and signing tools for deliberate local use. CI remains diagnostic and nonblocking; do not add required checks or approval gates.

The scheduled smoke result is not release qualification. Preserve runtime acquisition, source and package integrity, target identity, and signature/update verification. Do not publish smoke artifacts as verified releases or change authenticated runtime/update contracts.

## Archived legacy automation

The former custom workflows are preserved, inactive, under `.github/workflow-archive/2026-11-08/`, with original paths and hashes recorded in its manifest. This archive supersedes older descriptions of automatic builds, retries, reporting, and release publishing. Do not move them back to `.github/workflows/`, enable, or dispatch them without a new explicit owner instruction. GitHub-managed security services remain separate and enabled.
