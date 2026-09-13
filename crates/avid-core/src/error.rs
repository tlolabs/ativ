use std::fmt;
use std::io;

pub type Result<T> = std::result::Result<T, AvidError>;

#[derive(Debug)]
pub enum AvidError {
    Cancelled,
    InvalidInput(String),
    MediaToolsUnavailable(String),
    MediaToolFailed {
        tool: &'static str,
        detail: String,
    },
    Io {
        action: &'static str,
        source: io::Error,
    },
}

impl AvidError {
    pub(crate) fn io(action: &'static str, source: io::Error) -> Self {
        Self::Io { action, source }
    }

    pub fn user_message(&self) -> String {
        match self {
            Self::Cancelled => {
                "Video creation was stopped. The previous output was preserved.".into()
            }
            Self::InvalidInput(message) | Self::MediaToolsUnavailable(message) => message.clone(),
            Self::MediaToolFailed { tool, detail } => {
                format!("{tool} could not complete this media operation. {detail}")
            }
            Self::Io { action, source } => format!("Could not {action}: {source}"),
        }
    }

    pub fn code(&self) -> &'static str {
        match self {
            Self::Cancelled => "cancelled",
            Self::InvalidInput(_) => "invalid_input",
            Self::MediaToolsUnavailable(_) => "media_tools_unavailable",
            Self::MediaToolFailed { .. } => "media_tool_failed",
            Self::Io { .. } => "io_error",
        }
    }
}

impl fmt::Display for AvidError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.user_message())
    }
}

impl std::error::Error for AvidError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io { source, .. } => Some(source),
            _ => None,
        }
    }
}
