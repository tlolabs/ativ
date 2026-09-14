# Native distribution migration

## Baseline review

ATIV baseline: d88043d. ENcap reference: 46ffd343d3e83c5d58d522c8c33f8013f3b849f1. Shared core: 0cce6ba838827d0bed540efc98731e74a1014456. Reference repositories are read-only.

Both hosts already use SwiftUI/AppKit, WinUI 3, and GTK 4/libadwaita over a Rust JSON subprocess boundary. ATIV retains its standalone adapter, all 27 presets, original input/audio semantics, software H.264/AAC, flips, progress, cancellation and atomic publication. No document format or hardware encoding changes are needed.

ENcap uses macOS 13, Windows 10 1809, GTK 4.10/libadwaita 1.4, and Linux x64. ATIV will align these baselines and retain its existing Linux ARM64 support as an additional target. Both now acquire the same pinned FFmpeg 9.0.1 artifacts; the source recipe wrappers in ENcap delegate to acquisition. No second FFmpeg pair is necessary.

ENcap dynamically loads checksum-pinned Sparkle 2.9.6 and publishes Ed25519 appcasts and signed JSON metadata from encap-release. Its Windows and Linux clients do not consume update metadata. No current nightly, AppImage, deb, rpm, Windows installer, production Developer ID/notary workflow, or acceptance matrix exists to copy. Its release job requires all platforms, contrary to this request. These are documented adaptations, not claims of proven ENcap functionality. Use signed metadata plus native installers for ATIV, Sparkle on macOS, separate development identity/feed, and publish only validated passing targets.

ENcap has accessible native controls and adaptive system styling, but sparse explicit labels/settings on Linux and Windows. ATIV needs keyboard commands, persistent appearance/preferences, better async lifecycle handling, native integration tests and explicit manual assistive-technology acceptance evidence. Native views should be completed rather than discarded wholesale.

## Implementation sequence

1. Baseline engine tests and architecture review.
2. Deterministic resource pipeline from assets/icons, replacing the obsolete icon.
3. Complete native appearance, preferences, keyboard, lifecycle and integration behavior.
4. Add isolated ATIV updater helper with signed metadata validation and native installation handoff; adapt Sparkle bridge.
5. Unify version/channel configuration and native packages, signing/notarization, installer and AppImage generation.
6. CI native startup/media/package tests and independent stable/development publication.
7. Documentation, acceptance matrix and local macOS verification; run platform CI where available.

## Verification policy

Automated checks establish only what was executed. A macOS build does not certify Windows/Linux or screen readers. Credential-dependent signing, real upgrade cycles and hardware/OS acceptance remain explicit gates until tested. No release tag will be invented or published during implementation.
