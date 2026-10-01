# AVID Core runtime acquisition

AVID Core owns the FFmpeg/FFprobe source, recipe, native builds and runtime contract. ATIV never builds or selects a separate distribution. The exact six-target build identity is recorded in `runtime/core-runtime.json`, with original archive, source, executable and manifest hashes.

The shared `script/core_runtime.py` verifies the expected repository, release tag, promotion workflow, release revision, manifest digest and matched runtime identity before extraction or execution. Normal builds acquire the published `ffmpeg-9.0.1-r7.1` release, whose manifest SHA-256 is `ef7eb4e2b62f656aa3cb6808dc2d227eb035be2050367d596e1f79a6d6d45779`. The Rust library and native tool build are pinned to `25d19098a22936638b0e2a70616083d929fe409c`; the release promotion revision is `2e137df692aa612e0dd62ebd93b5fff26c61663a`. There is no system/PATH fallback or first-launch media-tool download.

For unpublished host qualification only, set `AVID_CORE_QUALIFICATION=1` locally or dispatch `native-release.yml` with `qualify_core_candidate=true`. Candidate origin is pinned to Core commit `25d19098a22936638b0e2a70616083d929fe409c`, maintainer dispatch run `36681249099`, six actual native jobs and GitHub artifact digests. PR/push publication cannot acquire candidates.

Final packages preserve Core metadata and corresponding source. `signed-payload.json` records original and signed derivative hashes without rewriting Core's original checksum manifest. Packaging validates the compiled Core identity and both bundled tools with an empty PATH. See [release integration](release-integration.md) for signing configuration and remaining gates.
