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
| Installer/package structure and machine type | A | A | A | A | A | A |
| Clean-machine installation | M | M | A + M | A + M | A + M | A + M |
| Reinstallation / real version upgrade | M | M | A reinstall + M upgrade | A reinstall + M upgrade | A reinstall + M upgrade | A reinstall + M upgrade |
| Automatic update / manual update check | M | M | M | M | M | M |
| Signed feed / corrupt download rejection | A | A | A | A | A | A |
| Actual signed update installation and restart | M | M | M | M | M | M |
| Uninstall without deleting user media | M | M | A + M | A + M | A + M | A + M |
| Signing and timestamp verification | A + M | A + M | A when configured | A when configured | Signed update metadata | Signed update metadata |
| Notarization and stapling | A when configured + M | A when configured + M | N/A | N/A | N/A | N/A |
| Package checksums/integrity | A | A | A | A | A | A |
| Minimum supported OS runtime | M macOS 13 | M macOS 13 | M Win10 1809 | M Win10 1809 | M baseline glibc/toolkit | M baseline glibc/toolkit |

## Automated evidence

Local Apple Silicon: Rust workspace (12 tests), strict clippy, five signed-release infrastructure tests, Swift native process integration, native build/launch, staged package machine/resource/update validation, bundled discovery with empty PATH, ad-hoc signing and DMG integrity verification have passed during this migration. Native implementation `c7275e2` passed macOS Apple Silicon/Intel and Windows x64/ARM64 in [run 34802411354](https://github.com/tlolabs/ativ/actions/runs/34802411354). Both Linux targets passed in [run 34803708905](https://github.com/tlolabs/ativ/actions/runs/34803708905) at `937a9a8`, which changes CI fixture execution and documentation without changing native application code. See the [validation report](native-distribution-report.md) for the original Linux fixture failure and resolution. Full engine/media contracts run in CI against each release tool pair.

The native startup marker is emitted only after the UI creates its controls and its real native process client decodes 27 engine presets. Windows also runs the actual C# client in an integration harness and installs/reinstalls/uninstalls the generated installer. Linux launches the packaged AppImage under Xvfb/D-Bus, installs the actual Debian package, launches its installed executable without engine-path overrides, then reinstalls and removes the package. These checks exercise package replacement; an actual older-to-newer version upgrade still requires manual acceptance. Native smoke is not a pixel comparison or a substitute for manual interactions.

## Manual procedure

On every target, select artwork/audio using both keyboard file pickers and drag/drop. Try square, portrait, landscape and 4:5 presets, both flips, custom bitrate and 1/30/240 fps. Export to a new and existing destination, cancel during startup and encoding, close/quit during a render, and retry after errors. Verify the displayed final status corresponds to actual publication and inputs remain unchanged.

Traverse controls with the screen reader and keyboard, inspect 100/150/200% scaling, Retina/HiDPI and large text. Test all appearance modes and OS contrast/reduced-motion settings. Check icon identity in the Dock/taskbar/application menu, About UI, installer and desktop integration. Install without development tools or system FFmpeg.

For upgrades, install a signed older build using the same verification key and channel, publish a higher test build, check automatic and manual notification, defer it, then install it. Verify preference retention, restart, offline handling, wrong-key/tampered downloads, read-only AppImage location, and installer interruption/recovery. Confirm development cannot update stable and a missing platform artifact offers no broken download.

## External gates

The first computer-use inspection failed with `Sky Computer Use native pipe closed before response`. A later retry reached the host but reported the Mac locked; interactive inspection requires the user to unlock it. Apple signing/notarization and Windows Authenticode credentials were absent when inspected. The initial Ed25519 update-signing secret and public variable have since been configured. Credential-dependent release trust and live update delivery cannot be certified until configured and exercised. These gaps must stay visible and must not be relabelled as passes.
