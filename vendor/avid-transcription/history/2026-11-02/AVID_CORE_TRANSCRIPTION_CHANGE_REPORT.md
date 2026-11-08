# AVID Core transcription changes and application handoff

Status: The review and fix cycle is complete. Final Antigravity review: complete, no findings. All 45 automated tests and the bundled catalog validation passed in the final clean snapshot. Application integration and the explicitly deferred checks below remain separate work.

AVID Core now has an additive Apple transcription implementation: verified direct model installation, local recognition and alignment, a shared timed-transcript contract, caption grouping, and SRT/WebVTT export. ATIV and EnCAP still need their own integration, user interface, persistence, packaging, and application validation. EnCAP additionally needs to replace its existing transcription stack safely.

## Source identity and scope

- Local Core repository: `/Users/tlothian/Documents/Projects/AVID Core`.
- Coding thread: `Choose free local transcription models`, `01a19f75-250e-7181-a21e-4e13098d5d73`, host `local`.
- Baseline HEAD: `7e124a3387349e38cc99e5db7e89a73cc23068ad`.
- External-review task: `desktop-transcription-20261102-e8b98234`. The same baseline and task ID are retained across rounds.
- Original requirements and baseline evidence: `/tmp/desktop-transcription-20261102-e8b98234/requirements.txt`, `initial-status.txt`, and `baseline.diff`.
- Review state: `/tmp/desktop-transcription-20261102-e8b98234/review/ec3e49efc695c9f8/671c6a95803b8d66b91f`.
- Final review: round 3, `20261102-203009-2fbae761`, `status: reviewed`, provider `antigravity`, `coverage: complete`, `validation: passed`, no findings.
- Final complete-review snapshot SHA-256: `0cac6c3611b74b7a65cb1ccae27bcc39a712c1602c31bf4c85c52d505451dfdd`.
- Preserved evidence: [final review result](review-evidence/round-3-result.json), [final review](review-evidence/round-3-review.md), [exact validation commands and captured results](review-evidence/final-tests.json), and [complete review file manifest](review-evidence/final-manifest.json).
- Frozen source: [AVID_CORE_TRANSCRIPTION_SOURCE.tar.gz](AVID_CORE_TRANSCRIPTION_SOURCE.tar.gz), SHA-256 `f4555615571d54b96d714be26caf0484f6049835065d7215820c3244bf761c5a`.
- Export manifest: [AVID_CORE_TRANSCRIPTION_SOURCE_MANIFEST.json](AVID_CORE_TRANSCRIPTION_SOURCE_MANIFEST.json). All 34 exported files matched the final reviewed file hashes, with zero mismatches. [Full source inventory](AVID_CORE_TRANSCRIPTION_SOURCE_INVENTORY.md).

The new Swift packages remain uncommitted working-tree content. The baseline commit alone does not contain them, and no published commit, tag, or package release is established by this report. The frozen archive makes the exact reviewed Apple source available without relying on later sibling-checkout changes. It contains the Apple components, catalog tooling, documentation, policy, and license, not the entire Rust repository, Git history, build products, or model weights. Both applications currently pin the existing Rust `avid-core` crate at revision `15f28236142c100d0a83bf19154ed6f9f5b44e75`; changing that Cargo pin alone does not import these Swift packages.

The checkout already contained substantial unrelated Rust/image/publisher fixes, Cargo and licensing changes, historical audit material, and `BUGFIX_REPORT.md`. Those pre-existing changes were recorded before transcription work. This report documents the transcription task and its targeted evidence; it does not certify every inherited working-tree change. Preserve that work when integrating or preparing a distributable source revision.

## Implementation changes

### Shared contract and model store

`apple/AVIDTranscription` is a Swift 6.0 package targeting macOS 14 or later. It provides the `AVIDTranscription` library and the `avid-transcription` model/caption command. It has no third-party Swift package dependencies.

| Source area | Implemented behavior |
| --- | --- |
| `Sources/AVIDTranscription/ModelCatalog.swift` and `Resources/models.json` | Validated catalog of exact model repositories, immutable revisions, artifact paths, sizes, SHA-256 digests, language capabilities, roles, and license notices. Installation identity includes the complete manifest so auxiliary tokenizer pins cannot collide. |
| `Sources/AVIDTranscription/ModelStore.swift` | Install, inspect, verify, import exact catalog-compatible local models, remove managed installations, and report progress. Size/hash verification precedes atomic publication. Partial files remain separate from usable installations. Per-model OS locks coordinate multiple stores/apps. `withInstalledModel` leases a verified installation through loading, inference, and unload. |
| `Sources/AVIDTranscription/HTTPModelDownloadTransport.swift` | Streamed HTTPS downloads, bounded expected size, HTTP Range resumption, restart when a server ignores Range, cancellation, and explicit truncated/oversized/error handling. |
| `Sources/AVIDTranscription/Transcript.swift` | Codable/Sendable transcript, segment, word, confidence, timing-method, recognition provenance, and separate alignment provenance records. Invalid timestamps are rejected. Untimed text is representable. Editing text invalidates affected word alignment rather than preserving stale times. |
| `Sources/AVIDTranscription/Providers.swift` | Recognition/alignment request and provider protocols, source offsets, local input validation, and structured progress. |
| `Sources/AVIDTranscription/Captioning.swift` | `CaptionOptions`, `CaptionWindow`, `CaptionCue`, grouping, trim/timeline projection, and SRT/WebVTT export. Missing word timing is an explicit failure; no evenly spaced word timing is invented. |
| `Sources/avid-transcription/Command.swift` | Model listing/install/verify/import/remove and caption-export commands, cache selection, progress, and cancellation. Display-oriented model output is not an application JSON service protocol. |

The default shared model cache is `~/Library/Application Support/AVID/Transcription/Models`. The store does not authorize deleting original imported folders, third-party application caches, or arbitrary user models. Hosts must retain the model lease until backend cleanup completes; returning an unleased directory and keeping mapped weights is not equivalent.

### Local inference and alignment

`apple/AVIDTranscriptionEngines` adds the provider implementations and `avid-transcribe` command. The documented supported engine configuration is Apple silicon, macOS 14 or later, Swift 6.3 or later, and the Apple Metal toolchain. An iOS entry in a package manifest does not establish a tested mobile product; mobile remains deferred.

| Source area | Implemented behavior |
| --- | --- |
| `Sources/AVIDTranscriptionEngines/AudioInput.swift` | Local AVFoundation decoding/resampling and chunked model input. Preserves initial silence of delayed audio tracks and validates decoded timing. Source offsets remain distinct from output-timeline projection. |
| `WhisperKitProvider.swift` | Full large-v3 and Turbo Core ML model loading from verified local folders, local tokenizer provisioning, word-timestamp recognition, control-token suppression, and normalized shared transcript output. |
| `FluidAudioProvider.swift` | Local Parakeet recognition and conversion of native token/word timings into the shared contract. |
| `QwenProviders.swift` | Local MLX Qwen recognition and optional forced alignment of original or edited text. Recognition and alignment provenance/capability remain separate. Qwen recognition alone is untimed. Temporary writable backend files do not mutate the verified model installation, and unlisted weight shards are excluded. |
| `LanguageInput.swift` | Normalizes trimmed regional/locale language hints to model language codes; explicit unsupported input is rejected rather than silently selecting English. |
| `ModelLifecycle.swift` | Awaited cleanup on successful, throwing, and cancelled model operations while retaining the original operation error. Provider cleanup completes before the host's model lease ends. |
| `Sources/avid-transcribe/Command.swift` | Recognition/alignment commands with explicit model/language selection, offline mode, local model import, source offset, and new JSON output-file creation. Existing output files are not silently overwritten. |

The engines use installed local files for inference. Normal model acquisition is anonymous direct download from the public upstream repositories and their HTTPS storage redirects. There is no AVID-hosted weight service, paid inference service, user API key, or audio upload in this implementation. Uncached installation still depends on upstream availability; installed models can operate offline.

Pinned engine dependencies are recorded in `apple/AVIDTranscriptionEngines/Package.swift` and `Package.resolved`:

| Dependency | Direct pin |
| --- | --- |
| Argmax `argmax-oss-swift` / WhisperKit | `9f99b5cb6a907730543823ad271b82532782a899` |
| FluidInference `FluidAudio` | `ee78635d23d52379117554ba72358b65a0612447` |
| `mlx-audio-swift` | `df2a2546705f50ca267037702a34cd63aa6e35a6` |
| `mlx-swift` | Exact version `0.33.0`; resolved revision is retained in `Package.resolved` |

### Model catalog and licensing

The bundled catalog has five model choices and 84 listed artifacts. Sizes below are download bytes, not runtime-memory requirements or an accuracy ranking.

| Model ID | Purpose | Download bytes | Upstream |
| --- | --- | ---: | --- |
| `whisper-large-v3` | Default quality recognizer with word timing | 3,093,084,631 | `argmaxinc/whisperkit-coreml`, plus separately pinned tokenizer assets |
| `whisper-large-v3-turbo` | Alternative Whisper recognizer | 1,622,295,995 | Same model publisher, plus tokenizer assets |
| `parakeet-tdt-v3` | Parakeet recognizer with native timings | 632,170,204 | `FluidInference/parakeet-tdt-0.6b-v3-coreml` |
| `qwen3-asr-1.7b-4bit` | Qwen recognition | 1,607,630,579 | `mlx-community/Qwen3-ASR-1.7B-4bit` |
| `qwen3-forced-aligner-0.6b-4bit` | Optional Qwen word alignment | 975,854,832 | `mlx-community/Qwen3-ForcedAligner-0.6B-4bit` |

Catalog maintenance is implemented by `script/update_transcription_catalog.py`; `script/test_transcription_catalog.py` provides offline checks. Publisher allowlists and immutable pins are deliberate inputs. The catalog generator verifies metadata/small-file identities without downloading multi-gigabyte weights. New model revisions require deliberate catalog regeneration, capability/notices review, and appropriate checks.

`apple/AVIDTranscription/MODEL_NOTICES.md` and `apple/AVIDTranscriptionEngines/THIRD_PARTY_NOTICES.md` track model and SDK obligations separately, including the adapted Whisper tokenizer code. Free local inference does not remove attribution or redistribution obligations. Model weights are not added to the Git repository or app bundle by default.

### Tests and documentation

The implementation adds core tests for catalog/model integrity, HTTP response/resume/cancellation behavior, manual/offline provisioning, shared-cache locking, transcript validation/editing, Unicode grouping, offsets/trims, and SRT/WebVTT. Engine contract tests cover local audio decoding, delayed audio, source offsets, language/alignment behavior, and local-file constraints. The final inventory and source manifest identify the exact files.

Documentation includes `apple/README.md`, `apple/VERIFICATION.md`, package notices, and additions to the root README. These explain host integration, model management, inference/alignment commands, timing semantics, maintenance, and verification limits. No downstream app UI, project migration, installer, or caption-rendering integration is established by those Core changes alone.

## Review and fix record

| Item | Trigger and disposition |
| --- | --- |
| Whisper control-token leakage | Real large-v3 smoke output initially contained `<|...|>` control tokens. The implementation enabled clean text decoding; a subsequent real-model output contained the expected text without those tokens. |
| Delayed/source-offset timing | Tests exercise delayed video audio and an AAC source offset of 12.5 seconds. Recognition and subsequent Qwen alignment retain the source offset without applying it twice. |
| Explicit model cleanup on failure/cancellation | Round-1 Copilot fallback identified that Whisper's sole `unloadModels()` call was on the success path. The watcher confirmed throwing/cancelled paths bypassed it and returned it to the coding agent. Explicit awaited cleanup was added for Whisper and Parakeet paths; success/error/cancellation regression checks passed, and the updated source was included in the completed second-round Antigravity review. No measured memory-leak claim is made. |
| Regional language tags | The coding agent found Whisper could fall back to English for a regional tag such as `pt-BR`. Adapter normalization, unsupported-input rejection, and explicit automatic-language-detection handling were added. Updated automated checks and real offline regional/automatic-language checks passed; the updated source was included in round 2. |
| Qwen alignment language metadata | Antigravity round 2 found that an explicit alignment language could be validated/used but omitted from the returned transcript when its original language was nil. The watcher confirmed the assignment path and sent the finding back. `QwenTranscriptOutput` now preserves normalized effective alignment language and normalizes the recognition fallback while retaining recognition/alignment provenance and source offsets. Two regression checks and a real nil-language/explicit `EN_us` alignment check passed; the latter returned `en`, the original text, and all 17 timed words. Final Antigravity review confirmed the defect resolved. |

Round 1 used a clean source snapshot with SHA-256 `9b701de239c181316502441feab395b60e39a2411c6c167ce5a38eb2f36e3313`. Its four validation commands passed: 24 core Swift tests, six engine contract tests, seven Python catalog tests, and catalog validation. Antigravity was interrupted near the configured 300-second review limit and returned no usable report. The automatic Copilot fallback reported partial coverage and the cleanup finding above. `result.json` records `status: incomplete`; this is not completed Antigravity verification.

Round 2 completed with Antigravity alone, `coverage: complete`, `status: findings`, and passing validation, using snapshot `047a33d7a62fe101e473ad7d4c581e437cf71ebb31c60fd0502ee50df5316091`. All 43 recorded automated tests passed: 24 core XCTest tests, 12 engine Swift Testing checks, and seven Python catalog tests, plus bundled catalog validation. Antigravity identified the Qwen metadata issue above. Its analysis was static over the supplied source and runner results; it did not independently rerun live model downloads, real inference, or benchmarks.

The coding agent received that verified finding, fixed it, added regression coverage, reran affected checks, and requested the third permitted Antigravity-only review with the same baseline/task ID. Round 3 completed with no findings and passing validation. Antigravity explicitly inspected the task-scoped packages, scripts, documentation, and the recorded check results, including the Qwen metadata fix. Its independent analysis was static; the neural smoke tests were run separately by the coding agent and are not represented as model executions by Antigravity. No unresolved finding or provider blocker remains in this Core cycle.

## Final automated validation

The review runner executed these commands in a clean source copy. Every command exited 0 without timing out. Runs started on November 3, 2026 UTC; the Core verification notes use the Mac's local November 2 date.

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/avid-review-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/avid-review-module-cache swift test --disable-sandbox --package-path apple/AVIDTranscription --scratch-path /tmp/avid-review-core-build
swift test --package-path apple/AVIDTranscriptionEngines --scratch-path /tmp/avid-review-engines-build -j 6
python3 script/test_transcription_catalog.py
python3 script/update_transcription_catalog.py --check
```

Results: 24 core XCTest tests, 14 engine Swift Testing checks, seven Python catalog tests, and validation of all five catalog models. The engine checks include awaited cleanup on success/error/cancellation, regional language normalization, explicit automatic detection, normalized Qwen output metadata/provenance, real audio decoding/resampling, and delayed-audio timing. [Captured results](review-evidence/final-tests.json) retain the exact argument arrays, timestamps, outputs, and exit codes.

## Functional validation and its limits

The coding agent installed and SHA-256-verified complete artifacts for Parakeet v3, full Whisper large-v3, Qwen3-ASR, and Qwen3 forced alignment in a temporary cache. Inference used offline mode against those local installations. The 5.511-second synthesized English sample was:

> Hello. This is a local transcription test. Every word should have a start and an end time.

| Backend | Recorded functional result |
| --- | --- |
| Parakeet v3 | 17 expected words; ordered native word times, 0.00–5.36 seconds; punctuation differs. |
| Qwen3-ASR plus forced alignment | 17 expected words; ordered aligned times, 0.00–5.28 seconds; recognition/alignment provenance retained separately. |
| Whisper large-v3 | 17 expected timed words; ordered native times, approximately 0.02–5.12 seconds; clean text after the control-token fix. |

Parakeet output exported to three SRT cues. JSON retained the individual timed words. Automated tests additionally check WebVTT and timeline mapping. Subsequent real offline runs covered regional `EN_us` input, automatic language detection, automatic alignment-language selection, and explicit alignment of a nil-language transcript. These are functional smoke tests, not a general accuracy benchmark or manually measured acoustic-boundary evaluation.

The initial 300-second Antigravity attempt failed to complete and the first fallback was partial; neither is counted as clean verification. The subsequent Antigravity passes completed, and the final automated checks have no failure or timeout. The following remain unrun or outside established verification: a representative multilingual/long-form corpus, acoustic timing ground truth, peak memory and comparative throughput, Turbo weight installation/inference, iPhone/iPad inference, Intel/older-macOS engine support, Windows/Linux engine support, ATIV/EnCAP UI and packaged-app integration, and animated caption burn-in. Antigravity did not rerun upstream network verification or real neural inference. Core's existing authenticated FFmpeg/ffprobe and immutable Recipe 7 release contracts are separate from these Swift packages and must not be weakened to integrate them.

## ATIV implementation handoff

- Project: `ATIV`, project ID `local-887f8ab0c347b4bff9b4facddcbeac16`, host `local`.
- Repository: `/Users/tlothian/Documents/Projects/ATIV`.
- Inspected HEAD: `25c245f49270b663a116ff7f823e977798d81491`; existing dirty changes must be preserved and rechecked at task start.
- Full task prompt: [ATIV_TRANSCRIPTION_IMPLEMENTATION_PROMPT.md](ATIV_TRANSCRIPTION_IMPLEMENTATION_PROMPT.md).

ATIV has no inspected production transcription implementation. Its native macOS UI uses a JSON process boundary to the Rust media engine; Windows/Linux use Qt. Add the shared transcription/model/caption behavior through a verified integration while preserving normal media export and existing macOS-13/Intel/Qt support. Its current Rust render request has no caption field. Timed preview and SRT/WebVTT must not be represented as animated video burn-in.

## EnCAP replacement handoff

- Project: `EnCAP`, project ID `local-c40b81d05a853ea819a699ed5c9f2df1`, host `local`.
- Repository: `/Users/tlothian/Documents/Projects/EnCAP`.
- Inspected HEAD: `2c20da6c6499484c1141c3902d03c9f6afcefba2`; workspace version `2.0.9`, with pre-existing dirty work to preserve.
- Full task prompt: [ENCAP_TRANSCRIPTION_IMPLEMENTATION_PROMPT.md](ENCAP_TRANSCRIPTION_IMPLEMENTATION_PROMPT.md).

Replace the EnCAP-owned Apple Speech, whisper.cpp, old WhisperKit helper, GGML catalog, provider/model discovery, and obsolete build/package paths with the new shared implementation. Do not retain those backends as a permanent hidden fallback. Preserve legacy `.encap` projects, stable segment/word IDs, speaker names, flattened unknown fields, schema migration, editing, exports, atomic saves/recovery, and source-edit behavior. Do not delete MacWhisper/Superwhisper caches or original user models. Old GGML weights are not equivalent to the new Core ML/MLX manifests.

EnCAP's current transcript times are episode-timeline values accumulated across source files. Core records original-source timings and optional boundaries. The integration must retain source identity/provenance and apply extraction, trim, source-order, and timeline offsets exactly once. Text edits must invalidate stale alignment. Neither Core's display-oriented model command nor its output-file transcription command is a drop-in replacement for EnCAP's JSON service contract; implement a deliberate thin bridge, with shared inference/catalog ownership remaining in Core.

## Shared integration decisions

Both apps currently support macOS 13 and Intel, and EnCAP also has existing transcription paths on Windows/Linux. The new engine stack's documented Apple-silicon/macOS-14 scope does not establish replacement parity. A separately bundled higher-minimum-OS helper may preserve base-app launch compatibility, but its actual packaging, resources, deployment target, and platform behavior require validation. EnCAP must extend the shared solution or obtain an explicit support-policy decision before a complete replacement can remove working support. Do not silently drop a supported target or disguise old inference as the completed new stack.

The Swift packages are nested beneath `apple`; there is no established root SwiftPM package. New tasks must verify the archive hash and consume its exact reviewed source through controlled package paths, or establish another reproducible dependency on the same reviewed files. The archive expands under `avid-core-transcription/`, keeping both packages as siblings beneath `apple`. An unmodified, attributed vendor snapshot can serve as a dependency if its manifest and update process remain explicit; do not create competing app-owned forks of the implementation. A floating branch or arbitrary neighboring checkout is not a production dependency strategy. No public package/source release is implied by this archive. Preserve the independent Rust dependency and authenticated media-runtime pins.

The two implementation tasks should share a source contract and model cache, not make competing copies of Core inference/catalog code. If a shared machine-readable bridge or renderer extension is needed, identify the common change and coordinate one owner before changing the shared checkout; keep each app's independent work moving. Do not let concurrent app tasks mutate the reviewed Core source underneath one another.

## Starting the two implementation threads

Documentation is ready. Start one new local coding thread in each project using its full prompt and this report as the authoritative handoff. Suggested titles are `Integrate AVID Core transcription in ATIV` and `Replace EnCAP transcription with AVID Core`. The parent task will create and track those threads. No ATIV or EnCAP application changes were made during this inspection and documentation task.

Each new thread should implement the authorized behavior, preserve existing changes, run appropriate validation, and use the existing Antigravity-first review/fix workflow. The prompts explicitly retain unsupported-platform, source-publication, rendering, and migration gaps instead of presenting them as completed work.
