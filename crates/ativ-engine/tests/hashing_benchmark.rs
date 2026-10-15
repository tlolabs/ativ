//! Diagnostic benchmarks; opt in with --release --ignored --nocapture --test-threads=1.
use sha2::{Digest, Sha256};
use std::{fs, hint::black_box, io::Read, path::Path, sync::LazyLock, time::Instant};

fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut result = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        result.push(DIGITS[(b >> 4) as usize] as char);
        result.push(DIGITS[(b & 15) as usize] as char);
    }
    result
}
fn hash<const SIZE: usize>(path: &Path) -> String {
    let mut source = fs::File::open(path).unwrap();
    let mut buffer = [0; SIZE];
    let mut digest = Sha256::new();
    loop {
        let n = source.read(&mut buffer).unwrap();
        if n == 0 {
            break;
        }
        digest.update(&buffer[..n]);
    }
    hex(&digest.finalize())
}

#[test]
#[ignore = "benchmark: requires explicit ATIV_BENCH_FFMPEG and ATIV_BENCH_FFPROBE"]
fn bench_hashing_strategies() {
    let first = std::env::var("ATIV_BENCH_FFMPEG").expect("Set ATIV_BENCH_FFMPEG");
    let second = std::env::var("ATIV_BENCH_FFPROBE").expect("Set ATIV_BENCH_FFPROBE");
    let (a, b) = (Path::new(&first), Path::new(&second));
    let expected = (
        hex(&Sha256::digest(fs::read(a).unwrap())),
        hex(&Sha256::digest(fs::read(b).unwrap())),
    );
    println!(
        "hash input bytes: {} + {}",
        fs::metadata(a).unwrap().len(),
        fs::metadata(b).unwrap().len()
    );
    for sample in 0..11 {
        for offset in 0..3 {
            let mode = (sample + offset) % 3;
            let start = Instant::now();
            let actual = match mode {
                0 => (hash::<65536>(a), hash::<65536>(b)),
                1 => std::thread::scope(|s| {
                    let a = s.spawn(|| hash::<65536>(a));
                    let b = s.spawn(|| hash::<65536>(b));
                    (a.join().unwrap(), b.join().unwrap())
                }),
                _ => std::thread::scope(|s| {
                    let a = s.spawn(|| hash::<131072>(a));
                    let b = s.spawn(|| hash::<131072>(b));
                    (a.join().unwrap(), b.join().unwrap())
                }),
            };
            let elapsed = start.elapsed().as_secs_f64();
            assert_eq!(actual, expected);
            println!("hash sample={sample} mode={mode} seconds={elapsed:.9}");
        }
    }
}

#[test]
#[ignore = "benchmark"]
fn bench_hex_encoding() {
    let bytes: [u8; 32] = std::array::from_fn(|n| n as u8);
    assert_eq!(
        hex(&bytes),
        bytes.iter().map(|b| format!("{b:02x}")).collect::<String>()
    );
    for sample in 0..11 {
        for offset in 0..2 {
            let mode = (sample + offset) % 2;
            let start = Instant::now();
            for _ in 0..100_000 {
                let bytes = black_box(&bytes);
                black_box(if mode == 0 {
                    bytes.iter().map(|b| format!("{b:02x}")).collect::<String>()
                } else {
                    hex(bytes)
                });
            }
            println!(
                "hex sample={sample} mode={mode} seconds_per_iteration={:.12}",
                start.elapsed().as_secs_f64() / 100_000.0
            );
        }
    }
}

#[test]
#[ignore = "benchmark"]
fn bench_json_pins_parsing() {
    const A: &str = include_str!("../../../runtime/core-runtime.json");
    const B: &str = include_str!("../../../runtime/platform-runtimes.json");
    fn first() -> serde_json::Value {
        serde_json::from_str(black_box(A)).unwrap()
    }
    fn second() -> serde_json::Value {
        serde_json::from_str(black_box(B)).unwrap()
    }
    for sample in 0..11 {
        let a = LazyLock::new(first);
        let b = LazyLock::new(second);
        let start = Instant::now();
        black_box((&*a, &*b));
        println!(
            "json sample={sample} first_initialization_seconds={:.9}",
            start.elapsed().as_secs_f64()
        );
        for offset in 0..2 {
            let mode = (sample + offset) % 2;
            let start = Instant::now();
            for _ in 0..1000 {
                if mode == 0 {
                    let (parsed_a, parsed_b) = (first(), second());
                    black_box((&parsed_a["targets"], &parsed_b["targets"]));
                } else {
                    black_box((&black_box(&*a)["targets"], &black_box(&*b)["targets"]));
                }
            }
            println!(
                "json sample={sample} mode={mode} seconds_per_iteration={:.12}",
                start.elapsed().as_secs_f64() / 1000.0
            );
        }
    }
}

#[test]
#[ignore = "benchmark"]
fn bench_presets_formatting() {
    use std::fmt::Write as _;
    fn format_dynamic() -> String {
        let mut payload = String::with_capacity(2048);
        payload.push_str("{\"event\":\"presets\",\"items\":[");
        for (index, preset) in ativ_core::PRESETS.iter().enumerate() {
            if index > 0 {
                payload.push(',');
            }
            write!(
                payload,
                "{{\"platform\":\"{}\",\"aspect\":\"{}\",\"width\":{},\"height\":{}}}",
                preset.platform, preset.aspect, preset.width, preset.height
            )
            .unwrap();
        }
        payload.push_str("]}");
        payload
    }
    let cached = LazyLock::new(format_dynamic);
    let first = Instant::now();
    assert_eq!(&*cached, &format_dynamic());
    println!(
        "presets initialization plus equality check: {:?}",
        first.elapsed()
    );
    for mode in 0..2 {
        let start = Instant::now();
        for _ in 0..100_000 {
            if mode == 0 {
                black_box(format_dynamic());
            } else {
                black_box(black_box(&*cached).as_str());
            }
        }
        println!(
            "presets mode={mode} seconds_per_iteration={:.12}",
            start.elapsed().as_secs_f64() / 100_000.0
        );
    }
}
