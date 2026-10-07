#!/usr/bin/env python3
"""Verify native engine process integration against created smoke media fixtures."""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 test_engine_fixtures.py FIXTURES_DIR")

    fixtures = Path(sys.argv[1]).resolve()
    engine = os.environ.get("ATIV_ENGINE_PATH")
    if not engine or not Path(engine).is_file():
        sys.exit(f"ATIV_ENGINE_PATH is unset or missing: {engine}")

    def run_engine(*args, check=True):
        cmd = [str(engine), *args]
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    # 1. Presets check
    presets_proc = run_engine("presets")
    presets_data = json.loads(presets_proc.stdout)
    items = presets_data.get("items", [])
    if len(items) != 27:
        sys.exit(f"Expected 27 presets, got {len(items)}")

    # 2. Missing input error handling
    missing_proc = run_engine("probe", "--audio", str(fixtures / "missing.wav"), check=False)
    if missing_proc.returncode == 0:
        sys.exit("Probe unexpectedly succeeded on missing file")

    # 3. Probe audio duration
    audio = fixtures / "audio ü.wav"
    probe_proc = run_engine("probe", "--audio", str(audio))
    probe_data = json.loads(probe_proc.stdout)
    duration = probe_data.get("duration_seconds", 0)
    if abs(duration - 1.0) > 0.05:
        sys.exit(f"Unexpected audio duration: {duration}")

    # 4. Preview generation
    image = fixtures / "artwork ü.ppm"
    preview_out = fixtures / "native-preview.png"
    run_engine("preview", "--image", str(image), "--output", str(preview_out),
               "--width", "160", "--height", "90", "--flip-horizontal", "--flip-vertical")
    if not preview_out.is_file() or preview_out.stat().st_size == 0:
        sys.exit("Preview generation failed or produced empty file")

    # 5. Render export
    video_out = fixtures / "native-export.mp4"
    render_proc = run_engine("render", "--image", str(image), "--audio", str(audio),
                             "--output", str(video_out), "--width", "160", "--height", "90",
                             "--audio-bitrate", "128k", "--fps", "30",
                             "--flip-horizontal")
    if not video_out.is_file() or video_out.stat().st_size < 100:
        sys.exit("Render export failed or produced invalid file")

    print("Native process integration passed: presets, probe, preview, and export verified.")

if __name__ == "__main__":
    main()
