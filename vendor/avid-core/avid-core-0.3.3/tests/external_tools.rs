//! The production integration contract needs only caller-supplied executable paths.
use avid_core::{CancellationToken, Error, MediaTools};

#[test]
fn missing_explicit_paths_fail_without_discovery() {
    let root = tempfile::tempdir().unwrap();
    let error = MediaTools::from_paths(
        root.path().join("missing-encoder"),
        root.path().join("missing-probe"),
        &CancellationToken::default(),
    )
    .unwrap_err();
    assert!(matches!(
        error,
        Error::ToolUnavailable { tool: "ffmpeg", .. }
    ));
}

#[test]
fn cancellation_precedes_file_access() {
    let token = CancellationToken::default();
    token.cancel();
    assert!(matches!(
        MediaTools::from_paths("missing", "missing", &token),
        Err(Error::Cancelled)
    ));
}

#[cfg(unix)]
mod unix {
    use super::*;
    use avid_core::{Input, PreviewRequest, RenderRequest, RenderSettings, Renderer};
    use std::{fs, os::unix::fs::symlink, path::Path, time::Duration};

    fn fixture(destination: &Path, name: &str) {
        symlink(
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("tests/fixtures/lifecycle")
                .join(name),
            destination,
        )
        .unwrap();
    }

    #[test]
    fn external_split_paths_probe_capabilities_preview_and_render_without_manifests() {
        let root = tempfile::Builder::new()
            .prefix("host media ü ")
            .tempdir()
            .unwrap();
        let encoder_dir = root.path().join("application tools");
        let probe_dir = root.path().join("another location");
        fs::create_dir(&encoder_dir).unwrap();
        fs::create_dir(&probe_dir).unwrap();
        let ffmpeg = encoder_dir.join("custom encoder");
        let ffprobe = probe_dir.join("custom probe");
        fixture(&ffmpeg, "ffmpeg.sh");
        fixture(&ffprobe, "ffprobe.sh");
        fs::write(encoder_dir.join("fixture-mode"), "ok").unwrap();
        let token = CancellationToken::default();
        let tools = MediaTools::from_paths(&ffmpeg, &ffprobe, &token).unwrap();
        assert_eq!(tools.ffmpeg(), ffmpeg);
        assert_eq!(tools.ffprobe(), ffprobe);
        assert_eq!(tools.ffmpeg_version(), "ffmpeg version test");
        assert_eq!(tools.ffprobe_version(), "ffprobe version test");
        let renderer = Renderer::new(tools);
        let image = root.path().join("art ü.png");
        let audio = root.path().join("track.wav");
        fs::write(&image, b"artwork").unwrap();
        fs::write(&audio, b"audio").unwrap();
        assert_eq!(renderer.inspect_image(&image, &token).unwrap(), (64, 48));
        assert_eq!(
            renderer.probe_audio_duration(&audio, &token).unwrap(),
            Some(2.0)
        );
        assert!(!renderer.capabilities(&token).unwrap().encoders.is_empty());
        let settings = RenderSettings::default();
        let preview = root.path().join("preview.png");
        renderer
            .preview(
                &PreviewRequest {
                    image: image.clone(),
                    output: preview.clone(),
                    settings: settings.clone(),
                    protected_paths: vec![],
                },
                &token,
                &(),
            )
            .unwrap();
        assert_eq!(fs::read(preview).unwrap(), b"completed");
        let output = root.path().join("video.mp4");
        renderer
            .render(
                &RenderRequest {
                    input: Input::Single { image, audio },
                    output: output.clone(),
                    settings,
                    protected_paths: vec![],
                },
                &token,
                &(),
            )
            .unwrap();
        assert_eq!(fs::read(output).unwrap(), b"completed");
        // Old packaging metadata has no influence on the library contract.
        fs::write(encoder_dir.join("spec.json"), "invalid historical manifest").unwrap();
        fs::write(probe_dir.join("build.json"), "{}").unwrap();
        MediaTools::from_paths(&ffmpeg, &ffprobe, &token).unwrap();
        fs::remove_file(&ffprobe).unwrap();
        assert!(matches!(
            MediaTools::from_paths(&ffmpeg, &ffprobe, &token),
            Err(Error::ToolUnavailable {
                tool: "ffprobe",
                ..
            })
        ));
    }

    #[test]
    fn versions_are_reported_without_a_core_release_pin_but_must_match() {
        let root = tempfile::tempdir().unwrap();
        let ffmpeg_dir = root.path().join("encoder");
        let ffprobe_dir = root.path().join("probe");
        fs::create_dir(&ffmpeg_dir).unwrap();
        fs::create_dir(&ffprobe_dir).unwrap();
        let ffmpeg = ffmpeg_dir.join("tool");
        let ffprobe = ffprobe_dir.join("tool");
        fixture(&ffmpeg, "identity.sh");
        fixture(&ffprobe, "identity.sh");
        let token = CancellationToken::default();
        for version in ["6.1.2", "7.1.1-vendor", "N-custom-build"] {
            fs::write(
                ffmpeg_dir.join("identity"),
                format!("ffmpeg version {version}\n"),
            )
            .unwrap();
            fs::write(
                ffprobe_dir.join("identity"),
                format!("ffprobe version {version}\n"),
            )
            .unwrap();
            let tools = MediaTools::from_paths(&ffmpeg, &ffprobe, &token).unwrap();
            assert_eq!(tools.ffmpeg_version(), format!("ffmpeg version {version}"));
        }
        for invalid in [
            "ffprobe version other",
            "another program",
            "ffprobe version",
            "ffprobe versions N-custom-build",
        ] {
            fs::write(ffprobe_dir.join("identity"), invalid).unwrap();
            assert!(matches!(
                MediaTools::from_paths(&ffmpeg, &ffprobe, &token),
                Err(Error::ToolUnavailable { .. })
            ));
        }
    }

    #[test]
    fn external_validation_obeys_the_host_timeout() {
        let root = tempfile::tempdir().unwrap();
        let ffmpeg = root.path().join("slow-encoder");
        let ffprobe = root.path().join("probe");
        fixture(&ffmpeg, "slow.sh");
        fixture(&ffprobe, "ffprobe.sh");
        assert!(matches!(
            MediaTools::from_paths_with_timeout(
                &ffmpeg,
                &ffprobe,
                Duration::from_millis(50),
                &CancellationToken::default()
            ),
            Err(Error::Timeout(_))
        ));
    }
}
