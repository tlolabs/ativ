use crate::{Error, Result, MAX_OUTPUT_DIMENSION, MAX_OUTPUT_PIXELS};
use serde::Serialize;
use std::{collections::HashSet, path::PathBuf};

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum Codec {
    #[default]
    H264,
    Hevc,
}
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum Encoding {
    Automatic,
    Hardware,
    #[default]
    Software,
}
/// Frame generation policy, independent of codec and visual treatment.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum RenderMode {
    /// Preserve the original per-frame artwork processing path.
    #[default]
    PerFrame,
    /// Composite the first artwork frame once per clip and reuse it at the requested fps.
    /// Artwork and background blur remain static; timeline clips still use hard cuts.
    Simple,
}

/// Existing visual treatments, described by behavior rather than host identity.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum Composition {
    /// ATIV: sigma 40 background, fitted unpadded foreground.
    #[default]
    Fitted,
    /// EnCAP: sigma 20 background, foreground padded to a square.
    SquarePadded,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RenderSettings {
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    pub audio_bitrate: String,
    pub codec: Codec,
    pub encoding: Encoding,
    pub composition: Composition,
    pub flip_horizontal: bool,
    pub flip_vertical: bool,
}
impl Default for RenderSettings {
    fn default() -> Self {
        Self {
            width: 1920,
            height: 1080,
            fps: 30,
            audio_bitrate: "128k".into(),
            codec: Codec::H264,
            encoding: Encoding::Software,
            composition: Composition::Fitted,
            flip_horizontal: false,
            flip_vertical: false,
        }
    }
}
impl RenderSettings {
    pub fn validate(&self) -> Result<()> {
        validate_dimensions(self.width, self.height)?;
        if !(1..=240).contains(&self.fps) {
            return Err(Error::InvalidInput("Frame rate must be 1–240 fps".into()));
        }
        let bitrate = self.audio_bitrate.as_bytes();
        let digits = if bitrate
            .last()
            .is_some_and(|c| matches!(c, b'k' | b'm' | b'b'))
        {
            &bitrate[..bitrate.len() - 1]
        } else {
            bitrate
        };
        if digits.is_empty()
            || !digits.iter().all(u8::is_ascii_digit)
            || digits.iter().all(|c| *c == b'0')
        {
            return Err(Error::InvalidInput(
                "Audio bitrate must be positive digits with optional k/m/b suffix".into(),
            ));
        }
        Ok(())
    }
}
pub(crate) fn validate_dimensions(width: u32, height: u32) -> Result<()> {
    if width == 0
        || height == 0
        || width % 2 != 0
        || height % 2 != 0
        || width > MAX_OUTPUT_DIMENSION
        || height > MAX_OUTPUT_DIMENSION
        || u64::from(width) * u64::from(height) > MAX_OUTPUT_PIXELS
    {
        return Err(Error::InvalidInput(
            "Dimensions must be positive and even, at most 8192 per axis and 33,177,600 pixels"
                .into(),
        ));
    }
    Ok(())
}
#[derive(Clone, Debug, PartialEq)]
pub struct Clip {
    pub id: String,
    pub image: PathBuf,
    pub audio: PathBuf,
    /// Length from the beginning of this audio source, not a seek into a combined recording.
    pub duration_seconds: f64,
}
/// Ordered, validated clips; selection never mutates the source collection.
#[derive(Clone, Debug, PartialEq)]
pub struct Timeline {
    clips: Vec<Clip>,
    duration: f64,
}
impl Timeline {
    pub fn new(clips: Vec<Clip>) -> Result<Self> {
        let mut seen = HashSet::new();
        let mut duration = 0.0;
        for clip in &clips {
            if !seen.insert(&clip.id) {
                return Err(Error::InvalidInput("Duplicate clip ID".into()));
            }
            if !clip.duration_seconds.is_finite() || clip.duration_seconds <= 0.0 {
                return Err(Error::InvalidInput(
                    "Clip duration must be finite and positive".into(),
                ));
            }
            duration += clip.duration_seconds;
        }
        if !duration.is_finite() {
            return Err(Error::InvalidInput("Timeline duration overflow".into()));
        }
        Ok(Self { clips, duration })
    }
    pub fn select(clips: &[Clip], ids: &[String], initialized: bool) -> Result<Self> {
        let available: Vec<_> = clips.iter().map(|clip| clip.id.as_str()).collect();
        let selected = select_clip_indices(&available, ids, initialized)?
            .into_iter()
            .map(|index| clips[index].clone())
            .collect();
        Self::new(selected)
    }
    pub fn clips(&self) -> &[Clip] {
        &self.clips
    }
    pub fn duration_seconds(&self) -> f64 {
        self.duration
    }
    /// At a boundary selects the next clip; the final endpoint selects the last clip at its end.
    pub fn position(&self, seconds: f64) -> Option<TimelinePosition> {
        if !seconds.is_finite() {
            return None;
        }
        let target = seconds.clamp(0.0, self.duration);
        let mut start = 0.0;
        for (index, clip) in self.clips.iter().enumerate() {
            if target < start + clip.duration_seconds || index + 1 == self.clips.len() {
                return Some(TimelinePosition {
                    index,
                    start_seconds: start,
                    offset_seconds: target - start,
                });
            }
            start += clip.duration_seconds;
        }
        None
    }
}
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TimelinePosition {
    pub index: usize,
    pub start_seconds: f64,
    pub offset_seconds: f64,
}
#[derive(Clone, Debug, PartialEq)]
pub enum Input {
    /// Original ATIV path: original audio format, no artificial duration trim or concat.
    Single { image: PathBuf, audio: PathBuf },
    /// EnCAP path: hard cuts and stereo/48 kHz audio normalization.
    Timeline(Timeline),
}
#[derive(Clone, Debug)]
pub struct RenderRequest {
    pub input: Input,
    pub settings: RenderSettings,
    pub output: PathBuf,
    /// Host project/archive and unselected source paths that must not be replaced.
    pub protected_paths: Vec<PathBuf>,
}
#[derive(Clone, Debug)]
pub struct PreviewRequest {
    pub image: PathBuf,
    pub output: PathBuf,
    pub settings: RenderSettings,
    pub protected_paths: Vec<PathBuf>,
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct EncoderCapability {
    pub codec: String,
    pub encoder: String,
    pub hardware: bool,
}
#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize)]
pub struct Capabilities {
    pub encoders: Vec<EncoderCapability>,
}

/// Resolve an ordered selection before a host maps its source records into media clips.
/// Empty/uninitialized selects all; empty/initialized selects none. IDs must be unambiguous.
pub fn select_clip_indices(
    available_ids: &[&str],
    selected_ids: &[String],
    initialized: bool,
) -> Result<Vec<usize>> {
    let mut known = std::collections::HashMap::new();
    for (index, id) in available_ids.iter().enumerate() {
        if known.insert(*id, index).is_some() {
            return Err(Error::InvalidInput("Duplicate clip ID".into()));
        }
    }
    if selected_ids.is_empty() && !initialized {
        return Ok((0..available_ids.len()).collect());
    }
    let mut seen = HashSet::new();
    selected_ids
        .iter()
        .map(|id| {
            if !seen.insert(id) {
                return Err(Error::InvalidInput(
                    "A clip was selected more than once".into(),
                ));
            }
            known.get(id.as_str()).copied().ok_or_else(|| {
                Error::InvalidInput(format!("Selection refers to missing clip {id}"))
            })
        })
        .collect()
}
