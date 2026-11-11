use avid_core::{
    optimize_image, CancellationToken, ImageOptimizationOptions, ImageOptimizationRequest,
};
use std::fs;
use turbojpeg::{Compressor, Image, PixelFormat, Subsamp};

fn jpeg(width: usize, height: usize, grayscale: bool, efficient: bool) -> Vec<u8> {
    let channels = if grayscale { 1 } else { 3 };
    let pixels: Vec<_> = (0..width * height * channels)
        .map(|i| if efficient { 128 } else { (i * 71 % 256) as u8 })
        .collect();
    let mut encoder = Compressor::new().unwrap();
    encoder.set_quality(80).unwrap();
    encoder
        .set_subsamp(if grayscale {
            Subsamp::Gray
        } else {
            Subsamp::None
        })
        .unwrap();
    encoder.set_optimize(efficient).unwrap();
    encoder
        .compress_to_vec(Image {
            pixels: &pixels[..],
            width,
            height,
            pitch: width * channels,
            format: if grayscale {
                PixelFormat::GRAY
            } else {
                PixelFormat::RGB
            },
        })
        .unwrap()
}

#[test]
fn stripping_removes_private_trailers_even_when_original_scan_wins() {
    let root = tempfile::tempdir().unwrap();
    let input = root.path().join("source.jpg");
    let output = root.path().join("stripped.jpg");
    let trailer = b"\xff\xe1\0\x13Exif\0\0private-GPS";
    for grayscale in [false, true] {
        let original = jpeg(8, 8, grayscale, true);
        let mut with_trailer = original.clone();
        with_trailer.extend_from_slice(trailer);
        fs::write(&input, &with_trailer).unwrap();
        for lossy in [false, true] {
            let mut request = ImageOptimizationRequest {
                input: input.clone(),
                output: output.clone(),
                options: ImageOptimizationOptions {
                    lossy,
                    ..Default::default()
                },
                protected_paths: vec![],
            };
            optimize_image(&request, &CancellationToken::default()).unwrap();
            // This efficient fixture uses the original scan as its size fallback.
            // Assert exact bytes, so the marker-looking trailer cannot survive.
            assert_eq!(fs::read(&output).unwrap(), original);
            assert_eq!(fs::read(&input).unwrap(), with_trailer);
            request.options.strip_jpeg_metadata = false;
            optimize_image(&request, &CancellationToken::default()).unwrap();
            assert_eq!(fs::read(&output).unwrap(), with_trailer);
        }
    }
}

#[test]
fn stripping_a_concatenated_jpeg_publishes_only_the_first_image() {
    let root = tempfile::tempdir().unwrap();
    let input = root.path().join("source.jpg");
    let output = root.path().join("stripped.jpg");
    let first = jpeg(8, 8, false, true);
    let mut concatenated = first.clone();
    concatenated.extend_from_slice(&jpeg(16, 16, false, false));
    fs::write(&input, &concatenated).unwrap();
    optimize_image(
        &ImageOptimizationRequest {
            input,
            output: output.clone(),
            options: ImageOptimizationOptions::default(),
            protected_paths: vec![],
        },
        &CancellationToken::default(),
    )
    .unwrap();
    assert_eq!(fs::read(output).unwrap(), first);
}

#[test]
fn stripping_removes_jfif_thumbnails_and_extra_adobe_payloads() {
    let root = tempfile::tempdir().unwrap();
    let input = root.path().join("source.jpg");
    let output = root.path().join("stripped.jpg");
    let original = jpeg(8, 8, false, true);
    let thumbnail = b"private GPS thumbnail bytes"; // 3 x 3 RGB pixels
    let private_adobe = b"private Adobe trailer";
    assert_eq!(thumbnail.len(), 3 * 3 * 3);
    for add_thumbnail in [false, true] {
        let mut decorated = original.clone();
        if add_thumbnail {
            let length = usize::from(u16::from_be_bytes([decorated[4], decorated[5]]));
            let end = 4 + length;
            decorated[end - 2..end].copy_from_slice(&[3, 3]);
            decorated[4..6].copy_from_slice(&((length + thumbnail.len()) as u16).to_be_bytes());
            decorated.splice(end..end, thumbnail.iter().copied());
        }
        let mut adobe = b"Adobe\0\x64\0\0\0\0\x01".to_vec();
        adobe.extend_from_slice(private_adobe);
        let mut segment = b"\xff\xee".to_vec();
        segment.extend_from_slice(&((adobe.len() + 2) as u16).to_be_bytes());
        segment.extend_from_slice(&adobe);
        decorated.splice(2..2, segment);
        fs::write(&input, &decorated).unwrap();
        let mut request = ImageOptimizationRequest {
            input: input.clone(),
            output: output.clone(),
            options: ImageOptimizationOptions::default(),
            protected_paths: vec![],
        };
        optimize_image(&request, &CancellationToken::default()).unwrap();
        let stripped = fs::read(&output).unwrap();
        assert!(!stripped.windows(thumbnail.len()).any(|w| w == thumbnail));
        assert!(!stripped
            .windows(private_adobe.len())
            .any(|w| w == private_adobe));
        assert_eq!(
            turbojpeg::decompress(&stripped, PixelFormat::RGB)
                .unwrap()
                .pixels,
            turbojpeg::decompress(&decorated, PixelFormat::RGB)
                .unwrap()
                .pixels
        );
        request.options.strip_jpeg_metadata = false;
        optimize_image(&request, &CancellationToken::default()).unwrap();
        assert_eq!(fs::read(&output).unwrap(), decorated);
    }
}

#[test]
fn preserving_exif_only_input_does_not_add_a_jfif_marker() {
    let root = tempfile::tempdir().unwrap();
    let input = root.path().join("source.jpg");
    let output = root.path().join("preserved.jpg");
    let mut original = jpeg(96, 64, false, false);
    assert_eq!(&original[2..4], b"\xff\xe0");
    let end = 4 + usize::from(u16::from_be_bytes([original[4], original[5]]));
    original.drain(2..end);
    let exif = b"\xff\xe1\0\x0dExif\0\0audit";
    original.splice(2..2, exif.iter().copied());
    fs::write(&input, &original).unwrap();
    for lossy in [false, true] {
        optimize_image(
            &ImageOptimizationRequest {
                input: input.clone(),
                output: output.clone(),
                options: ImageOptimizationOptions {
                    strip_jpeg_metadata: false,
                    lossy,
                    jpeg_quality: 60,
                    ..Default::default()
                },
                protected_paths: vec![],
            },
            &CancellationToken::default(),
        )
        .unwrap();
        let preserved = fs::read(&output).unwrap();
        assert!(preserved.len() < original.len());
        assert_eq!(&preserved[2..2 + exif.len()], exif);
        assert!(!preserved.windows(5).any(|bytes| bytes == b"JFIF\0"));
        let decoded = turbojpeg::decompress(&preserved, PixelFormat::RGB).unwrap();
        assert_eq!((decoded.width, decoded.height), (96, 64));
        if !lossy {
            assert_eq!(
                decoded.pixels,
                turbojpeg::decompress(&original, PixelFormat::RGB)
                    .unwrap()
                    .pixels
            );
        }
        let stripped_output = root.path().join("stripped.jpg");
        let result = optimize_image(
            &ImageOptimizationRequest {
                input: input.clone(),
                output: stripped_output.clone(),
                options: ImageOptimizationOptions {
                    strip_jpeg_metadata: true,
                    lossy,
                    jpeg_quality: 60,
                    ..Default::default()
                },
                protected_paths: vec![],
            },
            &CancellationToken::default(),
        )
        .unwrap();
        let stripped = fs::read(&stripped_output).unwrap();
        assert!(result.optimized);
        assert!(stripped.len() < preserved.len());
        assert!(!stripped.windows(5).any(|bytes| bytes == b"Exif\0"));
        assert!(!stripped.windows(5).any(|bytes| bytes == b"JFIF\0"));
        if !lossy {
            assert_eq!(
                turbojpeg::decompress(&stripped, PixelFormat::RGB)
                    .unwrap()
                    .pixels,
                decoded.pixels
            );
        }
    }
}
