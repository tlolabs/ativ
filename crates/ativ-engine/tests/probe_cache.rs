//! Process doubles verify that ATIV retains Core caches, not media appearance.
#![cfg(unix)]
use ativ_core::{CancellationToken, MediaTools, Renderer};
use std::{fs, os::unix::fs::PermissionsExt, path::Path, process::Command};

fn quote(path: &Path) -> String {
    format!("'{}'", path.to_string_lossy().replace('\'', "'\"'\"'"))
}

#[test]
fn shared_renderer_caches_probes_and_invalidates_changed_artwork() {
    let root = std::env::temp_dir().join(format!("ativ-cache ü {}", std::process::id()));
    fs::create_dir_all(&root).unwrap();
    let image = root.join("image ü.png");
    let probes = root.join("probes");
    let caps = root.join("capabilities");
    let ffmpeg = root.join("ffmpeg");
    let ffprobe = root.join("ffprobe");
    fs::write(&image, b"a").unwrap();
    fs::write(&ffmpeg, format!("#!/bin/sh\nif [ \"$1\" = -version ]; then echo 'ffmpeg version cache-test'; exit; fi\nprintf x >> {}\necho ' V..... libx264 software'\n", quote(&caps))).unwrap();
    fs::write(&ffprobe, format!("#!/bin/sh\nif [ \"$1\" = -version ]; then echo 'ffprobe version cache-test'; exit; fi\nprintf x >> {}\nif [ \"$(wc -c < {})\" -eq 1 ]; then echo 4x2; else echo 8x6; fi\n", quote(&probes), quote(&image))).unwrap();
    for tool in [&ffmpeg, &ffprobe] {
        fs::set_permissions(tool, fs::Permissions::from_mode(0o700)).unwrap();
    }
    let token = CancellationToken::default();
    let renderer = Renderer::new(MediaTools::from_paths(&ffmpeg, &ffprobe, &token).unwrap());
    assert_eq!(renderer.inspect_image(&image, &token).unwrap(), (4, 2));
    assert_eq!(
        renderer.clone().inspect_image(&image, &token).unwrap(),
        (4, 2)
    );
    assert_eq!(fs::read(&probes).unwrap(), b"x");
    fs::write(&image, b"changed").unwrap();
    assert_eq!(renderer.inspect_image(&image, &token).unwrap(), (8, 6));
    assert_eq!(fs::read(&probes).unwrap(), b"xx");
    renderer.capabilities(&token).unwrap();
    Renderer::new(renderer.tools().clone())
        .capabilities(&token)
        .unwrap();
    assert_eq!(fs::read(&caps).unwrap(), b"x");
    let output = Command::new(env!("CARGO_BIN_EXE_ativ-engine"))
        .arg("inspect-image")
        .arg("--image")
        .arg(&image)
        .arg("--image")
        .arg(&image)
        .arg("--ffmpeg")
        .arg(&ffmpeg)
        .arg("--ffprobe")
        .arg(&ffprobe)
        .env("ATIV_LOG_PATH", root.join("log"))
        .output()
        .unwrap();
    assert!(output.status.success(), "{:?}", output);
    assert_eq!(String::from_utf8(output.stdout).unwrap().lines().count(), 2);
    assert_eq!(fs::read(&probes).unwrap(), b"xxx");
    fs::remove_dir_all(root).unwrap();
}
