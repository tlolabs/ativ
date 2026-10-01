# Privacy

ATIV is a TLO Labs open-source project. It processes selected images and audio on the user's device. ATIV has no account, analytics, hosted crash reporter, telemetry upload, cloud rendering, advertising or sale or sharing of user data. Media files are not uploaded by ATIV. Core export and preview work offline after installation.

## Network activity

The native applications can check **GitHub Releases** for updates. macOS uses Sparkle and a GitHub-hosted appcast; Windows and Linux use a signed GitHub-hosted `latest.json` feed. Windows and Linux check on launch and approximately every 24 hours while enabled; the macOS Sparkle schedule is managed by Sparkle. The user can disable automatic checks in application preferences. A manual check still connects to GitHub. The update request exposes ordinary connection metadata, including the user's IP address, to GitHub. ATIV sends no media or diagnostic logs with it. The updater downloads a release artifact only after the user chooses to install; it verifies the signed update metadata and artifact checksum. Native platform services, including notarization or operating-system trust checks, may make their own network requests outside ATIV's control.

Building from source requires downloads of pinned dependencies and tools. These are development activities, not runtime application downloads. ATIV does not load remote fonts or artwork while running.

## Local data and diagnostics

The engine keeps a local diagnostic log: `~/Library/Logs/ATIV/ativ-engine.log` on macOS, `%LOCALAPPDATA%\ATIV\Logs\ativ-engine.log` on Windows, and `${XDG_STATE_HOME:-~/.local/state}/ativ/ativ-engine.log` on Linux. A custom `ATIV_LOG_PATH` can override the location. The log rotates when it exceeds 1 MiB; at most the current file and one `.log.old` file are kept, with no time-based deletion. Logs can include local media paths, operation stages and error details. They remain on the user's device unless the user explicitly shares them. The macOS app may also write to the local macOS unified log. Windows preferences are stored locally in `%LOCALAPPDATA%\ATIV\preferences.json`; equivalent native preferences are local on macOS and Linux.

For privacy or security concerns, use [private GitHub vulnerability reporting](https://github.com/tlolabs/ativ/security/advisories/new). Public project/security email: **TBD**.
