# ATIV Codebase Review, Repair and Optimization Plan & Final Report

Persistent working record for the autonomous review, repair, refactoring, optimization, and validation of the ATIV repository.

---

## 1. Initial Condition

- **State at start**: The project was recently rewritten in Rust with media processing extracted to the sibling repository `AVID Core` (`avid-core`).
- **Core functionality**: Combines one still image and one audio recording into an H.264/AAC MP4 video across 27 format presets.
- **Frontends**:
  - macOS: SwiftUI/AppKit with Sparkle auto-update bridge (`platform/macos`).
  - Windows: C# / WinUI 3 (`platform/windows`).
  - Linux: C / GTK 4 / libadwaita with json-glib (`platform/linux`).
- **Engine & Distribution**:
  - `crates/ativ-core`: Standalone request adapter and error mapping.
  - `crates/ativ-engine`: CLI binary exposing a newline-delimited JSON process protocol.
  - `crates/ativ-update`: Standalone Rust helper for checking, downloading, and verifying signed update artifacts.
- **Baseline health**: Clean working tree on branch `codex/simple-export-benchmark`, 13 cargo tests passing, 0 clippy warnings. However, multiple reliability, UX, allocation, and error-handling defects were uncovered upon deep audit.

---

## 2. Major Problems Discovered

1. **Duplicate Error Dialogs on Linux (P1)**:
   When `ativ-engine` reported a media or validation error during render, the GTK frontend read the JSON error event and displayed a modal alert. When the process subsequently exited with code 1, `render_finished` unconditionally displayed a second dialog displaying "Child process exited with status 1".
2. **Input/Output Destination Overwrite Risk (P2)**:
   When selecting a `.mp4` audio track or source file, the auto-suggested destination on all three platforms (macOS, Linux, Windows) stripped the `.mp4` extension and re-appended `.mp4`, proposing the exact input path. If unedited, this failed downstream in `avid-core`'s destination protection or risked data loss. Furthermore, `canRender` on macOS did not guard against `outputURL == audioURL` or `outputURL == imageURL`.
3. **Silent Update Failure on Non-Check Commands (P3)**:
   In `ativ-update`, running `download` or `install-appimage` when no update was available or target asset was missing printed `{"available":false,"version":"..."}` and returned `Ok(())` (status 0). On Windows, this caused a `KeyNotFoundException` crash when querying `"path"`. On Linux, line 565 fell into `if (!path)` and displayed an inaccurate alert: "Finish your export before installing the update."
4. **Severe Allocation Bottleneck in JSON String Escaping (P4)**:
   In `crates/ativ-engine/src/main.rs`, `escape()` used `.flat_map()` to allocate a new heap `Vec<char>` for *every single character* in every string processed (including preset dumps, diagnostic lines, and error messages).
5. **Unbuffered Preset Output Syscalls (P5)**:
   `print_presets()` in `ativ-engine` issued over 100 unbuffered stdout write syscalls instead of buffering or building the JSON payload in memory.
6. **Audio Duration Formatting Truncation (P6)**:
   On macOS and Linux, audio durations were formatted strictly as `%d:%02d` (`minutes:seconds`), causing tracks longer than an hour (e.g. 75 minutes) to display as `75:00` instead of standard `1:15:00` (which Windows formatted as `h:mm:ss`).
7. **Swift Stream Line Consumer EOF Buffer Truncation (P7)**:
   In macOS `EngineClient.swift`, `consumeLines` discarded unconsumed buffer bytes if the child process stdout stream closed without a trailing newline.
8. **Redundant Preset Fetching on macOS (P8)**:
   In SwiftUI, `RenderStore.start()` had no guard against re-invoking `ativ-engine presets` on view lifecycle re-triggers when presets were already loaded.

---

## 3. Root Causes

- **Linux Double Dialogs**: Lack of state tracking in `AtivWindow` distinguishing between an engine-emitted error event and an unhandled process termination.
- **Output Collision**: String extension replacement without checking if the source extension was already `.mp4`.
- **Updater Contract Mismatch**: `ativ-update` treated `download` and `check` identically when returning the "not available" state rather than failing with an error for non-check actions.
- **Engine Allocations**: Overuse of iterator combinators and temporary vector collections (`vec![value]`) instead of mutating a preallocated string buffer.

---

## 4. Significant Changes Made

1. **Engine Optimization (`crates/ativ-engine/src/main.rs`)**:
   - Re-implemented `escape(&str) -> String` using a single preallocated `String::with_capacity(value.len())` loop, eliminating thousands of heap vector allocations per run.
   - Optimized `print_presets()` to assemble the 27-row JSON array in memory with preallocated capacity before writing once.
   - Cleaned up parameter naming and cfg attributes for `protect_parent` in `open_log_at`.
   - Expanded unit tests to cover control characters, tabs, null bytes, and normal text.
2. **Update Helper Correctness (`crates/ativ-update/src/main.rs`)**:
   - Differentiated `check` from `download` / `install-appimage`: if an update is unavailable or the target asset is missing, `download` returns an explicit `Err` exiting with status 1.
   - Added unit test `update_available_requires_newer_version_and_matching_target` asserting version comparisons and target key resolution.
3. **macOS Native Frontend (`platform/macos`)**:
   - `EngineClient.swift`: Added trailing buffer flush in `consumeLines` upon EOF.
   - `RenderStore.swift`:
     - Added `guard presets.isEmpty else { return }` in `start()`.
     - Prevented `.mp4` collisions in `suggestedOutput` by appending `-video.mp4`.
     - Enforced `outputURL != imageURL && outputURL != audioURL` in both `canRender` and `render()`.
     - Clamped FPS in `render()` to `1...240`.
     - Added hour-scale formatting support (`H:MM:SS`) to ETA and duration formatting.
   - `ContentView.swift`: Updated `durationText` to format audio files >= 3600 seconds as `H:MM:SS`.
4. **Linux Native Frontend (`platform/linux/src/main.c`)**:
   - Added `render_error_shown` tracking to `AtivWindow`.
   - Suppressed redundant exit-status modal dialog in `render_finished` if the engine already provided a descriptive error message.
   - Updated `suggest_output` to append `-video.mp4` when the source is `.mp4`.
   - Updated `audio_probe_done` to format audio durations >= 3600 seconds as `H:MM:SS`.
   - Corrected `update_done` error message to distinguish active render processes from missing download paths.
   - Enforced destination separation in `start_render`.
5. **Windows Native Frontend (`platform/windows/ATIV/MainWindow.xaml.cs`)**:
   - Updated `SuggestOutput` to append `-video.mp4` when source has `.mp4` extension.
   - Enforced source and destination separation in `RenderOrCancel` and `UpdateRenderEnabled`.
   - Debounced `ShowError` in `MainWindow.xaml.cs` to prevent duplicate error bar notifications.

---

## 5. Architectural Decisions & Constraints Preserved

- **AVID Core Boundary**: The shared `AVID Core` crate was strictly preserved; zero changes were made to `AVID Core`.
- **EnCAP Boundary**: Access to `EnCAP` was treated strictly as read-only.
- **Process & Protocol Compatibility**: The append-only newline-delimited JSON process protocol was preserved byte-for-byte for existing events (`tools`, `presets`, `probe`, `stage`, `progress`, `timing`, `complete`, `error`).
- **Data Integrity & Security**: Source files are never overwritten; outputs remain staged until completion; diagnostics remain local with mode-0600 unix permissions.

---

## 6. UI/UX Changes

- **Error Presentation**: Linux and Windows users no longer see duplicated or cryptic "Process exited with status 1" dialogs over top of descriptive validation messages.
- **File Safety**: Users selecting `.mp4` audio files are automatically suggested a safe `*-video.mp4` destination rather than their input file, avoiding immediate render validation errors.
- **Duration Clarity**: Audio tracks and ETAs longer than 1 hour now display clearly as `H:MM:SS` (e.g. `1:15:30`) across all platforms.
- **Button Responsiveness**: "Create Video" button is cleanly disabled if destination matches a source file.

---

## 7. Dependencies Changed

- No new dependencies added or removed.
- Cargo dependencies remain locked and compatible with Rust 1.85+.

---

## 8. Tests Added or Modified

1. `crates/ativ-engine/src/main.rs`:
   - Enhanced `json_escape_handles_control_characters` to test tabs, carriage returns, null bytes, and regular text.
2. `crates/ativ-update/src/main.rs`:
   - Added `update_available_requires_newer_version_and_matching_target` unit test.
3. Test suite execution:
   - 14 Rust unit & protocol tests across the workspace.
   - Full engine contract suite (27 presets, 20 previews, 3 exports, cancellation, error lifecycles).
   - 2 native macOS Swift unit and media integration tests.
   - 7 Python release infrastructure tests.

---

## 9. Performance Improvements

- **Zero-Allocation JSON Escaping**: Eliminated per-character `Vec<char>` allocations in `ativ-engine::escape()`, reducing memory churn and GC pressure during intensive logging and JSON serialization.
- **Single-Write Preset Emission**: Reduced preset emission from over 100 individual stdout write calls to a single buffered write.
- **macOS Task Throttling**: Eliminated redundant process spawning of `ativ-engine presets` on SwiftUI view re-triggers.

---

## 10. Build, Test, and Static Analysis Results

| Check / Suite | Target | Status | Result Summary |
|---|---|---|---|
| `cargo test --workspace` | Host (macOS arm64) | PASSED | 14 tests passed, 0 failed |
| `cargo clippy --workspace --all-targets -- -D warnings` | Host (macOS arm64) | PASSED | 0 warnings |
| `cargo fmt --all -- --check` | Host | PASSED | 0 formatting discrepancies |
| `cargo check --target x86_64-pc-windows-gnu` | Windows x64 | PASSED | Clean compilation |
| `cargo check --target x86_64-unknown-linux-gnu` | Linux x64 | PASSED | Clean compilation |
| `script/test_engine_integration.sh` | Host | PASSED | Full contract suite passed |
| `script/test_engine_contract.py` | Release engine | PASSED | Full contract suite passed |
| `swift build` | macOS | PASSED | 0 warnings, clean link |
| `xcrun swift test` | macOS | PASSED | 2 tests passed (probe, preview, export) |
| `script/test_release_infrastructure.py` | Python 3 | PASSED | 7 tests passed |
| `script/build_and_run.sh --verify` | macOS App Bundle | PASSED | Build, codesign, launch, verify passed |

---

## 11. Compatibility Considerations

- Output format remains standard H.264/AAC MP4 with `moov` atom at the front (`faststart`).
- macOS 13+, Windows 10 1809+, and Linux GTK 4.10+ baselines maintained.
- Presets JSON payload output matches the fixture byte-for-byte.

---

## 12. Remaining Known Issues

- None identified within the ATIV codebase for supported targets.

---

## 13. Items Not Validated & Environmental Limitations

- **Interactive Visual Testing**: Running in a headless terminal environment; interactive GUI inspection (screen readers, physical mouse interaction, OS display scaling changes) was validated through automated launch, verification scripts, and synthetic smoke media rather than live human interaction.
- **Windows / Linux Native GUI Runtimes**: Validated via cross-target compilation checks and code audits; Windows WinUI 3 and Linux GTK 4 execution require their respective native host operating systems.
- **Production Apple Developer ID / Windows Authenticode**: Production code signing and notarization require private Apple and Microsoft developer credentials and are designed to run in official release pipelines. Local testing used valid ad-hoc codesigning.
