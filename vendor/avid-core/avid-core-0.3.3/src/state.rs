use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
fn default_video_schema() -> u64 {
    1
}
fn default_video_platform() -> String {
    "Instagram".into()
}
fn default_video_aspect() -> String {
    "Horizontal video (16:9)".into()
}
fn default_video_width() -> u32 {
    1920
}
fn default_video_height() -> u32 {
    1080
}
fn default_video_codec() -> String {
    "h264".into()
}
fn default_video_encoding() -> String {
    "software".into()
}
fn default_video_bitrate() -> String {
    "128k".into()
}
fn default_video_fps() -> u32 {
    30
}
fn default_preview_quality() -> String {
    "automatic".into()
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct VideoSettings {
    #[serde(default = "default_video_platform")]
    pub platform: String,
    #[serde(default = "default_video_aspect")]
    pub aspect: String,
    #[serde(default = "default_video_width")]
    pub width: u32,
    #[serde(default = "default_video_height")]
    pub height: u32,
    #[serde(default = "default_video_codec")]
    pub codec: String,
    #[serde(default = "default_video_encoding")]
    pub encoding: String,
    #[serde(default = "default_video_bitrate")]
    pub audio_bitrate: String,
    #[serde(default = "default_video_fps")]
    pub fps: u32,
    #[serde(default)]
    pub flip_horizontal: bool,
    #[serde(default)]
    pub flip_vertical: bool,
    #[serde(default = "default_preview_quality")]
    pub preview_quality: String,
    #[serde(default)]
    pub selected_chapter_ids: Vec<String>,
    #[serde(default)]
    pub selection_initialized: bool,
    #[serde(flatten)]
    pub extensions: BTreeMap<String, Value>,
}

impl Default for VideoSettings {
    fn default() -> Self {
        Self {
            platform: default_video_platform(),
            aspect: default_video_aspect(),
            width: default_video_width(),
            height: default_video_height(),
            codec: default_video_codec(),
            encoding: default_video_encoding(),
            audio_bitrate: default_video_bitrate(),
            fps: default_video_fps(),
            flip_horizontal: false,
            flip_vertical: false,
            preview_quality: default_preview_quality(),
            selected_chapter_ids: Vec::new(),
            selection_initialized: false,
            extensions: BTreeMap::new(),
        }
    }
}

/// Versioned home for Video 2 export state. The additive extension maps and
/// reserved composition collection let 3.x add layers/keyframes/variants
/// without changing the authoritative audio or transcript models.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct VideoProjectState {
    #[serde(default = "default_video_schema")]
    pub schema_version: u64,
    #[serde(default)]
    pub export_settings: VideoSettings,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub compositions: Vec<Value>,
    #[serde(flatten)]
    pub extensions: BTreeMap<String, Value>,
}

impl Default for VideoProjectState {
    fn default() -> Self {
        Self {
            schema_version: default_video_schema(),
            export_settings: VideoSettings::default(),
            compositions: Vec::new(),
            extensions: BTreeMap::new(),
        }
    }
}

impl VideoSettings {
    /// Validate the existing EnCAP video-state policy and adapt it to the rendering API.
    /// Unknown string values survive deserialization but cannot be executed silently.
    pub fn render_settings(&self) -> crate::Result<crate::RenderSettings> {
        use crate::{Codec, Composition, Encoding, Error, RenderSettings};
        if !(1..=120).contains(&self.fps) {
            return Err(Error::InvalidInput(
                "Video state frame rate must be 1–120 fps".into(),
            ));
        }
        if !matches!(
            self.audio_bitrate.as_str(),
            "64k" | "96k" | "128k" | "160k" | "192k" | "256k" | "320k"
        ) {
            return Err(Error::InvalidInput(
                "Unsupported Video state audio bitrate".into(),
            ));
        }
        let codec = match self.codec.to_ascii_lowercase().as_str() {
            "h264" => Codec::H264,
            "hevc" => Codec::Hevc,
            _ => {
                return Err(Error::InvalidInput(
                    "Video codec must be H264 or HEVC".into(),
                ))
            }
        };
        let encoding = match self.encoding.to_ascii_lowercase().as_str() {
            "automatic" => Encoding::Automatic,
            "hardware" => Encoding::Hardware,
            "software" => Encoding::Software,
            _ => return Err(Error::InvalidInput("Unknown Video encoding mode".into())),
        };
        let result = RenderSettings {
            width: self.width,
            height: self.height,
            fps: self.fps,
            audio_bitrate: self.audio_bitrate.clone(),
            codec,
            encoding,
            composition: Composition::SquarePadded,
            flip_horizontal: self.flip_horizontal,
            flip_vertical: self.flip_vertical,
        };
        result.validate()?;
        Ok(result)
    }
}
impl VideoProjectState {
    pub fn validate_schema(&self) -> crate::Result<()> {
        if self.schema_version != 1 {
            return Err(crate::Error::InvalidInput(format!(
                "Unsupported Video schema {}; supported schema is 1",
                self.schema_version
            )));
        }
        Ok(())
    }
}

#[cfg(test)]
mod encoding_policy_tests {
    use super::*;

    #[test]
    fn software_is_default_but_saved_choices_round_trip() {
        assert_eq!(VideoSettings::default().encoding, "software");
        let old: VideoSettings = serde_json::from_str("{}").unwrap();
        assert_eq!(old.encoding, "software");
        for mode in ["software", "automatic", "hardware"] {
            let settings: VideoSettings =
                serde_json::from_value(serde_json::json!({"encoding": mode})).unwrap();
            assert_eq!(serde_json::to_value(settings).unwrap()["encoding"], mode);
        }
    }
}
