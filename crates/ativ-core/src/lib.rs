//! ATIV application policy and error presentation over the canonical media engine.
//! No media execution or validation is implemented in this compatibility adapter.
mod error;
mod model;

pub use avid_core::{
    CancellationToken, Composition, EventSink, MediaTools, PRESETS, Preset, PreviewRequest,
    Progress as RenderProgress, RenderMode, RenderSettings, Renderer, Stage,
};
pub use error::{AtivError, Result};
pub use model::RenderRequest;

/// Application identity, independent of the shared library version.
pub const VERSION: &str = match option_env!("ATIV_VERSION") {
    Some(version) => version,
    None => env!("CARGO_PKG_VERSION"),
};

/// Shared dependency identity generated from the checked-in Cargo pin and lockfile.
pub const CORE_VERSION: &str = env!("ATIV_CORE_VERSION");
pub const CORE_REVISION: &str = env!("ATIV_CORE_REVISION");
pub const CORE_SOURCE: &str = env!("ATIV_CORE_SOURCE");
