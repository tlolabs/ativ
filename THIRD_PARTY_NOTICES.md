# Third-party notices

## FFmpeg 9.0.1

A.T.I.V. distribution packages include FFmpeg and ffprobe 9.0.1. FFmpeg is available from <https://ffmpeg.org/> under the GNU Lesser General Public License 2.1 or later, with optional components that can make a particular build subject to GNU General Public License 2 or later. A.T.I.V. itself is GPL-3.0-or-later and release builds enable GPL components such as libx264.

Release packaging must include the exact FFmpeg build's license and configuration alongside this notice. Source and corresponding-build information are available from the distributor named in the release manifest and from <https://ffmpeg.org/download.html>.

Windows and Linux packages use checksum-pinned GPL builds from BtbN's FFmpeg-Builds project. macOS packages use architecture-specific, checksum-pinned static builds distributed by Martin Riedl. The pinned URLs and SHA-256 values are recorded in `script/fetch_ffmpeg.sh` and are verified before any binary is copied or signed.

## Windows App SDK

The Windows application uses Microsoft Windows App SDK 2.4 under its accompanying Microsoft license and notices.

## GTK and libadwaita

The Linux application uses GTK 4 and libadwaita, distributed under the GNU Lesser General Public License 2.1 or later.

## AVID Core and Rust dependencies

ATIV links `avid-core` 0.1.0 from https://github.com/tlolabs/avid-core at revision `0cce6ba838827d0bed540efc98731e74a1014456`. It contains reconciled ATIV and EnCAP video work and is GPL-3.0-only. See the shared repository's `docs/provenance.md` for source attribution. Packages include its complete license as `AVID_CORE_LICENSE.txt`. The host source retains GPL-3.0-or-later; the linked shared component does not grant a later-version option.

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
