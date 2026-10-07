# Installation and updates

Stable releases use only authenticated, qualified artifacts from [GitHub Releases](https://github.com/tlolabs/ativ/releases/latest). Match the operating system and processor. SHA-256 detects transfer corruption; application updates additionally require the installed Ed25519 key and native platform checks. The current 0.2.6 candidate has [not passed release qualification](updates/qualification-20261001.md).

## macOS production

Install the native signed and notarized `ATIV-<version>-macos-arm64.zip` or `ATIV-<version>-macos-intel.zip`. The production application remains SwiftUI/AppKit and uses Sparkle for updates. The separate `ATIV-Qt-macos-arm64.zip` is an internal Qt reference artifact with a distinct identity; it is never a production download or update.

## Windows

Extract the architecture-matched `ATIV-<version>-windows-x64.zip` or `ATIV-<version>-windows-arm64.zip` and keep its files together. Launch `ATIV.exe`. The shared Qt UI offers **Help → Check for Updates**; after confirmation the authenticated portable update helper replaces the package and relaunches ATIV. Preferences remain under the current user's LocalAppData/ATIV directory. Development builds use a separate directory and identity. The portable helper's interruption and recovery behavior requires [native release qualification](RELEASING.md).

## Linux

Download the architecture-matched `ATIV-<version>-linux-x64.AppImage` or `ATIV-<version>-linux-arm64.AppImage`, make it executable, and launch it. The AppImage contains the shared Qt UI with bundled platform plugins. It still requires the documented Linux kernel/glibc and desktop libraries. When FUSE is unavailable, `APPIMAGE_EXTRACT_AND_RUN=1` runs it through the AppImage runtime.

Keep the AppImage in a user-writable directory for an in-place update. The application menu offers manual and automatic checks. A verified update atomically replaces the AppImage and preserves a previous copy for recovery; restart afterward. When direct replacement is unavailable, ATIV downloads the authenticated file and opens its containing folder for manual replacement after closing the app. Preferences preserve the previous GTK application's values through a one-way INI-to-JSON import; media and completed videos remain outside the package.
