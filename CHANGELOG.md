# Changelog

Notable changes to ATIV are recorded here using a [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) style and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Optional offline transcription on Apple silicon with macOS 14+, using the verified shared AVID Core model catalog and model cache through an isolated helper.
- Native model installation/import/verification, transcript corrections and realignment, versioned source-bound documents, word-highlight caption preview, and SRT/WebVTT sidecars.
- Reproducible reviewed-source acquisition, nested helper resources and Swift runtime packaging, dependency/model notices, cancellation and update/quit coordination.

### Limitations

- Existing macOS 13/Intel and Windows/Linux media workflows remain supported; these Apple transcription engines are unavailable there. MP4 caption burn-in requires an additional shared Core render contract.

## [0.2.8] — 2026-10-29

### Fixed

- Collect dependency licenses when invoked outside the repository, including relative destination paths.
- Accept native macOS file drops and raw paths without changing literal filename characters or spaces; reject remote and relative URLs.
- Regenerate suggested output names when they collide with either media input, including repeated filename collisions and file aliases.
- Recognize normalized paths, symbolic links, hard links, and filesystem case behavior when protecting source files in both frontends; preserve distinct custom destinations and Qt filenames containing trailing spaces.

### Changed

- Align workspace, Qt, dependency inventory, and local benchmark package selection with version 0.2.8.
- Isolate Qt workflow and accessibility test preferences in temporary directories.

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
