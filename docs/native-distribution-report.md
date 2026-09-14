# Native distribution migration report

## Scope and implementation

Implementation revision: `c7275e2`, on `codex/native-distribution`. Subsequent documentation/reporting changes do not change native application binaries. ATIV started at `d88043d`; ENcap was reviewed at `46ffd343d3e83c5d58d522c8c33f8013f3b849f1` and AVID Core at `0cce6ba838827d0bed540efc98731e74a1014456`. This work did not modify either reference repository. ENcap independently advanced to `a2ab34d848ac4d27cded378e734e99e00d75e40b`; its cleanup diff was reviewed and does not change the selected native/core, FFmpeg or updater architecture. AVID Core remains at the pinned revision.

ATIV already had true native interfaces. This migration completed their distribution and integration behavior instead of replacing working platform-specific code with another toolkit. SwiftUI/AppKit, WinUI 3 and GTK/libadwaita remain native. Shared media policy still selects software H.264/AAC; no hardware encoding or project format was added.

- Converted authoritative artwork into macOS ICNS/catalog resources, Windows ICO/scaled logos and Linux hicolor icons. Removed the obsolete icon and identity strings.
- Added System/Light/Dark preferences, persistent native settings, keyboard commands, explicit labels, Windows DPI-aware startup sizing and scrolling, native taskbar identity, GTK drag/drop/audio probing, and safe render shutdown behavior.
- Corrected stale probe handling and Swift pipe draining. Added real Swift/C# probe-preview-export integration tests, native startup markers, installer upgrade/uninstall checks, AppImage launch tests and Debian install/reinstall/removal tests.
- Added host-only `ativ-update`, which verifies exact Ed25519-signed metadata bytes, channel, version, target, size and SHA-256 before installation handoff. AppImage replacement stages beside the existing file and publishes atomically. Native package installers handle Windows and Debian installation.
- Adapted ENcap's checksum-pinned Sparkle 2.9.6 bridge, with default automatic checks, manual checking, signed appcasts and verification before extraction. macOS packaging signs nested code inside-out, notarizes/staples the app before archiving, then notarizes/staples the DMG.
- Kept the exact common FFmpeg 9.0.1 acquisition recipe. Added dependency license collection, native package architecture/resource/version validation, Windows per-user installers, and AppImage/`.deb` distribution. Removed the superseded raw Linux archive.
- Added separate development app/package identities and signed feeds. Main pushes publish a rolling development prerelease; stable tags publish matching versions. Passing artifacts survive unrelated target failures, and CI explicitly reports incomplete releases. Metadata never lists absent artifacts. Release-note reruns preserve generated notes, and feed upload failures fail the job.
- Bootstrapped the initial GitHub Actions Ed25519 private secret and public variable. The private seed has a mode-0600 backup outside the repository. No credentials were committed. Apple and Windows certificate credentials were not supplied.

## Validation evidence

[Final native validation run](https://github.com/tlolabs/ativ/actions/runs/34802411354) tests the implementation revision above. The run includes six native OS/architecture targets, real shared media contracts, native process integration, package resources and machine types, bundled discovery without PATH, native startup, and platform installation smoke checks.

Local Apple Silicon verification passed: Rust workspace tests, strict clippy, the engine's declared Rust 1.85 minimum, five release infrastructure tests, two Swift tests including actual probe/preview/export, app launch, package validation, deep strict ad-hoc signature verification, and ZIP/DMG generation with DMG integrity verification. The public update key was included in the final local package.

An initial Linux x64 attempt in the final run failed in AVID Core's `concurrent_operations_have_independent_cancellation_and_staging` test while starting a freshly created fake FFmpeg script (`ExecutableFileBusy` / `Text file busy`). This occurred before the test's actual concurrent render operations. Earlier Linux runs passed. An unchanged rerun reproduced the failure. ATIV CI now runs the shared test harness serially to avoid concurrent fixture-write/spawn races. Every test remains enabled, including the test that explicitly launches concurrent render threads. No retry was embedded into the pipeline and no shared-core source was changed. Linux validation is being repeated with this harness configuration.

## Release gates

This is not a claim of production signing or manual accessibility certification. Apple Developer ID/notary secrets remain required to execute the signing/notarization branch. Windows Authenticode wiring is present but certificate-dependent execution remains unverified. Manual VoiceOver/Narrator/Orca, light/dark/system appearance, display scaling, minimum-OS runtime, and real older-to-newer authenticated upgrade acceptance remain on the [matrix](acceptance-matrix.md).

Interactive local inspection first encountered a computer-use service error and later a locked Mac. The user must unlock it to continue that verification. No release tag was created and no new public release was published during build-only validation. The release workflow and signed metadata generation were tested without publishing a release.

## Reference decisions

ENcap's existing native process architecture, common FFmpeg recipe and Sparkle integration were reused. Its reviewed checkout has no Windows/Linux update client, native installer/AppImage pipeline, nightly implementation or independent partial-platform publication to copy. ATIV's additions and Linux ARM64 retention are documented adaptations. macOS 13, Windows 10 1809 and GTK 4.10/libadwaita 1.4 align the reference baselines.

Relevant upstream specifications: [Sparkle publishing](https://sparkle-project.org/documentation/publishing/), [WinUI unpackaged distribution](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/unpackage-winui-app), [Windows DPI queries](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdpiforwindow), [taskbar identity](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-setcurrentprocessexplicitappusermodelid), [Inno architecture selection](https://jrsoftware.org/ishelp/topic_setup_architecturesallowed.htm), and [AppImage native packaging](https://docs.appimage.org/packaging-guide/from-source/native-binaries.html).
