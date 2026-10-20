# GitHub Actions optimization proposals — public ATIV scope

Historical proposals from the October 13, 2026 read-only audit; narrowed for publication on October 20, 2026. Only public ATIV evidence is retained. Other repositories and account-level usage, billing and access details are excluded. Exact originals are preserved locally in an ignored, access-restricted backup. No workflow or GitHub setting was changed by this audit.

Evidence: [audit](github-actions-audit.md) and [public ATIV inventory](github-actions-inventory.csv). These proposals require a fresh configuration check before implementation.

## Repair publication and failure-report event matching

The historical publisher used `workflows: [Native build, test, and package]`, which YAML parses as three names instead of the actual workflow name. Its six observed runs came from push or manual dispatch. Quote the exact workflow name, retain one early publication path, and invoke completed-run recovery only when required. Normalize the source run, ref and channel before serializing publication; one source revision can have both development and stable releases.

The reporter's monitored names referenced the old publisher name. Align source and YAML workflow names and paginate run, branch, tag and security enumeration before reducing report frequency. Keep failures visible in the consolidated issue, bounded retries, and independent publication of each verified target. Fixing missing recovery can add necessary execution; no runtime savings are claimed.

### Publisher configuration fragment — review only

```yaml
on:
  push:
    branches: [main]
    tags: ['v*']
  workflow_run:
    workflows: ['Native build, test, and package']
    types: [completed]
  workflow_dispatch:
    inputs:
      source_run_id:
        type: string
        required: true
jobs:
  publish:
    if: >-
      github.event_name == 'push' ||
      github.event_name == 'workflow_dispatch' ||
      (github.event.workflow_run.event == 'push' &&
       github.event.workflow_run.head_repository.full_name == github.repository &&
       (github.event.workflow_run.run_attempt > 1 ||
        github.event.workflow_run.conclusion == 'failure'))
    # Keep current runner, permissions, verification and publication steps.
    # Normalize source-run/ref identity before protecting release writes.
```

Keep `cancel-in-progress: false` for publishing. A completion with missing artifacts despite overall success needs an explicit recovery check/manual route; do not silently abandon it. This fragment restores intended event matching but is not a full final recovery implementation.

## Cache compatible build inputs and limit cancellation

ATIV had no active Actions caches in the snapshot. Consider Cargo registry, Git and build intermediates plus appropriate Swift/Qt inputs, keyed by OS, architecture, compiler, lockfile, build profile and relevant script identity. Preserve runtime receipts, hashes, attestations and final native checks. Cache hits never establish artifact qualification.

Cancel only superseded disposable validation. Signing, qualification and publication need protected operation identities and must not be interrupted by an unrelated same-ref dispatch. Measure setup and compile duration after a bounded pilot; no savings are established by the current evidence.

## Scope reference and documentation work to verified inputs

The historical Qt reference job ran on every non-tag event, including non-macOS manual platform requests. Five dispatch reference jobs used approximately 13.6 macOS minutes, but the retained API data did not establish which were unnecessary. Keep reference coverage for shared engine, Qt, runtime, dependency, workflow, packaging and related inputs; allow explicit reference requests and periodic full validation.

Skip native packaging for documentation-only changes only after confirming the files are not build or package inputs. Do not broadly exclude licenses or notices. Keep tag-native qualification and conservative input coverage. No exact savings calculation is justified by this audit.

## Reduce idle publication work without delaying verified targets

ATIV's six publisher runs used 97.1 job minutes, including verification, uploads, download checks and polling. Investigate per-target publishers that begin after that target's native checks and reuse exact same-run artifacts. Retain idempotent manual recovery, same-source and target identities, package digests, native derivative checks, and independent publication when siblings fail. Additional short publisher jobs incur setup cost; polling runtime is not entirely avoidable.

## Shorten only ordinary artifact retention

ATIV's snapshot contained 343 nonexpired artifacts totaling 41.010 GiB; this includes history outside the execution window. Common package retention was 30 days and reference retention 14 days. Consider 7–14 days only for ordinary CI candidates whose downstream recovery window permits it. Preserve required provenance, immutable runtime references, signing and upgrade qualification inputs, and unresolved diagnostic evidence. No artifact was deleted and no financial saving is asserted.

## Keep failure reporting useful

ATIV's 41 report runs used 8.1 job minutes. After fixing name drift and pagination, serialize issue mutation and coalesce refreshes that read the same current state. Primary completion, publication failure, retry failure, security freshness and recovery must still refresh the consolidated issue. Keep the daily reconciliation. No reduction should hide failures or create a mandatory development check.

## Preserve verification and release policy

- Retain all six native OS/CPU targets and existing package formats.
- Preserve each artifact's integrity, identity, runtime dependency, launch and functional checks, including native checks after optional signing or attestation.
- Preserve dependency and security analysis, runtime origin authentication, signed update metadata, installed verification keys and upgrade checks.
- Keep successful targets independent and failed or unverified artifacts unpublished. Keep unsigned direct downloads outside authenticated update feeds.
- Keep diagnostic failures nonblocking, bounded retries automated, and unresolved failures tracked in the consolidated issue.
- Add no mandatory DCO, signed commits, reviews, approvals, branch protection or required status checks.

For any later authorized implementation, validate parsed YAML and representative push, PR, tag, dispatch, schedule and retry events; verify independent native publication and source/runtime identity; then measure job runtime once before and after. This historical audit applied no workflow changes, dispatched no Actions, and published nothing.
