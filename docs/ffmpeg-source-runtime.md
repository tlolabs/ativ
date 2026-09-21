# ATIV-owned FFmpeg source runtime

ATIV builds and packages its own FFmpeg and ffprobe. It does not acquire runtime assets from AVID Core or any binary distributor. The unchanged Core 0.2.1 API remains pinned to `eab97dd043187aa8b7a1cae4eb2c1228fa25a9db` as a Cargo Git dependency; a neighboring Core checkout is neither read nor modified by the build.

## Upstream and dependency record

[`runtime/ffmpeg/dependency.json`](../runtime/ffmpeg/dependency.json) is the machine-readable dependency lock and configure profile. On September 20, 2026, the [official FFmpeg download page](https://www.ffmpeg.org/download.html) identified **9.0.2**, released September 18, as the latest stable release. The authoritative source is [ffmpeg-9.0.2.tar.xz](https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz), corresponding to tag `n9.0.2` in `https://git.ffmpeg.org/ffmpeg.git`.

The archive SHA-256 is `8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e`. Every clean build verifies that checksum and its detached upstream OpenPGP signature using the checked-in release key, in a temporary isolated keyring. The required signer fingerprint is `FCF986EA15E6E293A5644F10B4322F04D67658D8`, published by FFmpeg. Signature failure or a changed archive fails the build. No mirror or older-version fallback is implemented.

The two external libraries are also built from checksum-pinned upstream source:

| Library | Pin | License | Purpose |
|---|---|---|---|
| x264 | stable commit `b35605ace3ddf7c1a5d67a2eb553f034aef41d55`, official VideoLAN archive | GPL-2.0-or-later | ATIV software H.264 export |
| zlib | 1.3.1, official zlib fossil archive | Zlib | PNG input and previews |

The combined FFmpeg executables use GPL-2.0-or-later. `--enable-version3` and nonfree components are disabled. The app's own licenses do not replace these obligations. Every package carries the exact source archives, upstream license texts, source signature/key, and build scripts. Source archives are alongside the executables in `sources/` on Windows/Linux and in `Contents/Resources/FFmpeg/sources/` on macOS. The recipe can be reconstructed using the included scripts and dependency record; their normal repository layout is `script/` and `runtime/ffmpeg/`. Redistributors must preserve these materials and applicable notices. Platform system libraries are dynamically linked; x264 and zlib are static. No Homebrew/MSYS2 codec-library binary is linked.

## Build profile and reproducibility

The dependency record contains the complete common and target-specific configure options. The profile enables FFmpeg/ffprobe, static FFmpeg libraries, libx264, zlib, software AAC, PNG and media-fixture encoders, scaling/resampling, and ATIV's composition/flip/loop filters. All available built-in decoders, demuxers and parsers remain enabled to preserve the broad image/audio file pickers (including MP3, AAC/ALAC, FLAC, Vorbis, Opus, WMA, AIFF/PCM, PNG/JPEG/WebP/BMP/TIFF). It does not enable unrelated external HEVC or MP3 exporters: ATIV's existing API requests H.264/AAC. macOS retains optional H.264 VideoToolbox support. Networking, capture devices, ffplay, documentation, debugging, external-library autodetection and nonfree code are disabled; only file/pipe protocols are enabled. `lavfi` exists for local test fixtures.

Assembly is disabled in the initial portable recipe, reducing assembler/platform variability while retaining codec functionality. This can reduce encoding speed; restoring assembly requires qualification and a recipe change. CPU-native tuning is not used. Builds set `SOURCE_DATE_EPOCH=1789699562`, `TZ=UTC`, `LC_ALL=C`, deterministic archive settings and path mapping for x264/zlib, and omit Windows PE timestamps. FFmpeg uses a fixed installation prefix and relative include/link paths. Toolchain/SDK updates may change bytes; this is an as-reproducible-as-practical native build, not a claim of identical output across compilers or operating systems.

`build.json` records the compiler, target triple, SDK/linker/tool versions, runner image, effective configure commands, recipe digest, version output and original binary hashes. `payload.json` hashes the corresponding source and metadata. `config.log`, `config.h`, `capabilities.json` and `linkage.json` preserve build and capability evidence. The builder rejects unexpected machine types, versions, missing required codecs/filters, and non-system dynamic dependencies.

## Native builders and caching

The native workflow uses macOS 15 ARM64/Intel, Windows 2025 x64, Windows 11 ARM64, and Ubuntu 24.04 x64/ARM64 builders. Windows uses MSYS2 CLANG64/CLANGARM64, with native target compilers and static library builds. The MSYS shell may be emulated; GitHub runner architecture identifies the native host, and PE machine validation confirms the resulting binaries. MSYS2 provides build tools only; it does not supply FFmpeg. macOS uses Xcode Clang and the macOS 13 deployment target; Linux uses GCC and the Ubuntu 24.04 glibc baseline.

The cache key hashes the dependency record (including FFmpeg version/checksum/configuration and external pins), recipe scripts, release key, target, and actual compiler/toolchain/SDK/runner inputs. There are no partial restore keys. Restored payloads are revalidated before use. Verified runtimes are saved before application tests, so an unrelated app failure does not discard a successful source build. Unrelated Rust/UI edits reuse a matching runtime. CI's `clean_ffmpeg: true` bypasses cache restoration and saving and rebuilds all source. A failed or damaged cache fails verification; use a clean dispatch to replace the build input. Neither signing nor notarization gates manual unsigned qualification.

```sh
# Native target only; source build tools and Python 3.11+ are required.
# macOS: use full Xcode (also required for the app).
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
python3 script/ffmpeg_build.py build macos-arm64 --clean
python3 script/ffmpeg_runtime.py provision macos-arm64
./script/test_engine_integration.sh macos-arm64
./script/package_macos.sh arm64

# CI: all six native targets, no publication.
gh workflow run native-release.yml --ref YOUR_BRANCH -f platform=all -f clean_ffmpeg=true -f sign_macos=false
```

Valid target IDs are `macos-arm64`, `macos-x86_64`, `windows-x86_64`, `windows-arm64`, `linux-x86_64`, and `linux-arm64`. Windows source builds run in the corresponding MSYS2 shell. Other platforms need C compiler/make/pkg-config/GnuPG. Build tools may come from the OS package manager; distributed FFmpeg and linked codec libraries may not.

## Packaged runtime and tests

Normal packaging calls `ffmpeg_runtime.py provision`, `stage`, `finish`, and `validate`. The binaries sit beside `ativ-engine`: `Contents/MacOS/` on macOS, the installation directory on Windows, and `usr/lib/ativ` (or `ativ-development`) on Linux. macOS metadata moves to `Contents/Resources/FFmpeg` before sealing the app. `finish` records post-signing hashes separately from the verified original hashes.

The Rust host compares the packaged dependency record with the embedded ATIV pin, checks target/provenance and payload/binary hashes, then calls the existing Core discovery API with both absolute paths and `search_path: false`. Missing, damaged, or mismatched bundles fail with a structured error even when a working pair is on PATH. Development tests may deliberately supply **both** `--ffmpeg` and `--ffprobe`; a partial override fails. No automatic system fallback exists. CI's `ATIV_FFMPEG_RUNTIME` selects only a manifest-verified ATIV source payload for packaging, not arbitrary executable paths.

Each native CI job runs the normal ATIV Rust tests, actual staged-engine media tests, package validation, and native client/startup/installer checks. The contract covers all 27 presets, 20 flip/aspect previews, H.264/AAC exports at 1/30/240 fps, probing, corrupted input, output preservation, cancellation and cleanup. Packaged discovery is tested with PATH empty, and negative tests put a usable runtime on PATH. Build evidence and application packages are retained as CI artifacts; manual dispatches never publish a release.

## Updating FFmpeg

1. Check the official download page for the latest stable release; fetch the archive and detached signature.
2. Verify the signature with the published release fingerprint before recording the new SHA-256.
3. Update `source.version`, tag, URLs, checksum and `source_date_epoch` in `dependency.json`; increment `recipe` if build behavior changes. Review configure changes and external-library licenses.
4. Dispatch the six-target workflow with `clean_ffmpeg=true`. Require build, package, media and cleanup evidence for every target before accepting the update.
5. Commit the lock/recipe and qualification results. Ordinary releases use the same build path. Do not publish from a qualification branch.

Current evidence and any outstanding gates are recorded in [ffmpeg-qualification.md](ffmpeg-qualification.md). Earlier Core runtime migration notes are historical and do not describe the current acquisition path.
