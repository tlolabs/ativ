// SPDX-FileCopyrightText: Thomas Lothian
// SPDX-License-Identifier: GPL-3.0-or-later

//! Shared, source-built JPEG and PNG optimization for ATIV and EnCAP.

mod jpeg;
mod png;

use crate::{
    storage::{self, StagedOutput},
    CancellationToken, Error, Result, MAX_SOURCE_IMAGE_DIMENSION, MAX_SOURCE_IMAGE_PIXELS,
};
use serde::{Deserialize, Serialize};
use std::{
    fs::{self, File},
    io::Read,
    path::PathBuf,
};

/// Compressed input limit; dimensions and pixel count are limited separately.
pub const MAX_OPTIMIZATION_INPUT_BYTES: u64 = 128 * 1024 * 1024;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OptimizedImageFormat {
    Jpeg,
    Png,
}

/// Shared UI choices. Hosts persist their own copy; Core has no global settings.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OptimizationEffort {
    Fast,
    Normal,
    #[default]
    Extra,
    Insane,
}

impl OptimizationEffort {
    fn png_level(self) -> u8 {
        match self {
            Self::Fast => 1,
            Self::Normal => 2,
            Self::Extra => 4,
            Self::Insane => 6,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct ImageOptimizationOptions {
    /// Allow JPEG pixel recompression. False uses a lossless coefficient transform.
    pub lossy: bool,
    /// JPEG quality, 1–100, used only when `lossy` is true.
    pub jpeg_quality: u8,
    /// Remove EXIF, GPS, orientation and color profiles, matching ImageOptim.
    pub strip_jpeg_metadata: bool,
    /// Remove optional PNG metadata, including gamma and color profiles.
    pub strip_png_metadata: bool,
    pub effort: OptimizationEffort,
    /// Also try Zopfli and keep the smaller lossless PNG candidate.
    pub png_zopfli: bool,
}

impl Default for ImageOptimizationOptions {
    fn default() -> Self {
        Self {
            lossy: false,
            jpeg_quality: 80,
            strip_jpeg_metadata: true,
            strip_png_metadata: true,
            effort: OptimizationEffort::Extra,
            png_zopfli: true,
        }
    }
}

#[derive(Clone, Debug)]
pub struct ImageOptimizationRequest {
    pub input: PathBuf,
    /// A separate file of the same format (.jpg/.jpeg or .png).
    pub output: PathBuf,
    pub options: ImageOptimizationOptions,
    /// Other source/project paths the destination must not overwrite.
    pub protected_paths: Vec<PathBuf>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ImageOptimizationResult {
    pub format: OptimizedImageFormat,
    pub input_bytes: u64,
    pub output_bytes: u64,
    pub bytes_saved: u64,
    /// True when the output is strictly smaller than the input.
    pub optimized: bool,
}

/// Optimize a static JPG/JPEG or PNG on the calling worker thread.
///
/// Builds libjpeg-turbo, OxiPNG and Zopfli from pinned sources; no FFmpeg, installed
/// ImageOptim application, network access or external executable is used at runtime.
/// JPEG uses lossless coefficient optimization unless `lossy` is enabled. PNG
/// compression is lossless. PNG artwork containing transparent pixels is rejected.
/// Metadata stripping defaults to enabled, including color/orientation
/// data; hosts can disable each format's stripping independently.
/// Animated PNG and CMYK JPEG inputs are unsupported. If recompression does not
/// reduce the byte count, the smallest policy-compliant candidate is copied.
/// The source is never replaced, including through hard-link/symlink aliases.
///
/// Cancellation is cooperative between codec phases and before staged publication;
/// it cannot interrupt an active in-process codec call. Hosts must serialize writers
/// to the same destination.
pub fn optimize_image(
    request: &ImageOptimizationRequest,
    cancel: &CancellationToken,
) -> Result<ImageOptimizationResult> {
    cancel.check()?;
    if !(1..=100).contains(&request.options.jpeg_quality) {
        return Err(Error::InvalidInput("JPEG quality must be 1–100".into()));
    }
    storage::file(&request.input)?;
    let protect_output = || {
        storage::protect(
            &request.output,
            std::iter::once(&request.input).chain(request.protected_paths.iter()),
        )
    };
    protect_output()?;
    let source = File::open(&request.input)
        .map_err(|e| Error::io("open image source", &request.input, e))?;
    if source
        .metadata()
        .map_err(|e| Error::io("inspect image source", &request.input, e))?
        .len()
        > MAX_OPTIMIZATION_INPUT_BYTES
    {
        return Err(input_too_large());
    }
    let mut input = Vec::new();
    // Bound the actual read too, including if another writer grows the source.
    source
        .take(MAX_OPTIMIZATION_INPUT_BYTES + 1)
        .read_to_end(&mut input)
        .map_err(|e| Error::io("read image source", &request.input, e))?;
    if input.len() as u64 > MAX_OPTIMIZATION_INPUT_BYTES {
        return Err(input_too_large());
    }
    cancel.check()?;
    let format = if input.starts_with(b"\x89PNG\r\n\x1a\n") {
        OptimizedImageFormat::Png
    } else if input.starts_with(b"\xff\xd8\xff") {
        OptimizedImageFormat::Jpeg
    } else {
        return Err(Error::InvalidInput(
            "Expected a JPG/JPEG or PNG image".into(),
        ));
    };
    let extension = request
        .output
        .extension()
        .and_then(|v| v.to_str())
        .unwrap_or_default();
    let valid_extension = match format {
        OptimizedImageFormat::Png => extension.eq_ignore_ascii_case("png"),
        OptimizedImageFormat::Jpeg => {
            extension.eq_ignore_ascii_case("jpg") || extension.eq_ignore_ascii_case("jpeg")
        }
    };
    if !valid_extension {
        return Err(Error::InvalidInput(
            "Output extension must match the source image format (.jpg/.jpeg or .png)".into(),
        ));
    }
    let optimized = match format {
        OptimizedImageFormat::Png => png::optimize(&input, &request.options, cancel)?,
        OptimizedImageFormat::Jpeg => jpeg::optimize(
            &input,
            request.options.jpeg_quality,
            request.options.lossy,
            request.options.strip_jpeg_metadata,
            cancel,
        )?,
    };
    cancel.check()?;
    let smaller = optimized.len() < input.len();
    let output = &optimized;
    let result = ImageOptimizationResult {
        format,
        input_bytes: input.len() as u64,
        output_bytes: output.len() as u64,
        bytes_saved: input.len().saturating_sub(output.len()) as u64,
        optimized: smaller,
    };
    let staged = StagedOutput::new(&request.output, ".image")?;
    fs::write(staged.path(), output)
        .map_err(|e| Error::io("write optimized image", staged.path(), e))?;
    cancel.check()?;
    protect_output()?;
    staged.publish(&request.output)?;
    Ok(result)
}

fn input_too_large() -> Error {
    Error::InvalidInput("Image optimization input exceeds 128 MiB".into())
}

fn check_dimensions(width: u32, height: u32) -> Result<()> {
    if width == 0
        || height == 0
        || width > MAX_SOURCE_IMAGE_DIMENSION
        || height > MAX_SOURCE_IMAGE_DIMENSION
        || u64::from(width) * u64::from(height) > MAX_SOURCE_IMAGE_PIXELS
    {
        return Err(Error::InvalidInput(format!(
            "Image dimensions {width}×{height} exceed optimization limits"
        )));
    }
    Ok(())
}

// Inspect framing, dimensions and PLTE/tRNS layout before the codec allocates
// decoded pixels. CRCs, supported bit depths and compressed pixel integrity
// are checked by png/OxiPNG.
fn inspect_png(input: &[u8]) -> Result<()> {
    let invalid = || Error::ImageOptimization("Invalid or truncated PNG chunk framing".into());
    if input.len() < 33 || &input[8..16] != b"\0\0\0\rIHDR" {
        return Err(invalid());
    }
    let dimension = |offset| u32::from_be_bytes(input[offset..offset + 4].try_into().unwrap());
    check_dimensions(dimension(16), dimension(20))?;
    let bit_depth = input[24];
    let color_type = input[25];
    let mut position = 8usize;
    let mut seen_image_data = false;
    let mut seen_trns = false;
    let mut palette_entries = None;
    while position < input.len() {
        let header = input.get(position..position + 8).ok_or_else(invalid)?;
        let length = u32::from_be_bytes(header[..4].try_into().unwrap()) as usize;
        let end = position
            .checked_add(12)
            .and_then(|v| v.checked_add(length))
            .filter(|end| *end <= input.len())
            .ok_or_else(invalid)?;
        let kind = &header[4..];
        let payload = &input[position + 8..end - 4];
        if position != 8 && kind == b"IHDR" {
            return Err(invalid());
        }
        // Palette/transparency information must precede pixel data and conform to
        // ISO/IEC 15948 section 11.3.2.1 so the pre-optimization opacity decoder
        // and OxiPNG cannot disagree on which pixels are transparent.
        if kind == b"PLTE" {
            if seen_image_data
                || seen_trns
                || palette_entries.is_some()
                || length == 0
                || length > 768
                || length % 3 != 0
                || matches!(color_type, 0 | 4)
            {
                return Err(invalid());
            }
            palette_entries = Some(length / 3);
        } else if kind == b"tRNS" {
            if seen_image_data || seen_trns {
                return Err(invalid());
            }
            seen_trns = true;
            let valid_trns = match color_type {
                0 => {
                    matches!(bit_depth, 1 | 2 | 4 | 8 | 16)
                        && payload.len() == 2
                        && u32::from(u16::from_be_bytes([payload[0], payload[1]]))
                            < (1_u32 << bit_depth)
                }
                2 => {
                    matches!(bit_depth, 8 | 16)
                        && payload.len() == 6
                        && payload.chunks_exact(2).all(|sample| {
                            u32::from(u16::from_be_bytes([sample[0], sample[1]]))
                                < (1_u32 << bit_depth)
                        })
                }
                3 => palette_entries.is_some_and(|entries| (1..=entries).contains(&payload.len())),
                _ => false,
            };
            if !valid_trns {
                return Err(invalid());
            }
        }
        if kind == b"IDAT" {
            seen_image_data = true;
        }
        if matches!(kind, b"acTL" | b"fcTL" | b"fdAT") {
            return Err(Error::InvalidInput(
                "Animated PNG optimization is unsupported; use a static PNG".into(),
            ));
        }
        if kind == b"IEND" {
            return if length == 0 && end == input.len() {
                Ok(())
            } else {
                Err(invalid())
            };
        }
        position = end;
    }
    Err(invalid())
}
