# Legacy Python behavior reference

The validated Python baseline is commit `c97aab7` and remains runnable from `legacy-python/`.

## Workflow

1. Select one local image and one local audio file.
2. Choose a social outlet, aspect ratio, and matching resolution.
3. Optionally flip the image horizontally or vertically and adjust AAC bitrate/FPS.
4. Preview a centered sharp foreground over a blurred, aspect-filled background.
5. Choose an MP4 destination, start encoding, follow progress/ETA, or cancel.

The default selection is Instagram, horizontal 16:9, 1920×1080, 128k AAC, and 30 FPS. The output suggestion follows the selected audio filename, falling back to the image filename. Existing outputs survive failures and cancellation.

The legacy app has one utility window, an expandable FFmpeg console, native file dialogs through Tk, no application-specific menus, and no persistent user settings. It accepts PNG, JPEG, WebP, BMP, and TIFF images plus WAV, MP3, M4A, AAC, FLAC, Ogg, and Opus audio through FFmpeg-supported local formats.

## Verified baseline

- 59 Python tests pass on macOS ARM64.
- The source GUI launches and detects `/opt/homebrew/bin/ffmpeg`.
- GitHub listed no open issues at rewrite start.
- Legacy packaging used PyInstaller and bundled FFmpeg/ffprobe on macOS, Windows x64, and Linux x64.

The original UI was inspected before implementation. Its primary window is a two-column form and preview with a collapsible console.
