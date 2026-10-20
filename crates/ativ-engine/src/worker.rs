//! All ATIV media processes for this user share one cancellable worker permit.
//! The OS releases the lock on exit/crash. Keeping the lock inode avoids races
//! between old waiters and new processes; it is outside media/output directories.
use ativ_core::{AtivError, CancellationToken};
use fs2::FileExt;
use sha2::{Digest, Sha256};
use std::{
    fs::{File, OpenOptions},
    io, thread,
    time::Duration,
};

pub fn lock_path() -> std::path::PathBuf {
    let identity = std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .unwrap_or_default();
    let key = Sha256::digest(identity.as_encoded_bytes());
    let name = key.iter().map(|b| format!("{b:02x}")).collect::<String>();
    std::env::temp_dir().join(format!("ativ-engine-worker-{name}.lock"))
}

pub fn acquire(token: &CancellationToken) -> ativ_core::Result<File> {
    let path = lock_path();
    let mut options = OpenOptions::new();
    options.create(true).truncate(false).read(true).write(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let file = options
        .open(&path)
        .map_err(|_| AtivError::InvalidInput("Could not acquire the media worker.".into()))?;
    loop {
        if token.is_cancelled() {
            return Err(AtivError::cancelled());
        }
        match file.try_lock_exclusive() {
            Ok(()) => return Ok(file),
            Err(error) if contended(&error) => thread::sleep(Duration::from_millis(20)),
            Err(_) => {
                return Err(AtivError::InvalidInput(
                    "Could not acquire the media worker.".into(),
                ));
            }
        }
    }
}

fn contended(error: &io::Error) -> bool {
    error.kind() == io::ErrorKind::WouldBlock
        || error.raw_os_error() == fs2::lock_contended_error().raw_os_error()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn recognizes_native_lock_contention() {
        assert!(contended(&fs2::lock_contended_error()));
        assert!(!contended(&io::Error::from(io::ErrorKind::NotFound)));
    }
}
