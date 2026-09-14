use avid_core::Error;
use std::fmt;

pub type Result<T> = std::result::Result<T, AtivError>;

#[derive(Debug)]
pub enum AtivError {
    /// Host-authored CLI guidance only; never put shared diagnostic text here.
    InvalidInput(String),
    Shared(Error),
}
impl From<Error> for AtivError {
    fn from(error: Error) -> Self {
        Self::Shared(error)
    }
}
impl AtivError {
    pub fn code(&self) -> &'static str {
        match self {
            Self::InvalidInput(_) | Self::Shared(Error::InvalidInput(_)) => "invalid_input",
            Self::Shared(Error::Cancelled) => "cancelled",
            Self::Shared(Error::ToolUnavailable { .. }) => "media_tools_unavailable",
            Self::Shared(Error::Io { .. }) => "io_error",
            // Preserve the old discovery exit/spawn categories without discarding causes.
            Self::Shared(Error::Process {
                source: Some(_), ..
            }) => "io_error",
            Self::Shared(Error::Process { failure, .. })
                if failure.operation == "validate media tool" =>
            {
                "media_tools_unavailable"
            }
            Self::Shared(_) => "media_tool_failed",
        }
    }
    pub fn user_message(&self) -> String {
        match self {
            Self::InvalidInput(message) => message.clone(),
            Self::Shared(Error::Cancelled) =>
                "Video creation was stopped. The previous output was preserved.".into(),
            Self::Shared(Error::InvalidInput(_)) =>
                "Check the artwork, audio, dimensions, frame rate, bitrate, and output destination. The output must be separate from the source files.".into(),
            _ => match self.code() {
                "media_tools_unavailable" => "A.T.I.V. could not use its media tools. Restore the matching bundled FFmpeg and ffprobe pair or check the configured tools.",
                "io_error" => "A.T.I.V. could not access a required file or start a media tool. Check file permissions and the output destination.",
                _ => "The media tool could not complete this operation. Check the selected media and see the local diagnostics for technical details.",
            }.into(),
        }
    }
}
impl fmt::Display for AtivError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.user_message())
    }
}
impl std::error::Error for AtivError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Shared(error) => Some(error),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use avid_core::ProcessFailure;
    fn failure(operation: &'static str) -> Box<ProcessFailure> {
        Box::new(ProcessFailure {
            operation,
            executable: "/private/tool".into(),
            arguments: vec!["/private/source".into()],
            status: None,
            stderr: "private stderr".into(),
        })
    }
    #[test]
    fn protocol_categories_retain_structured_private_diagnostics() {
        let cases = [
            (Error::Cancelled, "cancelled"),
            (
                Error::InvalidInput("/private/source".into()),
                "invalid_input",
            ),
            (
                Error::ToolUnavailable {
                    tool: "ffmpeg",
                    detail: "/private/tool".into(),
                },
                "media_tools_unavailable",
            ),
            (
                Error::Io {
                    operation: "open",
                    path: "/private/file".into(),
                    source: std::io::Error::other("private OS error"),
                },
                "io_error",
            ),
            (
                Error::Process {
                    failure: failure("render"),
                    source: None,
                },
                "media_tool_failed",
            ),
            (
                Error::Process {
                    failure: failure("validate media tool"),
                    source: None,
                },
                "media_tools_unavailable",
            ),
            (
                Error::Process {
                    failure: failure("render"),
                    source: Some(std::io::Error::other("private OS error")),
                },
                "io_error",
            ),
            (Error::Timeout(failure("render")), "media_tool_failed"),
            (Error::CaptureLimit(failure("probe")), "media_tool_failed"),
            (
                Error::Fallback {
                    hardware: Box::new(Error::Timeout(failure("hardware"))),
                    software: Box::new(Error::Timeout(failure("software"))),
                },
                "media_tool_failed",
            ),
        ];
        for (error, code) in cases {
            let adapter = AtivError::from(error);
            assert_eq!(adapter.code(), code);
            assert!(!adapter.user_message().contains("private"));
            assert!(std::error::Error::source(&adapter).is_some());
            if code != "cancelled" {
                assert!(format!("{adapter:?}").contains("private"));
            }
        }
    }
}
