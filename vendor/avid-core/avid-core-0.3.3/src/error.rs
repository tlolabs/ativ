use std::{ffi::OsString, fmt, io, path::PathBuf, process::ExitStatus};

pub type Result<T> = std::result::Result<T, Error>;

/// Captured context is local diagnostic data; hosts should redact paths before presentation.
#[derive(Debug)]
pub struct ProcessFailure {
    pub operation: &'static str,
    pub executable: PathBuf,
    pub arguments: Vec<OsString>,
    pub status: Option<ExitStatus>,
    /// Last 64 KiB, decoded lossily. stdout is captured separately for successful probes.
    pub stderr: String,
}

#[derive(Debug)]
#[non_exhaustive]
pub enum Error {
    Cancelled,
    InvalidInput(String),
    /// Image codec diagnostics, independent of the external media process runner.
    ImageOptimization(String),
    ToolUnavailable {
        tool: &'static str,
        detail: String,
    },
    Io {
        operation: &'static str,
        path: PathBuf,
        source: io::Error,
    },
    Process {
        failure: Box<ProcessFailure>,
        source: Option<io::Error>,
    },
    Timeout(Box<ProcessFailure>),
    CaptureLimit(Box<ProcessFailure>),
    Fallback {
        hardware: Box<Error>,
        software: Box<Error>,
    },
}
impl Error {
    pub(crate) fn io(operation: &'static str, path: impl Into<PathBuf>, source: io::Error) -> Self {
        Self::Io {
            operation,
            path: path.into(),
            source,
        }
    }
    pub fn code(&self) -> &'static str {
        match self {
            Self::Cancelled => "cancelled",
            Self::InvalidInput(_) => "invalid_input",
            Self::ImageOptimization(_) => "image_optimization_failed",
            Self::ToolUnavailable { .. } => "media_tools_unavailable",
            Self::Io { .. } => "io_error",
            Self::Timeout(_) => "timeout",
            Self::CaptureLimit(_) => "capture_limit",
            Self::Process { .. } | Self::Fallback { .. } => "media_tool_failed",
        }
    }
}
impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Cancelled => write!(f, "Operation cancelled"),
            Self::InvalidInput(s) => f.write_str(s),
            Self::ImageOptimization(s) => write!(f, "Image optimization failed: {s}"),
            Self::ToolUnavailable { tool, detail } => write!(f, "{tool} unavailable: {detail}"),
            Self::Io {
                operation,
                path,
                source,
            } => write!(f, "{operation} ({}): {source}", path.display()),
            Self::Process { failure, source } => {
                write!(
                    f,
                    "{} failed ({:?}): {}",
                    failure.operation,
                    failure.status,
                    failure.stderr.trim()
                )?;
                if let Some(source) = source {
                    write!(f, ": {source}")?;
                }
                Ok(())
            }
            Self::Timeout(p) => write!(f, "{} timed out", p.operation),
            Self::CaptureLimit(p) => write!(f, "{} exceeded the output capture limit", p.operation),
            Self::Fallback { hardware, software } => write!(
                f,
                "Hardware attempt failed ({hardware}); software fallback failed ({software})"
            ),
        }
    }
}
impl std::error::Error for Error {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io { source, .. }
            | Self::Process {
                source: Some(source),
                ..
            } => Some(source),
            Self::Fallback { software, .. } => Some(software.as_ref()),
            _ => None,
        }
    }
}
