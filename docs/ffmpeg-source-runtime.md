# AVID Core runtime acquisition

AVID Core owns the FFmpeg/FFprobe source, recipe, native builds and runtime contract. ATIV never builds or selects a separate distribution. The exact six-target build identity is recorded in `runtime/core-runtime.json`, with original archive, source, executable and manifest hashes.

The shared `script/core_runtime.py` verifies the expected repository, release tag, promotion workflow, release revision, manifest digest and matched runtime identity before extraction or execution. Production requires a published Core release; it currently fails closed because the release is not yet published and pinned. There is no system/PATH fallback or first-launch media-tool download.

For unpublished host qualification only, set `AVID_CORE_QUALIFICATION=1` locally or dispatch `native-release.yml` with `qualify_core_candidate=true`. Candidate origin is pinned to Core commit `25d19098a22936638b0e2a70616083d929fe409c`, maintainer dispatch run `36681249099`, six actual native jobs and GitHub artifact digests. PR/push publication cannot acquire candidates.

Final packages preserve Core metadata and corresponding source. `signed-payload.json` records original and signed derivative hashes without rewriting Core's original checksum manifest. Packaging validates the compiled Core identity and both bundled tools with an empty PATH. See [release integration](release-integration.md) for signing configuration and remaining gates.
