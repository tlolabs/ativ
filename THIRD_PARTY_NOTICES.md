# Third-party notices

## FFmpeg and FFprobe

ATIV builds FFmpeg 9.0.2 and ffprobe from the official FFmpeg release archive, verified with SHA-256 and the upstream release signature. The exact source, configure options and external pins are in `runtime/ffmpeg/dependency.json`.

The statically linked external libraries are x264 (GPL-2.0-or-later, stable commit b35605ace3ddf7c1a5d67a2eb553f034aef41d55) and zlib 1.3.1 (Zlib license). The resulting FFmpeg executables are GPL-2.0-or-later; version3 and nonfree components are disabled. Packages include complete corresponding source archives, build scripts, original upstream notices in `ffmpeg-licenses/`, and build/provenance records. On macOS these live in `Contents/Resources/FFmpeg`; elsewhere they accompany the engine. Preserve these materials when redistributing. See [the source-runtime documentation](docs/ffmpeg-source-runtime.md).

Windows FFmpeg packages also include the MinGW-w64 runtime notices and the GCC Runtime Library Exception or LLVM compiler-rt notices for compiler support code. Linux packages include GCC runtime copyright/exception material and GPL-3 text. These notices are preserved under `ffmpeg-licenses/toolchain-*`; compiler and package versions are recorded in `build.json`.

## Windows App SDK

The Windows application uses Microsoft Windows App SDK 2.4 under its accompanying Microsoft license and notices.

## GTK and libadwaita

The Linux application uses GTK 4 and libadwaita, distributed under the GNU Lesser General Public License 2.1 or later.

## AVID Core and Rust dependencies

ATIV links `avid-core` from https://github.com/tlolabs/avid-core at the exact revision in `runtime/core-revision`; Cargo.lock records its version. It contains reconciled ATIV and EnCAP video work and is GPL-3.0-only. See the shared repository's `docs/provenance.md` for source attribution. Packages include its complete license as `AVID_CORE_LICENSE.txt`. The host source retains GPL-3.0-or-later; the linked shared component does not grant a later-version option.

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

Inno Setup (https://jrsoftware.org/isinfo.php) builds Windows installers. linuxdeploy and appimagetool (https://github.com/linuxdeploy/linuxdeploy, https://github.com/AppImage/appimagetool) package Linux AppImages; their runtime/tool licenses apply to redistributed components. Python, Pillow and cryptography are development/release tooling and are not bundled as application runtimes. Native UI frameworks retain their platform/distribution licenses.
