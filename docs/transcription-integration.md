# Local transcription integration

ATIV adds optional local transcription to the native macOS application. The
existing image/audio video renderer remains independent. Transcript editing,
word-highlight authoring preview, and SRT/WebVTT sidecars are separate from MP4
rendering: this implementation does not burn captions into exported video.

## Source identities and compatibility

The Rust media dependency remains AVID Core 0.3.1 at
`15f28236142c100d0a83bf19154ed6f9f5b44e75`. Its authenticated FFmpeg runtime pin
is unchanged. The Apple transcription implementation is a separate, unmodified
dependency, supplied by the reviewed source archive in
[`vendor/avid-transcription`](../vendor/avid-transcription/README.md).

- Archive SHA-256: `f4555615571d54b96d714be26caf0484f6049835065d7215820c3244bf761c5a`.
- Upstream baseline: `7e124a3387349e38cc99e5db7e89a73cc23068ad`; that commit
  alone does not contain the new Apple packages.
- Reviewed source snapshot SHA-256:
  `0cac6c3611b74b7a65cb1ccae27bcc39a712c1602c31bf4c85c52d505451dfdd`.
- Upstream review: Antigravity round 3, task
  `desktop-transcription-20261102-e8b98234`, complete with no findings. This is
  upstream evidence, not verification of ATIV's application integration.

`script/transcription_runtime.py acquire` verifies the archive and every exported
file against its manifest, then materializes the dependency at
`build/transcription-core`. Both nested Swift packages stay together beneath
`apple/`. A sibling development checkout, floating branch, or unpublished Git
revision is not used to acquire transcription source. The archive is a dependency
snapshot, not an app-owned fork; refresh it deliberately with a new reviewed
archive, manifest, hash, dependency lock, notices, and validation evidence.

| Target | Existing video workflow | New local inference |
| --- | --- | --- |
| Apple silicon, macOS 14 or later | Retained | Separate bundled helper |
| Apple silicon, macOS 13 | Retained | Unavailable; capability explanation shown |
| Intel, macOS 13 or later | Retained | Unavailable; no Apple silicon helper packaged |
| Windows x64/ARM64 | Retained Qt workflow | Not implemented by these Apple engines |
| Linux x64/ARM64 | Retained Qt workflow | Not implemented by these Apple engines |
| iPhone/iPad | No ATIV product established here | Deferred |

The base UI package and application plist retain macOS 13 support. They do not
link either higher-minimum-OS transcription library. Only
`platform/transcription-helper` links `AVIDTranscription` and
`AVIDTranscriptionEngines`; it requires Swift 6.3+, the Xcode Metal toolchain,
Apple silicon, and macOS 14+. Unsupported platforms do not select a cloud service
or another recognition implementation.

## User workflow

Choose audio in Source Media, then use the transcription section. Model management
and recognition/alignment have their own operation status and cancellation.

1. Select a recognizer. Full Whisper large-v3 is the default; Turbo, Parakeet, and
   Qwen ASR are alternatives. Inspect download bytes, current disk/partial bytes,
   and the model's notice. These sizes do not describe runtime memory or rank
   model accuracy.
2. Install or resume the selected model, or import an exact catalog-compatible
   local folder. Verify checks its contents; Remove only removes installations
   managed by the shared store. Presence in the selector is distinct from a full
   integrity check, which also runs before inference.
3. Recognize the selected recording locally. An optional language hint is passed
   to Core; blank permits supported automatic detection. Recognition uses an
   installed model and does not silently download missing weights or tokenizers.
4. Review and edit transcript segments. Applying a text correction invalidates
   affected word timings. Realign runs the Qwen forced aligner on the existing
   text rather than recognizing the words again. Qwen ASR alone produces untimed
   text and cannot create timed captions until supported alignment succeeds.
5. Adjust caption word/character limits, duration, pause grouping, source trim,
   and output timeline offset. Generate captions to inspect the word-highlight
   preview and export SRT or WebVTT. Missing timing is reported explicitly;
   evenly spaced word boundaries are not invented.
6. Save a transcript document to preserve text, words, provenance, source identity,
   and caption preferences; reopen it with the matching recording to continue.

Installed models use the shared default cache
`~/Library/Application Support/AVID/Transcription/Models`, so ATIV and EnCAP can
share one verified installation. The model catalog supplies complete revision and
artifact identities, exact sizes and SHA-256 digests, recognition/timing languages,
and licenses. Downloads are anonymous HTTPS requests to the allowed upstream
repositories and storage redirects. No account, API key, hosted inference, audio
upload, telemetry service, or AVID-hosted model service is added. Uncached models
still require upstream availability; installed models can be used offline.

Core owns resumable partial downloads, verification, atomic installation, model
import, and cross-process OS locks. ATIV holds `withInstalledModel` through loading,
inference, and backend unload. Removal therefore reports busy while another app
or operation has a model lease. It does not delete an imported original folder,
another application's cache, or unknown directories. Cancellation waits for actual
helper exit; a running Core ML/Metal kernel may finish before cancellation is
observed.

Changing the selected recording stops work tied to that recording while catalog
and model-cache operations continue. Unchanged editor updates retain the caption
preview; reverting a text draft clears its unsaved state only when no other edits
or caption-setting changes remain.

## Persistence, timing, and process boundary

The app's version-1 document envelope stores the canonical Core transcript JSON,
a source SHA-256/byte count with an original-path hint, and separate caption
preferences. File content identifies the source; its path alone does not. A move
can retain identity, while replacing audio at the same path does not. A retained
transcript for different audio cannot silently become that recording's alignment.
Malformed or future-version documents are rejected. The document size limit is
32 MiB.

Save/export uses a private staging file in the destination directory. Publication
without replacement fails if a destination exists; replacement requires an
intentional user action. Media source aliases and hard links are rejected as
destinations. Original media and imported model folders are never the transcript
storage location. Pending edits and changed source selection are tracked rather
than silently applied to another recording.

Core's transcript words retain original-source seconds and timing provenance.
Recognition model and alignment model identities stay separate. Caption windows
map source time through trims and output timeline offsets without modifying the
recognition record. Delayed audio and extracted-source offsets belong to the
source clock; layout must not apply them a second time. Grouping preferences and
preview appearance are not recognition or timing evidence.

The native client launches
`Contents/Helpers/ATIVTranscriptionHelper.app/Contents/MacOS/ATIVTranscriptionHelper --request PATH` with
individual arguments and no shell. The private request contains paths and JSON,
not uploaded audio. Version-1 newline-delimited JSON events report progress,
results, or errors. The client drains both pipes, bounds diagnostics and response
size, propagates cancellation, and waits for process termination. The helper
validates, edits, groups, and exports through the canonical Core types rather
than reimplementing them in the macOS-13 UI. Source generations and operation
identities reject superseded results and progress. App termination and update
replacement drain active work before files can be replaced.

## Packaging and notices

Apple silicon builds stage a nested `Contents/Helpers/ATIVTranscriptionHelper.app`.
Its `Contents/Resources` holds SwiftPM resource bundles, Metal resources,
source/SDK/model notices; `Contents/Frameworks` holds required non-system
libraries, including the Swift compatibility runtime. The outer application's
`Contents/Resources/transcription-package.json` records the finalized helper
payload after nested signing and before the enclosing application is signed.
`script/transcription_runtime.py` validates payload hashes, Mach-O architecture,
deployment target, catalog discovery, and a relocated helper catalog invocation
with empty PATH and a fresh home/cache. Native code is signed before the enclosing
application; the payload record is refreshed after signing. Model weights are
optional post-installation downloads, not multi-gigabyte bundle resources.

SDK terms and model-weight terms are separate. Preserve the bundled Core license,
`MODEL_NOTICES.md`, `THIRD_PARTY_NOTICES.md`, resolved Swift dependency identities,
and original dependency license texts. Whisper retains combined MIT/Apache-2.0
notices; Parakeet retains NVIDIA/FluidInference attribution and CC-BY-4.0 model
obligations; Qwen converted models retain Apache-2.0 notices and conversion
provenance. Free inference does not remove redistribution obligations.

## Shared renderer work required for burned-in captions

The missing behavior is an AVID Core composition layer that draws timed caption
cues and word emphasis into video frames. The reviewed Apple packages produce
caption data and subtitle text. The pinned Rust `avid_core::RenderRequest` accepts
media, settings, output, and protected paths; neither it nor `RenderSettings`
accepts captions. ATIV's `crates/ativ-core/src/model.rs` currently creates
`Input::Single`, `Composition::Fitted`, and software H.264. No ATIV filter graph or
second media runtime is introduced to bypass this boundary.

A separately scoped shared-Core implementation should provide:

- A versioned optional `CaptionTrack` in the shared render request, carrying
  source/clip identity, canonical timed words or validated projected cues, and
  explicit source trim/output timeline mapping. Untimed text must fail rather
  than acquire estimated word boundaries.
- A separate `CaptionStyle` contract for font/resource identity, size, safe-area
  position, line wrapping, foreground/background/highlight colors, and supported
  word-emphasis behavior. Font files and output paths must enter existing source
  protection and staging rules.
- Core-owned compositing/filter construction and resource validation, retaining
  fitted/square-padded composition, flips, presets, audio, render modes,
  cancellation, and successful-publication-only completion. Optional absence must
  preserve existing non-captioned output and protocol compatibility.
- A documented Swift-to-Rust caption interchange that preserves Unicode text,
  missing timing, recognition/alignment provenance, and the source clock exactly
  once. Additive engine arguments/events should expose verified capability;
  unsupported combinations must fail explicitly.

Expected shared paths are AVID Core `src/model.rs`, `src/renderer.rs`,
`src/command.rs`, Apple caption contracts, and their tests. After a new immutable
Core source identity is available, ATIV would update `crates/ativ-core/src/model.rs`,
engine request parsing, its client/UI, protected resources, packaging notices,
and acceptance evidence. EnCAP should consume that same shared contract.

Validation must inspect actual exported MP4 frames before, during, and after word
boundaries against timed golden fixtures. Include delayed audio, nonzero source
offsets, trim-crossing words, output offsets, silence, punctuation, Unicode/CJK,
long material, frame-rate quantization, font fallback, missing resources,
cancellation, staged replacement, and ordinary non-captioned regressions. Build
and launch each artifact natively on its target. Subtitle export or an editor
highlight alone cannot establish video burn-in.

## Validation record and remaining limits

Application validation and the Antigravity-first review are recorded by the
integration task. Upstream's 45 automated checks and short real-model smoke
record are retained in the vendored change report; they must not be counted as
ATIV-specific checks. Run the commands in [building](BUILDING.md) and
[testing](TESTING.md), plus the acquired Core package/catalog and helper tests.

Remaining qualification includes native Intel/macOS-13 behavior, Windows/Linux
regressions on their own runners, representative-language and long-form accuracy,
acoustic boundary error, peak memory, and any installed-model/packaged-inference
checks not explicitly recorded by this task. A short known-English sample is
functional smoke evidence, not an accuracy benchmark. Six-platform automation
and nonblocking development policy remain in force. No release publication or
authenticated update-feed change is authorized by this integration.
