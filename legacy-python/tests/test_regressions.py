"""Behavioral coverage for the September engineering review."""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest import mock

from PIL import Image, ImageChops

import avid
import check_ffmpeg_bundle


class RenderSafetyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.image = self.root / "image.png"
        Image.new("RGB", (16, 16), "red").save(self.image)
        self.audio = self.root / "audio.wav"
        self.audio.write_bytes(b"audio input")
        self.output = self.root / "output.mp4"
        self.output.write_bytes(b"previous successful render")
        self.original = self.output.read_bytes()
        self.find = mock.patch("avid.ensure_ffmpeg", return_value="ffmpeg")
        self.find.start()
        self.addCleanup(self.find.stop)
        self.probe = mock.patch("avid.get_media_duration", return_value=1.0)
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def render(self, **kwargs):
        avid.create_video(self.image, self.audio, self.output, output_size=(16, 16), **kwargs)

    def test_failure_preserves_existing_output_and_removes_staging(self):
        def fail(**kwargs):
            kwargs["output_path"].write_bytes(b"partial")
            raise avid.FFmpegExecutionError(1, [], "bad media")
        with mock.patch("avid.run_ffmpeg", side_effect=fail):
            with self.assertRaises(avid.FFmpegExecutionError):
                self.render()
        self.assertEqual(self.output.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob(".avid_*")), [])

    def test_success_replaces_existing_output_after_encoder_finishes(self):
        def encode(**kwargs):
            self.assertEqual(self.output.read_bytes(), self.original)
            self.assertEqual(kwargs["output_path"].parent.parent.resolve(), self.root.resolve())
            kwargs["output_path"].write_bytes(b"complete video")
        with mock.patch("avid.run_ffmpeg", side_effect=encode):
            self.render()
        self.assertEqual(self.output.read_bytes(), b"complete video")
        self.assertEqual(list(self.root.glob(".avid_*")), [])

    def test_output_named_like_internal_frame_is_safe(self):
        self.output = self.root / "composite.png"
        self.output.write_bytes(b"old output")

        def encode(**kwargs):
            self.assertNotEqual(kwargs["composite_path"], kwargs["output_path"])
            kwargs["output_path"].write_bytes(b"mp4 data")

        with mock.patch("avid.run_ffmpeg", side_effect=encode):
            self.render()
        self.assertEqual(self.output.read_bytes(), b"mp4 data")

    def test_late_cancellation_preserves_output(self):
        stop = threading.Event()
        def encode(**kwargs):
            kwargs["output_path"].write_bytes(b"video")
            stop.set()
        with mock.patch("avid.run_ffmpeg", side_effect=encode):
            with self.assertRaises(avid.RenderCancelledError):
                self.render(stop_event=stop)
        self.assertEqual(self.output.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob(".avid_*")), [])

    def test_early_cancellation_does_not_probe_or_encode(self):
        stop = threading.Event()
        stop.set()
        with mock.patch("avid.get_media_duration") as probe, mock.patch("avid.run_ffmpeg") as encode:
            with self.assertRaises(avid.RenderCancelledError):
                self.render(stop_event=stop)
        probe.assert_not_called()
        encode.assert_not_called()

    def test_rejects_input_paths_and_hardlink_aliases(self):
        alias = self.root / "alias.mp4"
        os.link(self.image, alias)
        for output in (self.image, self.audio, alias):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "different"):
                avid.create_video(self.image, self.audio, output)
        self.assertEqual(self.audio.read_bytes(), b"audio input")
        with Image.open(self.image) as image:
            self.assertEqual(image.size, (16, 16))

    def test_rejects_directories_and_noninteger_fps(self):
        with self.assertRaises(FileNotFoundError):
            avid.create_video(self.root, self.audio, self.output)
        for fps in (0, -1, 1.5, True):
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                self.render(fps=fps)

    def test_rejects_output_above_pixel_budget(self):
        with self.assertRaisesRegex(ValueError, "safety limit"):
            avid.create_video(
                self.image,
                self.audio,
                self.output,
                output_size=(8192, 8192),
            )


class ProbeAndValidationTests(unittest.TestCase):
    def test_bitrate_rejects_repeated_suffixes_and_unicode_digits(self):
        for value in ("128kk", "128kbm", "128mb", "１２８k", "128.5k", "0m"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                avid.validate_audio_bitrate(value)

    def test_nonfinite_progress_is_not_reported(self):
        for value in ("nan", "inf", "-inf", "00:00:nan", "1:inf", "00:00:1e999"):
            self.assertIsNone(avid._parse_time_to_seconds(value))

    @mock.patch("avid.find_ffprobe", return_value=("ffprobe", "system"))
    def test_probe_ignores_nonfinite_values_and_selects_audio(self, _find):
        with mock.patch("avid.subprocess.run") as run:
            run.return_value.stdout = "nan\ninf\n-1\nN/A\n3.25\n"
            self.assertEqual(avid.get_media_duration(Path("-audio.wav")), 3.25)
        args, kwargs = run.call_args
        self.assertIn("a:0", args[0])
        self.assertEqual(args[0][args[0].index("-protocol_whitelist") + 1], avid.LOCAL_MEDIA_PROTOCOLS)
        self.assertTrue(Path(args[0][-1]).is_absolute())
        self.assertEqual(kwargs["timeout"], 10)
        run.assert_called_once()

    @mock.patch("avid.find_ffprobe", return_value=("ffprobe", "system"))
    def test_probe_timeout_is_unavailable_duration(self, _find):
        with mock.patch("avid.subprocess.run", side_effect=subprocess.TimeoutExpired("ffprobe", 10)):
            self.assertIsNone(avid.get_media_duration(Path("audio.wav")))

    def test_binary_discovery_skips_directories_and_nonexecutables(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            directory = root / "ffmpeg"
            directory.mkdir()
            bad = root / "not-executable"
            bad.write_text("not a binary")
            good = root / "working-ffmpeg"
            good.write_text("binary")
            good.chmod(0o755)
            candidates = [directory, good] if os.name == "nt" else [directory, bad, good]
            with mock.patch("avid.bundled_ffmpeg_candidates", return_value=candidates):
                self.assertEqual(avid.bundled_ffmpeg_path(), good)
            with mock.patch("avid.bundled_ffprobe_candidates", return_value=[directory]):
                self.assertIsNone(avid.bundled_ffprobe_path())

    def test_bundle_validator_requires_executable_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "ffmpeg" / "darwin" / "arm64"
            target.mkdir(parents=True)
            (target / "ffmpeg").write_text("placeholder")
            (target / "ffprobe").mkdir()
            argv = [
                "check_ffmpeg_bundle.py",
                "--root",
                str(root),
                "--platform",
                "darwin",
                "--arch",
                "arm64",
                "--require-bundled-ffmpeg",
            ]
            with (
                mock.patch("sys.argv", argv),
                mock.patch("sys.stdout", new=io.StringIO()),
                mock.patch("sys.stderr", new=io.StringIO()),
            ):
                self.assertEqual(check_ffmpeg_bundle.main(), 1)

    def test_bundle_validator_accepts_pyinstaller_macos_layout(self):
        with tempfile.TemporaryDirectory() as td:
            app = Path(td) / "AVID.app"
            frameworks = app / "Contents" / "Frameworks"
            frameworks.mkdir(parents=True)
            for name in ("ffmpeg", "ffprobe"):
                binary = frameworks / name
                binary.write_text("placeholder")
                binary.chmod(0o755)
            argv = [
                "check_ffmpeg_bundle.py",
                "--root",
                str(app),
                "--platform",
                "darwin",
                "--arch",
                "arm64",
                "--require-bundled-ffmpeg",
            ]
            with mock.patch("sys.argv", argv), mock.patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(check_ffmpeg_bundle.main(), 0)


class ProcessTests(unittest.TestCase):
    def run_process(self, **kwargs):
        avid.run_ffmpeg("ffmpeg", Path("frame.png"), Path("audio.wav"), Path("-out.mp4"), "128k", 30, **kwargs)

    def test_progress_is_batched_and_eta_uses_speed(self):
        process = mock.Mock(stdout=io.StringIO("out_time_us=5000000\nout_time_ms=5000000\nout_time=00:00:05\nspeed=2x\nprogress=continue\n"))
        process.wait.return_value = process.poll.return_value = 0
        updates = []
        with mock.patch("avid.subprocess.Popen", return_value=process) as popen:
            self.run_process(duration_seconds=15, progress_callback=updates.append)
        self.assertEqual(len(updates), 1)
        self.assertAlmostEqual(updates[0]["fraction"], 1/3)
        self.assertEqual(updates[0]["eta_seconds"], 5)
        command = popen.call_args.args[0]
        self.assertEqual([command[i+1] for i, arg in enumerate(command) if arg == "-map"], ["0:v:0", "1:a:0"])
        self.assertEqual(
            [command[i+1] for i, arg in enumerate(command) if arg == "-protocol_whitelist"],
            [avid.LOCAL_MEDIA_PROTOCOLS, avid.LOCAL_MEDIA_PROTOCOLS],
        )
        self.assertEqual(command[command.index("-f") + 1], "mp4")
        self.assertTrue(Path(command[-1]).is_absolute())

    def test_unknown_speed_does_not_claim_eta(self):
        process = mock.Mock(stdout=io.StringIO("out_time_us=1000000\nspeed=N/A\nprogress=continue\n"))
        process.wait.return_value = process.poll.return_value = 0
        updates = []
        with mock.patch("avid.subprocess.Popen", return_value=process):
            self.run_process(duration_seconds=10, progress_callback=updates.append)
        self.assertIsNone(updates[0]["eta_seconds"])

    def test_reader_failure_is_propagated_and_process_reaped(self):
        process = mock.Mock()
        process.stdout.readline.side_effect = OSError("broken pipe")
        process.poll.return_value = None
        with mock.patch("avid.subprocess.Popen", return_value=process):
            with self.assertRaisesRegex(RuntimeError, "Could not read"):
                self.run_process()
        process.kill.assert_called_once()
        process.wait.assert_called()

    def test_cancellation_reaps_real_silent_child(self):
        real_popen = subprocess.Popen
        children = []
        def spawn(*_args, **kwargs):
            child = real_popen([sys.executable, "-u", "-c", "import time; time.sleep(30)"], **kwargs)
            children.append(child)
            return child
        stop = threading.Event()
        timer = threading.Timer(0.2, stop.set)
        timer.start()
        try:
            with mock.patch("avid.subprocess.Popen", side_effect=spawn):
                with self.assertRaises(avid.RenderCancelledError):
                    self.run_process(stop_event=stop)
        finally:
            timer.cancel()
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait()
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)
        self.assertFalse(any(t.name == "avid-ffmpeg-output" and t.is_alive() for t in threading.enumerate()))


class CompositeRegressionTests(unittest.TestCase):
    def test_source_image_limit_is_checked_before_decode(self):
        raw_image = mock.MagicMock()
        raw_image.size = (avid.MAX_SOURCE_IMAGE_DIMENSION + 1, 1)
        opened = mock.MagicMock()
        opened.__enter__.return_value = raw_image
        with (
            mock.patch("avid.Image.open", return_value=opened),
            mock.patch("avid.ImageOps.exif_transpose") as transpose,
        ):
            with self.assertRaisesRegex(ValueError, "Source image dimensions"):
                avid.build_composite(Path("oversized.png"), (64, 64), False, False)
        transpose.assert_not_called()

    def test_direct_composite_rejects_output_above_pixel_budget(self):
        with self.assertRaisesRegex(ValueError, "safety limit"):
            avid.build_composite(Path("unused.png"), (8192, 8192), False, False)

    def test_flips_change_image_content(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "pattern.png"
            image = Image.new("RGB", (20, 20), "red")
            image.paste("blue", (0, 0, 10, 10))
            image.save(path)
            normal = avid.build_composite(path, image.size, False, False)
            flipped = avid.build_composite(path, image.size, True, True)
            expected = normal.transpose(Image.Transpose.FLIP_LEFT_RIGHT).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            self.assertIsNone(ImageChops.difference(flipped, expected).getbbox())
            self.assertIsNotNone(ImageChops.difference(flipped, normal).getbbox())

    def test_extreme_panorama_has_bounded_resize_dimensions(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "panorama.png"
            Image.new("RGB", (20000, 2), "red").save(path)
            sizes = []
            original_resize = Image.Image.resize
            def resize(image, size, *args, **kwargs):
                sizes.append(size)
                self.assertLessEqual(size[0] * size[1], 64 * 64)
                return original_resize(image, size, *args, **kwargs)
            with mock.patch.object(Image.Image, "resize", new=resize):
                result = avid.build_composite(path, (64, 64), False, False)
            self.assertEqual(result.size, (64, 64))
            self.assertTrue(sizes)


class MediaIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg, _ = avid.find_ffmpeg()
        self.ffprobe, _ = avid.find_ffprobe()
        if not self.ffmpeg or not self.ffprobe:
            self.skipTest("Real FFmpeg and ffprobe required")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.image = self.root / "red.png"
        Image.new("RGB", (32, 32), "red").save(self.image)
        self.audio = self.root / "audio.wav"
        with wave.open(str(self.audio), "wb") as audio:
            audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            audio.writeframes(b"\0\0" * 4000)
        self.output = self.root / "output.mp4"

    def render(self, audio):
        stop = threading.Event()
        watchdog = threading.Timer(5, stop.set)
        watchdog.start()
        try:
            avid.create_video(self.image, audio, self.output, output_size=(32, 32), fps=10, stop_event=stop)
        finally:
            watchdog.cancel()

    def test_video_in_audio_source_cannot_replace_composite(self):
        source = self.root / "blue-video.mp4"
        subprocess.run([self.ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=blue:s=128x128:d=0.5",
                        "-i", str(self.audio), "-c:v", "libx264", "-c:a", "aac", "-shortest", str(source)], check=True, timeout=10)
        self.render(source)
        probe = subprocess.run([self.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(self.output)], capture_output=True, text=True, check=True, timeout=10)
        media = json.loads(probe.stdout)
        self.assertEqual([s["codec_type"] for s in media["streams"]], ["video", "audio"])
        self.assertEqual(media["streams"][0]["width"], 32)
        self.assertLess(abs(float(media["format"]["duration"]) - 0.5), 0.2)
        frame = subprocess.run([self.ffmpeg, "-v", "error", "-i", str(self.output), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, check=True, timeout=10).stdout
        self.assertGreater(frame[0], 200)
        self.assertLess(frame[2], 20)

    def test_missing_audio_fails_promptly_preserving_output(self):
        self.output.write_bytes(b"keep me")
        with self.assertRaises(avid.FFmpegExecutionError):
            self.render(self.image)
        self.assertEqual(self.output.read_bytes(), b"keep me")
        self.assertFalse(list(self.root.glob(".avid_*")))


if __name__ == "__main__":
    unittest.main()
