# Accessibility and platform support audit — 2026-10-07

This is a best-effort engineering audit, not WCAG certification. The review covers the production SwiftUI/AppKit Mac interface and the Qt 6 Widgets interface used on Windows, Linux, and the internal Apple Silicon Mac reference. The media engine and update installation logic were reviewed only where they affect user-facing status and errors.

## Existing support commitments

| Interface | Supported systems and architectures | Distribution |
| --- | --- | --- |
| SwiftUI/AppKit | macOS 13+, Apple Silicon and Intel | Signed/notarized ZIP |
| Qt 6 Widgets | Windows 10 1809+, x64 and ARM64 | Portable ZIP |
| Qt 6 Widgets | Linux X11/Wayland, x64 and ARM64 | AppImage |
| Qt 6 Widgets reference | Internal macOS arm64 | Internal ZIP |

No minimum version, architecture, UI framework, or distribution format changed.

## Confirmed issues addressed

| Area | Finding and change |
| --- | --- |
| Mac appearance | The preference applied a color scheme only to the main content view. It now also sets the application appearance, so native menus, alerts, and Settings follow the System/Light/Dark choice immediately. |
| Mac file replacement | An automatically suggested destination could already exist, bypassing the save panel's overwrite warning. Creating a video now asks before replacing an existing file. |
| Mac dynamic status | Render stages and final success now send AppKit accessibility announcements; rapidly changing percentages remain readable in the progress control without repeated speech. |
| Mac forms and layout | Format pickers have explicit accessibility labels, decorative icons are hidden from the accessibility tree, flip controls can stack when space is tight, and Settings can grow beyond its minimum width. |
| Qt constrained windows | The previous 860 × 650 minimum could exceed a small desktop. The new 640 × 480 minimum uses a vertically scrollable control pane, wrapping form rows, and a smaller preview minimum. The destination remains reachable with larger text. |
| Qt progress and status | Progress now displays its percentage. The status label exposes its current text rather than a fixed accessible name, and major stage/completion changes emit accessibility name-change events. |
| Qt preview state | The caption now states when the preview is preparing, ready, or unavailable, so its state does not depend on the custom image canvas alone. |
| Qt dark appearance | Tooltip foreground and background are now distinct. Disabled text has an explicit readable color in the dark palette. |
| Engine launch errors | Both interfaces give a plain-language recovery step when the media engine cannot start; technical process details remain in local logs. |

## Verification performed

- Before changes: Qt reference build and existing `qt-workflow` CTest passed.
- After changes: native Mac Swift target compiled with Command Line Tools, targeting macOS 13. Qt reference build, existing `qt-workflow`, and the separate informational accessibility tests passed on macOS arm64 with Qt 6.11.2.
- The internal Qt Mac reference ZIP was rebuilt. Bundle validation passed for embedded dependencies and runtime provenance; its packaged engine passed the existing workflow test.
- The rebuilt Qt reference launched. Its macOS accessibility tree exposed named file-selection buttons, format controls, destination, progress, and current status text.
- The new Qt accessibility test checks status/progress semantics and destination reachability at 640 × 480 with enlarged text. CI runs it as a nonblocking step on native Windows, Linux, and the internal Mac reference jobs. It is deliberately outside CTest so it does not create an accessibility release gate.

The full native Mac XCTest suite could not run locally: the installed Xcode license has not been accepted, while Command Line Tools lack XCTest. The Swift application target compiled. Modified Windows and Linux packages were not built on this Mac; their native CI jobs remain the compatibility check. A modified production Mac ZIP was not packaged locally because that workflow needs the full Xcode toolchain and release configuration.

## Manual verification still required

Test the exact modified packages on each supported platform and architecture. Use VoiceOver, Narrator or NVDA, and Orca to verify speech, focus order, dialog restoration, stage/error announcements, and keyboard navigation. Check System/Light/Dark appearance, contrast and reduced-motion preferences, 100/125/150/175/200% scaling where available, Retina/HiDPI, display moves, and small windows. Record results in the acceptance matrix. The Qt accessibility-tree inspection and automated tests do not establish screen-reader usability.

## Limitations and recommendations

- Qt's platform accessibility bridges and host styles determine some spoken roles, popup behavior, high-contrast handling, and AT-SPI/UI Automation output. Verify on the actual Windows and Linux hosts before treating those paths as complete.
- The native Mac content still has a split-view layout with a 720-point minimum width. Assess compact layout and large system text manually before changing the established composition further.
- Review contextual help or onboarding only after observing users who need it; this audit did not add new instructional flows.
- Older Windows, Linux, and macOS baselines require native runtime testing. Compiling against a newer SDK does not prove behavior on the minimum supported OS.
