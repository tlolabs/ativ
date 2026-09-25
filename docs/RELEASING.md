# Packaging, updates and release operations

## Current state and next release gates

ATIV's existing pipeline builds and tests six native targets and publishes passing artifacts independently. It currently produces DMG/ZIP on macOS, installer/ZIP on Windows, and AppImage/`.deb` on Linux. The target standard is a lowercase ZIP for macOS and Windows and an AppImage for Linux. The current updater opens the Windows installer and supports the Linux `.deb`; those paths must be migrated and tested together before the extra formats can safely be removed.

Stable tags now have a CI signature verification gate. Before the next stable release, Thomas must configure the base64-encoded armored GPG public key as `ATIV_RELEASE_SIGNING_PUBLIC_KEY_B64` and its fingerprint as `ATIV_RELEASE_SIGNING_FINGERPRINT` repository variables, then sign an annotated tag with the matching private key. Existing unsigned tags remain historical records; do not move or rewrite them. `Cargo.toml` and package metadata must agree with the tag.

The pipeline still needs Azure Artifact Signing for Windows, GPG signatures for Linux AppImages, and a release path for beta/RC tags. Stable target jobs now request GitHub/Sigstore attestations for passing artifacts before upload, but this has not yet been exercised in a live tagged run. Until the signing gates exist and pass, do not describe those artifacts as production signed or the workflow as fully compliant with [the signing policy](../CODE_SIGNING_POLICY.md). A CycloneDX SBOM and `SHA256SUMS` are generated for releases; review the final package contents and notices for every target.

## Reference and adaptations

ENcap supplied the native subprocess boundary, Sparkle 2.9.6 bridge and Ed25519 release-signing pattern. Its reviewed implementation has no Windows/Linux update client, nightly convention, native installers or AppImage pipeline. ATIV adds these host-owned pieces and independent publication. ATIV owns runtime source builds and package qualification; see [the integration contract](core-runtime-migration.md). See [the review](native-distribution-plan.md).

## Repository configuration

Set these in the ATIV repository's GitHub Actions settings, never in source control:

| Name | Kind | Meaning |
| --- | --- | --- |
| `ATIV_UPDATE_PUBLIC_KEY` | Variable | Base64 32-byte Ed25519 public key embedded in apps |
| `ATIV_UPDATE_PRIVATE_KEY` | Secret | Matching base64 32-byte Ed25519 private seed; signs appcasts and JSON envelopes |
| `MACOS_CERTIFICATE_BASE64` | Secret | Exported Developer ID Application PKCS#12 |
| `MACOS_CERTIFICATE_PASSWORD` | Secret | PKCS#12 password |
| `MACOS_SIGNING_IDENTITY` | Secret | Developer ID Application identity |
| `MACOS_NOTARY_APPLE_ID` | Secret | Apple notarization account |
| `MACOS_NOTARY_PASSWORD` | Secret | App-specific notarization password |
| `MACOS_NOTARY_TEAM_ID` | Secret | Apple Developer team |
| `WINDOWS_CERTIFICATE_BASE64` | Secret, optional | Authenticode PFX |
| `WINDOWS_CERTIFICATE_PASSWORD` | Secret, optional | PFX password |

The initial ATIV update-signing secret and public variable were configured during this migration. `script/configure_update_keys.py` supports first-time setup and refuses to replace existing keys.

Keep a protected offline backup of the Ed25519 seed. A missing update key fails authenticated feed generation. Never replace a deployed verification key without an explicit rotation/migration plan. The same key may sign separate channel payloads; clients enforce the signed channel. Public keys are not secrets.

Windows unsigned development builds work without a certificate; supplying the certificate enables executable and installer signing with timestamp verification. macOS stable tags require Developer ID/notary credentials. The macOS app is notarized and stapled before final archives are created, and the DMG is separately notarized/stapled. Sparkle nested code is signed inside-out. The ZIP contains the stapled app; the DMG contains the app and Applications shortcut.

## Configure macOS signing from a local certificate

Use a **Developer ID Application** identity exported as a password-protected `.p12`, including its private key. Apple Development, Apple Distribution and Developer ID Installer certificates do not replace this identity for ATIV's DMG/ZIP distribution. ENcap's current ad-hoc signature and update-signing key are separate from Apple Developer ID signing.

If needed, create the identity through [Apple's Developer ID certificate process](https://developer.apple.com/help/account/certificates/create-developer-id-certificates), then export the identity and private key from Keychain Access. Create a dedicated app-specific password for notarization in your Apple account.

Run this command in your own interactive macOS terminal, replacing the example path:

```sh
python3 script/configure_macos_signing.py /absolute/path/DeveloperID.p12
```

The helper prompts privately for the export password and Apple app-specific password, checks the identity in a temporary keychain, derives its Team ID, and validates authentication with Apple's notarization service before sending the six secrets directly to `tlolabs/ativ`. It restores the original keychain search list and deletes its temporary keychain. It never writes passwords into repository files or logs. GitHub secret writes are sequential; an interrupted upload can be completed by rerunning with `--replace`. That option also permits an intentional credential replacement.

After setup, validate both macOS architectures without publishing:

```sh
gh workflow run native-release.yml --ref main -f platform=macos -f sign_macos=true
```

Once validation passes, failed macOS jobs for an existing release can be rerun using the newly configured secrets. Do not move an existing release tag to another commit.

## Stable release

Update the workspace version, validate the branch, merge it, and push the matching `v<version>` tag. No manual approval job is required. The workflow tests Rust/shared media contracts, native integration and startup, builds the checksum/signature-pinned official FFmpeg source runtime, packages every supported target, validates architectures/resources/metadata, signs where configured and uploads only passing job artifacts.

Publication uses `always()` after all target jobs. Passing artifacts publish even when another target failed. Release notes explicitly identify incomplete jobs; the final reporting step fails so normal GitHub notifications remain effective. Empty or mixed-version artifact collections fail publication. Update feeds contain only artifacts actually present. An absent target cannot be offered for installation.

`release_metadata.py` signs the exact payload bytes in a base64 envelope, avoiding cross-language canonical-JSON ambiguity. The payload binds version, channel, target, filename, length, SHA-256 and repository download URL. macOS appcasts sign the complete DMG with Ed25519. Download clients require HTTPS, a valid signature, matching channel, newer semantic version, correct target and verified size/hash before handing off installation. A failed download is discarded. AppImage replacement is staged on the same filesystem and atomically renamed.

GitHub-generated notes are the stable changelog convention, matching ENcap. The attached `SHA256SUMS` covers downloadable artifacts and metadata.

## Development builds

Main branch pushes create `<base>-dev.<GitHub run number>` and update the `development` prerelease. macOS bundle IDs, Windows install IDs/directories, and Linux package IDs differ from stable. Feeds are `/releases/download/development/…`; stable uses `/releases/latest/download/…`. There is no runtime channel selector. Development artifact filenames include the run version, preventing cached bytes from being mistaken for newer downloads. Stale assets/feeds are removed from the rolling prerelease before the new validated set is uploaded.

`workflow_dispatch` is build-only, suitable for testing feature branches without creating releases. Its `platform` input can select macOS, Windows or Linux for focused verification; pushes, pull requests and tags always build all targets. Its optional `sign_macos` input tests Developer ID signing/notarization once credentials are configured, without creating a release tag. Matrix jobs use `fail-fast: false`.

## Package formats and limits

macOS: DMG and ZIP. Windows: per-user Inno Setup installer and portable ZIP. Linux: AppImage and `.deb`. ENcap has no proven RPM implementation to adapt, so RPM is not introduced in this pass. Linux ARM64 is retained from ATIV in addition to ENcap's x64 baseline.

Linux `.deb` installation remains owned by the distribution package manager. AppImage self-updates require a writable installation directory and apply after user confirmation; an existing running mapping remains valid until restart. A signed update is not a substitute for testing a real upgrade on every platform.

Use [the release checklist](release-checklist.md) and [acceptance matrix](acceptance-matrix.md) before declaring a release production-ready.
