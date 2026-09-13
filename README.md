# A.V.I.D. – Audio Visual Integration & Distribution

A.V.I.D. can be used as either a GUI or CLI. It builds a single composite frame from an image, then encodes a video using FFmpeg for the full duration of the audio.

## Context

This tool was built to support my students' media workflow. I am an instructor first, and I write code when it solves a practical problem in my classes or media environment.

The project is shared publicly under the GNU General Public License v3.0 (GPLv3) for transparency and educational use. It works for my systems and use case.

The software is provided as-is, without warranty or guaranteed support. I maintain it as needed for my own environment. Bug reports and pull requests are welcome, but response times may vary during the academic term.

## License

A.V.I.D. is licensed under the GNU General Public License v3.0 (GPLv3).

Why GPLv3 for this project:

- Forces derivatives to remain open.
- Prevents incorporation into proprietary systems.
- Requires source distribution if redistributed.
- Is widely respected in academic and technical communities.
- Sends a clear message: reciprocity matters.

## What it does

- Loads one image.
- Displays the selected audio file duration as confirmation before rendering.
- Creates a background layer by scaling the image to fill the full frame and applying a Gaussian blur radius of 40.
- Creates a foreground layer by scaling the image to fit inside a square based on the frame's smallest dimension.
- Centers the foreground on top of the blurred background.
- Uses FFmpeg to loop that composite frame for the full audio duration.
- Compresses audio with AAC.
- GUI presets for social media outlet, supported resolution, and matching aspect ratio.
- Prefers bundled FFmpeg/ffprobe binaries, then falls back to binaries installed on the system `PATH`.
- On launch, the GUI guides the user to current FFmpeg download pages if FFmpeg is missing.

## Setup

Python 3.10 or newer is required.

1. For source-based development, install FFmpeg or provide bundled FFmpeg/ffprobe binaries in the expected project paths. Packaged app releases include the required media binaries.
2. Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

### Bundled FFmpeg

A.V.I.D. looks for bundled FFmpeg and ffprobe binaries in common source and PyInstaller app-bundle locations, including:

- `ffmpeg/<platform>/<arch>/ffmpeg`
- `ffmpeg/<platform>/ffmpeg`
- `ffmpeg/ffmpeg`
- direct app resource paths such as `AVID.app/Contents/Resources/ffmpeg`
- direct app executable paths such as `AVID.app/Contents/MacOS/ffmpeg`

On Windows, the binary names must be `ffmpeg.exe` and `ffprobe.exe`.

If no bundled binary is found, A.V.I.D. uses `ffmpeg` and `ffprobe` from the system `PATH`.

Example bundle paths:

- `ffmpeg/darwin/arm64/ffmpeg`
- `ffmpeg/darwin/arm64/ffprobe`
- `ffmpeg/windows/x86_64/ffmpeg.exe`
- `ffmpeg/windows/x86_64/ffprobe.exe`
- `ffmpeg/linux/x86_64/ffmpeg`
- `ffmpeg/linux/x86_64/ffprobe`

To validate a release build before packaging:

```bash
python3 check_ffmpeg_bundle.py --require-bundled-ffmpeg
```

To validate for a different target:

```bash
python3 check_ffmpeg_bundle.py --platform windows --arch x86_64 --require-bundled-ffmpeg
```

### Release builds

Local macOS builds can be created with:

```bash
./build_macos_app.sh arm64
./build_macos_app.sh x86_64
```

The Intel macOS build requires an x86_64 Python/PyInstaller environment. The GitHub Actions workflow in `.github/workflows/build-packages.yml` builds native packages for macOS ARM64, macOS Intel, Windows x64, and Linux x64 on the appropriate runner platforms.

Tagged macOS releases require Developer ID signing and notarization. Configure the repository secrets `MACOS_CERTIFICATE_BASE64`, `MACOS_CERTIFICATE_PASSWORD`, `MACOS_SIGNING_IDENTITY`, `MACOS_NOTARY_APPLE_ID`, `MACOS_NOTARY_PASSWORD`, and `MACOS_NOTARY_TEAM_ID`. Manual workflow runs may still produce unsigned test packages. Local signed builds use `MACOS_SIGNING_IDENTITY` and a `notarytool` keychain profile named by `MACOS_NOTARY_PROFILE`; set `AVID_REQUIRE_SIGNED_RELEASE=1` to fail closed when either is missing.

## Usage

### GUI

```bash
python3 avid_gui.py
```

The GUI now uses platform-specific presets:

- `Social media outlet` filters the available aspect ratios.
- `Aspect ratio` filters the available resolutions.
- `Resolution` shows the valid sizes for the selected platform and aspect ratio.
- On launch, if FFmpeg is missing, A.V.I.D. shows the expected bundle path and offers to open platform-specific download pages.
- A live preview thumbnail shows the styled frame with the selected aspect ratio and composition treatment, without forced square letterboxing.
- The progress bar uses FFmpeg progress updates to show an approximate percentage and ETA.
- A collapsible FFmpeg console tray below the UI shows the exact command and live progress output.
- Horizontal and vertical flip controls update both the live preview and rendered video.
- The render button switches to a stop action immediately when rendering starts.

### CLI

```bash
python3 avid.py input.jpg input.wav output.mp4 --size 1080x1920
```

Check FFmpeg availability from the CLI:

```bash
python3 avid.py --check-ffmpeg
```

### Options

- `--size WIDTHxHEIGHT` output dimensions (default: `1080x1920`)
- `--flip-horizontal` flip image layers horizontally
- `--flip-vertical` flip image layers vertically
- `--audio-bitrate` AAC bitrate, e.g. `96k`, `128k`, `192k` (default: `128k`)
- `--fps` video fps (default: `30`)

For predictable memory use, source images are limited to 32,768 pixels per axis and 50 million pixels total. Output is limited to 8,192 pixels per axis and 33,177,600 pixels total (8K UHD). FFmpeg and ffprobe are restricted to local file and pipe protocols while reading selected media.

### Example

```bash
python3 avid.py photo.png voice.wav result.mp4 --size 1920x1080 --flip-horizontal --audio-bitrate 96k
```
