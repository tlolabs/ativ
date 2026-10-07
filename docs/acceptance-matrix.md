> Current release integration: the automated results below are historical unless tied to the new exact application commit, Core pair and final package. The next Windows package is a portable ZIP and Linux package an AppImage. Installer/deb/DMG results do not qualify them. Local Apple credentials are now usable; no Azure account exists. New real upgrades and manual acceptance remain awaiting evidence. Core uses the approved hosted-runner OS policy; older OS rows below are untested compatibility claims, not proof from deployment targets.

# Cross-platform acceptance matrix

This is an evidence ledger, not a claim that unexecuted checks passed. `A` denotes an automated check implemented in CI; `M` denotes manual acceptance still required. Every row applies to each target: macOS Apple Silicon, macOS Intel, Windows x64, Windows ARM64, Linux x64 and Linux ARM64. Exact CI results are recorded below after validation.

| Requirement | macOS ARM64 | macOS Intel | Windows x64 | Windows ARM64 | Linux x64 | Linux ARM64 |
| --- | --- | --- | --- | --- | --- | --- |
| Rust/shared core build and tests | A | A | A | A | A | A |
| Native application build | A | A | A | A | A | A |
| Native launch + 27 decoded presets | A | A | A | A | A | A |
| Native UI toolkit and process boundary | A + M | A + M | A + M | A + M | A + M | A + M |
| Artwork input, audio input, Unicode paths | A + M | A + M | A + M | A + M | A + M | A + M |
| Styled preview and both flips | A + M | A + M | A + M | A + M | A + M | A + M |
| MP4 H.264/AAC export and source preservation | A | A | A | A | A | A |
| Cancellation and previous-output preservation | A + M | A + M | A + M | A + M | A + M | A + M |
| Progress, ETA, errors and final publication | A + M | A + M | A + M | A + M | A + M | A + M |
| Bundled FFmpeg and ffprobe without PATH | A | A | A | A | A | A |
| Accessibility semantics / screen reader | M VoiceOver | M VoiceOver | M Narrator | M Narrator | M Orca | M Orca |
| Keyboard navigation and logical focus | M | M | M | M | M | M |
| Light / Dark / System appearance | M | M | M | M | M | M |
| HiDPI, scaled text and multiple displays | M | M | M | M | M | M |
| Native icon resources / visible app identity | A + M | A + M | A + M | A + M | A + M | A + M |
| Version/channel metadata | A | A | A | A | A | A |
| Package structure and machine type | A | A | A | A | A | A |
| Clean-machine installation | M | M | M portable ZIP | M portable ZIP | M AppImage | M AppImage |
| Reinstallation / real version upgrade | M | M | M portable upgrade | M portable upgrade | M AppImage upgrade | M AppImage upgrade |
| Automatic update / manual update check | M | M | M | M | M | M |
| Signed feed / corrupt download rejection | A | A | A | A | A | A |
| Actual signed update installation and restart | M | M | M | M | M | M |
| Removal without deleting user media | M | M | M portable removal | M portable removal | M AppImage removal | M AppImage removal |
| Signing and timestamp verification | A + M | A + M | A when configured | A when configured | Signed update metadata | Signed update metadata |
| Notarization and stapling | A when configured + M | A when configured + M | N/A | N/A | N/A | N/A |
| Package checksums/integrity | A | A | A | A | A | A |
| Minimum supported OS runtime | M macOS 13 | M macOS 13 | M Win10 1809 | M Win10 1809 | M baseline glibc/desktop dependencies | M baseline glibc/desktop dependencies |

## Shared Qt presentation migration evidence

The shared Qt 6 Widgets implementation passes the shared Rust and release-infrastructure gate, Windows portable targets, Linux AppImages, native macOS production targets, and the internal Apple Silicon Qt reference. The Qt test suite (`ativ-qt-tests`) and Python native integration harness verify engine presets, probe, preview scaling, export, cancellation, and settings migration. The internal reference passes actual bundle startup plus probe, preview and export integration; its separately downloadable CI artifact is `ATIV-INTERNAL-REFERENCE-macos-arm64`.

These automated results do not establish interactive file-picker, drag/drop, screen-reader, high-DPI, older-OS or signed older-to-newer update behavior. This run was build/qualification only; it did not sign or publish a production release. The 0.2.6 updater qualification remains [open](updates/qualification-20261001.md).

## Historical automated evidence

The WinUI, GTK Debian, and former Avalonia results document retired formats and do not qualify the Qt packages.

Local Apple Silicon: Rust workspace (12 tests), strict clippy, five signed-release infrastructure tests, Swift native process integration, native build/launch, staged package machine/resource/update validation, bundled discovery with empty PATH, ad-hoc signing and DMG integrity verification have passed during this migration. Full engine/media contracts run in CI against each release tool pair.

The native startup marker is emitted only after the UI creates its controls and its real process client decodes 27 engine presets. Windows also runs the native integration harness and validates package contents. Linux launches the packaged AppImage under Xvfb/D-Bus. These checks exercise package execution; an actual older-to-newer version upgrade still requires manual acceptance. Native smoke is not a pixel comparison or a substitute for manual interactions.

## Manual procedure

On every target, select artwork/audio using both keyboard file pickers and drag/drop. Try square, portrait, landscape and 4:5 presets, both flips, custom bitrate and 1/30/240 fps. Export to a new and existing destination, cancel during startup and encoding, close/quit during a render, and retry after errors. Verify the displayed final status corresponds to actual publication and inputs remain unchanged.

Traverse controls with the screen reader and keyboard, inspect 100/150/200% scaling, Retina/HiDPI and large text. Test all appearance modes and OS contrast/reduced-motion settings. Check icon identity in the Dock/taskbar/application menu, About UI, installer and desktop integration. Install without development tools or system FFmpeg.

For upgrades, install a signed older build using the same verification key and channel, publish a higher test build, check automatic and manual notification, defer it, then install it. Verify preference retention, restart, offline handling, wrong-key/tampered downloads, read-only AppImage location, and installer interruption/recovery. Confirm development cannot update stable and a missing platform artifact offers no broken download.

## Historical external gates

The first computer-use inspection failed with `Sky Computer Use native pipe closed before response`. A later retry reached the host but reported the Mac locked; interactive inspection requires the user to unlock it. Apple signing/notarization and Windows Authenticode credentials were absent when inspected. The initial Ed25519 update-signing secret and public variable have since been configured. Credential-dependent release trust and live update delivery cannot be certified until configured and exercised. These gaps must stay visible and must not be relabelled as passes.
