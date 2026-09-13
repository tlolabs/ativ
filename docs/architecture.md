# A.V.I.D. native architecture

A.V.I.D. 0.2 is one shared Rust media engine with three independent native desktop presentations.

```text
SwiftUI/AppKit ─┐
WinUI 3/C# ─────┼─ newline-delimited typed process protocol ─ avid-engine ─ FFmpeg/ffprobe
GTK 4/Adwaita ──┘                                      │
                                                avid-core library
```

The process boundary is deliberate. It contains no unsafe code, gives each UI natural asynchronous process APIs, keeps crashes and cancellation isolated, and lets each package place the engine and media tools together. Native applications send paths as individual process arguments (never shell command strings), consume JSON events from standard output, and send `cancel` on standard input.

`avid-core` owns presets, validation, source resource limits, image composition, probing, FFmpeg argument construction, progress normalization, cancellation, staging, and publication. Platform applications own only file panels, drag and drop, menus, appearance, accessibility, window lifecycle, and presentation state.

## Data and compatibility

The Python application has no project/document format, database, preference file, credentials, or saved preset format. Its user-data contract consists of user-selected source media and MP4 output. The replacement does not modify source media. A completed output is encoded beside the destination and published only after FFmpeg succeeds. Cancellation or failure removes staging data and preserves a prior output.

No settings migration runs because there are no legacy settings to migrate. Native platform window restoration uses each operating system's standard facilities and cannot affect the preserved Python application.

## Protocol stability

The engine protocol is append-only within major version 0.2. Unknown JSON fields and event types must be ignored by clients. Current events are `tools`, `presets`, `probe`, `stage`, `progress`, `complete`, and `error`. Errors include a stable machine-readable `code` and a plain-language `message`. File paths never appear in events unless a future protocol version explicitly documents them.

Cancellation is the UTF-8 line `cancel\n`. The engine terminates and reaps FFmpeg, deletes its staged output, and exits with status 130.

## Platform baselines

- macOS 12 or later, Apple Silicon and Intel. The legacy package did not declare a minimum; macOS 12 is the lowest practical baseline for the SwiftUI and concurrency APIs used here and remains compatible with currently supported Intel Macs.
- Windows 10 version 1809 or later, x64 and ARM64, matching the Windows App SDK 2.4 support floor.
- Linux distributions providing GTK 4 and libadwaita 1.5 or later. Release packages target current Ubuntu/Fedora-family runtimes and bundle the Rust engine plus FFmpeg tools.

## Security boundaries

- Inputs are local files and FFmpeg protocols are restricted to `file,pipe`.
- Source images are capped at 32,768 pixels per axis and 50 megapixels before decode.
- Output is capped at 8,192 pixels per axis and 33,177,600 pixels.
- FFmpeg and ffprobe are launched without a shell and with standard input disabled.
- Packaged tools are version-checked before use.
- No telemetry or automatic diagnostic upload exists.
- Raw tool output remains local and is never presented as the primary user-facing error.
