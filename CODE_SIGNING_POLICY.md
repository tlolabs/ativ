# Code signing policy

An official stable ATIV release is a GitHub Release built from a verified annotated `vMAJOR.MINOR.PATCH` Git tag approved by Thomas Lothian. He is the sole maintainer and final release approver. CI may build and verify artifacts but must not turn a development build into an official release.

Stable macOS applications use Apple Developer ID signing and notarization. The completed, stapled app is verified and distributed in a ZIP. Stable Windows executables use Azure Artifact Signing and Authenticode verification, then a portable ZIP. Stable Linux AppImages require GitHub/Sigstore artifact attestations and exact package identity checks. Stable downloadable artifacts receive SHA-256 checksums, an SBOM and provenance attestations where supported. These are the intended requirements; the current workflow must be brought into agreement before a new stable release is authorized.

Prerelease and development builds are not production signed and must be clearly labeled. Development packages are unsupported. Only passing platform artifacts may be published; release notes identify incomplete targets.

Private keys, signing certificates, service credentials and approval tokens belong in protected CI secrets or secure local key stores, never in Git. The maintainer verifies the tag and release source, approves publication, and checks applicable platform signatures and release metadata. Provider-required approval still applies.

ATIV does not currently use SignPath. If that changes, this policy and the release workflow must be updated to meet its terms before displaying SignPath attribution.
