# Engineering review record — 2026-09-12

Status: Completed. The repository was reviewed, repaired, and validated within the limits listed in sections 12 and 13. Existing uncommitted work was preserved and extended; no Git history was rewritten and no commit was created.

## 1. Initial condition

A.V.I.D. is a Python 3.10+ Tkinter desktop application and CLI that turns a still image and an audio file into an H.264/AAC MP4. Pillow builds a sharp centered foreground over a blurred fill background; local FFmpeg and ffprobe processes inspect and encode media. The project targets macOS ARM64 and Intel, Windows x64, and Linux x64 through PyInstaller and GitHub Actions. It has no database, authentication, runtime credentials, server, telemetry, or persistence beyond user-selected media paths and output files.

The working tree already contained uncommitted changes in core, GUI, workflow, and test files plus untracked review/test files. They were treated as user work and preserved. The baseline environment was macOS ARM64, Python 3.14.7, Pillow 12.1.1, and FFmpeg 9.0.1. The baseline suite passed 29 tests with no skips in 0.462 seconds. There was no linter, type-checker, or project-specific static-analysis configuration.

## 2. Major problems discovered

| Priority | Problem | Final state |
| --- | --- | --- |
| P1 | FFmpeg wrote directly to the requested output, so failure or cancellation could destroy a prior result; output could alias an input. | Resolved with same-filesystem staging, atomic publication, and alias checks. |
| P1 | Automatic FFmpeg stream choice could replace the intended image with video from the audio container, while missing audio could leave the looped still running. | Resolved with explicit video/audio stream maps and real-media tests. |
| P1 | GUI teardown could destroy Tk state while render work was active, and worker callbacks could enter Tk from background threads. | Resolved with a bounded UI callback queue, retained render thread, cancellation, and asynchronous shutdown polling. |
| P2 | ffprobe could hang, non-finite duration/progress values were accepted, progress callbacks were noisy, and ETA ignored encoder speed. | Resolved with timeout, finite-value validation, progress batching, and speed-aware ETA. |
| P2 | Preview decoding blocked the UI; stale results could win; extreme panoramas created oversized intermediate images. | Resolved with background preview work, generation checks, crop-before-resize compositing, and scaled preview blur. |
| P2 | Typed output paths could be overwritten by suggestions; empty paths could become the current directory. | Resolved with explicit text validation and tracking of auto-generated versus user-edited output paths. |
| P2 | Binary discovery accepted unsuitable entries and bitrate parsing admitted malformed suffixes. | Resolved with regular executable-file checks and a full ASCII bitrate grammar. |
| P2 | CI tested too narrowly, used a retired Intel macOS runner, granted broad write permission, and packaged mutable dependencies. | Resolved with a cross-platform test matrix, supported runners, job-scoped permissions, immutable action SHAs, pinned build dependencies, and checksum-verified Linux FFmpeg. |
| P2 | Local media could make FFmpeg follow nested network references; image and CLI output dimensions lacked application resource budgets. | Resolved with local protocol allowlists and source/output pixel limits. |
| P2 | Tagged macOS packages lacked publisher signing and notarization gates. | Resolved in the build pipeline; tagged builds now fail closed unless signing/notarization credentials are configured. |
| P3 | The Pillow floor admitted old parser releases with subsequently fixed security defects. | Resolved by requiring Pillow 12.3.x and validating 12.3.0 locally. |

## 3. Root causes

- Encoding, cancellation, and output publication were coupled in one direct-to-destination subprocess path.
- FFmpeg defaults were relied on for stream choice and media protocols even though the product requires one known image stream, one audio stream, and local-only inputs.
- GUI work crossed thread boundaries without a single UI-thread dispatch mechanism, and shutdown did not retain ownership of the renderer.
- Image processing limited final preview dimensions but did not constrain decoded source size or crop before allocating an aspect-fill intermediate.
- Validation checked basic syntax and positivity without enforcing full grammars, finite values, executable type, or resource ceilings.
- Release jobs trusted mutable tags and downloads, and macOS distribution had no required identity/notarization stage.
- Tests emphasized happy paths and file existence rather than failure recovery, content/stream correctness, lifecycle transitions, and resource boundaries.

## 4. Significant changes made

- `create_video` resolves paths, rejects missing/non-file inputs and output aliases (including hard links), stages beside the destination in a private temporary directory, and publishes only a completed MP4 with `os.replace`.
- `run_ffmpeg` uses `-nostdin`, absolute paths, explicit `0:v:0` and `1:a:0` maps, an explicit MP4 muxer, a bounded output queue, deterministic terminate/kill/wait cleanup, batched progress, and speed-aware ETA.
- ffprobe selects the first audio stream, considers stream and container duration, times out after ten seconds, and ignores non-finite or non-positive values.
- FFmpeg and ffprobe inputs are restricted to `file,pipe`; source images are limited to 32,768 pixels per axis and 50,000,000 pixels total; output is limited to 8,192 pixels per axis and 33,177,600 pixels total.
- Compositing preserves alpha and applies flips to both layers. The background now crops the visible source region while resizing directly to the target, avoiding huge panorama intermediates.
- Executable discovery and bundle validation require regular executable files. Audio bitrate parsing accepts only positive ASCII integers with one optional `k`, `m`, or `b` suffix.
- Documentation now states Python support, media resource limits, local protocol behavior, and release-signing requirements.

## 5. Architectural changes

The core render boundary now separates four responsibilities: input validation, composite creation, staged FFmpeg encoding, and atomic publication. Failure or cancellation in any earlier stage leaves the final destination untouched.

The GUI uses one bounded callback queue as the thread boundary for Tk work. Audio probing and preview generation share a bounded one-active/one-pending background scheduler. Generation identifiers discard stale results. The non-daemon render thread remains owned until FFmpeg cleanup completes, while window close cancels work, hides the UI, and polls without blocking Tk.

Release workflows now separate routine test jobs from manually/tag-triggered package jobs. Default GitHub token authority is read-only; only the tag-only release job receives `contents: write`.

## 6. UI/UX changes

- The window and primary panes resize with weighted rows/columns.
- Image and audio browse controls have specific labels instead of identical generic labels.
- Horizontal and vertical flip controls update preview and output consistently.
- Typed/pasted audio paths trigger debounced duration loading; typed output paths are preserved.
- Preview generation no longer blocks the Tk event loop, and stale preview work cannot overwrite a newer selection.
- Render progress reports percentage, elapsed media time, duration, and ETA. The FFmpeg console is collapsible and capped at 1,000 lines.
- Closing during rendering requests cancellation and waits for subprocess cleanup before destroying Tk state.
- A source and packaged GUI were visually exercised on macOS. Keyboard-only and screen-reader behavior could not be comprehensively tested in this environment.

## 7. Dependencies changed

- Runtime: `Pillow>=12.3.0,<13`; the local environment was upgraded to and validated with 12.3.0.
- Release builds: `requirements-build.txt` pins Pillow 12.3.0 and PyInstaller 6.19.0 while inheriting runtime requirements.
- Linux packaging: FFmpeg 7.0.2 uses a versioned HTTPS URL and pinned SHA-256 `abda8d77ce8309141f83ab8edf0596834087c52467f6badf376a6a2a4c87cf67`; CI verifies it before extraction and exercises the exact bundled executables.
- GitHub Actions are pinned to immutable commit SHAs. `.github/dependabot.yml` schedules monthly update proposals for Actions and Python dependencies.

## 8. Tests added or modified

The suite now has 59 tests. Added behavioral coverage includes:

- Existing-output preservation on encode failure and early/late cancellation.
- Successful atomic replacement, output/input equality and hard-link rejection, directory rejection, and safe internal filenames.
- Explicit stream maps, muxer selection, local protocol allowlists, malformed bitrate rejection, non-finite progress, probe timeout, reader failure, and real child-process reaping.
- A real FFmpeg source containing its own video stream, correct output stream/dimension/content checks, and prompt failure for missing audio.
- Alpha/flipping behavior, bounded panorama resize, rejection before oversized source decode, and output pixel ceilings.
- Manual output-path preservation, queued main-thread GUI callbacks, stale-preview rejection, and shutdown behavior with idle and active render threads.
- Bundle validation for directories and non-executable files.

## 9. Performance improvements

- The aspect-fill background resizes only the crop that can appear in the output, avoiding intermediates hundreds of times larger than the frame for panoramas.
- Preview work moved off the UI thread and retains at most one pending job.
- Preview blur scales with thumbnail size instead of applying a full-resolution radius.
- FFmpeg output and GUI console storage are bounded.
- Progress callbacks occur once per FFmpeg progress record instead of once per parsed line.
- Resource ceilings prevent pathological image and output allocations.

## 10. Build, test, and static-analysis results

- Final local suite: 59 tests passed with zero failures, errors, or skips. This includes Tk initialization and real FFmpeg encoding/probing.
- `bash -n build_macos_app.sh`: passed.
- Ruby YAML parsing for the GitHub Actions and Dependabot files: passed.
- `python -m pip check`: no broken requirements.
- `git diff --check`: passed; macOS emitted benign sandbox-related `xcrun` cache warnings.
- `avid.py --check-ffmpeg`: found `/opt/homebrew/bin/ffmpeg` as a system binary.
- An isolated ARM64 PyInstaller application was built after the final script changes; the build-time validator found bundled FFmpeg and ffprobe, the DMG checksum verified, the Mach-O executable was ARM64, and `codesign --verify --deep --strict` passed for the ad-hoc test build. The packaged GUI also launched using bundled FFmpeg. The signed/notarized tagged-release path could not be executed without project credentials.
- Codex Security scan `7771c52a-18e9-4d81-8013-97657477633b` completed with four high-confidence, low-severity findings in the pre-hardening snapshot: media protocol access, image resource limits, Linux FFmpeg integrity, and macOS release authentication. Each corresponding repository-controlled remediation is present in the final working tree.

## 11. Compatibility considerations

- Public CLI arguments and GUI features remain intact. Unsupported odd H.264 dimensions continue to fail clearly.
- Python 3.10 through 3.14 remains the intended range; CI covers 3.10, 3.12, and 3.14 across the three operating systems.
- Normal local image/audio formats continue to work under the FFmpeg `file,pipe` policy. Playlist or container inputs that require network protocols are intentionally rejected because the application documents local media processing.
- The 8K output ceiling and 50-megapixel source ceiling reject pathological requests while covering all existing GUI presets and common high-resolution photographs.
- Manual workflow runs may create unsigned macOS test artifacts. Tagged releases require Apple signing/notarization secrets and fail rather than publish unidentified builds.

## 12. Remaining known issues

- The tracked `packages/AVID-macos-arm64.dmg` and `.zip` predate this review and are stale relative to current source. They were preserved because they were existing user artifacts; current release workflows generate fresh packages and do not publish the tracked ZIP.
- Linux FFmpeg 7.0.2 is now reproducibly pinned and authenticated by digest, but should be advanced deliberately when the provider publishes a suitable newer static release.
- The project has no configured linter or type checker. The small codebase passed tests, syntax/import execution, shell/YAML checks, and manual diff review; introducing a new style/type tool was not justified solely for this repair.
- The sealed security artifact retains interim deferred ledger rows and therefore labels aggregate coverage partial even though all repository source files were reviewed and final candidates were resolved. Its four findings and source evidence remain valid for the recorded pre-hardening snapshot.

## 13. Items not validated and why

- Windows and Linux packages and the complete hosted CI matrix were not executed locally because this host is macOS. Their workflow syntax, command failure handling, dependency provenance, and package construction were reviewed statically.
- Intel macOS packaging was not executed because the local machine and Python environment are ARM64; CI now uses GitHub's supported `macos-15-intel` runner.
- Developer ID signing, notarization, stapling, and Gatekeeper acceptance were not run because no Apple Developer certificate or notarization credentials were available. Tagged CI releases now require the documented secrets and fail closed when they are absent.
- Opaque third-party native binaries and historical release archives were inspected for structure, hashes, architecture, and signature metadata but were not reverse engineered.
- Full assistive-technology testing was unavailable; labels, layout behavior, status feedback, and Tk thread safety were reviewed and the GUI was visually exercised.
