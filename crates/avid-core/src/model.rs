use std::path::PathBuf;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Preset {
    pub platform: &'static str,
    pub aspect: &'static str,
    pub width: u32,
    pub height: u32,
}

pub const PRESETS: &[Preset] = &[
    Preset {
        platform: "Instagram",
        aspect: "Horizontal video (16:9)",
        width: 1920,
        height: 1080,
    },
    Preset {
        platform: "Instagram",
        aspect: "Square (1:1)",
        width: 1080,
        height: 1080,
    },
    Preset {
        platform: "Instagram",
        aspect: "4:5",
        width: 1080,
        height: 1350,
    },
    Preset {
        platform: "Instagram",
        aspect: "Vertical video (9:16)",
        width: 1080,
        height: 1920,
    },
    Preset {
        platform: "TikTok",
        aspect: "Vertical video (9:16)",
        width: 1080,
        height: 1920,
    },
    Preset {
        platform: "TikTok",
        aspect: "Vertical video (9:16)",
        width: 720,
        height: 1280,
    },
    Preset {
        platform: "Facebook",
        aspect: "Horizontal video (16:9)",
        width: 1280,
        height: 720,
    },
    Preset {
        platform: "Facebook",
        aspect: "Square (1:1)",
        width: 1080,
        height: 1080,
    },
    Preset {
        platform: "Facebook",
        aspect: "Vertical video (9:16)",
        width: 720,
        height: 1280,
    },
    Preset {
        platform: "Facebook",
        aspect: "Vertical video (9:16)",
        width: 1080,
        height: 1920,
    },
    Preset {
        platform: "Facebook",
        aspect: "4:5",
        width: 1080,
        height: 1350,
    },
    Preset {
        platform: "Twitter / X",
        aspect: "Horizontal video (16:9)",
        width: 1280,
        height: 720,
    },
    Preset {
        platform: "Twitter / X",
        aspect: "Square (1:1)",
        width: 720,
        height: 720,
    },
    Preset {
        platform: "Twitter / X",
        aspect: "Vertical video (9:16)",
        width: 720,
        height: 1280,
    },
    Preset {
        platform: "YouTube",
        aspect: "Horizontal video (16:9)",
        width: 1920,
        height: 1080,
    },
    Preset {
        platform: "YouTube",
        aspect: "Vertical video (9:16)",
        width: 1080,
        height: 1920,
    },
    Preset {
        platform: "YouTube",
        aspect: "Square (1:1)",
        width: 1080,
        height: 1080,
    },
    Preset {
        platform: "YouTube",
        aspect: "4:3",
        width: 1440,
        height: 1080,
    },
    Preset {
        platform: "LinkedIn",
        aspect: "Horizontal video (16:9)",
        width: 1920,
        height: 1080,
    },
    Preset {
        platform: "LinkedIn",
        aspect: "Square (1:1)",
        width: 1080,
        height: 1080,
    },
    Preset {
        platform: "Snapchat",
        aspect: "Vertical video (9:16)",
        width: 1080,
        height: 1920,
    },
    Preset {
        platform: "Pinterest",
        aspect: "Vertical video (9:16)",
        width: 1080,
        height: 1920,
    },
    Preset {
        platform: "Generic",
        aspect: "Horizontal video (16:9)",
        width: 1920,
        height: 1080,
    },
    Preset {
        platform: "Generic",
        aspect: "Vertical video (9:16)",
        width: 1080,
        height: 1920,
    },
    Preset {
        platform: "Generic",
        aspect: "Square (1:1)",
        width: 1080,
        height: 1080,
    },
    Preset {
        platform: "Generic",
        aspect: "4:3",
        width: 1440,
        height: 1080,
    },
    Preset {
        platform: "Generic",
        aspect: "4:5",
        width: 1080,
        height: 1350,
    },
];

#[derive(Clone, Debug)]
pub struct RenderRequest {
    pub image: PathBuf,
    pub audio: PathBuf,
    pub output: PathBuf,
    pub width: u32,
    pub height: u32,
    pub audio_bitrate: String,
    pub fps: u32,
    pub flip_horizontal: bool,
    pub flip_vertical: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Stage {
    Validating,
    Probing,
    Compositing,
    Encoding,
    Publishing,
    Complete,
}

impl Stage {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Validating => "validating",
            Self::Probing => "probing",
            Self::Compositing => "compositing",
            Self::Encoding => "encoding",
            Self::Publishing => "publishing",
            Self::Complete => "complete",
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct RenderProgress {
    pub elapsed_seconds: Option<f64>,
    pub duration_seconds: Option<f64>,
    pub fraction: Option<f64>,
    pub eta_seconds: Option<f64>,
}
