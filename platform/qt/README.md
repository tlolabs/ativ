# ATIV Qt — Shared Cross-Platform Presentation Layer

C++17 / Qt 6 Widgets frontend for ATIV's unchanged Rust engine. This shared
presentation layer powers Windows and Linux production builds, and provides an
internal macOS ARM64 reference build for development and parity testing.
Production macOS remains native SwiftUI/AppKit.

Run `./script/build_qt_macos.sh` on macOS with Qt 6 (Widgets and Test), CMake,
Xcode Command Line Tools, Rust, and the Core runtime provisioning prerequisites installed.
Set `ATIV_QT_PREFIX` if Qt is installed outside `qmake6`'s reported prefix.

- Default / `--verify`: build, bundle dependencies, test, launch, verify process.
- `--build`: build, bundle, and test without launching.
- `--run`: build, bundle, test, and launch.

Outputs on macOS: `build/qt-macos/ATIV Qt.app` and `ATIV-Qt-macos-arm64.zip`.
The internal macOS reference app has a separate bundle ID (`com.tlolabs.ativ.qt-experiment`),
uses the macOS system appearance, is ad-hoc signed for local use, and disables automatic updates.

Features: native file dialogs, file drops, all 27 engine presets grouped by
outlet/aspect/resolution, engine-rendered previews (scaled to 360px base for performance),
horizontal/vertical flips, frame rate, audio bitrate, audio duration, H.264/AAC export,
progress, stage reporting, reveal in Finder/Explorer/Folder, cooperative cancellation,
cross-platform preferences (JSON, with legacy Linux INI migration), system/light/dark appearance,
and automatic update integration on Windows and Linux via `ativ-update`.

The build stages the authenticated pinned AVID Core runtime with the production
verification scripts. On Windows, `windeployqt` stages Qt libraries; on Linux, Qt platform
plugins and libraries are packaged into AppImages; on macOS reference builds, `macdeployqt`
embeds Qt frameworks.

Tests exercise the actual Qt UI and engine: preset selection, preview
scaling, successful export with H.264/AAC verification, invalid
input recovery, missing engine errors, legacy INI migration, preferences roundtrip,
destination validation, and cancellation preserving an existing file.

Original Qt frontend source is GPL-3.0-or-later, as is ATIV. Qt is dynamically
linked under LGPL-3.0 / GPL-3.0 open-source licensing terms; see
https://www.qt.io/licensing/open-source-lgpl-obligations and `THIRD_PARTY_NOTICES.md`.
