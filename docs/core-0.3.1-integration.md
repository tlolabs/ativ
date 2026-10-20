# AVID Core 0.3.1 integration — local qualification

ATIV on `main` consumes the exact Git source revision
`15f28236142c100d0a83bf19154ed6f9f5b44e75`, version `=0.3.1`, from
`https://github.com/tlolabs/avid-core.git`. Cargo.lock is retained and updated.
The workspace builds from Cargo's resolved dependency without an adjacent Core
checkout. The pre-existing EngineClient changes, updater snapshot and untracked
GitHub Actions audit files were preserved. No commit, push, workflow dispatch,
application publication or other repository modification was performed.

The implementation was checked against the resolved source, public
[application integration contract](https://github.com/tlolabs/avid-core/blob/15f28236142c100d0a83bf19154ed6f9f5b44e75/docs/integration.md),
[provider contract](https://github.com/tlolabs/avid-core/blob/15f28236142c100d0a83bf19154ed6f9f5b44e75/docs/ffmpeg/provider-contract.md),
Renderer, media tools, commands, probes and staged publication implementation.
Historical handoffs were not treated as the current contract.

## Behavior and ownership

Artwork dimensions, bounded probes, PNG composition previews, software H.264/AAC
exports, progress, cancellation and atomic output publication use Core's public
Renderer API. These capabilities include work from earlier Core releases; this
integration does not claim they all originated in 0.3.1. ATIV contains no copied
filter graph or rendering implementation.

The default `auto` policy uses `render_with_mode(..., RenderMode::Simple, ...)`
only for verified single-image PNG/JPEG/BMP containers. Simple composes the first
frame once and reuses it in FFmpeg memory; it writes no intermediate PNG.
Container checking is bounded, allocation-free host playback policy, not image
validation. Core still validates/probes the artwork.

Potential animation stays on `RenderMode::PerFrame` (`--render-mode current`):
APNG, appended PNG/BMP/JPEG streams, PNM, WebP, GIF, TIFF and unknown inputs. Both
native choosers/drop handling admit animated formats. Tests demonstrated that
concatenated PPM/PNG/BMP animate with existing PerFrame behavior, so suffix-only
static detection would have been a regression. PNG must end at IEND/EOF without
an animation control chunk; BMP's declared size must match EOF; JPEG's first end
marker must be EOF. Ambiguous/large containers conservatively retain PerFrame.
Explicit `--render-mode simple|current` remains available for comparisons, and
`auto` is optional. Static WebP/TIFF/PNM also retain PerFrame until Core exposes a
public animation-aware inspection contract.

`inspect-image --image PATH [--image PATH ...]` exposes Core inspection while
reusing one Renderer/cache. Renderer clones share cache state; capability caches
are shared with MediaTools clones. The GUI retains the process-per-request
protocol, so caches do not persist across separate GUI process launches. macOS
preview keys include source size/modification time so changed artwork refreshes.
Core's cache fingerprint is size plus modification time, not a content hash.

Input::Single, Composition::Fitted, software H.264/AAC, the 27 presets, flips,
1–240 fps, audio bitrate syntax, audio handling, dimensions, UI controls and
application/updater versions are preserved. No project schema was changed. These
native hosts do not currently expose project-file persistence. Callers can pass
project and other source paths with repeatable `--protected-path PATH`; Core also
protects the active image/audio. The engine supplies its executable, runtime
pair, diagnostic log and worker lock as protected paths. Preview clients protect
selected audio as well. Existing JSON events are retained; previews additionally
forward Core's existing stage events before their existing completion event.

## Lifecycle and runtime safety

Core blocking operations run in the engine process from native application
workers. macOS clients and Qt jobs serialize operations and drain workers before
application/runtime replacement or termination. A cancellable OS file-lock permit
also serializes engine processes for the current user, bounding aggregate Core
probing to at most four workers and preventing simultaneous destination writers.
Windows contention uses fs2's native error code. Each operation receives its own
cancellation token; cancellation while queued starts no media child.

Core alone stages and atomically replaces completed output. Failure/cancellation
keeps an existing destination intact. Clients honor successful return/publication
and Stage::Complete even when Stop arrives after publication; progress fraction 1
alone is never publication evidence. Failed previews no longer delete an existing
output. Stale probe callbacks cannot replace active export status.

The Rust update does not change either authenticated runtime pin. Current native
validation used the already selected macOS ARM64 platform release:

- FFmpeg/FFprobe 9.0.1 recipe 7, build revision
  `36ed2e8cc851236b30bf5325d8b465edceea45f4`.
- FFmpeg source `bf1b838f2ab88b4f8fd83443325c782ea0e0f7fa`.
- FFmpeg SHA-256 `eb9937d7e3d27b7bbbb73698d50e1e20149b540113b09e3d430d55d718b36ec0`.
- FFprobe SHA-256 `1851a46d6de0467078019b4f66269c56fc081e96fe7778d6ec91914adbb3f0a7`.

Existing provisioning reverified immutable release/tag, pinned manifest and
asset identities, trusted provider workflow/source/ref attestation, archive,
source, checksums and binaries. Complete installed Core directories use
MediaTools::from_core_directory; damaged metadata never falls back to bare tools.
Signed application bundles split metadata from executable copies and retain
ATIV's original strict signed-derivative validation followed by from_paths.
Staging validates the complete original directory through Core. There is no
production PATH/system fallback or checksum-only authentication. Acquisition,
installation, rollback, signing and authenticated update-feed requirements remain
unchanged. Core owns runtime builds/publication; ATIV owns its integration/package.

## Local evidence (October 20, 2026, macOS ARM64)

Commands and evidence below are diagnostic. No development gate was introduced.
The normal six-platform workflows remain automated and were not dispatched.

| Check | Result and coverage |
| --- | --- |
| cargo fmt --all -- --check | Passed |
| cargo build --workspace --locked --all-targets --all-features | Passed |
| cargo test --workspace --locked --all-targets --all-features | 43 passed, 5 intentionally ignored benchmarks |
| cargo clippy --workspace --locked --all-targets --all-features -- -D warnings | Passed |
| Configured build/release-tools Python unittest discovery | 58 passed |
| Dependency inventory generation/check | Passed; source identity updated, runtime unchanged |
| cargo audit --no-fetch | Passed using local advisory database; no fresh network audit claimed |
| Focused authenticated runtime/media diagnostics | 55 native groups passed, 0 failed, 0 simulated; 18 successful previews and 34 successful exports |
| Packaged runtime contract | 47 preset/aspect/flip previews, 4 exports, cancellation/process cleanup, protection, timeouts; 23 missing/damaged/provenance rejection cases passed |
| Swift client/store/Sparkle tests | 17 passed, 0 skipped; 5 native engine tests, 4 new process doubles plus other host/unit checks |
| Qt workflows on macOS | 21 passed including initialization/cleanup; actual preview/export/cancel plus 3 new process doubles |
| Qt accessibility on macOS | 10 passed including initialization/cleanup; UI fixtures use missing-engine state |
| build_and_run.sh --verify | App build, authenticated staging, ad-hoc signing, package validation and launch passed |
| Direct native UI exercise | PNG preview, both flips, Unicode WAV probe/destination and Create Video succeeded; output is H.264/AAC 1920×1080, 30 fps, 1.0 s |

The Rust cache integration test uses process doubles to count actual probe calls:
one repeated inspection across Renderer clones, a fresh probe after size changes,
one capability query across MediaTools clones, and one probe for two CLI requests
in one Renderer. Other error/unit checks also use doubles; they are not described
as native media qualification. Native diagnostics include portrait/landscape,
flips, static and concatenated containers, Unicode, repeated/changed inspection,
corrupt/oversized inputs, protected direct/hardlink/symlink paths, existing-output
preservation, missing/damaged tools, native encoder/preview/queued cancellation,
and success after cancellation arrives at Stage::Complete.

Native evidence is retained locally under `build/core-0.3.1/`:
`native-rendering.json`, `ui-verification.json`, `cargo-audit.json`,
`python-tests-configured.log`. Runtime rejection evidence is in
`build/core-0.3.1-native-engine/runtime-verification.json`. Swift/Qt/package logs
are under `build/core031-host-media/`. The local app is `dist/ATIV.app`.
The normal native integration script now runs both managed-runtime and focused
Core diagnostics, continuing to the second suite if the first reports failure.

## Measured Simple/PerFrame comparison

Identical artwork, encoder settings and authenticated runtime: 1200×800 source,
1920×1080 output, software H.264/AAC, 30 fps, 128k audio, three seconds. One warmup
and three alternating measured rounds per mode. Application wall time includes
runtime validation, probes and atomic publication.

| Mode | Median wall seconds | Decoded result |
| --- | --- | --- |
| Simple | 0.458735 | 90 frames, 3.0 s video/audio |
| PerFrame/current | 0.648563 | 90 frames, 3.0 s video/audio |

All decoded frame hashes/timestamps and decoded audio matched. This fixture had
about 29.3% lower wall time with Simple on this host; it is not a general speed
promise. Four additional portrait/landscape/flip comparisons at 30/60 fps also
matched decoded RGB/audio/cadence/duration. Core's historical PerFrame endpoint
rules remain unchanged; parity is measured for these fixtures, not asserted for
all durations or inputs.

## Failures, limitations and unrun work

- Core's current PerFrame animated GIF export fails with `Option loop not found.`
  The exact runtime inspected a valid two-frame GIF and generated its first-frame
  PNG preview; default/current exports both failed and preserved the destination.
  ATIV keeps PerFrame policy and reports the error. No substitute filter graph
  or forced first-frame export was introduced. This existing Core limitation and
  remaining platform qualification are tracked in [ATIV's consolidated issue #18](https://github.com/tlolabs/ativ/issues/18#issuecomment-6295191692).
- Core exposes dimensions, not public frame-count/animation classification.
  Conservative host defaults are intentional. Concatenated JPEG retains the
  exact runtime's existing first-image behavior.
- Core has no optimize_image, TurboJPEG, OxiPNG or standalone optimizer. This work
  makes no JPEG optimization, metadata removal or image privacy guarantee.
- First sandbox Rust run: three updater loopback-server binds were denied; all
  passed with local sockets permitted. System Python lacked cryptography (two
  import errors); configured build Python passed all 58. Swift nested sandbox /
  module-cache and Qt preferences-write restrictions were resolved using local
  caches, --disable-sandbox for SwiftPM, and isolated CFFIXED_USER_HOME for tests.
- An initial native diagnostic incorrectly expected concatenated JPEG animation;
  the fixture expectation was corrected to compare existing PerFrame behavior.
  Its report is retained as native-rendering-initial-jpeg-expectation.json. The
  final 55-group report passed against the same engine source.
- A CUA screenshot permission review timed out once; its retry succeeded and
  showed the saved-video status. No task action remained blocked.
- macOS Intel, Windows ARM64/x64 and Linux ARM64/x64 native builds, packages,
  accessibility, runtime/launch and functional checks were not run here. Qt on
  macOS does not qualify those native targets. Windows lock behavior is covered
  by portable code/unit assertions, not a native Windows run. No other platform
  artifact is qualified for publication by this local run.
- Five opt-in microbenchmarks, a compiler-at-exact-MSRV 1.88 run, new online
  advisory/security service checks, CodeQL, Developer ID/notarization and signed
  updater publication were not run. Existing automation/signing workflows remain.

## Changed source files

- Cargo.toml and Cargo.lock; crates/ativ-engine/Cargo.toml.
- crates/ativ-engine/src/{main,media_tools,artwork,worker}.rs.
- crates/ativ-engine/tests/{protocol,probe_cache}.rs.
- platform/macos/Sources/Services/EngineClient.swift;
  platform/macos/Sources/Stores/RenderStore.swift;
  platform/macos/Tests/EngineClientTests.swift.
- platform/qt/{EngineJob.cpp,EngineJob.h,MainWindow.cpp,MainWindow.h,tests.cpp}.
- script/{ffmpeg_runtime.py,test_core_rendering.py,test_engine_contract.py,
  test_engine_integration.sh,test_runtime_ownership.py}.
- README.md, THIRD_PARTY_NOTICES.md, docs/BUILDING.md, docs/ARCHITECTURE.md,
  docs/core-runtime-migration.md, docs/dependency-inventory.json and this report.

No existing unrelated local change was reverted or committed.
