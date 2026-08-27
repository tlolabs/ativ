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
import queue
import platform
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
        if candidate.exists():
            return candidate
    return None


def bundled_ffprobe_path() -> Path | None:
    for candidate in bundled_ffprobe_candidates():
        if candidate.exists():
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


def get_media_duration(audio_path: Path) -> float | None:
    ffprobe_path, _source = find_ffprobe()
    if ffprobe_path is None:
        return None
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    duration_text = result.stdout.strip()
    if not duration_text:
        return None
    try:
        duration = float(duration_text)
    except ValueError:
        return None
    return duration if duration > 0 else None


def build_composite(
    image_path: Path,
    output_size: tuple[int, int],
    flip_horizontal: bool,
    flip_vertical: bool,
) -> Image.Image:
    out_w, out_h = output_size
    with Image.open(image_path) as raw_image:
        base = ImageOps.exif_transpose(raw_image).convert("RGBA")

    if flip_horizontal:
        base = base.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if flip_vertical:
        base = base.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    bg_scale = max(out_w / base.width, out_h / base.height)
    bg_size = (
        max(1, int(round(base.width * bg_scale))),
        max(1, int(round(base.height * bg_scale))),
    )
    background_source = Image.alpha_composite(Image.new("RGBA", base.size, "black"), base).convert("RGB")
    background = background_source.resize(bg_size, Image.Resampling.LANCZOS)
    bg_x = (bg_size[0] - out_w) // 2
    bg_y = (bg_size[1] - out_h) // 2
    background = background.crop((bg_x, bg_y, bg_x + out_w, bg_y + out_h))
    background = background.filter(ImageFilter.GaussianBlur(radius=40))

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
    cmd = [
        ffmpeg_path,
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(fps),
        "-i",
        str(composite_path),
        "-i",
        str(audio_path),
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
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]
    if command_callback is not None:
        command_callback(" ".join(shlex.quote(part) for part in cmd))

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    progress_state: dict[str, str] = {}
    output_tail: deque[str] = deque(maxlen=20)
    output_queue: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        if process.stdout is None:
            output_queue.put(None)
            return
        for output_line in iter(process.stdout.readline, ""):
            output_queue.put(output_line)
        output_queue.put(None)

    reader = threading.Thread(target=read_output, name="avid-ffmpeg-output", daemon=True)
    reader.start()
    try:
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
                raw_line = output_queue.get(timeout=0.1)
            except queue.Empty:
                raw_line = ""

            if raw_line is None:
                return_code = process.wait()
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
                    progress_state[key] = value
                    if progress_callback is not None and key in {"out_time_ms", "out_time_us", "progress"}:
                        progress_seconds = None
                        raw_value = progress_state.get("out_time_us") or progress_state.get("out_time_ms")
                        if raw_value:
                            try:
                                progress_seconds = int(raw_value) / 1_000_000
                            except ValueError:
                                progress_seconds = None

                        fraction = None
                        eta_seconds = None
                        if duration_seconds and progress_seconds is not None:
                            fraction = max(0.0, min(progress_seconds / duration_seconds, 1.0))
                            remaining = max(duration_seconds - progress_seconds, 0.0)
                            eta_seconds = remaining

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
        if process.poll() is None:
            process.kill()
            process.wait()
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
    ffmpeg_path = ensure_ffmpeg()

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")
    if fps <= 0:
        raise ValueError("fps must be a positive integer")
    if output_size[0] <= 0 or output_size[1] <= 0:
        raise ValueError("Output width and height must be positive")
    if output_size[0] % 2 or output_size[1] % 2:
        raise ValueError("Output width and height must be even numbers for H.264 video")
    duration_seconds = get_media_duration(audio_path)

    composite = build_composite(
        image_path=image_path,
        output_size=output_size,
        flip_horizontal=flip_horizontal,
        flip_vertical=flip_vertical,
    )
    if stop_event is not None and stop_event.is_set():
        raise RenderCancelledError("Video creation stopped.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="avid_") as tmp_dir:
        composite_path = Path(tmp_dir) / "composite.png"
        composite.save(composite_path, "PNG")
        run_ffmpeg(
            ffmpeg_path=ffmpeg_path,
            composite_path=composite_path,
            audio_path=audio_path,
            output_path=output_path,
            audio_bitrate=audio_bitrate,
            fps=fps,
            stop_event=stop_event,
            duration_seconds=duration_seconds,
            progress_callback=progress_callback,
            command_callback=command_callback,
        )


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
    parser.add_argument("--audio-bitrate", default="128k", help="AAC audio bitrate (default: 128k)")
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
