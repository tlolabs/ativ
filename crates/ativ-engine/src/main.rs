use ativ_core::{
    AtivError, CancellationToken, Composition, EventSink, MediaTools, PRESETS, PreviewRequest,
    RenderMode, RenderProgress, RenderRequest, RenderSettings, Renderer, Stage, ToolDiscovery,
};
use std::collections::{HashMap, HashSet};
use std::env;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Instant;

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            append_log(&format!("error [{}]: {error:?}", error.code()));
            println!(
                "{{\"event\":\"error\",\"code\":\"{}\",\"message\":\"{}\"}}",
                error.code(),
                escape(&error.user_message())
            );
            eprintln!("{}", error.user_message());
            if error.code() == "cancelled" {
                ExitCode::from(130)
            } else {
                ExitCode::from(1)
            }
        }
    }
}

fn run() -> ativ_core::Result<()> {
    let mut arguments = env::args().skip(1);
    let command = arguments.next().unwrap_or_else(|| "help".into());
    let parsed = Arguments::parse(arguments.collect())?;
    let token = if matches!(command.as_str(), "check" | "probe" | "preview" | "render") {
        stdin_cancellation()
    } else {
        CancellationToken::default()
    };
    match command.as_str() {
        "help" | "--help" | "-h" => {
            print_help();
            Ok(())
        }
        "version" | "--version" | "-V" => {
            println!("ativ-engine {}", ativ_core::VERSION);
            Ok(())
        }
        "presets" => {
            print_presets();
            Ok(())
        }
        "check" => {
            let tools = tools(&parsed, &token)?;
            println!(
                "{{\"event\":\"tools\",\"ffmpeg\":\"{}\",\"ffprobe\":\"{}\"}}",
                escape(tools.ffmpeg_version()),
                escape(tools.ffprobe_version())
            );
            Ok(())
        }
        "probe" => {
            let tools = tools(&parsed, &token)?;
            let duration = Renderer::new(tools)
                .probe_audio_duration(&parsed.required_path("audio")?, &token)?;
            println!(
                "{{\"event\":\"probe\",\"duration_seconds\":{}}}",
                number(duration)
            );
            Ok(())
        }
        "preview" => {
            let tools = tools(&parsed, &token)?;
            Renderer::new(tools).preview(
                &PreviewRequest {
                    image: parsed.required_path("image")?,
                    output: parsed.required_path("output")?,
                    settings: RenderSettings {
                        width: parsed.required_u32("width")?,
                        height: parsed.required_u32("height")?,
                        composition: Composition::Fitted,
                        flip_horizontal: parsed.flags.contains("flip-horizontal"),
                        flip_vertical: parsed.flags.contains("flip-vertical"),
                        ..Default::default()
                    },
                    protected_paths: vec![],
                },
                &token,
                &(),
            )?;
            println!("{{\"event\":\"complete\",\"kind\":\"preview\"}}");
            Ok(())
        }
        "render" => {
            let started = Instant::now();
            let mode = match parsed
                .values
                .get("render-mode")
                .map(String::as_str)
                .unwrap_or("simple")
            {
                "simple" => RenderMode::Simple,
                "current" => RenderMode::PerFrame,
                _ => {
                    return Err(AtivError::InvalidInput(
                        "--render-mode must be simple or current.".into(),
                    ));
                }
            };
            let tools = tools(&parsed, &token)?;
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
                        AtivError::InvalidInput("FPS must be a positive integer.".into())
                    })
                })?,
                flip_horizontal: parsed.flags.contains("flip-horizontal"),
                flip_vertical: parsed.flags.contains("flip-vertical"),
            };
            let events = JsonEvents::new();
            let result =
                Renderer::new(tools).render_with_mode(&request.shared(), mode, &token, &events);
            let seconds = started.elapsed().as_secs_f64();
            events.log(&format!(
                "export wall time: {seconds:.6}s; mode: {mode:?}; success: {}",
                result.is_ok()
            ));
            println!(
                "{{\"event\":\"timing\",\"wall_seconds\":{seconds},\"render_mode\":\"{}\",\"success\":{}}}",
                if mode == RenderMode::Simple {
                    "simple"
                } else {
                    "current"
                },
                result.is_ok()
            );
            result?;
            Ok(())
        }
        _ => Err(AtivError::InvalidInput(
            "Unknown command. Run ativ-engine help.".into(),
        )),
    }
}

fn stdin_cancellation() -> CancellationToken {
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
    CancellationToken::from(cancelled)
}

fn tools(arguments: &Arguments, token: &CancellationToken) -> ativ_core::Result<MediaTools> {
    Ok(MediaTools::discover(
        ToolDiscovery {
            ffmpeg: arguments.values.get("ffmpeg").map(PathBuf::from),
            ffprobe: arguments.values.get("ffprobe").map(PathBuf::from),
            ..Default::default()
        },
        token,
    )?)
}

#[derive(Default)]
struct Arguments {
    values: HashMap<String, String>,
    flags: HashSet<String>,
}

impl Arguments {
    fn parse(raw: Vec<String>) -> ativ_core::Result<Self> {
        let mut parsed = Self::default();
        let mut index = 0;
        while index < raw.len() {
            let key = raw[index]
                .strip_prefix("--")
                .ok_or_else(|| {
                    AtivError::InvalidInput("Unexpected argument. Run ativ-engine help.".into())
                })?
                .to_owned();
            if matches!(key.as_str(), "flip-horizontal" | "flip-vertical") {
                parsed.flags.insert(key);
                index += 1;
            } else {
                let value = raw
                    .get(index + 1)
                    .ok_or_else(|| AtivError::InvalidInput(format!("--{key} requires a value.")))?
                    .to_owned();
                parsed.values.insert(key, value);
                index += 2;
            }
        }
        Ok(parsed)
    }

    fn required_path(&self, name: &str) -> ativ_core::Result<PathBuf> {
        self.values
            .get(name)
            .map(PathBuf::from)
            .ok_or_else(|| AtivError::InvalidInput(format!("--{name} is required.")))
    }
    fn required_u32(&self, name: &str) -> ativ_core::Result<u32> {
        self.values
            .get(name)
            .ok_or_else(|| AtivError::InvalidInput(format!("--{name} is required.")))?
            .parse()
            .map_err(|_| AtivError::InvalidInput(format!("--{name} must be a positive integer.")))
    }
}

struct JsonEvents {
    log: Mutex<Option<File>>,
}

impl JsonEvents {
    fn new() -> Self {
        Self {
            log: Mutex::new(open_log()),
        }
    }

    fn log(&self, line: &str) {
        use std::io::Write;
        let Ok(mut guard) = self.log.lock() else {
            return;
        };
        if let Some(file) = guard.as_mut() {
            let _ = writeln!(file, "{line}");
        }
    }
}

impl EventSink for JsonEvents {
    fn stage(&self, stage: Stage) {
        self.log(&format!("stage: {}", stage.as_str()));
        println!("{{\"event\":\"stage\",\"stage\":\"{}\"}}", stage.as_str());
    }
    fn progress(&self, progress: RenderProgress) {
        self.log(&format!("progress: {progress:?}"));
        println!(
            "{{\"event\":\"progress\",\"elapsed_seconds\":{},\"duration_seconds\":{},\"fraction\":{},\"eta_seconds\":{}}}",
            number(progress.elapsed_seconds),
            number(progress.duration_seconds),
            number(progress.fraction),
            number(progress.eta_seconds)
        );
    }
    fn diagnostic(&self, line: &str) {
        self.log(line);
    }
}

fn append_log(line: &str) {
    use std::io::Write;
    if let Some(mut file) = open_log() {
        let _ = writeln!(file, "{line}");
    }
}

fn open_log() -> Option<File> {
    if let Some(path) = env::var_os("ATIV_LOG_PATH") {
        return open_log_at(&PathBuf::from(path), false);
    }
    open_log_at(&default_diagnostic_log_path()?, true)
}

fn open_log_at(path: &Path, _protect_parent: bool) -> Option<File> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).ok()?;
        #[cfg(unix)]
        if _protect_parent {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(parent, fs::Permissions::from_mode(0o700)).ok()?;
        }
    }
    if fs::metadata(path).is_ok_and(|metadata| metadata.len() > 1_048_576) {
        let rotated = path.with_extension("log.old");
        let _ = fs::remove_file(&rotated);
        let _ = fs::rename(path, &rotated);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = fs::set_permissions(&rotated, fs::Permissions::from_mode(0o600));
        }
    }
    let mut options = OpenOptions::new();
    options.create(true).append(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let file = options.open(path).ok()?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o600)).ok()?;
    }
    Some(file)
}

#[cfg(target_os = "macos")]
fn default_diagnostic_log_path() -> Option<PathBuf> {
    env::var_os("HOME")
        .map(PathBuf::from)
        .map(|home| home.join("Library/Logs/ATIV/ativ-engine.log"))
}

#[cfg(target_os = "windows")]
fn default_diagnostic_log_path() -> Option<PathBuf> {
    env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .map(|root| root.join("ATIV/Logs/ativ-engine.log"))
}

#[cfg(all(unix, not(target_os = "macos")))]
fn default_diagnostic_log_path() -> Option<PathBuf> {
    if let Some(root) = env::var_os("XDG_STATE_HOME") {
        return Some(PathBuf::from(root).join("ativ/ativ-engine.log"));
    }
    env::var_os("HOME")
        .map(PathBuf::from)
        .map(|home| home.join(".local/state/ativ/ativ-engine.log"))
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
        "A.T.I.V. shared engine\n\nCommands:\n  check [--ffmpeg PATH --ffprobe PATH]\n  presets\n  probe --audio PATH\n  preview --image PATH --output PATH --width N --height N [--flip-horizontal] [--flip-vertical]\n  render --image PATH --audio PATH --output PATH --width N --height N [--audio-bitrate 128k] [--fps 30] [--render-mode simple|current] [--flip-horizontal] [--flip-vertical]\n\nDuring a media operation, write 'cancel' followed by a newline to standard input to stop safely."
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
    fn protocol_numbers_preserve_null_for_unknown_or_nonfinite_values() {
        for value in [
            None,
            Some(f64::NAN),
            Some(f64::INFINITY),
            Some(f64::NEG_INFINITY),
        ] {
            assert_eq!(number(value), "null");
        }
        assert_eq!(number(Some(0.0)), "0");
        assert_eq!(number(Some(1.25)), "1.25");
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

    #[cfg(unix)]
    #[test]
    fn diagnostic_logs_are_private() {
        use std::os::unix::fs::PermissionsExt;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let directory =
            env::temp_dir().join(format!("ativ-log-test-{}-{unique}", std::process::id()));
        let path = directory.join("ativ-engine.log");
        drop(open_log_at(&path, true).expect("open private log"));
        assert_eq!(
            fs::metadata(&directory)
                .expect("directory")
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
        assert_eq!(
            fs::metadata(&path).expect("log").permissions().mode() & 0o777,
            0o600
        );
        fs::remove_dir_all(directory).expect("cleanup");
    }
}
