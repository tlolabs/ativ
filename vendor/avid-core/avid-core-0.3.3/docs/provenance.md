# Source provenance

> Historical extraction document. FFmpeg acquisition, build ownership and migration instructions are superseded by [the Core-owned FFmpeg guide](ffmpeg/README.md) and [current host handoff](ffmpeg/migration.md).
- ATIV: https://github.com/tlolabs/ativ, analyzed `2c5eeed27e48d67fed128a62ff74dab6f00c2a82`, GPL-3.0-or-later. `crates/ativ-core/src/{model,media,render,error}.rs` supply the baseline. Native origin `f488f67`, cross-platform commit `3bc4e58`, rename `34dfccc`.
- EnCAP: https://github.com/tlolabs/encap, analyzed `a96978e5bb89189b944e5dd6a30e5ee7e8fe28d4`, GPL-3.0-only. `crates/encap-video/src/lib.rs`, `crates/encap-ffmpeg/src/lib.rs`, and the Video state definitions in `crates/encap-core/src/model.rs` supply sequence, state and encoder behavior. Video integration commit `86e0b33` describes the prior AVID adaptation.
- `src/state.rs`: feature-only VideoSettings/VideoProjectState definitions and default helpers derived from EnCAP; execution adapters added here. No EnCAP project/archive or Audio/Transcript model was copied into the crate.
- `src/presets.rs`: reconciled identical ATIV and EnCAP entries, retaining EnCAP's fps=30 field.
- `src/command.rs`, `src/progress.rs`: preserve the two reference compositions and ATIV progress semantics, with unified execution settings and stricter parsing.
- Other implementation files combine the original lifecycle/safety requirements using new host-independent APIs.
- `tests/fixtures/ativ-presets.json`: complete ATIV table, plus EnCAP's existing fps field.
- `tests/fixtures/encap-graph.txt`: generated once by compiling and executing the unchanged EnCAP filter_graph/seconds functions with two 2/3-second clips, 160x90, horizontal flip. Temporary comparison tooling lives only in ignored target output, not in the shipped crate.
- `tests/fixtures/video-state.json`: small synthetic schema-1 video fixture covering every known export field plus future fields/compositions.
- `docs/source-snapshot.json`: initial reference HEADs/status and SHA-256 of tracked and unignored source files. ATIV's existing untracked assets are included and were preserved.
- `docs/reference-audit.json`: observed comparisons against the unchanged ATIV library compiled into this repository's target directory.

This historical extraction was originally published under GPL-3.0-only because EnCAP's repository uses that declaration. The identified EnCAP-derived files and all AVID Core implementation history have only Tom/Thomas Lothian as a human Git author. As copyright holder of that original work, Thomas separately grants the AVID Core version under GPL-3.0-or-later, without changing the license statement in the EnCAP repository or any prior release. The full GPLv3 text remains in `LICENSE`; [the licensing review](../LICENSING_REVIEW.md) records the rights evidence and scope. No FFmpeg executable or large third-party media asset is redistributed here. Host packaging continues to own FFmpeg licensing notices and distribution details.
