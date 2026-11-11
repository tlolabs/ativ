# Shared JPEG and PNG optimization

Core provides one image optimizer for ATIV and EnCAP using source-built
[libjpeg-turbo through TurboJPEG](https://github.com/honzasp/rust-turbojpeg) and
[OxiPNG](https://github.com/shssoichiro/oxipng) with Zopfli. Its defaults follow the
supplied ImageOptim preferences: lossless compression, metadata removal, Extra
effort, and Zopfli enabled. JPEG quality 80 is inactive unless the caller opts into
lossy encoding. The ImageOptim macOS application is not a dependency; these codecs
run independently of FFmpeg, the renderer and host UI.

This API is included in source version `0.3.2`. Hosts must pin an immutable Core source
revision containing it and regenerate their lockfiles before calling it.

## API and persistent settings

```rust,no_run
use avid_core::{
    optimize_image, CancellationToken, ImageOptimizationOptions,
    ImageOptimizationRequest, Result,
};

fn optimize_artwork() -> Result<()> {
    let request = ImageOptimizationRequest {
        input: "cover.jpg".into(),
        output: "cover.optimized.jpg".into(),
        options: ImageOptimizationOptions::default(),
        protected_paths: vec!["project.encap".into()],
    };
    let result = optimize_image(&request, &CancellationToken::default())?;
    println!("Saved {} bytes", result.bytes_saved);
    Ok(())
}
```

`optimize_image(&ImageOptimizationRequest, &CancellationToken)` returns
`Result<ImageOptimizationResult>`. Request input/output fields are `PathBuf`s;
`protected_paths` is a `Vec<PathBuf>` for additional sources and project files.
There is no renderer, tool discovery or subprocess involved.

`ImageOptimizationOptions` supports serde serialization/deserialization with
defaults for missing fields. ATIV and EnCAP can persist their own settings and
expose equivalent General/Quality controls; Core keeps no global preferences.

| Setting | Default | Behavior |
| --- | --- | --- |
| `lossy: bool` | `false` | JPEG coefficient optimization; `true` enables JPEG decode/re-encode |
| `jpeg_quality: u8` | 80 | Valid 1–100; used only with lossy JPEG encoding |
| `strip_jpeg_metadata: bool` | `true` | Remove optional JPEG metadata; `false` requests preservation |
| `strip_png_metadata: bool` | `true` | Remove optional PNG metadata; `false` requests preservation |
| `effort: OptimizationEffort` | `Extra` | `Fast`, `Normal`, `Extra`, `Insane` select PNG levels 1, 2, 4, 6 and Zopfli iterations 1, 5, 15, 30 |
| `png_zopfli: bool` | `true` | Also try Zopfli and keep the smaller lossless candidate |

The effort enum serializes in snake_case. PNG compression stays lossless when
`lossy` is enabled; no lossy PNG palette-quantization quality slider is provided.
GIF and SVG optimization are outside this API.

The result contains `format: OptimizedImageFormat` (`Jpeg` or `Png`),
`input_bytes: u64`, `output_bytes: u64`, `bytes_saved: u64` and `optimized: bool`.
`optimized` means the output is strictly smaller; `bytes_saved` is zero if it is
not. Outputs never exceed input size. Hosts should report the returned values
rather than assume every image shrinks.

## Image behavior and limits

Input bytes identify the format. JPEG output must use `.jpg` or `.jpeg`; PNG
output must use `.png`. Optimization keeps the input format and dimensions and
does not resize, crop or rotate images.

Default JPEG optimization uses lossless DCT coefficient transformation and
entropy/progressive optimization without pixel requantization. With `lossy = true`,
Core decodes and re-encodes at the requested quality, including loss at quality
100. Keep originals and avoid repeated lossy encoding. CMYK JPEG is rejected to
avoid an implicit color conversion.

PNG compression preserves pixel values. Any nonopaque pixel is rejected for
album artwork, including transparency in 16-bit or palette/`tRNS` PNGs. Fully
opaque alpha channels are accepted and may be removed losslessly. Core does not
silently composite transparency onto a background. APNG is rejected rather than
flattened into a still frame.

Metadata removal is enabled for both formats. Removing EXIF orientation or an
ICC/color profile can change a viewer's displayed orientation or color even
when JPEG coefficients or PNG pixel values are unchanged. Disable the respective
strip option when those interpretation fields must be retained. JPEG preservation
keeps application and comment markers; PNG preservation follows OxiPNG's policy
and is not byte-for-byte for arbitrary chunks. OxiPNG removes invalidated C2PA
`caBX` signatures and may reconcile conflicting ICC/sRGB declarations.

Core selects the smallest candidate that obeys the requested metadata policy.
JPEG and accepted PNG outputs do not grow. Size fallback cannot
restore stripped metadata; transparent inputs fail before publication.
JPEG stripping also discards bytes after the image's end marker, including when
the original compressed scan is the smallest candidate. Structural JFIF/Adobe
fields needed for image interpretation remain, with JFIF thumbnails and extra
payload bytes removed. Preservation keeps the source APP/COM marker payloads
without adding a synthetic JFIF marker to an
EXIF-only source; marker placement may be normalized to the header.

Inputs are limited to 128 MiB, dimensions of at most 32,768 per axis and at most
50 million pixels. Unsupported formats, malformed data and invalid options fail
without publishing a replacement. Keep host import limits and previews consistent
with this contract.

## Publication and cancellation

Use a separate output path. Core rejects input/output aliases, including hard
links, and protected-path collisions. It stages output beside the destination
and publishes atomically after validation, encoding and the final cancellation
check succeed. Existing output survives failure before publication. Hosts
serialize writers to a shared destination and update project references only
after successful publication.

On Windows, publication retries access-denied, sharing-violation and
lock-violation errors for up to two seconds. A persistent lock still returns an
error and removes the stage. Other platforms attempt the atomic rename once;
Core does not fall back to a copy on network or cloud-synced filesystems.

Original source attributes and hard links remain untouched because optimization
writes a separate file. The output gets ordinary newly created file attributes;
Core does not clone source timestamps, extended attributes or hard-link topology.

Run the synchronous function on a worker thread. Clone the ordinary Core
`CancellationToken` into the host stop handler. Cancellation is cooperative
between phases and before publication; it cannot interrupt a running in-process
codec call and has no whole-operation timeout. There are no progress callbacks
for this API. A successful return is the publication signal.

PNG opacity validation checks transformed rows, including Adam7 pass rows,
without reconstructing a complete frame. It still validates the complete source
and its checksums before metadata removal. Compression effort and defaults are
unchanged; the optimizer retains its complete-image codec working buffers.

Core does not enforce an aggregate host memory budget. A 50-megapixel 16-bit
RGBA frame alone occupies about 400 MB, and codec working buffers and candidates
add to the peak. Start with one optimization worker and measure peak memory and
cancellation latency on the host's largest supported inputs before increasing
concurrency. Zopfli effort can substantially lengthen an uninterruptible phase.

## Source pins and ImageOptim differences

Core pins `turbojpeg =1.5.1`, `turbojpeg-sys =1.2.0`, `oxipng =9.1.5`,
`libdeflate-sys =1.26.1`, `zopfli =0.8.2` and `png =0.17.16`. The exact native pins
also survive fresh dependency resolution by a host. The `-sys` crates compile
vendored libjpeg-turbo 3.1.0 and libdeflate 1.26 sources. Builds need Rust 1.85,
CMake and a target C compiler; cross-builds also need the target SDK and archiver.
The static JPEG build allows a scalar fallback when NASM is unavailable and
needs no prebuilt codec/tool download.
OxiPNG uses Zopfli without its CLI or parallel feature.

This is not exact ImageOptim pipeline parity. JPEG uses the jpegtran-family
coefficient engine without a separate jpegoptim executable. PNG uses OxiPNG and
Zopfli rather than a chain of AdvPNG/other optimizers. PNGOUT is excluded because
upstream offers executable downloads and separate bundling terms, without a
source-build dependency. See [the upstream PNGOUT distribution page](https://www.advsys.net/ken/utils.htm).
Output sizes and run times can therefore differ from the ImageOptim application.

Carry the Core license, [third-party notices](../THIRD_PARTY_NOTICES.md) and the
[preserved codec license texts](../licenses/image-optimization/README.md) into
host distributions. This software is based in part on the work of the Independent
JPEG Group. Core owns the shared implementation and source pins. ATIV and EnCAP
own UI, settings storage, worker scheduling, project integration, application
testing, signing and release schedules. Host acceptance does not block Core
development or verified Core releases.

## Verification

Run the locked suite in [TESTING.md](TESTING.md). Verify lossless JPEG coefficient
behavior, optional JPEG quality, metadata strip/preserve settings, transparent
PNG rejection, opaque PNG pixels, size accounting and fallback.
Also cover malformed input, APNG/CMYK rejection, resource limits, cancellation,
aliases/protected paths and existing-output preservation.

ATIV and EnCAP should test settings persistence, import, preview,
optimize-to-new-file, project save/reopen, cancel and failure behavior with
representative artwork. Native Windows/Linux image-codec execution and packaged
host integration remain outstanding until recorded evidence establishes them.
Diagnostic failures remain visible without creating mandatory development or
downstream approval gates.

Local verification on 2026-10-19 (macOS ARM64): the offline locked release build,
Rust 1.85 all-target check, Clippy with warnings denied, formatting, dependency
inventory, 12 preserved license hashes and source-package compilation passed.
The all-target/all-feature suite passed 77 tests, including 19 image integration
tests and 10 JPEG unit tests; the documentation test also passed. Eight opt-in
FFmpeg/runtime tests and the performance benchmark were skipped. Native
Windows/Linux execution and ATIV/EnCAP UI/integration tests were not run.
