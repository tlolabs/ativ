# ATIV architecture

ATIV is a native desktop application backed by one shared Rust media engine. The app combines artwork and an audio track into an MP4 without sending either file to a service.

```text
SwiftUI/AppKit ─┐
WinUI 3/C# ─────┼─ process protocol ─ ativ-engine ─ ativ-core ─ avid-core ─ FFmpeg/ffprobe
GTK 4/Adwaita ──┘                                  adapter
```

## Components

- `avid-core` in the sibling `AVID Core` repository owns presets, validation, probing, media commands, previews, rendering, progress, cancellation, staging, and publication.
- `ativ-core` is a thin ATIV compatibility adapter: it maps the standalone request to single-track, fitted, software H.264 settings, presents path-free errors, and retains ATIV application version identity. It contains no media implementation.
- `ativ-engine` exposes that functionality through a stable newline-delimited JSON process interface.
- `platform/macos`, `platform/windows`, and `platform/linux` provide native file pickers, drag and drop, accessibility, window management, and each platform’s visual language.

The process boundary keeps media work isolated from the user interfaces. Native clients pass file paths as individual process arguments, not shell strings; receive JSON events on standard output; and send `cancel` on standard input when a render must stop. A shared cancellation token now also covers tool validation, probes, and previews. Native worker queues and preview-generation guards remain unchanged.

## Render lifecycle

1. ATIV validates the artwork, audio, dimensions, and destination.
2. It probes the audio duration and builds the image composition.
3. FFmpeg renders to a staged file beside the requested destination.
4. After a successful render, ATIV atomically publishes the staged file.

Only the `complete` stage means publication succeeded; progress can reach 1 before publication. Cancellation after completion cannot undo a file.

Cancellation and failure remove `.avid-*` staged data and leave an existing destination untouched. Source files are never modified.

## Engine protocol

The engine protocol is append-only within the 0.2 major line. Clients must ignore event types and JSON fields they do not recognize. Current events are `tools`, `presets`, `probe`, `stage`, `progress`, `complete`, and `error`.

Errors retain `cancelled`, `invalid_input`, `media_tools_unavailable`, `media_tool_failed`, and `io_error`. Shared timeout, capture-limit and fallback failures map to `media_tool_failed`; structured process and OS causes stay in the local log. Errors contain a stable machine-readable `code` and a plain-language `message`. Paths are supplied as command arguments and are not emitted in events. To cancel a render, write the UTF-8 line `cancel\n`; the engine stops FFmpeg, removes its staged output, and exits with status 130.

## Safety boundaries

- Inputs are local files; FFmpeg protocols are limited to `file,pipe`.
- Source images are limited to 32,768 pixels per axis and 50 megapixels.
- Output is limited to 8,192 pixels per axis and 33,177,600 pixels.
- FFmpeg and ffprobe run without a shell and with standard input disabled.
- Packaged media tools are version-checked by avid-core before use; mismatched version identifiers are rejected. Each platform/architecture uses one approved 9.0.1 pair for all modes. The shared crate supplies no binaries.
- Diagnostics remain local; ATIV has no telemetry or automatic diagnostic upload.

## Platform support

- **macOS:** macOS 12 or later, Apple Silicon and Intel.
- **Windows:** Windows 10 version 1809 or later, x64 and ARM64.
- **Linux:** GTK 4 and libadwaita 1.5 or later on current Ubuntu- and Fedora-family distributions.
