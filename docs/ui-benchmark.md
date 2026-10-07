# Local macOS UI comparison

`script/benchmark_ui.sh` compares the two arm64 **Release** ZIPs:
production SwiftUI/AppKit and the internal Qt Widgets reference. It writes
every run to a fresh timestamped `build/benchmark-results/` directory. No changes
to application behavior or normal user files are needed. The directory is Git-ignored.

```sh
./script/benchmark_ui.sh --quick
./script/benchmark_ui.sh --standard
./script/benchmark_ui.sh --deep
./script/benchmark_ui.sh --quick --candidate qt --workload engine --engine-repeats 5
python3 script/benchmark_ui_resources.py build/benchmark-results/<run-directory>
```

Run on macOS arm64 with the packages built. The runner extracts each
ZIP, verifies the packaged engine identity, generates synthetic fixtures, and
rotates candidate order. It launches the extracted `.app` bundles with
`/usr/bin/open -n -F -g`, identifies only the newly launched executable, and
terminates only those benchmark-owned PIDs. Each app receives a temporary
HOME profile. No unrelated app is closed. The ordinary OS cache remains warm.

`--quick` takes one first-profile launch plus three ordinary launches per app,
8 seconds of process idle samples, and one engine warm-up plus two matched
10-second exports. `--standard` uses 20 ordinary launches, 60 seconds of idle,
and five exports. `--deep` uses 40 launches, 180 seconds idle, and ten exports.
`--launches`, `--idle-seconds`, `--engine-repeats`, and `--sample-interval`
override counts; `--workload` and `--candidate` can be repeated. Results include
raw CSV/JSON, package and fixture hashes, and a generated `report.md`.
The separate resource diagnostic samples the Rust engine and FFmpeg process
tree during a 60-second synthetic export. Run it after a main benchmark, then
regenerate the report with
`python3 script/benchmark_ui_report.py build/benchmark-results/<run-directory>`.
Its timing includes the cost of memory sampling and is not a headline result.

The runner measures when a process first appears; it does **not** measure when
the window is presented or ready for input. Its `footprint` samples give macOS
physical footprint and `ps` gives RSS. `footprint` is heavier than the launch
poll, so those series are separate. Engine exports are performed through the
*packaged* Rust binary with identical input, settings, and validated H.264/AAC
output. They measure shared work, not GUI integration. The report marks
unmeasured UI latency, frame pacing, energy, and retention explicitly.

For a visual workflow check, open each extracted package in its result folder,
use the paths in `fixtures.json`, set 1920×1080, 30 fps, and 128k AAC, and
select separate output paths inside that same result folder. Check that image,
audio duration, preview, progress, cancellation, and completed output are
visible. Save any observations outside the timed launch/idle run. Both SwiftUI
and Qt request an approximately 360-pixel preview and suggest output paths.

The current macOS benchmark evidence is under
[`build/benchmark-results/`](../build/benchmark-results/). These results cannot
establish Windows or Linux performance. A toolkit choice should also consider
accessibility, functional gaps, update support, and maintenance, which package
size and idle memory alone do not decide.
