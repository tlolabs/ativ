# AVID Core 0.3.2 integration in ATIV 0.2.8

ATIV pins the published AVID Core `v0.3.2` release at
`8296a9e623c6924c12e456b5fe9e7c10b59dfbde` in Cargo.toml and Cargo.lock.
The Rust API and separately packaged Apple transcription components use that exact
commit. No AVID Core checkout is needed to build ATIV and no upstream files were
edited. The existing authenticated FFmpeg platform pins and update verification
contracts remain unchanged.

## Changes

Core supplies portrait square-pixel correction and GIF/APNG video rendering fixes,
as well as its released image optimization dependencies. Native integration tests
now verify animated playback, finite-animation last-frame holding, default/current
pixel parity, and explicit Simple-mode freezing, including misleading suffixes.
The lifecycle FFmpeg test double advertises its required setsar capability.
Packaging includes Core's nested image codec license texts and third-party notices.

The Apple archive contains 34 unmodified files from the same released commit.
Its SHA-256 is
`a302200860bde5c47cd4aeabacefedefa30e6112248302925164589ce9f45937`.
Acquisition still verifies the hardcoded archive identity and every extracted file.
The original November 2 archive, manifest and report are retained under
`vendor/avid-transcription/history/2026-11-02`; that historical audit is not
attributed to this refreshed source. The new model store performs full verification
on its utility queue and retains the model lease through recognition/alignment.

Release diagnostics also identified pre-existing updater dependency advisories.
Cargo.lock now uses rustls-webpki 0.103.16, webpki-roots 1.0.10 and tokio 1.53.3.
The dependency inventory was regenerated from the exact source graph.

## Local verification on November 8, 2026

The following checks passed on native macOS Apple silicon:

| Check | Result |
| --- | --- |
| Rust format and strict workspace/all-target Clippy | Passed |
| Locked workspace/all-target tests | 43 passed, 5 intentionally ignored |
| Configured Python unittest discovery | 68 passed |
| Weekly smoke controller offline tests | 87 passed |
| Dependency inventory check | Passed |
| cargo audit --no-fetch | Passed with the installed 1,422-advisory database; no fresh database update claimed |
| Debug-engine Core native diagnostics | 58 native groups passed, zero failed or simulated |
| Packaged engine media contract | Passed: 27 presets, 20 previews, 4 exports, errors, cancellation and process cleanup |
| Native Swift application tests using packaged engine | 49 passed |
| Core Apple transcription contracts | 32 passed |
| Core engine adapter tests | 14 passed, including native AVFoundation decoding |
| Transcription helper bridge tests | 9 passed |
| Native release packaging | Rust/Swift/Metal builds, architecture, helper resources/dependencies, strict ad-hoc signature checks, authenticated runtime validation and fresh ZIP extraction passed |
| Packaged startup and engine communication | Passed: startup true, 27 presets |
| Native application/engine/media runtime dependencies | Passed; no unbundled developer dependencies |

Local artifact: `packages/ATIV-0.2.8-macos-arm64.zip`.
SHA-256: `eb79ab2bc5c3fee5758d9d5cfe43404e1cc39cea6341edbc338b7e7d80638887`.
Additional native diagnostic reports are retained in `build/core-0.3.2/`.
Task logs, requirements, initial status and independent audit records are retained
outside the source tree under task ID `ativ-core032-release-20261108-a73f09`.
Review attribution, findings, audited/final source hashes and actual publication
state are recorded with the task's final release evidence; this report does not
claim a completed external audit or a published artifact in advance.

## Resolved setup failures and remaining limitations

The first updater HTTP contract tests lacked local socket permission; the complete
workspace rerun passed with native access. The first Swift app tests used the bare
debug engine without packaged runtime metadata; all 49 passed against the packaged
engine. Two AVFoundation adapter tests initially lacked system-service access;
both passed in the native rerun. Initial package validation exposed the missing
setsar capability in the test double; the corrected full package checks passed.
A preliminary packaged diagnostic overlapped a bundle rebuild and briefly could
not find the engine; its result is not treated as a clean run.

An offline speech inference smoke attempt could not run because the old temporary
model cache contains no model weights. No weights were downloaded. Contract,
adapter, helper catalog/integrity and package checks do not establish recognition
accuracy. Fresh three-model recognition/alignment inference remains unverified.

The ZIP is ad-hoc signed, without Developer ID signing or notarization, and is
not enrolled in an authenticated update feed. Intel macOS, Windows and Linux
artifacts were not natively qualified by this task. No legacy workflows were
restored or dispatched. The weekly Linux/Windows smoke schedule remains diagnostic
and does not publish artifacts. Interactive accessibility, minimum-OS runtime and
full speech accuracy testing were not performed.
