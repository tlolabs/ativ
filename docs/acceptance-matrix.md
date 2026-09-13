# Acceptance matrix

| Requirement | Shared engine | macOS | Windows | Linux | Verification |
| --- | --- | --- | --- | --- | --- |
| Image + audio to MP4 | Rust FFmpeg pipeline | SwiftUI/AppKit | WinUI 3 | GTK 4/libadwaita | Real H.264/AAC integration render |
| Social presets | One immutable preset table | Native pickers | Native pickers | Native pickers | Unit tests and engine protocol |
| Preview and flips | Shared filter graph | Native image view | Native image view | Native picture | Preview integration test |
| Progress and ETA | Parsed FFmpeg progress | Live status | Live status | Live status | Engine unit tests/manual UI |
| Cancellation | Atomic flag + child termination | Stop action | Stop action | Stop action | Existing output preservation test |
| Safe output | Staged file + atomic publish | Engine mediated | Engine mediated | Engine mediated | Failure/cancel regression tests |
| Bundled FFmpeg 9.0.1 | Adjacent binary discovery | App bundle | App directory | `/usr/lib/avid` | Pinned checksum/package jobs |
| Privacy | No network or telemetry code | Local only | Local only | Local only | Source/security review |
| Diagnostics | Rotating local log | Platform log directory | Platform log directory | XDG state directory | `AVID_LOG_PATH` override |
| Legacy preservation | N/A | N/A | N/A | N/A | `legacy-python/` retained intact |

Native package jobs cover Apple Silicon, Intel macOS, Windows x64, Windows ARM64, Linux x86_64, and Linux ARM64. Hardware/GPU acceleration is intentionally not enabled: the still-image workload prioritizes reproducible software encoding and universal H.264 playback over driver-specific acceleration.
