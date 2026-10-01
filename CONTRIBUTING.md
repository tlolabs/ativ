# Contributing to ATIV

Outside contributions are welcome. Thomas Lothian is the sole maintainer and final release authority. Start with an issue for substantial changes, then submit a focused pull request to `main`.

Run the checks described in [docs/TESTING.md](docs/TESTING.md), update relevant documentation, and identify the platforms you actually tested. Preserve third-party notices and disclose any new dependency or asset license. Contributions to original ATIV code and assets must be compatible with GPL-3.0-or-later; combined binaries also include components under their own licenses, including GPL-3.0-only AVID Core.

The project uses the [Developer Certificate of Origin 1.1](https://developercertificate.org/). Add `Signed-off-by: Your Name <your-address>` to each contributed commit, for example with `git commit -s`. This certifies that you have the right to submit the contribution under the applicable licenses. A CLA is not required.

Use concise, descriptive, imperative commit subjects. Do not include secrets, personal machine paths, or generated build output.

## Commit signing

Use unsigned Git commits for ATIV. Disable automatic cryptographic commit signing in each clone with:

```sh
git config --local commit.gpgsign false
```

Create contributions with `git commit --no-gpg-sign -s`. The `Signed-off-by` trailer records the Developer Certificate of Origin; it is plain commit-message text and remains required. It does not require a PGP key.

When replacing historical signed commits, preserve the complete message (including DCO trailers), author and committer identities and timestamps, file trees, and merge topology. Removing a signature changes that commit's ID and the IDs of its descendants. Preserve the original history in a verified Git bundle and retain an old-to-new commit map before updating branch references. Coordinate published-history rewrites and use explicit `--force-with-lease` expectations; existing clones must reconcile with the replacement history.

GitHub-created merge commits and bot commits can carry GitHub-managed signatures even when local automatic signing is disabled. Maintainers should create and push merges locally with `git -c commit.gpgsign=false merge` when an unsigned merge is needed. Existing GitHub signatures do not require contributors to obtain or manage a signing key.

Commit signing is separate from release-tag, application, artifact, and update-feed signing. Those requirements remain governed by [the code signing policy](CODE_SIGNING_POLICY.md).
