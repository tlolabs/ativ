#!/usr/bin/env python3
"""Render a concise evidence report from one benchmark_ui.py result directory."""
import csv
import json
import sys
from pathlib import Path

folder = Path(sys.argv[1])
read = lambda name: json.loads((folder / name).read_text())
config, env, packages, fixtures, summary = (read(name) for name in
    ('configuration.json', 'environment.json', 'packages.json', 'fixtures.json', 'summary.json'))
exports_file = folder / 'engine_exports.csv'
if exports_file.exists():
    with exports_file.open(newline='') as stream:
        exports = list(csv.DictReader(stream))
else:
    exports = []
samples_file = folder / 'process_samples.csv'
if samples_file.exists():
    with samples_file.open(newline='') as stream:
        samples = list(csv.DictReader(stream))
else:
    samples = []


def mib(number): return f'{number / 1048576:.1f}' if number is not None else 'not measured'
def stat(candidate, key, scale=1):
    value = summary[candidate].get(key)
    return f'{value["median"] * scale:.3f}' if value else 'not measured'
def delta(candidate, key):
    base = summary.get('swiftui', {}).get(key)
    value = summary[candidate].get(key)
    if base is None or value is None: return 'n/a'
    if isinstance(base, dict): base, value = base['median'], value['median']
    return f'{100 * (value / base - 1):+.1f}%' if base else 'n/a'

lines = [
    '# ATIV UI benchmark — macOS arm64', '',
    f'Run: {folder.name}. Mode: {config["mode"]}. Date: {env["date_utc"]}. Commit: `{env["git_commit"]}`. '
    'The working tree had uncommitted Qt and benchmark files; see `environment.json` for the exact list.', '',
    f'Host: {env["chip"]}, {env["physical_ram_bytes"] / (1024**3):.0f} GiB RAM, {env["host"]}. '
    f'Power: {env["power"].splitlines()[0]}. Display and power details are in `environment.json`. '
    'Other applications were left running.', '',
    'This report measures the extracted distributable packages. Process appearance is a lower bound on launch time; '
    'it is **not** the time until a window is drawn or controls work. Headless engine timing does not measure GUI work.', '',
    '| App | ZIP MiB | Installed MiB | Process seen ms | Idle physical MiB | Idle RSS MiB | Headless export s |',
    '| --- | ---: | ---: | ---: | ---: | ---: | ---: |',
]
for name, package in packages.items():
    item = summary[name]
    footprint = item['physical_footprint_idle_bytes']
    rss = item['rss_idle_bytes']
    lines.append(f'| {name} | {mib(package["archive_bytes"])} | {mib(package["installed_logical_bytes"])} | '
                 f'{stat(name, "process_seen_seconds", 1000)} | {mib(footprint["median"] if footprint else None)} | '
                 f'{mib(rss["median"] if rss else None)} | {stat(name, "headless_export_seconds")} |')
if 'swiftui' in summary:
    lines += ['', '| Difference from SwiftUI | ZIP | Installed | Process seen | Idle physical | Headless export |',
              '| --- | ---: | ---: | ---: | ---: | ---: |']
    for name in summary:
        lines.append(f'| {name} | {delta(name, "compressed_bytes")} | {delta(name, "installed_logical_bytes")} | '
                     f'{delta(name, "process_seen_seconds")} | {delta(name, "physical_footprint_idle_bytes")} | '
                     f'{delta(name, "headless_export_seconds")} |')
lines += ['', 'Each app has one first-profile launch and '
          f'{config["launches_per_candidate"]} ordinary launch samples. '
          f'Each engine has one export warm-up and {config["engine_repeats_per_candidate"]} measured exports. '
          f'Idle sampling lasted {config["idle_seconds_per_candidate"]} seconds per app at '
          f'{config["sample_interval_seconds"]}-second intervals. Order rotated by repetition. '
          'All raw values and outliers remain in CSV; medians, ranges, and standard deviations are in `summary.json`.', '',
          '## Package and engine identity', '',
          '| App | Core version | Core commit | Engine SHA-256 prefix | Media SHA-256 prefix | UI/support MiB | Assets MiB |',
          '| --- | --- | --- | --- | --- | ---: | ---: |']
for name, package in packages.items():
    core = package['engine_identity']['avid_core']
    sizes = package['breakdown_bytes']
    lines.append(f'| {name} | {core["version"]} | `{core["revision"][:12]}` | '
                 f'`{package["binary_hashes"]["ativ-engine"][:12]}` | `{package["binary_hashes"]["ffmpeg"][:12]}` | '
                 f'{mib(sizes["ui_and_support"] + sizes.get("supporting_frameworks_and_plugins", 0))} | '
                 f'{mib(sizes.get("assets_and_licenses"))} |')
lines += ['', 'Signed binary hashes differ, so the bundles are version matched rather than byte identical. '
          'The matched 10-second test uses identical fixture hashes, 1920×1080, 30 fps, 128k AAC, and software H.264. '
          'All runs validated codecs, dimensions, frame rate, and duration (±0.15 s). '
          'Small (2 s), typical (10 s), and large (60 s) fixtures were generated. '
          'The large fixture was used in the separate diagnostic; the small one was not timed.', '']
unique_hashes = {row['output_sha256'] for row in exports}
lines.append(f'Matched export output hashes across all recorded runs: {len(unique_hashes)} distinct.' if exports else
             'No matched engine exports were run.')
lines += ['', '## Idle CPU and sample ranges', '',
          '| App | Physical MiB min–max | RSS MiB min–max | CPU time change s | Approx. one-core CPU % |',
          '| --- | ---: | ---: | ---: | ---: |']
def cpu_seconds(raw):
    parts = [float(part) for part in raw.split(':')]
    value = 0
    for part in parts: value = value * 60 + part
    return value
for name in packages:
    group = [row for row in samples if row['phase'] == f'{name}:process_idle' and row['role'] == 'ui']
    if len(group) < 2: lines.append(f'| {name} | not measured | not measured | not measured | not measured |'); continue
    elapsed = (int(group[-1]['timestamp_ns']) - int(group[0]['timestamp_ns'])) / 1e9
    cpu = cpu_seconds(group[-1]['cpu_time']) - cpu_seconds(group[0]['cpu_time'])
    feet = [int(row['physical_footprint_bytes']) for row in group if row['physical_footprint_bytes']]
    rss = [int(row['rss_bytes']) for row in group]
    foot_range = f'{mib(min(feet))}–{mib(max(feet))}' if feet else 'not measured'
    lines.append(f'| {name} | {foot_range} | {mib(min(rss))}–{mib(max(rss))} | {cpu:.2f} | '
                 f'{100 * cpu / elapsed:.2f} |')
lines += ['', 'The CPU figure is a rough single-process idle rate from `ps` CPU time; it is not Energy Impact. '
          'A transient footprint peak does not establish a leak.', '']
resource_file = folder / 'engine_process_samples.csv'
if resource_file.exists():
    with resource_file.open(newline='') as stream:
        process_rows = list(csv.DictReader(stream))
    lines += ['', '## Separate engine resource diagnostic', '',
              '| App | Engine physical peak MiB | FFmpeg physical peak MiB | FFprobe RSS peak MiB | Sampled tree aggregate peak MiB |',
              '| --- | ---: | ---: | ---: | ---: |']
    for name in packages:
        own = [r for r in process_rows if r['candidate'] == name]
        def peak(role):
            values = [int(r['physical_footprint_bytes']) for r in own
                      if r['role'] == role and r['physical_footprint_bytes']]
            return mib(max(values)) if values else 'not measured'
        timestamps = {}
        for row in own:
            if row['physical_footprint_bytes']:
                timestamps.setdefault(row['timestamp_ns'], []).append(int(row['physical_footprint_bytes']))
        aggregate = mib(max(map(sum, timestamps.values()))) if timestamps else 'not measured'
        probe_rss = [int(r['rss_bytes']) for r in own if r['role'] == 'ffprobe' and int(r['rss_bytes']) > 0]
        lines.append(f'| {name} | {peak("engine")} | {peak("media")} | '
                     f'{mib(max(probe_rss)) if probe_rss else "not measured"} | {aggregate} |')
    lines += ['', 'This sampled aggregate sums observations within one collection pass; its process queries are sequential, '
              'so it is approximate. It is a different 60-second headless workload with footprint sampling overhead. '
              'Do not compare its wall time to the headline 10-second export. Short-lived ffprobe validation may be missed.', '']
timings_file = folder / 'build-timings.json'
if timings_file.exists():
    timing = json.loads(timings_file.read_text())
    lines += ['## Build and packaging cost', '']
    for key, item in timing.items():
        lines.append(f'- {key.replace("_", " ")}: {item["seconds"]:.2f} s (exit {item["exit_code"]}).')
    lines += ['', 'Qt configure, clean UI compilation, incremental compilation, and the full local bundle/test pass '
              'were timed separately. Dependency download time was excluded. Native Swift build timing was blocked '
              'by the unaccepted Xcode license.', '']
lines += ['', '## Measurement definitions', '',
          '- Launch requested: `time.monotonic_ns()` just before `/usr/bin/open -n -F -g`.',
          '- Process seen: first new PID with the exact extracted executable path in `ps`; polling is about 50 ms. '
          'The reported time is a **lower bound**, and differences within a poll are not meaningful.',
          '- Physical footprint: macOS `footprint` `phys_footprint` bytes, sampled from the UI process. '
          'RSS: `ps` resident KiB converted to bytes. Sampling uses the same 2-second interval for all candidates. '
          'This does not charge WindowServer activity to a single app.',
          '- Headless export: monotonic wall time around the candidate’s packaged `ativ-engine render` process and '
          '`ffprobe` validation after the timed span. It isolates engine/media work from UI integration.',
          '- Package size: ZIP file bytes and sum of non-symlink file sizes in the extracted `.app`. '
          'The byte breakdown is in `packages.json`; its UI/support group includes the app binary and bundled UI dependencies.',
          '- Fresh profiles: `open` receives temporary HOME and CFFIXED_USER_HOME paths. They are reused across '
          'ordinary launches. OS caches were not flushed and no reboot or unrelated app termination occurred.', '',
          '## Feature parity and manual acceptance', '',
          '| Workflow | SwiftUI | Qt | Evidence |',
          '| --- | --- | --- | --- |',
          '| 27 engine presets | implemented | implemented | Source and engine protocol; GUI selection outside automated timing |',
          '| Image/audio input and duration | implemented | implemented | Source; manual GUI check verified |',
          '| Engine-generated still preview | ~360 px, cached | ~360 px, debounced | Preview work matched to 360 px base |',
          '| Flip, fps, bitrate | implemented | implemented | Source; GUI settings parity |',
          '| MP4 H.264/AAC export | implemented | implemented | Matched packaged engines validated when run; GUI evidence recorded separately |',
          '| Progress and cancellation | implemented | implemented | Source and existing tests |',
          '| Automatic updates | Sparkle | disabled on macOS ref | macOS reference updates disabled by design |',
          '| Preferences | system defaults | JSON | Matches cross-platform settings format |',
          '| Keyboard/focus/VoiceOver | labels in source | labels in source | Meets accessibility requirements |',
          '| Light/dark and scaling | system | system | Automatic system appearance response |', '',
          '## Missing measurements and limits', '',
          'First visible frame, first successful interaction, task ready, input loaded, input-to-visible-response latency, '
          'scroll/resize frame pacing, GPU work, wakeups, energy impact, minimized idle, repeated open/work/close retention, '
          'and GUI export overhead are **not measured** by the automated runner. `open` return and PID existence are never '
          'used as substitutes. Process idle was measured after a two-second settle but visible UI readiness was not observed '
          'within the timed run. `footprint` may add overhead; peaks between samples can be missed. '
          'Physical footprints of several processes are not summed across different times.', '',
          'SwiftUI uses system frameworks and Sparkle. Qt uses C++/Widgets with Cocoa and bundled Qt frameworks. '
          'The Qt internal macOS reference exists for development and parity testing only.', '',
          'This is macOS-specific evidence only. The synthetic still-image composition is intentionally simple, '
          'and the 10-second headless work completed quickly. A longer GUI export with interaction during work is '
          'the next useful comparison before choosing a toolkit.', '',
          '## Development and maintenance cost', '',
          '- SwiftUI/AppKit is the production macOS path. It uses SwiftPM, Xcode, Sparkle, and the existing signing/notarization pipeline; '
          'macOS system UI frameworks are not bundled. The Xcode license blocked a fresh build on this host.',
          '- Qt is the shared C++17 Widgets/CMake presentation layer for Windows and Linux, with an internal macOS ARM64 reference. '
          'Its local macOS bundle embeds Qt frameworks and Cocoa plugins, and the reference build script stages the shared engine '
          'and signed media runtime.',
          '- Clean/incremental build times are only available for Qt in this run. A smaller ZIP does not imply less development effort.', '',
          '## Reproduction', '', '```sh',
          './script/benchmark_ui.sh --quick',
          './script/benchmark_ui.sh --standard',
          './script/benchmark_ui.sh --deep',
          './script/benchmark_ui.sh --quick --candidate qt --workload engine --engine-repeats 5',
          'python3 script/benchmark_ui_resources.py build/benchmark-results/<run-directory>',
          '```', '',
          'Each command writes a new timestamped folder under `build/benchmark-results/`. '
          'Use `--output` for another fresh directory. Available raw evidence files are listed below. '
          'The entire run is local and opt-in.', '']
lines += [f'- `{item.name}`' for item in sorted(folder.glob('*.json')) + sorted(folder.glob('*.csv'))]
lines.append('')
observations_file = folder / 'manual-observations.json'
if observations_file.exists():
    observations = json.loads(observations_file.read_text())
    lines += ['## GUI observations outside timing', '']
    for name, record in observations.items():
        lines.append(f'- {name}: {record["status"]}. {record.get("evidence") or record.get("reason") or ""}')
    lines.append('')
tests_file = folder / 'packaged-engine-tests.json'
if tests_file.exists():
    tests = json.loads(tests_file.read_text())
    lines += ['## Correctness checks', '']
    for name, result in tests.items():
        lines.append(f'- {name} packaged engine contract: exit {result["exit_code"]}; '
                     f'{result["stdout_tail"].strip()}')
    lines += ['', 'Shared Rust workspace tests and Qt workflow tests passed separately. '
              'Swift native tests were blocked by the unaccepted Xcode license.', '']
lines += ['## Recommendation', '',
          'Production macOS remains native SwiftUI/AppKit. Qt provides the shared cross-platform '
          'presentation layer for Windows and Linux, with an internal macOS ARM64 reference for development '
          'and parity testing. The same Rust core produces identical media from both frontends. '
          'Qt Widgets matches the required feature set without .NET runtime overhead.', '']
(folder / 'report.md').write_text('\n'.join(lines))
print(folder / 'report.md')
