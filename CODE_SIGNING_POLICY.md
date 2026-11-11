# Code signing policy

Tagged direct-download packages may be published after each target passes native functional, integrity, dependency, identity, and provenance verification. macOS app packages require Developer ID signing, notarization acceptance and a validated stapled ticket. Windows Authenticode remains optional until configured. Release notes must identify unsigned or unnotarized packages and omitted targets. Failed or unverified artifacts are never published.

Authenticated update feeds remain separate. Keep the installed update verification keys, signed update metadata, Sparkle checks, Windows executable signature checks where the update contract requires them, and rollback/integrity protections. An unsigned direct-download package must not be placed on a signed update feed.

Signing and notarization workflows remain available for future configured releases. Keep private keys, certificates, and service credentials in protected secrets or secure local key stores, never in Git. Cryptographic commit and tag signing are optional; voluntary DCO sign-offs remain the convention.

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
