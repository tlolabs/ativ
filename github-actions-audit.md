# GitHub Actions audit — public ATIV scope

Historical read-only audit dated October 13, 2026 (America/Los_Angeles). This publication was narrowed on October 20, 2026 to the public `tlolabs/ativ` repository. All other repositories and account-level usage, billing and access details are excluded. Exact original reports are preserved locally in an ignored, access-restricted backup. No workflows, repository settings, issues, releases, commits or pushes were changed by the audit.

## Scope and interpretation

The execution window is September 14, 2026 at 05:07:09 UTC through October 14, 2026 at 05:07:09 UTC. The entries below describe the retained public ATIV history and source snapshots collected for that window; they are not a fresh statement about the current release or current remote settings.

Public ATIV's inventory contains seven current YAML workflows, two registrations whose YAML was removed from the default branch, and two GitHub-managed workflows. An API-active removed file is not proof of a runnable workflow. Managed workflow policy is not fully described by repository YAML.

Observed job runtime sums nonnegative job completion minus start times across all retained attempts, excluding queue time. Parallel job durations add together. The CSV's elapsed-run proxy can include waits and metadata changes and must not be treated as runner runtime. Retained historical success does not qualify a new release artifact. Deleted history cannot be reconstructed.

## Public ATIV workflow inventory

| Repository | Workflow / file | Presence / API state | Events | Runners | Jobs | Runs / attempts | Job minutes | Observed events |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |
| ativ | Attest and verify native Linux AppImages<br>`.github/workflows/attest-linux.yml` | current_yaml / active | workflow_dispatch | ubuntu-24.04, ubuntu-24.04-arm | 2 | 0 / 0 | 0.0 | {} |
| ativ | FFmpeg Windows source diagnostic<br>`.github/workflows/ffmpeg-diagnostic.yml` | removed_from_default_branch / active | workflow_dispatch, push | windows-2025 | 1 | 1 / 1 | 20.3 | {"push":1} |
| ativ | Native build, test, and package<br>`.github/workflows/native-release.yml` | current_yaml / active | workflow_dispatch, pull_request, push | macos-15, macos-15-intel, ubuntu-24.04, ubuntu-24.04-arm, windows-11-arm, windows-2025 | 5 | 99 / 100 | 2,289.6 | {"push":22,"pull_request":35,"workflow_dispatch":42} |
| ativ | Publish independently verified native platforms<br>`.github/workflows/publish-recovered-artifacts.yml` | current_yaml / active | push, workflow_run, workflow_dispatch | ubuntu-24.04 | 1 | 6 / 6 | 97.1 | {"push":4,"workflow_dispatch":2} |
| ativ | Recipe 7 host qualification (no publication)<br>`.github/workflows/recipe7-qualification.yml` | removed_from_default_branch / active | workflow_dispatch, push | macos-15, macos-15-intel, ubuntu-24.04, ubuntu-24.04-arm, windows-11-arm, windows-2025 | 4 | 3 / 3 | 137.2 | {"push":3} |
| ativ | Report CI/CD failures<br>`.github/workflows/report-ci-failures.yml` | current_yaml / active | workflow_run, schedule, workflow_dispatch | ubuntu-24.04 | 1 | 41 / 41 | 8.1 | {"schedule":2,"workflow_run":38,"workflow_dispatch":1} |
| ativ | Retry failed verification workflows<br>`.github/workflows/retry-failed-verification.yml` | current_yaml / active | workflow_run | ubuntu-24.04 | 1 | 17 / 17 | 0.1 | {"workflow_run":17} |
| ativ | Sign Windows portable packages with Azure<br>`.github/workflows/sign-windows.yml` | current_yaml / active | workflow_dispatch | windows-11-arm, windows-2025 | 2 | 0 / 0 | 0.0 | {} |
| ativ | Verify locally notarized Mac qualification packages<br>`.github/workflows/verify-macos.yml` | current_yaml / active | workflow_dispatch | macos-15, macos-15-intel | 1 | 0 / 0 | 0.0 | {} |
| ativ | Dependabot Updates<br>`dynamic/dependabot/dependabot-updates` | managed / active | managed/unknown | Linux | unknown | 27 / 27 | 23.4 | {"dynamic":27} |
| ativ | Dependency Graph<br>`dynamic/dependabot/update-graph` | managed / active | managed/unknown | Linux | unknown | 1 / 1 | 0.6 | {"dynamic":1} |
| ativ | 35 | 0 | 40.4 |

## Trigger map and execution chains

1. Main/`v*` push, PR or manual dispatch → `native-release.yml`: independent Rust quality job and two native architectures each on macOS/Windows/Linux, plus a non-tag Qt Mac ARM64 reference. Native jobs have no sibling `needs`. Manual platform selection limits native groups but never constrains `engine`/`qt-reference`.
2. The same push independently starts an Ubuntu publisher, polling matching native artifacts and publishing each verified target as soon as available. It does not rebuild packages. Polling waits up to 150 minutes; six publisher runs used 97.1 minutes.
3. **The configured publisher workflow-run name is malformed:** `[Native build, test, and package]` parses as three names (`Native build`, `test`, `and package`), not the actual `Native build, test, and package`. Requested/completed native events therefore do not match. Observed publisher runs were four pushes and two dispatches, zero workflow-run events. Correcting the quoting while retaining push + requested + completed creates up to three launch opportunities; SHA concurrency serializes, but does not deduplicate, them. Those duplicates are a future risk, not observed waste.
4. Native completion → first-party first-attempt failure-only retry of failed jobs, plus failure reporter. Retry-workflow completion → another reporter; retried native completion → another reporter and usually skipped retry-workflow record. Publication completion also triggers reporting. Retry cap prevents loops; skipped records are not billable work estimates.
5. Failure reporter runs daily at `06:17 UTC` and manually, without concurrency. Its Python monitored-name set still lists `Publish recovered platform artifacts`, but actual publisher name is `Publish independently verified native platforms`. Repair this omission before thinning report triggers. The script only scans the latest 100 runs and first-page branch/tag/security listings, which can hide current failures during heavy activity.
6. Mac notarized qualification, Azure Windows signing and Linux attestation are manual, acquire exact same-commit native artifacts, and verify final derivatives on target architectures. These checks are required derivative validation rather than duplicate original compilation. Windows/Linux prepare once, then verify on two native targets; Mac directly verifies on two native targets.

`workflow_run` chains depend on exact upstream workflow names. `workflow_call` jobs execute within their caller. Default `GITHUB_TOKEN` repository writes generally do not recursively trigger push/release workflows; dispatch events and other credentials can behave differently. See [GitHub event behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).

## Repeated revisions and local optimization evidence

Public ATIV had 35 multi-run workflow/source-SHA groups and no exact main-push/PR-head SHA pairs in this window. Later attempts used 40.4 job minutes. Repeated source revisions can represent deliberate platform selection, signing options, retries and release channels; these figures are not proven waste.

ATIV's six publisher runs used 97.1 job minutes, including useful verification and publication as well as polling. Five historical manual-dispatch Qt reference jobs used approximately 13.6 macOS minutes, but retained API inputs did not establish which were unnecessary. These figures are ceilings for investigation, not savings claims.

ATIV's snapshot had 343 nonexpired artifact records totaling 41.010 GiB and no active Actions caches. Artifact sizes include older runs outside the execution window. Consider shorter retention only for ordinary CI artifacts after preserving runtime provenance, signing, upgrade qualification and recovery lifetimes. No artifact was deleted or downloaded for this audit.

## Recommendations and verification limits

[Optimization proposals](github-actions-optimization.md) preserve six native targets, existing package formats, independent publication, automated diagnostic checks, bounded retries, optional direct-download signing, and authenticated update verification. They are historical proposals, not applied configuration.

The audit inspected public ATIV workflow definitions, available removed snapshots, retained runs and all-attempt job pages. It performed no native build, signing, publication, fresh release qualification or GitHub mutation. Each future artifact still requires its own native integrity, identity, dependency, launch and functional verification. Unsigned direct downloads must remain outside authenticated update feeds.

ATIV's `AGENTS.md` retains voluntary `git commit -s` as a convention. No mandatory DCO, signatures, review, approval, protection, required status checks or development gates are proposed.

## Public ATIV configuration appendix

These are historical source snapshots. Runner expressions may depend on caller inputs. GitHub-managed definitions have no inspectable repository YAML in this appendix.

### tlolabs/ativ — Attestand verify native Linux AppImages

current_yaml; [source](https://github.com/tlolabs/ativ/blob/main/.github/workflows/attest-linux.yml).

```json
{
  "file": ".github/workflows/attest-linux.yml",
  "on": {
    "workflow_dispatch": {
      "inputs": {
        "native_run": {
          "description": "Same-commit native Linux qualification run",
          "type": "string",
          "required": true
        }
      }
    }
  },
  "concurrency": null,
  "jobs": {
    "attest": {
      "runs-on": "ubuntu-24.04"
    },
    "verify-native": {
      "name": "Verify attested Linux ${{ matrix.target }}",
      "runs-on": "${{ matrix.runner }}",
      "strategy": {
        "fail-fast": false,
        "matrix": {
          "include": [
            {
              "runner": "ubuntu-24.04",
              "target": "linux-x86_64",
              "label": "x64"
            },
            {
              "runner": "ubuntu-24.04-arm",
              "target": "linux-arm64",
              "label": "arm64"
            }
          ]
        }
      },
      "needs": "attest"
    }
  }
}
```

### tlolabs/ativ — FFmpeg Windows source diagnostic

removed_from_default_branch; [source](https://github.com/tlolabs/ativ/blob/551968543cfae1387a4369931201d07e3626a5ea/.github/workflows/ffmpeg-diagnostic.yml).

```json
{
  "file": ".github/workflows/ffmpeg-diagnostic.yml",
  "on": {
    "workflow_dispatch": null,
    "push": {
      "branches": [
        "codex/ativ-owned-ffmpeg"
      ],
      "paths": [
        ".github/workflows/ffmpeg-diagnostic.yml",
        "script/diagnose_ffmpeg_windows.py"
      ]
    }
  },
  "concurrency": null,
  "jobs": {
    "diagnose": {
      "runs-on": "windows-2025",
      "strategy": {
        "fail-fast": false,
        "matrix": {
          "include": [
            {
              "system": "CLANG64",
              "compiler": "clang",
              "packages": "clang:p llvm:p lld:p pkgconf:p gdb:p"
            },
            {
              "system": "UCRT64",
              "compiler": "gcc",
              "packages": "gcc:p llvm:p pkgconf:p gdb:p"
            }
          ]
        }
      }
    }
  }
}
```

### tlolabs/ativ — Native build, test, and package

current_yaml; [source](https://github.com/tlolabs/ativ/blob/main/.github/workflows/native-release.yml).

```json
{
  "file": ".github/workflows/native-release.yml",
  "on": {
    "workflow_dispatch": {
      "inputs": {
        "platform": {
          "description": "Native platform group to qualify",
          "type": "choice",
          "options": [
            "all",
            "macos",
            "windows",
            "linux"
          ],
          "default": "all"
        },
        "stable_macos": {
          "description": "Compatibility input; manual builds use the application version without requiring signing",
          "type": "boolean",
          "default": false
        },
        "owner_testing": {
          "description": "Build packages for owner testing without application acceptance prerequisites",
          "type": "boolean",
          "default": false
        },
        "qualify_core_candidate": {
          "description": "Use the exact authenticated candidate for unpublished host qualification",
          "type": "boolean",
          "default": false
        },
        "clean_ffmpeg": {
          "description": "Reserved compatibility input; Core artifacts are acquired, never rebuilt",
          "type": "boolean",
          "default": false
        },
        "sign_macos": {
          "description": "Sign and notarize macOS validation artifacts (does not publish a release)",
          "type": "boolean",
          "default": false
        }
      }
    },
    "pull_request": null,
    "push": {
      "branches": [
        "main"
      ],
      "tags": [
        "v*"
      ]
    }
  },
  "concurrency": {
    "group": "native-${{ github.ref }}-${{ inputs.platform || 'all' }}",
    "cancel-in-progress": "${{ !startsWith(github.ref, 'refs/tags/') }}"
  },
  "jobs": {
    "engine": {
      "name": "Shared Rust engine",
      "runs-on": "ubuntu-24.04"
    },
    "macos": {
      "name": "macOS ${{ matrix.arch }}",
      "runs-on": "${{ matrix.runner }}",
      "strategy": {
        "fail-fast": false,
        "matrix": {
          "include": [
            {
              "arch": "arm64",
              "runtime_arch": "arm64",
              "runner": "macos-15"
            },
            {
              "arch": "x86_64",
              "runtime_arch": "x86_64",
              "runner": "macos-15-intel"
            }
          ]
        }
      },
      "if": "github.event_name == 'push' || github.event_name == 'pull_request' || (github.event_name == 'workflow_dispatch' && (inputs.platform == 'all' || inputs.platform == 'macos'))"
    },
    "windows": {
      "name": "Windows ${{ matrix.arch }}",
      "runs-on": "${{ matrix.runner }}",
      "strategy": {
        "fail-fast": false,
        "matrix": {
          "include": [
            {
              "arch": "x64",
              "runtime_arch": "x86_64",
              "runner": "windows-2025"
            },
            {
              "arch": "ARM64",
              "runtime_arch": "arm64",
              "runner": "windows-11-arm"
            }
          ]
        }
      },
      "if": "github.event_name == 'push' || github.event_name == 'pull_request' || (github.event_name == 'workflow_dispatch' && (inputs.platform == 'all' || inputs.platform == 'windows'))"
    },
    "linux": {
      "name": "Linux ${{ matrix.arch }}",
      "runs-on": "${{ matrix.runner }}",
      "strategy": {
        "fail-fast": false,
        "matrix": {
          "include": [
            {
              "arch": "x86_64",
              "runtime_arch": "x86_64",
              "runner": "ubuntu-24.04"
            },
            {
              "arch": "aarch64",
              "runtime_arch": "arm64",
              "runner": "ubuntu-24.04-arm"
            }
          ]
        }
      },
      "if": "github.event_name == 'push' || github.event_name == 'pull_request' || (github.event_name == 'workflow_dispatch' && (inputs.platform == 'all' || inputs.platform == 'linux'))"
    },
    "qt-reference": {
      "name": "Internal Qt macOS arm64 reference",
      "runs-on": "macos-15",
      "if": "${{ !startsWith(github.ref, 'refs/tags/') }}"
    }
  }
}
```

### tlolabs/ativ — Publish independently verified native platforms

current_yaml; [source](https://github.com/tlolabs/ativ/blob/main/.github/workflows/publish-recovered-artifacts.yml).

```json
{
  "file": ".github/workflows/publish-recovered-artifacts.yml",
  "on": {
    "push": {
      "branches": [
        "main"
      ],
      "tags": [
        "v*"
      ]
    },
    "workflow_run": {
      "workflows": [
        "Native build",
        "test",
        "and package"
      ],
      "types": [
        "requested",
        "completed"
      ]
    },
    "workflow_dispatch": {
      "inputs": {
        "source_run_id": {
          "description": "First-party native push run to publish or recover",
          "type": "string",
          "required": true
        }
      }
    }
  },
  "concurrency": {
    "group": "native-publisher-${{ github.event.workflow_run.head_sha || inputs.source_run_id || github.sha }}",
    "cancel-in-progress": false
  },
  "jobs": {
    "publish": {
      "runs-on": "ubuntu-24.04",
      "if": "github.event_name == 'push' || github.event_name == 'workflow_dispatch' || (github.event.workflow_run.event == 'push' &&\n github.event.workflow_run.head_repository.full_name == 'tlolabs/ativ')",
      "timeout-minutes": 180
    }
  }
}
```

### tlolabs/ativ — Recipe 7 host qualification (no publication)

removed_from_default_branch; [source](https://github.com/tlolabs/ativ/blob/ba87f58fcd42a7d99d46ab8a5f4d3b96569eb61d/.github/workflows/recipe7-qualification.yml).

```json
{
  "file": ".github/workflows/recipe7-qualification.yml",
  "on": {
    "workflow_dispatch": {
      "inputs": {
        "platform": {
          "description": "Native platform to validate (normal pushes and tags always build all)",
          "type": "choice",
          "options": [
            "all",
            "macos",
            "windows",
            "linux"
          ],
          "default": "all"
        },
        "sign_macos": {
          "description": "Sign and notarize macOS validation artifacts (does not publish a release)",
          "type": "boolean",
          "default": false
        }
      }
    },
    "push": {
      "branches": [
        "codex/recipe7-host-qualification"
      ]
    }
  },
  "concurrency": {
    "group": "recipe7-${{ github.ref }}",
    "cancel-in-progress": "${{ !startsWith(github.ref, 'refs/tags/') }}"
  },
  "jobs": {
    "engine": {
      "name": "Shared Rust engine",
      "runs-on": "ubuntu-24.04"
    },
    "macos": {
      "name": "macOS ${{ matrix.arch }}",
      "runs-on": "${{ matrix.runner }}",
      "strategy": {
        "fail-fast": false,
        "matrix": {
          "include": [
            {
              "arch": "arm64",
              "core_arch": "arm64",
              "runner": "macos-15"
            },
            {
              "arch": "x86_64",
              "core_arch": "x86_64",
              "runner": "macos-15-intel"
            }
          ]
        }
      },
      "needs": "engine",
      "if": "github.event_name != 'workflow_dispatch' || inputs.platform == 'all' || inputs.platform == 'macos'"
    },
    "windows": {
      "name": "Windows ${{ matrix.arch }}",
      "runs-on": "${{ matrix.runner }}",
      "strategy": {
        "fail-fast": false,
        "matrix": {
          "include": [
            {
              "arch": "x64",
              "core_arch": "x86_64",
              "runner": "windows-2025"
            },
            {
              "arch": "ARM64",
              "core_arch": "arm64",
              "runner": "windows-11-arm"
            }
          ]
        }
      },
      "needs": "engine",
      "if": "github.event_name != 'workflow_dispatch' || inputs.platform == 'all' || inputs.platform == 'windows'"
    },
    "linux": {
      "name": "Linux ${{ matrix.arch }}",
      "runs-on": "${{ matrix.runner }}",
      "strategy": {
        "fail-fast": false,
        "matrix": {
          "include": [
            {
              "arch": "x86_64",
              "core_arch": "x86_64",
              "runner": "ubuntu-24.04"
            },
            {
              "arch": "aarch64",
              "core_arch": "arm64",
              "runner": "ubuntu-24.04-arm"
            }
          ]
        }
      },
      "needs": "engine",
      "if": "github.event_name != 'workflow_dispatch' || inputs.platform == 'all' || inputs.platform == 'linux'"
    }
  }
}
```

### tlolabs/ativ — Report CI/CD failures

current_yaml; [source](https://github.com/tlolabs/ativ/blob/main/.github/workflows/report-ci-failures.yml).

```json
{
  "file": ".github/workflows/report-ci-failures.yml",
  "on": {
    "workflow_run": {
      "workflows": [
        "Native build, test, and package",
        "Sign Windows portable packages with Azure",
        "Verify locally notarized Mac qualification packages",
        "Attest and verify native Linux AppImages",
        "CodeQL",
        "Retry failed verification workflows",
        "Publish independently verified native platforms"
      ],
      "types": [
        "completed"
      ]
    },
    "schedule": [
      {
        "cron": "17 6 * * *"
      }
    ],
    "workflow_dispatch": null
  },
  "concurrency": null,
  "jobs": {
    "update-report": {
      "runs-on": "ubuntu-24.04"
    }
  }
}
```

### tlolabs/ativ — Retry failed verification workflows

current_yaml; [source](https://github.com/tlolabs/ativ/blob/main/.github/workflows/retry-failed-verification.yml).

```json
{
  "file": ".github/workflows/retry-failed-verification.yml",
  "on": {
    "workflow_run": {
      "workflows": [
        "Native build, test, and package"
      ],
      "types": [
        "completed"
      ]
    }
  },
  "concurrency": null,
  "jobs": {
    "retry-once": {
      "runs-on": "ubuntu-24.04",
      "if": "github.event.workflow_run.conclusion == 'failure' && github.event.workflow_run.run_attempt < 2 && github.event.workflow_run.head_repository.full_name == github.repository"
    }
  }
}
```

### tlolabs/ativ — Sign Windows portable packages with Azure

current_yaml; [source](https://github.com/tlolabs/ativ/blob/main/.github/workflows/sign-windows.yml).

```json
{
  "file": ".github/workflows/sign-windows.yml",
  "on": {
    "workflow_dispatch": {
      "inputs": {
        "native_run": {
          "description": "Successful native Windows qualification run for this exact commit",
          "required": true,
          "type": "string"
        }
      }
    }
  },
  "concurrency": null,
  "jobs": {
    "sign": {
      "runs-on": "windows-2025"
    },
    "verify-native": {
      "name": "Verify signed Windows ${{ matrix.target }}",
      "runs-on": "${{ matrix.runner }}",
      "strategy": {
        "fail-fast": false,
        "matrix": {
          "include": [
            {
              "runner": "windows-2025",
              "target": "windows-x86_64",
              "label": "x64"
            },
            {
              "runner": "windows-11-arm",
              "target": "windows-arm64",
              "label": "arm64"
            }
          ]
        }
      },
      "needs": "sign"
    }
  }
}
```

### tlolabs/ativ — Verify locally notarized Mac qualification packages

current_yaml; [source](https://github.com/tlolabs/ativ/blob/main/.github/workflows/verify-macos.yml).

```json
{
  "file": ".github/workflows/verify-macos.yml",
  "on": {
    "workflow_dispatch": {
      "inputs": {
        "native_run": {
          "description": "Exact same-commit native Mac qualification run",
          "type": "string",
          "required": true
        },
        "qualification_tag": {
          "description": "Same-commit draft qualification release tag",
          "type": "string",
          "required": true
        },
        "qualification_release_id": {
          "description": "Immutable GitHub ID of the same-commit qualification draft",
          "type": "string",
          "required": true
        },
        "arm64_sha256": {
          "description": "Final stapled arm64 ZIP SHA-256",
          "type": "string",
          "required": true
        },
        "intel_sha256": {
          "description": "Final stapled Intel ZIP SHA-256",
          "type": "string",
          "required": true
        },
        "qualify_core_candidate": {
          "description": "Unpublished candidate verification only",
          "type": "boolean",
          "default": false
        }
      }
    }
  },
  "concurrency": null,
  "jobs": {
    "verify-native": {
      "name": "Verify signed macOS ${{ matrix.target }}",
      "runs-on": "${{ matrix.runner }}",
      "strategy": {
        "fail-fast": false,
        "matrix": {
          "include": [
            {
              "runner": "macos-15",
              "target": "macos-arm64",
              "label": "arm64",
              "artifact_label": "arm64"
            },
            {
              "runner": "macos-15-intel",
              "target": "macos-x86_64",
              "label": "intel",
              "artifact_label": "x86_64"
            }
          ]
        }
      }
    }
  }
}
```
