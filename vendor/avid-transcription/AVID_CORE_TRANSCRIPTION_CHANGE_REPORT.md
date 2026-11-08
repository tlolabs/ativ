# AVID Core 0.3.2 Apple source refresh

ATIV now vendors the exact Apple transcription source from published AVID Core
`v0.3.2` at `8296a9e623c6924c12e456b5fe9e7c10b59dfbde`. All 34 exported files come directly from that commit, with no
local source edits. Archive SHA-256: `a302200860bde5c47cd4aeabacefedefa30e6112248302925164589ce9f45937`.

The earlier handoff archive, manifest, and report are preserved unchanged under
[`history/2026-11-02`](history/2026-11-02/AVID_CORE_TRANSCRIPTION_CHANGE_REPORT.md).
That handoff's upstream review and test claims apply only to its recorded source
hash. This refresh makes no claim that the historical audit reviewed these bytes.

Compared with the former handoff, the changed implementation files are
`ModelStore.swift`, `ModelStoreTests.swift`, and `avid-transcribe/Command.swift`.
The released store adds `provisionForUse` for explicit local, offline, and download
routing; `withInstalledModel` reports verification progress and performs full
verification on a utility queue while retaining the model lease through use.
The command uses those APIs when provisioning recognition and alignment models.
The released README, repository policy, and Apple verification report are also
included. Catalog/model pins, engine package locks, deployment targets, and
third-party notices remain byte-identical to the original handoff.

The build scripts pin the new archive hash and continue rejecting altered source,
unexpected files, unsafe archive members, and mismatching package integrity seals.
ATIV's dependency inventory identifies the published upstream commit and release;
it no longer attributes the old handoff review snapshot to the current source.

Current application build, package, functional, and independent-review evidence
must be assessed against this refreshed source separately from historical results.
