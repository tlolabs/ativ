# Changelog

Notable changes to ATIV are recorded here using a [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) style and [Semantic Versioning](https://semver.org/).

## [Unreleased]

- Add collapsible Source Media, Format, and Destination controls with live summaries, and keep Create Video visible while scrolling.
- Standardized authenticated stable updates; corrected the Sparkle manual update command and active-export shutdown coordination. Version 0.2.5 is the local updater bridge; 0.2.6 is the next release candidate.

- Preserve cancellation status when a media operation is stopped before tool discovery begins.

### Changed

- ATIV 0.2.5 consumes AVID Core's published FFmpeg/ffprobe runtime instead of compiling its own source recipe; Mac apps are distributed as ZIP archives.
- Packaged runtime provenance follows the compiled application version, including development builds.
- Standardize project policy, documentation, dependency disclosure, and release requirements for the next release.

The existing Git history and [GitHub Releases](https://github.com/tlolabs/ativ/releases) remain the record for earlier versions.
