//! Application discovery policy. Compatibility and capabilities belong to AVID Core.
use ativ_core::{CancellationToken, MediaTools, ToolDiscovery};
use std::path::PathBuf;

pub fn resolve(
    ffmpeg: Option<PathBuf>,
    ffprobe: Option<PathBuf>,
    token: &CancellationToken,
) -> ativ_core::Result<MediaTools> {
    // CLI paths are deliberate development overrides, retaining their existing policy.
    #[cfg(feature = "managed-runtime")]
    if ffmpeg.is_none() && ffprobe.is_none() {
        let executable = std::env::current_exe().map_err(|_| {
            ativ_core::AtivError::InvalidInput(
                "Could not locate the application media directory.".into(),
            )
        })?;
        let directory = executable.parent().ok_or_else(|| {
            ativ_core::AtivError::InvalidInput(
                "Could not locate the application media directory.".into(),
            )
        })?;
        let metadata = if cfg!(target_os = "macos")
            && directory.file_name().is_some_and(|n| n == "MacOS")
            && directory
                .parent()
                .and_then(|p| p.file_name())
                .is_some_and(|n| n == "Contents")
        {
            directory.join("../Resources/FFmpeg")
        } else {
            directory.to_owned()
        };
        return Ok(MediaTools::from_managed_layout(
            directory, &metadata, token,
        )?);
    }
    Ok(MediaTools::discover(
        ToolDiscovery {
            ffmpeg,
            ffprobe,
            ..Default::default()
        },
        token,
    )?)
}
