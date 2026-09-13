use crate::{
    AtivError, MAX_OUTPUT_DIMENSION, MAX_OUTPUT_PIXELS, MAX_SOURCE_IMAGE_DIMENSION,
    MAX_SOURCE_IMAGE_PIXELS, MediaTools, RenderProgress, RenderRequest, Result, Stage,
};
use std::collections::HashMap;
use std::fs;
use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, mpsc};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const LOCAL_PROTOCOLS: &str = "file,pipe";

pub trait EventSink: Send + Sync {
    fn stage(&self, _stage: Stage) {}
    fn progress(&self, _progress: RenderProgress) {}
    fn diagnostic(&self, _line: &str) {}
}

pub fn probe_audio_duration(tools: &MediaTools, path: &Path) -> Result<Option<f64>> {
    validate_file(path, "audio")?;
    let output = Command::new(&tools.ffprobe)
        .args([
            "-v",
            "error",
            "-protocol_whitelist",
            LOCAL_PROTOCOLS,
            "-select_streams",
            "a:0",
        ])
        .args([
            "-show_entries",
            "stream=duration:format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
        ])
        .arg(path)
        .stdin(Stdio::null())
        .output()
        .map_err(|error| AtivError::io("inspect the audio file", error))?;
    if !output.status.success() {
        return Err(AtivError::MediaToolFailed {
            tool: "ffprobe",
            detail: "The selected audio file may be damaged or unsupported.".into(),
        });
    }
    Ok(String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter_map(|line| line.trim().parse::<f64>().ok())
        .find(|value| value.is_finite() && *value > 0.0))
}

pub fn render_preview(
    tools: &MediaTools,
    image: &Path,
    output: &Path,
    width: u32,
    height: u32,
    flip_horizontal: bool,
    flip_vertical: bool,
) -> Result<()> {
    validate_dimensions(width, height)?;
    validate_image(tools, image)?;
    let parent = output
        .parent()
        .ok_or_else(|| AtivError::InvalidInput("Choose a valid preview destination.".into()))?;
    fs::create_dir_all(parent)
        .map_err(|error| AtivError::io("create the preview folder", error))?;
    let staged = staging_path(output, "preview", "png");
    let mut guard = StagedFile::new(staged.clone());
    let result = Command::new(&tools.ffmpeg)
        .args([
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-protocol_whitelist",
            LOCAL_PROTOCOLS,
            "-i",
        ])
        .arg(image)
        .args([
            "-filter_complex",
            &filter_graph(width, height, flip_horizontal, flip_vertical),
            "-map",
            "[video]",
            "-frames:v",
            "1",
            "-f",
            "image2",
        ])
        .arg(&staged)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .output()
        .map_err(|error| AtivError::io("start FFmpeg for the preview", error))?;
    if !result.status.success() {
        return Err(AtivError::MediaToolFailed {
            tool: "FFmpeg",
            detail: clean_failure(
                &result.stderr,
                "The selected image may be damaged or unsupported.",
            ),
        });
    }
    publish(&staged, output)?;
    guard.keep = true;
    Ok(())
}

pub fn render_video(
    tools: &MediaTools,
    request: &RenderRequest,
    cancelled: Arc<AtomicBool>,
    events: &dyn EventSink,
) -> Result<()> {
    events.stage(Stage::Validating);
    validate_request(request)?;
    check_output_aliases(request)?;
    validate_image(tools, &request.image)?;
    if cancelled.load(Ordering::SeqCst) {
        return Err(AtivError::Cancelled);
    }

    events.stage(Stage::Probing);
    let duration = probe_audio_duration(tools, &request.audio)?;
    let output_parent = request
        .output
        .parent()
        .ok_or_else(|| AtivError::InvalidInput("Choose a valid output destination.".into()))?;
    fs::create_dir_all(output_parent)
        .map_err(|error| AtivError::io("create the output folder", error))?;
    let staged = staging_path(&request.output, "render", "mp4");
    let mut guard = StagedFile::new(staged.clone());

    events.stage(Stage::Compositing);
    let mut command = Command::new(&tools.ffmpeg);
    command
        .args([
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-loop",
            "1",
            "-framerate",
        ])
        .arg(request.fps.to_string())
        .args(["-protocol_whitelist", LOCAL_PROTOCOLS, "-i"])
        .arg(&request.image)
        .args(["-protocol_whitelist", LOCAL_PROTOCOLS, "-i"])
        .arg(&request.audio)
        .args([
            "-filter_complex",
            &filter_graph(
                request.width,
                request.height,
                request.flip_horizontal,
                request.flip_vertical,
            ),
        ])
        .args([
            "-map",
            "[video]",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-tune",
            "stillimage",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
        ])
        .arg(&request.audio_bitrate)
        .args([
            "-shortest",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            "-progress",
            "pipe:1",
            "-nostats",
        ])
        .arg(&staged)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    events.stage(Stage::Encoding);
    let mut child = command
        .spawn()
        .map_err(|error| AtivError::io("start FFmpeg", error))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| AtivError::MediaToolFailed {
            tool: "FFmpeg",
            detail: "Diagnostic output was unavailable.".into(),
        })?;
    let stderr_thread = thread::spawn(move || read_stderr(stderr));
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| AtivError::MediaToolFailed {
            tool: "FFmpeg",
            detail: "Progress output was unavailable.".into(),
        })?;
    let (sender, receiver) = mpsc::sync_channel::<Option<String>>(256);
    let stdout_thread = thread::spawn(move || {
        for line in BufReader::new(stdout).lines() {
            match line {
                Ok(line) => {
                    if sender.send(Some(line)).is_err() {
                        return;
                    }
                }
                Err(_) => break,
            }
        }
        let _ = sender.send(None);
    });

    let monitor_result = monitor_ffmpeg(&mut child, receiver, &cancelled, duration, events);
    let stderr_tail = stderr_thread.join().unwrap_or_default();
    let _ = stdout_thread.join();
    for line in stderr_tail.lines() {
        events.diagnostic(line);
    }
    monitor_result?;
    let status = child
        .wait()
        .map_err(|error| AtivError::io("finish the FFmpeg process", error))?;
    if !status.success() {
        return Err(AtivError::MediaToolFailed {
            tool: "FFmpeg",
            detail: clean_failure(
                stderr_tail.as_bytes(),
                "The selected media may be damaged or unsupported.",
            ),
        });
    }
    if cancelled.load(Ordering::SeqCst) {
        return Err(AtivError::Cancelled);
    }

    events.stage(Stage::Publishing);
    publish(&staged, &request.output)?;
    guard.keep = true;
    events.stage(Stage::Complete);
    Ok(())
}

fn monitor_ffmpeg(
    child: &mut Child,
    receiver: mpsc::Receiver<Option<String>>,
    cancelled: &AtomicBool,
    duration: Option<f64>,
    events: &dyn EventSink,
) -> Result<()> {
    let mut values = HashMap::<String, String>::new();
    loop {
        if cancelled.load(Ordering::SeqCst) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(AtivError::Cancelled);
        }
        match receiver.recv_timeout(Duration::from_millis(100)) {
            Ok(Some(line)) => {
                events.diagnostic(&line);
                if let Some((key, value)) = line.split_once('=') {
                    values.insert(key.trim().into(), value.trim().into());
                    if key.trim() == "progress" {
                        events.progress(progress_from(&values, duration));
                    }
                }
            }
            Ok(None) => return Ok(()),
            Err(mpsc::RecvTimeoutError::Timeout) => {
                if child
                    .try_wait()
                    .map_err(|error| AtivError::io("check FFmpeg", error))?
                    .is_some()
                {
                    return Ok(());
                }
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => return Ok(()),
        }
    }
}

fn read_stderr(mut stderr: impl Read) -> String {
    let mut text = String::new();
    let _ = stderr.read_to_string(&mut text);
    text.lines()
        .rev()
        .take(30)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect::<Vec<_>>()
        .join("\n")
}

fn progress_from(values: &HashMap<String, String>, duration: Option<f64>) -> RenderProgress {
    let elapsed = values
        .get("out_time_us")
        .or_else(|| values.get("out_time_ms"))
        .and_then(|value| value.parse::<f64>().ok())
        .map(|value| value / 1_000_000.0)
        .filter(|value| value.is_finite() && *value >= 0.0)
        .or_else(|| {
            values
                .get("out_time")
                .and_then(|value| parse_timestamp(value))
        });
    let speed = values
        .get("speed")
        .and_then(|value| value.trim_end_matches('x').parse::<f64>().ok())
        .filter(|value| value.is_finite() && *value > 0.0);
    let fraction = elapsed
        .zip(duration)
        .map(|(elapsed, duration)| (elapsed / duration).clamp(0.0, 1.0));
    let eta_seconds = elapsed
        .zip(duration)
        .zip(speed)
        .map(|((elapsed, duration), speed)| ((duration - elapsed).max(0.0)) / speed);
    RenderProgress {
        elapsed_seconds: elapsed,
        duration_seconds: duration,
        fraction,
        eta_seconds,
    }
}

fn parse_timestamp(value: &str) -> Option<f64> {
    let mut total = 0.0;
    let parts: Vec<_> = value.trim().split(':').collect();
    if !(2..=3).contains(&parts.len()) {
        return None;
    }
    for part in parts {
        total = total * 60.0 + part.parse::<f64>().ok()?;
    }
    total.is_finite().then_some(total)
}

fn filter_graph(width: u32, height: u32, flip_horizontal: bool, flip_vertical: bool) -> String {
    let square = width.min(height);
    let flips = match (flip_horizontal, flip_vertical) {
        (true, true) => "hflip,vflip,",
        (true, false) => "hflip,",
        (false, true) => "vflip,",
        (false, false) => "",
    };
    format!(
        "[0:v]{flips}split=2[bgsrc][fgsrc];[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},gblur=sigma=40[bg];[fgsrc]scale={square}:{square}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[video]"
    )
}

fn validate_request(request: &RenderRequest) -> Result<()> {
    validate_file(&request.image, "image")?;
    validate_file(&request.audio, "audio")?;
    validate_dimensions(request.width, request.height)?;
    if request.fps == 0 || request.fps > 240 {
        return Err(AtivError::InvalidInput(
            "Frame rate must be between 1 and 240 FPS.".into(),
        ));
    }
    let bitrate = request.audio_bitrate.as_bytes();
    let suffix_ok = bitrate
        .last()
        .is_some_and(|value| matches!(value, b'k' | b'm' | b'b'));
    let digits = if suffix_ok {
        &bitrate[..bitrate.len().saturating_sub(1)]
    } else {
        bitrate
    };
    if digits.is_empty()
        || !digits.iter().all(u8::is_ascii_digit)
        || digits.iter().all(|value| *value == b'0')
    {
        return Err(AtivError::InvalidInput(
            "Audio bitrate must be a positive value such as 128k or 192k.".into(),
        ));
    }
    Ok(())
}

fn validate_file(path: &Path, kind: &str) -> Result<()> {
    if path.is_file() {
        Ok(())
    } else {
        Err(AtivError::InvalidInput(format!(
            "The selected {kind} file does not exist or is not a file."
        )))
    }
}

fn validate_dimensions(width: u32, height: u32) -> Result<()> {
    let pixels = u64::from(width) * u64::from(height);
    if width == 0 || height == 0 || width % 2 != 0 || height % 2 != 0 {
        return Err(AtivError::InvalidInput(
            "Output width and height must be positive even numbers.".into(),
        ));
    }
    if width > MAX_OUTPUT_DIMENSION || height > MAX_OUTPUT_DIMENSION || pixels > MAX_OUTPUT_PIXELS {
        return Err(AtivError::InvalidInput(
            "The requested output exceeds A.T.I.V.'s 8K safety limit.".into(),
        ));
    }
    Ok(())
}

fn validate_image(tools: &MediaTools, image: &Path) -> Result<()> {
    validate_file(image, "image")?;
    let output = Command::new(&tools.ffprobe)
        .args([
            "-v",
            "error",
            "-protocol_whitelist",
            LOCAL_PROTOCOLS,
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
        ])
        .arg(image)
        .stdin(Stdio::null())
        .output()
        .map_err(|error| AtivError::io("inspect the image", error))?;
    if !output.status.success() {
        return Err(AtivError::MediaToolFailed {
            tool: "ffprobe",
            detail: "The selected image may be damaged or unsupported.".into(),
        });
    }
    let dimensions = String::from_utf8_lossy(&output.stdout);
    let (width, height) = dimensions.trim().split_once('x').ok_or_else(|| {
        AtivError::InvalidInput("The selected file does not contain a readable image.".into())
    })?;
    let width = width.parse::<u32>().map_err(|_| {
        AtivError::InvalidInput("The selected image dimensions are invalid.".into())
    })?;
    let height = height.parse::<u32>().map_err(|_| {
        AtivError::InvalidInput("The selected image dimensions are invalid.".into())
    })?;
    if width > MAX_SOURCE_IMAGE_DIMENSION
        || height > MAX_SOURCE_IMAGE_DIMENSION
        || u64::from(width) * u64::from(height) > MAX_SOURCE_IMAGE_PIXELS
    {
        return Err(AtivError::InvalidInput(
            "The source image exceeds A.T.I.V.'s 50-megapixel safety limit.".into(),
        ));
    }
    Ok(())
}

fn check_output_aliases(request: &RenderRequest) -> Result<()> {
    if paths_refer_to_same_file(&request.image, &request.output)?
        || paths_refer_to_same_file(&request.audio, &request.output)?
    {
        return Err(AtivError::InvalidInput(
            "The output must be different from the image and audio inputs.".into(),
        ));
    }
    if request.output.exists() && !request.output.is_file() {
        return Err(AtivError::InvalidInput(
            "The output destination must be a file path.".into(),
        ));
    }
    Ok(())
}

fn paths_refer_to_same_file(left: &Path, right: &Path) -> Result<bool> {
    if left == right {
        return Ok(true);
    }
    if !right.exists() {
        return Ok(false);
    }
    let left_meta =
        fs::metadata(left).map_err(|error| AtivError::io("inspect an input file", error))?;
    let right_meta =
        fs::metadata(right).map_err(|error| AtivError::io("inspect the output file", error))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        Ok(left_meta.dev() == right_meta.dev() && left_meta.ino() == right_meta.ino())
    }
    #[cfg(not(unix))]
    {
        Ok(fs::canonicalize(left).ok() == fs::canonicalize(right).ok())
    }
}

fn staging_path(output: &Path, label: &str, extension: &str) -> PathBuf {
    let parent = output.parent().unwrap_or_else(|| Path::new("."));
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    parent.join(format!(
        ".ativ-{label}-{}-{stamp}.{extension}",
        std::process::id()
    ))
}

#[cfg(not(windows))]
fn publish(staged: &Path, output: &Path) -> Result<()> {
    fs::rename(staged, output).map_err(|error| AtivError::io("publish the completed output", error))
}

#[cfg(windows)]
fn publish(staged: &Path, output: &Path) -> Result<()> {
    if !output.exists() {
        return fs::rename(staged, output)
            .map_err(|error| AtivError::io("publish the completed output", error));
    }
    let backup = staging_path(output, "recovery", "bak");
    fs::rename(output, &backup)
        .map_err(|error| AtivError::io("protect the previous output", error))?;
    match fs::rename(staged, output) {
        Ok(()) => {
            let _ = fs::remove_file(backup);
            Ok(())
        }
        Err(error) => {
            let _ = fs::rename(&backup, output);
            Err(AtivError::io("publish the completed output", error))
        }
    }
}

fn clean_failure(bytes: &[u8], fallback: &str) -> String {
    let text = String::from_utf8_lossy(bytes);
    let last_line = text
        .lines()
        .rev()
        .find(|line| !line.trim().is_empty())
        .unwrap_or_default();
    if last_line.is_empty() {
        fallback.into()
    } else {
        format!("{fallback} See diagnostics for technical details.")
    }
}

struct StagedFile {
    path: PathBuf,
    keep: bool,
}
impl StagedFile {
    fn new(path: PathBuf) -> Self {
        Self { path, keep: false }
    }
}
impl Drop for StagedFile {
    fn drop(&mut self) {
        if !self.keep {
            let _ = fs::remove_file(&self.path);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn timestamp_parser_rejects_non_finite_values() {
        assert_eq!(parse_timestamp("00:01:02.5"), Some(62.5));
        assert_eq!(parse_timestamp("01:02"), Some(62.0));
        assert_eq!(parse_timestamp("nan"), None);
        assert_eq!(parse_timestamp("00:00:inf"), None);
    }

    #[test]
    fn filter_contains_expected_composition_and_flips() {
        let graph = filter_graph(1080, 1920, true, true);
        assert!(graph.contains("hflip,vflip"));
        assert!(graph.contains("gblur=sigma=40"));
        assert!(graph.contains("scale=1080:1080:force_original_aspect_ratio=decrease"));
        assert!(graph.ends_with("format=yuv420p[video]"));
    }

    #[test]
    fn dimensions_enforce_h264_and_resource_limits() {
        assert!(validate_dimensions(1920, 1080).is_ok());
        assert!(validate_dimensions(1919, 1080).is_err());
        assert!(validate_dimensions(8192, 8192).is_err());
    }
}
