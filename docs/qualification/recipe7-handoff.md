# ATIV Recipe 7 qualification handoff: incomplete

**Do not mark Core's ATIV `host_packaging` gates satisfied yet.** All six targets passed the automated candidate build/package, runtime/media/lifecycle, installation/launch, checksum/provenance and offline update-signature checks. Required release acceptance remains incomplete.

- Exact Core build/source: `fab2ed86bb64582d3f7a7dd736c713cc3951550b`, Core 0.2.2, FFmpeg 9.0.1 Recipe 7; original native run `35157560636`.
- Exact ATIV tested source: `ba87f58fcd42a7d99d46ab8a5f4d3b96569eb61d`, provisional branch `codex/recipe7-host-qualification`.
- Final host run: [35164085994](https://github.com/tlolabs/ativ/actions/runs/35164085994). Its six native jobs intentionally fail only at `Enforce outstanding application release gates`; every preceding recorded qualification step passed. This is not a passed full release gate.
- [Machine-readable six-target summary](ci/35164085994/summary.json), [job/step results](ci/35164085994/jobs.json), [immutable artifact IDs/digests](ci/35164085994/artifacts.json), [exact original archive/source/executable checksums](../../runtime/recipe7-candidate.json).

| Target | Build/package | Media/lifecycle and bundled discovery | Installation/launch and packaged provenance | Offline update signatures | Full host gate |
| --- | --- | --- | --- | --- | --- |
| macos-arm64 | Passed, ad-hoc signed | Passed | Passed, installed DMG app; launch/exit | Passed, Sparkle-format package and metadata | Incomplete |
| macos-x86_64 | Passed, ad-hoc signed | Passed | Passed, installed DMG app; launch/exit | Passed, Sparkle-format package and metadata | Incomplete |
| windows-x86_64 | Passed, unsigned | Passed | Passed, actual installer, installed app and same-version replacement/uninstall | Passed, native updater verification and tamper rejection | Incomplete |
| windows-arm64 | Passed, unsigned | Passed | Passed, actual installer, installed app and same-version replacement/uninstall | Passed, native updater verification and tamper rejection | Incomplete |
| linux-x86_64 | Passed | Passed | Passed, extracted/launched AppImage, installed deb, replacement/removal | Passed, signed real package metadata | Incomplete |
| linux-arm64 | Passed | Passed | Passed, extracted/launched AppImage, installed deb, replacement/removal | Passed, signed real package metadata | Incomplete |

Each target's report records its actual native OS/architecture, exact candidate and ATIV source, original/signed/actual packaged executable hashes, package checksums, step outcomes and missing gates. Tests ran natively on the authorized macOS 15, Windows Server 2025 x64, Windows 11 ARM64 and Ubuntu 24.04 runner families. No minimum-OS claim is added. Reports were downloaded from digest-verified immutable Actions evidence ZIPs. The summary authenticates retained reports and compressed full job logs with SHA-256.

## Exact remaining gates and root causes

1. **Production application signing/notarization — both macOS targets.** Developer ID identity/certificate and notarization credentials are unavailable. The owner explicitly confirmed setup is not completed. The only repository secret found before qualification was the update-signing key; the local keychain had zero valid code-signing identities. Ad-hoc signature verification passed but does not fulfill this gate.
2. **Production application signing — both Windows targets.** Windows signing certificate setup is unavailable, as confirmed by the owner. Actual unsigned packages were exercised, but they cannot establish production signature acceptance.
3. **Authenticated end-to-end application upgrade — all six targets.** The existing clients select production/development GitHub release feeds; an isolated candidate delivery/upgrade route has not been implemented or qualified. No feed/release was published or changed. Actual-package signatures, signature tampering, native updater checksum verification on Windows and same-version installer replacement on Windows/Linux passed. These do not prove a signed newer application was discovered, downloaded, applied and relaunched through the real update client.
4. **Manual UI/accessibility acceptance — all six targets.** Automated startup/native process tests passed. Manual UI/accessibility acceptance was not performed and is not represented as passed.

No remaining FFmpeg candidate defect was demonstrated. ATIV-local problems were repaired: relocate macOS runtime notices before main-executable signing; preserve exact Core binaries after linuxdeploy's ELF rewriting; use native Rust updater verification for Windows ARM64 instead of an unavailable Python/OpenSSL toolchain. The [prior full run](ci/35162941168/summary.json) and its retained logs preserve those failures. [Supplemental local macOS evidence](local-macos-arm64/report.json) is explicitly marked as an observation from a modified worktree; the final clean CI source is authoritative.

Core source/ledger were not changed. No production ATIV release was published. These exact candidate observations must not be transferred to a different executable pair or silently changed to `passed`.

To independently recollect the final immutable evidence into a fresh directory:

```sh
python3 script/collect_recipe7_evidence.py 35164085994 \
  --revision ba87f58fcd42a7d99d46ab8a5f4d3b96569eb61d \
  --output build/recollected-recipe7-evidence
```

## Message for the AVID Core task

ATIV tested the exact Recipe 7 candidates from Core `fab2ed86bb64582d3f7a7dd736c713cc3951550b` / native run `35157560636` on all six required native targets. ATIV tested source is `ba87f58fcd42a7d99d46ab8a5f4d3b96569eb61d`; host run is `35164085994`. All automated build/package, media/lifecycle, installed-launch, provenance/checksum and offline signature checks passed after ATIV-local fixes. Full `host_packaging` remains incomplete: production macOS/Windows signing setup is unavailable, authenticated end-to-end upgrades are unperformed, and manual UI/accessibility is unperformed. Do not mark the gates passed. The ATIV qualification branch contains exact-pair reports, immutable artifact digests, source/package checksums and full logs under `docs/qualification/ci/35164085994/`, with original candidate hashes in `runtime/recipe7-candidate.json`. No Core modification or production ATIV publication occurred.
