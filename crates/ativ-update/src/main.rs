//! ATIV distribution helper. No media or shared-core dependency.
use base64::{Engine as _, engine::general_purpose::STANDARD as B64};
use ring::signature::{ED25519, UnparsedPublicKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    error::Error,
    fs,
    io::{Read, Write},
    path::Path,
    time::Duration,
};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
const REPO: &str = "https://github.com/tlolabs/ativ/releases/";
#[derive(Deserialize)]
struct Config {
    version: String,
    channel: String,
    target: String,
    public_key: String,
}
#[derive(Deserialize, Serialize, Clone)]
struct Asset {
    url: String,
    sha256: String,
    size: u64,
    filename: String,
}
#[derive(Deserialize, Serialize)]
struct Payload {
    schema: u32,
    version: String,
    channel: String,
    assets: BTreeMap<String, Asset>,
}
#[derive(Deserialize, Serialize)]
struct Envelope {
    payload: String,
    signature: String,
}
fn verify(bytes: &[u8], config: &Config) -> Result<Payload> {
    let envelope: Envelope = serde_json::from_slice(bytes)?;
    let payload = B64.decode(envelope.payload)?;
    let key = B64.decode(&config.public_key)?;
    UnparsedPublicKey::new(&ED25519, key)
        .verify(&payload, &B64.decode(envelope.signature)?)
        .map_err(|_| "Update signature is invalid")?;
    let result: Payload = serde_json::from_slice(&payload)?;
    if result.schema != 1 || result.channel != config.channel {
        return Err("Update channel or schema mismatch".into());
    }
    let version = semver::Version::parse(&result.version)?;
    if config.channel == "stable" && !version.pre.is_empty() {
        return Err("Prerelease in stable feed".into());
    }
    for asset in result.assets.values() {
        if !asset.url.starts_with(&format!("{REPO}download/"))
            || asset.url.contains(['?', '#'])
            || asset.filename.is_empty()
            || asset.filename.contains(['/', '\\'])
            || !asset.url.ends_with(&format!("/{}", asset.filename))
            || asset.sha256.len() != 64
            || !asset.sha256.bytes().all(|x| x.is_ascii_hexdigit())
            || asset.size == 0
            || asset.size > 2 * 1024 * 1024 * 1024
        {
            return Err("Invalid update artifact metadata".into());
        }
    }
    Ok(result)
}
fn download(mut source: impl Read, mut output: impl Write, asset: &Asset) -> Result<()> {
    let mut hash = Sha256::new();
    let mut total = 0;
    let mut buffer = [0u8; 65536];
    loop {
        let n = source.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        total += n as u64;
        if total > asset.size {
            return Err("Update exceeds signed size".into());
        }
        hash.update(&buffer[..n]);
        output.write_all(&buffer[..n])?;
    }
    if total != asset.size || format!("{:x}", hash.finalize()) != asset.sha256 {
        return Err("Update checksum or size mismatch".into());
    }
    Ok(())
}
fn run() -> Result<()> {
    let directory = std::env::current_exe()?
        .parent()
        .ok_or("Missing executable directory")?
        .to_owned();
    let config: Config = serde_json::from_slice(&fs::read(directory.join("update-config.json"))?)?;
    if !["stable", "development"].contains(&config.channel.as_str()) {
        return Err("Invalid build channel".into());
    }
    if B64.decode(&config.public_key)?.len() != 32 {
        return Err("This build has no update verification key".into());
    }
    let command = std::env::args().nth(1).unwrap_or_else(|| "check".into());
    if !["check", "download", "install-appimage"].contains(&command.as_str()) {
        return Err("Unknown update command".into());
    }
    let feed = if config.channel == "stable" {
        format!("{REPO}latest/download/latest.json")
    } else {
        format!("{REPO}download/development/latest.json")
    };
    let client = reqwest::blocking::Client::builder()
        .https_only(true)
        .connect_timeout(Duration::from_secs(20))
        .timeout(Duration::from_secs(900))
        .user_agent("ATIV-updater")
        .build()?;
    let mut bytes = Vec::new();
    client
        .get(feed)
        .timeout(Duration::from_secs(30))
        .send()?
        .error_for_status()?
        .take(1024 * 1024 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 1024 * 1024 {
        return Err("Update metadata is too large".into());
    }
    let payload = verify(&bytes, &config)?;
    let available =
        semver::Version::parse(&payload.version)? > semver::Version::parse(&config.version)?;
    let asset = payload.assets.get(&config.target);
    if !available || asset.is_none() {
        println!(
            "{}",
            serde_json::json!({"available":false,"version":payload.version})
        );
        return Ok(());
    }
    let asset = asset.unwrap();
    if command == "check" {
        println!(
            "{}",
            serde_json::json!({"available":true,"version":payload.version})
        );
        return Ok(());
    }
    let response = client.get(&asset.url).send()?.error_for_status()?;
    if command == "install-appimage" {
        if !config.target.ends_with("appimage") {
            return Err("This build is managed by the system package installer".into());
        }
        let target = std::env::var("APPIMAGE")?;
        let target = Path::new(&target);
        if !target.is_absolute() || fs::symlink_metadata(target)?.file_type().is_symlink() {
            return Err("Invalid AppImage installation path".into());
        }
        let mut staged =
            tempfile::NamedTempFile::new_in(target.parent().ok_or("Missing AppImage parent")?)?;
        download(response, &mut staged, asset)?;
        staged.as_file().sync_all()?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            staged
                .as_file()
                .set_permissions(fs::Permissions::from_mode(0o755))?;
        }
        staged.persist(target)?;
        println!(
            "{}",
            serde_json::json!({"installed":true,"version":payload.version})
        );
    } else {
        let directory = tempfile::Builder::new().prefix("ativ-update-").tempdir()?;
        let path = directory.path().join(&asset.filename);
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)?;
        download(response, &mut file, asset)?;
        file.sync_all()?;
        let _ = directory.keep();
        println!(
            "{}",
            serde_json::json!({"path":path,"version":payload.version})
        );
    }
    Ok(())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("Update failed: {error}");
        std::process::exit(1);
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use ring::signature::{Ed25519KeyPair, KeyPair};
    fn fixture(channel: &str) -> (Config, Vec<u8>) {
        let key = Ed25519KeyPair::from_seed_unchecked(&[7; 32]).unwrap();
        let config = Config {
            version: "0.2.1".into(),
            channel: "stable".into(),
            target: "linux-x64-deb".into(),
            public_key: B64.encode(key.public_key().as_ref()),
        };
        let payload = serde_json::to_vec(&Payload {
            schema: 1,
            version: "0.3.0".into(),
            channel: channel.into(),
            assets: BTreeMap::new(),
        })
        .unwrap();
        let envelope = Envelope {
            payload: B64.encode(&payload),
            signature: B64.encode(key.sign(&payload)),
        };
        (config, serde_json::to_vec(&envelope).unwrap())
    }
    #[test]
    fn verifies_signature_and_rejects_tampering() {
        let (config, bytes) = fixture("stable");
        assert!(verify(&bytes, &config).is_ok());
        let mut envelope: Envelope = serde_json::from_slice(&bytes).unwrap();
        envelope.payload = B64.encode(b"tampered");
        assert!(verify(&serde_json::to_vec(&envelope).unwrap(), &config).is_err());
    }
    #[test]
    fn rejects_wrong_channel_and_key() {
        let (mut config, bytes) = fixture("development");
        assert!(verify(&bytes, &config).is_err());
        config.public_key = B64.encode([8; 32]);
        assert!(verify(&bytes, &config).is_err());
    }
    #[test]
    fn download_rejects_corruption_truncation_and_overflow() {
        let data = b"verified artifact";
        let asset = Asset {
            url: String::new(),
            filename: String::new(),
            size: data.len() as u64,
            sha256: format!("{:x}", Sha256::digest(data)),
        };
        assert!(download(&data[..], Vec::new(), &asset).is_ok());
        assert!(download(&data[..3], Vec::new(), &asset).is_err());
        assert!(download(&b"corrupted artifact"[..], Vec::new(), &asset).is_err());
    }
}
