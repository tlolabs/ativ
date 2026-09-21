# ATIV FFmpeg 9.0.2 qualification

ATIV owns these builds independently of the historical Core runtime ledger. The official FFmpeg 9.0.2 source archive is verified with its pinned SHA-256 and upstream OpenPGP signature. x264 and zlib are built from checksum-pinned upstream source. No production release was published.

| Target | Native toolchain | Source/build | Package/media/lifecycle/native checks |
|---|---|---|---|
| macOS Apple Silicon | Apple Clang 17 in CI; Clang 21 locally | Passed | Passed |
| macOS Intel | Apple Clang 17 | Passed | Passed |
| Windows x64 | MSYS2 UCRT64 / GCC 16.2 | Passed | Passed |
| Windows ARM64 | MSYS2 CLANGARM64 / Clang 22.1.8 | Passed | Passed |
| Linux x64 | Ubuntu GCC 13.3 | Passed | Passed |
| Linux ARM64 | Ubuntu GCC 13.3 | Passed | Passed |

[Native run 35564197949](https://github.com/tlolabs/ativ/actions/runs/35564197949) passed both macOS targets, both Linux targets and Windows ARM64 at `0280b23d035e0012bb1831db565479903b76eda5`. Its Windows x64 compile succeeded but the notice collector expected the newer MSYS2 `libgcc` directory; the installed package used `gcc-libs`. The collector now supports both verified layouts, requires the GPL and runtime-exception notices, and checks them before compilation. [Windows run 35564915234](https://github.com/tlolabs/ativ/actions/runs/35564915234) passed both complete Windows pipelines with that Windows-only correction at `8f9d881fdd21d5d3eccb0b833f4cffc4da53206d`. The FFmpeg source and configure profile are unchanged by the notice-layout correction. Subsequent edits are documentation and CLI help only; engine tests and cache reuse were checked locally after the help edit.

Each complete native pipeline verifies source acquisition/signature/checksums, both executables' versions and architecture, ATIV's normal Rust tests, 27 presets, 20 aspect/flip previews, four exports (including per-frame mode), probing, input/output protection, cancellation and actual child-process cleanup. Missing/damaged bundles fail even with usable tools on PATH. Package validation uses an empty PATH, and native client/startup/installer checks exercise the installed pair. CI artifacts retain source build logs, provenance records and native packages. The eight source-builder regression tests, ownership guard, release-infrastructure tests, Rust formatting and clippy pass.

Minimum OS declarations are build targets; execution on a newer hosted image alone does not prove behavior on the exact minimum OS. Signing/notarization is not required for this source-build qualification.

## Reproducibility and cache evidence

On macOS 26.7 with Apple Clang 21 and SDK 26.5, repeated clean builds, including recipe 2 and the final notice-layout correction, produced byte-identical executables:

- FFmpeg: `dab4050515804bc55ad9049e077f245837465253833dde092e415a10ae27c5c0`
- ffprobe: `e3bdb03d4d6f756d978ba728b8f81d4f95c6e654e516f39f6bdb94ed2c68c169`

The final local media/discovery tests and normal ZIP/DMG build passed. ZIP inspection verified both signed binary hashes and all three corresponding-source archives. Both Swift native integration tests passed, and the packaged app reported `{"startup":true,"presets":27}`. Local logs are in ignored `build/ffmpeg-*.log`.

Local exact-key cache reuse avoided compilation, including after a CLI-help-only application edit. [Windows run 35562441460](https://github.com/tlolabs/ativ/actions/runs/35562441460) also restored and revalidated a source-built runtime cache before application tests; ARM64 completed the entire native pipeline. Recipe changes invalidated the caches and caused new source builds. The manifest/target/toolchain invalidation and corrupt-source rejection tests pass. `clean_ffmpeg=true` and local `--clean` remain available for forced rebuilds.

## Windows x64 compiler choice

The initial CLANG64 build reproduced exit `0xC0000005` on the existing 90×160 portrait/blur composition, independently of the Core API. Single-threaded filtering and disabled runtime CPU flags also failed. Native GDB stopped at `filter_frame+1312`, on a `cvtps2dq` memory instruction. The same official, unmodified FFmpeg source and configure profile built with UCRT64/GCC passed all six diagnostic variants and exited normally under GDB. [Compiler comparison run 35563331551](https://github.com/tlolabs/ativ/actions/runs/35563331551) retains the trace and outcomes. Recipe 2 therefore selects GCC for Windows x64 and keeps Clang for ARM64. No FFmpeg patch, Core API change or omitted regression test is involved.

The Core API/revision remains pinned to `eab97dd043187aa8b7a1cae4eb2c1228fa25a9db`. Neither the neighboring AVID Core repository nor EnCAP was modified. No Core FFmpeg runtime asset or third-party prebuilt FFmpeg/ffprobe is required.

## Remaining FFmpeg-specific blockers

None for the requested six-target source-build migration. The Windows x64 filter crash is resolved by the qualified GCC toolchain. Assembly remains disabled as a documented portability/performance tradeoff. Exact minimum-OS execution and production signing/notarization are separate from this qualification.
