# Third-party notices

## FFmpeg and FFprobe

ATIV builds FFmpeg 9.0.2 and ffprobe from the official FFmpeg release archive, verified with SHA-256 and the upstream release signature. The exact source, configure options and external pins are in `runtime/ffmpeg/dependency.json`.

The statically linked external libraries are x264 (GPL-2.0-or-later, stable commit b35605ace3ddf7c1a5d67a2eb553f034aef41d55) and zlib 1.3.1 (Zlib license). The resulting FFmpeg executables are GPL-2.0-or-later; version3 and nonfree components are disabled. Packages include complete corresponding source archives, build scripts, original upstream notices in `ffmpeg-licenses/`, and build/provenance records. On macOS these live in `Contents/Resources/FFmpeg`; elsewhere they accompany the engine. Preserve these materials when redistributing. See [the source-runtime documentation](docs/ffmpeg-source-runtime.md).

Windows FFmpeg packages also include the MinGW-w64 runtime notices and the GCC Runtime Library Exception or LLVM compiler-rt notices for compiler support code. Linux packages include GCC runtime copyright/exception material and GPL-3 text. These notices are preserved under `ffmpeg-licenses/toolchain-*`; compiler and package versions are recorded in `build.json`.

## Windows App SDK

The Windows application uses Microsoft Windows App SDK 2.4 under its [Microsoft Software License Terms](https://www.nuget.org/packages/Microsoft.WindowsAppSDK.WinUI/2.3.6/License) and package `NOTICE.txt`. Self-contained deployment copies its runtime files into the application package. Windows ML files have [separate Microsoft terms](https://www.nuget.org/packages/Microsoft.Windows.AI.MachineLearning/2.1.74/License). These terms apply to the Microsoft components; they are not relicensed as GPL. The exact current ZIP contents, including the Windows SDK projection, are in [the Windows licensing audit](docs/WINDOWS_LICENSING.md). Future packages must carry the applicable Microsoft terms and notices alongside the binaries; the already published v0.2.4 ZIPs omit them.

The self-contained .NET 8 runtime and `System.Numerics.Tensors` use MIT terms according to their [Microsoft](https://www.nuget.org/packages/Microsoft.NETCore.App.Runtime.win-x64/8.0.30) and [NuGet](https://www.nuget.org/packages/System.Numerics.Tensors/9.0.0) package metadata. Preserve their copyright and license notices in future packages.

The three WebView2 SDK DLLs in the Windows ZIP are covered by the following [Microsoft WebView2 package license](https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.3719.77/License). Its copyright notice, conditions and disclaimer must accompany binary redistribution:

> Copyright (C) Microsoft Corporation. All rights reserved.
>
> Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
>
> * Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
> * Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
> * The name of Microsoft Corporation, or the names of its contributors may not be used to endorse or promote products derived from this software without specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

## GTK and libadwaita

The Linux application uses GTK 4 and libadwaita, distributed under the GNU Lesser General Public License 2.1 or later.

## AVID Core and Rust dependencies

ATIV links `avid-core` from https://github.com/tlolabs/avid-core at the exact revision in Cargo.toml and Cargo.lock (v0.3.0, `3fb68807bc7c350359e1634b32af477ea3042c16`); the bundled engine reports it with `build-info`. It contains reconciled ATIV and EnCAP video work and is GPL-3.0-only. See the shared repository's `docs/provenance.md` for source attribution. Packages include its complete license as `AVID_CORE_LICENSE.txt`. The host source retains GPL-3.0-or-later; the linked shared component does not grant a later-version option.

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

Inno Setup (https://jrsoftware.org/isinfo.php) builds Windows installers. linuxdeploy and appimagetool (https://github.com/linuxdeploy/linuxdeploy, https://github.com/AppImage/appimagetool) package Linux AppImages; their runtime/tool licenses apply to redistributed components. Python, Pillow and cryptography are development/release tooling and are not bundled as application runtimes. Native UI frameworks retain their platform/distribution licenses.
