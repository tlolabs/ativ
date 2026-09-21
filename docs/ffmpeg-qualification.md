# ATIV FFmpeg 9.0.2 qualification

This records ATIV-owned builds, independent of the historical Core runtime ledger. No production release is published by qualification. Source: official FFmpeg 9.0.2 archive, verified with pinned SHA-256 and upstream OpenPGP signature. External libraries: source-built x264 and zlib.

| Target | Source/build | Package/media/lifecycle |
|---|---|---|
| macOS Apple Silicon | Passed locally and in native CI | Full package/media/lifecycle/native startup passed |
| macOS Intel | Passed in native CI | Full package/media/lifecycle/native startup passed |
| Windows x64 | Passed in native CI | Portrait-filter crash under Clang; compiler diagnosis in progress |
| Windows ARM64 | Passed in native CI; verified cache reuse | Full package/media/lifecycle/native client and installer passed |
| Linux x64 | Passed in native CI | Final package/media rerun in progress |
| Linux ARM64 | Passed in native CI | Full package/media/lifecycle/GTK/deb/AppImage passed |

Local ATIV Rust workspace tests, clippy and runtime ownership guard passed. The existing Core API and commit are unchanged. Minimum OS declarations are build targets; execution on a newer hosted image alone does not prove behavior on the exact minimum OS.

## Local Apple Silicon evidence

On macOS 26.7 with Apple Clang 21, two clean builds produced byte-identical FFmpeg and ffprobe. The later download-only recipe changes retained those same binary hashes:

- FFmpeg: `dab4050515804bc55ad9049e077f245837465253833dde092e415a10ae27c5c0`
- ffprobe: `e3bdb03d4d6f756d978ba728b8f81d4f95c6e654e516f39f6bdb94ed2c68c169`

The normal development ZIP/DMG was built, its ZIP binary hashes matched the signed manifest, and the ZIP contained all three corresponding-source archives. All 14 Rust tests, 7 release-infrastructure tests, ownership checks, clippy and the actual media contract passed. The contract now includes per-frame mode and verifies the cancelled FFmpeg child PID is gone. Both Swift native integration tests passed, and the packaged app emitted `{"startup":true,"presets":27}`. The local runtime cache reused the exact build without recompiling. These are native execution results on this host, not a macOS 13 execution claim.

Local logs are in ignored `build/ffmpeg-*.log`. Cross-platform acceptance remains pending until the final CI results below are recorded.

## Native qualification evidence

- [Run 35561441899](https://github.com/tlolabs/ativ/actions/runs/35561441899): both macOS targets and Linux ARM64 passed the complete native package pipeline.
- [Run 35562441460](https://github.com/tlolabs/ativ/actions/runs/35562441460): Windows ARM64 restored and verified its source-built cache, then passed all media, packaging, native client and installed-runtime checks. Windows x64 reproduced an access violation in the 90×160 portrait filter.
