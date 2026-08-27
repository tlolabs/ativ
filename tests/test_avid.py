import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import avid


class ParseSizeTests(unittest.TestCase):
    def test_accepts_even_dimensions(self) -> None:
        self.assertEqual(avid.parse_size("1080x1920"), (1080, 1920))

    def test_rejects_odd_dimensions(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            avid.parse_size("1081x1920")


class BinaryDiscoveryTests(unittest.TestCase):
    @mock.patch("avid.shutil.which", return_value="/usr/local/bin/ffmpeg")
    @mock.patch("avid.bundled_ffmpeg_path", return_value=None)
    def test_ffmpeg_falls_back_to_system_path(self, _bundled: mock.Mock, _which: mock.Mock) -> None:
        self.assertEqual(avid.find_ffmpeg(), ("/usr/local/bin/ffmpeg", "system"))

    @mock.patch("avid.shutil.which", return_value="/usr/local/bin/ffprobe")
    @mock.patch("avid.bundled_ffprobe_path", return_value=None)
    def test_ffprobe_falls_back_to_system_path(self, _bundled: mock.Mock, _which: mock.Mock) -> None:
        self.assertEqual(avid.find_ffprobe(), ("/usr/local/bin/ffprobe", "system"))


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


if __name__ == "__main__":
    unittest.main()
