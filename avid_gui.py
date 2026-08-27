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
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from PIL import Image, ImageTk

from avid import (
    RenderCancelledError,
    build_composite,
    create_video,
    ffmpeg_setup_details,
    find_ffmpeg,
    find_ffprobe,
    get_media_duration,
    parse_size,
)


PLATFORM_FORMATS = {
    "Instagram": [
        {"resolution": "1920x1080", "aspect": "Horizontal video (16:9)"},
        {"resolution": "1080x1080", "aspect": "Square (1:1)"},
        {"resolution": "1080x1350", "aspect": "4:5"},
        {"resolution": "1080x1920", "aspect": "Vertical video (9:16)"},
    ],
    "TikTok": [
        {"resolution": "1080x1920", "aspect": "Vertical video (9:16)"},
        {"resolution": "720x1280", "aspect": "Vertical video (9:16)"},
    ],
    "Facebook": [
        {"resolution": "1280x720", "aspect": "Horizontal video (16:9)"},
        {"resolution": "1080x1080", "aspect": "Square (1:1)"},
        {"resolution": "720x1280", "aspect": "Vertical video (9:16)"},
        {"resolution": "1080x1920", "aspect": "Vertical video (9:16)"},
        {"resolution": "1080x1350", "aspect": "4:5"},
    ],
    "Twitter / X": [
        {"resolution": "1280x720", "aspect": "Horizontal video (16:9)"},
        {"resolution": "720x720", "aspect": "Square (1:1)"},
        {"resolution": "720x1280", "aspect": "Vertical video (9:16)"},
    ],
    "YouTube": [
        {"resolution": "1920x1080", "aspect": "Horizontal video (16:9)"},
        {"resolution": "1080x1920", "aspect": "Vertical video (9:16)"},
        {"resolution": "1080x1080", "aspect": "Square (1:1)"},
        {"resolution": "1440x1080", "aspect": "4:3"},
    ],
    "LinkedIn": [
        {"resolution": "1920x1080", "aspect": "Horizontal video (16:9)"},
        {"resolution": "1080x1080", "aspect": "Square (1:1)"},
    ],
    "Snapchat": [
        {"resolution": "1080x1920", "aspect": "Vertical video (9:16)"},
    ],
    "Pinterest": [
        {"resolution": "1080x1920", "aspect": "Vertical video (9:16)"},
    ],
    "Generic": [
        {"resolution": "1920x1080", "aspect": "Horizontal video (16:9)"},
        {"resolution": "1080x1920", "aspect": "Vertical video (9:16)"},
        {"resolution": "1080x1080", "aspect": "Square (1:1)"},
        {"resolution": "1440x1080", "aspect": "4:3"},
        {"resolution": "1080x1350", "aspect": "4:5"},
    ],
}

PREVIEW_BOX = (260, 260)


class AvidGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("A.V.I.D. – Audio Visual Integration & Distribution")
        self.root.resizable(False, False)

        self.image_var = tk.StringVar()
        self.audio_var = tk.StringVar()
        self.audio_duration_var = tk.StringVar(value="No audio selected")
        self.output_var = tk.StringVar()
        self.platform_var = tk.StringVar()
        self.aspect_ratio_var = tk.StringVar()
        self.resolution_var = tk.StringVar()
        self.audio_bitrate_var = tk.StringVar(value="128k")
        self.fps_var = tk.StringVar(value="30")
        self.flip_horizontal_var = tk.BooleanVar(value=False)
        self.flip_vertical_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Select files and settings.")

        self.preview_photo: ImageTk.PhotoImage | None = None
        self.preview_after_id: str | None = None
        self.render_stop_event: threading.Event | None = None
        self.render_in_progress = False
        self.closing = False
        self.command_tray_open = False
        self.audio_duration_seconds: float | None = None
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_text_var = tk.StringVar(value="Idle")

        outer = ttk.Frame(root, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")

        controls = ttk.Frame(outer)
        controls.grid(row=0, column=0, sticky="nw")

        preview_panel = ttk.LabelFrame(outer, text="Preview", padding=12)
        preview_panel.grid(row=0, column=1, sticky="n", padx=(16, 0))

        ttk.Label(controls, textvariable=self.status_var, wraplength=420).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )

        self._build_row(controls, 1, "Image", self.image_var, self.pick_image)
        self._build_row(controls, 2, "Audio", self.audio_var, self.pick_audio)
        ttk.Label(controls, text="Audio duration").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Label(controls, textvariable=self.audio_duration_var).grid(row=3, column=1, columnspan=2, sticky="w", pady=4)
        self._build_row(controls, 4, "Output (.mp4)", self.output_var, self.pick_output)

        ttk.Label(controls, text="Social media outlet").grid(row=5, column=0, sticky="w", pady=4)
        self.platform_combo = ttk.Combobox(
            controls,
            textvariable=self.platform_var,
            values=list(PLATFORM_FORMATS),
            state="readonly",
            width=28,
        )
        self.platform_combo.grid(row=5, column=1, sticky="w", pady=4)
        self.platform_combo.bind("<<ComboboxSelected>>", self._on_platform_change)

        ttk.Label(controls, text="Aspect ratio").grid(row=6, column=0, sticky="w", pady=4)
        self.aspect_ratio_combo = ttk.Combobox(
            controls,
            textvariable=self.aspect_ratio_var,
            state="readonly",
            width=28,
        )
        self.aspect_ratio_combo.grid(row=6, column=1, sticky="w", pady=4)
        self.aspect_ratio_combo.bind("<<ComboboxSelected>>", self._on_aspect_ratio_change)

        ttk.Label(controls, text="Resolution").grid(row=7, column=0, sticky="w", pady=4)
        self.resolution_combo = ttk.Combobox(
            controls,
            textvariable=self.resolution_var,
            state="readonly",
            width=28,
        )
        self.resolution_combo.grid(row=7, column=1, sticky="w", pady=4)
        self.resolution_combo.bind("<<ComboboxSelected>>", self._on_resolution_change)

        ttk.Label(controls, text="Audio bitrate").grid(row=8, column=0, sticky="w", pady=4)
        ttk.Entry(controls, textvariable=self.audio_bitrate_var, width=20).grid(row=8, column=1, sticky="w", pady=4)

        ttk.Label(controls, text="FPS").grid(row=9, column=0, sticky="w", pady=4)
        ttk.Entry(controls, textvariable=self.fps_var, width=20).grid(row=9, column=1, sticky="w", pady=4)

        flip_controls = ttk.Frame(controls)
        flip_controls.grid(row=10, column=1, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(flip_controls, text="Flip horizontally", variable=self.flip_horizontal_var).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Checkbutton(flip_controls, text="Flip vertically", variable=self.flip_vertical_var).grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )

        self.progress_bar = ttk.Progressbar(
            controls,
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
            length=360,
        )
        self.progress_bar.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(12, 6))
        ttk.Label(controls, textvariable=self.progress_text_var).grid(row=12, column=0, columnspan=3, sticky="w")

        self.render_button = ttk.Button(controls, text="Create Video", command=self.on_render)
        self.render_button.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(6, 6))

        self.preview_label = ttk.Label(preview_panel, text="Choose an image to see the styled preview.", anchor="center")
        self.preview_label.grid(row=0, column=0)

        self.preview_meta_var = tk.StringVar(value="No preview available")
        ttk.Label(preview_panel, textvariable=self.preview_meta_var, justify="center").grid(
            row=1, column=0, pady=(10, 0)
        )

        self.command_toggle_button = ttk.Button(controls, text="Show FFmpeg Console", command=self.toggle_command_tray)
        self.command_toggle_button.grid(row=13, column=2, sticky="ew", padx=(6, 0), pady=(6, 6))

        self.command_tray = ttk.Frame(outer)
        self.command_output = scrolledtext.ScrolledText(self.command_tray, width=95, height=10, state="disabled")
        self.command_output.grid(row=0, column=0, sticky="ew")

        self.platform_var.set("Instagram")
        self._update_aspect_ratio_options()
        self._bind_preview_updates()
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.root.after(150, self._check_ffmpeg_on_launch)

    def _build_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        var: tk.StringVar,
        button_command,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=var, width=50).grid(row=row, column=1, sticky="w", pady=4)
        ttk.Button(parent, text="Browse", command=button_command).grid(row=row, column=2, padx=(6, 0), pady=4)

    def _bind_preview_updates(self) -> None:
        for variable in (
            self.image_var,
            self.platform_var,
            self.aspect_ratio_var,
            self.resolution_var,
            self.flip_horizontal_var,
            self.flip_vertical_var,
        ):
            variable.trace_add("write", self._schedule_preview_update)

    def _run_on_ui_thread(self, callback) -> None:
        if self.closing:
            return
        try:
            self.root.after(0, callback)
        except tk.TclError:
            pass

    def _on_window_close(self) -> None:
        self.closing = True
        if self.render_stop_event is not None:
            self.render_stop_event.set()
        self.root.destroy()

    def _schedule_preview_update(self, *_args: object) -> None:
        if self.preview_after_id is not None:
            self.root.after_cancel(self.preview_after_id)
        self.preview_after_id = self.root.after(150, self._refresh_preview)

    def _formats_for_platform(self) -> list[dict[str, str]]:
        return PLATFORM_FORMATS.get(self.platform_var.get(), [])

    def _update_aspect_ratio_options(self) -> None:
        aspect_values = []
        seen = set()
        for video_format in self._formats_for_platform():
            aspect = video_format["aspect"]
            if aspect not in seen:
                seen.add(aspect)
                aspect_values.append(aspect)

        self.aspect_ratio_combo["values"] = aspect_values
        if self.aspect_ratio_var.get() not in aspect_values:
            self.aspect_ratio_var.set(aspect_values[0] if aspect_values else "")
        self._update_resolution_options()

    def _update_resolution_options(self) -> None:
        selected_aspect = self.aspect_ratio_var.get()
        resolution_values = [
            video_format["resolution"]
            for video_format in self._formats_for_platform()
            if video_format["aspect"] == selected_aspect
        ]
        self.resolution_combo["values"] = resolution_values
        if self.resolution_var.get() not in resolution_values:
            self.resolution_var.set(resolution_values[0] if resolution_values else "")

    def _on_platform_change(self, _event: object) -> None:
        self._update_aspect_ratio_options()

    def _on_aspect_ratio_change(self, _event: object) -> None:
        self._update_resolution_options()

    def _on_resolution_change(self, _event: object) -> None:
        self._schedule_preview_update()

    def _selected_output_size(self) -> tuple[int, int] | None:
        resolution = self.resolution_var.get().strip()
        if not resolution:
            return None
        try:
            return parse_size(resolution)
        except Exception:
            return None

    def _preview_output_size(self, width: int, height: int) -> tuple[int, int]:
        max_w, max_h = PREVIEW_BOX
        scale = min(max_w / width, max_h / height)
        return max(1, int(width * scale)), max(1, int(height * scale))

    def _format_seconds(self, total_seconds: float | None) -> str:
        if total_seconds is None:
            return "--:--"
        rounded = max(0, int(round(total_seconds)))
        minutes, seconds = divmod(rounded, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _set_audio_duration(self, audio_path: Path, duration: float | None) -> None:
        if Path(self.audio_var.get().strip()) != audio_path:
            return

        self.audio_duration_seconds = duration
        if duration is None:
            self.audio_duration_var.set("Duration unavailable")
            return

        self.audio_duration_var.set(self._format_seconds(duration))

    def _load_audio_duration(self, audio_path: Path) -> None:
        duration = get_media_duration(audio_path)
        self._run_on_ui_thread(lambda: self._set_audio_duration(audio_path, duration))

    def toggle_command_tray(self) -> None:
        self.command_tray_open = not self.command_tray_open
        if self.command_tray_open:
            self.command_tray.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
            self.command_toggle_button.configure(text="Hide FFmpeg Console")
        else:
            self.command_tray.grid_remove()
            self.command_toggle_button.configure(text="Show FFmpeg Console")

    def _reset_command_output(self) -> None:
        self.command_output.configure(state="normal")
        self.command_output.delete("1.0", tk.END)
        self.command_output.configure(state="disabled")

    def _append_command_output(self, line: str) -> None:
        self.command_output.configure(state="normal")
        self.command_output.insert(tk.END, line + "\n")
        self.command_output.see(tk.END)
        self.command_output.configure(state="disabled")

    def _enqueue_command_output(self, line: str) -> None:
        self._run_on_ui_thread(lambda: self._append_command_output(line))

    def _handle_progress_update(self, progress: dict[str, float | str | None]) -> None:
        self._run_on_ui_thread(lambda: self._apply_progress_update(progress))

    def _apply_progress_update(self, progress: dict[str, float | str | None]) -> None:
        fraction = progress.get("fraction")
        eta_seconds = progress.get("eta_seconds")
        progress_seconds = progress.get("progress_seconds")
        duration_seconds = progress.get("duration_seconds")

        if isinstance(fraction, (int, float)):
            percent = max(0.0, min(float(fraction) * 100.0, 100.0))
            self.progress_var.set(percent)
        if isinstance(progress_seconds, (int, float)) and isinstance(duration_seconds, (int, float)):
            self.progress_text_var.set(
                f"{self.progress_var.get():.0f}%  |  {self._format_seconds(float(progress_seconds))} / "
                f"{self._format_seconds(float(duration_seconds))}  |  ETA {self._format_seconds(float(eta_seconds) if isinstance(eta_seconds, (int, float)) else None)}"
            )
            self.status_var.set("Rendering video with FFmpeg...")
        else:
            self.progress_text_var.set("Rendering video...")

    def _refresh_preview(self) -> None:
        self.preview_after_id = None
        image_text = self.image_var.get().strip()
        output_size = self._selected_output_size()
        if not image_text or output_size is None:
            self.preview_label.configure(image="", text="Choose an image to see the styled preview.")
            self.preview_meta_var.set("No preview available")
            self.preview_photo = None
            return

        image_path = Path(image_text)
        if not image_path.exists():
            self.preview_label.configure(image="", text="Image file not found.")
            self.preview_meta_var.set("No preview available")
            self.preview_photo = None
            return

        preview_size = self._preview_output_size(*output_size)
        try:
            preview_image = build_composite(
                image_path=image_path,
                output_size=preview_size,
                flip_horizontal=self.flip_horizontal_var.get(),
                flip_vertical=self.flip_vertical_var.get(),
            )
            self.preview_photo = ImageTk.PhotoImage(preview_image)
            self.preview_label.configure(image=self.preview_photo, text="")
            self.preview_meta_var.set(
                f"{self.aspect_ratio_var.get()}\n{self.resolution_var.get()} for {self.platform_var.get()}"
            )
        except Exception as exc:  # noqa: BLE001
            self.preview_label.configure(image="", text="Preview unavailable.")
            self.preview_meta_var.set(str(exc))
            self.preview_photo = None

    def pick_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.tiff"), ("All files", "*.*")],
        )
        if path:
            self.image_var.set(path)

    def pick_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Select audio",
            filetypes=[("Audio files", "*.wav *.mp3 *.m4a *.aac *.flac"), ("All files", "*.*")],
        )
        if path:
            self.audio_var.set(path)
            self.audio_duration_seconds = None
            self.audio_duration_var.set("Reading duration...")
            thread = threading.Thread(target=self._load_audio_duration, args=(Path(path),), daemon=True)
            thread.start()

    def pick_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save output video",
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
        )
        if path:
            self.output_var.set(path)

    def _check_ffmpeg_on_launch(self) -> None:
        ffmpeg_path, source = find_ffmpeg()
        if ffmpeg_path is not None:
            self.status_var.set(f"FFmpeg ready ({source}): {ffmpeg_path}")
            return

        details = ffmpeg_setup_details()
        download_url = details["downloads"][0]
        message = (
            "FFmpeg was not found.\n\n"
            f"Platform: {details['platform']} ({details['architecture']})\n"
            f"Expected bundled binary: {details['bundle_target']}\n\n"
            "To use A.V.I.D.:\n"
            "1. Download the current FFmpeg build for your platform.\n"
            "2. Extract the ffmpeg executable.\n"
            "3. Either install it system-wide or place it at the bundled path shown above.\n\n"
            "Open the download page now?"
        )
        should_open = messagebox.askyesno("A.V.I.D. FFmpeg Setup", message)
        self.status_var.set("FFmpeg missing. Install or bundle FFmpeg before rendering.")
        if should_open:
            webbrowser.open(download_url)
            for extra_url in details["downloads"][1:]:
                if messagebox.askyesno("A.V.I.D. FFmpeg Setup", "Open another recommended FFmpeg download page?"):
                    webbrowser.open(extra_url)

    def on_render(self) -> None:
        try:
            image_path = Path(self.image_var.get().strip())
            audio_path = Path(self.audio_var.get().strip())
            output_path = Path(self.output_var.get().strip())
            output_size = parse_size(self.resolution_var.get().strip())
            fps = int(self.fps_var.get().strip())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Invalid settings", str(exc))
            return

        if not str(image_path) or not str(audio_path) or not str(output_path):
            messagebox.showerror("Missing files", "Please select image, audio, and output paths.")
            return

        if not self.platform_var.get() or not self.aspect_ratio_var.get() or not self.resolution_var.get():
            messagebox.showerror("Missing format", "Please select a platform, aspect ratio, and resolution.")
            return

        self.render_in_progress = True
        self.render_stop_event = threading.Event()
        self.progress_var.set(2.0)
        self.progress_text_var.set("Preparing render...")
        self.render_button.configure(text="Stop Video Creation", command=self.stop_render)
        self.render_button.state(["!disabled"])
        self.status_var.set("Preparing video. Click stop to cancel.")
        self._reset_command_output()
        if not self.command_tray_open:
            self.toggle_command_tray()

        thread = threading.Thread(
            target=self._render_worker,
            args=(
                image_path,
                audio_path,
                output_path,
                output_size,
                self.audio_bitrate_var.get().strip(),
                fps,
                self.flip_horizontal_var.get(),
                self.flip_vertical_var.get(),
                self.render_stop_event,
            ),
            daemon=True,
        )
        thread.start()

    def stop_render(self) -> None:
        if self.render_stop_event is None:
            return
        self.render_stop_event.set()
        self.render_button.state(["disabled"])
        self.render_button.configure(text="Stopping...")
        self.status_var.set("Stopping video creation...")

    def _render_worker(
        self,
        image_path: Path,
        audio_path: Path,
        output_path: Path,
        output_size: tuple[int, int],
        audio_bitrate: str,
        fps: int,
        flip_horizontal: bool,
        flip_vertical: bool,
        stop_event: threading.Event,
    ) -> None:
        try:
            self._enqueue_command_output("Checking FFmpeg availability...")
            ffmpeg_path, ffmpeg_source = find_ffmpeg()
            if ffmpeg_path is None:
                details = ffmpeg_setup_details()
                self._enqueue_command_output("FFmpeg not found. Render cannot start.")
                self._enqueue_command_output(f"Expected bundled path: {details['bundle_target']}")
                self._enqueue_command_output("Install FFmpeg or rebuild A.V.I.D. with bundled ffmpeg and ffprobe binaries.")
            else:
                self._enqueue_command_output(f"FFmpeg ready ({ffmpeg_source}): {ffmpeg_path}")

            ffprobe_path, ffprobe_source = find_ffprobe()
            if ffprobe_path is None:
                self._enqueue_command_output("ffprobe not found. ETA may be unavailable, but rendering can continue.")
            else:
                self._enqueue_command_output(f"ffprobe ready ({ffprobe_source}): {ffprobe_path}")

            create_video(
                image_path=image_path,
                audio_path=audio_path,
                output_path=output_path,
                output_size=output_size,
                flip_horizontal=flip_horizontal,
                flip_vertical=flip_vertical,
                audio_bitrate=audio_bitrate,
                fps=fps,
                stop_event=stop_event,
                progress_callback=self._handle_progress_update,
                command_callback=self._enqueue_command_output,
            )
            self._run_on_ui_thread(lambda: self._render_done(f"Done: {output_path}", success=True))
        except RenderCancelledError as exc:
            msg = str(exc)
            self._run_on_ui_thread(lambda m=msg: self._render_done(m, success=False, cancelled=True))
        except Exception as exc:  # noqa: BLE001
            msg = f"Error: {exc}"
            self._run_on_ui_thread(lambda m=msg: self._render_done(m, success=False))

    def _render_done(self, status: str, success: bool, cancelled: bool = False) -> None:
        self.render_in_progress = False
        self.render_stop_event = None
        self.progress_var.set(100.0 if success else 0.0)
        self.progress_text_var.set("Complete" if success else ("Stopped" if cancelled else "Idle"))
        self.render_button.state(["!disabled"])
        self.render_button.configure(text="Create Video", command=self.on_render)
        self.status_var.set(status)

        if success:
            messagebox.showinfo("A.V.I.D. – Audio Visual Integration & Distribution", status)
        elif cancelled:
            messagebox.showwarning("A.V.I.D. – Audio Visual Integration & Distribution", status)
        else:
            messagebox.showerror("A.V.I.D. – Audio Visual Integration & Distribution", status)


def main() -> int:
    root = tk.Tk()
    AvidGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
