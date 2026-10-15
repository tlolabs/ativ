# Performance report remediation — 2026-10-14

Local correctness fixes are implemented and tested on macOS arm64. This is not a six-platform clearance: native Windows/Linux/Intel macOS execution and first usable UI timing remain open. Historical performance claims are distinguished below from fresh evidence. No version, dependency, CI policy, update-feed signature requirement, or runtime acquisition policy was changed.

## Revisions, scope, and evidence

Corrective local code commits: `7cc7259b5ea417783edb43e821e9a42f9fb5f5cd` (Handle verification and diagnostic I/O failures safely), `1763fdb48ab286186f7602bdff51a6da7b5e6df3` (Preserve export destinations and bound frontend event streams), `cf92710375941af9e44838420566ab6b7ac7afa3` (Make performance measurements reproducible and evidence based). Each uses the repository identity and a DCO sign-off.

The attachment contains the assignment text. No separate report artifact was present; the checked-in `docs/PERFORMANCE.md` contains the cited numerical claims and optimization descriptions and is the assessed report.

The complete nine-file optimization commit is locally available as `7121cd8dd596b274fe9130e406551cb30cc13162`; its parent is `41b18aa29cccccd55187c3d99f6555779876c195`. All nine reported paths exist. The additional Qt `MainWindow::updateAspects()` change caches the current platform and uses a membership set while retaining first-seen display order; it is sound and retained. The commit changes logging, verification, caches, stream consumption, benchmarks, and this report's predecessor. It does **not** change Core's rendering algorithm or the engine's default render mode.

Work began on `main` at `aba4aa84b919a96697fd9aff5839c224a1dbe8a6`, five commits after the optimization. Those commits include frontend, security, dependency/MSRV, CI reporting, and documentation work. They were preserved. Three preexisting untracked files (`github-actions-audit.md`, `github-actions-inventory.csv`, `github-actions-optimization.md`) were left untouched.

Detached local worktrees under `build/performance-remediation-20261014/{baseline,optimization}` hold the exact parent and optimization revisions. Each has its own Cargo build directory. The corrected build uses `build/performance-remediation-20261014/current-target`; Swift/CMake builds also have separate directories per revision. Builds used the checked-in locks, Cargo offline mode, Rust 1.98.1, full Xcode, Swift release configuration, and CMake Release. The host is Apple Silicon, macOS 27.0.1; detailed host/tool/power/display evidence is in `environment.json` and `ui/environment.json` under that evidence directory.

Fresh bundles contain each revision's rebuilt engine and UI. Supporting runtime resources, frameworks, plugins, icons, licenses, and updater configuration were held constant within each frontend family. Native and Qt templates contain different signed copies/acquisition archives with identical original media binary hashes; signature removal on disposable copies confirms identical executable content. The 60-second revision comparison uses only the native family, including identical runtime metadata. Cross-frontend headless comparisons are not evidence of parser performance. Qt deployment ran on the freshly linked executable; freshly generated Qt bundle metadata replaced the template metadata. Bundles were ad-hoc signed locally, then validated. This compares code with matched supporting package contents; it does not recreate every historical packaging operation. Existing installed/distribution bundles and release archives were not replaced. Runtime attestation/provenance checks were not bypassed. No signing identities or credentials were invented.

Generated media, source snapshots, worktrees, archives, raw timings, package inventories, command/status JSON, and logs remain ignored under `build/performance-remediation-20261014/`. They are newly collected evidence except `historical-evidence.json`, which explicitly copies preexisting historical records. Exact source and executable hashes are recorded in the evidence manifest and benchmark inventories. The retained worktrees and raw logs allow local reproduction without a remote fetch.

## Findings register

| ID/category | Original claim | Independently established behavior/evidence | Disposition and action |
|---|---|---|---|
| A — concurrent verification | Both required media hashes run concurrently; 12.50 → 6.12 ms, 2.04×; corrupted tools rejected | Both workers are started and joined on normal I/O errors; source/pin/provenance/tree checks remain. `join().unwrap()` and infallible `scope.spawn()` could panic outside the structured IPC error path. Fresh matched streaming measurements support approximately twofold hashing throughput, not a twofold reduction in whole-command startup. Real missing/damaged tests exercise both ffmpeg and ffprobe. | **Partially confirmed; corrected.** Retain concurrency. Use fallible scoped thread creation, explicitly join both workers, then propagate results in ffmpeg/ffprobe order. Spawn/join errors map to the existing `media_tools_unavailable` error. Injected worker errors/panics demonstrate both workers finish. |
| B — LazyLock JSON | Immutable pins/spec cached; 807.8× parsing/startup benefit | Only `include_str!` constants and Core's compiled specification are cached. Mutable package metadata is still read and checked each operation. Existing initialization `expect` behavior is retained. Original benchmark amortized its first initialization over 1,000 iterations and compared repeated parse/drop against mostly warm access. `run()` serves one CLI command; `tools()` resolves once on that path. There is no repeated warm pin lookup across UI commands because each starts another engine process. | **Partially supported; application benefit unsupported.** Retain the small immutable cache, measure first initialization separately, and withdraw the implied engine-startup multiplier. Warm microbenchmark ratios are not application speedups. |
| C — SHA-256 hex | “Zero allocations,” 32 allocations removed in both engine and updater; 24.7× | Engine lookup encoding is safe Rust, lowercase, fixed 64-byte output, with leading zeros retained. It allocates one resulting pre-sized String and avoids per-byte temporary Strings. Original per-byte formatting has at least 32 intermediate allocations, plus output growth; total allocation counts were not instrumented. The updater previously used direct `format!("{:x}", digest)`, not the engine's per-byte iterator. Its claimed 32-allocation reduction has no source basis. | **Engine confirmed; allocation wording and updater attribution incorrect.** Retain/test engine encoding. Restore the updater's simpler standard digest formatter. New hex timings are encoding-only and apply to the engine comparison. |
| D — buffered diagnostics/event formatting | Fewer writes, no temporary strings, final logs flushed on drop; “zero-allocation IPC” | `BufWriter` buffers only the diagnostic file. Protocol events still use newline `println!` on Rust's line-buffered stdout. Normal success/error/cancellation returns already drop the writer before main appends a terminal error. Stage/progress `format_args!` avoids those particular intermediate Strings, but `number()` still constructs Strings for IPC fields. No syscall-count or allocation profiler establishes the report's quantitative wording. | **Partially confirmed; reliability improved.** Explicitly flush diagnostics on stages and after final timing, including failed/cancelled renders. Report write/flush failures to stderr on a best-effort basis, including when stderr itself is unavailable. Test file visibility/order before writer drop. Pending progress diagnostics can still be lost on SIGKILL/abrupt termination or storage failure; flush is not fsync. No protocol buffering change or zero-total-allocation claim. |
| E — Swift/Qt byte streams | Batch slicing removes O(N²) movement and explains faster headless exports/XCTest | Original slices remain alive during decode/parse and have no demonstrated dangling use. Installed Qt's `QPodArrayOps::erase` advances its pointer when erasing a prefix; prefix removal is not invariably a memmove. No trace proves the blanket quadratic claim for Foundation Data either. Both original consumers could retain an unlimited unterminated line and rescan the accumulated prefix on every read. Swift capture operations read the whole byte stream before decoding. Headless export starts no frontend parser, so its timing cannot establish a parser speedup. | **Correctness mostly supported; complexity/causal claim unsupported; boundedness corrected.** Consume only new bytes, retain incomplete bytes, and limit individual lines to 8 MiB. Complete lines take a view fast path. Swift ignores malformed/empty lines and invalid EOF tails, as before; Qt records failure for malformed/empty records and parses a nonempty EOF tail, as before. Oversized lines follow those error policies, drain through newline/EOF, and release retained data. Swift capture uses the same framing. Tests cover every split, UTF-8, batches, large/bytewise fragments, empty reads, malformed input, overflow recovery, and EOF. |
| F — preset collections and Qt aspect deduplication | Cached collections refresh on selection/load, linear deduplication, lower idle memory | Current UI load/selection callbacks already called normalization; they work in workflow tests. However, store properties remained publicly mutable: direct preset replacement or restored/invalid selections could leave caches and selection inconsistent until a callback ran. The Set retains first-seen order. At 27 presets, there is no allocation profile tying the reported idle-memory delta to this change. | **Partially confirmed; invalidation strengthened.** Normalize when presets/platform/aspect/preset mutate, with a recursion guard on the MainActor. Keep callback-driven preview behavior. Test initial load, duplicates, empty/replaced presets, invalid selections and restoration. Retain Qt's ordered membership-set change. Withdraw the causal memory claim. |
| G — traversal and larger buffers | `file_type()` saves metadata calls; 64 → 128 KiB is faster | `DirEntry::file_type()` does not follow symlinks; non-file/non-directory entries are still rejected and listed files are independently hashed. read_dir/entry/type/read failures still reject the runtime. OS filesystems may obtain type information differently; syscall savings were not counted. Rotated 64/128 KiB tests show overlapping ranges and small inconsistent gains while doubling stack buffers (two concurrent hash readers). Short reads and partial writes remain handled by read loops/write_all. | **Traversal semantics confirmed; speed claim partial; buffer gain inconclusive.** Retain file_type and rejection tests. Restore 64 KiB in engine/updater. File-to-sink updater measurements do not establish TLS/network performance. Do not weaken checksum, byte-count or signature verification. |

### Additional confirmed defect: cancellation deletes existing output

The current Swift client removed the output URL after a cancelled render. The engine already stages exports and owns cleanup, so this could delete an older completed destination. This defect is in the later frontend changes, not the optimization commit. Remove that client deletion and keep engine ownership intact.

A test waits for the real engine's `validating` stage, cancels, and checks a preexisting 25-byte destination. Run against a `git archive` snapshot of `aba4aa8` with only the test injected, it **fails** because the destination becomes absent. The identical test passes with the corrected client. A before-launch test also now preserves a sentinel destination. No source image/audio files are changed.

## Benchmark methodology and interpretation

All controlled workloads run serially after builds/tests finish. Run order rotates. Other ordinary host applications remain running; OS caches are not purged and background load is not fully controlled. The first observation is retained separately, not called a cold boot. Subsequent samples report counts, medians, ranges and variability. Small overlapping differences are inconclusive. Resource sampling runs separately because it perturbs export throughput. No XCTest suite duration is presented as an application performance metric.

### 60-second export claim

The historical `build/export-benchmark/engine-60s-candidate/results.json` contains the reported 12.969636 / 2.221106 second medians, but its baseline SHA-256 is `7f2093dc1b9bcc718f127b6001f148d9a1bfc7900c90139d0c8d419e222b0c26`. It points to `build/export-benchmark/ativ-engine-baseline`, not a build identified as `7121cd8^`. The standalone file still exists; its Git source revision is not authoritatively recorded. It must not be substituted for the available commit parent. Both actual parent and optimization sources already default to Simple.

Newly generated artwork/audio are byte-identical to the historical fixtures:

- Artwork: 2400×1600 PNG, SHA-256 `cecc7c47b426b1918d38904f4491bd1da09e99a1cf3d8be8b0b3b275681b85bd`.
- Audio: 60 s mono PCM, 44.1 kHz, SHA-256 `ba885e232ddc732b7731e546d26625dd602645220962387d7c784f49ba3ca65c`.

The controlled revision comparison uses identical packaged media executables and runtime resources across all engines, output 1920×1080, 30 fps, software libx264, stillimage tune, default quality/preset/thread selection, yuv420p, AAC 128k, and a matched 60-second endpoint. It includes packaged verification, probing, rendering, staging/publication and process completion; no PATH fallback or development overrides are used in this comparison. A completion event and successful timing event are required. Each timed run writes a new path and is validated afterward, outside timing.

`benchmark_revision_exports.py` refuses an existing output directory, records executable/input identities and exact commands, rotates revision order, and validates **every** run. All 12 outputs (three revisions × first observation plus three measured samples) have 1,800 frames, matching resolution/rate/codecs/durations and mono 44.1 kHz AAC. Every decoded video frame and timestamp matches the newly generated equal-duration per-frame reference; decoded audio hashes also match across all 12 outputs. This establishes matched deterministic output for this fixture/settings, not every media file or platform.

The repository's original `benchmark_engine_export.py` was also rerun in a fresh directory with the actual parent as baseline and optimization as candidate. Its `current` label explicitly selects PerFrame, while its `baseline` omits a mode (already Simple in the actual parent). These are different workloads, not successive implementation revisions. The script's old reuse of one filename per mode and final-output-only validation is avoided by the new matched harness.

The historical export script used `build/ffmpeg-macos-arm64/{ffmpeg,ffprobe}`, whose current binary hashes differ from the packaged pair. Their identity is a third-party `9.0.1-https://www.martin-riedl.de` build (about 66 MB per executable), whereas the pinned packaged executables are about 21 MB each. The report's export commands therefore did not measure production bundled verification. A separate reproduction retains those exact local paths and the preserved standalone baseline, records their identities, and builds a fresh per-frame reference with that same pair. That experiment is a development-override/render-mode comparison with an unidentified older engine, not proof of this optimization commit's speedup. Exact original numerical medians are not guaranteed by a later run.

### Microbenchmark corrections

`hashing_benchmark.rs` now requires explicit input paths instead of silently passing when files are absent, uses streaming on both sides, records real input sizes (21,404,320 and 21,230,288 bytes), rotates modes, uses optimization barriers, and separates first JSON initialization from warmed lookup. The old “original hashing” benchmark read whole files even though the actual parent already streamed them. Preset formatting remains an opt-in diagnostic; repeated cached formatting is not an application startup metric. Benchmarks stay ignored by ordinary tests and create no development gate.

JSON first initialization measures fresh LazyLocks with retained parsed Values. Repeated parse includes parse/use/drop; warm access reads the `targets` entries from already initialized Values. That distinction matters more than the quotient. The production one-command process pays initialization again on each invocation. Hex results exclude hashing/I/O and compare the actual per-byte-formatting and lookup approaches. No end-to-end multiplier is inferred from either microbenchmark.

### UI/resource/package claim corrections

Saved historical UI records exist for `20261013-222221` and `20261013-223502`. They have three ordinary launch samples and two measured headless exports per frontend; they do not establish UI-ready latency. Idle samples are repeated observations of a single process, not independent process populations. “0.00%” CPU reflects rounded process-time sampling over a short interval, not a proof of no activity. The report's “100% of allocated cores” claim lacks an established sampling denominator.

The original Qt archive sizes were **64,340,672 and 64,351,128 bytes** (about 61.36 and 61.37 MiB), an increase of about 0.016%, not a 4.5% reduction. The table mixed decimal MB with binary MiB. No packaging-content reduction is supported. Fresh comparison archives use the same ditto method and supporting contents; their sizes/inventories are reported separately from historical release artifacts. Engine size changes cannot be assigned to thread inlining without binary analysis.

Fresh UI measurements launch extracted bundles with the repository `benchmark_ui.py` implementation, through `/usr/bin/open`, and check the exact executable path/PID. Each has one first-profile observation, three ordinary launches, eight seconds of idle sampling, and first plus three 10-second headless exports. Headless engines do not exercise the Swift/Qt UI. No first visible window, interactive readiness, display pacing, VoiceOver, Narrator, or Orca timing is inferred. The report generator was also corrected to stop emitting hardcoded claims about an unaccepted Xcode license, completed manual GUI/accessibility acceptance, and an assumed dirty-tree state. Those statements were not measurements. The separate resource sampler reports sampled engine/media process trees; those timings are intentionally excluded from headline export timing.

## Regression coverage and final validation

Each check runs independently; failure does not prevent unrelated diagnostics. Detailed exact commands, environments and status codes are in `*-status.json`, with output in matching `*.log` files. Equivalent core invocations include:

```sh
CARGO_NET_OFFLINE=true cargo test --workspace --locked --offline
CARGO_NET_OFFLINE=true cargo clippy --workspace --all-targets --locked --offline -- -D warnings
cargo fmt --all -- --check
python3 script/dependency_inventory.py --check
python3 script/test_runtime_ownership.py

# E = absolute path to freshly staged Contents/MacOS/ativ-engine
ATIV_ENGINE_PATH="$E" python3 script/test_engine_fixtures.py "$RESULTS/fixtures"
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  ATIV_ENGINE_PATH="$E" ATIV_TEST_MEDIA="$RESULTS/fixtures" \
  swift test --package-path platform/macos --scratch-path "$RESULTS/swift-tests"
ATIV_QT_TEST_ENGINE="$QE" ctest --test-dir "$RESULTS/corrected-qt" --output-on-failure
QT_QPA_PLATFORM=offscreen "$RESULTS/corrected-qt/ativ-qt-accessibility-tests"
python3 script/validate_package.py "$APP" macos-arm64
python3 script/validate_qt_macos.py "$QT_APP"
python3 script/test_ffmpeg_runtime.py --engine "$E" --runtime "$RUNTIME" --target macos-arm64
```

`RESULTS`, `APP`, `QT_APP`, `E`, `QE`, and `RUNTIME` refer to the isolated paths in the evidence logs, not an installed app or an old package. The repository's build/run and packaging entrypoints were inspected; their online provisioning and replacement of existing output locations were avoided by equivalent offline isolated builds/staging. No native platform claim is inferred from source portability or cross-compilation.

Added/strengthened tests exercise worker failure/panic joins; lowercase/all-byte/leading-zero hex equivalence; unknown tree entries, directory/broken symlinks and traversal errors; pre-drop diagnostic flush order and nonfatal writer failure; fragmented UTF-8, EOF and stream overflow recovery; preset invalidation and selection consistency; before/after-launch cancellation preserving a destination; empty/large/leading-zero updater downloads with short reads and partial writes. Existing authentication, corruption, size, failed-install and retry tests remain.

| Check | Final result and scope |
|---|---|
| Cargo workspace tests | **Passed:** 39 ordinary tests (2 core, 10 engine unit, 5 protocol, 22 updater contracts); diagnostic benchmarks remain opt-in. |
| Clippy / format | **Passed** with locked/offline workspace/all-target checks and `-D warnings`; format check passed. |
| Dependency inventory / runtime ownership | **Passed**, independently. |
| Engine fixtures | **Passed** through the corrected packaged engine: presets, missing-input handling, probe, preview and export. |
| Native Swift tests | **Passed:** 13 tests; real process integration plus new stream/cache/cancellation coverage. |
| Qt workflow | **Passed:** CTest's `qt-workflow`, offscreen macOS; stream regression tests included. |
| Qt accessibility | **Passed:** 10 including setup/cleanup, offscreen macOS. Warnings from intentional missing-engine fixtures remain visible. This is not a screen-reader certification. |
| Package integrity / identity / runtime dependencies | **Passed:** fresh native and Qt bundles, Mach-O target identity, local code-signature checks and bundled dependencies. Qt validator reports 27 Mach-O files. Native validation invokes real package/media contracts. |
| Media lifecycle / runtime tampering | **Passed:** 27 presets, 20 previews, 4 exports, cancellation/failed exports preserving destinations, private error logs, timeouts/owned-child cleanup, both required tools missing/damaged, modified metadata/provenance, and no PATH fallback. |
| Output comparisons / export and UI benchmarks | Fresh commands and results are recorded in the measured-results section below. |
| Expected before-fix regression | **Failed as intended:** cancellation on uncorrected `aba4aa8` deletes the sentinel, and the direct-mutation cache test reports stale selections/collections (10 assertions). Both corrected tests pass. |
| Other native targets, manual assistive technology, first usable UI | **Not run / blocked by coverage:** only a native Apple Silicon Mac is available for this assignment. |

Initial local attempts exposed a digest-array type mismatch in the added helper, an unsupported LowerHex benchmark variant, and Clippy condition-style diagnostics. These were corrected, then the checks rerun. The first Qt staging validation rejected a copied older minimum-OS plist; staging now uses the fresh CMake-generated plist and validation passes. These failed-attempt logs are retained. No test was suppressed, integrity validator relaxed, or diagnostic made a mandatory gate.

## Remaining work / consolidated local follow-up register

This section is the local draft for consolidated issue tracking; no remote issue or other remote write was made during this local-only assignment.

1. **Native platform coverage:** run the same engine/updater/IPC, package and media checks natively on macOS Intel, Windows x64/ARM64, and Linux x64/ARM64 when hosts are available. Actions minutes are exhausted; no workflows were dispatched. A Mac Qt result provides no Windows/Linux runtime evidence.
2. **UI readiness and assistive technology:** obtain repeatable first-visible/first-interactive instrumentation and human screen-reader validation if those claims are needed. PID appearance and XCTest duration cannot supply that evidence.
3. **Historical provenance and unsupported causal claims:** the standalone older benchmark engine has a known blob hash but no authoritative Git revision/build receipt. Preserve that limitation. Fat-vs-thin LTO “99%”, hardware-acceleration rationale, daemon startup “51 ms”, allocation totals, syscall counts, and UI allocation/memory causation in the historical prose lack controlled evidence here and are withdrawn as established findings. No speculative LTO, daemon, UI, encoder, or acceleration changes were made.
4. **Limits of diagnostics:** true OS-cold runs, sustained resource profiling, filesystem-specific syscall counts, forced OS thread-creation exhaustion, Windows filesystem/reparse behavior, and crash/power-loss log durability were not validated. Error mappings and native Unix symlink behavior were inspected/tested as described. Logs are best effort; killed processes cannot guarantee final IPC/log delivery. Packaged hashing keeps its existing cancellation granularity: a cancellation arriving during file verification waits for those reads/joins before Core observes the token. Buffer size does not add token polling, and slow-filesystem cancellation latency was not measured. Swift still suppresses child stderr; structured operation errors remain on stdout. Captured command events still assume the trusted engine emits a finite number of valid events; the new cap bounds individual malformed lines, not an adversarial endless sequence of valid events.

Local corrections and available-platform checks are complete; the open coverage and evidentiary limitations above prevent declaring the entire historical audit resolved.

## Measured results

### Final matched packaged 60 s / 1080p export

| Revision | First observation s | n | Median s | Min–max s | SD s |
|---|---:|---:|---:|---:|---:|
| baseline | 1.823416 | 3 | 1.888172 | 1.827663–1.892051 | 0.036107 |
| optimization | 1.832093 | 3 | 1.830087 | 1.828411–1.849263 | 0.011585 |
| corrected | 1.823757 | 3 | 1.865633 | 1.864452–1.874466 | 0.005473 |

The final corrected median differs little from the actual parent. Small differences vary between the earlier `revision-exports` cohort and final cohort; no application-level export speedup or unacceptable throughput regression is established. Both cohorts and all raw samples remain available. Final cohort: all 12 outputs independently pass 1,800-frame/timestamp comparisons and decoded-audio identity.

### Full packaged `check` latency

| Revision | n | Median ms | Min–max ms | SD ms |
|---|---:|---:|---:|---:|
| baseline | 10 | 87.313 | 79.424–92.123 | 3.986 |
| optimization | 10 | 76.196 | 71.307–82.603 | 4.311 |
| corrected | 10 | 79.986 | 71.451–83.673 | 3.731 |

Includes process launch, the complete package verification path (not just two binary hashes), and media-tool identity commands with empty PATH. First observations are separate in `verification-final.json`; caches were already exercised.

### Warm microbenchmarks

| Workload | Samples | Median | Min–max |
|---|---:|---:|---:|
| Sequential streaming, 64 KiB | 10 | 14.503 ms | 14.168–14.944 ms |
| Concurrent streaming, 64 KiB | 10 | 7.700 ms | 7.521–7.952 ms |
| Concurrent streaming, 128 KiB | 10 | 7.633 ms | 7.422–7.742 ms |
| Two JSON LazyLocks, first initialization | 10 | 40.812 µs | 38.209–59.000 µs |
| Two JSON parse/use/drop operations | 10 | 43.886 µs | 43.687–44.223 µs |
| Two warm targets lookups | 10 | 20.938 ns | 19.667–24.000 ns |
| Engine per-byte format/collect | 10 | 0.794 µs | 0.787–0.800 µs |
| Engine pre-sized lookup encoder | 10 | 0.026 µs | 0.026–0.027 µs |
| Updater-shaped file→sink copy/hash, 64 KiB | 10 | 37.087 ms | 36.620–37.254 ms |
| Updater-shaped file→sink copy/hash, 128 KiB | 10 | 36.791 ms | 36.530–36.995 ms |

One first sample per strategy is excluded from those microbenchmark summaries. Hash strategies each hash the same 42,634,608 bytes; updater-shaped copying uses the same ffmpeg file. Hex samples each time 100,000 operations; JSON repeated samples time 1,000 operations. The static pin/spec checks and lookup safety tests are separate. The two buffer experiments (original `micro.log` and later `micro-retained.log`) show small changes with overlap; doubling buffer storage is not justified here.

### Renderer controls and preserved older experiment

- Packaged FFmpeg renderer control: current **8.411680 s**, png **3.509891 s**, cached **1.890180 s**. Three measured runs per mode after one warmup; raw commands/settings/validation: `reference-60s/results.json`.
- Original harness, actual parent as baseline: baseline **2.099398 s**, current **10.120703 s**, simple **2.086837 s**. Three measured runs per mode after one warmup; raw commands/settings/validation: `legacy-harness/results.json`.
  Actual parent endpoint: 60.000000 s, 1800 frames; its default is already Simple.
- Preserved unidentified engine + third-party FFmpeg development overrides: baseline **11.982909 s**, current **12.046199 s**, simple **2.046416 s**. Three measured runs per mode after one warmup; raw commands/settings/validation: `preserved-report-comparison/results.json`.
  Baseline video endpoint: 62.066667 s, 1862 frames; Simple is exactly 60 s / 1,800 frames. An unbounded PerFrame endpoint is not identical work.

The preserved setup reproduces a **5.86×** renderer-mode gain, close to the historical 5.84×, with output equality against its fresh same-tool equal-duration control. This supports the rendering technique. It does not support attributing that gain to `7121cd8` or treating those third-party tools as the packaged runtime. The older baseline cannot report build-info and its Git source remains unknown.

### UI process, idle, headless, and archive observations

Parent/optimization rows below come from the same six-bundle cohort (`ui/`). Final rows are a subsequent two-bundle cohort (`final-ui/`) after the final best-effort logging error-path adjustment; UI executables are identical to the earlier corrected cohort, engines have fresh identities. Do not interpret these short, separate cohorts as proof of a UI optimization. Raw summary JSON supplies ranges and SD for every field.

| Revision / frontend | Process seen ms (range), n=3 | 10 s headless export s (range), n=3 | Idle physical / RSS MiB | ZIP bytes |
|---|---:|---:|---:|---:|
| baseline-swiftui | 101.344 (97.193–109.575) | 0.511358 (0.505827–0.518915) | 33.42 / 102.80 | 42,145,829 |
| optimization-swiftui | 99.447 (93.810–100.830) | 0.510400 (0.508120–0.525020) | 33.58 / 103.02 | 42,154,934 |
| baseline-qt | 110.083 (99.559–110.532) | 0.504270 (0.502646–0.512529) | 64.42 / 140.14 | 64,352,568 |
| optimization-qt | 98.713 (96.566–106.437) | 0.524059 (0.514409–0.525684) | 64.66 / 140.34 | 64,361,123 |
| final-swiftui | 101.398 (96.995–108.981) | 0.508311 (0.498813–0.515368) | 33.95 / 102.89 | 42,175,592 |
| final-qt | 93.891 (93.294–110.480) | 0.510562 (0.509308–0.515123) | 64.81 / 140.52 | 64,369,643 |

Idle memory has five time samples from one process per candidate. The current source also includes the five preserved intervening commits, so its Qt footprint difference cannot be assigned to this remediation or the preset cache. Every headless run passes structure/duration checks; it starts no GUI parser.

| Final frontend | First-profile process seen ms | Idle CPU time delta / sample span | Approx. one-core utilization |
|---|---:|---:|---:|
| swiftui | 108.253 | 0.00 s / 8.01 s | 0.00% |
| qt | 105.498 | 0.00 s / 8.01 s | 0.00% |

Rounded process CPU accounting and short observation windows limit these numbers. They do not establish zero wakeups, zero energy use, visible readiness, or busy export CPU saturation.

### Final resource sample (separate workload)

| Frontend | Sampled engine peak physical MiB | Sampled media peak physical MiB | Observed roles |
|---|---:|---:|---|
| swiftui | 2.11 | 960.55 | engine, media |
| qt | 2.05 | 960.17 | engine, media |

150 ms nominal sampling, with sequential footprint/process queries; brief peaks/probes may be missed. These are individual-process peaks, not simultaneous aggregate or end-to-end throughput claims.

### Executable identity and sizes

| Revision | Packaged engine bytes | SHA-256 |
|---|---:|---|
| baseline | 827,376 | `c3fabd7fda0d987a4440a399a6eff5812f409f00a65d3dfe6af0638859684bb7` |
| optimization | 844,368 | `e3a54204d8ba7a7fd8f0d078dcf393787fed03452e0c19bddeaa7990290cfcc7` |
| corrected | 860,064 | `f154669f77ab2033e6fb72e99ff57d6d1d7aa6831409b4097c3b56b7a541899a` |

The native packages used for all three 60-second comparison revisions use ffmpeg SHA-256 `3673c4626d1f9b6bba00823d618de14fa79b679598a937e2decf67209b0e71c8` and ffprobe SHA-256 `37d8ae684cfe2c9ebc195dff819965a4c81f9aac7ee8dffe31d6336b7e5c651c`. Their sizes are 21,404,320 / 21,230,288 bytes. Qt uses distinct signed copies and a distinct pinned acquisition archive; the signed hashes are in packages.json. Both templates record identical original binary hashes, and removing signatures on disposable copies produces identical binaries (signature-comparison.json). Each frontend family keeps its media/metadata constant across revisions; native-vs-Qt headless timing is additionally confounded by these packaging differences. The distinct third-party tool hashes/build configuration are recorded in `preserved-input-identities.json`; neither was installed into an app. ZIP method/metadata and support contents must be considered before assigning size changes to code.

### Reproduction of the matched comparison

Build/stage isolated bundles as described above, create the equal-duration control, then use a **new** directory for each invocation:

```sh
python3 script/benchmark_export.py --ffmpeg "$FFMPEG" --ffprobe "$FFPROBE" \
  --directory "$RESULTS/reference-60s" --seconds 60 --rounds 3
python3 script/benchmark_revision_exports.py \
  --engine "baseline=$BASELINE_ENGINE" --engine "optimization=$OPTIMIZATION_ENGINE" \
  --engine "corrected=$CORRECTED_ENGINE" --directory "$RESULTS/matched-exports" \
  --ffmpeg "$FFMPEG" --ffprobe "$FFPROBE" \
  --image "$RESULTS/reference-60s/artwork.png" --audio "$RESULTS/reference-60s/audio.wav" \
  --reference-video "$RESULTS/reference-60s/current.mp4" --rounds 3
ATIV_BENCH_FFMPEG="$FFMPEG" ATIV_BENCH_FFPROBE="$FFPROBE" \
  cargo test --release --locked --offline -p ativ-engine --test hashing_benchmark \
  -- --ignored --nocapture --test-threads=1
ATIV_BENCH_FFMPEG="$FFMPEG" cargo test --release --locked --offline \
  -p tlo-updater --test contract benchmark_download_buffers \
  -- --ignored --nocapture --test-threads=1
```

The ignored orchestration scripts `validate_local.py`, `finalize_validation.py`, `last_checks.py`, `run_benchmarks.py`, `additional_measurements.py`, `check_evidence.py`, and UI wrappers preserve the exact commands, staging paths and environments used in this run. Fresh root paths are needed to repeat them; existing result directories are deliberately rejected. No downloaded artifacts, old output files, XCTest durations, or old reports are presented as new measurements.
