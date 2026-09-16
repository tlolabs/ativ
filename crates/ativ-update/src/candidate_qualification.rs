//! Ignored, credentialed qualification of actual packages through production verification.
use super::*;
use ring::signature::{Ed25519KeyPair, KeyPair};

#[test]
#[ignore = "requires actual candidate packages and configured owner update credentials"]
fn qualifies_real_candidate_package_signatures() {
    assert_eq!(std::env::var("ATIV_QUALIFICATION_R7").as_deref(), Ok("1"));
    let config: Config = serde_json::from_slice(
        &fs::read(std::env::var("ATIV_QUALIFICATION_CONFIG").expect("candidate config")).unwrap(),
    )
    .unwrap();
    assert_eq!(config.channel, "development");
    let seed = B64
        .decode(std::env::var("ATIV_UPDATE_PRIVATE_KEY").expect("update signing credential"))
        .expect("base64 signing seed");
    let key = Ed25519KeyPair::from_seed_unchecked(&seed).expect("Ed25519 signing seed");
    assert_eq!(
        key.public_key().as_ref(),
        B64.decode(&config.public_key).unwrap()
    );
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap();
    let mut reports = Vec::new();
    for entry in fs::read_dir(root.join("packages")).unwrap() {
        let path = entry.unwrap().path();
        if !path.is_file() {
            continue;
        }
        let filename = path.file_name().unwrap().to_str().unwrap().to_owned();
        let mut data = fs::read(&path).unwrap();
        assert!(!data.is_empty());
        let asset = Asset {
            url: format!("{REPO}download/development/{filename}"),
            sha256: format!("{:x}", Sha256::digest(&data)),
            size: data.len() as u64,
            filename,
        };
        let payload = Payload {
            schema: 1,
            version: config.version.clone(),
            channel: config.channel.clone(),
            assets: BTreeMap::from([(config.target.clone(), asset.clone())]),
        };
        let raw = serde_json::to_vec(&payload).unwrap();
        let envelope = Envelope {
            payload: B64.encode(&raw),
            signature: B64.encode(key.sign(&raw)),
        };
        let envelope_bytes = serde_json::to_vec(&envelope).unwrap();
        let verified = verify(&envelope_bytes, &config).expect("real package signature");
        let verified_asset = verified.assets.get(&config.target).unwrap();
        download(&data[..], std::io::sink(), verified_asset)
            .expect("real package checksum and size");
        data[0] ^= 1;
        assert!(download(&data[..], std::io::sink(), verified_asset).is_err());
        let changed = Envelope {
            payload: B64.encode(b"changed candidate metadata"),
            signature: envelope.signature.clone(),
        };
        assert!(verify(&serde_json::to_vec(&changed).unwrap(), &config).is_err());
        reports.push(serde_json::json!({"asset":asset,"envelope":envelope,
            "package_tampering_rejected":true,"metadata_tampering_rejected":true}));
    }
    assert!(!reports.is_empty(), "actual candidate packages required");
    let output = root.join("build/qualification-evidence");
    fs::create_dir_all(&output).unwrap();
    fs::write(output.join("update-signatures.json"), serde_json::to_vec_pretty(&serde_json::json!({
        "status":"passed","scope":"native updater verify/download against real candidate packages; offline, not end-to-end upgrade",
        "target":config.target,"public_key":config.public_key,"packages":reports,"published":false
    })).unwrap()).unwrap();
}
