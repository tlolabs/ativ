# Release readiness checklist

- For a stable source release, confirm the annotated tag matches the workspace version and exact tested commit. A source tag does not qualify native artifacts; main pushes do not automatically build or publish releases.
- Confirm the Rust Core source identity matches Cargo.toml/Cargo.lock and the engine's `build-info`. Authenticate the independently pinned platform runtime and package matching FFmpeg and FFprobe.
- Review Rust, native UI, accessibility, dependency, and security checks. Track unresolved failures without blocking unrelated development.
- For each target, require native build, package-integrity, architecture, runtime discovery, launch, and functional smoke checks before its artifact is uploaded or published.
- Record each artifact's source revision, native checks, signing state and checksum. When using retained publication tools, preserve their source-job, artifact-digest, provenance, package-byte and public-download checks. Publish each target only after its own qualification; leave failed or unverified targets absent and document limitations.
- Keep weekly Linux/Windows smoke CI diagnostic: only a new stable source-release tag, no automatic retry, no macOS build and no release publication. Leave archived workflows inactive. Scheduled smoke results and artifacts do not establish release qualification.
- Record whether each direct download is unsigned, ad-hoc signed, Developer ID signed, notarized, or Authenticode signed. Standard macOS distributions require Developer ID signing, Apple notarization acceptance, stapling, and final Gatekeeper validation. Other platforms retain their existing signing policy.
- Keep unsigned direct downloads off authenticated update feeds. Any update feed requires the installed verification key, signed metadata, exact package identity, and native upgrade validation.
- Test rollback and preservation of user media before promoting an authenticated update. Never replace a published artifact or move its tag.

## Withdrawal and recovery

Remove an affected artifact and its corresponding feed entry together, publish clear release notes, and prepare a higher-version corrective release. Never advertise a missing artifact or change a signed payload without regenerating its signature. Do not rotate the installed trust key as a shortcut for an ordinary release problem.
