# Reviewed AVID Core transcription source

This directory retains the exact, unpublished Apple source export supplied by
the AVID Core transcription handoff. It is not a fork or a claim of a published
release. The original archive is kept intact; no transcription implementation is
edited here. The manifest records every exported file and the completed upstream
Antigravity review identity. The accompanying report preserves upstream evidence
and its limits; relative evidence links refer to the original handoff folder.

Archive SHA-256:
`f4555615571d54b96d714be26caf0484f6049835065d7215820c3244bf761c5a`.

`python3 script/transcription_runtime.py acquire` verifies the archive against the
hard-coded identity and every extracted file against the manifest, then atomically
materializes `build/transcription-core`. ATIV's separate helper uses local package
references into that controlled tree. A neighboring AVID Core checkout is never
required. The helper's own `Package.resolved` pins the engine SDK graph.

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
