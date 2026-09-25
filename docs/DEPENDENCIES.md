# Dependencies

ATIV pins the Rust graph in `Cargo.lock` and its direct AVID Core Git revision in `Cargo.toml`. `docs/dependency-inventory.json` is the machine-readable source inventory. Release packages also carry exact license texts gathered by `script/collect_licenses.py`, FFmpeg source/build records and original notices; see [third-party notices](../THIRD_PARTY_NOTICES.md). Check the inventory whenever a dependency changes.

| Direct dependency | Purpose and source | License and distribution |
| --- | --- | --- |
| AVID Core 0.3.0 | Shared media model/rendering from `tlolabs/avid-core`, pinned Git commit | GPL-3.0-only, linked into the engine; limits the combined work to GPL v3 pending rights review. |
| FFmpeg 9.0.2 / ffprobe | Local media decode, composition and export; official authenticated FFmpeg source | Configured GPL-2.0-or-later executable, bundled with corresponding source and notices. |
| x264 | H.264 encoder, pinned upstream source archive | GPL-2.0-or-later, statically linked into FFmpeg. |
| zlib | Compression support, pinned upstream source archive | zlib license, statically linked into FFmpeg. |
| Sparkle 2.9.6 | macOS GitHub Release update checks | Permissive upstream license; framework and notice bundled. |
| Microsoft Windows App SDK 2.4 / WinUI 2.3.6 | Native Windows UI and self-contained runtime from Microsoft NuGet packages | Microsoft Software License Terms; the [Windows audit](WINDOWS_LICENSING.md) inventories exact release files, license links, GPL System Library analysis, and a framework-dependent alternative. The broad metapackage currently includes unused AI/ML/Search/Widgets files. |
| .NET 8 and WebView2 SDK | Windows managed runtime and WinUI transitive WebView2 SDK from Microsoft NuGet | .NET MIT and WebView2 SDK three-clause BSD-style; see exact versions in the [Windows binary inventory](windows-distribution-inventory.json). The WebView2 browser runtime is not bundled. |
| GTK 4, libadwaita 1.4, json-glib | Native Linux UI from distribution repositories | LGPL-family terms for GTK/libadwaita; AppImage bundling retains component notices. |
| Rust crates (`serde`, `reqwest`, `ring`, etc.) | Serialization, signed updates, TLS and local file handling from crates.io | Exact versions and checksums in `Cargo.lock`; package license files are copied into releases. |
| Python build requirements | Icon generation, update metadata signing and release tooling; pinned in `script/requirements-build.txt` | Build-time only; not shipped as an application runtime. |
| linuxdeploy, appimagetool and runtime | Linux AppImage creation from hash-verified downloads | Build tools and AppImage runtime retain their upstream terms. |

Windows and Apple operating-system frameworks are platform dependencies. CI and package scripts acquire additional compilers and tools; their versions should be recorded in build provenance. The inventory is exhaustive for the locked Rust graph and enumerates the direct native/source inputs; it does not substitute for a final scan of binary contents or legal review of Windows App SDK redistribution.
