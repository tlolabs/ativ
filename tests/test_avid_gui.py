import threading
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

import avid
import avid_gui


class PlatformFormatsTests(unittest.TestCase):
    def test_all_platform_resolutions_are_valid_even_sizes(self) -> None:
        for platform_name, formats in avid_gui.PLATFORM_FORMATS.items():
            self.assertTrue(len(formats) > 0, f"Platform {platform_name} has empty formats list")
            for item in formats:
                res_str = item["resolution"]
                aspect_str = item["aspect"]
                self.assertTrue(bool(res_str))
                self.assertTrue(bool(aspect_str))
                w, h = avid.parse_size(res_str)
                self.assertEqual(w % 2, 0, f"Odd width {w} in {platform_name}: {res_str}")
                self.assertEqual(h % 2, 0, f"Odd height {h} in {platform_name}: {res_str}")


class GUIShutdownTests(unittest.TestCase):
    def make_gui(self) -> avid_gui.AvidGUI:
        gui = avid_gui.AvidGUI.__new__(avid_gui.AvidGUI)
        gui.root = mock.Mock()
        gui.closing = False
        gui.render_stop_event = threading.Event()
        gui.render_thread = None
        gui.preview_after_id = "preview"
        gui.audio_after_id = "audio"
        gui.launch_after_id = "launch"
        gui.ui_after_id = "ui"
        return gui

    def test_close_requests_cancellation_before_destroying_window(self) -> None:
        gui = self.make_gui()
        gui._on_window_close()
        self.assertTrue(gui.closing)
        self.assertTrue(gui.render_stop_event.is_set())
        gui.root.withdraw.assert_called_once()
        gui.root.destroy.assert_called_once()
        self.assertEqual(gui.root.after_cancel.call_count, 4)

    def test_close_waits_while_renderer_is_alive(self) -> None:
        gui = self.make_gui()
        gui.render_thread = mock.Mock()
        gui.render_thread.is_alive.return_value = True
        gui._on_window_close()
        gui.root.destroy.assert_not_called()
        gui.root.after.assert_called_with(50, gui._wait_for_render_shutdown)


class AvidGUIUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
            cls.gui = avid_gui.AvidGUI(cls.root)
        except tk.TclError:
            raise unittest.SkipTest("Tkinter display not available")

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "root"):
            cls.root.destroy()

    def test_format_seconds(self) -> None:
        self.assertEqual(self.gui._format_seconds(None), "--:--")
        self.assertEqual(self.gui._format_seconds(0.0), "00:00")
        self.assertEqual(self.gui._format_seconds(45.2), "00:45")
        self.assertEqual(self.gui._format_seconds(125.0), "02:05")
        self.assertEqual(self.gui._format_seconds(3665.0), "1:01:05")

    def test_preview_output_size(self) -> None:
        # PREVIEW_BOX is (260, 260)
        pw, ph = self.gui._preview_output_size(1080, 1920)
        self.assertLessEqual(pw, 260)
        self.assertLessEqual(ph, 260)
        self.assertAlmostEqual(pw / ph, 1080 / 1920, places=1)

        pw_h, ph_h = self.gui._preview_output_size(1920, 1080)
        self.assertLessEqual(pw_h, 260)
        self.assertLessEqual(ph_h, 260)
        self.assertAlmostEqual(pw_h / ph_h, 1920 / 1080, places=1)

    def test_platform_change_updates_aspect_and_resolution(self) -> None:
        self.gui.platform_var.set("YouTube")
        self.gui._on_platform_change(None)
        aspects = self.gui.aspect_ratio_combo["values"]
        self.assertIn("Horizontal video (16:9)", aspects)
        self.assertIn("Vertical video (9:16)", aspects)

        self.gui.aspect_ratio_var.set("Horizontal video (16:9)")
        self.gui._on_aspect_ratio_change(None)
        resolutions = self.gui.resolution_combo["values"]
        self.assertIn("1920x1080", resolutions)

    def test_suggest_output_path(self) -> None:
        self.gui.output_var.set("")
        self.gui.auto_output_set = False
        self.gui.audio_var.set("/tmp/my_podcast.wav")
        self.gui._suggest_output_path()
        self.assertEqual(self.gui.output_var.get(), "/tmp/my_podcast.mp4")
        self.assertTrue(self.gui.auto_output_set)

    def test_manual_output_path_is_not_overwritten(self) -> None:
        self.gui.output_var.set("/tmp/custom-name.mp4")
        self.gui.audio_var.set("/tmp/different-audio.wav")
        self.gui._suggest_output_path()
        self.assertEqual(self.gui.output_var.get(), "/tmp/custom-name.mp4")
        self.assertFalse(self.gui.auto_output_set)

    def test_worker_callback_is_queued_for_the_ui_thread(self) -> None:
        called_on = []
        worker = threading.Thread(
            target=lambda: self.gui._run_on_ui_thread(
                lambda: called_on.append(threading.current_thread())
            )
        )
        worker.start()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(called_on, [])

        self.gui._drain_ui_callbacks()
        self.assertEqual(called_on, [threading.current_thread()])

    def test_stale_preview_result_is_ignored(self) -> None:
        previous_caption = self.gui.preview_meta_var.get()
        self.gui._preview_generation = 10
        self.gui._apply_preview(9, None, "stale error")
        self.assertEqual(self.gui.preview_meta_var.get(), previous_caption)


if __name__ == "__main__":
    unittest.main()
