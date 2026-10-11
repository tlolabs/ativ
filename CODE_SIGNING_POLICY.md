# Code signing policy

Tagged direct-download packages may be published after each target passes native functional, integrity, dependency, identity, and provenance verification. Developer ID signing, notarization, and Windows Authenticode are optional until their credentials and services are configured. Release notes must identify unsigned or unnotarized packages and omitted targets. Failed or unverified artifacts are never published.

Authenticated update feeds remain separate. Keep the installed update verification keys, signed update metadata, Sparkle checks, Windows executable signature checks where the update contract requires them, and rollback/integrity protections. An unsigned direct-download package must not be placed on a signed update feed.

Signing and notarization workflows remain available for future configured releases. Keep private keys, certificates, and service credentials in protected secrets or secure local key stores, never in Git. Cryptographic commit and tag signing are optional; voluntary DCO sign-offs remain the convention.
