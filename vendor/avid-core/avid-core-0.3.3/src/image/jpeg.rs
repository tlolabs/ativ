// SPDX-FileCopyrightText: Thomas Lothian
// SPDX-License-Identifier: GPL-3.0-or-later

use crate::{
    CancellationToken, Error, Result, MAX_SOURCE_IMAGE_DIMENSION, MAX_SOURCE_IMAGE_PIXELS,
};
use std::ops::Range;
use turbojpeg::{Colorspace, Compressor, Decompressor, Image, PixelFormat, Transform, Transformer};

// Bound bookkeeping independently of the encoded file limit. Ordinary JPEGs have
// only a handful of metadata segments; a large ICC profile can use many more.
const MAX_METADATA_SEGMENTS: usize = 65_536;

pub(super) fn optimize(
    input: &[u8],
    quality: u8,
    lossy: bool,
    strip_metadata: bool,
    cancel: &CancellationToken,
) -> Result<Vec<u8>> {
    cancel.check()?;
    let (metadata, image_end) = scan_metadata(input, cancel)?;
    let image_bytes = &input[..image_end];
    let mut decoder = Decompressor::new().map_err(codec_error)?;
    let header = decoder.read_header(image_bytes).map_err(codec_error)?;
    let (width, height) = (header.width, header.height);
    if width == 0
        || height == 0
        || width > MAX_SOURCE_IMAGE_DIMENSION as usize
        || height > MAX_SOURCE_IMAGE_DIMENSION as usize
        || (width as u64) * (height as u64) > MAX_SOURCE_IMAGE_PIXELS
    {
        return Err(Error::InvalidInput(format!(
            "JPEG dimensions {width}x{height} exceed the source image limits"
        )));
    }
    let (pixel_format, channels) = match header.colorspace {
        Colorspace::Gray => (PixelFormat::GRAY, 1),
        Colorspace::RGB | Colorspace::YCbCr => (PixelFormat::RGB, 3),
        _ => {
            return Err(Error::InvalidInput(
                "JPEG optimization supports grayscale, RGB and YCbCr; CMYK/YCCK is unsupported"
                    .into(),
            ));
        }
    };
    cancel.check()?;
    let output = if lossy {
        let mut pixels = Vec::new();
        pixels
            .try_reserve_exact(width * height * channels)
            .map_err(|_| Error::ImageOptimization("JPEG pixel allocation failed".into()))?;
        pixels.resize(width * height * channels, 0);
        let mut image = Image {
            pixels,
            width,
            pitch: width * channels,
            height,
            format: pixel_format,
        };
        decoder
            .decompress(image_bytes, image.as_deref_mut())
            .map_err(codec_error)?;
        cancel.check()?;
        let mut encoder = Compressor::new().map_err(codec_error)?;
        encoder
            .set_quality(i32::from(quality))
            .map_err(codec_error)?;
        encoder.set_subsamp(header.subsamp).map_err(codec_error)?;
        // Preserve the encoded color space so restored Adobe/JFIF/ICC markers
        // retain their interpretation when metadata stripping is disabled.
        encoder
            .set_colorspace(header.colorspace)
            .map_err(codec_error)?;
        encoder.set_optimize(true).map_err(codec_error)?;
        encoder.set_progressive(true).map_err(codec_error)?;
        encoder
            .compress_to_vec(image.as_deref())
            .map_err(codec_error)?
    } else {
        // An identity transform entropy-encodes the existing quantized DCT
        // coefficients without pixel decoding, color conversion or added loss.
        // Restore metadata ourselves when requested so APP15 and metadata after
        // a progressive scan are retained as well.
        let mut transform = Transform::default();
        transform.optimize = true;
        transform.progressive = true;
        transform.copy_none = true;
        let mut transformer = Transformer::new().map_err(codec_error)?;
        cancel.check()?;
        transformer
            .transform_to_vec(&transform, image_bytes)
            .map_err(codec_error)?
    };
    cancel.check()?;
    let has_jfif = metadata.iter().any(|range| {
        let (marker, payload) = marker_payload(input, range);
        marker == 0xe0 && payload.starts_with(b"JFIF\0")
    });
    let candidate = if strip_metadata {
        let (metadata, image_end) = scan_metadata(&output, cancel)?;
        strip_extra_metadata(&output[..image_end], &metadata, has_jfif)?
    } else {
        restore_metadata(input, &metadata, output, cancel)?
    };
    // Entropy optimization and an optional lossy re-encode can be larger for an
    // already efficient JPEG. The original encoding remains a valid candidate,
    // but requested metadata removal must still be applied to that candidate.
    let original = if strip_metadata {
        // Bytes beyond EOI are not part of the decoded image and can contain
        // private editing data. They must not survive the smaller-file fallback.
        strip_extra_metadata(image_bytes, &metadata, has_jfif)?
    } else {
        input.to_vec()
    };
    cancel.check()?;
    if candidate.len() < original.len() {
        Ok(candidate)
    } else {
        Ok(original)
    }
}

fn codec_error(error: turbojpeg::Error) -> Error {
    Error::ImageOptimization(format!("JPEG codec: {error}"))
}

fn malformed(detail: &str) -> Error {
    Error::ImageOptimization(format!("Invalid JPEG: {detail}"))
}

// Preserve every APP0..APP15 and COM payload, including those encountered
// between progressive scans. Header-only marker extraction would silently miss
// metadata following the first scan.
fn metadata_segments(data: &[u8], cancel: &CancellationToken) -> Result<Vec<Range<usize>>> {
    scan_metadata(data, cancel).map(|(metadata, _)| metadata)
}

fn scan_metadata(data: &[u8], cancel: &CancellationToken) -> Result<(Vec<Range<usize>>, usize)> {
    if !data.starts_with(&[0xff, 0xd8]) {
        return Err(malformed("missing start marker"));
    }
    let mut metadata = Vec::new();
    let mut pos = 2;
    let mut scanned = false;
    loop {
        cancel.check()?;
        let start = pos;
        if data.get(pos) != Some(&0xff) {
            return Err(malformed("expected a marker"));
        }
        while data.get(pos) == Some(&0xff) {
            pos += 1;
        }
        let marker = *data.get(pos).ok_or_else(|| malformed("truncated marker"))?;
        pos += 1;
        match marker {
            0xd9 => {
                if !scanned {
                    return Err(malformed("missing image scan"));
                }
                return Ok((metadata, pos));
            }
            0x00 | 0xd8 => return Err(malformed("unexpected marker")),
            0x01 | 0xd0..=0xd7 => continue,
            _ => {}
        }
        let length = data
            .get(pos..pos + 2)
            .map(|bytes| usize::from(u16::from_be_bytes([bytes[0], bytes[1]])))
            .ok_or_else(|| malformed("truncated segment length"))?;
        if length < 2 || length > data.len().saturating_sub(pos) {
            return Err(malformed("truncated segment"));
        }
        pos += length;
        if marker == 0xfe || (0xe0..=0xef).contains(&marker) {
            if metadata.len() >= MAX_METADATA_SEGMENTS {
                return Err(malformed("too many metadata segments"));
            }
            metadata.push(start..pos);
        }
        if marker == 0xda {
            scanned = true;
            // Locate the next real marker, ignoring stuffed 0xff bytes and
            // restart markers. Scan in bounded batches so cancellation remains
            // responsive even for a very large entropy-coded segment.
            loop {
                cancel.check()?;
                let end = (pos + 65_536).min(data.len());
                match data[pos..end].iter().position(|&byte| byte == 0xff) {
                    Some(offset) => pos += offset,
                    None if end < data.len() => {
                        pos = end;
                        continue;
                    }
                    None => return Err(malformed("missing end marker")),
                }
                let marker_start = pos;
                while data.get(pos) == Some(&0xff) {
                    pos += 1;
                }
                let next = *data.get(pos).ok_or_else(|| malformed("truncated scan"))?;
                if next == 0 || (0xd0..=0xd7).contains(&next) {
                    pos += 1;
                    continue;
                }
                pos = marker_start;
                break;
            }
        }
    }
}

fn marker_payload<'a>(data: &'a [u8], range: &Range<usize>) -> (u8, &'a [u8]) {
    let segment = &data[range.clone()];
    let marker_offset = segment.iter().position(|&byte| byte != 0xff).unwrap();
    (segment[marker_offset], &segment[marker_offset + 3..])
}

fn strip_extra_metadata(
    input: &[u8],
    metadata: &[Range<usize>],
    keep_jfif: bool,
) -> Result<Vec<u8>> {
    let mut result = Vec::with_capacity(input.len());
    let mut copied = 0;
    for range in metadata {
        let (marker, payload) = marker_payload(input, range);
        result.extend_from_slice(&input[copied..range.start]);
        // Preserve color interpretation without carrying optional thumbnails or
        // private suffixes inside otherwise structural JFIF/Adobe markers, and
        // do not synthesize a JFIF marker when the source had none.
        if keep_jfif && marker == 0xe0 && payload.starts_with(b"JFIF\0") {
            let header = payload
                .get(..14)
                .ok_or_else(|| malformed("truncated JFIF header"))?;
            result.extend_from_slice(b"\xff\xe0\0\x10");
            result.extend_from_slice(&header[..12]);
            result.extend_from_slice(&[0, 0]); // no JFIF thumbnail
        } else if marker == 0xee && payload.starts_with(b"Adobe") {
            let header = payload
                .get(..12)
                .ok_or_else(|| malformed("truncated Adobe header"))?;
            result.extend_from_slice(b"\xff\xee\0\x0e");
            result.extend_from_slice(header);
        }
        copied = range.end;
    }
    result.extend_from_slice(&input[copied..]);
    Ok(result)
}

fn restore_metadata(
    input: &[u8],
    metadata: &[Range<usize>],
    output: Vec<u8>,
    cancel: &CancellationToken,
) -> Result<Vec<u8>> {
    let generated = metadata_segments(&output, cancel)?;
    let has_adobe = metadata.iter().any(|range| {
        let (marker, payload) = marker_payload(input, range);
        marker == 0xee && payload.starts_with(b"Adobe")
    });
    let metadata_size: usize = metadata.iter().map(Range::len).sum();
    let mut result = Vec::new();
    result
        .try_reserve_exact(output.len() + metadata_size)
        .map_err(|_| Error::ImageOptimization("JPEG output allocation failed".into()))?;
    result.extend_from_slice(&output[..2]);
    for range in metadata {
        result.extend_from_slice(&input[range.clone()]);
    }
    let mut copied = 2;
    for range in generated {
        let (marker, payload) = marker_payload(&output, &range);
        if (marker == 0xe0 && payload.starts_with(b"JFIF\0"))
            || (has_adobe && marker == 0xee && payload.starts_with(b"Adobe"))
        {
            result.extend_from_slice(&output[copied..range.start]);
            copied = range.end;
        }
    }
    result.extend_from_slice(&output[copied..]);
    cancel.check()?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use turbojpeg::Subsamp;

    fn fixture(colorspace: Colorspace, width: usize, height: usize) -> Vec<u8> {
        let (format, channels, subsamp) = match colorspace {
            Colorspace::Gray => (PixelFormat::GRAY, 1, Subsamp::Gray),
            Colorspace::CMYK => (PixelFormat::CMYK, 4, Subsamp::None),
            _ => (PixelFormat::RGB, 3, Subsamp::None),
        };
        let pixels: Vec<u8> = (0..width * height * channels)
            .map(|index| ((index * 71 + index / 37) % 256) as u8)
            .collect();
        let mut encoder = Compressor::new().unwrap();
        encoder.set_quality(98).unwrap();
        encoder.set_subsamp(subsamp).unwrap();
        encoder.set_colorspace(colorspace).unwrap();
        encoder.set_optimize(false).unwrap();
        let mut result = encoder
            .compress_to_vec(Image {
                pixels: &pixels[..],
                width,
                pitch: width * channels,
                height,
                format,
            })
            .unwrap();
        // EXIF orientation=6, ICC profile, APP15 and a comment must survive
        // byte-for-byte when callers choose to retain source metadata.
        let metadata = [
            (0xe1, &b"Exif\0\0II\x2a\0\x08\0\0\0\x01\0\x12\x01\x03\0\x01\0\0\0\x06\0\0\0\0\0\0\0keep-exif"[..]),
            (0xe2, &b"ICC_PROFILE\0\x01\x01keep-profile"[..]),
            (0xef, &b"keep-app15"[..]),
            (0xfe, &b"keep-comment"[..]),
        ];
        let mut additions = Vec::new();
        for (marker, payload) in metadata {
            additions.extend_from_slice(&[0xff, marker]);
            additions.extend_from_slice(&((payload.len() + 2) as u16).to_be_bytes());
            additions.extend_from_slice(payload);
        }
        // Put source metadata after the codec's mandatory JFIF/Adobe marker.
        let existing = metadata_segments(&result, &CancellationToken::default()).unwrap();
        let offset = existing.first().map_or(2, |range| range.end);
        result.splice(offset..offset, additions);
        result
    }

    fn pixels(input: &[u8], format: PixelFormat) -> Vec<u8> {
        turbojpeg::decompress(input, format).unwrap().pixels
    }

    fn payloads(data: &[u8]) -> Vec<(u8, Vec<u8>)> {
        metadata_segments(data, &CancellationToken::default())
            .unwrap()
            .iter()
            .map(|range| {
                let (marker, payload) = marker_payload(data, range);
                (marker, payload.to_vec())
            })
            .collect()
    }

    #[test]
    fn lossless_optimization_reduces_size_and_preserves_decoded_pixels() {
        let input = fixture(Colorspace::YCbCr, 96, 64);
        let output = optimize(&input, 1, false, false, &CancellationToken::default()).unwrap();
        assert!(output.len() < input.len());
        assert_eq!(
            pixels(&output, PixelFormat::RGB),
            pixels(&input, PixelFormat::RGB)
        );
        assert_eq!(payloads(&input), payloads(&output));
        // The inactive quality value cannot affect lossless output.
        assert_eq!(
            output,
            optimize(&input, 100, false, false, &CancellationToken::default()).unwrap()
        );
    }

    #[test]
    fn metadata_stripping_removes_exif_profiles_comments_and_app15() {
        let input = fixture(Colorspace::YCbCr, 48, 32);
        let output = optimize(&input, 80, false, true, &CancellationToken::default()).unwrap();
        let metadata = payloads(&output);
        assert!(metadata
            .iter()
            .all(|(marker, _)| [0xe0, 0xee].contains(marker)));
        assert_eq!(
            pixels(&output, PixelFormat::RGB),
            pixels(&input, PixelFormat::RGB)
        );
        assert!(!output.windows(5).any(|bytes| bytes == b"Exif\0"));
    }

    #[test]
    fn explicit_lossy_recompression_reduces_size_and_keeps_metadata_on_request() {
        let input = fixture(Colorspace::YCbCr, 96, 64);
        let output = optimize(&input, 65, true, false, &CancellationToken::default()).unwrap();
        assert!(output.len() < input.len());
        assert_eq!(payloads(&input), payloads(&output));
        let header = turbojpeg::read_header(&output).unwrap();
        assert_eq!((header.width, header.height), (96, 64));
        assert_ne!(
            pixels(&input, PixelFormat::RGB),
            pixels(&output, PixelFormat::RGB)
        );
    }

    #[test]
    fn rejects_malformed_truncated_and_non_image_jpegs() {
        let token = CancellationToken::default();
        for input in [
            &b"not-a-jpeg"[..],
            &[0xff, 0xd8, 0xff, 0xd9][..],
            &[0xff, 0xd8, 0xff, 0xe1, 0, 50, 0][..],
            &[0xff, 0xd8, 0xff, 0xda, 0, 2, 0xff, 0xd9][..],
        ] {
            assert!(optimize(input, 80, false, true, &token).is_err());
        }
        let input = fixture(Colorspace::YCbCr, 8, 8);
        assert!(optimize(&input[..input.len() - 2], 80, false, true, &token).is_err());
    }

    #[test]
    fn rejects_oversized_headers_before_decoding_pixels() {
        let token = CancellationToken::default();
        let original = fixture(Colorspace::YCbCr, 8, 8);
        let frame = original
            .windows(2)
            .position(|bytes| bytes[0] == 0xff && [0xc0, 0xc1, 0xc2].contains(&bytes[1]))
            .unwrap();
        for (width, height) in [
            ((MAX_SOURCE_IMAGE_DIMENSION + 1) as u16, 1_u16),
            (8_000, 8_000),
        ] {
            let mut input = original.clone();
            input[frame + 5..frame + 7].copy_from_slice(&height.to_be_bytes());
            input[frame + 7..frame + 9].copy_from_slice(&width.to_be_bytes());
            assert!(matches!(
                optimize(&input, 80, false, true, &token),
                Err(Error::InvalidInput(_))
            ));
        }
    }

    #[test]
    fn rejects_cmyk_instead_of_changing_its_color_interpretation() {
        let input = fixture(Colorspace::CMYK, 8, 8);
        assert!(matches!(
            optimize(&input, 80, false, true, &CancellationToken::default()),
            Err(Error::InvalidInput(_))
        ));
    }

    #[test]
    fn retains_grayscale_and_rgb_encoding_with_unchanged_pixels() {
        let token = CancellationToken::default();
        for (color, format) in [
            (Colorspace::Gray, PixelFormat::GRAY),
            (Colorspace::RGB, PixelFormat::RGB),
        ] {
            let input = fixture(color, 32, 24);
            let output = optimize(&input, 80, false, false, &token).unwrap();
            let header = turbojpeg::read_header(&output).unwrap();
            assert_eq!(header.colorspace, color);
            assert_eq!((header.width, header.height), (32, 24));
            assert_eq!(pixels(&input, format), pixels(&output, format));
            assert_eq!(payloads(&input), payloads(&output));
        }
    }

    #[test]
    fn preserves_metadata_after_an_image_scan() {
        let token = CancellationToken::default();
        let mut input = fixture(Colorspace::YCbCr, 16, 16);
        let marker = b"\xff\xef\0\x0ckeep-late!";
        input.splice(input.len() - 2..input.len() - 2, marker.iter().copied());
        let output = optimize(&input, 80, false, false, &token).unwrap();
        assert_eq!(
            output
                .windows(marker.len())
                .filter(|bytes| *bytes == marker)
                .count(),
            1
        );
        assert_eq!(
            pixels(&input, PixelFormat::RGB),
            pixels(&output, PixelFormat::RGB)
        );
    }

    #[test]
    fn observes_cancellation_before_entering_the_codec() {
        let token = CancellationToken::default();
        token.cancel();
        assert!(matches!(
            optimize(&[], 80, false, true, &token),
            Err(Error::Cancelled)
        ));
    }

    #[test]
    fn repeated_optimization_never_grows_or_restores_stripped_metadata() {
        let token = CancellationToken::default();
        for strip in [false, true] {
            for (color, format) in [
                (Colorspace::Gray, PixelFormat::GRAY),
                (Colorspace::YCbCr, PixelFormat::RGB),
            ] {
                let mut input = fixture(color, 17, 31);
                let original_pixels = pixels(&input, format);
                for _ in 0..3 {
                    let output = optimize(&input, 80, false, strip, &token).unwrap();
                    assert!(output.len() <= input.len());
                    assert_eq!(pixels(&output, format), original_pixels);
                    if strip {
                        assert!(payloads(&output)
                            .iter()
                            .all(|(marker, _)| [0xe0, 0xee].contains(marker)));
                    } else {
                        assert_eq!(payloads(&input), payloads(&output));
                    }
                    input = output;
                }
            }
        }
    }
}
