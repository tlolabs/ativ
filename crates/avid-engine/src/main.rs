use avid_core::{
    AvidError, EventSink, MediaTools, PRESETS, RenderProgress, RenderRequest, Stage, ToolOverrides,
    probe_audio_duration, render_preview, render_video,
};
use std::collections::{HashMap, HashSet};
use std::env;
use std::io::{self, BufRead};
use std::path::PathBuf;
use std::process::ExitCode;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            println!(
                "{{\"event\":\"error\",\"code\":\"{}\",\"message\":\"{}\"}}",
                error.code(),
                escape(&error.user_message())
            );
            eprintln!("{}", error.user_message());
            if matches!(error, AvidError::Cancelled) {
                ExitCode::from(130)
            } else {
                ExitCode::from(1)
            }
        }
    }
}

fn run() -> avid_core::Result<()> {
    let mut arguments = env::args().skip(1);
    let command = arguments.next().unwrap_or_else(|| "help".into());
    let parsed = Arguments::parse(arguments.collect())?;
    match command.as_str() {
        "help" | "--help" | "-h" => {
            print_help();
            Ok(())
        }
        "version" | "--version" | "-V" => {
            println!("avid-engine {}", avid_core::VERSION);
            Ok(())
        }
        "presets" => {
            print_presets();
            Ok(())
        }
        "check" => {
            let tools = tools(&parsed)?;
            println!(
                "{{\"event\":\"tools\",\"ffmpeg\":\"{}\",\"ffprobe\":\"{}\"}}",
                escape(&tools.ffmpeg_version),
                escape(&tools.ffprobe_version)
            );
            Ok(())
        }
        "probe" => {
            let tools = tools(&parsed)?;
            let duration = probe_audio_duration(&tools, &parsed.required_path("audio")?)?;
            println!(
                "{{\"event\":\"probe\",\"duration_seconds\":{}}}",
                number(duration)
            );
            Ok(())
        }
        "preview" => {
            let tools = tools(&parsed)?;
            render_preview(
                &tools,
                &parsed.required_path("image")?,
                &parsed.required_path("output")?,
                parsed.required_u32("width")?,
                parsed.required_u32("height")?,
                parsed.flags.contains("flip-horizontal"),
                parsed.flags.contains("flip-vertical"),
            )?;
            println!("{{\"event\":\"complete\",\"kind\":\"preview\"}}");
            Ok(())
        }
        "render" => {
            let tools = tools(&parsed)?;
            let request = RenderRequest {
                image: parsed.required_path("image")?,
                audio: parsed.required_path("audio")?,
                output: parsed.required_path("output")?,
                width: parsed.required_u32("width")?,
                height: parsed.required_u32("height")?,
                audio_bitrate: parsed
                    .values
                    .get("audio-bitrate")
                    .cloned()
                    .unwrap_or_else(|| "128k".into()),
                fps: parsed.values.get("fps").map_or(Ok(30), |value| {
                    value.parse::<u32>().map_err(|_| {
                        AvidError::InvalidInput("FPS must be a positive integer.".into())
                    })
                })?,
                flip_horizontal: parsed.flags.contains("flip-horizontal"),
                flip_vertical: parsed.flags.contains("flip-vertical"),
            };
            let cancelled = Arc::new(AtomicBool::new(false));
            let input_cancelled = Arc::clone(&cancelled);
            thread::spawn(move || {
                for line in io::stdin().lock().lines().map_while(Result::ok) {
                    if line.trim().eq_ignore_ascii_case("cancel") {
                        input_cancelled.store(true, Ordering::SeqCst);
                        break;
                    }
                }
            });
            render_video(&tools, &request, cancelled, &JsonEvents)
        }
        _ => Err(AvidError::InvalidInput(format!(
            "Unknown command '{command}'. Run avid-engine help."
        ))),
    }
}

fn tools(arguments: &Arguments) -> avid_core::Result<MediaTools> {
    MediaTools::discover(ToolOverrides {
        ffmpeg: arguments.values.get("ffmpeg").map(PathBuf::from),
        ffprobe: arguments.values.get("ffprobe").map(PathBuf::from),
    })
}

#[derive(Default)]
struct Arguments {
    values: HashMap<String, String>,
    flags: HashSet<String>,
}

impl Arguments {
    fn parse(raw: Vec<String>) -> avid_core::Result<Self> {
        let mut parsed = Self::default();
        let mut index = 0;
        while index < raw.len() {
            let key = raw[index]
                .strip_prefix("--")
                .ok_or_else(|| {
                    AvidError::InvalidInput(format!("Unexpected argument '{}'.", raw[index]))
                })?
                .to_owned();
            if matches!(key.as_str(), "flip-horizontal" | "flip-vertical") {
                parsed.flags.insert(key);
                index += 1;
            } else {
                let value = raw
                    .get(index + 1)
                    .ok_or_else(|| AvidError::InvalidInput(format!("--{key} requires a value.")))?
                    .to_owned();
                parsed.values.insert(key, value);
                index += 2;
            }
        }
        Ok(parsed)
    }

    fn required_path(&self, name: &str) -> avid_core::Result<PathBuf> {
        self.values
            .get(name)
            .map(PathBuf::from)
            .ok_or_else(|| AvidError::InvalidInput(format!("--{name} is required.")))
    }
    fn required_u32(&self, name: &str) -> avid_core::Result<u32> {
        self.values
            .get(name)
            .ok_or_else(|| AvidError::InvalidInput(format!("--{name} is required.")))?
            .parse()
            .map_err(|_| AvidError::InvalidInput(format!("--{name} must be a positive integer.")))
    }
}

struct JsonEvents;
impl EventSink for JsonEvents {
    fn stage(&self, stage: Stage) {
        println!("{{\"event\":\"stage\",\"stage\":\"{}\"}}", stage.as_str());
    }
    fn progress(&self, progress: RenderProgress) {
        println!(
            "{{\"event\":\"progress\",\"elapsed_seconds\":{},\"duration_seconds\":{},\"fraction\":{},\"eta_seconds\":{}}}",
            number(progress.elapsed_seconds),
            number(progress.duration_seconds),
            number(progress.fraction),
            number(progress.eta_seconds)
        );
    }
}

fn print_presets() {
    print!("{{\"event\":\"presets\",\"items\":[");
    for (index, preset) in PRESETS.iter().enumerate() {
        if index > 0 {
            print!(",");
        }
        print!(
            "{{\"platform\":\"{}\",\"aspect\":\"{}\",\"width\":{},\"height\":{}}}",
            escape(preset.platform),
            escape(preset.aspect),
            preset.width,
            preset.height
        );
    }
    println!("]}}");
}

fn number(value: Option<f64>) -> String {
    value
        .filter(|value| value.is_finite())
        .map_or_else(|| "null".into(), |value| value.to_string())
}
fn escape(value: &str) -> String {
    value
        .chars()
        .flat_map(|character| match character {
            '\\' => "\\\\".chars().collect::<Vec<_>>(),
            '"' => "\\\"".chars().collect(),
            '\n' => "\\n".chars().collect(),
            '\r' => "\\r".chars().collect(),
            '\t' => "\\t".chars().collect(),
            value if value.is_control() => "�".chars().collect(),
            value => vec![value],
        })
        .collect()
}

fn print_help() {
    println!(
        "A.V.I.D. shared engine\n\nCommands:\n  check [--ffmpeg PATH --ffprobe PATH]\n  presets\n  probe --audio PATH\n  preview --image PATH --output PATH --width N --height N [--flip-horizontal] [--flip-vertical]\n  render --image PATH --audio PATH --output PATH --width N --height N [--audio-bitrate 128k] [--fps 30] [--flip-horizontal] [--flip-vertical]\n\nDuring render, write 'cancel' followed by a newline to standard input to stop safely."
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn json_escape_handles_control_characters() {
        assert_eq!(escape("a\"b\\c\n"), "a\\\"b\\\\c\\n");
    }
    #[test]
    fn parser_preserves_paths_with_spaces() {
        let parsed = Arguments::parse(vec![
            "--image".into(),
            "/tmp/my image.png".into(),
            "--flip-horizontal".into(),
        ])
        .unwrap();
        assert_eq!(parsed.values["image"], "/tmp/my image.png");
        assert!(parsed.flags.contains("flip-horizontal"));
    }
}
