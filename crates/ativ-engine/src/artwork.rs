//! Host playback policy only. Core remains responsible for artwork validation,
//! dimension inspection and composition. Unknown/multi-image containers retain
//! PerFrame so an accepted animation is never silently frozen by the default.
use ativ_core::{CancellationToken, RenderMode};
#[cfg(unix)]
use std::os::unix::fs::OpenOptionsExt;
use std::{
    fs::File,
    io::{BufRead, BufReader, Read, Seek, SeekFrom},
    path::Path,
};

pub fn default_mode(path: &Path, token: &CancellationToken) -> RenderMode {
    if static_container(path, token).unwrap_or(false) {
        RenderMode::Simple
    } else {
        RenderMode::PerFrame
    }
}

fn static_container(path: &Path, token: &CancellationToken) -> std::io::Result<bool> {
    if token.is_cancelled() {
        return Ok(false);
    }
    let mut options = File::options();
    options.read(true);
    // A path can name a FIFO. Its open must return before we can check its type.
    #[cfg(unix)]
    options.custom_flags(libc::O_NONBLOCK);
    let mut file = options.open(path)?;
    let metadata = file.metadata()?;
    if !metadata.is_file() {
        return Ok(false);
    }
    let mut header = [0; 8];
    file.read_exact(&mut header)?;
    let length = metadata.len();
    if header.starts_with(&[0xff, 0xd8, 0xff]) {
        return static_jpeg(&mut file, length, token);
    }
    if header.starts_with(b"BM") {
        return Ok(u64::from(u32::from_le_bytes(header[2..6].try_into().unwrap())) == length);
    }
    // PNM, WebP, GIF, TIFF and unknown containers may carry multiple images.
    if &header != b"\x89PNG\r\n\x1a\n" {
        return Ok(false);
    }
    // APNG's animation control precedes its first IDAT. Do not decode pixels or
    // trust a suffix; bounded, allocation-free chunk walking handles renamed PNGs.
    for _ in 0..1024 {
        if token.is_cancelled() {
            return Ok(false);
        }
        file.read_exact(&mut header)?;
        let size = u64::from(u32::from_be_bytes(header[..4].try_into().unwrap()));
        let end = file
            .stream_position()?
            .checked_add(size)
            .and_then(|v| v.checked_add(4));
        if end.is_none_or(|end| end > length) {
            return Ok(false);
        }
        match &header[4..] {
            b"acTL" => return Ok(false),
            b"IEND" => return Ok(size == 0 && end == Some(length)),
            _ => {
                file.seek(SeekFrom::Start(end.unwrap()))?;
            }
        }
    }
    Ok(false)
}

fn static_jpeg(file: &mut File, length: u64, token: &CancellationToken) -> std::io::Result<bool> {
    if length > 64 * 1024 * 1024 {
        return Ok(false);
    }
    file.seek(SeekFrom::Start(2))?;
    let mut reader = BufReader::new(file);
    let mut position = 2;
    let mut in_scan = false;
    let mut frame_seen = false;
    let mut scan_seen = false;
    // Segment payloads can contain JPEG thumbnails and arbitrary marker bytes.
    // Walk their lengths; only entropy data uses byte stuffing/restart markers.
    for _ in 0..4096 {
        let Some(marker) = jpeg_marker(&mut reader, &mut position, length, in_scan, token)? else {
            return Ok(false);
        };
        match marker {
            0xd9 => return Ok(frame_seen && scan_seen && position == length),
            // Another image or hierarchical frame may carry different pixels.
            0xd8 | 0xd0..=0xd7 | 0xde | 0xdf => return Ok(false),
            0x01 => continue, // TEM is a standalone arithmetic-coding marker.
            0xc0..=0xc3 | 0xc5..=0xc7 | 0xc9..=0xcb | 0xcd..=0xcf => {
                if frame_seen {
                    return Ok(false);
                }
                frame_seen = true;
            }
            0xda => {
                if !frame_seen {
                    return Ok(false);
                }
                scan_seen = true;
            }
            0xc4 | 0xcc | 0xdb..=0xdd | 0xe0..=0xef | 0xfe => {}
            _ => return Ok(false),
        }
        if position + 2 > length {
            return Ok(false);
        }
        let mut bytes = [0; 2];
        reader.read_exact(&mut bytes)?;
        let size = u16::from_be_bytes(bytes);
        if size < 2 {
            return Ok(false);
        }
        let end = position + u64::from(size);
        if end > length {
            return Ok(false);
        }
        reader.seek_relative(i64::from(size - 2))?;
        position = end;
        // Progressive JPEGs can put tables between scans. DNL alone can appear
        // within a scan, after which its entropy data continues.
        in_scan = marker == 0xda || (in_scan && marker == 0xdc);
    }
    Ok(false)
}

fn jpeg_marker(
    reader: &mut impl BufRead,
    position: &mut u64,
    length: u64,
    in_scan: bool,
    token: &CancellationToken,
) -> std::io::Result<Option<u8>> {
    loop {
        if token.is_cancelled() || *position >= length {
            return Ok(None);
        }
        if in_scan {
            // Inspect one buffered chunk at a time so both work and cancellation
            // latency stay bounded without a read syscall for every pixel byte.
            loop {
                if token.is_cancelled() || *position >= length {
                    return Ok(None);
                }
                let buffer = reader.fill_buf()?;
                let buffer = &buffer[..buffer.len().min((length - *position) as usize)];
                if buffer.is_empty() {
                    return Ok(None);
                }
                let marker = memchr::memchr(0xff, buffer);
                let consumed = marker.map_or(buffer.len(), |index| index + 1);
                reader.consume(consumed);
                *position += consumed as u64;
                if marker.is_some() {
                    break;
                }
            }
        } else {
            let mut byte = [0];
            reader.read_exact(&mut byte)?;
            *position += 1;
            if byte[0] != 0xff {
                return Ok(None);
            }
        }
        let marker = loop {
            if token.is_cancelled() || *position >= length {
                return Ok(None);
            }
            let mut byte = [0];
            reader.read_exact(&mut byte)?;
            *position += 1;
            if byte[0] != 0xff {
                break byte[0];
            }
        };
        match marker {
            0x00 | 0xd0..=0xd7 if in_scan => continue,
            0x00 => return Ok(None),
            _ => return Ok(Some(marker)),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn segment(marker: u8, payload: &[u8]) -> Vec<u8> {
        let mut bytes = vec![0xff, marker];
        bytes.extend_from_slice(&u16::try_from(payload.len() + 2).unwrap().to_be_bytes());
        bytes.extend_from_slice(payload);
        bytes
    }

    fn jpeg(frame_marker: u8, metadata: &[u8], entropy: &[u8]) -> Vec<u8> {
        let mut bytes = vec![0xff, 0xd8];
        bytes.extend_from_slice(metadata);
        bytes.extend(segment(frame_marker, &[8, 0, 1, 0, 1, 1, 1, 0x11, 0]));
        bytes.extend(segment(0xda, &[1, 1, 0, 0, 63, 0]));
        bytes.extend_from_slice(entropy);
        bytes.extend_from_slice(&[0xff, 0xd9]);
        bytes
    }

    #[test]
    fn jpeg_policy_skips_thumbnail_markers_and_preserves_multiscan_images() {
        let root = std::env::temp_dir().join(format!("ativ-jpeg-policy-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let path = root.join("artwork.jpeg");
        let thumbnail = jpeg(0xc0, &[], &[1, 2, 3]);
        let mut exif = b"Exif\0\0".to_vec();
        exif.extend_from_slice(&thumbnail);
        let metadata = [segment(0xe1, &exif), segment(0xfe, &thumbnail)].concat();
        let baseline = jpeg(0xc0, &metadata, &[1, 0xff, 0x00, 0xd9, 0xff, 0xd0, 2]);
        let mut progressive = jpeg(0xc2, &metadata, &[1, 2]);
        progressive.truncate(progressive.len() - 2);
        progressive.extend(segment(0xc4, &[0xff, 0xd9]));
        progressive.extend(segment(0xda, &[1, 1, 0, 1, 63, 0]));
        progressive.extend_from_slice(&[3, 0xff, 0xd7, 4, 0xff, 0xff, 0xd9]);
        // Exercise a marker prefix straddling the buffered reader's boundary.
        let boundary = jpeg(0xc0, &[], &vec![1; 8192 - 1 - (13 + 10)]);
        for bytes in [&baseline, &progressive, &boundary] {
            std::fs::write(&path, bytes).unwrap();
            assert_eq!(
                default_mode(&path, &CancellationToken::default()),
                RenderMode::Simple
            );
        }

        let mut second_frame = baseline.clone();
        second_frame.truncate(second_frame.len() - 2);
        second_frame.extend_from_slice(&thumbnail[2..]);
        let mut no_scan = vec![0xff, 0xd8];
        no_scan.extend(segment(0xc0, &[8, 0, 1, 0, 1, 1, 1, 0x11, 0]));
        no_scan.extend_from_slice(&[0xff, 0xd9]);
        let mut unknown_marker = baseline.clone();
        unknown_marker.splice(2..2, segment(0xf0, &[1, 2]));
        let mut many_segments = vec![0xff, 0xd8];
        for _ in 0..4096 {
            many_segments.extend(segment(0xe1, &[]));
        }
        many_segments.extend_from_slice(&baseline[2..]);
        for bytes in [
            [baseline.clone(), thumbnail].concat(),
            [baseline.clone(), vec![0]].concat(),
            second_frame,
            no_scan,
            unknown_marker,
            many_segments,
            jpeg(0xc0, &[], &[1, 0xff, 0xd8, 2]),
            vec![0xff, 0xd8, 0xff, 0xe1, 0, 1, 0xff, 0xd9],
            vec![0xff, 0xd8, 0xff, 0xe1, 0xff, 0xff, 0xff, 0xd9],
            baseline[..baseline.len() - 1].to_vec(),
        ] {
            std::fs::write(&path, bytes).unwrap();
            assert_eq!(
                default_mode(&path, &CancellationToken::default()),
                RenderMode::PerFrame
            );
        }
        std::fs::write(&path, &baseline).unwrap();
        let token = CancellationToken::default();
        token.cancel();
        assert_eq!(default_mode(&path, &token), RenderMode::PerFrame);
        File::options()
            .write(true)
            .open(&path)
            .unwrap()
            .set_len(64 * 1024 * 1024 + 1)
            .unwrap();
        assert_eq!(
            default_mode(&path, &CancellationToken::default()),
            RenderMode::PerFrame
        );
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn container_policy_preserves_animation_and_does_not_trust_suffixes() {
        let root = std::env::temp_dir().join(format!("ativ-artwork-policy-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let path = root.join("renamed.jpg");
        let png = |animated| {
            let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec();
            if animated {
                bytes.extend_from_slice(b"\0\0\0\0acTL\0\0\0\0");
            }
            bytes.extend_from_slice(b"\0\0\0\0IDAT\0\0\0\0");
            bytes.extend_from_slice(b"\0\0\0\0IEND\0\0\0\0");
            bytes
        };
        for (bytes, expected) in [
            (b"P6\n2 2\n255\n".to_vec(), RenderMode::PerFrame),
            (b"GIF89a1234".to_vec(), RenderMode::PerFrame),
            (b"RIFFxxxxWEBP".to_vec(), RenderMode::PerFrame),
            (png(false), RenderMode::Simple),
            (png(true), RenderMode::PerFrame),
            ([png(false), png(false)].concat(), RenderMode::PerFrame),
            (jpeg(0xc0, &[], &[1, 2, 3]), RenderMode::Simple),
            (b"\xff\xd8\xff12345\xff\xd9".to_vec(), RenderMode::PerFrame),
            (
                b"\xff\xd8\xff12345\xff\xd9trailing".to_vec(),
                RenderMode::PerFrame,
            ),
            (b"BM\x0a\0\0\0xxxx".to_vec(), RenderMode::Simple),
            (b"BM\x0a\0\0\0xxxxxxxx".to_vec(), RenderMode::PerFrame),
            (
                b"\x89PNG\r\n\x1a\n\xff\xff\xff\xffIDAT".to_vec(),
                RenderMode::PerFrame,
            ),
        ] {
            std::fs::write(&path, bytes).unwrap();
            assert_eq!(default_mode(&path, &CancellationToken::default()), expected);
        }
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn cancelled_classification_skips_opening_the_input() {
        let root =
            std::env::temp_dir().join(format!("ativ-cancelled-artwork-{}", std::process::id()));
        std::fs::create_dir(&root).unwrap();
        let token = CancellationToken::default();
        token.cancel();
        assert!(!static_container(&root.join("absent.png"), &token).unwrap());
        std::fs::remove_dir(root).unwrap();
    }
}
