# ATIV 0.2.6 updater qualification — 2026-10-01

**Not qualified.** The requested transition from 0.2.5 through GitHub discovery, authenticated in-app download, installation, relaunch into 0.2.6 and post-update regression has **not run**. No stable `v0.2.6` tag or release was created. Publication gates remain closed.

## Exact source and artifacts

Build source: `c8023ffbba9b91de0c5cf3164f34109dbdbf5d52`. The source is preserved on `codex/ativ-0.2.6-native-source`; the working branch is `codex/ativ-core-runtime-build`. Subsequent documentation commits record evidence without changing build inputs.

[Native qualification run 36876018252](https://github.com/tlolabs/ativ/actions/runs/36876018252) passed the shared-engine job and all six targets: macOS arm64/x86_64, Windows arm64/x86_64 and Linux arm64/x86_64. The Mac inputs were independently downloaded and checked against GitHub artifact digests and exact source/job identity before local signing.

| Candidate | Package | SHA-256 |
| --- | --- | --- |
| A: fixed 0.2.5 bridge | `build/updater-qualification-20260930/bridge-a/ATIV-0.2.5-macos-arm64.zip` | `ce2cbe8688954c5a7bc0804364676b3acfc1d5e4ee57dacc507f5caa443b5dc2` |
| B: current 0.2.6 arm64, **not notarized** | `packages/ATIV-0.2.6-macos-arm64.zip` | `090171222c36d9936be8a176afe79198959ae7423700cd46328573ab601a44dc` |
| B: current 0.2.6 Intel, **not notarized** | `packages/ATIV-0.2.6-macos-intel.zip` | `76aa3a3cad99213cae7aeb86ba9c64a07d8856ecc824a0dd95656a71f649a58c` |

A was built through the production path from `4ba41fc738fc72ce821286ed18d91dc9fdfbe80a`. It passes Developer ID verification, notarization, stapling and Gatekeeper. Notarization ID: `576a981f-8437-4a86-87a7-b22b280836ee`. Its standalone launch passed; its updater installation has not been exercised. Published 0.2.4 was unsuitable because its manual update action targeted the wrong Sparkle object.

Both current B bundles match the original CI executable code and resources, use `com.tlolabs.ativ`, report 0.2.6, have the expected architecture, and pass strict nested Developer ID verification for Team `VR64M92P2M` with hardened runtime. Both stopped at notarization: `No Keychain password item found for profile: EnCAP`. Independent `notarytool history` reproduced that error. Neither has a stapled ticket; Gatekeeper rejects both as **Unnotarized Developer ID**. These files are incomplete signing outputs, not distributable final packages. No current-source qualification draft or `verify-macos.yml` run was created.

An [earlier unpublished qualification draft](https://github.com/tlolabs/ativ/releases/tag/untagged-97773b46515965188a37) remains as historical evidence only: release ID `401040650`, source `e6c61a961e6339d6d09b457b2d92e5c0e3a16781`. Its notarized artifacts are not substitutes for the current source. It is neither the requested stable release nor evidence of updater installation.

## Audit, fixes and tests

The security diff scan reviewed 27 source items plus surrounding native and release code and reported no plausible security findings within its frozen initial scope. Later fixes were reviewed and tested separately; the sealed scan does not cover every later edit. The [machine-readable report](qualification-20261001.json) records scope, scan identity, usage, failures, source revisions and hashes.

Fixes include the Sparkle manual action receiver; active-export termination coordination; Windows render/update startup coordination; malformed/failed/interrupted download handling tests; cancellation error classification; immutable GitHub draft-ID lookup; authenticated stapled-ticket handling in provenance comparison; platform compiler warnings; release-tool dependency patches; and reproducible Linux packaging tool pins. The shared updater snapshot remains identical in ATIV and EnCAP. AVID Core was not changed.

| Verification | Result |
| --- | --- |
| Rust unit/integration/updater tests | 33 passed, including 21 shared updater tests |
| Existing performance tests | Both explicitly executed and passed despite being ignored by default |
| Python release/packaging tests | 30 passed |
| Native Swift tests | 6 passed on each Mac CI architecture |
| Media and lifecycle | 27 presets, 20 previews, 4 exports, cancellation/failure/process cleanup, damaged/missing managed runtime checks passed |
| Formatting and lint | Rust fmt, workspace/all-target Clippy with warnings denied, actionlint and shellcheck passed |
| Dependency inventory | 131 Rust dependencies; no missing metadata or notice files; native Linux notices have a separate unresolved gap |
| Current B local authentication | Signed manifest and archive accepted with deployed key; official Sparkle verification accepted genuine archive and rejected invalid signature/modified bytes |
| Native publication gate | Correctly rejected missing macOS arm64 installation evidence |

A previous Intel CI failure exposed early cancellation being misreported as `media_tools_unavailable`. A new deterministic regression reproduced it, the implementation was fixed, and the original lifecycle assertion was retained. The final matrix passes. No tests or signing gates were removed or weakened.

SHA-256 checks integrity; it is not the authentication authority. The shared path verifies Ed25519 metadata bound to application/repository/version/platform/architecture and the archive digest. macOS additionally retains Sparkle archive authentication and native Developer ID/Gatekeeper checks. Unit, fixture and command-line authentication results do not establish the native installation/relaunch portion of this trust chain.

## Unperformed acceptance and remaining blockers

Every requested in-app step remains unperformed: displayed A version, manual GitHub discovery of B, in-app download, install, relaunch into B, settings/user-file preservation, post-update media regression, same-version no-update check and normal subsequent relaunch. Standalone launch tests and independent downloads were not counted as these steps.

1. Restore or unlock the existing `EnCAP` notarization profile locally. Preserve incomplete package files before resuming the signing script; it intentionally refuses replacement. Complete notarization/stapling/Gatekeeper, create the exact-source unpublished draft, and run the independent `verify-macos.yml` workflow using its immutable release ID.
2. Native UI attachment repeatedly crashes in `SkyComputerUseService` while ATIV remains running. Finder attachment succeeded. The computer-use tool requires explicit authorization before switching automation technology; permission to use AppleScript accessibility automation was requested and remains pending. No alternative UI automation was used.
3. Perform prepublication native upgrade/failure tests and manual acceptance for exact final package hashes. Only then may ledgers mark those checks passed. Publish through the normal signed-tag pipeline, then execute the actual GitHub A-to-B transition and regression checks.
4. The configured GPG signing key could not unlock through noninteractive curses pinentry. All source commits have DCO sign-offs; cryptographic commit signatures were omitted as authorized. A cryptographically signed stable tag is still required.
5. Windows still needs Azure signing provisioning and real signed upgrade/interruption/recovery qualification, including the portable replacement power-loss gap. Linux still needs production signing, native AppImage update/failure tests, bundled native-library notice coverage (including liblzo2) and AppStream metadata cleanup. One GTK header pedantic warning comes from the runner's system header. Default-branch dependency alerts remain separate from the patched branch.

The upstream hash-pinned Sparkle Downloader has an empty entitlement dictionary, preserved in the signed app. No claim is made that this change enables its sandbox.

Evidence logs and retained historical candidates are under `build/updater-qualification-20260930/` and excluded from Git. Native acceptance ledgers remain unqualified.
