# ATIV migration to AVID Core

> Historical first extraction report. Current integration and verification: [Core 0.3.0 migration](core-runtime-migration.md). Paths, versions and blockers below describe the original work only.

ATIV now delegates its feature engine to the independently versioned `avid-core` crate. This is the first host migration. EnCAP was not modified, and the two-host consolidation is not complete.

## Revisions and preserved work

- ATIV baseline: `2c5eeed27e48d67fed128a62ff74dab6f00c2a82`.
- Migration branch: `codex/ativ-shared-core`.
- Engine migration and contract tests: `daad195` (`Delegate ATIV media processing to avid-core and preserve engine protocol`). Packaging, CI, notices, and this report are the following commit.
- Exact shared revision tested: **`0cce6ba838827d0bed540efc98731e74a1014456`** in `/Users/tlothian/Documents/Projects/AVID Core`. Its public remote HEAD matched this revision. Shared README, report, inventory, and reference audit were read before implementation. Its implementation commit follows the extraction inventory commit `a6b1abb`; there were no subsequent commits or working-tree changes to reconcile.
- ATIV started with only untracked `assets/`. Those files remain untracked and untouched. The original engine was preserved under ignored `target/migration-reference/ativ-engine`; generated test media remains outside tracked source.
- No shared implementation gaps required a shared-repository change. The shared checkout remains clean at the tested revision. No EnCAP files were edited.

## Adapter and protocol decisions

The workspace root declares `avid-core = { path = "../AVID Core" }`; `crates/ativ-core` consumes it with `avid-core.workspace = true`. Cargo.lock records the dependency graph. Native builds continue producing `ativ-engine`; no native client or UI source changed.

`ativ-core` retains only ATIV request mapping, application version identity, shared API re-exports, and error presentation. Its old `media.rs` and `render.rs` were removed after migrated callers, unit tests, and reference media comparisons passed. Local preset tables, validators, graphs, process monitoring, progress parsing, alias checks, staging, and publication are gone.

Export uses `Input::Single`, explicit `Codec::H264`, `Encoding::Software`, and `Composition::Fitted`. All request dimensions, FPS, bitrate, and flips are forwarded. It never uses the timeline path or EnCAP's narrower persisted-settings validator. Preview uses the shared PNG renderer with fitted composition and both flips, retaining only the existing preview completion event on stdout.

The engine retains CLI parsing, JSON escaping and serialization, `ATIV_LOG_PATH`, private rotating logs, and stdin cancellation. The same atomic cancellation flag is wrapped by the shared token before discovery, covering tool validation, probes, preview, and export. Case-insensitive `cancel\n`, cancellation status 130, and failure status 1 remain intact.

The 27-row presets event is byte-for-byte compatible with the baseline (the additional shared FPS field is omitted). Application version remains 0.2.1, independent of shared version 0.1.0. Unknown and nonfinite numeric values remain JSON null. Render stage ordering and progress field names remain unchanged; only the complete stage signals successful publication.

Shared errors remain structured until local logging, including executable, arguments, status, stderr and underlying OS cause. Native messages do not expose shared diagnostic Display text. Timeout, capture-limit and fallback failures map to `media_tool_failed`; the old discovery process-exit category remains `media_tools_unavailable`, and process-spawn/I/O failures remain `io_error`. Missing/invalid input and cancellation retain their existing categories.

The existing log writer used a let-chain unsupported by the declared Rust 1.85 minimum. It now uses equivalent supported syntax; a Windows-only unused-parameter warning was also removed. Logging permissions and rotation policy remain unchanged.

## Checks actually run

All results below are local unless explicitly described as pending.

| Check | Result |
| --- | --- |
| Original ATIV format/check/test/clippy and original integration script | Passed; six original unit tests, real encode, preview and cancellation |
| Shared `cargo fmt --all -- --check` | Passed |
| Shared `cargo check --locked --all-targets` | Passed |
| Shared `cargo test --locked --all-targets` | 36 tests passed; three media tests ignored in this invocation |
| Shared `cargo clippy --locked --all-targets -- -D warnings` | Passed |
| Shared `cargo test --locked --test ffmpeg -- --ignored` | All three passed with ATIV's existing 9.0.1 pair |
| Migrated ATIV format/check/test/clippy with locked dependencies | Passed; nine unit/process protocol tests |
| ATIV `cargo +1.85.0 check --locked --all-targets` | Passed after the logging syntax correction |
| Windows x86_64 GNU all-target check and clippy with warnings denied | Passed; compile only |
| Linux x86_64 GNU all-target check and clippy with warnings denied | Passed; compile only |
| Strengthened `script/test_engine_integration.sh` | Passed, including its original assertions and expanded contract suite |
| Debug engine versus preserved original engine | 20 previews and three exports: identical decoded preview/video/audio bytes |
| Packaged release engine versus preserved original engine | Full contract suite passed, including the same decoded parity comparisons |
| Shell/Python syntax, workflow YAML parsing, `git diff --check` | Passed |

The expanded Python suite generates deterministic asymmetric PPM artwork and one-second WAV files in paths containing spaces and Unicode. It renders all 27 actual preset dimensions to PNG with a non-PNG destination suffix. It additionally compares five aspect families (landscape, portrait, square, 4:3, 4:5) across all four flip combinations. Three exports cover 1/30/240 fps, 128k/224k/integer 128000 bitrates, mono 44.1 kHz and stereo 48 kHz, H.264/AAC, yuv420p, MP4 independent of suffix, faststart, audio-ending duration, successful existing-output replacement, and progress fields/stages.

Failure checks cover corrupt artwork/audio, missing input/tools, invalid dimensions/FPS/bitrate, source image limits and zero dimensions, direct/hard-link/symlink aliases for selected sources, preview aliases, private diagnostics, mismatch/wrong tool identity, unknown-duration nulls, process failures, real and fake in-flight encoding cancellation, immediate cancellation of each media command, existing-output preservation, and absence of both `.ativ-*` and `.avid-*` stages. Source hashes remain unchanged. A fake probe verifies the actual default 30-second timeout through the engine's legacy error code.

Deterministic cancellation immediately before publication, render/preview timeout cleanup, capture overflow, and child reaping are also covered by the shared lifecycle/process tests run above. They are not separately claimed as native UI timing tests.

## One FFmpeg build and packaging

No FFmpeg was built, downloaded, or added for the shared crate. Local tests and packages used only the existing `build/ffmpeg-macos-arm64` pair, both identifying as `9.0.1-https://www.martin-riedl.de`.

Input artifact SHA-256:

- ffmpeg: `393e4c395020a1cb7cbd77fbe00599ce69d1c6466fee0dbd59d13f86a81a1611`
- ffprobe: `7abc49fb2bdf2204f018e76dc6e0a8ae7643313bae09a9fa43e7eb12442271bc`

The macOS build advertises libx264, libx265, AAC, libmp3lame, AudioToolbox AAC, PNG, and all required fitted/timeline filters. FFmpeg's Mach-O minimum OS is 12.0. The existing package script confirmed only system dynamic dependencies. Capability advertisement is not a complete EnCAP audio/device runtime test; EnCAP's later common-build correction remains separate.

The new packaging gate checks the approved version through canonical discovery and verifies the required codec/filter union. These packaging capability lists are intentional host-owned occurrences of `gblur`/`libx264`; fake test tools also mention encoder/probe identifiers. Production Rust has no remaining graph or FFprobe command construction. The preset JSON fixture is test data, not a second production table.

CI now checks out ATIV and the exact shared revision into sibling directories. Its engine job uses the pinned Linux release tools instead of installing a separate system FFmpeg. Every native packaging job runs canonical real-media tests and ATIV integration tests using its own single release pair. CI changes were parsed and reviewed locally; the workflow has not been dispatched from this task.

macOS results:

- `script/build_and_run.sh --verify` passed, producing and launching `dist/ATIV.app`. Process existence was independently confirmed.
- Debug and release builds initially encountered cached Swift modules referencing the previous `avid` directory. Cleaning the corresponding ignored Swift scratch directories resolved this without source changes.
- `script/package_macos.sh arm64` passed with ad-hoc signing and produced `packages/ATIV-0.2.1-macos-arm64.zip` and `.dmg`.
- Debug/release deep strict signature verification passed. DMG checksum verification passed.
- Release engine discovery passed with an empty PATH, proving the adjacent bundled pair works without development tools.
- The packaged engine passed the complete media/contract/reference suite. Shared license and current third-party notices were verified in the bundle.

## Remaining platform and manual release gates

- Interactive macOS UI inspection was attempted, but the computer-use service failed with `Sky Computer Use native pipe closed before response`. Native artwork pickers, preview generation races, appearance, accessibility, UI error presentation, and Stop interactions have not been interactively certified in this task. Source review confirms existing async worker queues and generation guards were retained.
- Intel macOS and minimum-OS runtime verification remain pending. Only the local Apple Silicon app was built/launched/packaged.
- Windows 10 1809+ x64/ARM64 and GTK Linux x86_64/ARM64 packaging/runtime tests need their native runners. This host lacks their native SDK/toolkit/runtime environment. GNU cross-target Rust checks do not establish MSVC/ARM64 packaging, native UI behavior, Windows file-locking/overwrite behavior, or Linux desktop installation.
- Other platform FFmpeg artifacts have not been locally standardized or certified. Run the new capability gate and shared/host media suites on every target before selecting common distribution inputs.
- Developer ID/notarization, Windows Authenticode, clean-machine installs, low-disk/read-only destinations, remote filesystem behavior, and the full manual acceptance matrix remain release gates. The local macOS artifacts are ad-hoc signed verification builds.
- No commits were pushed and no release was published by this task.

Next: finish thorough ATIV native verification, then perform the separate EnCAP Video migration. Its existing macOS FFmpeg recipe needs the common build's software video encoders, not an additional executable pair.
