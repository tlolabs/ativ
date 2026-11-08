# ATIV local transcription helper

This optional Apple silicon/macOS 14 process isolates AVID Core's Swift 6.3
inference dependencies from ATIV's macOS 13/Intel UI. The source archive and
per-file manifest under `vendor/` supply the exact reviewed shared packages;
`script/transcription_runtime.py acquire` materializes them at
`build/transcription-core`. The shared implementation is consumed unchanged,
including its model catalog, model store, provider cleanup and caption builder.

`ATIVTranscriptionHelper --request /absolute/path/request.json` processes one
request and exits. Requests are bounded to 64 MiB. Stdout is newline-delimited
JSON; upstream SDK output is redirected to stderr. The parent must drain both
pipes, retain a bounded diagnostic tail, treat a nonzero exit as failure and
await exit after cancellation. SIGINT and SIGTERM cancel the owning Swift task;
an active Core ML/Metal kernel may finish before cancellation is observed.
The task retains its shared-cache lease until provider cleanup finishes.

Every response includes `event` and `protocolVersion: 1`. Events are `progress`
(`message`, optional `fraction`), `result` (fields below) or `error` (`message`).
Individual responses are limited to less than 15 MiB; oversized results fail
explicitly. Progress is throttled to approximately ten events per second.

All requests contain `operation`. Optional `cachePath` selects a local cache for
isolated tests; normal application operation omits it and uses Core's shared
`~/Library/Application Support/AVID/Transcription/Models` location.

| Operation | Request fields | Result fields |
| --- | --- | --- |
| `catalog` | none | `models`, `defaultModelID`, `cachePath` |
| `install`, `verify`, `remove` | `modelID` | `message` |
| `import` | `modelID`, `localPath` (absolute catalog-compatible folder) | `message` |
| `transcribe` | `audioPath`, optional `modelID`, `language`, `sourceOffset` | canonical `transcript` |
| `align` | `audioPath`, canonical `transcript`, optional `modelID`, `language`, `sourceOffset` | canonical `transcript` |
| `validate` | canonical `transcript` | canonical `transcript` |
| `edit` | canonical `transcript`, either zero-based `segmentIndex` + replacement `text`, or `edits: [{segmentIndex, text}]` | canonical `transcript` |
| `captions` | canonical `transcript`, optional `captionOptions`, `captionWindow` | canonical `cues`, `srt`, `webVTT` |

Catalog model entries include `id`, `displayName`, `role`, `engine`, `revision`,
`installationID`, `downloadBytes`, `diskBytes`, `partialBytes`, `installed`,
`verificationState`, `license`, `recognitionLanguages` and `timingLanguages`.
`installed` means Core's cheap presence check found the current installation;
`verificationState: "notChecked"` makes clear that listing is not a hash audit.
Explicit verification, installation/import, and every inference operation verify
the exact files. Disk counts cover listed regular files in this exact revision;
they exclude unknown files, other revisions, and filesystem allocation overhead.

`captionOptions` accepts `maximumCharacters`, `maximumWords`,
`maximumDurationSeconds`, and `maximumPauseSeconds`. `captionWindow` accepts
`sourceStartSeconds`, optional `sourceEndSeconds`, and `timelineStartSeconds`.
Defaults come from Core. The original transcript clock is never changed by
caption projection. Missing word times produce an error; Qwen recognition alone
therefore needs explicit alignment before caption export.

Inference is offline-only: a missing or corrupt installed model fails and never
triggers an implicit download. Model acquisition is a separate deliberate
operation. Full Whisper large-v3 is the default recognizer; the default aligner
is `qwen3-forced-aligner-0.6b-4bit`. Editing uses Core's correction contract to
invalidate affected word timing and clear stale alignment provenance. Alignment
uses corrected text without another recognition pass.

The helper writes no transcript, subtitle or source-media file. The host owns
versioned document persistence, source identity, intentional replacement and safe
publication. The helper does not burn captions into video.

Batch edits use one request and return one completed transcript; indices must be
unique and in range. A failed or cancelled batch returns no partial transcript.
Existing single-edit requests remain supported. Package the updated helper with
the UI when using batched corrections.
