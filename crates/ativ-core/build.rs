use std::{env, fs, path::PathBuf, process::Command};

fn main() {
    let manifest = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap());
    let root = manifest.parent().unwrap().parent().unwrap();
    let core = root.parent().unwrap().join("AVID Core");
    let mapping = root.join("runtime/core-revision");
    println!("cargo:rerun-if-changed={}", mapping.display());
    let expected = fs::read_to_string(&mapping).expect("Read the tested Core revision");
    let actual = Command::new("git")
        .arg("-C")
        .arg(&core)
        .args(["rev-parse", "HEAD"])
        .output()
        .expect("Resolve the local Core checkout");
    assert!(
        actual.status.success(),
        "The canonical AVID Core checkout is required"
    );
    assert_eq!(
        String::from_utf8_lossy(&actual.stdout).trim(),
        expected.trim(),
        "Local AVID Core differs from runtime/core-revision; use the same tested revision as CI"
    );
    // Branch switches and commits must recheck the local dependency as well.
    for reference in ["HEAD", "packed-refs"] {
        let path = Command::new("git")
            .arg("-C")
            .arg(&core)
            .args([
                "rev-parse",
                "--path-format=absolute",
                "--git-path",
                reference,
            ])
            .output()
            .expect("Locate Core Git metadata");
        assert!(path.status.success());
        println!(
            "cargo:rerun-if-changed={}",
            String::from_utf8_lossy(&path.stdout).trim()
        );
    }
    let branch = Command::new("git")
        .arg("-C")
        .arg(&core)
        .args(["symbolic-ref", "-q", "HEAD"])
        .output()
        .unwrap();
    if branch.status.success() {
        let reference = String::from_utf8_lossy(&branch.stdout);
        let path = Command::new("git")
            .arg("-C")
            .arg(&core)
            .args([
                "rev-parse",
                "--path-format=absolute",
                "--git-path",
                reference.trim(),
            ])
            .output()
            .unwrap();
        println!(
            "cargo:rerun-if-changed={}",
            String::from_utf8_lossy(&path.stdout).trim()
        );
    }
}
