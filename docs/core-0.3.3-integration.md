# Core 0.3.3 integration and capability audit

ATIV 0.2.9 integrates local AVID Core 0.3.3 at
`8e27a86ec106028d93130de35a35c0eeda7a9ce3`, replacing 0.3.2 at
`8296a9e623c6924c12e456b5fe9e7c10b59dfbde`. On November 10, 2026,
`git ls-remote` confirmed that GitHub HEAD and the latest published source tag
still identify 0.3.2. The owner explicitly selected integration of the local
0.3.3 commit with a checked-in source snapshot. Nothing was published.

Cargo.toml and Cargo.lock retain the exact Git identity. `.cargo/config.toml`
replaces only that source with 71 unmodified tracked files under
`vendor/avid-core/avid-core-0.3.3`. The snapshot includes Rust source, tests,
examples, benchmark, runtime specification, and license/provenance materials.
Its file-manifest SHA-256 is
`028cdd71f6a9ff716766b3ca677bf6f4e62c340aa9f6043041de691cf5e67e14`.
Cargo checksum metadata and a separate verifier protect the exported bytes and
matching manifest/lock/config identities. See [reproduction instructions](../vendor/avid-core/README.md).
Locked offline Cargo metadata also passed with an empty Git cache and only the
ordinary crates.io registry cache available; the Core manifest resolved to the
checked-in snapshot. Run Cargo from the ATIV root so its source configuration is loaded; existing shell/PowerShell build entrypoints explicitly pass the checked-in config and also work from another directory.

## Actual changes from 0.3.2

The upstream commit comparison contains no public API, Apple package, dependency
requirement, or FFmpeg runtime-contract change. Core 0.3.3 borrows probe-cache
lookup paths, retains one fingerprint/value per path, deduplicates identical
protected-path spellings while repeating publication checks, validates PNG opacity
by transformed rows/Adam7 passes, and retains bounded process tails with a deque.
The upstream benchmark changes separate cold/warm samples; this integration makes
no general speedup claim.

JPEG/PNG optimization, Apple transcription, forced alignment and caption export,
portrait square-pixel correction, and GIF/APNG fixes were already present in the
original 0.3.2 pin. Composition, preview, presets and staged media publication
were integrated even earlier. They are not new ATIV features in this change.

## Capability-by-capability disposition

| Core area | ATIV callers and disposition |
| --- | --- |
| FFmpeg processing and FFprobe inspection | `crates/ativ-engine/src/main.rs` delegates duration/image inspection, preview and video export to Core `Renderer`. `ativ-core` reexports the shared model. No competing media process runner or filter-graph implementation exists in ATIV. Retain the ATIV JSON process adapter. |
| Runtime builds and packaging | Core owns FFmpeg builds, recipe and tool pair. ATIV's `ffmpeg_runtime.py`/`platform_runtime.py` authenticate, stage and validate host packages; they do not build FFmpeg. The vendored `core_runtime.py` verifier is byte-identical to current Core and remains pinned by `runtime/core-acquirer.json`. |
| JPEG/PNG optimization and metadata | Core `optimize_image` already supplies lossless defaults, metadata controls, opacity validation and staged output. ATIV has no optimization product caller, implementation, ImageOptim runtime dependency or competing optimizer dependency to remove. Do not add an optimization feature. Core's transitive codec graph and nested licenses remain necessary for the linked crate. |
| WhisperKit | The helper delegates to Core `WhisperKitProvider`; model installation and local inference remain separate operations. No ATIV inference implementation remains. |
| FluidAudio Parakeet | Delegates to Core `FluidAudioProvider` with the pinned catalog and local model installation. No duplicate engine. |
| MLX Qwen ASR | Delegates to Core `QwenASRProvider`. Recognition text without word timings remains untimed; ATIV does not interpolate timestamps. |
| Forced alignment and word timing | Delegates to Core `QwenAlignmentProvider` and canonical `Transcript`/segment/word types. Editing invalidates alignment. Recognition-language support does not imply aligner-language support. |
| Caption grouping and SRT/WebVTT | Uses Core `CaptionBuilder`, `CaptionOptions`, `CaptionWindow`, and `CaptionExporter`. Removed copied default constants in the helper's partial JSON mapping; defaults now come from Core constructors. Explicit zero stays explicit and is validated by Core. |
| Artwork layouts, blurred backgrounds and flips | Core owns composition. `crates/ativ-core/src/model.rs` adapts ATIV's existing fitted artwork, sigma-40 background, software H.264/AAC, frame rate and bitrate policy. Square-padded artwork is a Core capability without an ATIV workflow to migrate. |
| Presets and previews | Both UIs obtain Core's 27 presets through the engine. Core renders preview pixels. Native authoring preview, appearance, persistence and controls stay in ATIV. UI bitrate choices are presentation policy. |
| Chapter sequences and timelines | Core exposes sequence/timeline rendering; ATIV has no chapter-sequence product or execution caller. No feature or duplicate timeline engine was added. Caption source-window projection already uses Core's caption timeline mapping. |
| MP4 rendering and animation | Core owns MP4 encoding, Simple/PerFrame graphs and GIF/APNG behavior. ATIV retains auto-mode selection for known static containers and conservatively preserves animation in unknown containers. Explicit modes remain available. |
| Model downloads and integrity | Core `ModelStore`, pinned catalog, resumable transport, SHA-256/size verification and cross-process leases own acquisition. ATIV calls `withInstalledModel` through load/inference/unload; inference never silently downloads missing weights. |
| Runtime provenance | Core validates original colocated runtimes. ATIV additionally validates split, platform-signed bundle derivatives, original archive identity, application/Core provenance and corresponding source. Keep these host checks before `MediaTools::from_paths`; original complete packages already use `from_core_directory`. |
| Cancellation and progress | Core owns media children, provider cleanup, model leases, process progress and staged media outputs. ATIV owns task/signal forwarding, bounded IPC, UI throttling and shutdown coordination. These responsibilities are complementary. |
| Diagnostics and output safety | Core supplies structured errors, bounded stderr and safe media publication. ATIV maps errors to its existing protocol/private logs, protects app/tool/project paths, serializes workers, and safely publishes transcript documents and sidecars. Authenticated update verification remains separate. |

## Necessary host implementations retained

* `artwork.rs` chooses the existing automatic playback policy. Core has no public
  static-container classifier with equivalent behavior; its private input sniffing
  chooses decoder options, not ATIV's automatic freeze/animate policy.
* `media_tools.rs` and the packaging adapters authenticate signed/split application
  layouts that Core's original-runtime loader does not cover. Removing these checks
  would weaken runtime acquisition and provenance. The old Core handoff suggesting
  their removal predates this authenticated packaging contract.
* `worker.rs` uses `fs2` for cancellable cross-process/multi-window serialization;
  Core requires callers to serialize writers. `sha2` has live runtime-integrity and
  worker-identity callers. No redundant dependency removal was justified.
* The transcription bridge applies supported Core segment replacement in a batch
  and rebuilds the transcript once. Repeated whole-transcript edits would copy the
  complete array for every edit. Existing equivalence, provenance and cancellation
  tests cover this adapter.
* Model disk-size display remains a bounded regular-file inventory. Core exposes
  verified installation APIs but no equivalent UI byte-count query. Presence/size
  display never substitutes for model verification.
* ATIV document schemas, process clients, source binding, UI, word-highlight
  authoring preview and animated-caption presentation remain ATIV-owned. Core does
  not burn animated captions into MP4, and ATIV's existing export does not claim it.

## Source, runtime, platform and license boundaries

The Apple archive now identifies the same local Core commit. Its SHA-256 is
`4234053bad548df25c68949265cb32b4052091856e6da6ad2d0710640f8f67ae`.
All 34 exported files are individually pinned; only the root README differs from
the previous archive. Apple implementation, model catalog, SDK locks, licenses and
minimum platforms are unchanged. The original historical source audit stays
associated with its historical archive, not this refresh.

FFmpeg remains independently pinned to version 9.0.1, recipe 7 and the six
per-platform releases from run `38185320964` in `runtime/platform-runtimes.json`.
Explicit legacy `ffmpeg-9.0.1-r7.1` selection remains authenticated. The Core runtime
specification hash is still
`0d5a568452cd28e79022d933e642731b8f86183a4c474ce83b97b49ac7900763`.
Neither pin set, source verifier, acquisition trust, update signatures nor
fallback behavior changed.

Core Rust declares Rust 1.85; ATIV's workspace requires Rust 1.88 and the existing
local toolchain policy selects 1.99.1. Source-built image codecs require a target
C compiler and CMake; Core's scalar libjpeg-turbo build does not require NASM.
ATIV's native macOS UI remains macOS 13+, while the optional inference helper
requires Apple silicon, macOS 14+, Swift 6.3+ and the Xcode Metal toolchain. The
contract-only Swift package requires Swift 6/macOS 14. Intel macOS, macOS 13 and
Windows/Linux do not acquire Apple inference support. Windows 10 1809+ and current
Linux x86_64/ARM64 media workflows retain their existing requirements.

Source-built TurboJPEG/OxiPNG arrived with Core 0.3.2. Their original native codec
texts remain in the source snapshot and package license collector; top-level
notices now explicitly acknowledge the Independent JPEG Group. Core's GPL license,
model notices and independent SDK terms remain preserved. No dependency graph
changes beyond Core's source/version identity were needed.

## Validation on native macOS ARM64

Logs are retained in `/tmp/ativ-core-033-20261110-01/`; Swift transcription logs
also remain under `build/transcription-*`. Commands run from the ATIV root unless
otherwise stated. These are development/test builds, not notarized distributables.

| Command/check | Exact result |
| --- | --- |
| `cargo test --workspace --locked` | 44 passed, 5 ignored benchmarks, 0 failed. Initial restricted run had three updater loopback socket permission errors; native rerun passed without code changes. |
| `cargo test -p ativ-engine --locked --test protocol --test probe_cache` | 7 passed; includes identity, same-size/mtime-preserving replacements, unknown-duration caching, cloned renderers and cancellation. |
| `cargo check --workspace --locked` | Passed. Full locked/offline metadata resolution from `/tmp` with explicit absolute `--config` also passed. |
| `cargo clippy --workspace --locked -- -D warnings` | Passed. |
| `cargo fmt --all -- --check` | Passed. |
| `cargo +1.99.1 test --locked --all-features --offline` in an unchanged temporary copy of the Core snapshot | 109 passed, 10 opt-in native/runtime tests ignored, 0 failed; includes PNG/Adam7, cache capacity/identity, fresh output protection, process capture and lifecycle tests. Direct dependency `--all-features` selection is unsupported by Cargo, so this used a standalone copy; all copied bytes/modes remained unchanged. |
| `python3 -B script/verify_core_source.py` / `script/test_core_source.py` | 71 files verified; 12 integrity/configuration regressions passed. |
| `python3 -B script/test_runtime_ownership.py` / `script/test_platform_runtime.py` | 3 and 7 tests passed. |
| `python3 script/test_transcription_runtime.py` | 10 passed. |
| `build/release-tools/bin/python -B -m unittest discover -s script -p 'test_*.py'` | 87 passed. Bare system Python initially ran 56 successfully with 2 import errors because `cryptography` was absent; the existing pinned release-tools environment resolved those errors. |
| `python3 -B script/dependency_inventory.py --check` | Passed after regenerating the locked inventory. |
| `script/test_core_rendering.py --engine target/debug/ativ-engine --runtime RUNTIME --target macos-arm64 --report build/core-0.3.3/native-rendering.json` | 58 native groups passed, 0 failed, 0 simulated. Includes attestation, presets/previews, decoded Simple/PerFrame parity, portrait SAR, GIF/APNG behavior, safe outputs, cancellation, cleanup and serialization. |
| `script/test_ffmpeg_runtime.py --engine target/debug/ativ-engine --runtime RUNTIME --target macos-arm64` | Passed staged authentication/tampering/missing-tool checks and media contract: 27 presets, 20 previews, 4 exports, errors and child cleanup. |
| `env ATIV_ENGINE_PATH=ENGINE ATIV_TEST_MEDIA=MEDIA swift test --package-path platform/macos --scratch-path build/core-0.3.3/swift-app-tests` | Native app built; 49 passed, 0 failed/skipped, using newly staged Core-0.3.3 engine and authenticated runtime. |
| `swift test --package-path build/transcription-core/apple/AVIDTranscription --scratch-path build/transcription-core-tests` with local Swift cache options | 32 passed. |
| `swift test --package-path build/transcription-core/apple/AVIDTranscriptionEngines --scratch-path build/transcription-engine-tests --force-resolved-versions` with local Swift cache options | 14 Swift Testing adapter tests passed, including native audio decoding. |
| `swift test --package-path platform/transcription-helper --scratch-path build/transcription-helper --force-resolved-versions --filter ProtocolTests` with local Swift cache options | Helper built; 10 passed. New test covers Core-derived caption defaults and explicit zero. Initial compiler-cache restriction and missing `try` in the new test were resolved. |
| Catalog tests / `update_transcription_catalog.py --check` in acquired source | 7 passed / passed; no weight downloads. |
| Direct built-helper smoke | Passed five-model catalog, source-window/timeline caption mapping, SRT/WebVTT and explicit offline missing-model rejection. Mach-O arm64, minimum macOS 14.0. |
| `git diff --check` | Passed. |

`RUNTIME` is
`build/core-acquisition/platform-ffmpeg-9.0.1-r7-macos-arm64-run38185320964/macos-arm64/avid-ffmpeg-9.0.1-r7-macos-arm64`.
`ENGINE` is the absolute path to `build/core-0.3.3/native-engine/ativ-engine`;
`MEDIA` is `build/core-0.3.3/swift-media`, generated by `create_smoke_media.py`.
Transcription Swift commands set `MACOSX_DEPLOYMENT_TARGET=14.0`, local
Clang/Swift module caches and existing SwiftPM cache/config/security paths, with
`--disable-sandbox`; native compiler access was needed for Metal's system cache.
Upstream MLX compiler warnings remain unchanged.

Full model inference/accuracy was not run because the configured cache contains
no model weights; no multi-gigabyte downloads were made. Intel macOS, Windows and
Linux were not natively built or runtime-qualified in this task. Minimum-OS runtime,
interactive accessibility, notarization and distributable package qualification
were not performed. No distributable was requested or published.

The weekly smoke workflow and all pre-existing signing/notarization changes were
preserved. The already edited build guide received the Core identity/prerequisites update; the already edited macOS package script received only explicit Cargo config selection for directory-independent builds. No CI trigger, update signature, protection, release or publication
policy was changed by this integration. No commit or push was made.

The standard independent Gemini audit runs after this implementation and the
checks above. Its exact source hash, attribution and any Codex repairs are recorded
with task `ativ-core-033-20261110-01`, baseline
`4348faa423a25f6f6add3f70128376173d7b9a21`, outside the repository. Earlier Core
or ATIV reports do not substitute for this source audit.
