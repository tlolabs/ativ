# TLO Labs automatic updates

Status: implementation and migration in progress; **no application/platform is end-to-end qualified**. Passing the common tests, compiling native code, or authenticating a release is not installation qualification. `runtime/updater-qualification.json` intentionally records `not_run` for every architecture.

## Architecture decision

Use the independent `tlo-updater` Rust crate in `updater/`, thin application-specific CLI entry points, the existing macOS Sparkle integration, and native installation adapters. The shared crate depends on neither ATIV nor AVID Core. It owns stable release discovery, SemVer, identity/platform/architecture/OS selection, bounded downloads, Ed25519 and SHA-256 verification, persisted check policy and rollback-version state. Native UIs own user consent, unsaved work and application shutdown. Application packages own their public verification keys and platform signing policy.

The component is currently vendored source, suitable for extraction into a standalone TLO Labs repository without any media dependency. ATIV is the initial source location, not a runtime dependency for other applications. `updater/SNAPSHOT.json` records the reviewed shared Rust and release-tooling bytes. Consumers copy an entire reviewed snapshot; CI checks for changes. Before finishing the EnCAP migration, compare both copies using `python3 script/check_updater_snapshot.py --compare ../EnCAP`. Do not maintain application-specific forks. A future standalone Git remote should replace vendoring with immutable revisions after publication; no fictitious or unpublished Git dependency is used here.

Retain [Sparkle](https://sparkle-project.org/documentation/) rather than reimplement its installer, signing validation or native UI. It already handles signed ZIPs and macOS application installation. The release pipeline retains Developer ID, hardened runtime, accepted notarization, stapling and post-extraction verification. Sparkle 2.9.6 remains hash-pinned. Archives are Ed25519 signed with the existing application key. Appcasts use the existing per-architecture URLs. Sparkle handles appcast version comparison and native code-signing identity; Windows/Linux consume the signed JSON contract. This is an intentional platform difference.

[WinSparkle](https://winsparkle.org/guides/integrating-winsparkle/) provides update UI and signed-download support, but does not make ATIV's current portable directory replacement transactional. An installer migration or persistent recovery bootstrapper is required before claiming power-loss-safe Windows installation. Keep the existing portable adapter as an unqualified candidate, strengthen its authentication, and require native interruption evidence before publishing. Do not add another update discovery system merely to launch the same unsafe ZIP replacement.

[AppImageUpdate](https://github.com/AppImageCommunity/AppImageUpdate) supports embedded update information and delta transport. Existing images do not have the required update information/zsync channel; the installed trust chain uses the signed update manifest and release provenance attestations. For this bridge, retain and harden the existing full-download atomic AppImage adapter behind the shared API. Authentication always precedes replacement. Delta transport may be adopted later under the same signed manifest; a zsync checksum is not authentication.

## Repository audit and scope

| Repository | Audited baseline | Migration in this work |
| --- | --- | --- |
| ATIV | Sparkle 2.9.6; separate `ativ-update` Rust CLI with schema-1 Ed25519 feed; Windows portable helper; GTK update UI; development feed path; no persistent check throttle | CLI delegates to shared crate; stable-only signed schema-2 feed; legacy schema-1 output retained; native coordination and package identity checks strengthened; CI release gates and public probe added |
| EnCAP | Sparkle 2.9.6; Rust `encap-release` generator with a different schema-1 object envelope; Windows ZIP, Linux tar.gz; no native Windows/Linux updater at audit start; tagged publisher used `--clobber` | Initial shared snapshot and `encap-update` adapter added. Another process is actively changing its native adapters, packaging and workflows. Those concurrent changes were not overwritten or claimed qualified here. Reconcile the shared snapshot and release-tooling interface before merging |
| AVID Core | Shared media/runtime crate, not a desktop app; runtime release manifests and attestations | No application updater added. Existing unrelated working changes preserved |

Read-only GitHub inspection confirmed the latest published stable starting points: ATIV `v0.2.4` (schema-1 `latest.json`, appcasts, ZIP/DMG, Windows installer/ZIP, AppImage/deb) and EnCAP `v2.0.3` (object-envelope `latest.json`, macOS appcasts/DMGs, Windows ZIP, Linux tar.gz). Neither release contains `update-manifest.json`. No release was created or modified; the new public feed therefore cannot yet pass production qualification.

The audit covers the three supplied workspace roots. It does not establish the status of other TLO Labs repositories.

ATIV's deployment key names are `ATIV_UPDATE_PRIVATE_KEY` (secret) and `ATIV_UPDATE_PUBLIC_KEY` (public variable). EnCAP's existing names are `ENCAP_UPDATE_PRIVATE_KEY` and `ENCAP_UPDATE_PUBLIC_KEY`; local EnCAP key files also exist. The existing ATIV seed was used locally by signing tools to authenticate qualification fixtures; no private key contents were displayed, exported, regenerated or changed. The updater preserves those identities. Existing EnCAP legacy release generation is retained until migration is proven; it must not race the standardized publisher.

## Stable GitHub Release contract

The only discovery URL for the shared client is:

`https://github.com/<owner>/<repository>/releases/latest/download/update-manifest.json`

There are no HTML scrapers, CI artifact endpoints, branch/nightly fallbacks, API tokens or normal REST API discovery calls. GitHub's public latest-release asset route supplies the feed; authenticated metadata independently requires a stable release, canonical `vMAJOR.MINOR.PATCH` tag and matching application. Fail closed when the latest release omits metadata. A missing architecture is reported as no compatible update. Partial ATIV publication must account for this; do not publish a newest release that unintentionally strands another architecture.

An envelope contains `payload` and `signature`, both standard base64. The signature is Ed25519 over the **exact decoded payload bytes**, not reparsed or reserialized JSON. The verifying key is installed with the application, never accepted from the network. Payload schema is [manifest.schema.json](../updater/manifest.schema.json). The Rust verifier enforces additional relationships beyond JSON Schema:

| Field | Contract |
| --- | --- |
| `schema` | `2` |
| `application_id`, `repository` | Exact installed application ID and owner/repository |
| `version`, `tag` | Strict numeric SemVer; tag equals `v` plus version; no prerelease/build suffix |
| `channel`, `draft`, `prerelease` | `stable`, `false`, `false` |
| `published_at` | Release metadata timestamp from immutable release/tag commit time in the generator; actual GitHub publication time may be later |
| `release_notes_url` | Exact GitHub release tag URL |
| `restart_required`, `migration` | `true`, and `none` or `manual`; manual migration prevents automatic download/install commands |
| `assets` | Map keyed by supported target; no guessing filenames |
| Each asset | Exact platform, architecture, format, minimum OS, Linux glibc floor, filename, canonical tag-bound URL, positive bounded byte size, lower-case SHA-256 |

Supported keys: `macos-arm64`, `macos-intel`, `windows-x64`, `windows-arm64`, `linux-x64-appimage`, `linux-arm64-appimage`. Architecture spellings in the payload are `x86_64` or `aarch64`. Current Linux payloads require glibc 2.39 or newer; this is a conservative Ubuntu 24.04 build floor, not a claim of older-distro qualification. Raise/lower a floor only with native evidence. Windows uses `RtlGetVersion`, Linux checks kernel/glibc, and Sparkle enforces the macOS floor.

Every asset URL must equal `https://github.com/<repository>/releases/download/v<version>/<filename>`. Redirects are HTTPS-only and limited to GitHub's release asset hosts. Metadata is bounded to 1 MiB; artifacts to 2 GiB and their signed exact size. Filenames cannot contain path separators, queries or traversal. Artifacts are written to unique staging files. Truncation, corruption, over-size responses and any signature failure abort without execution.

## Trust chain and policy

1. Install an independently authenticated initial application (native signed/notarized package or release-attested AppImage).
2. Its binary pins its application/repository/version; its authenticated package supplies the existing Ed25519 public key and target.
3. Authenticate the manifest before trusting any artifact URL, checksum, version or target.
4. Compare numeric semantic versions with both the installed version and the highest previously authenticated version. Equal/older versions are not updates. A replay below the high-water mark fails.
5. Download and verify the signed size and SHA-256. SHA-256 alone never authorizes installation.
6. Apply native verification/installation. Windows rechecks the same open archive stream, package application/version/target/key and timestamped Authenticode signer identity before running a new executable. Linux's signed manifest authenticates exact bytes; GitHub attestations remain a publication gate. Sparkle uses archive Ed25519 plus the macOS signing chain.

An attacker with the release signing key can sign malicious releases; keys and protected release authority remain trusted. Persisted high-water state defends ordinary replay after observation, not a malicious local user deleting state, a first-install freeze attack, or a compromised operating system. There is no online freshness authority. HTTPS outages and metadata failures leave the app usable. GitHub necessarily sees ordinary request network metadata; the client sends no installation ID, hardware profile, media paths, analytics or telemetry.

Windows/Linux automatic checks run at startup when due and periodically through native UI timers. State records last attempt, last successful authenticated check and highest authenticated version under the application-specific state directory. Checks occur at most daily by default; failures back off one hour. Manual checks bypass scheduling but never verification. OS file locks serialize helpers and release on crashes. Temporary state writes are flushed and atomically replaced. Clock rollback causes a fresh check. Automatic checking can be disabled in native preferences. macOS uses Sparkle's own persisted scheduling at a daily interval with automatic installation disabled and profiling off.

ATIV's Sparkle delegate defers checks and an already requested restart while exporting. Application termination also waits for export completion when Sparkle bypasses that callback; users can explicitly stop the export. Windows checks work state again after download, saves settings and coordinates closing. Linux prevents starting a render while an update is running, retains a prior image, flushes staged bytes and atomically replaces the image on the same filesystem. Failure before replacement leaves the old path intact. The new process is not automatically started; users restart after saving work. The UI offers a separate verified download/manual-install option for non-writable locations. Backups are not silently removed.

**Windows limitation:** the current adapter performs two directory renames. A power loss between them can leave the original path absent even though the complete backup survives. Runtime startup checking does not solve this. Do not qualify or publish Windows automatic updates until a persistent bootstrapper/installer and recovery tests resolve this gap. The new release ledger explicitly requires `interrupted_installation` evidence; compilation cannot satisfy it.

## Versions and release procedure

`Cargo.toml` workspace package version is authoritative per application. ATIV's helper uses Cargo's compiled package version. Distribution configuration refuses a different environment override. Windows project versions derive from Cargo; macOS plist is a build template whose two version fields are set during packaging; Meson reads Cargo. Stable tags must match exactly. Release generation reads embedded package identity (ZIP metadata, macOS Info.plist, or AppImage SquashFS data without executing it), rejecting application, version, target or key disagreement.

Keep the existing native build, platform signing, notarization and attestation workflows and the applicable final-package gates. In addition:

1. Run shared Rust tests and release tooling tests; verify the source snapshot and dependency inventory.
2. Package native production artifacts and authenticate them under the existing platform policy.
3. Obtain exact-artifact older-to-newer native qualification evidence. Record every target, including unperformed targets.
4. Generate `update-manifest.json`, compatibility `latest.json`, Sparkle appcasts and `SHA256SUMS` with the deployed update key. `script/release_metadata.py` is ATIV's compatibility entry point; shared implementation is `script/tlo_update_release.py`.
5. Independently verify metadata against actual packaged artifacts; run `script/qualify_updates.py --assets <directory>`. Existing application qualification gates still apply.
6. Create a new draft for the verified annotated tag. Upload immutable artifacts and metadata, download them again, verify hashes/applicable signatures/attestations and appcast agreement.
7. Publish without replacing existing assets or tags. Run `script/qualify_updates.py --assets <verified-downloads> --published`, which invokes the same Rust verification code against the public latest URL and actual downloaded artifact for each trusted old configuration. Failure fails CI qualification; do not silently rewrite published bytes.

Python and `cryptography` are release-only tools. Apps do not acquire a Python runtime. `unsquashfs` is needed in Linux release verification, never to execute a downloaded application.

## Qualification and migration

`updater/tests/contract.rs` covers SemVer ordering, no target/no update, old/equal/malformed versions, draft/prerelease/development rejection, wrong identities/targets, tampering/signature failures, truncation/overflow/checksum failures, minimum OS, replay, outages, interrupted streams, a local mock release endpoint and AppImage staging/backup behavior. Fixture keys are test-only. Local HTTP injection is confined to tests; no production endpoint/trust bypass exists.

`script/test_tlo_update_release.py` checks deterministic generation, packaged identities, artifact/metadata agreement, signatures and both legacy wire formats. These tests do not install an application. `tlo-qualify` reports `installation: not_tested` even when public authentication/download succeeds.

For each native architecture, use an isolated installation of an authenticated older build with representative settings, media, user additions and unsaved work. Discover/authenticate/download/install the newer exact final package; check restart, native signatures, settings/user-file preservation and active-work coordination. Repeat with wrong application/target/signature, modified bytes and interrupted download/install. Include process termination and machine-restart/power-loss simulations where applicable. macOS additionally needs actual Sparkle install/relaunch acceptance; Linux tests writable and non-writable image locations; Windows tests locked files and interruption recovery.

For legacy configs without `application_id` or `repository`, the native qualification harness must add those constants only after verifying the old signed package identity; never take them from unverified network metadata.

Store reports under `docs/updates/`, with exact previous and new package hashes, versions, target, previous packaged `update-config.json`, host, tested timestamp, reviewer and case results. `script/qualify_updates.py` defines the required fields. Hash the report into `runtime/updater-qualification.json`. Never mark a check passed merely to open publication gates.

ATIV's existing schema-1 `latest.json` and per-architecture Sparkle feeds remain signed with the installed key for a bridge release. New clients exclusively read schema 2 under a different filename. EnCAP's object-payload signature serialization is retained for legacy ZIP readers. Existing EnCAP Linux tar distributions need an explicit manual bridge to AppImage; do not advertise an AppImage as a tar archive. Existing development installations are not production update sources and must move to an authenticated stable package manually. Retain old feed support until installed-version qualification proves migration; do not delete EnCAP's legacy generator while another process is integrating it.

## Signing key ownership and recovery

Thomas Lothian retains application release/signing authority. Private update seeds remain in approved secret stores; public keys are embedded in authenticated packages and public CI variables. Platform signing credentials remain separate from Ed25519 update keys. This change does not provision a paid service or export keys.

Do not replace a key as a setup shortcut. Planned rotation requires a bridge that the old installed key can authenticate, distribution of the new trust root in that authenticated application, and actual oldest-supported-to-bridge-to-new-key tests. The current Windows adapter deliberately rejects a public-key change; implement and qualify explicit bridge support before rotation. Do not overwrite the old secret until supported installed versions can migrate. Keep offline protected recovery copies under the maintainer's custody.

If the old update-signing key is unavailable, use an independently authenticated manual reinstall. If it is compromised, stop release publication, revoke/recover platform and repository credentials as appropriate, and establish a new trusted initial installation. A manifest signed only by a compromised key is not a recovery authority.

## Adoption and troubleshooting

A new application vendors the reviewed standalone snapshot, adds a tiny CLI adapter with constant application/repository identity and `env!("CARGO_PKG_VERSION")`, and writes `update-config.json` from its authoritative version at packaging time. Native UI invokes `check-auto`, `check`, `download`, or (Linux AppImage only) `install-appimage` off the UI thread. Native adapters must coordinate unsaved work and retain platform signature verification. Adopt the shared release tooling, existing-key migration contract and qualification gates; qualify every supported platform before publication.

If an update is unavailable: check stable tag/latest release metadata presence, installed key/identity, target and minimum OS, then the application-specific state file. Errors should remain local. A failed signature must never be bypassed. Clock changes cause a retry; outage retries are throttled. If a write fails, use the native manual-download action and a writable destination after closing the application. Restore an AppImage from the reported `tlo-previous-*.AppImage` backup after closing it. Windows recovery currently needs the retained `.ativ-backup-*` directory when interrupted; this is an outstanding production blocker, not automatic recovery.

Current qualification evidence: [2026-10-01 report](updates/qualification-20261001.md). The implementation-validation report describes the earlier implementation run and is historical.
