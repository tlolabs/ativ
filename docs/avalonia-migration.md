# Shared Avalonia migration and parity audit

The production macOS SwiftUI/AppKit app remains at `platform/macos`. The former Windows WinUI and Linux GTK/libadwaita windows were replaced by one `platform/avalonia` project. Its AXAML, styles, view model, engine protocol client, preferences model and update workflow are compiled unchanged for Windows x64/ARM64, Linux x64/ARM64, and the internal Apple Silicon Mac reference. `IPlatformUpdates` keeps installation behavior below the presentation layer: Windows launches the existing portable replacement helper, while Linux installs the authenticated AppImage or reveals a verified manual download. The reference Mac service disables updates and carries no update executable, configuration or production bundle identity.

Avalonia 12.1.3 targets .NET 8; its analyzers require a .NET 10 SDK for builds. No commercial Avalonia packages or new paid services are used. The full NuGet graph is locked in `platform/avalonia/packages.lock.json`, audited in [the dependency inventory](avalonia-dependencies.json), and included in the release SBOM. Avalonia/Skia/HarfBuzz are MIT; the Windows ANGLE native asset is BSD-3-Clause. The package includes license and notice files.

## Capability mapping

| Old Windows / Linux capability | Shared implementation | Current evidence |
| --- | --- | --- |
| Image, audio and MP4 destination pickers | Same Avalonia storage dialogs and validation | Picker wiring reviewed; CI reference startup and view-model tests pass; interactive dialogs still need checking |
| Dragged image/audio files | Same file drop handler and extension routing | Built; manual platform drop checks pending |
| 27 presets, dependent platform/aspect/resolution choices | Shared view model over unchanged Rust `presets` protocol | 27 presets decoded at packaged reference startup in CI; selection tests passed |
| Duration probe and suggested output name | Shared view model and existing C# engine client | Native C# packaged-engine probe passed; view-model tests passed |
| Styled image preview, flips and stale-request handling | Shared generation guard, engine preview, same AXAML image | Native C# packaged-engine preview passed; manual visual checks pending |
| Bitrate, FPS, flips and export | Shared controls and engine render command | Native C# packaged-engine export passed; Win/Linux package smoke pending |
| Progress, errors and safe cancellation | Shared status/live regions; existing engine cancel protocol | View-model update/render exclusion and cancellation tests passed |
| Window close during active export | Defers close until cancellation finishes | Implemented; manual platform lifecycle checks pending |
| Appearance and automatic-update preferences | Shared preferences UI; Windows JSON path preserved; Linux INI values imported into JSON without deleting source | Linux INI migration fixture passed; manual persistence checks pending |
| Automatic/manual update checks and installation | Same menu and workflow, platform update service | Built; actual signed older-to-newer upgrades pending prior release qualification |
| Menus, keyboard shortcuts and focus | Shared File/Settings/Help menus, Ctrl+I/O/Shift+S/Return and Escape | Built; Narrator/Orca and manual keyboard traversal pending |
| Engine CLI and media files | Unchanged Rust engine protocol and Core runtime | Mac reference packaged engine checks, probe, preview, export passed |
| Production Mac functionality | Unmodified SwiftUI/AppKit source and package path | Six local Swift tests and both native macOS CI targets passed on the migration branch |

The user-visible workflow remains a two-column editor and preview with a status/progress footer. Windows and Linux no longer carry separate presentation source or toolkit dependencies. Historical WinUI/GTK release reports remain in documentation as records of published older versions, not active implementation alternatives.

The internal Mac bundle is `ATIV-Reference.app`, with identifier `com.tlolabs.ativ.reference` and an `INTERNAL-REFERENCE.txt` marker. It is produced only by non-tag CI runs as `ATIV-INTERNAL-REFERENCE-macos-arm64`. The packaging script writes only under ignored `build/`; the production release gate accepts a fixed target list and native macOS package name. The reference does not include `ativ-update`, `update-config.json` or Sparkle and cannot enter the production macOS update feed.

Do not treat the internal Mac smoke as Windows/Linux usability proof. Native Windows/Linux package checks, update safety, and manual keyboard, screen-reader, drag/drop and display-scaling checks remain separate gates. The existing 0.2.6 updater qualification [remains unqualified](updates/qualification-20261001.md); this migration creates no stable tag or public release.
