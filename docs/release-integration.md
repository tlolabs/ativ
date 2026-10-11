# Release integration status

ATIV's native workflow builds and verifies macOS arm64 and Intel, Windows x64 and ARM64, and Linux x64 and ARM64 independently. On stable annotated tags, the release job downloads only artifacts uploaded by completed native jobs in the same run, checks target filenames, package contents and architecture, verifies GitHub provenance attestations and downloaded bytes, and publishes passing targets. Failed targets remain absent from the release and visible in Actions.

Direct downloads may be unsigned. Signing and notarization can be requested separately when configured. Authenticated updater feeds retain their signature, installed-key, and upgrade verification requirements; this direct-download path does not generate or alter signed update metadata.

The previous all-target application acceptance ledger and signed-package promotion process is [historical](historical/release-integration-before-nonblocking.md). Its pending evidence is not presented as current qualification. Existing tags and published asset bytes remain immutable.
