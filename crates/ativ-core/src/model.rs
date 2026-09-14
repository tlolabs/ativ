use avid_core::{Codec, Composition, Encoding, Input, RenderSettings};
use std::path::PathBuf;

#[derive(Clone, Debug)]
pub struct RenderRequest {
    pub image: PathBuf,
    pub audio: PathBuf,
    pub output: PathBuf,
    pub width: u32,
    pub height: u32,
    pub audio_bitrate: String,
    pub fps: u32,
    pub flip_horizontal: bool,
    pub flip_vertical: bool,
}

impl RenderRequest {
    /// Preserve standalone audio semantics and the ATIV software encoding policy.
    pub fn shared(&self) -> avid_core::RenderRequest {
        avid_core::RenderRequest {
            input: Input::Single {
                image: self.image.clone(),
                audio: self.audio.clone(),
            },
            output: self.output.clone(),
            settings: RenderSettings {
                width: self.width,
                height: self.height,
                fps: self.fps,
                audio_bitrate: self.audio_bitrate.clone(),
                flip_horizontal: self.flip_horizontal,
                flip_vertical: self.flip_vertical,
                codec: Codec::H264,
                encoding: Encoding::Software,
                composition: Composition::Fitted,
            },
            protected_paths: vec![],
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn standalone_policy_preserves_all_inputs_and_legacy_settings() {
        for bitrate in ["224k", "128000", "00128k", "1m", "128000b"] {
            for fps in [1, 30, 240] {
                let request = RenderRequest {
                    image: "cover ü.png".into(),
                    audio: "audio track.wav".into(),
                    output: "output.custom".into(),
                    width: 320,
                    height: 180,
                    audio_bitrate: bitrate.into(),
                    fps,
                    flip_horizontal: true,
                    flip_vertical: true,
                };
                let shared = request.shared();
                assert_eq!(
                    shared.input,
                    Input::Single {
                        image: request.image,
                        audio: request.audio
                    }
                );
                assert_eq!(shared.output, request.output);
                assert!(shared.protected_paths.is_empty());
                assert_eq!(
                    shared.settings,
                    RenderSettings {
                        width: 320,
                        height: 180,
                        fps,
                        audio_bitrate: bitrate.into(),
                        flip_horizontal: true,
                        flip_vertical: true,
                        codec: Codec::H264,
                        encoding: Encoding::Software,
                        composition: Composition::Fitted,
                    }
                );
                shared.settings.validate().unwrap();
            }
        }
    }
}
