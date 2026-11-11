# Release integration status

ATIV pins AVID Core 0.3.3 at `8e27a86ec106028d93130de35a35c0eeda7a9ce3`. The [integration record](core-0.3.3-integration.md) records verification for that source. Authenticated FFmpeg/ffprobe platform releases remain independently pinned in `runtime/platform-runtimes.json`.

Stable source releases use annotated version tags matching the workspace version and exact tested commit. Automatic CI runs weekly Linux/Windows native compilation and basic smoke tests only for a new stable source-release tag that has not already been attempted. It does not build macOS, retry tags or publish releases. Main pushes and tags do not trigger automatic builds or publication. [AGENTS.md](../AGENTS.md) supersedes the former automation described in historical reports.

macOS arm64 and Intel, Windows x64 and ARM64, and Linux x64 and ARM64 packages require deliberate native qualification. Each artifact must pass its own build, package-integrity, architecture, runtime-dependency, launch and functional checks before publication. Successful targets may publish independently; absent or failed targets remain explicit limitations. A source-release tag and a scheduled smoke result are not native artifact qualification. Preserve package digests, provenance and public-download checks when using the retained publication tools. Unsigned direct downloads do not enter the signed automatic-update feed.

Standard macOS direct downloads require Developer ID signing, Apple notarization acceptance, stapling and final Gatekeeper validation. Other platforms retain their existing signing policy. Authenticated updater feeds retain their signature, installed-key, and upgrade verification requirements; this direct-download path does not generate or alter signed update metadata.

The previous all-target application acceptance ledger and signed-package promotion process is [historical](historical/release-integration-before-nonblocking.md). Its pending evidence is not presented as current qualification. Existing tags and published asset bytes remain immutable.
