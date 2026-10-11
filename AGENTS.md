# Repository development and CI/CD policy

ATIV uses a nonblocking development and CI/CD model. Direct commits and pushes to `main` are allowed. No mandatory pull request, review, approval, DCO check, signed commit, branch protection, ruleset, or required status check may be introduced. Voluntary `git commit -s` DCO trailers remain the convention.

Keep unit, integration, functional, regression, accessibility, security, dependency, and six-platform build checks automated. Report failures and track unresolved work in a consolidated GitHub Issue; a diagnostic failure must not stop unrelated development or another verified platform.

Each release artifact must pass its own native build, package integrity, target identity, runtime dependency, launch, and functional checks before publication. Successful targets may publish independently. Never publish a failed or unverified artifact. Code signing and notarization are optional for direct downloads until configured. Signed update feeds retain their existing cryptographic signature and upgrade verification requirements; unsigned downloads must never be added to an authenticated update feed. Do not weaken runtime acquisition or update-signature checks.

Allow bounded automatic retries after relevant changes without creating a development gate. Preserve tests and future signing workflows. Do not reintroduce blocking gates without explicit owner authorization.
