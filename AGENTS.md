# Repository development and CI/CD policy

ATIV uses a nonblocking development and CI/CD model. Direct commits and pushes to `main` are allowed. No mandatory pull request, review, approval, DCO check, signed commit, branch protection, ruleset, or required status check may be introduced. Voluntary `git commit -s` DCO trailers remain the convention.

Preserve unit, integration, functional, regression, accessibility, security, dependency, and platform checks for deliberate local use. Scheduled CI follows the owner-directed smoke policy below. A diagnostic failure must not stop unrelated development or another verified platform.

Each release artifact must pass its own native build, package integrity, target identity, runtime dependency, launch, and functional checks before publication. Successful targets may publish independently. Never publish a failed or unverified artifact. Standard local macOS app distributions require Developer ID signing and notarization; explicit development packages remain unnotarized. Signed update feeds retain their existing cryptographic signature and upgrade verification requirements; unsigned downloads must never be added to an authenticated update feed. Do not weaken runtime acquisition or update-signature checks.

Do not automatically retry the same release tag in scheduled CI. Preserve tests and future signing workflows. Do not reintroduce blocking gates without explicit owner authorization.

## Owner-directed weekly smoke CI

Automatic CI runs once weekly on Sunday mornings Pacific time (16:17 UTC, 08:17 PST / 09:17 PDT), and native work runs only for a new stable `vMAJOR.MINOR.PATCH` source-release tag that has not already been attempted. Run only native Linux and Windows x86_64/arm64 compilation and basic smoke tests. Do not run macOS CI, push/PR/tag-triggered CI, automatic retries, full diagnostic suites, or unrelated diagnostic jobs on the scheduled path. Retain broader test and signing tools for deliberate local use. CI remains diagnostic and nonblocking; do not add required checks or approval gates.

Owner clarification (2026-11-12): the weekly native Windows/Linux jobs package
and publish successful platform direct downloads to the matching existing
stable release. A raw build or smoke result alone is insufficient: preserve
runtime acquisition, final-package integrity, target identity, dependencies,
native launch and signature verification. Publish each qualified platform
independently; fail closed on missing signing configuration. Do not overwrite
assets, move tags, alter Latest or authenticated updater feeds, or automatically
retry attempted tags. No macOS hosted build or event-driven CI is added.
Before claiming any target, require an existing published stable release with an
exact-version `ATIV-VERSION-macos-arm64.zip` or `-macos-intel.zip` asset in uploaded
state, nonzero size and a GitHub SHA-256 digest. No per-release manual enrollment
is needed. Raw tags, drafts/prereleases, missing Mac assets, invalid/missing update
public key, and Windows without all existing Azure signing prerequisites are
reported as ineligible without status writes. An existing native asset or sidecar
also skips that target without rebuilding or overwriting it.
A nonempty repository variable `ATIV_WEEKLY_RELEASE_HOLD` pauses publication
when captured by a job; clear it to resume eligibility. This captured configuration
is not a reliable in-flight stop. A release-note marker `<!-- ativ-release-hold -->`
(case-insensitive) holds that release and is freshly fetched before each asset
operation. Remove the marker only when its hold is resolved. Selection rechecks
prerequisites before the first claim; publication rechecks the current release
and release-note hold, Mac asset and remote tag before each asset operation. API/enumeration errors fail closed, never masquerade as absent releases.
Ineligible work is not an attempt; previously attempted/failed targets stay
consumed and are never reset or automatically retried.

## Archived legacy automation

The former custom workflows are preserved, inactive, under `.github/workflow-archive/2026-11-08/`, with original paths and hashes recorded in its manifest. This archive supersedes older descriptions of automatic builds, retries, reporting, and release publishing. Do not move them back to `.github/workflows/`, enable, or dispatch them without a new explicit owner instruction. GitHub-managed security services remain separate and enabled.

## Local macOS notarization (owner update, 2026-11-09)

Standard local distributable macOS app packages require Developer ID Application
signing, Apple notarization acceptance, stapling, and signature/Gatekeeper checks
of the final extracted app. Missing credentials stop that packaging path before
building; they never silently select an unsigned download. Use an existing
Keychain notarytool profile and keep credentials out of source control.
Ordinary debug/test runs and explicitly named development/reference artifacts
remain local and unnotarized. This supersedes older optional-notarization wording
for macOS app distribution only. Windows/Linux policy, authenticated updates,
DCO conventions, and the restricted weekly CI schedule are unchanged.
