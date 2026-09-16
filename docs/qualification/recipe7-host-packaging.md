# Recipe 7 ATIV host qualification

This branch is provisional qualification, not production migration. Core's current prerequisite and native reports were read at `eb57c9068958543e3cf4401fc2defb66d041e309`. The actual binary/build source is `fab2ed86bb64582d3f7a7dd736c713cc3951550b` (0.2.2), run 35157560636, Recipe 7. `runtime/recipe7-candidate.json` is an exact copy of Core's native evidence and pins all six runtime/source archives, Actions artifact digests and executable pairs. ATIV's starting commit was `f38c433076c2980ff356da3d54e6f9b465439e6d`.

Required ATIV targets: macOS ARM64/x86_64, Windows ARM64/x86_64 and Linux ARM64/x86_64. The host gate includes build/package, applicable signing/notarization, installation, application launch, bundled discovery, media, lifecycle/resource release, authenticated upgrades, provenance and manual UI/accessibility acceptance. Core native qualification does not establish these host results. Hosted execution is scoped to the currently authorized macOS 15, Windows Server 2025/Windows 11 ARM64 and Ubuntu 24.04 runners, not minimum OS claims.

The dedicated `recipe7-qualification.yml` workflow uses the existing application packaging/native tests, with explicit `ATIV_QUALIFICATION_R7=1` and development identity. Acquisition authenticates the retained ZIP, archive, source and exact native pair, verifies Core's full payload contract and requires the exact consuming Core pin. It never builds or substitutes FFmpeg. Normal provisioning remains release-only without the explicit opt-in. Stable channels and tag/release builds reject the opt-in. Candidate provenance is marked `qualification_only`; original and host-signed hashes remain distinct.

The owner confirmed signing setup is not completed. No valid local code-signing identity or macOS/Windows repository signing secrets were found. macOS observations therefore use ad-hoc signing and Windows observations are unsigned; these cannot pass release signing gates. The existing authenticated updater uses production/development GitHub release feeds. Neither feed is modified or published by this workflow. Unit signature tests and same-version installer replacement are partial update evidence, not authenticated end-to-end upgrades. Manual UI/accessibility remains unperformed. Every target's final gate intentionally fails until all required evidence exists.

Each native job retains `R7-evidence-<target>` containing a JSON report with the exact ATIV commit/run, source/binary identity, native host, step outcomes, packaged provenance and artifact hashes. Candidate packages are retained separately. The final report cannot mark `host_packaging` passed while required gates are unperformed. This branch must not be merged or tagged as a completed production migration.

Reproduction: use the dedicated workflow on this branch, or check out this ATIV revision beside an unmodified Core checkout at the pinned commit and run:

```sh
export ATIV_CHANNEL=development ATIV_QUALIFICATION_R7=1
export ATIV_VERSION=0.2.3-dev.7001
python3 script/qualify_recipe7.py <native-target>
```

Then run the matching existing packaging/native scripts as specified in the workflow. `gh` needs read access to the public Core Actions artifacts. Missing/expired or changed artifacts fail closed. Never set these qualification variables for production release jobs.

## ATIV-local failures found and repaired

- macOS `codesign` initially rejected the app executable because runtime notices were still under `Contents/MacOS`. Move the existing Core metadata/notices relocation before signing the main executable. Original media helper hashes are verified before signing and signed hashes are retained.
- Both Linux AppImage builds failed `Packaged binary changed after signing: ffprobe`. `linuxdeploy` changes ELF RPATH even in the already-qualified Core tools. Restore both tools from the authenticated package stage after deployment and compare their bytes; do not accept a new hash for modified runtime bytes. Qualification additionally extracts the final AppImage and rechecks its runtime and media behavior.
- Windows ARM64's added Python signature harness could not build cryptography without OpenSSL. Windows now uses an ignored, explicitly credentialed native Rust test to exercise the updater's existing `verify` and `download` code against actual candidate packages, including metadata/package tampering. macOS retains Sparkle-format offline signature verification. These tests do not claim authenticated delivery or full application upgrade acceptance.
- The macOS installed-launch helper resolves `/tmp` aliases, checks that the installed app is still running after startup and waits for that exact app to exit. It does not stop unrelated application processes.
