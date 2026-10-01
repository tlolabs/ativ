# Third-party notices

## FFmpeg and FFprobe

ATIV bundles FFmpeg 9.0.1 and ffprobe from AVID Core's authenticated `ffmpeg-9.0.1-r7.1` release. Core owns the official source verification, configure options and native builds. `runtime/core-runtime.json` pins the release, binary, metadata and corresponding-source hashes for all six targets.

The statically linked external libraries are x264 (GPL-2.0-or-later, stable commit b35605ace3ddf7c1a5d67a2eb553f034aef41d55), x265 4.1 (GPL-2.0-or-later), LAME 4.0 (LGPL-2.0-or-later), and zlib 1.3.1 (zlib license). The resulting FFmpeg executables are GPL-2.0-or-later; version3 and nonfree components are disabled. Packages preserve Core's complete corresponding-source archive, build scripts, original upstream notices in `licenses/`, and build/provenance records. On macOS these live in `Contents/Resources/FFmpeg`; on Windows/Linux they live in `ffmpeg-runtime/` beside the engine. Preserve these materials when redistributing. See [the runtime documentation](docs/ffmpeg-source-runtime.md).

Core preserves the original compiler runtime notices in each runtime's `licenses/` directory. Compiler and package versions are recorded in `build.json`.

## Avalonia and managed runtime

Current Windows/Linux presentation uses Avalonia 12.1.3 (MIT), SkiaSharp 3.119.4 (MIT), HarfBuzzSharp 8.3.1.3 (MIT), ANGLE 2.1.27548.20260419 (BSD-3-Clause on Windows), and a self-contained .NET 8 runtime (MIT). Exact NuGet package versions, hashes, target selection and declared licenses appear in `docs/avalonia-dependencies.json`. The packages include `licenses/Avalonia.txt`, `Avalonia-notices.txt`, `SkiaSharp.txt`, `HarfBuzzSharp.txt` and `ANGLE.txt`. Preserve them on redistribution. The .NET runtime retains its upstream notices and source attribution.

Published v0.2.4 Windows ZIPs used WinUI and Microsoft Windows App SDK; [their historical audit](docs/WINDOWS_LICENSING.md) remains available. Those components are removed from the new source packaging path. Linux GTK/libadwaita source and deployment dependencies are likewise retired.

## AVID Core and Rust dependencies

ATIV links `avid-core` from https://github.com/tlolabs/avid-core at the exact revision in Cargo.toml and Cargo.lock (0.3.0, `25d19098a22936638b0e2a70616083d929fe409c`); the bundled engine reports it with `build-info`. It contains reconciled ATIV and EnCAP video work and this pinned revision declares GPL-3.0-or-later. See the shared repository's `docs/provenance.md` for source attribution. Packages include its complete license as `AVID_CORE_LICENSE.txt`.

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
