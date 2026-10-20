# Third-party notices

## FFmpeg and FFprobe

ATIV bundles FFmpeg 9.0.1 and ffprobe from AVID Core's authenticated `ffmpeg-9.0.1-r7.1` release. Core owns the official source verification, configure options and native builds. `runtime/core-runtime.json` pins the release, binary, metadata and corresponding-source hashes for all six targets.

The statically linked external libraries are x264 (GPL-2.0-or-later, stable commit b35605ace3ddf7c1a5d67a2eb553f034aef41d55), x265 4.1 (GPL-2.0-or-later), LAME 4.0 (LGPL-2.0-or-later), and zlib 1.3.1 (zlib license). The resulting FFmpeg executables are GPL-2.0-or-later; version3 and nonfree components are disabled. Packages preserve Core's complete corresponding-source archive, build scripts, original upstream notices in `licenses/`, and build/provenance records. On macOS these live in `Contents/Resources/FFmpeg`; on Windows/Linux they live in `ffmpeg-runtime/` beside the engine. Preserve these materials when redistributing. See [the runtime documentation](docs/ffmpeg-source-runtime.md).

Core preserves the original compiler runtime notices in each runtime's `licenses/` directory. Compiler and package versions are recorded in `build.json`.

## Qt 6 Presentation Layer

Windows and Linux presentation uses Qt 6 Widgets (dynamically linked). An internal macOS ARM64 build is provided for development and parity testing.

Qt 6 is licensed under the GNU Lesser General Public License version 3 (LGPL-3.0-only) and GNU General Public License version 3 (GPL-3.0-only). Complete license texts are provided in the repository under `licenses/qt/LICENSE.LGPLv3` and `licenses/qt/LICENSE.GPLv3`, and are bundled in distributed packages as `QT_LICENSE.LGPLv3.txt` and `QT_LICENSE.GPLv3.txt`.

### Relinking and Replacement Instructions

In accordance with LGPLv3 Section 4(d), users have the right to modify the Qt libraries and relink or replace them with modified versions:

- **Windows Portable Distribution**:
  Qt 6 runtime libraries (`Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Widgets.dll`, and plugin subdirectories `platforms/qwindows.dll`, `imageformats/`) are dynamically linked and staged in the application directory alongside `ativ-qt-ui.exe`. To use a modified version of Qt:
  1. Build or acquire compatible replacement Qt 6.8+ DLLs with matching ABI.
  2. Replace the corresponding `.dll` files in the ATIV application directory.
  3. Launch `ativ-qt-ui.exe`.

- **Linux AppImage Distribution**:
  Linux AppImages bundle dynamic shared objects (`libQt6Core.so.6`, `libQt6Gui.so.6`, `libQt6Widgets.so.6`, plugins). To replace the Qt libraries:
  1. Extract the AppImage: `./ATIV-x86_64.AppImage --appimage-extract`
  2. In the resulting `squashfs-root/usr/lib/` directory, replace the Qt `.so` files with your modified, interface-compatible Qt 6 libraries.
  3. Run the modified application directly via `./squashfs-root/AppRun` or repackage it using `appimagetool ./squashfs-root`.

### Corresponding Source and Written Offer

- **Source Code Availability**: Source code for Qt 6.8.2 is available from the official Qt repository at https://code.qt.io/cgit/qt/qtbase.git (branch `6.8.2`) and upstream source archives at https://download.qt.io/official_releases/qt/6.8/6.8.2/submodules/qtbase-everywhere-src-6.8.2.tar.xz.
- **Written Offer**: For any recipient of binary distributions of ATIV, Thomas Lothian hereby provides a written offer, valid for at least three years from the date of distribution, to provide a complete machine-readable copy of the Corresponding Source code for the dynamically linked Qt libraries on a durable physical medium at no charge other than the actual cost of physically performing source distribution, or free of charge via download from https://github.com/tlolabs/ativ or https://download.qt.io.

Published v0.2.4 Windows ZIPs used WinUI and Microsoft Windows App SDK; earlier versions used Avalonia .NET. Those components are removed from the active source tree. Linux GTK/libadwaita and Avalonia dependencies are likewise retired.

## AVID Core and Rust dependencies

ATIV links `avid-core` from https://github.com/tlolabs/avid-core at the exact revision in Cargo.toml and Cargo.lock (0.3.1, `15f28236142c100d0a83bf19154ed6f9f5b44e75`); the bundled engine reports it with `build-info`. It contains reconciled ATIV and EnCAP video work and this pinned revision declares GPL-3.0-or-later. See the shared repository's `docs/provenance.md` for source attribution. Packages include its complete license as `AVID_CORE_LICENSE.txt`.

The exact Rust dependency versions and checksums are in Cargo.lock. The following packages retain their upstream notices and licenses (source archives are available from https://crates.io):

- serde, serde_core, serde_derive, serde_json, tempfile, bitflags, cfg-if, errno, fastrand, getrandom, itoa, libc, once_cell, proc-macro2, quote, syn, windows-link, windows-sys: MIT or Apache-2.0.
- same-file, memchr, winapi-util: MIT or Unlicense.
- rustix, linux-raw-sys: MIT, Apache-2.0, or Apache-2.0 with LLVM exception.
- r-efi: MIT, Apache-2.0, or LGPL-2.1-or-later.
- unicode-ident: (MIT or Apache-2.0) and Unicode-3.0.
- zmij: MIT.

Build-only and target-specific dependencies may not all be present in a particular binary. Release source/notice review must include the locked dependency source archives and their license files alongside the exact FFmpeg source/build information.

## Native updates and packaging

Sparkle 2.9.6 is redistributed in macOS bundles under its upstream permissive license; its framework distribution includes license notices. Source: https://github.com/sparkle-project/Sparkle. The ATIV updater uses ring (ISC/MIT/OpenSSL-derived notices), rustls (Apache-2.0/ISC/MIT), reqwest (MIT/Apache-2.0), serde, serde_json, base64, sha2, semver and tempfile under their upstream licenses. Cargo.lock records exact resolved versions.

`webpki-roots` 1.0.9, used by the TLS update stack, contains CA trust-anchor data derived from the Common CA Database under CDLA-Permissive-2.0. Its original data license must remain available with redistributed source and notices.

Inno Setup (https://jrsoftware.org/isinfo.php) builds Windows installers. linuxdeploy and appimagetool (https://github.com/linuxdeploy/linuxdeploy, https://github.com/AppImage/appimagetool) package Linux AppImages; their runtime/tool licenses apply to redistributed components. Python, Pillow and cryptography are development/release tooling and are not bundled as application runtimes. The native production macOS UI retains its platform license boundaries.
