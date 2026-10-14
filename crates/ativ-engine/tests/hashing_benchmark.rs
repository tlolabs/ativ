use sha2::{Digest, Sha256};
use std::fs;
use std::io::Read;
use std::path::Path;
use std::time::Instant;

fn original_hash(path: &Path) -> (String, usize) {
    let bytes = fs::read(path).unwrap();
    let len = bytes.len();
    let hash = Sha256::digest(&bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    (hash, len)
}

fn streaming_hash(path: &Path) -> (String, usize) {
    streaming_hash_buf::<65536>(path)
}

fn streaming_hash_buf<const BUF_SIZE: usize>(path: &Path) -> (String, usize) {
    const HEX_CHARS: &[u8; 16] = b"0123456789abcdef";
    let mut file = fs::File::open(path).unwrap();
    let mut hasher = Sha256::new();
    let mut buffer = Box::new([0u8; BUF_SIZE]);
    let mut total = 0;
    loop {
        let n = file.read(&mut buffer[..]).unwrap();
        if n == 0 {
            break;
        }
        total += n;
        hasher.update(&buffer[..n]);
    }
    let digest = hasher.finalize();
    let mut hex = String::with_capacity(64);
    for &b in &digest {
        hex.push(HEX_CHARS[(b >> 4) as usize] as char);
        hex.push(HEX_CHARS[(b & 0x0f) as usize] as char);
    }
    (hex, total)
}

#[test]
#[ignore = "benchmark"]
fn bench_hashing_strategies() {
    let p1 = Path::new("../../build/ffmpeg/macos-arm64/ffmpeg");
    let p2 = Path::new("../../build/ffmpeg/macos-arm64/ffprobe");
    if !p1.exists() || !p2.exists() {
        println!("Skipping: media tool binaries not at build/ffmpeg/macos-arm64");
        return;
    }

    let rounds = 10;

    // Warmup
    let (h1_orig, _) = original_hash(p1);
    let (h2_orig, _) = original_hash(p2);
    let (h1_stream, _) = streaming_hash(p1);
    let (h2_stream, _) = streaming_hash(p2);
    assert_eq!(h1_orig, h1_stream);
    assert_eq!(h2_orig, h2_stream);

    // Sequential Original (allocates 35MB Vec<u8> per iteration)
    let t0 = Instant::now();
    for _ in 0..rounds {
        let (h1, _) = original_hash(p1);
        let (h2, _) = original_hash(p2);
        assert!(!h1.is_empty() && !h2.is_empty());
    }
    let orig_time = t0.elapsed();

    // Sequential Streaming (64KB buffer, 0 large heap allocations)
    let t0 = Instant::now();
    for _ in 0..rounds {
        let (h1, _) = streaming_hash(p1);
        let (h2, _) = streaming_hash(p2);
        assert!(!h1.is_empty() && !h2.is_empty());
    }
    let stream_time = t0.elapsed();

    // Concurrent Streaming (2 threads, 64KB buffer each)
    let t0 = Instant::now();
    for _ in 0..rounds {
        let (h1, h2) = std::thread::scope(|s| {
            let t1 = s.spawn(|| streaming_hash(p1));
            let t2 = s.spawn(|| streaming_hash(p2));
            (t1.join().unwrap(), t2.join().unwrap())
        });
        assert!(!h1.0.is_empty() && !h2.0.is_empty());
    }
    let concurrent_time = t0.elapsed();

    // Concurrent Streaming (2 threads, 128KB buffer each)
    let t0 = Instant::now();
    for _ in 0..rounds {
        let (h1, h2) = std::thread::scope(|s| {
            let t1 = s.spawn(|| streaming_hash_buf::<131072>(p1));
            let t2 = s.spawn(|| streaming_hash_buf::<131072>(p2));
            (t1.join().unwrap(), t2.join().unwrap())
        });
        assert!(!h1.0.is_empty() && !h2.0.is_empty());
    }
    let concurrent_128k_time = t0.elapsed();

    println!("\n=== Hashing Benchmark (10 rounds, 34.8 MB media binaries) ===");
    println!(
        "Sequential Original (35MB heap alloc): {:?} total ({:?}/iter)",
        orig_time,
        orig_time / rounds
    );
    println!(
        "Sequential Streaming (64KB buffer):    {:?} total ({:?}/iter)",
        stream_time,
        stream_time / rounds
    );
    println!(
        "Concurrent Streaming (64KB buffer):    {:?} total ({:?}/iter)",
        concurrent_time,
        concurrent_time / rounds
    );
    println!(
        "Concurrent Streaming (128KB buffer):   {:?} total ({:?}/iter)",
        concurrent_128k_time,
        concurrent_128k_time / rounds
    );
    let speedup = orig_time.as_secs_f64() / concurrent_128k_time.as_secs_f64();
    println!("Concurrent Speedup: {:.2}x\n", speedup);
}

#[test]
#[ignore = "benchmark"]
fn bench_presets_formatting() {
    use ativ_core::PRESETS;
    use std::fmt::Write as _;

    fn format_dynamic() -> String {
        let mut payload = String::with_capacity(2048);
        payload.push_str("{\"event\":\"presets\",\"items\":[");
        for (index, preset) in PRESETS.iter().enumerate() {
            if index > 0 {
                payload.push(',');
            }
            let _ = write!(
                payload,
                "{{\"platform\":\"{}\",\"aspect\":\"{}\",\"width\":{},\"height\":{}}}",
                preset.platform, preset.aspect, preset.width, preset.height
            );
        }
        payload.push_str("]}");
        payload
    }

    static PRECOMPUTED: std::sync::LazyLock<String> = std::sync::LazyLock::new(format_dynamic);

    let rounds = 100_000;
    let t0 = Instant::now();
    for _ in 0..rounds {
        let s = format_dynamic();
        assert!(!s.is_empty());
    }
    let dyn_time = t0.elapsed();

    let t0 = Instant::now();
    for _ in 0..rounds {
        let s = PRECOMPUTED.as_str();
        assert!(!s.is_empty());
    }
    let static_time = t0.elapsed();

    println!("\n=== Presets Formatting Benchmark ({} rounds) ===", rounds);
    println!(
        "Dynamic formatting: {:?} total ({:.3} µs/iter)",
        dyn_time,
        dyn_time.as_micros() as f64 / rounds as f64
    );
    println!(
        "LazyLock static:    {:?} total ({:.3} µs/iter)",
        static_time,
        static_time.as_micros() as f64 / rounds as f64
    );
    println!(
        "Speedup: {:.1}x\n",
        dyn_time.as_secs_f64() / static_time.as_secs_f64()
    );
}

#[test]
#[ignore = "benchmark"]
fn bench_hex_encoding() {
    let dummy_digest = [0xabu8; 32];
    let rounds = 100_000;

    fn hex_original(bytes: &[u8; 32]) -> String {
        bytes.iter().map(|byte| format!("{byte:02x}")).collect()
    }

    fn hex_optimized(bytes: &[u8; 32]) -> String {
        const HEX_CHARS: &[u8; 16] = b"0123456789abcdef";
        let mut s = String::with_capacity(64);
        for &b in bytes {
            s.push(HEX_CHARS[(b >> 4) as usize] as char);
            s.push(HEX_CHARS[(b & 0x0f) as usize] as char);
        }
        s
    }

    assert_eq!(hex_original(&dummy_digest), hex_optimized(&dummy_digest));

    let t0 = Instant::now();
    for _ in 0..rounds {
        let s = hex_original(&dummy_digest);
        assert_eq!(s.len(), 64);
    }
    let orig_time = t0.elapsed();

    let t0 = Instant::now();
    for _ in 0..rounds {
        let s = hex_optimized(&dummy_digest);
        assert_eq!(s.len(), 64);
    }
    let opt_time = t0.elapsed();

    println!("\n=== Hex Encoding Benchmark ({} rounds) ===", rounds);
    println!(
        "Original (32 allocations per hash):  {:?} total ({:.3} µs/iter)",
        orig_time,
        orig_time.as_micros() as f64 / rounds as f64
    );
    println!(
        "Optimized (1 allocation per hash):   {:?} total ({:.3} µs/iter)",
        opt_time,
        opt_time.as_micros() as f64 / rounds as f64
    );
    println!(
        "Speedup: {:.1}x\n",
        orig_time.as_secs_f64() / opt_time.as_secs_f64()
    );
}

#[test]
#[ignore = "benchmark"]
fn bench_json_pins_parsing() {
    const LEGACY_PIN: &str = include_str!("../../../runtime/core-runtime.json");
    const PLATFORM_PINS: &str = include_str!("../../../runtime/platform-runtimes.json");

    let rounds = 1_000;
    let t0 = Instant::now();
    for _ in 0..rounds {
        let legacy: serde_json::Value = serde_json::from_str(LEGACY_PIN).unwrap();
        let platform: serde_json::Value = serde_json::from_str(PLATFORM_PINS).unwrap();
        assert!(!legacy["targets"].is_null());
        assert!(!platform["targets"].is_null());
    }
    let parse_time = t0.elapsed();

    static LEGACY: std::sync::LazyLock<serde_json::Value> =
        std::sync::LazyLock::new(|| serde_json::from_str(LEGACY_PIN).unwrap());
    static PLATFORM: std::sync::LazyLock<serde_json::Value> =
        std::sync::LazyLock::new(|| serde_json::from_str(PLATFORM_PINS).unwrap());

    let t0 = Instant::now();
    for _ in 0..rounds {
        let legacy = &*LEGACY;
        let platform = &*PLATFORM;
        assert!(!legacy["targets"].is_null());
        assert!(!platform["targets"].is_null());
    }
    let lazy_time = t0.elapsed();

    println!("\n=== JSON Pin Parsing Benchmark ({} rounds) ===", rounds);
    println!(
        "from_str on each call: {:?} total ({:.3} µs/iter)",
        parse_time,
        parse_time.as_micros() as f64 / rounds as f64
    );
    println!(
        "LazyLock parsed once:  {:?} total ({:.3} µs/iter)",
        lazy_time,
        lazy_time.as_micros() as f64 / rounds as f64
    );
    println!(
        "Speedup: {:.1}x\n",
        parse_time.as_secs_f64() / lazy_time.as_secs_f64()
    );
}
