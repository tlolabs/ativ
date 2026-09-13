use crate::{AvidError, Result};
use std::env;
use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

#[derive(Clone, Debug, Default)]
pub struct ToolOverrides {
    pub ffmpeg: Option<PathBuf>,
    pub ffprobe: Option<PathBuf>,
}

#[derive(Clone, Debug)]
pub struct MediaTools {
    pub ffmpeg: PathBuf,
    pub ffprobe: PathBuf,
    pub ffmpeg_version: String,
    pub ffprobe_version: String,
}

impl MediaTools {
    pub fn discover(overrides: ToolOverrides) -> Result<Self> {
        let ffmpeg = locate_tool("ffmpeg", overrides.ffmpeg)?;
        let ffprobe = locate_tool("ffprobe", overrides.ffprobe)?;
        let ffmpeg_version = validate_tool(&ffmpeg, "ffmpeg")?;
        let ffprobe_version = validate_tool(&ffprobe, "ffprobe")?;
        Ok(Self {
            ffmpeg,
            ffprobe,
            ffmpeg_version,
            ffprobe_version,
        })
    }
}

fn executable_name(base: &str) -> OsString {
    if cfg!(windows) {
        format!("{base}.exe").into()
    } else {
        base.into()
    }
}

fn locate_tool(name: &'static str, override_path: Option<PathBuf>) -> Result<PathBuf> {
    if let Some(path) = override_path {
        return validate_candidate(name, path);
    }
    let executable =
        env::current_exe().map_err(|error| AvidError::io("locate the A.V.I.D. engine", error))?;
    let binary = executable_name(name);
    let mut candidates = Vec::new();
    if let Some(directory) = executable.parent() {
        candidates.push(directory.join(&binary));
        candidates.push(directory.join("ffmpeg").join(&binary));
        if let Some(contents) = directory.parent() {
            candidates.push(contents.join("Resources").join(&binary));
            candidates.push(contents.join("Frameworks").join(&binary));
        }
    }
    if let Some(paths) = env::var_os("PATH") {
        candidates.extend(env::split_paths(&paths).map(|directory| directory.join(&binary)));
    }
    if let Some(path) = candidates.into_iter().find(|candidate| candidate.is_file()) {
        return Ok(path);
    }
    Err(AvidError::MediaToolsUnavailable(format!(
        "A.V.I.D. could not find its bundled {name} binary. Reinstall the application or restore the application package."
    )))
}

fn validate_candidate(name: &'static str, path: PathBuf) -> Result<PathBuf> {
    if path.is_file() {
        Ok(path)
    } else {
        Err(AvidError::MediaToolsUnavailable(format!(
            "The configured {name} binary does not exist or is not a file: {}",
            path.display()
        )))
    }
}

fn validate_tool(path: &Path, name: &'static str) -> Result<String> {
    let output = Command::new(path)
        .arg("-version")
        .stdin(Stdio::null())
        .output()
        .map_err(|error| AvidError::io("start a bundled media tool", error))?;
    if !output.status.success() {
        return Err(AvidError::MediaToolsUnavailable(format!(
            "The bundled {name} binary could not run. Reinstall A.V.I.D."
        )));
    }
    let first_line = String::from_utf8_lossy(&output.stdout)
        .lines()
        .next()
        .unwrap_or_default()
        .trim()
        .to_owned();
    if !first_line.to_ascii_lowercase().starts_with(name) {
        return Err(AvidError::MediaToolsUnavailable(format!(
            "The bundled file named {name} did not identify itself correctly. Reinstall A.V.I.D."
        )));
    }
    Ok(first_line)
}
