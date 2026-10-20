# Changelog

Notable changes to ATIV are recorded here using a [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) style and [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.7] — 2026-10-20

### Changed

- Integrate AVID Core 0.3.1 at `15f28236142c100d0a83bf19154ed6f9f5b44e75`, retaining the authenticated FFmpeg runtime pins.
- Select cached-frame Simple rendering for verified static PNG/JPEG/BMP artwork and retain PerFrame for potentially animated inputs.
- Serialize media workers, protect additional source paths, preserve existing outputs on cancellation/failure, and drain native clients before application replacement.
- Add focused inspection/cache, native rendering, animation, cancellation and publication diagnostics with measured Simple/PerFrame comparisons.
- Include the accumulated frontend, updater snapshot and GitHub Actions audit documentation changes in this source release.

### Known limitations

- Core PerFrame animated GIF export reports `Option loop not found.`; inspection and first-frame preview work.
- This local release build qualifies macOS ARM64 only. Other native targets and authenticated older-to-newer updater qualification remain separate work.

### Earlier unreleased work

- Add collapsible Source Media, Format, and Destination controls with live summaries, and keep Create Video visible while scrolling.
- Standardized authenticated stable updates; corrected the Sparkle manual update command and active-export shutdown coordination. Version 0.2.5 remains the historical local updater bridge; the 0.2.6 qualification record is retained.

- Preserve cancellation status when a media operation is stopped before tool discovery begins.

### Changed

- ATIV 0.2.5 consumes AVID Core's published FFmpeg/ffprobe runtime instead of compiling its own source recipe; Mac apps are distributed as ZIP archives.
- Packaged runtime provenance follows the compiled application version, including development builds.
- Standardize project policy, documentation, dependency disclosure, and release requirements for the next release.

The existing Git history and [GitHub Releases](https://github.com/tlolabs/ativ/releases) remain the record for earlier versions.
