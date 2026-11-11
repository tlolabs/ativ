# AVID Core 0.3.3 Apple source refresh

ATIV vendors the exact 34-file Apple transcription export from the local AVID
Core `v0.3.3` source-release commit at `8e27a86ec106028d93130de35a35c0eeda7a9ce3`, without local
source edits. GitHub still published 0.3.2 at integration time; the bundled snapshot
provides the local 0.3.3 source without depending on remote availability. Archive SHA-256:
`4234053bad548df25c68949265cb32b4052091856e6da6ad2d0710640f8f67ae`.
The tar entries use fixed timestamps, owner/group IDs and modes, and gzip uses a
fixed timestamp, so the archive can be reproduced from the manifest and commit.

Compared with the previously pinned `v0.3.2` export, only the root `README.md`
changed. Every Apple package source, test, model catalog, dependency lock, license,
and platform requirement is byte-identical. WhisperKit, FluidAudio Parakeet, MLX
Qwen recognition/alignment, verified model downloads, word timing, caption grouping,
and SRT/WebVTT were already integrated; they are not new 0.3.3 capabilities.

The earlier handoff archive, manifest, and report remain unchanged under
[`history/2026-11-02`](history/2026-11-02/AVID_CORE_TRANSCRIPTION_CHANGE_REPORT.md).
That handoff's review claims apply only to its recorded source. The prior 0.3.2
export remains in Git history. No historical audit is attributed to this refresh.

The acquisition script pins the release and revision as well as the archive hash,
then verifies every extracted file and rejects unexpected members or altered
existing source. A mismatching existing `build/transcription-core` is preserved;
move it aside before acquiring this version. Package integrity seals continue
identifying the exact source archive. Engine SDK pins and attribution do not change.

ATIV's helper owns the process protocol and batched edit orchestration, using
Core's segment-correction API while updating the segment array once. Partial
caption options/windows now obtain unspecified values from Core's public default
constructors. ATIV retains UI, document persistence, output publication, and
animated caption rendering. The optional helper still requires Apple silicon,
macOS 14, Swift 6.3 and Metal; Intel/macOS 13 UI and Windows/Linux do not gain local
transcription from this source refresh.

Current build, functional-test, and independent-review evidence must be assessed
against this source separately from historical results.
