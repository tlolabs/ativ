# Performance audit — 2026-11-10

Four focused internal optimizations remove measured allocation, filesystem and
copying waste. The evidence establishes specific phase/resource benefits; it does
not establish a general export, preview, JPEG or default-PNG speedup.

## Baseline, environment and method

- Original HEAD: `8296a9e623c6924c12e456b5fe9e7c10b59dfbde`.
- Task: `avid-perf-20261110-six-loops`; current checkout, no branch/commit/push/publication.
- Apple M5 Max, 18 cores, 128 GB; macOS 27.2.1 ARM64; Rust 1.99.1. Native checks also used Rust 1.85.0.
- Optimized Rust builds; identical 72 locked dependency records for original/current harnesses. No custom release RUSTFLAGS, LTO or codegen overrides.
- Explicit Homebrew FFmpeg/ffprobe 9.0.2; software H.264/libx264, AAC 128k and 30 fps for measured video. These are development tools, not the authenticated Recipe 7 package.
- SHA-256 FFmpeg: `7f6028378534aa10a2dfa07d807ddcc0d18c869bf5c2f64c89efcc18ee88c4ee`.
- SHA-256 FFprobe: `bfe676bfc3a889bebe63af07c71a926a6167f568c7a932a79c2f1fe51ae6d5a1`.
- Fixture creation excluded; fixed input hashes, settings, original binaries, commands, raw samples and outputs retained. Media fixtures include detailed 2048×1536 artwork and 1-, 30- and 600-second mono PCM audio.
- First operation reported separately. “Cold” means an empty application cache; OS page caches and CPU frequency were uncontrolled. No filesystem cold-start or tail-percentile claim.
- Independent microbenchmarks alternate variants; larger media blocks are sequential. Controls below investigate observed changes rather than infer causality from nonoverlapping ranges alone.
- MB denotes decimal bytes; capture caps and removed frame allocations use MiB.

Evidence is outside the checkout at `/private/tmp/avid-perf-20261110-six-loops/`;
original requirements, pre-existing status, per-report snapshots and all failed
attempts remain there. `ledger.md`, `review-identities.json` and the final review
artifacts record model attribution and exact source hashes separately from this
report, avoiding a self-referential source hash.

## Six loops and decisions

| Loop | Hypothesis and disposition |
| --- | --- |
| 1: baseline/map | Fixed mixed cold/warm benchmark samples, selected-runtime mismatch and omitted cold capability/filter/batch costs. Initial probe processes were about 39 ms versus about 4 µs for warm queries; default PNG compression dominated its small test fixtures. |
| 2: probing/startup | Removed owned path construction from cache hits and obsolete generations. Kept full replacement-sensitive fingerprints, Unix-only cache use and fresh runtime verification. |
| 3: composition/preview | Removed repeated exact-path source checks within each protection call. Fresh pre-publication validation remains. Simple already caches composed frames; changing PerFrame would risk animation semantics, so no filter/encoder shortcut was added. |
| 4: memory/image | Streamed transformed PNG rows solely for opacity validation. Full source/CRC/Adler validation, metadata policy, effort, alpha rejection and pixel depth remain. |
| 5: concurrency/lifecycle | Replaced overflow-front shifts with a deque. Capture limits, progress parsing, cancellation polling, timeouts, owned-child cleanup and bounded probing remain. No worker pool, async runtime or global mutable cache. |
| 6: integrated/simplification | Repeated original workloads, controls and full native checks; assessed the complete patch. No further implementation change was justified. Retained the narrow implementations and documented inherited tail variability and measurement limits. |

The initial Gemini report found four benchmark issues. Codex substantiated and
repaired all four; the second report independently verified them resolved.
Reports 3, 4 and 5 cover Loops 2, 3 and 4 and contain no findings. The final report
is requested for the complete accumulated implementation and integrated evidence.
An accepted final report may cover Loops 5 and 6 at the same unchanged source
hash under AGENTS.md's applicable-audit reuse policy. The ledger must disclose
that reuse: six completed reports include the Loop 1 repair recheck, not six
separate initial/recheck pairs. Any final finding or source repair requires its
own explicit disposition; exhausted capacity is not a clean recheck.

All requests use Antigravity profile `gemini`, CLI ID `gemini-3.8-flash-high`,
fallback `none`. CLI backend-selection logs identify “Gemini 3.8 Flash (High)”.
The provider response exposes no separate serving-model identity. Reviews are
static independent assessments plus runner-executed checks; the read-only adapter
prohibits reviewer shell execution. Scratch measurement harnesses and their
results were produced by Codex, not independently executed by Gemini.

## Implemented changes and isolated benefits

### Probe cache

`src/renderer.rs` now keys by path and stores the complete fingerprint with the
value. Borrowed lookups allocate no path; replacing one generation preserves
unrelated entries at the 1,024-distinct-path limit. Cached unknown duration remains
distinct from a miss. Source checks still precede lookup; no runtime authenticity
or identity check is cached away.

Optimized exact-code lookup, 15 alternating samples of 100,000 hits, full cache:

| Lookup | Original median [min–max], ms | Current median [min–max], ms |
| --- | ---: | ---: |
| Image | 7.084 [6.675–11.152] | 3.442 [3.256–5.573] |
| Duration | 6.658 [6.498–6.860] | 3.335 [3.171–3.553] |

Separate allocator instrumentation: 100,000 allocations/5,000,000 bytes per
original batch versus zero for the cache lookup itself. These measurements exclude
filesystem/source validation and do not prove a public-probe latency improvement.

### Source protection

`src/storage.rs` deduplicates exact lexical OsString inputs within one call.
Distinct spellings retain all canonical/identity checks. The next protection call,
including publication, starts fresh. The temporary set owns O(distinct paths)
strings and is freed on return; it is not a persistent filesystem cache.

Fifteen alternating warm-filesystem samples after three warmups, 128 entries from
four distinct sources:

| Destination | Original median [min–max], ms | Current median [min–max], ms |
| --- | ---: | ---: |
| New | 9.424 [8.808–12.664] | 0.350 [0.336–0.403] |
| Existing | 15.024 [14.018–16.015] | 0.556 [0.522–0.591] |

Unique-path cases showed no justified gain; integrated timeline ranges overlapped.
New tests retain distinct hardlink detection and symlink retarget checks across calls.

### PNG opacity validation

`src/image/png.rs` checks every transformed row, including Adam7 pass rows, then
finishes complete-source validation before reporting transparency. It preserves
EXPAND, 8/16-bit samples, strict ancillary CRC/Adler handling, cancellation and
all existing limits. Only frame reconstruction/storage for this validation phase
was removed; complete-image compression buffers still exist.

Ten decoder calls: first separated, nine warm calls; input already in memory.
Peak RSS includes input/process/allocator overhead, measured in fresh child processes.

| Input | Original median [min–max], ms | Rows median [min–max], ms | Peak RSS original → rows, MB |
| --- | ---: | ---: | ---: |
| RGBA8 4096² | 18.911 [18.341–19.150] | 17.729 [17.421–18.605] | 74.66 → 7.55 |
| RGBA16 4096², 31.2 MB source | 130.500 [129.186–131.222] | 129.257 [128.714–130.325] | 168.77 → 34.57 |
| Adam7 RGBA8 2048² | 13.323 [12.873–13.825] | 5.803 [5.657–5.938] | 21.95 → 5.18 |

Removed expanded buffers are 64, 128 and 16 MiB respectively. The supported 16-bit
fixture is below the 128 MiB input cap; an earlier oversized fixture is explicitly
excluded. Sixteen-bit latency is essentially unchanged; the memory reduction is
clear. These are validation-phase results, not whole-optimizer peak-memory promises.
The final production function matches the measured row algorithm.

### Bounded process capture

`src/process.rs` now uses VecDeque locally and linearizes once at EOF. The 4 MiB
ordinary stdout and 64 KiB stderr/progress caps, truncation flag, exact tail bytes,
structured CaptureLimit error and byte-by-byte progress parser remain unchanged.

Literal production drain, identical deterministic 32 MiB input, 15 alternating
samples after warmup:

| No-progress capture | Original median [min–max], ms | Current median [min–max], ms |
| --- | ---: | ---: |
| 64 KiB tail | 2.547 [2.412–2.784] | 1.063 [0.752–1.194] |
| 4 MiB tail | 193.389 [192.828–193.802] | 0.854 [0.829–1.090] |

Heap instrumentation matched: 71,104 bytes/8 allocation-or-reallocation calls at
64 KiB; 4,199,872 bytes/14 calls at 4 MiB. Progress-inclusive results varied between
runs and establish no progress-throughput gain. These are output-flood resilience
results, not typical FFmpeg export speedups. Portable tests cover wrap, exact cap,
short/Interrupted reads and bounded progress delivery.

## Integrated media observations

Original versus accumulated final code, same frozen harness/fixtures/runtime,
first operation plus five warm samples (audio probes use ten). Values below are
milliseconds; brackets are observed min–max. These serial blocks are observations,
not causal speed claims. Inherited PerFrame tail variability changes excess work
after audio EOF; its wall-time rows are not fixed-frame performance comparisons.

| Workload | Warm n | First original → final, ms | Original median [min–max], ms | Final median [min–max], ms |
| --- | ---: | ---: | ---: | ---: |
| single-1s-320x180-simple | 5 | 283.847 → 247.647 | 94.802 [93.104–95.167] | 82.395 [81.037–82.557] |
| single-1s-320x180-perframe | 5 | 296.218 → 309.464 | 167.834 [165.341–169.871] | 164.939 [161.360–172.730] |
| single-30s-320x180-simple | 5 | 411.977 → 364.449 | 218.200 [216.363–219.919] | 202.362 [202.290–226.323] |
| single-30s-320x180-perframe | 5 | 2519.214 → 2759.882 | 2342.046 [2275.857–2364.236] | 2601.220 [2542.908–2656.692] |
| single-1s-1280x720-simple | 5 | 308.607 → 273.391 | 117.256 [115.981–119.729] | 112.395 [109.385–112.650] |
| single-1s-1280x720-perframe | 5 | 373.686 → 356.898 | 215.323 [211.930–217.929] | 215.260 [199.610–224.572] |
| single-30s-1280x720-simple | 5 | 678.535 → 702.366 | 557.120 [537.889–564.318] | 559.770 [544.470–574.121] |
| single-30s-1280x720-perframe | 5 | 4008.904 → 4082.179 | 3869.227 [3833.455–3909.528] | 3952.911 [3915.424–3991.827] |
| timeline-24x0.25s-320x180-simple | 5 | 1382.005 → 1343.252 | 1145.585 [1059.454–1226.516] | 1186.924 [1141.501–1202.262] |
| preview-320x180 | 5 | 188.218 → 173.295 | 68.641 [67.763–69.580] | 82.110 [79.684–82.362] |
| preview-1280x720 | 5 | 188.715 → 174.480 | 93.684 [90.156–94.931] | 82.167 [81.922–82.444] |
| concurrent-2x30s-1280x720-simple | 5 | 974.735 → 975.695 | 812.148 [759.931–898.592] | 857.844 [818.812–874.160] |
| jpeg-2048x1536-lossless-defaults | 5 | 26.076 → 25.921 | 23.979 [23.742–24.188] | 24.726 [23.979–25.221] |
| single-600s-320x180-simple | 5 | 2859.939 → 3094.023 | 2720.194 [2716.154–2756.542] | 2909.731 [2878.739–2935.011] |
| probe-600s-uncached-renderer | 10 | — | 46.013 [40.794–46.898] | 46.790 [39.289–46.881] |
| probe-600s-cached-renderer | 10 | — | 0.004 [0.003–0.033] | 0.004 [0.003–0.020] |

Fourteen of fifteen retained media outputs initially matched exactly. The
30-second 320×180 PerFrame output differed only beyond audio EOF: original had
938 frames, final 946, while all first 900 required frames/timestamps and decoded
audio matched. The untouched original rerun produced 944 frames, proving inherited
tail variability. Original and final controls both produced 944 frames and the
same complete-file hash. This existing PerFrame `-shortest` tail behavior remains
an explicit limitation; it was not “fixed” by changing render-mode timing.
The 600-second Simple output has 18,000 frames and 600-second audio and matches exactly.

Follow-up original/current controls, five warm samples, also demonstrate drift:

| Workload | Original median [min–max], ms | Final median [min–max], ms |
| --- | ---: | ---: |
| 30s 320×180 PerFrame | 2607.042 [2467.251–2675.104] | 2634.402 [2462.189–2729.024] |
| 600s Simple | 2839.169 [2802.655–2876.489] | 2891.090 [2845.480–2911.454] |
| Preview 320×180 | 82.363 [82.010–82.425] | 81.008 [80.621–82.082] |

A small JPEG difference in sequential supplemental blocks prompted a separate
ABBA control using unchanged public defaults and 30 warm samples per block.
Original → final → final → original medians were 23.016, 23.050, 23.009 and
23.101 ms; ranges overlap and all output hashes match. No stable JPEG gain or
regression is established.

## Whole PNG optimizer with unchanged defaults

Extra effort and Zopfli remain enabled. Each fixture uses five calls, first
separated and four same-process warm calls. Output files match original hashes.
Sequential changes below are not attributed to row validation.

| Input | First original → final, s | Warm median [min–max] original, s | Warm median [min–max] final, s |
| --- | ---: | ---: | ---: |
| rgba8-default-512.png | 10.848 → 10.822 | 10.949 [10.900–10.979] | 10.910 [10.891–10.927] |
| rgba16-default-256.png | 36.225 → 35.829 | 37.293 [36.631–37.811] | 35.956 [35.860–36.016] |
| adam7-rgba8-default-256.png | 3.603 → 3.560 | 3.605 [3.588–3.650] | 3.565 [3.560–3.567] |

CPU totals include all five operations. Process peak RSS includes the retained harness input copy equally for both variants.

| Input | CPU original → final, s | Peak RSS original → final, MB |
| --- | ---: | ---: |
| rgba8-default-512.png | 54.549 → 54.389 | 105.40 → 104.89 |
| rgba16-default-256.png | 184.247 → 179.459 | 50.04 → 46.68 |
| adam7-rgba8-default-256.png | 17.993 → 17.779 | 32.03 → 30.59 |

The earlier Loop 4 512² sequential run observed +1.48% warm median latency and
three fresh-process pairs observed +1.43%; those results remain preserved. A final
balanced six-pair AB/BA run used a fresh process per call: original median
10.962885 s [10.876721–11.017694], final 10.959068 s
[10.898455–11.193330]. Standard deviations were 45.9 and 132.3 ms. Median
paired delta was +6.407 ms; all twelve outputs matched. CPU totals were
65.676 versus 66.063 s (+0.589%). The earlier median penalty did not persist,
but higher variability/CPU remains visible. No whole-default PNG speed gain or
stable small latency effect is established. Retention is justified by eliminating
the measured large transient validation frame, without lowering compression work.

## Cancellation and concurrent jobs

Native cancellation used actual FFmpeg, fixed detailed artwork/30-second audio,
1280×720 PerFrame software, a five-second watchdog and cancellation at first
progress. Time is cancellation request to operation return, excluding startup.
Initial nine-sample medians were 7.011 ms [4.781–7.162] original and
7.570 ms [7.223–7.899] final. All preserved existing output and removed stages.

Four ABBA blocks of nine calls gave medians 7.246 → 7.740 → 7.859 → 7.878 ms.
Pooled n=18 each: original 7.528 ms [7.052–7.973], final 7.856 ms
[7.130–8.104]. AB/BA effects were +0.494 and −0.020 ms, showing order-dependent
drift; no stable causal cancellation change or improvement is claimed. All 36
control operations returned Cancelled, preserved output and left no stages.

The integrated table includes exactly two concurrent Simple exports using cloned
Renderers and distinct outputs. Hosts retain control of aggregate job concurrency;
no global scheduler or FFmpeg thread-setting change was added. Resource wrappers
report a waited-child high-water mark, not summed simultaneously resident RSS.
The original main `/usr/bin/time -l` wrapper failed its sysctl resource query after
writing complete timing results, so its peak RSS was not accepted. Other resource
runs use fresh Python child accounting with zero prior usage asserted.

## Animated artwork

Fixed opaque 128² two-frame GIF/APNG, 0.2-second frame delays and infinite looping, with the retained one-second audio. Each variant has a first operation and five warm samples; OS caches are uncontrolled. Values are milliseconds.

| Workload | First original → final | Original warm median [min–max] | Final warm median [min–max] |
| --- | ---: | ---: | ---: |
| gif-perframe-320x180-30fps | 216.424 → 214.034 | 50.905 [50.579–51.025] | 50.906 [49.881–50.968] |
| gif-simple-320x180-30fps | 97.591 → 96.729 | 50.979 [50.606–51.042] | 50.794 [50.783–51.022] |
| apng-perframe-320x180-30fps | 96.699 → 97.557 | 50.837 [50.590–51.022] | 51.047 [50.556–51.779] |
| apng-simple-320x180-30fps | 97.713 → 97.621 | 50.976 [44.971–51.076] | 50.970 [48.557–51.047] |

All 48 retained files match their corresponding-mode baseline hashes. Decoded checks confirm 30 frames at 30 fps, exact timestamps, one-second duration and A/V timing, a changing red/blue PerFrame cycle and a frozen red first frame in Simple. No animation speed gain is established. Whole-harness CPU was 1.587 → 1.579 seconds; peak RSS was 42.57 MB for each, including 24 renders plus bookkeeping per variant; semantic checks were outside that resource interval.

## Checks and restrictions

All commands below passed on the accumulated production code. Test counts:
108 default tests, 108 all-feature tests, one doctest, seven opt-in real-media
tests, two opt-in relocated-runtime tests, and 13 Python tests. The default
suite skips ten opt-in tests; nine were separately executed, leaving the real
Core packaged-runtime check unavailable.

Native tests used `AVID_TEST_FFMPEG=/opt/homebrew/bin/ffmpeg`,
`AVID_TEST_FFPROBE=/opt/homebrew/bin/ffprobe` and, for relocated-pair tests,
`AVID_RUNTIME_DIRECTORY=/opt/homebrew/bin`. The latter validates copying,
cancellation, replacement, rollback and handle release of that supplied pair;
it does not qualify an authenticated Core package.

```sh
cargo fmt --all -- --check
cargo check --locked --offline --all-targets --all-features
cargo test --locked --offline --all-targets
cargo test --locked --offline --all-targets --all-features
cargo test --locked --offline --doc
cargo clippy --locked --offline --all-targets --all-features -- -D warnings
cargo +1.85.0 check --locked --offline --all-targets --all-features
cargo test --locked --offline --test ffmpeg -- --ignored --test-threads=1
cargo test --locked --offline --test runtime_contract -- --ignored --test-threads=1
cargo build --locked --offline --release
python3 script/dependency_inventory.py --check
python3 -m unittest discover -s scripts/ffmpeg -p 'test_*.py'
```

The maintained optimized benchmark was also run with both explicit tool variables
and `AVID_RUN_PERF_BENCH=1 cargo bench --locked --offline --bench perf_benchmark`.
Its warmups, cold operation setup, sample counts, tool identities and Unix-only
probe-cache qualification now make measurement state explicit.

Failed or unavailable checks remain visible:

- The first Antigravity attempt could not write CLI logs/listen inside the outer sandbox. The approved retry retained plan mode, terminal sandbox and source-mutation rejection and completed; the failed attempt remains preserved.
- An initial cache type-complexity Clippy diagnostic was repaired using a small ProbeEntry alias; final Clippy passes. The scratch animation harness also had a hex-format compile error, corrected before measurement; its failed build log is preserved.
- Explicit VideoToolbox H.264 smoke attempts could not create a compression session (`-12908`); no hardware fallback was substituted. Hardware performance is unverified.
- Native Windows/Linux, macOS Intel and other GPUs remain unverified. Cross-compilation was not used as native performance evidence.
- The authenticated Core/Recipe 7 packaged runtime was unavailable. Its constructor/verification code, pinned specification, manifest, consumers and published contract were not changed.
- Inherited static PerFrame buffered-tail variability after audio EOF remains documented above. Required-content pixels/audio match; no general byte-identical PerFrame tail guarantee is claimed.
- OS cold caches, aggregate concurrent RSS, disk-traffic tracing and whole-media allocation profiles were not measured. No unsupported percentiles or broad performance promises are made.

Source-protection/staging tests, decoded opaque PNG pixels, JPEG coefficient/quality
and metadata contracts, error categories, APNG/GIF timing versus Simple freezing,
frame cadence, fractional timeline cuts, audio handling and square pixels pass.
No public API, persisted default/format, codec setting, quality, authentication or
fallback policy was changed. Runtime hashes continue to stream and verify fresh;
no cache skips required verification. Archived workflows, weekly CI, downstream
repositories and publication settings were untouched.

Deferred ideas: more capability caching or single-flight blocking, whole-request
filesystem caches, PNG/JPEG effort reduction, PerFrame still shortcuts, new worker
pools and progress throttling lacked a measured benefit compatible with existing
semantics. They were not retained. Full-optimizer buffers and host concurrency
limits remain relevant even with cheaper opacity validation.

## Reproduction and evidence

`benches/perf_benchmark.rs` is the maintained startup/probe/preview/export harness.
Focused reproducible harnesses and raw evidence are outside tracked source:

- `media-bench/`: original/final binaries, fixture/runtime/lock identities, all raw samples, output/decoded comparisons, controls and `FINAL-COMPARISON-README.txt`.
- `png-validation/`: strict decoder/full-default measurements, balanced controls, original/final build identities, fresh-child resource wrapper and `commands.txt`.
- `process-drain/`: literal original/final drain functions, stress/allocator harnesses and exact-byte assertions.
- `cancel-bench/`: unchanged native cancellation harness, watchdog, ABBA samples and resource wrappers.
- `animation-bench/`: fixed animated fixtures, original/current binaries and semantic/output verification.
- `protect-bench/` and `/private/tmp/avid-lifecycle-perf/cache/`: alternating filesystem/cache benchmarks and allocation counts.
- `final-checks.json`, `final-test-counts.json`, `ledger.md`, `reviews/`: commands, outcomes, requirements, all reports, source manifests and attribution limits.

No scratch timing result is presented as independently executed by Gemini. Consult
the external final ledger for accepted coverage, exact audited/final source hashes,
all findings and any restriction that appeared after this report was generated.

## Hardware smoke follow-up

After the audit, matched direct FFmpeg and AVID Core tests isolated the
VideoToolbox failure to Codex's outer execution sandbox: both failed there with
`-12908` and passed outside it. The explicit Hardware AVID request produced
VideoToolbox H.264 at 1280×720, 30 fps, 30 frames and one-second duration without
software fallback. The earlier hardware limitation describes the sandboxed audit
run; this later result verifies one H.264 smoke case, not hardware performance or
HEVC qualification. No encoder settings or implementation were changed.
