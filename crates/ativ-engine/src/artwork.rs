//! Host playback policy only. Core remains responsible for artwork validation,
//! dimension inspection and composition. Unknown/multi-image containers retain
//! PerFrame so an accepted animation is never silently frozen by the default.
use ativ_core::{CancellationToken, RenderMode};
use std::{
    fs::File,
    io::{Read, Seek, SeekFrom},
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
    let mut file = File::open(path)?;
    let mut header = [0; 8];
    file.read_exact(&mut header)?;
    let length = file.metadata()?.len();
    if header.starts_with(&[0xff, 0xd8, 0xff]) {
        // Concatenated JPEG streams can animate too. A first end marker before
        // EOF (including a thumbnail marker) conservatively retains PerFrame.
        file.seek(SeekFrom::Start(2))?;
        let mut previous = 0;
        let mut position = 2u64;
        let mut buffer = [0; 8192];
        while position < length && position < 64 * 1024 * 1024 {
            if token.is_cancelled() {
                return Ok(false);
            }
            let read = file.read(&mut buffer)?;
            if read == 0 {
                return Ok(false);
            }
            for &byte in &buffer[..read] {
                position += 1;
                if previous == 0xff && byte == 0xd9 {
                    return Ok(position == length);
                }
                previous = byte;
            }
        }
        return Ok(false);
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

#[cfg(test)]
mod tests {
    use super::*;
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
            (b"\xff\xd8\xff12345\xff\xd9".to_vec(), RenderMode::Simple),
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
}
