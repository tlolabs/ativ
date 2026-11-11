# Dependencies

ATIV pins the Rust graph in `Cargo.lock` and its direct AVID Core Git revision in `Cargo.toml`. `docs/dependency-inventory.json` is the machine-readable source inventory. Release packages also carry exact license texts gathered by `script/collect_licenses.py`, FFmpeg source/build records and original notices; see [third-party notices](../THIRD_PARTY_NOTICES.md). Check the inventory whenever a dependency changes.

| Direct dependency | Purpose and source | License and distribution |
| --- | --- | --- |
| AVID Core 0.3.3 | Shared media model/rendering from `tlolabs/avid-core`, exact local Git commit with unmodified checked-in source replacement | GPL-3.0-or-later, linked into the engine. |
| AVID Core Apple transcription snapshot | Immutable reviewed archive in `vendor/avid-transcription`, acquired under `build/transcription-core`; separate from the Rust pin | Core GPL-3.0-or-later plus preserved SDK/model notices; linked only into the optional Apple silicon/macOS-14 helper. |
| WhisperKit / Argmax OSS Swift | Revision `9f99b5cb6a907730543823ad271b82532782a899` | MIT; original license and adapted-tokenizer notice retained. |
| FluidAudio | Revision `ee78635d23d52379117554ba72358b65a0612447` | Apache-2.0 SDK; model-weight licenses tracked separately. |
| MLX Audio Swift / MLX Swift | `df2a2546705f50ca267037702a34cd63aa6e35a6` / exact MLX `0.33.0`; transitive identities in helper `Package.resolved` | MIT SDKs; upstream licenses packaged. |
| TurboJPEG / OxiPNG | Core-owned JPEG/PNG implementation, transitively locked since 0.3.2; no independent ATIV optimizer | Original wrapper/native notices bundled by `collect_licenses.py`; see Core image notices. |
| FFmpeg 9.0.1 / ffprobe | Local media decode, composition and export; authenticated independent platform releases in `runtime/platform-runtimes.json`, with explicit legacy `ffmpeg-9.0.1-r7.1` compatibility selection | Configured GPL-2.0-or-later executable, bundled with corresponding source and notices. |
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

The transcription archive SHA-256 is
`4234053bad548df25c68949265cb32b4052091856e6da6ad2d0710640f8f67ae`.
Its manifest records all 34 files from local Core 0.3.3; it does not establish GitHub publication. The Apple code, model catalog, SDK pins and notices are unchanged from 0.3.2. The installed-model catalog pins weights, tokenizers,
capabilities, and notices independently of SDK code. Weights are optional and not
shipped in ATIV by default. The shared model cache can be reused by EnCAP without
changing artifact verification or cross-process leases. See
[transcription integration](transcription-integration.md) for support, persistence,
packaging, and the shared-renderer gap.
