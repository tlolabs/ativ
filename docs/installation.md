# Installation and updates

Download from [GitHub Releases](https://github.com/tlolabs/ativ/releases/latest). Choose the artifact for your processor. Verify `SHA256SUMS` when transferring packages between machines. A checksum detects corruption; authenticated updates additionally require the app's embedded Ed25519 public key.

## macOS

Open `ATIV-<version>-macos-arm64.dmg` on Apple Silicon or `macos-intel.dmg` on Intel. Drag ATIV to Applications. Stable production packages require Developer ID signing, notarization and stapling in CI. Local/development verification builds can be ad-hoc signed; these do not establish production Gatekeeper trust.

Sparkle checks for updates automatically and supplies its native update dialog. Use **ATIV → Check for Updates** for an immediate check. Automatic checks can be turned off in Settings. Updates are verified before extraction. Replacing the app does not remove preferences.

## Windows

Run `ATIV-<version>-windows-x64-setup.exe` or `windows-arm64-setup.exe`. The installer installs for the current user, creates a Start menu entry, and registers an uninstaller. Use Windows Settings → Apps to uninstall. The ZIP is a portable alternative; keep all its files together.

**Help → Check for updates** downloads a verified installer after confirmation. The app exits and the installer handles replacement. Unsigned builds remain possible; Authenticode signing is enabled when repository secrets are supplied. A signed update manifest authenticates the installer independently of Authenticode. Preferences live in the current user's LocalAppData/ATIV directory and survive upgrades and uninstall; remove that directory to reset them. Development builds use a separate directory and installer identity.

## Linux

For Ubuntu 24.04 or newer, install the `.deb` with the system package installer or `sudo apt install ./ATIV-<version>-linux-x64.deb` (use the ARM64 artifact on ARM64). This resolves native toolkit dependencies. Remove it with `sudo apt remove ativ`; the development package is `ativ-development`.

For AppImage, mark the downloaded file executable and launch it. AppImages bundle native toolkit dependencies, but still require a compatible Linux kernel/glibc baseline. On systems without FUSE, use `APPIMAGE_EXTRACT_AND_RUN=1 ./ATIV-….AppImage`. Keep the AppImage in a user-writable directory if you want in-place updates.

The application menu exposes appearance, automatic checks and manual update checking. An AppImage update is downloaded beside the current file, authenticated, flushed, and atomically replaces it; restart the app afterward. A `.deb` update downloads a verified package and opens the distribution's package installer, which manages privileges and dependencies. If your desktop has no `.deb` handler, install the verified download using apt. Distribution package transactions own rollback/recovery for system installs. ATIV does not self-write into `/usr`.

## Stable and development builds

Stable tags are `v<workspace version>`. Main branch pushes produce a rolling `development` prerelease with version `<workspace version>-dev.<run number>`. Development apps have separate identities/preferences and feeds. There is no in-app channel selector. A development build cannot update a stable installation through its feed.

The first release using this infrastructure requires the update-signing secrets described in [releasing](RELEASING.md). A build without a valid verification key reports that updates are unavailable; it never installs unauthenticated data.
