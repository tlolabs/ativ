# ATIV acceptance matrix

This matrix defines the behavior every native ATIV release must preserve.

| Capability | Shared engine | macOS | Windows | Linux | Verification |
| --- | --- | --- | --- | --- | --- |
| Artwork + track to MP4 | Rust/FFmpeg pipeline | SwiftUI/AppKit | WinUI 3 | GTK 4/libadwaita | Real H.264/AAC integration render |
| Platform formats | Immutable preset table | Native picker | Native picker | Native picker | Unit tests and engine protocol |
| Preview and flips | Shared filter graph | Native image view | Native image view | Native picture | Preview integration test |
| Progress and ETA | Parsed FFmpeg progress | Live status | Live status | Live status | Engine unit tests and manual UI check |
| Cancellation | Atomic flag and child termination | Stop action | Stop action | Stop action | Existing-output preservation test |
| Safe output | Staged file and atomic publish | Engine-mediated | Engine-mediated | Engine-mediated | Failure and cancellation regression tests |
| Bundled tools | Adjacent tool discovery | App bundle | App directory | `/usr/lib/ativ` | Pinned checksum/package jobs |
| Privacy | No network or telemetry code | Local only | Local only | Local only | Source and security review |
| Diagnostics | Rotating local log | Platform log directory | Platform log directory | XDG state directory | `ATIV_LOG_PATH` override |

Release jobs cover Apple Silicon, Intel macOS, Windows x64, Windows ARM64, Linux x86_64, and Linux ARM64. Hardware/GPU acceleration is intentionally disabled: the still-image workflow prioritizes reproducible software encoding and broad H.264 playback.
