# Release readiness checklist

- Confirm the shared-core revision matches CI and ENcap/AVID Core remain unchanged unless separately approved.
- Pass Rust formatting, strict clippy, workspace tests, real-media contract tests, release metadata tests and all native package/startup jobs.
- Verify each distributed package's architecture, version, native icons, licenses, engine, FFmpeg and ffprobe. Run bundled discovery without PATH.
- Complete the manual [acceptance matrix](acceptance-matrix.md), including screen readers, focus, appearance, scaling, cancellation, quit, clean install, upgrades and uninstall.
- Configure the update public variable/private secret and Apple Developer ID/notary secrets listed in [releasing](RELEASING.md). Optionally configure Windows Authenticode signing.
- Test a real older-to-newer update using the installed verification key. Reject corrupted downloads, wrong-channel feeds and lower versions; preserve the working installation on failure.
- Verify Developer ID, Hardened Runtime, nested Sparkle signatures, app/DMG notarization, stapling and Gatekeeper on macOS. Verify Authenticode/timestamps when Windows signing is configured.
- Verify separate development identity, package IDs, preferences and feed URLs. Existing legacy releases without an updater require one manual installation of the new version.
- Change the workspace version and push its matching `vX.Y.Z` tag only when intentionally releasing. Tagged publication is automatic, with no approval job. Review generated release notes and partial-platform status.
- Confirm passing artifacts remain downloadable after an unrelated target fails, feeds list only available verified artifacts, and CI reports incomplete targets.

## Withdrawal/recovery

Remove an affected artifact and its corresponding feed entry together, publish clear release notes, and prepare a higher-version corrective release. Never advertise a missing artifact or change a signed payload without regenerating its signature. Do not rotate the installed trust key as a shortcut for an ordinary release problem. Existing installations remain usable when update checks fail.
