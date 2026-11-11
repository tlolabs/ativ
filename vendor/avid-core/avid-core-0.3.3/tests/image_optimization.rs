// SPDX-FileCopyrightText: Thomas Lothian
// SPDX-License-Identifier: GPL-3.0-or-later

use avid_core::{
    optimize_image, CancellationToken, Error, ImageOptimizationOptions, ImageOptimizationRequest,
    OptimizationEffort, OptimizedImageFormat,
};
use std::{fs, io::Cursor, path::Path};

fn request(input: &Path, output: &Path) -> ImageOptimizationRequest {
    ImageOptimizationRequest {
        input: input.to_path_buf(),
        output: output.to_path_buf(),
        options: ImageOptimizationOptions {
            png_zopfli: false,
            ..ImageOptimizationOptions::default()
        },
        protected_paths: Vec::new(),
    }
}

fn rgba_pixels(width: u32, height: u32) -> Vec<u8> {
    let mut pixels = Vec::with_capacity((width * height * 4) as usize);
    for y in 0..height {
        for x in 0..width {
            pixels.extend_from_slice(&[
                x as u8,
                y as u8,
                (x.wrapping_mul(7) ^ y.wrapping_mul(11)) as u8,
                255,
            ]);
        }
    }
    pixels
}

fn png_fixture(width: u32, height: u32, pixels: &[u8]) -> Vec<u8> {
    let mut encoded = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut encoded, width, height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        encoder.set_compression(png::Compression::Fast);
        encoder.set_filter(png::FilterType::NoFilter);
        encoder
            .add_text_chunk("Description".into(), "AVID artwork source metadata".into())
            .unwrap();
        encoder.set_source_gamma(png::ScaledFloat::new(0.45455));
        let mut writer = encoder.write_header().unwrap();
        writer.write_image_data(pixels).unwrap();
    }
    encoded
}

fn png16_fixture(width: u32, height: u32, samples: &[u8]) -> Vec<u8> {
    let mut encoded = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut encoded, width, height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Sixteen);
        encoder.set_compression(png::Compression::Fast);
        encoder.set_filter(png::FilterType::NoFilter);
        encoder
            .add_text_chunk("Description".into(), "AVID 16-bit artwork".into())
            .unwrap();
        encoder
            .write_header()
            .unwrap()
            .write_image_data(samples)
            .unwrap();
    }
    encoded
}

fn decode_png(bytes: &[u8]) -> (u32, u32, Vec<u8>) {
    let (info, decoded) = decode_png_samples(bytes);
    assert!(matches!(
        info.color_type,
        png::ColorType::Rgb | png::ColorType::Rgba
    ));
    assert_eq!(info.bit_depth, png::BitDepth::Eight);
    (info.width, info.height, decoded)
}

fn decode_png_samples(bytes: &[u8]) -> (png::OutputInfo, Vec<u8>) {
    let mut decoder = png::Decoder::new(Cursor::new(bytes));
    decoder.set_transformations(png::Transformations::EXPAND);
    let mut reader = decoder.read_info().unwrap();
    let mut decoded = vec![0; reader.output_buffer_size()];
    let info = reader.next_frame(&mut decoded).unwrap();
    decoded.truncate(info.buffer_size());
    let decoded = match info.color_type {
        png::ColorType::Rgba => decoded,
        png::ColorType::Rgb => {
            let sample_bytes = if info.bit_depth == png::BitDepth::Sixteen {
                2
            } else {
                1
            };
            decoded
                .chunks_exact(3 * sample_bytes)
                .flat_map(|pixel| {
                    let mut rgba = pixel.to_vec();
                    rgba.extend(std::iter::repeat_n(255, sample_bytes));
                    rgba
                })
                .collect()
        }
        other => panic!("expected decoded RGB/RGBA artwork, got {other:?}"),
    };
    (info, decoded)
}

fn png_chunks(bytes: &[u8]) -> Vec<([u8; 4], &[u8])> {
    assert_eq!(&bytes[..8], b"\x89PNG\r\n\x1a\n");
    let mut chunks = Vec::new();
    let mut offset = 8;
    while offset < bytes.len() {
        let length = u32::from_be_bytes(bytes[offset..offset + 4].try_into().unwrap()) as usize;
        let kind = bytes[offset + 4..offset + 8].try_into().unwrap();
        chunks.push((kind, &bytes[offset + 8..offset + 8 + length]));
        offset += 12 + length;
    }
    chunks
}

fn png_chunk(kind: &[u8; 4], contents: &[u8]) -> Vec<u8> {
    let mut bytes = (contents.len() as u32).to_be_bytes().to_vec();
    bytes.extend_from_slice(kind);
    bytes.extend_from_slice(contents);
    let mut crc = !0_u32;
    for byte in &bytes[4..] {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xedb8_8320 & 0_u32.wrapping_sub(crc & 1));
        }
    }
    bytes.extend_from_slice(&(!crc).to_be_bytes());
    bytes
}

fn write_png(path: &Path) -> Vec<u8> {
    let bytes = png_fixture(192, 128, &rgba_pixels(192, 128));
    fs::write(path, &bytes).unwrap();
    bytes
}

#[test]
fn png_reduces_size_and_preserves_opaque_pixels_and_metadata() {
    let directory = tempfile::tempdir().unwrap();
    // Recognition must use file contents; source suffixes are not authoritative.
    let input = directory.path().join("source.data");
    let output = directory.path().join("optimized.PNG");
    let original = write_png(&input);
    let mut operation = request(&input, &output);
    operation.options.strip_png_metadata = false;
    let result = optimize_image(&operation, &CancellationToken::default()).unwrap();
    let optimized = fs::read(&output).unwrap();

    assert_eq!(result.format, OptimizedImageFormat::Png);
    assert!(result.optimized);
    assert_eq!(result.input_bytes, original.len() as u64);
    assert_eq!(result.output_bytes, optimized.len() as u64);
    assert!(result.output_bytes < result.input_bytes);
    assert_eq!(result.bytes_saved, result.input_bytes - result.output_bytes);
    assert_eq!(decode_png(&optimized), (192, 128, rgba_pixels(192, 128)));
    for kind in [*b"tEXt", *b"gAMA"] {
        assert_eq!(
            png_chunks(&optimized)
                .iter()
                .find(|(name, _)| *name == kind),
            png_chunks(&original).iter().find(|(name, _)| *name == kind),
            "metadata chunk {:?} changed",
            kind
        );
    }
    assert_eq!(fs::read(&input).unwrap(), original);
}

#[test]
fn default_png_optimization_strips_metadata_and_preserves_pixels() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("source.png");
    let output = directory.path().join("optimized.png");
    let original = png_fixture(2, 2, &rgba_pixels(2, 2));
    fs::write(&input, &original).unwrap();
    let mut operation = request(&input, &output);
    operation.options = ImageOptimizationOptions::default();
    let result = optimize_image(&operation, &CancellationToken::default()).unwrap();
    let optimized = fs::read(&output).unwrap();
    assert!(result.optimized);
    assert_eq!(decode_png(&optimized), (2, 2, rgba_pixels(2, 2)));
    for kind in [*b"tEXt", *b"gAMA"] {
        assert!(!png_chunks(&optimized).iter().any(|(name, _)| *name == kind));
    }
    assert_eq!(fs::read(&input).unwrap(), original);
}

#[test]
fn repeated_png_optimization_never_grows_and_reports_original_copy_fallback() {
    let directory = tempfile::tempdir().unwrap();
    let mut input = directory.path().join("source.png");
    write_png(&input);
    let mut saw_fallback = false;
    for generation in 0..5 {
        let output = directory
            .path()
            .join(format!("generation-{generation}.png"));
        let original = fs::read(&input).unwrap();
        let result =
            optimize_image(&request(&input, &output), &CancellationToken::default()).unwrap();
        let optimized = fs::read(&output).unwrap();
        assert!(optimized.len() <= original.len());
        assert_eq!(result.optimized, optimized.len() < original.len());
        assert_eq!(
            result.bytes_saved,
            (original.len() - optimized.len()) as u64
        );
        if !result.optimized {
            assert_eq!(
                optimized, original,
                "fallback must copy original bytes exactly"
            );
            saw_fallback = true;
        }
        assert_eq!(decode_png(&optimized), (192, 128, rgba_pixels(192, 128)));
        input = output;
    }
    assert!(
        saw_fallback,
        "a deterministic optimized PNG should reach a fixed point"
    );
}

#[test]
fn png_preserves_sixteen_bit_samples_and_opaque_indexed_pixels() {
    let directory = tempfile::tempdir().unwrap();
    let mut sixteen_bit = Vec::new();
    let mut samples = Vec::new();
    for y in 0..32_u16 {
        for x in 0..48_u16 {
            for sample in [x * 1_031, y * 1_507, x * 883 + y * 379, u16::MAX] {
                samples.extend_from_slice(&sample.to_be_bytes());
            }
        }
    }
    {
        let mut encoder = png::Encoder::new(&mut sixteen_bit, 48, 32);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Sixteen);
        encoder.set_compression(png::Compression::Fast);
        encoder.set_filter(png::FilterType::NoFilter);
        encoder
            .write_header()
            .unwrap()
            .write_image_data(&samples)
            .unwrap();
    }
    let mut indexed = Vec::new();
    let palette = [90, 40, 200, 100, 200, 50, 0, 120, 240, 250, 5, 130];
    let alpha = [255_u8; 4];
    let mut expected_palette_pixels = Vec::new();
    let mut packed = Vec::new();
    for y in 0..16 {
        for group in 0..4 {
            let mut byte = 0;
            for member in 0..4 {
                let index = (y + group * 4 + member) % 4;
                byte |= (index as u8) << (6 - member * 2);
                expected_palette_pixels.extend_from_slice(&palette[index * 3..index * 3 + 3]);
                expected_palette_pixels.push(255);
            }
            packed.push(byte);
        }
    }
    {
        let mut encoder = png::Encoder::new(&mut indexed, 16, 16);
        encoder.set_color(png::ColorType::Indexed);
        encoder.set_depth(png::BitDepth::Two);
        encoder.set_palette(palette.to_vec());
        encoder.set_trns(alpha.to_vec());
        encoder
            .write_header()
            .unwrap()
            .write_image_data(&packed)
            .unwrap();
    }
    for (name, original, expected, depth, dimensions) in [
        (
            "sixteen-bit",
            sixteen_bit,
            samples,
            png::BitDepth::Sixteen,
            (48, 32),
        ),
        (
            "indexed",
            indexed,
            expected_palette_pixels,
            png::BitDepth::Eight,
            (16, 16),
        ),
    ] {
        let input = directory.path().join(format!("{name}.png"));
        let output = directory.path().join(format!("{name}-optimized.png"));
        fs::write(&input, &original).unwrap();
        let result =
            optimize_image(&request(&input, &output), &CancellationToken::default()).unwrap();
        let optimized = fs::read(&output).unwrap();
        assert!(optimized.len() <= original.len());
        assert_eq!(
            result.bytes_saved,
            (original.len() as u64).saturating_sub(optimized.len() as u64)
        );
        assert_eq!(result.optimized, optimized.len() < original.len());
        let (info, decoded) = decode_png_samples(&optimized);
        assert_eq!((info.width, info.height), dimensions);
        assert!(matches!(
            info.color_type,
            png::ColorType::Rgb | png::ColorType::Rgba
        ));
        assert_eq!(info.bit_depth, depth);
        assert_eq!(decoded, expected);
        assert_eq!(fs::read(&input).unwrap(), original);
    }
}

#[test]
fn transparent_png_artwork_is_rejected_without_touching_output() {
    let directory = tempfile::tempdir().unwrap();
    let samples16 = [
        0x0102_u16,
        0x0304,
        0x0506,
        0,
        0x1234,
        0xabcd,
        0x2345,
        u16::MAX,
    ];
    let samples16 = samples16
        .into_iter()
        .flat_map(u16::to_be_bytes)
        .collect::<Vec<_>>();
    let mut indexed = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut indexed, 2, 1);
        encoder.set_color(png::ColorType::Indexed);
        encoder.set_depth(png::BitDepth::One);
        encoder.set_palette(vec![10, 20, 30, 40, 50, 60]);
        encoder.set_trns(vec![0, 255]);
        encoder
            .write_header()
            .unwrap()
            .write_image_data(&[0b0100_0000])
            .unwrap();
    }
    for (name, original) in [
        (
            "eight-bit",
            png_fixture(2, 1, &[1, 2, 3, 0, 40, 50, 60, 255]),
        ),
        ("sixteen-bit", png16_fixture(2, 1, &samples16)),
        ("indexed", indexed),
    ] {
        let input = directory.path().join(format!("{name}.png"));
        let output = directory.path().join(format!("{name}-output.png"));
        fs::write(&input, &original).unwrap();
        fs::write(&output, b"existing output").unwrap();
        for strip_metadata in [true, false] {
            let mut operation = request(&input, &output);
            operation.options.strip_png_metadata = strip_metadata;
            let error = optimize_image(&operation, &CancellationToken::default()).unwrap_err();
            assert_eq!(error.code(), "invalid_input");
            assert_eq!(fs::read(&output).unwrap(), b"existing output");
        }
        assert_eq!(fs::read(&input).unwrap(), original);
    }
}

#[test]
fn saved_settings_roundtrip_and_missing_fields_use_album_artwork_defaults() {
    let defaults = ImageOptimizationOptions::default();
    assert!(!defaults.lossy);
    assert_eq!(defaults.jpeg_quality, 80);
    assert!(defaults.strip_jpeg_metadata && defaults.strip_png_metadata && defaults.png_zopfli);
    assert!(matches!(defaults.effort, OptimizationEffort::Extra));
    let missing: ImageOptimizationOptions = serde_json::from_str("{}").unwrap();
    assert_eq!(
        serde_json::to_value(&missing).unwrap(),
        serde_json::to_value(&defaults).unwrap()
    );

    let configured = ImageOptimizationOptions {
        lossy: true,
        jpeg_quality: 61,
        strip_jpeg_metadata: false,
        strip_png_metadata: false,
        effort: OptimizationEffort::Insane,
        png_zopfli: false,
    };
    let saved = serde_json::to_value(&configured).unwrap();
    let restored: ImageOptimizationOptions = serde_json::from_value(saved.clone()).unwrap();
    assert_eq!(serde_json::to_value(&restored).unwrap(), saved);
    let mut invalid = saved;
    invalid["effort"] = serde_json::json!("unrecognized");
    assert!(serde_json::from_value::<ImageOptimizationOptions>(invalid).is_err());
}

const EXIF: &[u8] = b"Exif\0\0II\x2a\0\x08\0\0\0\0\0\0\0\0\0";
const ICC: &[u8] = b"ICC_PROFILE\0\x01\x01AVID test profile payload";
const COMMENT: &[u8] = b"AVID source comment retained during recompression";

fn jpeg_fixture(format: turbojpeg::PixelFormat) -> Vec<u8> {
    let width = 192;
    let height = 128;
    let components = format.size();
    let mut pixels = Vec::with_capacity(width * height * components);
    let mut seed = 0x1234_5678_u32;
    for _ in 0..width * height * components {
        seed = seed.wrapping_mul(1_664_525).wrapping_add(1_013_904_223);
        pixels.push((seed >> 24) as u8);
    }
    let mut compressor = turbojpeg::Compressor::new().unwrap();
    compressor.set_quality(100).unwrap();
    compressor.set_subsamp(turbojpeg::Subsamp::None).unwrap();
    let encoded = compressor
        .compress_to_vec(turbojpeg::Image {
            pixels: pixels.as_slice(),
            width,
            height,
            pitch: width * components,
            format,
        })
        .unwrap();
    // Inject real JPEG marker framing independently of the production metadata
    // parser so both retention and stripping are tested with controlled bytes.
    let mut marked = encoded[..2].to_vec();
    for (marker, payload) in [(0xe1, EXIF), (0xe2, ICC), (0xfe, COMMENT)] {
        marked.extend_from_slice(&[0xff, marker]);
        marked.extend_from_slice(&((payload.len() + 2) as u16).to_be_bytes());
        marked.extend_from_slice(payload);
    }
    marked.extend_from_slice(&encoded[2..]);
    marked
}

fn jpeg_header_markers(bytes: &[u8]) -> Vec<(u8, Vec<u8>)> {
    assert_eq!(&bytes[..2], &[0xff, 0xd8]);
    let mut offset = 2;
    let mut markers = Vec::new();
    loop {
        assert_eq!(bytes[offset], 0xff);
        while bytes[offset] == 0xff {
            offset += 1;
        }
        let marker = bytes[offset];
        offset += 1;
        if marker == 0xda || marker == 0xd9 {
            break;
        }
        let length = u16::from_be_bytes(bytes[offset..offset + 2].try_into().unwrap()) as usize;
        markers.push((marker, bytes[offset + 2..offset + length].to_vec()));
        offset += length;
    }
    markers
}

fn decode_jpeg(bytes: &[u8]) -> ((usize, usize), Vec<u8>) {
    let mut decoder = turbojpeg::Decompressor::new().unwrap();
    let header = decoder.read_header(bytes).unwrap();
    let mut pixels = vec![0; header.width * header.height * 3];
    decoder
        .decompress(
            bytes,
            turbojpeg::Image {
                pixels: pixels.as_mut_slice(),
                width: header.width,
                height: header.height,
                pitch: header.width * 3,
                format: turbojpeg::PixelFormat::RGB,
            },
        )
        .unwrap();
    ((header.width, header.height), pixels)
}

#[test]
fn jpeg_lower_quality_reduces_size_preserves_dimensions_and_markers() {
    let directory = tempfile::tempdir().unwrap();
    for suffix in ["jpg", "JPEG"] {
        let input = directory.path().join(format!("source-{suffix}.data"));
        let output = directory.path().join(format!("optimized.{suffix}"));
        let original = jpeg_fixture(turbojpeg::PixelFormat::RGB);
        fs::write(&input, &original).unwrap();
        let mut operation = request(&input, &output);
        operation.options.lossy = true;
        operation.options.strip_jpeg_metadata = false;
        operation.options.jpeg_quality = 65;
        let result = optimize_image(&operation, &CancellationToken::default()).unwrap();
        let optimized = fs::read(&output).unwrap();
        assert_eq!(result.format, OptimizedImageFormat::Jpeg);
        assert!(result.optimized);
        assert_eq!(result.input_bytes, original.len() as u64);
        assert_eq!(result.output_bytes, optimized.len() as u64);
        assert!(result.output_bytes < result.input_bytes);
        assert_eq!(result.bytes_saved, result.input_bytes - result.output_bytes);
        let (dimensions, decoded) = decode_jpeg(&optimized);
        assert_eq!(dimensions, (192, 128));
        assert_eq!(decoded.len(), 192 * 128 * 3);
        let markers = jpeg_header_markers(&optimized);
        for (kind, bytes) in [(0xe1, EXIF), (0xe2, ICC), (0xfe, COMMENT)] {
            assert!(markers
                .iter()
                .any(|(marker, data)| *marker == kind && data == bytes));
        }
        assert_eq!(fs::read(&input).unwrap(), original);
    }
}

#[test]
fn default_jpeg_optimization_is_lossless_and_strips_metadata() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("source.jpg");
    let output = directory.path().join("optimized.jpg");
    let original = jpeg_fixture(turbojpeg::PixelFormat::RGB);
    fs::write(&input, &original).unwrap();
    let result = optimize_image(&request(&input, &output), &CancellationToken::default()).unwrap();
    let optimized = fs::read(&output).unwrap();
    assert_eq!(result.format, OptimizedImageFormat::Jpeg);
    assert!(result.output_bytes <= result.input_bytes);
    assert_eq!(decode_jpeg(&original), decode_jpeg(&optimized));
    assert!(!jpeg_header_markers(&optimized)
        .iter()
        .any(|(marker, _)| [0xe1, 0xe2, 0xfe].contains(marker)));
    assert_eq!(fs::read(&input).unwrap(), original);
}

#[test]
fn options_reject_invalid_values_without_touching_output() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("input.png");
    let output = directory.path().join("output.png");
    write_png(&input);
    for quality in [0, 101] {
        fs::write(&output, b"existing output").unwrap();
        let mut operation = request(&input, &output);
        operation.options.jpeg_quality = quality;
        let error = optimize_image(&operation, &CancellationToken::default()).unwrap_err();
        assert_eq!(error.code(), "invalid_input");
        assert_eq!(fs::read(&output).unwrap(), b"existing output");
    }
}

#[test]
fn malformed_unsupported_and_mismatched_images_leave_existing_output_untouched() {
    let directory = tempfile::tempdir().unwrap();
    for (name, bytes, suffix) in [
        ("unknown", b"GIF89a".to_vec(), "png"),
        ("truncated-png", b"\x89PNG\r\n\x1a\n".to_vec(), "png"),
        (
            "truncated-jpeg",
            b"\xff\xd8\xff\xe0\0\x10JFIF\0".to_vec(),
            "jpg",
        ),
        (
            "wrong-extension",
            png_fixture(2, 2, &rgba_pixels(2, 2)),
            "jpg",
        ),
    ] {
        let input = directory.path().join(name);
        let output = directory.path().join(format!("output.{suffix}"));
        fs::write(&input, &bytes).unwrap();
        fs::write(&output, b"existing output").unwrap();
        assert!(optimize_image(&request(&input, &output), &CancellationToken::default()).is_err());
        assert_eq!(fs::read(&input).unwrap(), bytes);
        assert_eq!(fs::read(&output).unwrap(), b"existing output");
    }
    assert_eq!(
        Error::ImageOptimization("codec failed".into()).code(),
        "image_optimization_failed"
    );
}

#[test]
fn png_codec_failures_preserve_existing_output() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("corrupt.png");
    let output = directory.path().join("output.png");
    let valid = png_fixture(2, 2, &rgba_pixels(2, 2));
    let mut bad_crc = valid.clone();
    // The final IHDR CRC byte; all framing and image bytes remain valid.
    bad_crc[32] ^= 1;
    let mut corrupt_idat = valid[..8].to_vec();
    for (kind, contents) in png_chunks(&valid) {
        corrupt_idat.extend(png_chunk(
            &kind,
            if kind == *b"IDAT" {
                &[0x78, 0x9c, 0xff]
            } else {
                contents
            },
        ));
    }
    for damaged in [bad_crc, corrupt_idat] {
        fs::write(&input, &damaged).unwrap();
        fs::write(&output, b"existing output").unwrap();
        let error =
            optimize_image(&request(&input, &output), &CancellationToken::default()).unwrap_err();
        assert_eq!(error.code(), "image_optimization_failed");
        assert_eq!(fs::read(&input).unwrap(), damaged);
        assert_eq!(fs::read(&output).unwrap(), b"existing output");
    }
}

#[test]
fn png_checksum_failures_are_rejected_before_metadata_stripping() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("corrupt.png");
    let output = directory.path().join("output.png");
    let mut valid = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut valid, 2, 1);
        encoder.set_color(png::ColorType::Grayscale);
        encoder.set_depth(png::BitDepth::Eight);
        encoder
            .write_header()
            .unwrap()
            .write_image_data(&[17, 90])
            .unwrap();
    }
    let mut cases = Vec::new();
    for (kind, contents) in [
        (*b"tEXt", &b"Comment\0source metadata"[..]),
        (*b"gAMA", &45_455_u32.to_be_bytes()[..]),
        // Valid, unused transparency; only its checksum is corrupt.
        (*b"tRNS", &[0, 2][..]),
    ] {
        let mut chunk = png_chunk(&kind, contents);
        *chunk.last_mut().unwrap() ^= 1;
        let mut damaged = valid[..33].to_vec();
        damaged.extend(chunk);
        damaged.extend_from_slice(&valid[33..]);
        cases.push(damaged);
    }
    let mut bad_adler = valid[..8].to_vec();
    let mut image_data_chunks = 0;
    for (kind, contents) in png_chunks(&valid) {
        let mut contents = contents.to_vec();
        if kind == *b"IDAT" {
            image_data_chunks += 1;
            // Corrupt the zlib Adler-32 while keeping the enclosing PNG CRC valid.
            *contents.last_mut().unwrap() ^= 1;
        }
        bad_adler.extend(png_chunk(&kind, &contents));
    }
    assert_eq!(image_data_chunks, 1);
    cases.push(bad_adler);

    for damaged in cases {
        fs::write(&input, &damaged).unwrap();
        for strip_metadata in [true, false] {
            fs::write(&output, b"existing output").unwrap();
            let mut operation = request(&input, &output);
            operation.options.strip_png_metadata = strip_metadata;
            let error = optimize_image(&operation, &CancellationToken::default()).unwrap_err();
            assert_eq!(error.code(), "image_optimization_failed");
            assert_eq!(fs::read(&input).unwrap(), damaged);
            assert_eq!(fs::read(&output).unwrap(), b"existing output");
            // Failed validation must not leave any staged publication behind.
            assert_eq!(fs::read_dir(directory.path()).unwrap().count(), 2);
        }
    }
}

#[test]
fn animated_png_control_chunks_are_rejected_before_output_publication() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("animation.png");
    let output = directory.path().join("output.png");
    let still = png_fixture(2, 2, &rgba_pixels(2, 2));
    for (kind, contents) in [
        (*b"acTL", &[0, 0, 0, 2, 0, 0, 0, 0][..]),
        (*b"fcTL", &[0][..]),
        (*b"fdAT", &[0][..]),
    ] {
        let mut animated = still[..33].to_vec(); // Immediately after IHDR.
        animated.extend(png_chunk(&kind, contents));
        animated.extend_from_slice(&still[33..]);
        fs::write(&input, &animated).unwrap();
        fs::write(&output, b"existing output").unwrap();
        let error =
            optimize_image(&request(&input, &output), &CancellationToken::default()).unwrap_err();
        assert_eq!(error.code(), "invalid_input");
        assert_eq!(fs::read(&output).unwrap(), b"existing output");
        assert_eq!(fs::read(&input).unwrap(), animated);
    }
}

#[test]
fn duplicate_png_header_cannot_override_prechecked_dimensions() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("duplicate-header.png");
    let output = directory.path().join("output.png");
    let still = png_fixture(2, 2, &rgba_pixels(2, 2));
    for (width, height) in [(1_u32, 1_u32), (32_768, 32_768)] {
        let mut ihdr = width.to_be_bytes().to_vec();
        ihdr.extend_from_slice(&height.to_be_bytes());
        ihdr.extend_from_slice(&[8, 6, 0, 0, 0]);
        let mut duplicate = still[..33].to_vec();
        duplicate.extend(png_chunk(b"IHDR", &ihdr));
        duplicate.extend_from_slice(&still[33..]);
        fs::write(&input, &duplicate).unwrap();
        fs::write(&output, b"existing output").unwrap();
        let error =
            optimize_image(&request(&input, &output), &CancellationToken::default()).unwrap_err();
        assert_eq!(error.code(), "image_optimization_failed");
        assert_eq!(fs::read(&output).unwrap(), b"existing output");
        assert_eq!(fs::read(&input).unwrap(), duplicate);
    }
}

#[test]
fn trailing_png_transparency_cannot_bypass_artwork_opacity_checks() {
    let directory = tempfile::tempdir().unwrap();
    for (name, color, pixels, transparent_key) in [
        (
            "rgb",
            png::ColorType::Rgb,
            &[4, 5, 6, 40, 50, 60][..],
            &[0, 4, 0, 5, 0, 6][..],
        ),
        (
            "grayscale",
            png::ColorType::Grayscale,
            &[17, 90][..],
            &[0, 17][..],
        ),
    ] {
        let mut encoded = Vec::new();
        {
            let mut encoder = png::Encoder::new(&mut encoded, 2, 1);
            encoder.set_color(color);
            encoder.set_depth(png::BitDepth::Eight);
            encoder
                .write_header()
                .unwrap()
                .write_image_data(pixels)
                .unwrap();
        }
        let mut trailing_transparency = encoded[..8].to_vec();
        for (kind, contents) in png_chunks(&encoded) {
            if kind == *b"IEND" {
                // The transparent color matches the first decoded pixel. tRNS
                // belongs before IDAT and must not change opacity after checking.
                trailing_transparency.extend(png_chunk(b"tRNS", transparent_key));
            }
            trailing_transparency.extend(png_chunk(&kind, contents));
        }
        let input = directory
            .path()
            .join(format!("{name}-late-transparency.png"));
        let output = directory.path().join(format!("{name}-output.png"));
        fs::write(&input, &trailing_transparency).unwrap();
        fs::write(&output, b"existing output").unwrap();
        for strip_metadata in [true, false] {
            let mut operation = request(&input, &output);
            operation.options.strip_png_metadata = strip_metadata;
            let error = optimize_image(&operation, &CancellationToken::default()).unwrap_err();
            assert_eq!(error.code(), "image_optimization_failed");
            assert_eq!(fs::read(&input).unwrap(), trailing_transparency);
            assert_eq!(fs::read(&output).unwrap(), b"existing output");
        }
    }
}

#[test]
fn malformed_or_out_of_range_png_trns_cannot_bypass_opacity_checks() {
    let directory = tempfile::tempdir().unwrap();
    // 1. 16-bit grayscale with 4-byte tRNS (trailing bytes ignored by OxiPNG, rejected by png 0.17)
    let mut gray16 = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut gray16, 2, 1);
        encoder.set_color(png::ColorType::Grayscale);
        encoder.set_depth(png::BitDepth::Sixteen);
        encoder
            .write_header()
            .unwrap()
            .write_image_data(&[0, 16, 0, 90])
            .unwrap();
    }
    let mut gray16_padded_trns = gray16[..33].to_vec();
    gray16_padded_trns.extend(png_chunk(b"tRNS", &[0, 16, 0, 0]));
    gray16_padded_trns.extend_from_slice(&gray16[33..]);

    // 2. 16-bit RGB with 8-byte tRNS
    let mut rgb16 = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut rgb16, 2, 1);
        encoder.set_color(png::ColorType::Rgb);
        encoder.set_depth(png::BitDepth::Sixteen);
        encoder
            .write_header()
            .unwrap()
            .write_image_data(&[0, 1, 0, 2, 0, 3, 0, 40, 0, 50, 0, 60])
            .unwrap();
    }
    let mut rgb16_padded_trns = rgb16[..33].to_vec();
    rgb16_padded_trns.extend(png_chunk(b"tRNS", &[0, 1, 0, 2, 0, 3, 0, 0]));
    rgb16_padded_trns.extend_from_slice(&rgb16[33..]);

    // 3. 4-bit grayscale with out-of-range tRNS sample 0x0011 (17 > 15), matching 8-bit expanded sample 1 (0x11)
    let mut gray4 = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut gray4, 2, 1);
        encoder.set_color(png::ColorType::Grayscale);
        encoder.set_depth(png::BitDepth::Four);
        encoder
            .write_header()
            .unwrap()
            .write_image_data(&[0x12])
            .unwrap();
    }
    let mut gray4_out_of_range_trns = gray4[..33].to_vec();
    gray4_out_of_range_trns.extend(png_chunk(b"tRNS", &[0x00, 0x11]));
    gray4_out_of_range_trns.extend_from_slice(&gray4[33..]);

    // 4. 8-bit grayscale with out-of-range high byte in tRNS (0x0111 > 255)
    let mut gray8 = Vec::new();
    {
        let mut encoder = png::Encoder::new(&mut gray8, 2, 1);
        encoder.set_color(png::ColorType::Grayscale);
        encoder.set_depth(png::BitDepth::Eight);
        encoder
            .write_header()
            .unwrap()
            .write_image_data(&[0x11, 0x90])
            .unwrap();
    }
    let mut gray8_out_of_range_trns = gray8[..33].to_vec();
    gray8_out_of_range_trns.extend(png_chunk(b"tRNS", &[0x01, 0x11]));
    gray8_out_of_range_trns.extend_from_slice(&gray8[33..]);

    for (name, malformed) in [
        ("gray16-padded-trns", gray16_padded_trns),
        ("rgb16-padded-trns", rgb16_padded_trns),
        ("gray4-oob-trns", gray4_out_of_range_trns),
        ("gray8-oob-trns", gray8_out_of_range_trns),
    ] {
        let input = directory.path().join(format!("{name}.png"));
        let output = directory.path().join(format!("{name}-output.png"));
        fs::write(&input, &malformed).unwrap();
        fs::write(&output, b"existing output").unwrap();
        for strip_metadata in [true, false] {
            let mut operation = request(&input, &output);
            operation.options.strip_png_metadata = strip_metadata;
            let error = optimize_image(&operation, &CancellationToken::default()).unwrap_err();
            assert_eq!(error.code(), "image_optimization_failed");
            assert_eq!(fs::read(&input).unwrap(), malformed);
            assert_eq!(fs::read(&output).unwrap(), b"existing output");
        }
    }
}

#[test]
fn image_dimensions_and_input_byte_limits_reject_before_allocation() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("oversized.png");
    let output = directory.path().join("output.png");
    for (width, height) in [(32_769_u32, 1_u32), (8_000, 8_000)] {
        let mut ihdr = width.to_be_bytes().to_vec();
        ihdr.extend_from_slice(&height.to_be_bytes());
        ihdr.extend_from_slice(&[8, 6, 0, 0, 0]);
        let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec();
        bytes.extend(png_chunk(b"IHDR", &ihdr));
        bytes.extend(png_chunk(b"IEND", &[]));
        fs::write(&input, &bytes).unwrap();
        let error =
            optimize_image(&request(&input, &output), &CancellationToken::default()).unwrap_err();
        assert_eq!(error.code(), "invalid_input");
        assert!(!output.exists());
    }
    let file = fs::File::create(&input).unwrap();
    file.set_len(128 * 1024 * 1024 + 1).unwrap();
    drop(file);
    let error =
        optimize_image(&request(&input, &output), &CancellationToken::default()).unwrap_err();
    assert_eq!(error.code(), "invalid_input");
    assert!(!output.exists());
}

#[test]
fn source_and_protected_file_aliases_are_never_overwritten() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("input.png");
    let original = write_png(&input);
    let source_alias = directory.path().join("source-hardlink.png");
    fs::hard_link(&input, &source_alias).unwrap();
    for output in [&input, &source_alias] {
        let error =
            optimize_image(&request(&input, output), &CancellationToken::default()).unwrap_err();
        assert_eq!(error.code(), "invalid_input");
        assert_eq!(fs::read(&input).unwrap(), original);
    }

    let protected = directory.path().join("protected.png");
    fs::write(&protected, b"protected document image").unwrap();
    let protected_alias = directory.path().join("protected-hardlink.png");
    fs::hard_link(&protected, &protected_alias).unwrap();
    for output in [&protected, &protected_alias] {
        let mut operation = request(&input, output);
        operation.protected_paths.push(protected.clone());
        let error = optimize_image(&operation, &CancellationToken::default()).unwrap_err();
        assert_eq!(error.code(), "invalid_input");
        assert_eq!(fs::read(&protected).unwrap(), b"protected document image");
        assert_eq!(fs::read(&input).unwrap(), original);
    }

    let missing_sub = directory.path().join("missing-subdir");
    let dotdot_source = missing_sub.join("..").join("input.png");
    let dotdot_protected = missing_sub.join("..").join("protected.png");
    for output in [&dotdot_source, &dotdot_protected] {
        let mut operation = request(&input, output);
        operation.protected_paths.push(protected.clone());
        let error = optimize_image(&operation, &CancellationToken::default()).unwrap_err();
        assert_eq!(error.code(), "invalid_input");
        assert!(!missing_sub.exists());
        assert_eq!(fs::read(&protected).unwrap(), b"protected document image");
        assert_eq!(fs::read(&input).unwrap(), original);
    }
}

#[test]
#[cfg(unix)]
fn source_and_protected_symlink_aliases_are_never_overwritten() {
    use std::os::unix::fs::symlink;

    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("input.png");
    let original = write_png(&input);
    let source_alias = directory.path().join("source-symlink.png");
    symlink(&input, &source_alias).unwrap();
    let error = optimize_image(
        &request(&input, &source_alias),
        &CancellationToken::default(),
    )
    .unwrap_err();
    assert_eq!(error.code(), "invalid_input");
    assert!(fs::symlink_metadata(&source_alias)
        .unwrap()
        .file_type()
        .is_symlink());
    assert_eq!(fs::read(&input).unwrap(), original);

    let protected = directory.path().join("protected.png");
    fs::write(&protected, b"protected document image").unwrap();
    let protected_alias = directory.path().join("protected-symlink.png");
    symlink(&protected, &protected_alias).unwrap();
    let mut operation = request(&input, &protected_alias);
    operation.protected_paths.push(protected.clone());
    let error = optimize_image(&operation, &CancellationToken::default()).unwrap_err();
    assert_eq!(error.code(), "invalid_input");
    assert!(fs::symlink_metadata(&protected_alias)
        .unwrap()
        .file_type()
        .is_symlink());
    assert_eq!(fs::read(&protected).unwrap(), b"protected document image");
    assert_eq!(fs::read(&input).unwrap(), original);

    let dir_alias = directory.path().join("dir-alias");
    symlink(directory.path(), &dir_alias).unwrap();
    let reserved = directory.path().join("reserved.png");
    let reserved_via_alias = dir_alias.join("reserved.png");
    let mut operation = request(&input, &reserved_via_alias);
    operation.protected_paths.push(reserved.clone());
    let error = optimize_image(&operation, &CancellationToken::default()).unwrap_err();
    assert_eq!(error.code(), "invalid_input");
    assert!(!reserved.exists());
}

#[test]
fn cancellation_leaves_inputs_and_existing_or_missing_outputs_untouched() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("input.png");
    let original = write_png(&input);
    let existing = directory.path().join("existing.png");
    let missing = directory.path().join("missing.png");
    fs::write(&existing, b"existing output").unwrap();
    let token = CancellationToken::default();
    token.cancel();
    for output in [&existing, &missing] {
        let error = optimize_image(&request(&input, output), &token).unwrap_err();
        assert_eq!(error.code(), "cancelled");
        assert_eq!(fs::read(&input).unwrap(), original);
    }
    assert_eq!(fs::read(&existing).unwrap(), b"existing output");
    assert!(!missing.exists());
}

#[test]
fn cmyk_jpeg_rejection_does_not_change_existing_output() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("cmyk.jpg");
    let output = directory.path().join("output.jpg");
    let original = jpeg_fixture(turbojpeg::PixelFormat::CMYK);
    fs::write(&input, &original).unwrap();
    fs::write(&output, b"existing output").unwrap();
    let error =
        optimize_image(&request(&input, &output), &CancellationToken::default()).unwrap_err();
    assert_eq!(error.code(), "invalid_input");
    assert_eq!(fs::read(&input).unwrap(), original);
    assert_eq!(fs::read(&output).unwrap(), b"existing output");
}

fn adam7_fixture(input: &[u8]) -> Vec<u8> {
    let mut options = oxipng::Options::from_preset(0);
    options.interlace = Some(oxipng::Interlacing::Adam7);
    options.force = true;
    options.bit_depth_reduction = false;
    options.color_type_reduction = false;
    options.palette_reduction = false;
    options.grayscale_reduction = false;
    let interlaced = oxipng::optimize_from_memory(input, &options).unwrap();
    assert_eq!(interlaced[28], 1, "fixture must use Adam7");
    interlaced
}

#[test]
fn adam7_opacity_checks_cover_late_passes_and_preserve_sixteen_bit_samples() {
    let directory = tempfile::tempdir().unwrap();
    let width = 17;
    let height = 14;
    for depth in [8, 16] {
        for transparent in [false, true] {
            let mut samples = Vec::new();
            for y in 0..height {
                for x in 0..width {
                    for sample in [x * 1031, y * 1507, x * 883 + y * 379, u16::MAX] {
                        if depth == 16 {
                            samples.extend_from_slice(&sample.to_be_bytes());
                        } else {
                            samples.push((sample >> 8) as u8);
                        }
                    }
                }
            }
            if transparent {
                *samples.last_mut().unwrap() = 0;
            }
            let source = if depth == 16 {
                png16_fixture(width as u32, height as u32, &samples)
            } else {
                png_fixture(width as u32, height as u32, &samples)
            };
            let interlaced = adam7_fixture(&source);
            let input = directory.path().join("source.png");
            let output = directory.path().join("output.png");
            fs::write(&input, &interlaced).unwrap();
            fs::write(&output, b"previous").unwrap();
            let operation = request(&input, &output);
            let result = optimize_image(&operation, &CancellationToken::default());
            if transparent {
                assert!(matches!(result, Err(Error::InvalidInput(_))));
                assert_eq!(fs::read(&output).unwrap(), b"previous");
            } else {
                result.unwrap();
                assert_eq!(decode_png_samples(&fs::read(&output).unwrap()).1, samples);
            }
            assert_eq!(fs::read(&input).unwrap(), interlaced);
        }
    }
}

#[test]
fn transparent_adam7_checksums_fail_before_opacity_and_preserve_existing_output() {
    let directory = tempfile::tempdir().unwrap();
    let input = directory.path().join("source.png");
    let output = directory.path().join("output.png");
    let mut pixels = rgba_pixels(17, 14);
    // The final row is odd, so its last pixel belongs to Adam7's final pass.
    *pixels.last_mut().unwrap() = 0;
    let valid = adam7_fixture(&png_fixture(17, 14, &pixels));

    let mut bad_ancillary_crc = valid[..8].to_vec();
    let mut image_data = Vec::new();
    for (kind, contents) in png_chunks(&valid) {
        if kind == *b"IEND" {
            // Opacity was already observable while decoding image data; the
            // complete source must still be checked before reporting it.
            let mut ancillary = png_chunk(b"tEXt", b"Comment\0late source metadata");
            *ancillary.last_mut().unwrap() ^= 1;
            bad_ancillary_crc.extend(ancillary);
        }
        if kind == *b"IDAT" {
            image_data.extend_from_slice(contents);
        }
        bad_ancillary_crc.extend(png_chunk(&kind, contents));
    }
    // Corrupt the zlib checksum, then recompute the enclosing PNG chunk CRC.
    // Joining all IDAT chunks avoids assuming the encoder used just one.
    *image_data.last_mut().unwrap() ^= 1;
    let mut bad_adler = valid[..8].to_vec();
    let mut wrote_idat = false;
    for (kind, contents) in png_chunks(&valid) {
        if kind == *b"IDAT" {
            if !wrote_idat {
                bad_adler.extend(png_chunk(b"IDAT", &image_data));
                wrote_idat = true;
            }
        } else {
            bad_adler.extend(png_chunk(&kind, contents));
        }
    }
    assert!(wrote_idat);

    // Establish that each corruption is paired with an otherwise valid,
    // transparent Adam7 image rather than an independently malformed fixture.
    fs::write(&input, &valid).unwrap();
    fs::write(&output, b"existing output").unwrap();
    let error =
        optimize_image(&request(&input, &output), &CancellationToken::default()).unwrap_err();
    assert!(matches!(error, Error::InvalidInput(_)));
    assert_eq!(fs::read(&output).unwrap(), b"existing output");

    for damaged in [bad_ancillary_crc, bad_adler] {
        fs::write(&input, &damaged).unwrap();
        for strip_metadata in [true, false] {
            fs::write(&output, b"existing output").unwrap();
            let mut operation = request(&input, &output);
            operation.options.strip_png_metadata = strip_metadata;
            let error = optimize_image(&operation, &CancellationToken::default()).unwrap_err();
            assert!(matches!(error, Error::ImageOptimization(_)));
            assert_eq!(fs::read(&input).unwrap(), damaged);
            assert_eq!(fs::read(&output).unwrap(), b"existing output");
            assert_eq!(fs::read_dir(directory.path()).unwrap().count(), 2);
        }
    }
}
