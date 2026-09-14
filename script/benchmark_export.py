#!/usr/bin/env python3
"""Compare identical software H.264 exports; include PNG preparation in wall time."""
import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import time
from pathlib import Path


def run(args):
    start = time.perf_counter()
    result = subprocess.run([str(a) for a in args], stdin=subprocess.DEVNULL, capture_output=True, timeout=1800)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return time.perf_counter() - start, result.stdout.decode(errors="replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--image", type=Path)
    args = parser.parse_args()
    if args.rounds < 1 or not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("Use at least one round and a finite positive duration")
    if not 1 <= args.fps <= 240 or any(n <= 0 or n % 2 for n in (args.width, args.height)):
        parser.error("Use positive even dimensions and 1–240 fps")
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    ff = [args.ffmpeg.resolve(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    art = args.image.resolve() if args.image else root / "artwork.png"
    reserved = [root / name for name in ("audio.wav", "composite.png", "current.mp4", "png.mp4", "cached.mp4", "results.json")]
    if args.image and any(art == p or (p.exists() and art.samefile(p)) for p in reserved):
        parser.error("Source image must not be a generated benchmark output")
    if not args.image:
        run(ff + ["-f", "lavfi", "-i", "testsrc2=s=2400x1600", "-frames:v", "1", art])
    audio = root / "audio.wav"
    run(ff + ["-f", "lavfi", "-i", f"sine=frequency=523:duration={args.seconds}:sample_rate=44100", "-c:a", "pcm_s16le", audio])
    w, h, fps = args.width, args.height, args.fps
    square = min(w, h)
    graph = (f"[0:v]split=2[bgsrc][fgsrc];[bgsrc]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=40[bg];"
             f"[fgsrc]scale={square}:{square}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[video]")
    cached = graph.replace("[0:v]split", "[0:v]trim=end_frame=1,split").replace("[video]", f",loop=loop=-1:size=1:start=0,setpts=N/({fps}*TB)[video]")
    tail = ["-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-t", str(args.seconds), "-movflags", "+faststart", "-f", "mp4"]
    modes = ["current", "png", "cached"]
    rows = []
    for iteration in range(args.rounds + 1):
        for mode in modes[iteration % 3:] + modes[:iteration % 3]:
            output = root / f"{mode}.mp4"
            commands = []
            preparation = 0
            if mode == "png":
                composite = root / "composite.png"
                prepare = ff + ["-i", art, "-filter_complex", graph, "-map", "[video]", "-frames:v", "1", composite]
                preparation, _ = run(prepare)
                commands.append(prepare)
                command = ff + ["-loop", "1", "-framerate", str(fps), "-i", composite, "-i", audio, "-map", "0:v:0", "-map", "1:a:0"]
            else:
                command = ff + (["-loop", "1"] if mode == "current" else []) + ["-framerate", str(fps), "-i", art, "-i", audio, "-filter_complex", graph if mode == "current" else cached, "-map", "[video]", "-map", "1:a:0"]
            command += tail + [output]
            encoding, _ = run(command)
            commands.append(command)
            row = dict(mode=mode, warmup=iteration == 0, preparation_seconds=preparation, encoding_seconds=encoding, wall_seconds=preparation + encoding, commands=[[str(a) for a in c] for c in commands])
            rows.append(row)
            print(json.dumps({k:v for k,v in row.items() if k != "commands"}), flush=True)
    validation = {}
    for mode in modes:
        output = root / f"{mode}.mp4"
        _, info = run([args.ffprobe.resolve(), "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", output])
        info = json.loads(info)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        sound = next(s for s in info["streams"] if s["codec_type"] == "audio")
        assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
        assert (video["width"], video["height"]) == (w, h)
        assert video["avg_frame_rate"] == f"{fps}/1"
        assert int(video["nb_read_frames"]) == round(args.seconds * fps)
        assert sound["codec_name"] == "aac" and sound["sample_rate"] == "44100" and sound["channels"] == 1
        assert abs(float(info["format"]["duration"]) - args.seconds) < 0.1
        _, hashes = run(ff + ["-i", output, "-map", "0:v:0", "-f", "framemd5", "-"])
        validation[mode] = dict(probe=info, decoded_frames=hashes)
    assert validation["current"]["decoded_frames"] == validation["cached"]["decoded_frames"], "Cached output pixels or timestamps differ"
    report = dict(hardware=platform.platform(), ffmpeg=run([args.ffmpeg.resolve(), "-version"])[1].splitlines()[0], settings=vars(args) | {"image_sha256": hashlib.sha256(art.read_bytes()).hexdigest()}, runs=rows, median_seconds={m: statistics.median(r["wall_seconds"] for r in rows if r["mode"] == m and not r["warmup"]) for m in modes}, validation=validation)
    (root / "results.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report["median_seconds"]), flush=True)


if __name__ == "__main__":
    main()
