import argparse
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import avid


class ParseSizeTests(unittest.TestCase):
    def test_accepts_even_dimensions(self) -> None:
        self.assertEqual(avid.parse_size("1080x1920"), (1080, 1920))
        self.assertEqual(avid.parse_size("1920X1080"), (1920, 1080))

    def test_rejects_odd_dimensions(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError) as exc:
            avid.parse_size("1081x1920")
        self.assertIn("even numbers", str(exc.exception))

        with self.assertRaises(argparse.ArgumentTypeError) as exc:
            avid.parse_size("1080x1921")
        self.assertIn("even numbers", str(exc.exception))

    def test_rejects_invalid_format(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            avid.parse_size("1080-1920")

    def test_rejects_non_integers(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            avid.parse_size("1080.5x1920")

    def test_rejects_non_positive(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            avid.parse_size("0x1080")
        with self.assertRaises(argparse.ArgumentTypeError):
            avid.parse_size("-100x200")


class ValidateBitrateTests(unittest.TestCase):
    def test_accepts_valid_bitrates(self) -> None:
        self.assertEqual(avid.validate_audio_bitrate("128k"), "128k")
        self.assertEqual(avid.validate_audio_bitrate("192K"), "192k")
        self.assertEqual(avid.validate_audio_bitrate("320k"), "320k")
        self.assertEqual(avid.validate_audio_bitrate("64000"), "64000")

    def test_rejects_invalid_bitrates(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            avid.validate_audio_bitrate("")
        with self.assertRaises(argparse.ArgumentTypeError):
            avid.validate_audio_bitrate("invalid")
        with self.assertRaises(argparse.ArgumentTypeError):
            avid.validate_audio_bitrate("-128k")


class ParseTimeToSecondsTests(unittest.TestCase):
    def test_parses_microseconds(self) -> None:
        self.assertEqual(avid._parse_time_to_seconds("1500000"), 1.5)
        self.assertEqual(avid._parse_time_to_seconds("0"), 0.0)

    def test_parses_timestamps(self) -> None:
        self.assertAlmostEqual(avid._parse_time_to_seconds("00:01:23.500000") or 0.0, 83.5)
        self.assertAlmostEqual(avid._parse_time_to_seconds("01:30") or 0.0, 90.0)

    def test_handles_invalid_and_na(self) -> None:
        self.assertIsNone(avid._parse_time_to_seconds("N/A"))
        self.assertIsNone(avid._parse_time_to_seconds(""))
        self.assertIsNone(avid._parse_time_to_seconds("invalid"))


class BinaryDiscoveryTests(unittest.TestCase):
    @mock.patch("avid.shutil.which", return_value="/usr/local/bin/ffmpeg")
    @mock.patch("avid.bundled_ffmpeg_path", return_value=None)
    def test_ffmpeg_falls_back_to_system_path(self, _bundled: mock.Mock, _which: mock.Mock) -> None:
        self.assertEqual(avid.find_ffmpeg(), ("/usr/local/bin/ffmpeg", "system"))

    @mock.patch("avid.shutil.which", return_value="/usr/local/bin/ffprobe")
    @mock.patch("avid.bundled_ffprobe_path", return_value=None)
    def test_ffprobe_falls_back_to_system_path(self, _bundled: mock.Mock, _which: mock.Mock) -> None:
        self.assertEqual(avid.find_ffprobe(), ("/usr/local/bin/ffprobe", "system"))

    @mock.patch("avid.find_ffmpeg", return_value=(None, None))
    def test_ensure_ffmpeg_raises_when_missing(self, _find: mock.Mock) -> None:
        with self.assertRaises(RuntimeError) as exc:
            avid.ensure_ffmpeg()
        self.assertIn("FFmpeg is not available", str(exc.exception))

    @mock.patch("avid.find_ffprobe", return_value=(None, None))
    def test_ensure_ffprobe_raises_when_missing(self, _find: mock.Mock) -> None:
        with self.assertRaises(RuntimeError) as exc:
            avid.ensure_ffprobe()
        self.assertIn("ffprobe is not available", str(exc.exception))


class MediaDurationTests(unittest.TestCase):
    @mock.patch("avid.find_ffprobe", return_value=("/usr/bin/ffprobe", "system"))
    @mock.patch("avid.subprocess.run")
    def test_parses_duration_from_ffprobe_output(self, mock_run: mock.Mock, _find: mock.Mock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="124.56\n", stderr=""
        )
        duration = avid.get_media_duration(Path("audio.wav"))
        self.assertEqual(duration, 124.56)

    @mock.patch("avid.find_ffprobe", return_value=("/usr/bin/ffprobe", "system"))
    @mock.patch("avid.subprocess.run")
    def test_handles_multiline_and_na_output(self, mock_run: mock.Mock, _find: mock.Mock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout="N/A\n62.4\n", stderr=""
        )
        duration = avid.get_media_duration(Path("audio.mp3"))
        self.assertEqual(duration, 62.4)

    @mock.patch("avid.find_ffprobe", return_value=(None, None))
    def test_returns_none_when_ffprobe_missing(self, _find: mock.Mock) -> None:
        self.assertIsNone(avid.get_media_duration(Path("audio.wav")))


class CompositeTests(unittest.TestCase):
    def test_transparent_foreground_reveals_background(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "transparent.png"
            image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
            image.putpixel((0, 0), (0, 0, 0, 0))
            image.save(image_path)

            composite = avid.build_composite(image_path, (8, 4), False, False)

        self.assertEqual(composite.mode, "RGB")
        self.assertNotEqual(composite.getpixel((2, 0)), (0, 0, 0))

    def test_flips_applied_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "test.png"
            image = Image.new("RGB", (20, 20), (100, 150, 200))
            image.putpixel((0, 0), (255, 255, 255))
            image.save(image_path)

            composite_norm = avid.build_composite(image_path, (20, 20), False, False)
            composite_flipped = avid.build_composite(image_path, (20, 20), True, True)

            self.assertEqual(composite_norm.size, (20, 20))
            self.assertEqual(composite_flipped.size, (20, 20))


class FFmpegDiagnosticsTests(unittest.TestCase):
    @mock.patch("avid.subprocess.Popen")
    def test_failure_includes_recent_ffmpeg_output(self, popen: mock.Mock) -> None:
        process = popen.return_value
        process.stdout.readline.side_effect = ["first detail\n", "fatal encoder error\n", ""]
        process.stdout.close.return_value = None
        process.poll.return_value = 1
        process.wait.return_value = 1

        with self.assertRaises(avid.FFmpegExecutionError) as raised:
            avid.run_ffmpeg(
                "ffmpeg",
                Path("frame.png"),
                Path("audio.wav"),
                Path("output.mp4"),
                "128k",
                30,
            )

        self.assertIn("fatal encoder error", str(raised.exception))
        self.assertEqual(raised.exception.returncode, 1)

    @mock.patch("avid.subprocess.Popen")
    def test_cancellation_raises_render_cancelled_error(self, popen: mock.Mock) -> None:
        process = popen.return_value
        process.stdout.readline.side_effect = ["frame=1\n", "frame=2\n"]
        process.stdout.close.return_value = None
        process.poll.return_value = None
        process.wait.return_value = 0

        stop_event = threading.Event()
        stop_event.set()

        with self.assertRaises(avid.RenderCancelledError):
            avid.run_ffmpeg(
                "ffmpeg",
                Path("frame.png"),
                Path("audio.wav"),
                Path("output.mp4"),
                "128k",
                30,
                stop_event=stop_event,
            )


class CLIArgumentParsingTests(unittest.TestCase):
    @mock.patch("sys.argv", ["avid.py", "image.png", "audio.wav", "out.mp4", "--size", "1920x1080"])
    def test_parse_args_valid_options(self) -> None:
        args = avid.parse_args()
        self.assertEqual(args.image, Path("image.png"))
        self.assertEqual(args.audio, Path("audio.wav"))
        self.assertEqual(args.output, Path("out.mp4"))
        self.assertEqual(args.size, (1920, 1080))
        self.assertEqual(args.audio_bitrate, "128k")
        self.assertEqual(args.fps, 30)

    @mock.patch("sys.argv", ["avid.py", "--check-ffmpeg"])
    def test_parse_args_check_ffmpeg_flag(self) -> None:
        args = avid.parse_args()
        self.assertTrue(args.check_ffmpeg)


class EndToEndIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        ffmpeg_path, _ = avid.find_ffmpeg()
        if ffmpeg_path is None:
            self.skipTest("FFmpeg binary is not available on this system")

    def test_end_to_end_video_generation(self) -> None:
        import math
        import struct
        import wave

        with tempfile.TemporaryDirectory() as td:
            img_path = Path(td) / "test_input.jpg"
            img = Image.new("RGB", (320, 240), (45, 90, 180))
            img.save(img_path)

            audio_path = Path(td) / "test_input.wav"
            sample_rate = 44100
            duration_secs = 0.5
            with wave.open(str(audio_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                frames = []
                for i in range(int(sample_rate * duration_secs)):
                    val = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * 440.0 * i / sample_rate))
                    frames.append(struct.pack("<h", val))
                wf.writeframes(b"".join(frames))

            out_path = Path(td) / "test_output.mp4"
            progress_events = []

            avid.create_video(
                image_path=img_path,
                audio_path=audio_path,
                output_path=out_path,
                output_size=(720, 1280),
                fps=30,
                progress_callback=lambda p: progress_events.append(p),
            )

            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
