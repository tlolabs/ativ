# ATIV integration with AVID Core 0.3.0

The normal ATIV application consumes Core tag `v0.3.0`, commit
`3fb68807bc7c350359e1634b32af477ea3042c16`, as an exact Cargo Git dependency
with version `=0.3.0`. The published annotated tag was resolved before changes.
Cargo.toml and Cargo.lock are the authoritative pin. No sibling checkout, copied
Core source, feature flag, alternate application or qualification architecture is used.

The reviewed contract is [Core integration.md at the pinned commit](https://github.com/tlolabs/avid-core/blob/3fb68807bc7c350359e1634b32af477ea3042c16/docs/integration.md).
Core supplies validation, presets, models, probing, encoder detection, filters,
previews, rendering, progress, cancellation, process cleanup and staged publication.
ATIV's thin adapter retains application policy, protocol and user-facing errors.
No media implementation needed to be copied or replaced: the prior extraction
already delegated these operations; this migration updates the real dependency
and production executable-selection boundary.

ATIV verifies its bundle and passes both paths to `MediaTools::from_paths`.
Missing/damaged packages and missing explicit overrides fail without trying PATH,
environment tools, a conventional Core bundle or a vendor download. Both explicit
CLI paths are required for development overrides. The old discovery API is no
longer re-exported by ATIV's adapter.

## Identity and application-owned runtime

Run the bundled `ativ-engine build-info` to read the compiled Core version, full
commit and Cargo source. The build derives these values from the lockfile and
checks them against the workspace pin. `version` retains its existing protocol.
Normal package staging and validation compare the engine identity to the pin;
`ativ-runtime.json` records it alongside FFmpeg and ATIV identities. Packaged
runtime discovery rejects mismatched Core provenance. CI also checks the actual
resolved Cargo metadata, preventing a local path override from qualifying.

FFmpeg **9.0.2** remains the latest stable release on the [official download page](https://ffmpeg.org/download.html),
checked September 23, 2026. The existing ATIV-owned source pipeline already pins
this version. Its [dependency manifest](../runtime/ffmpeg/dependency.json) records
the official archive, tag, SHA-256, release signing key, external source pins,
configure options and all six targets. See [source build instructions](ffmpeg-source-runtime.md).
Native builders compile official FFmpeg plus pinned x264/zlib source. Packages
include both tools, source archives, notices, signature and build/provenance records.
Exact recipe/target/toolchain cache keys and verification prevent stale reuse.
Changing the staging script for Core provenance invalidates the old runtime cache.

The obsolete Core runtime acquirers, candidate application and Recipe qualification
workflows were already removed by the prior ATIV source-build work and remain
absent. This migration removes the redundant `runtime/core-revision` file and
remaining use of Core discovery. Historical reports are explicitly labeled;
no active build depends on Core runtime assets, Recipe 7, or prebuilt FFmpeg vendors.
AVID Core and EnCAP are unchanged.

## Verification

The normal native workflow builds macOS ARM64/Intel, Windows x64/ARM64 and Linux
x64/ARM64. Each uses the same package scripts as distribution, with signing optional
for manual runs. Tests check the resolved Core dependency and compiled identity,
both runtime versions, architectures and provenance, normal bundled discovery,
27 preset previews, 20 aspect/flip previews, H.264/AAC exports at 1/30/240 fps,
60 fps portrait per-frame export, audio probing, output/source protection,
cancellation and actual child reaping. Missing/corrupt metadata and executables
are rejected with a usable external runtime on PATH; explicit missing overrides
are rejected with an intact adjacent runtime. Native clients/startup/installers
and packaged media validation run on every target.

Local macOS Apple Silicon verification passed on September 23, 2026:

- Locked workspace tests (15), check, formatting and clippy; ownership checks (2),
  source-builder regression tests (8), release-infrastructure tests (7).
- Clean source build, full packaged-engine media/negative/lifecycle suite,
  normal `build_and_run.sh --verify`, normal release ZIP/DMG packaging and validation.
- Both Swift native tests, including probing, preview and export through the actual
  release engine; release app startup reported `{"startup":true,"presets":27}`.
- ZIP runtime hashes, all three source archives, Core identity/license, DMG checksum
  and strict bundle signature verification passed (local ad-hoc signing).
- Clean FFmpeg/ffprobe hashes matched the previously qualified local source build
  byte for byte. The Core library and bundle provenance changed; media binaries did not.

Logs are retained under ignored `build/core-030-*.log`.

### Six-platform CI results

All six native pipelines passed against implementation commit
`bc43ed0fc3c82acc4ea2ffbf0bb65fd2c8ebb91e`. Both manual dispatches forced clean
FFmpeg source builds and used the normal native application/package workflow.
No release was published.

| Platform | Native build, pinned Core, media, lifecycle, package and startup/installer |
| --- | --- |
| macOS Apple Silicon | Passed — [run 35894450676](https://github.com/tlolabs/ativ/actions/runs/35894450676) |
| macOS Intel | Passed — same run |
| Windows ARM64 | Passed — same run |
| Linux x64 | Passed — same run |
| Linux ARM64 | Passed — same run |
| Windows x64 | Passed — [retry run 35895120766](https://github.com/tlolabs/ativ/actions/runs/35895120766) |

The first run rejected a Windows x64 zlib download whose checksum did not match
before compilation. The same official URL and unchanged pinned checksum were
independently verified, then the normal Windows workflow passed on a fresh runner.
No source pin, integrity check, test or compiler setting was relaxed. The first
run therefore has an overall failure status despite five passing native targets;
the retry provides the complete passing Windows x64 evidence at the same commit.

Completed job logs confirm compilation of Core 0.3.0, successful full packaged
media tests and missing/damaged-runtime rejection on every target. Package
validation checks the full Core source revision against the lock/pin and both
FFmpeg/ffprobe identifiers against 9.0.2. Windows includes native C# media tests,
WinUI startup, installed runtime discovery, upgrade and uninstall. Linux includes
GTK startup, AppImage extraction/launch and deb install/reinstall/uninstall.
Both macOS targets include Swift media tests and packaged application startup.
Final follow-up edits are this report and dependency-notice references only.

No integration or Core defect remains, and no Core or EnCAP source was changed.
Production signing/notarization and exact minimum-OS device execution are separate
release concerns; they do not prevent the unsigned architecture verification.
