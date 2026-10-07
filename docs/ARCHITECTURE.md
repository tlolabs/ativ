# ATIV architecture

ATIV is a native desktop application backed by one shared Rust media engine. The app combines artwork and an audio track into an MP4 without sending either file to a service.

```text
SwiftUI/AppKit (macOS prod) ─┐
Qt 6 (Windows/Linux)        ├─ JSON process protocol ─ ativ-engine ─ ativ-core ─ avid-core ─ FFmpeg/ffprobe
Qt 6 (macOS arm64 reference) ┘
```

## Components

- The pinned `avid-core` Cargo dependency owns presets, validation, probing, media commands, previews, rendering, progress, cancellation, staging, and publication.
- `ativ-core` is a thin ATIV compatibility adapter: it maps the standalone request to single-track, fitted, software H.264 settings, presents path-free errors, and retains ATIV application version identity. It contains no media implementation.
- AVID Core owns FFmpeg/ffprobe source selection, build configuration and native runtime qualification. ATIV acquires the pinned Core release and owns application packaging, signing and bundled runtime discovery.
- `ativ-engine` exposes that functionality through a stable newline-delimited JSON process interface.
- `platform/macos` remains the native production SwiftUI/AppKit UI. `platform/qt` owns the single Windows/Linux presentation, controls, and engine client; the internal Apple Silicon reference runs that same project. Platform adapters retain updater installation and filesystem differences.

The process boundary keeps media work isolated from the user interfaces. Native clients pass file paths as individual process arguments, not shell strings; receive JSON events on standard output; and send `cancel` on standard input when a render must stop. A shared cancellation token now also covers tool validation, probes, and previews. The shared Qt UI retains preview-generation guards, render cancellation and update exclusion.

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
- Packaged media tools are version-checked by avid-core before use; mismatched version identifiers are rejected. Each platform/architecture uses one Core-built 9.0.1 pair for all modes. ATIV verifies the authenticated release, preserves Core's original metadata and records the hashes after platform signing.
- Diagnostics remain local; ATIV has no telemetry or automatic diagnostic upload.

## Platform support

- **macOS:** macOS 13 or later, Apple Silicon and Intel.
- **Windows:** Windows 10 version 1809 or later, x64 and ARM64.
- **Linux:** Qt 6 Widgets over X11/Wayland, packaged in AppImages for x64 and ARM64. The internal Mac arm64 Qt build is for development only.

## Application distribution boundary

`ativ-update` is an ATIV-only Rust executable; it has no avid-core dependency and never receives media paths. The shared Qt UI calls it asynchronously on Windows/Linux; the platform update client chooses portable Windows replacement via `ativ-portable-update.exe` or Linux AppImage replacement. The internal Mac reference has no updater binary and disables update checks by design. macOS production loads Sparkle through a small Objective-C bridge. Native UI confirmation and platform installers own the installation step. See [release architecture](RELEASING.md).

Appearance and media workflow state are shared by the Qt implementation on Windows/Linux/reference Mac. Windows and macOS JSON preferences retain their paths; Linux imports legacy INI values into a JSON store without deleting the INI. Production macOS keeps its own native stores. An audio probe for an older selection cannot replace the current duration. Native process clients keep pipes drained and pass arguments without a shell. Closing or quitting an active render requests safe engine cancellation.

`assets/icons` owns artwork; `generate_icons.py` converts it into tracked native resources. Distribution identity and versions are generated from the workspace version plus the CI development build number. Stable/development feeds and application identities are separate.

Core 0.3.0 is pinned at `25d19098a22936638b0e2a70616083d929fe409c`, matching the published runtime build. Staging calls `MediaTools::from_core_directory` to validate the original Core package. Production calls `MediaTools::from_paths` after ATIV verifies its signed bundle against the pinned original metadata and signed binary hashes. This preserves platform signing without changing Core's original qualification records. `ativ-engine build-info` identifies the compiled source dependency; package provenance must match the compiled application version, including development versions.
