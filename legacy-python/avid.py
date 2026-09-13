#!/usr/bin/env python3
# Copyright (C) 2026 Tom Lothian
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
import argparse
import math
import os
import platform
import queue
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps


FFMPEG_DOWNLOAD_PAGES = {
    "Darwin": [
        "https://ffmpeg.org/download.html#build-mac",
        "https://evermeet.cx/ffmpeg/",
    ],
    "Windows": [
        "https://ffmpeg.org/download.html#build-windows",
        "https://www.gyan.dev/ffmpeg/builds/",
    ],
    "Linux": [
        "https://ffmpeg.org/download.html#build-linux",
        "https://johnvansickle.com/ffmpeg/",
    ],
}

MAX_SOURCE_IMAGE_DIMENSION = 32_768
MAX_SOURCE_IMAGE_PIXELS = 50_000_000
MAX_OUTPUT_DIMENSION = 8_192
MAX_OUTPUT_PIXELS = 33_177_600  # 8K UHD: 7680 x 4320
LOCAL_MEDIA_PROTOCOLS = "file,pipe"


class RenderCancelledError(RuntimeError):
    pass


class FFmpegExecutionError(RuntimeError):
    def __init__(self, returncode: int, command: list[str], output: str) -> None:
        self.returncode = returncode
        self.command = command
        self.output = output
        message = f"FFmpeg failed with exit code {returncode}."
        if output:
            message += f"\n\nLast FFmpeg output:\n{output}"
        super().__init__(message)


def parse_size(size_text: str) -> tuple[int, int]:
    if "x" not in size_text.lower():
        raise argparse.ArgumentTypeError("Size must be in WIDTHxHEIGHT format (example: 1080x1920)")
    raw_w, raw_h = size_text.lower().split("x", 1)
    try:
        width = int(raw_w)
        height = int(raw_h)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Width and height must be integers") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("Width and height must be positive")
    if width % 2 or height % 2:
        raise argparse.ArgumentTypeError("Width and height must be even numbers for H.264 video")
    if width > MAX_OUTPUT_DIMENSION or height > MAX_OUTPUT_DIMENSION or width * height > MAX_OUTPUT_PIXELS:
        raise argparse.ArgumentTypeError(
            f"Output size exceeds the {MAX_OUTPUT_DIMENSION}px / {MAX_OUTPUT_PIXELS:,}-pixel safety limit"
        )
    return width, height


def current_platform() -> str:
    return platform.system()


def current_architecture() -> str:
    machine = platform.machine().lower()
    aliases = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    return aliases.get(machine, machine or "unknown")


def ffmpeg_binary_name() -> str:
    return "ffmpeg.exe" if current_platform() == "Windows" else "ffmpeg"


def ffprobe_binary_name() -> str:
    return "ffprobe.exe" if current_platform() == "Windows" else "ffprobe"


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_base_dirs() -> list[Path]:
    base_dir = app_base_dir()
    candidates = [
        base_dir,
        base_dir.parent / "Resources",
        base_dir.parent / "Frameworks",
        Path(getattr(sys, "_MEIPASS", base_dir)),
        Path(__file__).resolve().parent,
    ]
    unique_candidates = []
    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_candidates.append(resolved)
    return unique_candidates


def bundled_ffmpeg_candidates() -> list[Path]:
    binary_name = ffmpeg_binary_name()
    arch = current_architecture()
    candidates = []
    for base_dir in resource_base_dirs():
        candidates.extend(
            [
                base_dir / "ffmpeg" / current_platform().lower() / arch / binary_name,
                base_dir / "ffmpeg" / current_platform().lower() / binary_name,
                base_dir / "ffmpeg" / binary_name,
                base_dir / binary_name,
            ]
        )
    return candidates


def bundled_ffprobe_candidates() -> list[Path]:
    binary_name = ffprobe_binary_name()
    arch = current_architecture()
    candidates = []
    for base_dir in resource_base_dirs():
        candidates.extend(
            [
                base_dir / "ffmpeg" / current_platform().lower() / arch / binary_name,
                base_dir / "ffmpeg" / current_platform().lower() / binary_name,
                base_dir / "ffmpeg" / binary_name,
                base_dir / binary_name,
            ]
        )
    return candidates


def bundled_ffmpeg_path() -> Path | None:
    for candidate in bundled_ffmpeg_candidates():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def bundled_ffprobe_path() -> Path | None:
    for candidate in bundled_ffprobe_candidates():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def find_ffmpeg() -> tuple[str | None, str | None]:
    bundled = bundled_ffmpeg_path()
    if bundled is not None:
        return str(bundled), "bundled"

    system_binary = shutil.which(ffmpeg_binary_name())
    if system_binary is not None:
        return system_binary, "system"

    return None, None


def find_ffprobe() -> tuple[str | None, str | None]:
    bundled = bundled_ffprobe_path()
    if bundled is not None:
        return str(bundled), "bundled"

    system_binary = shutil.which(ffprobe_binary_name())
    if system_binary is not None:
        return system_binary, "system"

    return None, None


def ensure_ffmpeg() -> str:
    ffmpeg_path, _source = find_ffmpeg()
    if ffmpeg_path is None:
        platform_name = current_platform()
        arch = current_architecture()
        bundle_target = bundled_ffmpeg_candidates()[0]
        raise RuntimeError(
            "FFmpeg is not available.\n"
            f"Platform: {platform_name} ({arch})\n"
            f"Expected bundled binary: {bundle_target}\n"
            "Install FFmpeg system-wide or rebuild A.V.I.D. with a bundled platform-specific binary."
        )
    return ffmpeg_path


def ensure_ffprobe() -> str:
    ffprobe_path, _source = find_ffprobe()
    if ffprobe_path is None:
        raise RuntimeError("ffprobe is not available. Install or bundle ffprobe alongside ffmpeg.")
    return ffprobe_path


def ffmpeg_setup_details() -> dict[str, str | list[str]]:
    platform_name = current_platform()
    arch = current_architecture()
    bundle_target = str(bundled_ffmpeg_candidates()[0])
    downloads = FFMPEG_DOWNLOAD_PAGES.get(platform_name, ["https://ffmpeg.org/download.html"])
    return {
        "platform": platform_name,
        "architecture": arch,
        "bundle_target": bundle_target,
        "downloads": downloads,
    }


def validate_audio_bitrate(bitrate_text: str) -> str:
    clean = bitrate_text.strip().lower()
    if not clean:
        raise argparse.ArgumentTypeError("Audio bitrate cannot be empty")
    match = re.fullmatch(r"([0-9]+)[kmb]?", clean)
    if match is None or int(match.group(1)) <= 0:
        raise argparse.ArgumentTypeError(f"Invalid audio bitrate: '{bitrate_text}' (example: '128k' or '192k')")
    return clean


def _parse_time_to_seconds(time_val: str) -> float | None:
    time_val = time_val.strip()
    try:
        if ":" in time_val:
            parts = time_val.split(":")
            if len(parts) not in (2, 3):
                return None
            value = 0.0
            for part in parts:
                value = value * 60 + float(part)
        else:
            try:
                value = int(time_val) / 1_000_000
            except ValueError:
                value = float(time_val)
        return value if math.isfinite(value) else None
    except (ValueError, OverflowError):
        return None


def get_media_duration(audio_path: Path) -> float | None:
    ffprobe_path, _source = find_ffprobe()
    if ffprobe_path is None:
        return None
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-protocol_whitelist",
        LOCAL_MEDIA_PROTOCOLS,
        "-select_streams",
        "a:0",
        "-show_entries",
        "format=duration:stream=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path.resolve()),
    ]
    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.upper() == "N/A":
            continue
        try:
            duration = float(line)
            if math.isfinite(duration) and duration > 0:
                return duration
        except ValueError:
            continue
    return None


def build_composite(
    image_path: Path,
    output_size: tuple[int, int],
    flip_horizontal: bool,
    flip_vertical: bool,
    blur_radius: float = 40,
) -> Image.Image:
    out_w, out_h = output_size
    if (
        out_w <= 0
        or out_h <= 0
        or out_w > MAX_OUTPUT_DIMENSION
        or out_h > MAX_OUTPUT_DIMENSION
        or out_w * out_h > MAX_OUTPUT_PIXELS
    ):
        raise ValueError(
            f"Output size exceeds the {MAX_OUTPUT_DIMENSION}px / {MAX_OUTPUT_PIXELS:,}-pixel safety limit"
        )
    with Image.open(image_path) as raw_image:
        source_w, source_h = raw_image.size
        if (
            source_w <= 0
            or source_h <= 0
            or source_w > MAX_SOURCE_IMAGE_DIMENSION
            or source_h > MAX_SOURCE_IMAGE_DIMENSION
            or source_w * source_h > MAX_SOURCE_IMAGE_PIXELS
        ):
            raise ValueError(
                "Source image dimensions "
                f"{source_w}x{source_h} exceed the {MAX_SOURCE_IMAGE_DIMENSION}px / "
                f"{MAX_SOURCE_IMAGE_PIXELS:,}-pixel safety limit"
            )
        base = ImageOps.exif_transpose(raw_image).convert("RGBA")

    if flip_horizontal:
        base = base.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_vertical:
        base = base.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    # Resize only the visible source region. Resizing the entire panorama first
    # can allocate an intermediate image hundreds of times larger than output.
    bg_scale = max(out_w / base.width, out_h / base.height)
    crop_w, crop_h = out_w / bg_scale, out_h / bg_scale
    left, top = (base.width - crop_w) / 2, (base.height - crop_h) / 2
    background_rgba = base.resize(
        (out_w, out_h), Image.Resampling.BILINEAR,
        box=(left, top, left + crop_w, top + crop_h),
    )
    background = Image.alpha_composite(
        Image.new("RGBA", output_size, "black"), background_rgba,
    ).convert("RGB")
    background = background.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    square_side = min(out_w, out_h)
    fg_scale = min(square_side / base.width, square_side / base.height)
    fg_size = (
        max(1, int(round(base.width * fg_scale))),
        max(1, int(round(base.height * fg_scale))),
    )
    foreground = base.resize(fg_size, Image.Resampling.LANCZOS)
    fg_x = (out_w - fg_size[0]) // 2
    fg_y = (out_h - fg_size[1]) // 2

    composed = background.copy()
    composed.paste(foreground, (fg_x, fg_y), foreground.getchannel("A"))
    return composed


def run_ffmpeg(
    ffmpeg_path: str,
    composite_path: Path,
    audio_path: Path,
    output_path: Path,
    audio_bitrate: str,
    fps: int,
    stop_event: threading.Event | None = None,
    duration_seconds: float | None = None,
    progress_callback=None,
    command_callback=None,
) -> None:
    if stop_event is not None and stop_event.is_set():
        raise RenderCancelledError("Video creation stopped.")
    cmd = [
        ffmpeg_path,
        "-nostdin",
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(fps),
        "-protocol_whitelist",
        LOCAL_MEDIA_PROTOCOLS,
        "-i",
        str(composite_path.resolve()),
        "-protocol_whitelist",
        LOCAL_MEDIA_PROTOCOLS,
        "-i",
        str(audio_path.resolve()),
        "-map",
        "0:v:0",
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
        audio_bitrate,
        "-shortest",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path.resolve()),
    ]
    if command_callback is not None:
        command_callback(" ".join(shlex.quote(part) for part in cmd))

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    progress_state: dict[str, str] = {}
    output_tail: deque[str] = deque(maxlen=20)
    output_queue: queue.Queue[str | Exception | None] = queue.Queue(maxsize=256)
    reader_stop = threading.Event()

    def enqueue(item: str | Exception | None) -> None:
        while not reader_stop.is_set():
            try:
                output_queue.put(item, timeout=0.1)
                return
            except queue.Full:
                continue

    def read_output() -> None:
        try:
            if process.stdout is not None:
                for output_line in iter(process.stdout.readline, ""):
                    if reader_stop.is_set():
                        break
                    enqueue(output_line)
        except Exception as exc:
            enqueue(exc)
        finally:
            enqueue(None)

    reader = threading.Thread(target=read_output, name="avid-ffmpeg-output", daemon=True)
    reader.start()
    try:
        reached_eof = False
        while True:
            if stop_event is not None and stop_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise RenderCancelledError("Video creation stopped.")

            if process.stdout is None:
                raise RuntimeError("FFmpeg output stream was not available.")

            try:
                raw_line = None if reached_eof else output_queue.get(timeout=0.1)
            except queue.Empty:
                raw_line = ""

            if isinstance(raw_line, Exception):
                raise RuntimeError("Could not read FFmpeg output") from raw_line
            if raw_line is None:
                reached_eof = True
                try:
                    return_code = process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    continue
                if return_code != 0:
                    raise FFmpegExecutionError(return_code, cmd, "\n".join(output_tail))
                return

            line = raw_line.strip()
            if line:
                output_tail.append(line)
                if command_callback is not None:
                    command_callback(line)

                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    progress_state[key] = value
                    if progress_callback is not None and key == "progress":
                        progress_seconds = None
                        raw_us = progress_state.get("out_time_us") or progress_state.get("out_time_ms")
                        if raw_us:
                            try:
                                progress_seconds = int(raw_us) / 1_000_000
                            except ValueError:
                                progress_seconds = None

                        if progress_seconds is None and "out_time" in progress_state:
                            progress_seconds = _parse_time_to_seconds(progress_state["out_time"])

                        fraction = None
                        eta_seconds = None
                        if (
                            duration_seconds
                            and math.isfinite(duration_seconds)
                            and duration_seconds > 0
                            and progress_seconds is not None
                        ):
                            fraction = max(0.0, min(progress_seconds / duration_seconds, 1.0))
                            remaining = max(duration_seconds - progress_seconds, 0.0)
                            try:
                                speed = float(progress_state.get("speed", "").rstrip("x"))
                            except ValueError:
                                speed = 0.0
                            if math.isfinite(speed) and speed > 0:
                                eta_seconds = remaining / speed

                        progress_callback(
                            {
                                "progress_seconds": progress_seconds,
                                "duration_seconds": duration_seconds,
                                "fraction": fraction,
                                "eta_seconds": eta_seconds,
                                "status": progress_state.get("progress", "running"),
                            }
                        )

    finally:
        reader_stop.set()
        if process.poll() is None:
            process.kill()
            process.wait()
        reader.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()


def create_video(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    output_size: tuple[int, int] = (1080, 1920),
    flip_horizontal: bool = False,
    flip_vertical: bool = False,
    audio_bitrate: str = "128k",
    fps: int = 30,
    stop_event: threading.Event | None = None,
    progress_callback=None,
    command_callback=None,
) -> None:
    image_path = image_path.resolve()
    audio_path = audio_path.resolve()
    output_path = output_path.resolve()
    if stop_event is not None and stop_event.is_set():
        raise RenderCancelledError("Video creation stopped.")
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not audio_path.is_file():
        raise FileNotFoundError(f"Audio not found: {audio_path}")
    for input_path in (image_path, audio_path):
        if output_path == input_path or (output_path.exists() and output_path.samefile(input_path)):
            raise ValueError("Output must be different from the image and audio inputs")
    if output_path.exists() and not output_path.is_file():
        raise ValueError("Output must be a file path")
    if not isinstance(fps, int) or isinstance(fps, bool) or fps <= 0:
        raise ValueError("fps must be a positive integer")
    if len(output_size) != 2 or any(not isinstance(n, int) or isinstance(n, bool) for n in output_size):
        raise ValueError("Output width and height must be integers")
    if output_size[0] <= 0 or output_size[1] <= 0:
        raise ValueError("Output width and height must be positive")
    if output_size[0] % 2 or output_size[1] % 2:
        raise ValueError("Output width and height must be even numbers for H.264 video")
    if (
        output_size[0] > MAX_OUTPUT_DIMENSION
        or output_size[1] > MAX_OUTPUT_DIMENSION
        or output_size[0] * output_size[1] > MAX_OUTPUT_PIXELS
    ):
        raise ValueError(
            f"Output size exceeds the {MAX_OUTPUT_DIMENSION}px / {MAX_OUTPUT_PIXELS:,}-pixel safety limit"
        )
    audio_bitrate = validate_audio_bitrate(audio_bitrate)
    ffmpeg_path = ensure_ffmpeg()
    duration_seconds = get_media_duration(audio_path)

    if stop_event is not None and stop_event.is_set():
        raise RenderCancelledError("Video creation stopped.")
    composite = build_composite(
        image_path=image_path,
        output_size=output_size,
        flip_horizontal=flip_horizontal,
        flip_vertical=flip_vertical,
    )
    if stop_event is not None and stop_event.is_set():
        raise RenderCancelledError("Video creation stopped.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Same-filesystem staging preserves an existing output on failure or stop.
    with tempfile.TemporaryDirectory(prefix=".avid_", dir=output_path.parent) as tmp_dir:
        composite_path = Path(tmp_dir) / "composite.png"
        composite.save(composite_path, "PNG")
        staged_output = Path(tmp_dir) / "encoded.mp4"
        run_ffmpeg(
            ffmpeg_path=ffmpeg_path,
            composite_path=composite_path,
            audio_path=audio_path,
            output_path=staged_output,
            audio_bitrate=audio_bitrate,
            fps=fps,
            stop_event=stop_event,
            duration_seconds=duration_seconds,
            progress_callback=progress_callback,
            command_callback=command_callback,
        )
        if stop_event is not None and stop_event.is_set():
            raise RenderCancelledError("Video creation stopped.")
        os.replace(staged_output, output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a video from an image and WAV audio by compositing a sharp centered image over a blurred fill background."
        )
    )
    parser.add_argument("image", type=Path, nargs="?", help="Input image path")
    parser.add_argument("audio", type=Path, nargs="?", help="Input audio path (WAV recommended)")
    parser.add_argument("output", type=Path, nargs="?", help="Output video path (example: output.mp4)")
    parser.add_argument(
        "--size",
        type=parse_size,
        default=(1080, 1920),
        help="Output size as WIDTHxHEIGHT (default: 1080x1920)",
    )
    parser.add_argument("--flip-horizontal", action="store_true", help="Flip image layers horizontally")
    parser.add_argument("--flip-vertical", action="store_true", help="Flip image layers vertically")
    parser.add_argument(
        "--audio-bitrate",
        type=validate_audio_bitrate,
        default="128k",
        help="AAC audio bitrate (default: 128k)",
    )
    parser.add_argument("--fps", type=int, default=30, help="Output frames per second (default: 30)")
    parser.add_argument(
        "--check-ffmpeg",
        action="store_true",
        help="Report FFmpeg availability and the expected bundled binary path for this platform.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.check_ffmpeg:
            ffmpeg_path, source = find_ffmpeg()
            details = ffmpeg_setup_details()
            if ffmpeg_path is None:
                print("FFmpeg status: missing")
                print(f"Platform: {details['platform']} ({details['architecture']})")
                print(f"Bundle target: {details['bundle_target']}")
                print("Download pages:")
                for download_url in details["downloads"]:
                    print(download_url)
                return 1

            print(f"FFmpeg status: available ({source})")
            print(f"FFmpeg path: {ffmpeg_path}")
            return 0

        if args.image is None or args.audio is None or args.output is None:
            raise ValueError("image, audio, and output are required unless --check-ffmpeg is used")

        create_video(
            image_path=args.image,
            audio_path=args.audio,
            output_path=args.output,
            output_size=args.size,
            flip_horizontal=args.flip_horizontal,
            flip_vertical=args.flip_vertical,
            audio_bitrate=args.audio_bitrate,
            fps=args.fps,
        )

        print(f"Video written to: {args.output}")
        return 0
    except FFmpegExecutionError as exc:
        print(str(exc), file=sys.stderr)
        return exc.returncode
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
