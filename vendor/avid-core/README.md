# Frozen AVID Core source

ATIV integrates the local AVID Core 0.3.3 commit
`8e27a86ec106028d93130de35a35c0eeda7a9ce3`. As checked on November 10, 2026,
that commit and its local `v0.3.3` tag were not published upstream. This is an
explicitly authorized local integration, not a claim of an upstream release.

The workspace and lockfile retain the immutable Git identity. The checked-in
`.cargo/config.toml` replaces only that exact Git source with this directory so
clean ATIV checkouts can build without the unpublished commit or a sibling Core
checkout. Other Cargo dependencies still use their ordinary locked sources.
The media runtime and Apple transcription source have independent pins and
authentication; this replacement changes neither.

`avid-core-0.3.3` contains 71 unmodified tracked files from that commit, covering
the crate, tests, examples, benchmark, runtime specification, licenses, and the
selected integration documentation. Its `.cargo-checksum.json` is generated
Cargo directory-source metadata; it is the only file added inside the crate.
The outside `source-manifest.json` records every exported path and SHA-256.
Its snapshot SHA-256 is
`028cdd71f6a9ff716766b3ca677bf6f4e62c340aa9f6043041de691cf5e67e14`,
computed over UTF-8 JSON of `files_sha256` with sorted keys and separators
`(',', ':')`. This identifies the selected file set, not the entire Core Git tree.

Validate the checked-in snapshot, immutable identity, Cargo checksum metadata,
workspace pin, lockfile, and source replacement using Python 3.11 or later:

```sh
python3 -B script/verify_core_source.py
python3 -B script/test_core_source.py
cargo metadata --locked --offline --format-version 1
```

The Python checks require no network, sibling repository, Cargo registry cache,
or Apple SDK. The Cargo command additionally needs its locked registry sources
already cached. Validation does not establish upstream publication or native
artifact qualification. Existing release and notarization policies apply.

To reproduce the exported bytes when the exact original commit is available,
use an authenticated Core checkout or object store and, for each path in
`files_sha256`, save the raw output of
`git -C /absolute/core-checkout show 8e27a86ec106028d93130de35a35c0eeda7a9ce3:PATH`
at that path below a fresh `avid-core-0.3.3` directory. Use subprocess argument
arrays and binary file output rather than shell interpolation. Create
`.cargo-checksum.json` with `{"files": <files_sha256>, "package": null}`. Verify
every file against the manifest and run the validator above; do not normalize
line endings or modify upstream files. The manifest paths are the authoritative
subset selection. Preserve Core's GPL-3.0-or-later license, provenance, and native
image-codec notices when redistributing.

A future update must deliberately refresh the immutable pin, exported bytes,
manifest, checksum metadata, source replacement, and verifier's approved identity
together. Do not substitute a moving branch or silently use a different checkout.
