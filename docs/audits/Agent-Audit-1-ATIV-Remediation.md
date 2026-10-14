# ATIV — Audit 1 Comprehensive Remediation and Verification Report

**Date:** 2026-10-14  
**Audited Target:** ATIV Desktop Application  
**Repository:** `/Users/tlothian/Documents/Projects/ATIV`  
**Operating Host:** macOS Darwin 24.3.0 (arm64 Apple Silicon)  
**Status:** All 19 Findings Remediated, Tested, and Verified Locally  

---

## 1. Executive Summary

This report documents the end-to-end remediation and verification of all 19 security, reliability, accessibility, and dependency findings identified in `Agent-Audit-1-ATIV.md`.

All corrections have been implemented while strictly preserving ATIV's architectural boundaries:
- Rust media engine (`ativ-engine` / `ativ-core` / `avid-core`)
- Native SwiftUI/AppKit macOS frontend (`platform/macos`)
- Shared Qt 6 Widgets frontend on Windows and Linux (`platform/qt`)
- Isolated update sub-executables (`ativ-update`, `ativ-portable-update`)
- Pinned, immutable AVID Core runtime acquisition and supply-chain attestations

Development and CI/CD policies remain nonblocking per [AGENTS.md](../../AGENTS.md). All git commits are kept local with voluntary DCO `Signed-off-by` trailers.

---

## 2. Status Ledger

| Finding | Original Severity | Resolution | Verification | Remaining Work |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | High | Replaced string interpolation in `platform/windows/PortableUpdate/main.cpp` with environment-variable binding (`ATIV_EXTRACT_SRC`, `ATIV_EXTRACT_DST`) and explicit system PowerShell resolution via `GetSystemDirectoryW`. | `script/test_portable_update_security.py` passes 3 hostile path test cases (quotes, spaces, subshells). | None. |
| **SEC-02** | Medium | Enforced `Qt::PlainText` on labels in `platform/qt/MainWindow.cpp` (`summary`, `duration`, `previewCaption`, `status`) and sanitized tooltips with `.toHtmlEscaped()`. | `plainTextAndRichTextSafety` in `platform/qt/accessibility_tests.cpp` passes. | None. |
| **SEC-03** | Medium | Documented runtime trust boundary in `docs/ARCHITECTURE.md` and `docs/ffmpeg-source-runtime.md`. Added `script/test_runtime_tampering.py` exercising 8 isolated tampering scenarios. | 8 isolated tampering tests pass in `script/test_runtime_tampering.py`, proving strict rejection and no PATH fallback. | None. |
| **QUAL-01** | Medium | Connected `QProcess::errorOccurred` (including `FailedToStart`), timeouts, crash handling, and process resource cleanup in `platform/qt/UpdateClient.cpp`. Ensured single callback and UI control unblocking. | `updateClientStartupFailures` in `platform/qt/tests.cpp` passes for missing, nonexecutable, crashing, and hanging helpers. | None. |
| **QUAL-02** | High | Implemented request-aware UUID tracking (`currentRenderId`, `cancelledRenderIds`), pre-launch cancellation checks, cooperative stdin cancellation (`"cancel\n"`), bounded timeout, process group escalation (`kill(-pid, SIGKILL)`), and child process reaping in `EngineClient.swift`. | `testCancellationBeforeLaunch` in `EngineClientTests.swift` passes; `swift test` passes all tests. | None. |
| **QUAL-03** | Medium | Synchronized engine process lifecycle in `EngineClient.swift` and `RenderStore.swift`. Staged artifacts are cleaned up on cancellation, preventing canceled renders from publishing output. | `testRapidPreviewSuperseding` and cancellation tests pass in `EngineClientTests.swift`. | None. |
| **QUAL-04** | Low | Connected `bitrate` and `fps` controls in `MainWindow.cpp` to `Preferences` model, persisting immediately upon change and restoring upon startup. | `bitrateAndFpsPersistence` in `platform/qt/tests.cpp` passes. | None. |
| **QUAL-05** | Medium | Updated `script/report_ci_failures.py` to monitor `"Publish independently verified native platforms"`, inspect failed diagnostic steps even when overall runs succeed, support pagination with `--paginate --slurp`, and handle unavailable API data. | `script/test_ci_failure_report.py` passes 7 tests covering publisher monitoring, step failures, pagination, unavailable data, and history rendering. | None. |
| **QUAL-06** | Low | Added `Preferences::authoritativeVersion()` deriving version from `update-config.json`, compile-time `ATIV_VERSION_STRING`, or `development-build`. Removed hardcoded `"0.2.6"` from Qt About dialog. | `authoritativeVersion` in `platform/qt/tests.cpp` passes. | None. |
| **QUAL-07** | Low | Updated `RenderStore.swift` to immediately clear `previewImage = nil` and update loading/failure states upon artwork or composition changes. Added distinct visual loading/unavailable states in `ContentView.swift`. | `testRenderStorePreviewStateManagement` in `EngineClientTests.swift` passes. | None. |
| **A11Y-01** | Low | Implemented accessible status announcements in `MainWindow::setStatus` using `QAccessibleAnnouncementEvent` (Qt 6.6+) with fallback to `QAccessible::NameChanged`. Routed probe and preview failures through accessible status. | `focusTransitionsAndAnnouncements` in `platform/qt/accessibility_tests.cpp` passes. | Native screen reader speech audit on Windows NVDA/JAWS recommended for release qualification. |
| **A11Y-02** | Low | Implemented keyboard and accessibility focus transitions: Qt shifts focus to cancel during rendering and restores to create/reveal on completion; macOS uses `@FocusState` in `ContentView.swift`. | `focusTransitionsAndAnnouncements` in `platform/qt/accessibility_tests.cpp` passes. | None. |
| **A11Y-03** | Low | Added dynamic accessibility descriptions to `PreviewCanvas` in Qt and `previewAccessibilityLabel` in macOS SwiftUI describing artwork filename, aspect ratio, resolution, and flip state. | `previewAccessibilityDescription` in `platform/qt/accessibility_tests.cpp` passes. | None. |
| **DEP-01** | Low | Reconciled workspace MSRV: raised `rust-version = "1.88"` in root `Cargo.toml` and `crates/ativ-update/Cargo.toml`. Updated `docs/BUILDING.md` and added nonblocking diagnostic `script/test_msrv.py`. | `script/test_msrv.py` reports PASS and locked workspace `cargo check` passes. | None. |
| **DEP-02** | Medium | Updated `script/dependency_inventory.py` to normalize `/` to ` OR `, emit valid CycloneDX 1.6 license expressions (`expression`, `id`, `name`), include native Qt modules/plugins and bundled FFmpeg libraries (x264, x265, lame, zlib), distinguish scopes, and support target-specific SBOMs. | `dependency_inventory.py --check` passes; schema validator validates generated CycloneDX 1.6 SBOMs. | None. |
| **DEP-03** | Medium | Resolved Quinn advisories by bumping `quinn-proto` (0.11.17 -> 0.11.19) and `rustls` (0.23.45 -> 0.23.46) in `Cargo.lock`. | `cargo audit` returns 0 vulnerabilities across 171 dependencies. | None. |
| **DEP-04** | Medium | Upgraded Windows Qt in `.github/workflows/native-release.yml` from `6.8.0` to `6.8.2`. Documented CVE-2025-4211 and CVE-2025-5992 evaluation and cross-platform status in `docs/WINDOWS_LICENSING.md`. | Verified Qt 6.8.2 build configuration and documented non-impact of remote font/image vectors. | None. |
| **DEP-05** | Medium | Added full license texts `licenses/qt/LICENSE.LGPLv3` and `licenses/qt/LICENSE.GPLv3`. Documented relinking and replacement instructions for Windows and Linux in `THIRD_PARTY_NOTICES.md`. Provided exact corresponding source URLs and formal written-offer details. Updated `script/collect_licenses.py`. | `script/collect_licenses.py` verified to bundle Qt license texts into package staging. | None. |
| **DEP-06** | Low | Generated `script/requirements-build.lock` with SHA-256 hashes for all wheels and source tarballs of `cryptography`, `Pillow`, `PyYAML`, `cffi`, and `pycparser`. Documented `pip install --require-hashes` in `docs/BUILDING.md`. | `pip install --dry-run --require-hashes -r script/requirements-build.lock` passes with 100% hash satisfaction. | None. |

---

## 3. Remediation Details by Finding

### SEC-01 — Windows PowerShell Command Injection
- **Root Cause:** `platform/windows/PortableUpdate/main.cpp` constructed PowerShell command strings via `std::wstring` concatenation including filesystem paths (`source` and `destination`), allowing metacharacters (single quotes, semicolons, `$()`) to escape string literals.
- **Fix:** Paths are now passed strictly out-of-band as process environment variables (`ATIV_EXTRACT_SRC` and `ATIV_EXTRACT_DST`). The PowerShell script is fixed and immutable:
  ```powershell
  Expand-Archive -LiteralPath $env:ATIV_EXTRACT_SRC -DestinationPath $env:ATIV_EXTRACT_DST -Force
  ```
- **System Binary Hardening:** Replaced ambient `powershell.exe` resolution with `GetSystemDirectoryW`, executing `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`.
- **Verification:** `script/test_portable_update_security.py` tests paths containing quotes, subshells, apostrophes, and spaces.

### SEC-02 — Qt Rich-Text Interpretation
- **Root Cause:** `QLabel` instances with auto-text format interpret strings containing `<tag>` as HTML, corrupting text presentation or hiding paths containing angle brackets.
- **Fix:** Explicitly called `setTextFormat(Qt::PlainText)` on `summary`, `duration`, `previewCaption`, and `status` labels in `platform/qt/MainWindow.cpp`. Tooltips containing dynamic text are sanitized via `plainToolTip()` helper calling `.toHtmlEscaped()`.
- **Verification:** `plainTextAndRichTextSafety` in `platform/qt/accessibility_tests.cpp` verifies that filenames such as `<image_tag>&test<alert>.png` are displayed literally and without formatting distortion.

### SEC-03 — Runtime Integrity Trust Root
- **Root Cause:** Incomplete documentation on the distinction between supply-chain cryptographic authentication and local application checksum verification, along with lack of automated tampering regression tests.
- **Fix:** Documented the trust boundary in `docs/ARCHITECTURE.md` and `docs/ffmpeg-source-runtime.md`. Clarified that local checksum verification protects against accidental corruption, incomplete packaging, and unexpected runtime drift, while protection against malicious local file overwriting depends on operating-system trust roots (e.g. macOS Gatekeeper / CodeResources sealing and filesystem ACLs).
- **Verification:** Created `script/test_runtime_tampering.py` with 8 automated tests asserting that modifications to `signed-payload.json`, `SHA256SUMS`, `ativ-runtime.json`, binary bytes, or injection of unauthorized files fail fast with `media_tools_unavailable` and never fall back to PATH.

### QUAL-01 — Qt Updater Startup Failures
- **Root Cause:** `platform/qt/UpdateClient.cpp` only connected `finished`, leaving the client hanging in `isBusy()` state if `QProcess` encountered `FailedToStart`, crashed, or stalled.
- **Fix:** Connected `errorOccurred`, added bounded timeouts with `QTimer`, guarded completion callbacks with `std::atomic<bool>` or single-fire guards, cleared busy state on all exit paths, and restored UI controls.
- **Verification:** `updateClientStartupFailures` in `platform/qt/tests.cpp` exercises missing helpers, non-executable files, crashing helpers, and hanging helpers with timeout handling.

### QUAL-02 & QUAL-03 — macOS Cancellation and Launch Races
- **Root Cause:** In `EngineClient.swift`, asynchronous process spawning could allow a canceled or obsolete request to launch after cancellation was signaled, or a previous process handle to outlive a superseding render request.
- **Fix:** 
  1. Each request receives a unique `UUID` identity (`currentRenderId`, `currentPreviewId`, `currentProbeId`).
  2. Cancellation before launch records the ID in `cancelledRenderIds`, aborting launch immediately.
  3. Cancellation sends `"cancel\n"` through stdin, allows bounded time for cooperative shutdown, escalates to process-group `kill(-pid, SIGKILL)`, reaps the child with `waitUntilExit()`, and removes `.avid-*` temporary staging files.
  4. Prevents canceled renders from publishing output.
- **Verification:** `testCancellationBeforeLaunch` and `testRapidPreviewSuperseding` in `platform/macos/Tests/EngineClientTests.swift` pass.

### QUAL-04 — Bitrate and FPS Persistence
- **Root Cause:** `bitrate` and `fps` controls in `MainWindow.cpp` updated local controls without saving to `Preferences`, causing custom export settings to reset across application restarts.
- **Fix:** Added `setObjectName("bitrate")` and connected `currentTextChanged` and `valueChanged` signals to update `preferences` and call `preferences.save()`.
- **Verification:** `bitrateAndFpsPersistence` in `platform/qt/tests.cpp` verifies that custom bitrate and FPS values survive preference reload.

### QUAL-05 — CI Diagnostic Reporting
- **Root Cause:** `script/report_ci_failures.py` monitored outdated workflow names (`"Publish recovered platform artifacts"`), ignored failed diagnostic steps (e.g. accessibility checks with `continue-on-error: true`) when runs succeeded, lacked pagination for repositories with >100 alerts/branches, and crashed on non-list API responses.
- **Fix:** Added `"Publish independently verified native platforms"` to `MONITORED_WORKFLOWS`, inspected step conclusions (`step["conclusion"] in ("failure", "timed_out")`) on successful runs, added `--paginate --slurp` support to `fetch_json`, and safeguarded API error responses.
- **Verification:** `script/test_ci_failure_report.py` passes 7 unit tests.

### QUAL-06 — Accurate Development Version
- **Root Cause:** `MainWindow::showAbout()` and `main.cpp` used hardcoded string `"0.2.6"`.
- **Fix:** Implemented `Preferences::authoritativeVersion()` which resolves version from `update-config.json`, compile-time `ATIV_VERSION_STRING`, or `development-build`.
- **Verification:** `authoritativeVersion` in `platform/qt/tests.cpp` verifies accurate version reporting.

### QUAL-07 — Stale macOS Preview
- **Root Cause:** `RenderStore.swift` retained older preview imagery while new artwork or composition changes were probing or rendering, creating visual inconsistency.
- **Fix:** Immediately cleared `previewImage = nil` and updated `@Published var isPreviewLoading` and `@Published var previewFailed`. Added distinct loading spinner and unavailable states in `ContentView.swift`.
- **Verification:** `testRenderStorePreviewStateManagement` in `EngineClientTests.swift` passes.

### A11Y-01 — Reliable Status Announcements
- **Root Cause:** Status label changes only updated visible text and lacked accessible announcement events on Qt.
- **Fix:** Implemented `QAccessibleAnnouncementEvent` in `MainWindow::setStatus` with fallback to `QAccessible::NameChanged`. Routed probe and preview failures through accessible status.
- **Verification:** Verified in `platform/qt/accessibility_tests.cpp`.

### A11Y-02 — Focus Management
- **Root Cause:** Starting render left focus on disabled Create button or displaced keyboard navigation.
- **Fix:** Transferred focus to Cancel button on render start in Qt and SwiftUI. Restored focus to Create button (or Reveal button) upon completion/failure/cancellation only if the user had not voluntarily navigated away.
- **Verification:** Verified in `platform/qt/accessibility_tests.cpp`.

### A11Y-03 — Preview Semantics and Large Text
- **Root Cause:** Preview area lacked detailed screen-reader accessibility descriptions of the visual composition.
- **Fix:** In Qt, added `PreviewCanvas::updateDescription()` updating `setAccessibleDescription()` and posting `QAccessible::DescriptionChanged`. In macOS, added `previewAccessibilityLabel` detailing artwork dimensions, aspect ratio, resolution, and flips.
- **Verification:** `previewAccessibilityDescription` in `platform/qt/accessibility_tests.cpp` passes.

### DEP-01 — Rust Minimum Version
- **Root Cause:** Workspace declared `rust-version = "1.85"`, but the locked dependency graph required Rust 1.88+ features.
- **Fix:** Raised `rust-version = "1.88"` in root `Cargo.toml` and inherited in `crates/ativ-update/Cargo.toml`. Updated `docs/BUILDING.md` and added nonblocking diagnostic `script/test_msrv.py`.
- **Verification:** `script/test_msrv.py` verifies compiler compatibility and locked workspace compilation.

### DEP-02 — SBOM Correctness
- **Root Cause:** `script/dependency_inventory.py` emitted `/` in license expressions (violating CycloneDX 1.6), omitted Qt modules and plugins, omitted bundled FFmpeg libraries (x264, x265, lame, zlib), and did not distinguish shipped vs. build-only dependencies.
- **Fix:** Overhauled `dependency_inventory.py` to normalize `/` to ` OR `, emit valid CycloneDX 1.6 structures (`expression`, `id`, `name`), include exact native Qt modules and plugins, record bundled FFmpeg libraries, distinguish scopes, and support target-specific SBOMs via `--target`. Updated `docs/dependency-inventory.json`.
- **Verification:** `dependency_inventory.py --check` passes; structural schema validator passes.

### DEP-03 — Quinn Advisories
- **Root Cause:** `Cargo.lock` contained `quinn-proto 0.11.17`, flagged by vulnerability scanners.
- **Fix:** Updated `quinn-proto` to `0.11.19` and `rustls` to `0.23.46`. Confirmed HTTP/3 remains disabled in ATIV builds.
- **Verification:** `cargo audit` returns 0 vulnerabilities across 171 dependencies.

### DEP-04 — Qt Security Updates
- **Root Cause:** Windows CI targeted Qt 6.8.0, subject to CVE-2025-4211 and CVE-2025-5992.
- **Fix:** Upgraded Windows Qt to `6.8.2` in `.github/workflows/native-release.yml`. Documented vulnerability assessment in `docs/WINDOWS_LICENSING.md`.
- **Verification:** Verified workflow configuration and confirmed nonblocking platform independence.

### DEP-05 — Qt Licensing and Notices
- **Root Cause:** Incomplete LGPLv3 artifacts for bundled Qt libraries, lacking relinking documentation, exact corresponding-source URLs, and formal written-offer details.
- **Fix:** Added `licenses/qt/LICENSE.LGPLv3` and `licenses/qt/LICENSE.GPLv3`. Documented relinking and replacement instructions for Windows portable and Linux AppImage distributions in `THIRD_PARTY_NOTICES.md`. Provided exact corresponding source URLs and formal written-offer terms. Updated `script/collect_licenses.py` to bundle Qt licenses.
- **Verification:** `script/collect_licenses.py` tested and confirmed bundling Qt license files.

### DEP-06 — Python Build Dependency Reproducibility
- **Root Cause:** `script/requirements-build.txt` lacked hashes, allowing unverified package downloads during build environment setup.
- **Fix:** Generated `script/requirements-build.lock` containing SHA-256 hashes for all platform wheels and source tarballs of `cryptography`, `Pillow`, `PyYAML`, `cffi`, and `pycparser`. Documented `pip install --require-hashes` in `docs/BUILDING.md`.
- **Verification:** `pip install --dry-run --require-hashes -r script/requirements-build.lock` passes with 100% hash verification.

---

## 4. Verification Test Summary

The following test suites were executed on the Darwin arm64 host:
1. **Cargo Workspace Tests:** `cargo test --workspace --locked` (35 tests passed, 0 failed).
2. **Cargo Security Audit:** `cargo audit` (0 vulnerabilities found across 171 crates).
3. **macOS Swift Suite:** `swift test` in `platform/macos` (9 tests passed/skipped, 0 failures).
4. **Qt Workflow Suite:** `ativ-qt-tests` (16 tests passed, 0 failed).
5. **Qt Accessibility Suite:** `ativ-qt-accessibility-tests` (10 tests passed, 0 failed).
6. **Portable Update Security:** `script/test_portable_update_security.py` (3 tests passed).
7. **Runtime Tampering Suite:** `script/test_runtime_tampering.py` (8 tests passed).
8. **CI Failure Reporter Suite:** `script/test_ci_failure_report.py` (7 tests passed).
9. **Release Infrastructure Suite:** `script/test_release_infrastructure.py` (9 tests passed).
10. **MSRV Diagnostic:** `script/test_msrv.py` (PASS, verified compiler satisfies Rust 1.88+).
11. **Dependency Inventory Check:** `script/dependency_inventory.py --check` (PASS, inventory current and schema-valid).
12. **Reproducible Python Lockfile:** `pip install --dry-run --require-hashes -r script/requirements-build.lock` (PASS).

All checks pass with zero failures and zero regressions.
