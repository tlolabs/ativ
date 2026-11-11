use crate::{
    command::{self, os},
    process::{run, RunOptions},
    storage::{self, StagedOutput},
    CancellationToken, Capabilities, Encoding, Error, EventSink, Input, MediaTools, PreviewRequest,
    RenderMode, RenderRequest, Result, Stage, MAX_SOURCE_IMAGE_DIMENSION, MAX_SOURCE_IMAGE_PIXELS,
};
use std::{
    collections::{HashMap, HashSet},
    path::{Path, PathBuf},
    sync::{Arc, RwLock},
    time::{Duration, SystemTime},
};

#[derive(Clone, Copy, Hash, PartialEq, Eq, Debug)]
struct FileFingerprint {
    len: u64,
    modified: SystemTime,
    #[cfg(unix)]
    dev: u64,
    #[cfg(unix)]
    ino: u64,
    #[cfg(unix)]
    ctime: i64,
    #[cfg(unix)]
    ctime_nsec: i64,
}

impl FileFingerprint {
    #[cfg(unix)]
    fn from_path(path: &Path) -> Option<Self> {
        let meta = std::fs::metadata(path).ok()?;
        let modified = meta.modified().ok()?;
        #[cfg(unix)]
        use std::os::unix::fs::MetadataExt;
        Some(Self {
            len: meta.len(),
            modified,
            #[cfg(unix)]
            dev: meta.dev(),
            #[cfg(unix)]
            ino: meta.ino(),
            #[cfg(unix)]
            ctime: meta.ctime(),
            #[cfg(unix)]
            ctime_nsec: meta.ctime_nsec(),
        })
    }

    #[cfg(not(unix))]
    fn from_path(_path: &Path) -> Option<Self> {
        // Length/mtime and Windows creation time can survive file replacement.
        // Without a reliable replacement-sensitive identity, probe fresh rather
        // than return dimensions or duration belonging to the previous file.
        None
    }
}

type ProbeEntry<T> = (FileFingerprint, T);

#[derive(Default, Debug)]
struct ProbeCache {
    images: RwLock<HashMap<PathBuf, ProbeEntry<(u32, u32)>>>,
    durations: RwLock<HashMap<PathBuf, ProbeEntry<Option<f64>>>>,
}

impl ProbeCache {
    fn get_image(&self, path: &Path, fp: FileFingerprint) -> Option<(u32, u32)> {
        self.images
            .read()
            .ok()?
            .get(path)
            .and_then(|(cached_fp, value)| (*cached_fp == fp).then_some(*value))
    }
    fn insert_image(&self, path: PathBuf, fp: FileFingerprint, dims: (u32, u32)) {
        if let Ok(mut map) = self.images.write() {
            if map.len() >= 1024 && !map.contains_key(&path) {
                map.clear();
            }
            map.insert(path, (fp, dims));
        }
    }
    fn get_duration(&self, path: &Path, fp: FileFingerprint) -> Option<Option<f64>> {
        self.durations
            .read()
            .ok()?
            .get(path)
            .and_then(|(cached_fp, value)| (*cached_fp == fp).then_some(*value))
    }
    fn insert_duration(&self, path: PathBuf, fp: FileFingerprint, duration: Option<f64>) {
        if let Ok(mut map) = self.durations.write() {
            if map.len() >= 1024 && !map.contains_key(&path) {
                map.clear();
            }
            map.insert(path, (fp, duration));
        }
    }
}

#[derive(Clone, Debug)]
pub struct OperationOptions {
    /// Per probe/capability process; defaults to 30 seconds.
    pub probe_timeout: Option<Duration>,
    /// Per preview process; defaults to 120 seconds.
    pub preview_timeout: Option<Duration>,
    /// Per encoding attempt; defaults to no limit for long media jobs.
    pub render_timeout: Option<Duration>,
}
impl Default for OperationOptions {
    fn default() -> Self {
        Self {
            probe_timeout: Some(Duration::from_secs(30)),
            preview_timeout: Some(Duration::from_secs(120)),
            render_timeout: None,
        }
    }
}
/// Immutable configuration. Operations block the caller; use a dedicated host worker thread.
/// Independent calls can run concurrently. Hosts must serialize calls targeting the same output.
#[derive(Clone, Debug)]
pub struct Renderer {
    tools: MediaTools,
    options: OperationOptions,
    probe_cache: Arc<ProbeCache>,
}
impl Renderer {
    pub fn new(tools: MediaTools) -> Self {
        Self {
            tools,
            options: OperationOptions::default(),
            probe_cache: Arc::new(ProbeCache::default()),
        }
    }
    pub fn with_options(mut self, options: OperationOptions) -> Self {
        self.options = options;
        self
    }
    pub fn tools(&self) -> &MediaTools {
        &self.tools
    }
    fn probe(
        &self,
        args: &[std::ffi::OsString],
        token: &CancellationToken,
        operation: &'static str,
    ) -> Result<Vec<u8>> {
        run(
            self.tools.ffprobe(),
            args,
            token,
            RunOptions {
                operation,
                timeout: self.options.probe_timeout,
                progress_duration: None,
                parse_progress: false,
                events: &(),
            },
        )
    }
    pub fn probe_audio_duration(
        &self,
        path: &Path,
        token: &CancellationToken,
    ) -> Result<Option<f64>> {
        token.check()?;
        storage::file(path)?;
        let path = storage::absolute(path)?;
        let fp = FileFingerprint::from_path(&path);
        if let Some(fp) = fp {
            if let Some(cached) = self.probe_cache.get_duration(&path, fp) {
                return Ok(cached);
            }
        }
        let args = [
            os("-v"),
            os("error"),
            os("-protocol_whitelist"),
            os("file,pipe"),
            os("-select_streams"),
            os("a:0"),
            os("-show_entries"),
            os("stream=duration:format=duration"),
            os("-of"),
            os("default=noprint_wrappers=1:nokey=1"),
            os(&path),
        ];
        let output = self.probe(&args, token, "probe audio duration")?;
        let duration = parse_duration(&output);
        if let Some(fp) = fp {
            self.probe_cache.insert_duration(path, fp, duration);
        }
        Ok(duration)
    }
    pub fn inspect_image(&self, path: &Path, token: &CancellationToken) -> Result<(u32, u32)> {
        token.check()?;
        storage::file(path)?;
        let path = storage::absolute(path)?;
        let fp = FileFingerprint::from_path(&path);
        if let Some(fp) = fp {
            if let Some(cached) = self.probe_cache.get_image(&path, fp) {
                return Ok(cached);
            }
        }
        let args = [
            os("-v"),
            os("error"),
            os("-protocol_whitelist"),
            os("file,pipe"),
            os("-select_streams"),
            os("v:0"),
            os("-show_entries"),
            os("stream=width,height"),
            os("-of"),
            os("csv=p=0:s=x"),
            os(&path),
        ];
        let output = self.probe(&args, token, "inspect artwork")?;
        let dims = parse_image(&output)?;
        if let Some(fp) = fp {
            self.probe_cache.insert_image(path, fp, dims);
        }
        Ok(dims)
    }
    pub fn capabilities(&self, token: &CancellationToken) -> Result<Capabilities> {
        token.check()?;
        if let Some(cached) = self.tools.cached_capabilities() {
            return Ok(cached);
        }
        let output = run(
            self.tools.ffmpeg(),
            &[os("-hide_banner"), os("-encoders")],
            token,
            RunOptions {
                operation: "detect video encoders",
                timeout: self.options.probe_timeout,
                progress_duration: None,
                parse_progress: false,
                events: &(),
            },
        )?;
        let caps = command::parse_capabilities(&String::from_utf8_lossy(&output));
        self.tools.cache_capabilities(caps.clone());
        Ok(caps)
    }
    fn square_pixel_args(
        &self,
        args: &mut [std::ffi::OsString],
        token: &CancellationToken,
    ) -> Result<()> {
        token.check()?;
        let use_scale = if let Some(value) = self.tools.cached_scale_reset_sar() {
            value
        } else {
            let inspect = |arguments: &[std::ffi::OsString]| {
                run(
                    self.tools.ffmpeg(),
                    arguments,
                    token,
                    RunOptions {
                        operation: "detect artwork pixel normalization",
                        timeout: self.options.probe_timeout,
                        progress_duration: None,
                        parse_progress: false,
                        events: &(),
                    },
                )
            };
            let filters = inspect(&[os("-hide_banner"), os("-filters")])?;
            let has_setsar = String::from_utf8_lossy(&filters).lines().any(|line| {
                let mut fields = line.split_whitespace();
                fields.next().is_some_and(|flags| flags.len() == 3)
                    && fields.next() == Some("setsar")
            });
            let use_scale = !has_setsar;
            if use_scale {
                // Minimal Recipe 7 omits setsar; modern scale offers the same
                // normalization. Older full builds retain their setsar path.
                let help = inspect(&[os("-hide_banner"), os("-h"), os("filter=scale")])?;
                if !String::from_utf8_lossy(&help)
                    .lines()
                    .any(|line| line.split_whitespace().next() == Some("reset_sar"))
                {
                    return Err(Error::InvalidInput(
                        "FFmpeg needs the setsar filter or scale reset_sar for square-pixel artwork".into()
                    ));
                }
            }
            self.tools.cache_scale_reset_sar(use_scale);
            use_scale
        };
        if use_scale {
            if let Some(index) = args.iter().position(|arg| arg == "-filter_complex") {
                if let Some(graph) = args.get_mut(index + 1) {
                    *graph = os(graph
                        .to_string_lossy()
                        .replace(",setsar=1[", ",scale=iw:ih:reset_sar=1["));
                }
            }
        }
        Ok(())
    }

    pub fn preview(
        &self,
        request: &PreviewRequest,
        token: &CancellationToken,
        events: &dyn EventSink,
    ) -> Result<PathBuf> {
        token.check()?;
        events.stage(Stage::Validating);
        crate::model::validate_dimensions(request.settings.width, request.settings.height)?;
        let image = storage::absolute(&request.image)?;
        let output = storage::absolute(&request.output)?;
        let mut protected = request.protected_paths.clone();
        protected.push(image.clone());
        storage::protect(&output, &protected)?;
        events.stage(Stage::Probing);
        self.inspect_image(&image, token)?;
        let staged = StagedOutput::new(&output, ".png")?;
        let mut args = command::preview(&image, staged.path(), &request.settings);
        self.square_pixel_args(&mut args, token)?;
        events.stage(Stage::Compositing);
        run(
            self.tools.ffmpeg(),
            &args,
            token,
            RunOptions {
                operation: "render preview",
                timeout: self.options.preview_timeout,
                progress_duration: None,
                parse_progress: false,
                events,
            },
        )?;
        token.check()?;
        storage::protect(&output, &protected)?;
        events.stage(Stage::Publishing);
        token.check()?;
        staged.publish(&output)?;
        events.stage(Stage::Complete);
        Ok(request.output.clone())
    }
    pub fn render(
        &self,
        request: &RenderRequest,
        token: &CancellationToken,
        events: &dyn EventSink,
    ) -> Result<PathBuf> {
        self.render_with_mode(request, RenderMode::PerFrame, token, events)
    }
    /// Simple mode caches the composed first frame of each clip in FFmpeg memory.
    /// Uses the same validation, staging, progress, cancellation and encoder fallback as render.
    pub fn render_with_mode(
        &self,
        request: &RenderRequest,
        mode: RenderMode,
        token: &CancellationToken,
        events: &dyn EventSink,
    ) -> Result<PathBuf> {
        token.check()?;
        events.stage(Stage::Validating);
        request.settings.validate()?;
        let mut request = request.clone();
        let original_output = request.output.clone();
        request.output = storage::absolute(&request.output)?;
        let mut images = Vec::new();
        let mut protected = request.protected_paths.clone();
        match &mut request.input {
            Input::Single { image, audio } => {
                *image = storage::absolute(image)?;
                *audio = storage::absolute(audio)?;
                storage::file(image)?;
                storage::file(audio)?;
                images.push(image.clone());
                protected.extend([image.clone(), audio.clone()]);
            }
            Input::Timeline(timeline) => {
                if timeline.clips().is_empty() {
                    return Err(Error::InvalidInput(
                        "Select at least one clip for video export".into(),
                    ));
                }
                if request
                    .output
                    .extension()
                    .and_then(|v| v.to_str())
                    .is_none_or(|v| !v.eq_ignore_ascii_case("mp4"))
                {
                    return Err(Error::InvalidInput(
                        "Timeline export destination must use .mp4".into(),
                    ));
                }
                let mut clips = timeline.clips().to_vec();
                for clip in &mut clips {
                    clip.image = storage::absolute(&clip.image)?;
                    clip.audio = storage::absolute(&clip.audio)?;
                    storage::file(&clip.image)?;
                    storage::file(&clip.audio)?;
                    images.push(clip.image.clone());
                    protected.extend([clip.image.clone(), clip.audio.clone()]);
                }
                *timeline = crate::Timeline::new(clips)?;
            }
        }
        storage::protect(&request.output, &protected)?;
        events.stage(Stage::Probing);
        let mut checked = HashSet::new();
        let unique_images: Vec<_> = images
            .into_iter()
            .filter(|image| checked.insert(image.clone()))
            .collect();
        inspect_images_with(&unique_images, token, &|image, token| {
            self.inspect_image(image, token).map(|_| ())
        })?;
        let duration = match &request.input {
            Input::Single { audio, .. } => self.probe_audio_duration(audio, token)?,
            Input::Timeline(t) => Some(t.duration_seconds()),
        };
        let capabilities = self.capabilities(token)?;
        let encoder = command::select_encoder(
            request.settings.codec,
            request.settings.encoding,
            &capabilities,
        )?;
        let staged = StagedOutput::new(&request.output, ".mp4")?;
        events.stage(Stage::Compositing);
        let encode = |encoder: &str| -> Result<()> {
            let mut args =
                command::export_with_mode(&request, encoder, staged.path(), mode, duration)?;
            self.square_pixel_args(&mut args, token)?;
            events.stage(Stage::Encoding);
            run(
                self.tools.ffmpeg(),
                &args,
                token,
                RunOptions {
                    operation: "encode video",
                    timeout: self.options.render_timeout,
                    progress_duration: duration,
                    parse_progress: true,
                    events,
                },
            )?;
            Ok(())
        };
        if let Err(hardware) = encode(&encoder) {
            let retry = request.settings.encoding == Encoding::Automatic
                && !encoder.starts_with("libx")
                && matches!(hardware, Error::Process { .. });
            if !retry {
                return Err(hardware);
            }
            token.check()?;
            events.diagnostic("Automatic hardware encoding failed; retrying with software");
            let software =
                command::select_encoder(request.settings.codec, Encoding::Software, &capabilities)
                    .and_then(|name| encode(&name));
            if let Err(software) = software {
                if matches!(software, Error::Cancelled) {
                    return Err(software);
                }
                return Err(Error::Fallback {
                    hardware: Box::new(hardware),
                    software: Box::new(software),
                });
            }
        }
        token.check()?;
        storage::protect(&request.output, &protected)?;
        events.stage(Stage::Publishing);
        token.check()?;
        staged.publish(&request.output)?;
        events.stage(Stage::Complete);
        Ok(original_output)
    }
}
fn inspect_images_with(
    images: &[PathBuf],
    token: &CancellationToken,
    inspect: &(impl Fn(&Path, &CancellationToken) -> Result<()> + Sync),
) -> Result<()> {
    if images.len() <= 1 {
        for image in images {
            token.check()?;
            inspect(image, token)?;
        }
        return Ok(());
    }

    std::thread::scope(|scope| {
        for batch in images.chunks(4) {
            token.check()?;
            let mut workers = Vec::with_capacity(batch.len());
            let mut start_error = None;
            for image in batch {
                if let Err(error) = token.check() {
                    start_error = Some(error);
                    break;
                }
                match std::thread::Builder::new()
                    .name("avid-artwork-probe".into())
                    .spawn_scoped(scope, || inspect(image, token))
                {
                    Ok(worker) => workers.push((image, worker)),
                    Err(error) => {
                        start_error = Some(Error::io("start artwork probe worker", image, error));
                        break;
                    }
                }
            }

            let mut worker_error = None;
            for (image, worker) in workers {
                let result = worker.join().unwrap_or_else(|_| {
                    Err(Error::InvalidInput(format!(
                        "Image probe thread panicked: {}",
                        image.display()
                    )))
                });
                if let Err(error) = result {
                    worker_error.get_or_insert(error);
                }
            }
            if let Some(error) = worker_error.or(start_error) {
                return Err(error);
            }
        }
        Ok(())
    })
}

fn parse_duration(bytes: &[u8]) -> Option<f64> {
    String::from_utf8_lossy(bytes)
        .lines()
        .filter_map(|line| line.trim().parse::<f64>().ok())
        .find(|v| v.is_finite() && *v > 0.0)
}
fn parse_image(bytes: &[u8]) -> Result<(u32, u32)> {
    let text = String::from_utf8_lossy(bytes);
    let (w, h) = text
        .trim()
        .split_once('x')
        .and_then(|(w, h)| Some((w.parse::<u32>().ok()?, h.parse::<u32>().ok()?)))
        .ok_or_else(|| Error::InvalidInput("Artwork has no readable dimensions".into()))?;
    if w == 0
        || h == 0
        || w > MAX_SOURCE_IMAGE_DIMENSION
        || h > MAX_SOURCE_IMAGE_DIMENSION
        || u64::from(w) * u64::from(h) > MAX_SOURCE_IMAGE_PIXELS
    {
        return Err(Error::InvalidInput(
            "Artwork exceeds the 32,768-axis / 50-megapixel safety limit or has zero dimensions"
                .into(),
        ));
    }
    Ok((w, h))
}
#[cfg(test)]
mod tests {
    use super::*;

    fn cache_fingerprint() -> FileFingerprint {
        FileFingerprint {
            len: 100,
            modified: SystemTime::UNIX_EPOCH,
            #[cfg(unix)]
            dev: 1,
            #[cfg(unix)]
            ino: 2,
            #[cfg(unix)]
            ctime: 3,
            #[cfg(unix)]
            ctime_nsec: 4,
        }
    }

    #[test]
    fn probe_cache_checks_full_identity_and_preserves_unknown_duration() {
        let cache = ProbeCache::default();
        let path = Path::new("artwork");
        let fp = cache_fingerprint();
        cache.insert_image(path.to_owned(), fp, (640, 480));
        cache.insert_duration(path.to_owned(), fp, None);
        assert_eq!(cache.get_image(path, fp), Some((640, 480)));
        assert_eq!(cache.get_duration(path, fp), Some(None));

        let changed = [
            FileFingerprint {
                len: fp.len + 1,
                ..fp
            },
            FileFingerprint {
                modified: fp.modified + Duration::from_nanos(1),
                ..fp
            },
            #[cfg(unix)]
            FileFingerprint {
                dev: fp.dev + 1,
                ..fp
            },
            #[cfg(unix)]
            FileFingerprint {
                ino: fp.ino + 1,
                ..fp
            },
            #[cfg(unix)]
            FileFingerprint {
                ctime: fp.ctime + 1,
                ..fp
            },
            #[cfg(unix)]
            FileFingerprint {
                ctime_nsec: fp.ctime_nsec + 1,
                ..fp
            },
        ];
        for different in changed {
            assert_eq!(cache.get_image(path, different), None);
            assert_eq!(cache.get_duration(path, different), None);
        }

        let replacement = changed[0];
        cache.insert_image(path.to_owned(), replacement, (1920, 1080));
        cache.insert_duration(path.to_owned(), replacement, Some(12.5));
        assert_eq!(cache.get_image(path, fp), None);
        assert_eq!(cache.get_duration(path, fp), None);
        assert_eq!(cache.get_image(path, replacement), Some((1920, 1080)));
        assert_eq!(cache.get_duration(path, replacement), Some(Some(12.5)));
    }

    #[test]
    fn repeated_source_replacements_retain_unrelated_cached_probes_at_capacity() {
        let cache = ProbeCache::default();
        let fp = cache_fingerprint();
        for index in 0..1024 {
            let path = PathBuf::from(format!("artwork-{index}"));
            cache.insert_image(path.clone(), fp, (640, 480));
            cache.insert_duration(path, fp, Some(index as f64));
        }

        let changing = Path::new("artwork-0");
        let unrelated = Path::new("artwork-1023");
        let mut latest = fp;
        for generation in 1..=2048 {
            latest = FileFingerprint {
                len: fp.len + generation,
                ..fp
            };
            cache.insert_image(changing.to_owned(), latest, (1920, 1080));
            cache.insert_duration(changing.to_owned(), latest, None);
        }
        assert_eq!(cache.get_image(unrelated, fp), Some((640, 480)));
        assert_eq!(cache.get_duration(unrelated, fp), Some(Some(1023.0)));
        assert_eq!(cache.get_image(changing, fp), None);
        assert_eq!(cache.get_duration(changing, fp), None);
        assert_eq!(cache.get_image(changing, latest), Some((1920, 1080)));
        assert_eq!(cache.get_duration(changing, latest), Some(None));
        assert_eq!(cache.images.read().unwrap().len(), 1024);
        assert_eq!(cache.durations.read().unwrap().len(), 1024);

        let additional = Path::new("new-artwork");
        cache.insert_image(additional.to_owned(), fp, (1280, 720));
        cache.insert_duration(additional.to_owned(), fp, Some(5.0));
        assert_eq!(cache.images.read().unwrap().len(), 1);
        assert_eq!(cache.durations.read().unwrap().len(), 1);
        assert_eq!(cache.get_image(additional, fp), Some((1280, 720)));
        assert_eq!(cache.get_duration(additional, fp), Some(Some(5.0)));
        assert_eq!(cache.get_image(unrelated, fp), None);
        assert_eq!(cache.get_duration(unrelated, fp), None);
    }

    #[cfg(not(unix))]
    #[test]
    fn probe_cache_is_bypassed_without_replacement_sensitive_identity() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("art.png");
        std::fs::write(&path, b"image").unwrap();
        assert!(std::fs::metadata(&path).unwrap().modified().is_ok());
        assert!(FileFingerprint::from_path(&path).is_none());
    }

    use std::sync::atomic::{AtomicUsize, Ordering};

    struct Completion<'a>(&'a AtomicUsize);
    impl Drop for Completion<'_> {
        fn drop(&mut self) {
            self.0.fetch_add(1, Ordering::SeqCst);
        }
    }

    #[test]
    fn probe_parsing_preserves_duration_fallback_and_limits() {
        assert_eq!(parse_duration(b"N/A\nNaN\n-1\n0\n2.5\n3\n"), Some(2.5));
        assert_eq!(parse_duration(b"inf\nN/A"), None);
        assert_eq!(parse_image(b"640x480\n").unwrap(), (640, 480));
        for bad in ["0x1", "8192x8192", "32769x1", "N/A", "2x2\n2x2"] {
            assert!(parse_image(bad.as_bytes()).is_err());
        }
    }

    #[test]
    fn image_inspection_handles_empty_single_and_cancelled_inputs() {
        let token = CancellationToken::default();
        let calls = AtomicUsize::new(0);
        assert!(inspect_images_with(&[], &token, &|_, _| {
            calls.fetch_add(1, Ordering::SeqCst);
            Ok(())
        })
        .is_ok());
        assert!(
            inspect_images_with(&[PathBuf::from("one")], &token, &|_, _| {
                calls.fetch_add(1, Ordering::SeqCst);
                Err(Error::InvalidInput("probe failed".into()))
            })
            .is_err()
        );
        assert_eq!(calls.load(Ordering::SeqCst), 1);

        token.cancel();
        assert!(matches!(
            inspect_images_with(&[PathBuf::from("one")], &token, &|_, _| Ok(())),
            Err(Error::Cancelled)
        ));
    }

    #[test]
    fn image_probe_workers_are_bounded_and_all_joined_on_failure_or_panic() {
        use std::{thread, time::Duration};

        let active = AtomicUsize::new(0);
        let maximum = AtomicUsize::new(0);
        let calls = AtomicUsize::new(0);
        let images: Vec<_> = (0..9)
            .map(|index| PathBuf::from(format!("image-{index}")))
            .collect();
        let result = inspect_images_with(&images, &CancellationToken::default(), &|_, _| {
            let current = active.fetch_add(1, Ordering::SeqCst) + 1;
            maximum.fetch_max(current, Ordering::SeqCst);
            calls.fetch_add(1, Ordering::SeqCst);
            thread::sleep(Duration::from_millis(5));
            active.fetch_sub(1, Ordering::SeqCst);
            Ok(())
        });
        assert!(result.is_ok());
        assert_eq!(calls.load(Ordering::SeqCst), 9);
        assert!((1..=4).contains(&maximum.load(Ordering::SeqCst)));
        assert_eq!(active.load(Ordering::SeqCst), 0);

        for panic_worker in [false, true] {
            let calls = AtomicUsize::new(0);
            let completed = AtomicUsize::new(0);
            let token = CancellationToken::default();
            let result = inspect_images_with(&images, &token, &|image, _| {
                calls.fetch_add(1, Ordering::SeqCst);
                let _completion = Completion(&completed);
                if image == Path::new("image-0") {
                    if panic_worker {
                        panic!("probe worker panic");
                    }
                    Err(Error::InvalidInput("probe failed".into()))
                } else {
                    Ok(())
                }
            });
            assert!(result.is_err(), "panic_worker={panic_worker}");
            assert_eq!(calls.load(Ordering::SeqCst), 4);
            assert_eq!(completed.load(Ordering::SeqCst), 4);
            assert!(!token.is_cancelled());
        }
    }

    #[test]
    fn image_probe_cancellation_joins_started_workers_and_keeps_other_tokens_independent() {
        let images: Vec<_> = (0..9)
            .map(|index| PathBuf::from(format!("image-{index}")))
            .collect();
        let calls = AtomicUsize::new(0);
        let completed = AtomicUsize::new(0);
        let token = CancellationToken::default();
        let result = inspect_images_with(&images, &token, &|_, token| {
            calls.fetch_add(1, Ordering::SeqCst);
            let _completion = Completion(&completed);
            token.cancel();
            token.check()
        });
        assert!(matches!(result, Err(Error::Cancelled)));
        let started = calls.load(Ordering::SeqCst);
        assert!((1..=4).contains(&started));
        assert_eq!(completed.load(Ordering::SeqCst), started);

        let independent = CancellationToken::default();
        let independent_calls = AtomicUsize::new(0);
        let result = inspect_images_with(&images, &independent, &|_, token| {
            independent_calls.fetch_add(1, Ordering::SeqCst);
            token.check()
        });
        assert!(result.is_ok());
        assert_eq!(independent_calls.load(Ordering::SeqCst), images.len());
        assert!(!independent.is_cancelled());
    }
}
