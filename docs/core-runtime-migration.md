# Production runtime migration audit (2026-09-16)

> Historical record: superseded by [ATIV-owned FFmpeg source builds](ffmpeg-source-runtime.md). The Core publication blocker below no longer controls ATIV runtime acquisition.

## Before changes

ATIV's successful local qualification app and normal builds had different entrypoints:

| Path | Previous behavior |
| --- | --- |
| `script/fetch_ffmpeg.sh` | SHA-pinned Martin Riedl macOS binaries and BtbN Windows/Linux binaries; independently owned versions, URLs and cache reuse |
| `.github/workflows/native-release.yml` | Four acquisition steps invoked that downloader; all six native targets inherited it, including tagged and development builds |
| `script/package_macos.sh` | Accepted independent FFMPEG_BIN/FFPROBE_BIN, checked a literal version, copied the pair, and defaulted the FFmpeg license to ATIV's LICENSE |
| `script/package_windows.ps1`, `script/package_linux.sh` | Accepted an arbitrary binary directory, checked a provider-specific version prefix, copied tools/notices |
| `script/build_and_run.sh` | Selected independent environment/PATH tools and copied them into the local app |
| `crates/ativ-engine/src/media_tools.rs` | Managed discovery existed only behind a non-default feature; ordinary builds used general discovery |
| `script/verify_ffmpeg_distribution.py` | Duplicated version/capability policy from Core |
| `script/test_engine_contract.py`, `script/test_engine_integration.sh` | Legacy version prefix and PATH-based engine invocation |
| `script/package_core_candidate_macos.sh` | Enabled managed discovery, validated and staged Core's recipe-6 payload, signed it, relocated metadata into Resources and tested actual packaged media |
| `script/acquire_core_runtime.py` | Delegated authenticated acquisition to Core, but ordinary builds never called it |

Ignored `build/ffmpeg-*` directories and existing bundles contain working legacy media. They are not production inputs after migration; existing user artifacts are preserved. Historical benchmark and release reports describe old measurements and are retained as history, not build instructions.

## Core publication blocker

Core source tag `v0.2.1` resolves to `eab97dd043187aa8b7a1cae4eb2c1228fa25a9db`. It is not a runtime release. The runtime mapping remains FFmpeg 9.0.1, recipe 6, status candidate.

[Core run 35065840420](https://github.com/tlolabs/avid-core/actions/runs/35065840420) passed native macOS ARM64/x86_64, Linux ARM64/x86_64 and Windows ARM64. Windows x86_64 failed `simple_matches_legacy_pixels_audio_and_requested_cadence`: FFmpeg exited with 0xC0000005 (access violation) during legacy portrait composition at 60 fps. Completion/publication were skipped. These were build-only runs with publication disabled; Core also requires an explicit publish dispatch on its default branch and a fully qualified ledger. There is no evidence of a failed upload or an available runtime release. Minimum-OS, environment qualification and production host acceptance also remain incomplete in Core's ledger. The separate shared-core run has a Linux cancellation-test failure. No checks are waived by this migration.

Normal production acquisition requires Core to publish an immutable `ffmpeg-9.0.1-r6` release at the selected Core commit (or a newer qualified recipe and corresponding pin), with six matching `avid-ffmpeg-<version>-r<recipe>-<target>.tar.gz` runtime archives, six `-sources.tar.gz` corresponding-source archives, SHA-256 sidecars and GitHub build attestations. Embedded spec/build/validation/repeat/source/signature/license evidence must pass Core's verifier. GitHub asset digests, tag identity and attestations are checked before extraction. A crate tag or passing local candidate alone cannot satisfy this contract.

The architectural migration can be prepared and tested with the existing candidate, but production acquisition and cross-platform packaged acceptance remain blocked until Core supplies those artifacts. ATIV must fail clearly and must not download another vendor's binaries.

## Implemented host changes

- Normal engine discovery always calls Core's managed-layout API; deliberate CLI development overrides remain explicit.
- `script/core_runtime.py` provides host layout/provenance functions around Core's `acquire.py` and `host.py`. Production and the qualification harness share staging, source retention, original/signed hashes and packaged media validation. Production never enables candidate acceptance.
- The local app builder and all three native package scripts provision the same pinned runtime, before modifying any existing app. CI supplies only native target IDs; all four Core checkouts match the immutable pin.
- Removed `fetch_ffmpeg.sh`, vendor URLs/checksums, provider-specific version checks, arbitrary packaging binary inputs, the non-default managed-runtime feature, and duplicated `verify_ffmpeg_distribution.py` capability policy. Preserved ignored working caches/bundles, which have no remaining production references.
- Runtime metadata and actual notices/source live in macOS `Contents/Resources/FFmpeg` or beside the engine on Windows/Linux. `ativ-runtime.json` identifies app/Core/source-build versions and revisions, recipe, platform and architecture. Post-sign validation compares the payload with Core's verified original and checks the separately recorded signed binary hashes.
- `test_runtime_ownership.py` checks all production entrypoints, exact CI pins, forbidden vendor acquisition URLs, candidate bypasses and managed discovery. Package validators execute the actual bundled engine, FFmpeg and FFprobe and run exports/previews/lifecycle cases. Existing native launch/installer checks remain in CI.

## Verification of this change

| Target / check | Result |
| --- | --- |
| macOS ARM64 shared staging and signed candidate app | Passed: 27 presets, 20 previews, 3 exports, lifecycle, 2 native tests, launch/startup report |
| macOS ARM64 missing/damaged bundle with external runtime on PATH | Passed; no fallback |
| Manifest/provenance tampering and production rejection of candidate | Passed |
| macOS x86_64, Windows ARM64/x86_64, Linux ARM64/x86_64 normal packaging | Blocked before packaging: Core candidate cannot be acquired as production |
| All six target production acquisition attempts on local host | Correctly failed closed at Core qualification; no vendor request |
| ATIV Rust tests, formatting, clippy | Passed locally |
| Release infrastructure tests | 7 passed |
| Runtime ownership guards | 3 passed, including inserted downloader/bypass/pin regressions |
| Shell syntax, Python compilation, actionlint | Passed |
| Existing working macOS package | FFmpeg/FFprobe/engine SHA-256 values unchanged |

The tested candidate used FFmpeg 9.0.1 recipe 6 built at Core `9eb8651bc09b6fb007784d3df840d51fa7bbba82`; the consuming engine uses Core 0.2.1 at `eab97dd043187aa8b7a1cae4eb2c1228fa25a9db`. The source build and consumer revision are deliberately recorded separately. Candidate mode is local qualification only and does not assert authenticated production release acquisition.

Local logs: `build/core-migration-rust-tests.log`, `core-migration-managed-tests.log`, `core-migration-package.log`, `core-migration-acquisition.json`, `core-migration-provenance-tests.json` and `core-migration-launch.json` (all under `build/`). The new candidate is separate from the working app. No ATIV release has been published.

**Acceptance remains incomplete:** production artifacts, production package/media/startup acceptance across six targets, and Core's required qualification gates are still blocked. Once Core resolves the Windows crash, completes its ledger, rebuilds and publishes the immutable attested set, select that exact release commit consistently in the ATIV pin/lock/workflow and rerun the full native matrix. Do not merge this branch as a claim of completed production migration or publish an ATIV release on candidate evidence.

## Native CI result for the migration

[ATIV run 35118805357](https://github.com/tlolabs/ativ/actions/runs/35118805357), implementation commit `bfa026c9bd0334a471991e604e40c6188713f11a`, completed with the shared Rust engine/ownership job passing. **All six native jobs failed at `Acquire pinned Core runtime` with `Runtime qualification is incomplete`.** None reached application packaging or publication; those acceptance tests remain not run for production artifacts. This is evidence that each platform enforces the same Core gate, not evidence of passing native packages.

| Native CI target | Acquisition | Package/media/launch |
| --- | --- | --- |
| macOS ARM64 | Blocked by Core candidate | Not run |
| macOS x86_64 | Blocked by Core candidate | Not run |
| Windows ARM64 | Blocked by Core candidate | Not run |
| Windows x86_64 | Blocked by Core candidate | Not run |
| Linux ARM64 | Blocked by Core candidate | Not run |
| Linux x86_64 | Blocked by Core candidate | Not run |

The normal local `build_and_run.sh` and `package_macos.sh` entrypoints were also exercised: both stopped at acquisition before replacing the working bundle. The qualification app is the only newly built application from this migration. The preserved local caches are not used by any production entrypoint.
