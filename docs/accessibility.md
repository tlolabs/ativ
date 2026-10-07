# Accessibility and troubleshooting

The current engineering review and remaining manual checks are recorded in [the 2026-10-07 accessibility audit](accessibility-audit-20261007.md).

ATIV uses native controls with system text, colors, focus and scaling. The native Mac and shared Qt interfaces offer System/Light/Dark appearance, persistent audio bitrate/frame-rate preferences, keyboard file selection, a labelled preview, progress, errors and safe cancellation. Decorative icons do not replace text labels. No custom animation is required for normal operations; native controls follow platform reduced-motion behavior.

On macOS, Media menu commands expose image (⌘I), audio (⇧⌘A), destination (⇧⌘S) and export actions (⌘Return). Escape stops a running export. On Windows/Linux, use the shared File menu and Tab navigation; Ctrl+I/Ctrl+O choose media, Ctrl+Shift+S chooses output, Ctrl+Return exports, and Escape cancels. All file paths are also selectable through native file pickers; drag-and-drop is an additional route.

Qt 6 Widgets exposes named file buttons, format controls, bitrate, FPS, preview, progress and live status/error regions through UI Automation/IAccessible2 on Windows and AT-SPI on Linux. macOS native labels and progress values remain exposed to VoiceOver. Shared preferences use standard selection controls with buddies and explicit accessible names. Scrollable content prevents vertically clipped controls at larger text sizes.

Manual VoiceOver, Narrator and Orca tests remain required: traverse every control with the keyboard, read progress/errors, try high contrast and large text, move between displays, and verify 100/150/200% scaling (including Retina). Automated startup tests do not certify screen-reader usability. Record evidence in the acceptance matrix.

## Problems

- **Missing/damaged media tools:** reinstall the complete official package. Do not copy only the UI executable. All packages need the engine, FFmpeg and ffprobe together.
- **Update verification key unavailable:** this build was made without the release public key. Install an official configured release. Never bypass signature verification.
- **Update unavailable for this architecture:** a partial release may not contain your target. The current installation remains usable; consult release notes.
- **Update download/signature failure:** retry later. Incomplete downloads are discarded and the installed app remains untouched.
- **Read-only AppImage location:** move the AppImage to a user-writable directory, or download and replace it manually after verifying the release.
- **No Linux package installer opens:** the verified AppImage download is in the opened folder; close ATIV and replace the old image manually.
- **Preview/export failure:** verify the selected local input files are readable and the destination is writable. Technical details stay in local logs; ATIV never uploads them.
- **Cancelled export:** existing output is preserved. Quitting during rendering requests safe cancellation before shutdown on macOS/Windows/Linux.
- **Local Swift test cannot import XCTest:** point `DEVELOPER_DIR` at full Xcode, not only Command Line Tools.

Removing the app does not delete source media or completed videos. Preferences are intentionally retained unless the user removes them.
