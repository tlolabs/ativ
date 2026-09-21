# ATIV FFmpeg 9.0.2 qualification

This records ATIV-owned builds, independent of the historical Core runtime ledger. No production release is published by qualification. Source: official FFmpeg 9.0.2 archive, verified with pinned SHA-256 and upstream OpenPGP signature. External libraries: source-built x264 and zlib.

| Target | Source/build | Package/media/lifecycle |
|---|---|---|
| macOS Apple Silicon | Initial native source build passed; final recipe validation in progress | Qualification in progress |
| macOS Intel | Native CI pending | Pending |
| Windows x64 | Native CI pending | Pending |
| Windows ARM64 | Native CI pending | Pending |
| Linux x64 | Native CI pending | Pending |
| Linux ARM64 | Native CI pending | Pending |

Local ATIV Rust workspace tests, clippy and runtime ownership guard passed. The existing Core API and commit are unchanged. Minimum OS declarations are build targets; execution on a newer hosted image alone does not prove behavior on the exact minimum OS.
