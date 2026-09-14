#!/usr/bin/env python3
"""Time preserved baseline and candidate ATIV engines, including tool discovery and publication."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path
from benchmark_export import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "candidate", "ffmpeg", "ffprobe", "image", "audio", "directory"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--reference-video", type=Path, required=True, help="Equal-duration per-frame output from benchmark_export.py")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.rounds < 1:
        parser.error("Use at least one measured round")
    outputs = [root / name for name in ("baseline.mp4", "current.mp4", "simple.mp4", "results.json")]
    inputs = [args.baseline, args.candidate, args.ffmpeg, args.ffprobe, args.image, args.audio, args.reference_video]
    if any(source.resolve() == output or (output.exists() and source.samefile(output)) for source in inputs for output in outputs):
        parser.error("Inputs and reference video must not be benchmark outputs")
    rows = []
    _, audio_info = run([args.ffprobe.resolve(), "-v", "error", "-show_format", "-of", "json", args.audio.resolve()])
    duration = float(json.loads(audio_info)["format"]["duration"])
    modes = ["baseline", "current", "simple"]
    for iteration in range(0 if args.validate_only else args.rounds + 1):
        for mode in modes[iteration % 3:] + modes[:iteration % 3]:
            engine = args.baseline if mode == "baseline" else args.candidate
            command = [engine.resolve(), "render", "--ffmpeg", args.ffmpeg.resolve(), "--ffprobe", args.ffprobe.resolve(), "--image", args.image.resolve(), "--audio", args.audio.resolve(), "--output", root / f"{mode}.mp4", "--width", args.width, "--height", args.height, "--fps", args.fps]
            if mode != "baseline":
                command += ["--render-mode", mode]
            elapsed, stdout = run(command)
            events = [json.loads(line) for line in stdout.splitlines()]
            assert {"event": "stage", "stage": "complete"} in events
            if mode != "baseline":
                timing = next(e for e in events if e["event"] == "timing")
                assert timing["success"] and 0 < timing["wall_seconds"] <= elapsed
                assert timing["render_mode"] == mode
            row = dict(mode=mode, warmup=iteration == 0, wall_seconds=elapsed, command=[str(a) for a in command], events=events)
            rows.append(row)
            print(json.dumps({k: row[k] for k in ("mode", "warmup", "wall_seconds")}), flush=True)
    report = json.loads((root / "results.json").read_text()) if args.validate_only else dict(settings=vars(args), media_seconds=duration, runs=rows,
                  binary_sha256={key: hashlib.sha256(getattr(args, key).read_bytes()).hexdigest() for key in ("baseline", "candidate")},
                  median_seconds={m: statistics.median(r["wall_seconds"] for r in rows if r["mode"] == m and not r["warmup"]) for m in modes})
    (root / "results.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    validation = {}
    frames = {}
    for mode in modes:
        output = root / f"{mode}.mp4"
        _, raw = run([args.ffprobe.resolve(), "-v", "error", "-show_streams", "-show_format", "-of", "json", output])
        info = json.loads(raw)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
        assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
        assert (video["width"], video["height"]) == (args.width, args.height)
        assert video["avg_frame_rate"] == f"{args.fps}/1"
        assert audio["codec_name"] == "aac" and abs(float(audio["duration"]) - duration) < 0.05
        _, raw = run([args.ffmpeg.resolve(), "-v", "error", "-i", output, "-map", "0:v:0", "-f", "framemd5", "-"])
        frames[mode] = [line for line in raw.splitlines() if not line.startswith("#")]
        validation[mode] = info
    assert len(frames["simple"]) == round(duration * args.fps)
    # Legacy -shortest can produce a variable silent video tail; compare the actual audio interval.
    # Changing the endpoint changes x264 lookahead/rate control near EOF.
    # Compare exactly with the per-frame control encoded to the same endpoint.
    _, raw = run([args.ffmpeg.resolve(), "-v", "error", "-i", args.reference_video.resolve(), "-map", "0:v:0", "-f", "framemd5", "-"])
    reference = [line for line in raw.splitlines() if not line.startswith("#")]
    assert frames["simple"] == reference, "Integrated simple output differs from equal-duration per-frame control"
    report["reference_video"] = str(args.reference_video.resolve())
    report["baseline_mismatched_frames_due_to_different_endpoint"] = sum(a != b for a, b in zip(frames["simple"], frames["baseline"]))
    report["validation"] = validation
    report["decoded_pixels_and_timestamps_match_equal_duration_control"] = True
    (root / "results.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report["median_seconds"]), flush=True)


if __name__ == "__main__":
    main()
