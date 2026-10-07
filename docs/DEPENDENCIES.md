# Dependencies

ATIV pins the Rust graph in `Cargo.lock` and its direct AVID Core Git revision in `Cargo.toml`. `docs/dependency-inventory.json` is the machine-readable source inventory. Release packages also carry exact license texts gathered by `script/collect_licenses.py`, FFmpeg source/build records and original notices; see [third-party notices](../THIRD_PARTY_NOTICES.md). Check the inventory whenever a dependency changes.

| Direct dependency | Purpose and source | License and distribution |
| --- | --- | --- |
| AVID Core 0.3.0 | Shared media model/rendering from `tlolabs/avid-core`, pinned Git commit | GPL-3.0-or-later, linked into the engine. |
| FFmpeg 9.0.1 / ffprobe | Local media decode, composition and export; authenticated Core runtime release `ffmpeg-9.0.1-r7.1` | Configured GPL-2.0-or-later executable, bundled with corresponding source and notices. |
| x264 | H.264 encoder, pinned upstream source archive | GPL-2.0-or-later, statically linked into FFmpeg. |
| x265 | HEVC encoder in the shared Core runtime | GPL-2.0-or-later, statically linked into FFmpeg. |
| LAME | MP3 encoder in the shared Core runtime | LGPL-2.0-or-later, statically linked into FFmpeg. |
| zlib | Compression support, pinned upstream source archive | zlib license, statically linked into FFmpeg. |
| Sparkle 2.9.6 | macOS GitHub Release update checks | Permissive upstream license; framework and notice bundled. |
| Qt 6 Widgets | Shared Windows/Linux presentation and internal macOS reference | LGPL-3.0 / GPL-3.0; dynamically linked libraries and plugins deployed with application. |
| Rust crates (`serde`, `reqwest`, `ring`, etc.) | Serialization, signed updates, TLS and local file handling from crates.io | Exact versions and checksums in `Cargo.lock`; package license files are copied into releases. |
| Python build requirements | Icon generation, update metadata signing and release tooling; pinned in `script/requirements-build.txt` | Build-time only; not shipped as an application runtime. |
| linuxdeploy, appimagetool and runtime | Linux AppImage creation from hash-verified downloads | Build tools and AppImage runtime retain their upstream terms. |

Windows and Apple operating-system frameworks are platform dependencies. CI and package scripts acquire additional compilers and tools; their versions should be recorded in build provenance. The inventory is exhaustive for the locked Rust graph and enumerates the direct native/source inputs; it does not substitute for a final scan of binary contents or final binary notice coverage. The [older Windows App SDK audit](WINDOWS_LICENSING.md) applies only to published legacy ZIPs.
