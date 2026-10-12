# Release readiness checklist

- For a stable release, confirm the annotated tag matches the workspace version. Main pushes use an immutable development tag created by the dedicated publisher.
- Confirm the pinned AVID Core runtime is authenticated and packaged with matching FFmpeg and FFprobe.
- Review Rust, native UI, accessibility, dependency, and security checks. Track unresolved failures without blocking unrelated development.
- For each target, require native build, package-integrity, architecture, runtime discovery, launch, and functional smoke checks before its artifact is uploaded or published.
- Confirm the dedicated publisher verifies each native job's successful package, launch, media and host-evidence steps, the same-run artifact digest, package bytes and downloadable release asset. Publish each target as soon as its own checks complete; leave failed targets absent and visible in the consolidated CI/CD issue.
- Record whether each direct download is unsigned, ad-hoc signed, Developer ID signed, notarized, or Authenticode signed. These distribution signatures are optional until configured.
- Keep unsigned direct downloads off authenticated update feeds. Any update feed requires the installed verification key, signed metadata, exact package identity, and native upgrade validation.
- Test rollback and preservation of user media before promoting an authenticated update. Never replace a published artifact or move its tag.

## Withdrawal and recovery

Remove an affected artifact and its corresponding feed entry together, publish clear release notes, and prepare a higher-version corrective release. Never advertise a missing artifact or change a signed payload without regenerating its signature. Do not rotate the installed trust key as a shortcut for an ordinary release problem.
