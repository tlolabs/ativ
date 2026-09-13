//! Shared application engine for A.V.I.D.
//!
//! Platform applications communicate with `avid-engine`; this crate owns all
//! validation, presets, FFmpeg orchestration, progress, cancellation, and safe
//! output publication.

mod error;
mod media;
mod model;
mod render;

pub use error::{AvidError, Result};
pub use media::{MediaTools, ToolOverrides};
pub use model::{PRESETS, Preset, RenderProgress, RenderRequest, Stage};
pub use render::{EventSink, probe_audio_duration, render_preview, render_video};

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
pub const MAX_SOURCE_IMAGE_DIMENSION: u32 = 32_768;
pub const MAX_SOURCE_IMAGE_PIXELS: u64 = 50_000_000;
pub const MAX_OUTPUT_DIMENSION: u32 = 8_192;
pub const MAX_OUTPUT_PIXELS: u64 = 33_177_600;
