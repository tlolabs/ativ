# Release operations

The next application version is 0.2.6. The locally signed/notarized 0.2.5 bridge includes the corrected Sparkle manual action; the published 0.2.4 implementation sends that action to the wrong receiver. Existing tags and assets remain historical and must never be moved or overwritten. AVID Core owns the matched FFmpeg/FFprobe runtime; ATIV owns its native application, packaging, signing and update behavior.

Distribution formats are signed/notarized macOS ZIP, Azure Authenticode Windows portable ZIP, and GPG-signed Linux AppImage. The full native build matrix remains macOS, Windows and Linux on arm64/x86_64. ATIV may publish passing targets independently only when every applicable requirement for that target passes. A passing build alone cannot authorize publication.

## Qualification and publication

1. Validate Rust, release infrastructure and runtime ownership checks.
2. Dispatch `native-release.yml` on the exact reviewed branch with `qualify_core_candidate=true` for unpublished host packages. Record native package, startup, media and subprocess evidence for the exact Core pair.
3. Import authenticated host evidence into Core; satisfy its approved prerequisites and publish its exact six-target runtime.
4. Pin Core's real published release revision and authenticated manifest digest, remove `qualification_only`, then demonstrate clean production acquisition of the same runtime bytes.
5. Verify final application signing, actual previous-version authenticated upgrades and manual UI/accessibility acceptance against final package hashes. Preserve settings, media and deployed update verification keys.
6. Integrate through normal repository review/protection requirements. Create a new signed annotated tag matching the workspace version only after the executable application gates pass. Stage a new draft, verify its actual downloads and feeds, then publish. Never replace assets or move tags.

The existing rolling development publisher is retired in this integration because it moved tags and replaced assets. Candidate workflow uploads are qualification evidence and cannot be treated as production releases. See [integration status](release-integration.md) and the [acceptance matrix](acceptance-matrix.md). The earlier release operations document is preserved as [historical evidence](historical/releasing-before-core-integration.md).

## Trust configuration

Stable tag verification uses public variables `ATIV_RELEASE_SIGNING_PUBLIC_KEY_B64` and `ATIV_RELEASE_SIGNING_FINGERPRINT`, configured for verified maintainer fingerprint `F7E74ED98DB485D03F2565B96B68B73FE752FD16`. Commit cryptographic signing is recommended; release tags must satisfy the existing verification policy.

Update signing uses existing `ATIV_UPDATE_PRIVATE_KEY` (secret) and `ATIV_UPDATE_PUBLIC_KEY` (variable). Preserve the installed Ed25519 verification key; never rotate or regenerate it as a setup shortcut. Feeds must advertise only qualified, published packages in the actual ZIP/AppImage formats.

Apple Developer ID signing is available locally for Team ID `VR64M92P2M`. The existing notarization profile is `EnCAP`; it worked for earlier candidates, but the latest qualification attempt cannot find it in the login keychain. Restore or unlock that existing profile before resuming notarization. Local signing requires no CI key export. CI signing additionally needs secrets `MACOS_CERTIFICATE_BASE64`, `MACOS_CERTIFICATE_PASSWORD`, `MACOS_SIGNING_IDENTITY`, `MACOS_NOTARY_APPLE_ID`, `MACOS_NOTARY_PASSWORD`, `MACOS_NOTARY_TEAM_ID`. A new export/upload requires separate authorization. Sign nested executables/frameworks inside-out, require accepted notarization, staple, re-ZIP and verify the extracted final package.

For local Mac signing, authenticate the exact native run with `script/acquire_app_artifact.py`, sign its original bundles with `script/sign_macos_release.sh`, and upload the immutable ZIPs to an unpublished `qualification-VERSION-SOURCEPREFIX` draft. Dispatch `verify-macos.yml` with the native run, draft tag, immutable `qualification_release_id`, and both final ZIP hashes. The workflow fetches drafts by release ID (GitHub’s release-by-tag endpoint serves published releases), checks the exact tag/source binding, compares executable code and resources, and runs native signature, launch and media checks. This draft is not a stable release and does not satisfy updater-installation or manual-acceptance gates.

Azure provisioning is outstanding: no Artifact Signing account currently exists. Configure secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` and variables `AZURE_SIGNING_ENDPOINT`, `AZURE_SIGNING_ACCOUNT`, `AZURE_CERTIFICATE_PROFILE`, `AZURE_SIGNING_SUBJECT`, using repository-scoped OIDC and the Certificate Profile Signer role. Dispatch `sign-windows.yml` with the exact successful native run. All packaged executable signatures and timestamps must verify on both native architectures.

Linux key transfer to ATIV and EnCAP Actions stores is approved. Run `python3 script/configure_linux_signing.py` in a secure interactive terminal. It configures secrets `LINUX_GPG_PRIVATE_KEY_B64`, `LINUX_GPG_PASSPHRASE` and public variables `LINUX_GPG_PUBLIC_KEY_B64`, `LINUX_GPG_FINGERPRINT`, without logging/writing private material. Final AppImages require both the pinned maintainer GPG signature and GitHub/Sigstore attestation.

The Windows portable update helper stages the authenticated ZIP on the same filesystem, rejects unsafe entries and wrong targets, verifies executable signatures/timestamps and the intended Core runtime, waits for the application to exit, preserves user additions, retains the complete previous directory and rolls back a failed startup. The 0.2.6 native Windows x64 and ARM64 builds, tests and packaging pass in qualification run 36876018252. The real older-to-newer signed upgrade remains awaiting evidence; opening a ZIP or verifying metadata is not an installation test. Linux AppImage replacement must preserve the previous installation on failure; settings and user media remain outside replacement. macOS Sparkle installation/restart needs actual acceptance. Manual results stay awaiting acceptance until supplied by a reviewer for exact packages.

## Shared automatic updates

See [automatic updates](automatic-updates.md) for the signed schema-2 contract, compatibility feeds, native upgrade gates and migration blockers. No platform has been end-to-end updater qualified by compilation or common contract tests.
