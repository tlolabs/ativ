//! ATIV application policy and error presentation over the canonical media engine.
//! No media execution or validation is implemented in this compatibility adapter.
mod error;
mod model;

pub use avid_core::{
    CancellationToken, Composition, EventSink, MediaTools, PRESETS, Preset, PreviewRequest,
    Progress as RenderProgress, RenderSettings, Renderer, Stage, ToolDiscovery,
};
pub use error::{AtivError, Result};
pub use model::RenderRequest;

/// Application identity, independent of the shared library version.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
