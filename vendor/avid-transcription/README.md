# AVID Core 0.3.2 transcription source

This directory contains an unmodified export of 34 Apple transcription, catalog,
documentation, policy, and license files from published AVID Core `v0.3.2`,
commit [`8296a9e623c6924c12e456b5fe9e7c10b59dfbde`](https://github.com/tlolabs/avid-core/tree/8296a9e623c6924c12e456b5fe9e7c10b59dfbde). It is a pinned
source dependency, not an application-owned transcription fork. The manifest
records the upstream repository, release, commit, and every exported file hash.

Archive SHA-256:
`a302200860bde5c47cd4aeabacefedefa30e6112248302925164589ce9f45937`.

The original November 2 handoff archive, manifest, and report are retained under
[`history/2026-11-02`](history/2026-11-02/AVID_CORE_TRANSCRIPTION_CHANGE_REPORT.md).
Their completed upstream review covers that historical handoff only. It does not
certify this refreshed archive. The [refresh report](AVID_CORE_TRANSCRIPTION_CHANGE_REPORT.md)
describes the source changes; current ATIV validation is recorded separately.

`python3 script/transcription_runtime.py acquire` verifies the archive against the
hard-coded identity and every extracted file against the manifest, then atomically
materializes `build/transcription-core`. ATIV's separate helper uses local package
references into that controlled tree. A neighboring AVID Core checkout is never
required. The helper's own `Package.resolved` pins the engine SDK graph. Existing
extracted source from a different archive must be preserved or removed before
acquiring this version; source validation does not overwrite unexpected contents.

`stage` builds only on native Apple silicon, with deployment target macOS 14.0.
The helper is a separately signed app at
`Contents/Helpers/ATIVTranscriptionHelper.app`; its executable is under
`Contents/MacOS`, SwiftPM/Metal resource bundles and license notices are under
`Contents/Resources`, and required Swift compatibility libraries are under
`Contents/Frameworks`. An integrity manifest in the outer ATIV app's
`Contents/Resources/transcription-package.json` hashes the finalized helper app,
including its signatures. The enclosing ATIV UI remains macOS 13 compatible;
Intel packages omit the helper. Models are optional verified downloads after
installation and are not included in this source archive or the app bundle.
