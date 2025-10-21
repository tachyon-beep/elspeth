CI/CD and Security Workflows

This repository uses a set of pinned, least‑privilege GitHub Actions workflows to validate code quality, enforce security gates, and publish signed artifacts. The overview below summarizes what runs, when, and what gates apply.

Workflows

- `ci.yml` — Core validation (push/PR)
  - Linting (`ruff`), typing (`mypy`), unit tests (pytest), and security scans (Semgrep, Bandit, pip‑audit), plus SBOM generation.
  - Uploads SARIF where relevant for visibility in the Security tab.

- `codeql.yml` — CodeQL analysis (push/PR, scheduled)
  - Runs `github/codeql-action/{init,autobuild,analyze}` pinned by commit SHA.
  - Current pin: `16140ae1a102900babc80a33c44059580f687047` (v4.30.9).

- `codeql-summary.yml` — Post‑analysis CodeQL summary (workflow_run)
  - Triggers after CodeQL completes; fetches alerts via `gh api` with retry + fallback.
  - Minimal permissions: `security-events: read` + `contents: read` (private repos).

- `publish.yml` — Container build, attest, sign, verify (push tags/main)
  - Builds the image, generates SBOM, signs with Cosign, and performs signature verification.
  - Grype container scan runs with a failing gate on high‑severity issues.

- `dependency-review.yml` — PR dependency diffs
  - Surfaces risky dependency changes on pull requests.

- `dependabot-auto-merge.yml` — Safe auto‑merge of security updates
  - Approves and merges Dependabot security PRs only when all CI gates pass and policy conditions are met.

- `repin-base.yml` — Base image repinning
  - Periodically resolves base image digests and updates references to immutable `@sha256:` pins.

- `auto-bump-grype.yml`, `auto-bump-semgrep.yml` — Scanner version tracking
  - Open PRs to keep scanner versions aligned with latest releases while preserving SHA pins for actions/images.

- `scorecard.yml` — OpenSSF Scorecard
  - Runs Scorecard, uploads SARIF, and summarizes notable findings.

Security Gates (must pass)

- Tests: pytest suite with target coverage (~83% in CI).
- Lint & types: `ruff`, `mypy` (and `pytype` via `make lint` locally).
- Static analysis: Semgrep + Bandit; CodeQL (separate workflow) reports to Security tab.
- Dependencies: `pip-audit` on Python requirements.
- SBOM: CycloneDX generation (JSON), uploaded and/or attached to images.
- Container: Grype scan blocks on HIGH (or higher) severity findings.
- Secrets: Gitleaks run as part of security scans.
- Dependency review: Blocks risky changes on PRs where enabled.

Pinning and Permissions

- All third‑party actions are SHA‑pinned. CodeQL actions are currently pinned to:
  - `github/codeql-action/init@16140ae1a102900babc80a33c44059580f687047`
  - `github/codeql-action/autobuild@16140ae1a102900babc80a33c44059580f687047`
  - `github/codeql-action/analyze@16140ae1a102900babc80a33c44059580f687047`
  - `github/codeql-action/upload-sarif@16140ae1a102900babc80a33c44059580f687047`
- Workflows declare minimal `permissions:`; write scopes are granted only to jobs that create PRs, tags, or upload security events.

How to bump CodeQL pins

1) Check the latest `v4.*` tag at `github.com/github/codeql-action/tags`.
2) Copy the tag’s commit SHA and replace existing pins in:
   - `codeql.yml`
   - `ci.yml` (for `upload-sarif` steps)
   - `publish.yml`, `scorecard.yml` (if they use `upload-sarif`)
3) Keep the inline comment with the semantic version (e.g., `# v4.30.9`).

Notes

- Some summaries (CodeQL, Scorecard) are generated into the job summary for quick triage.
- Container and SBOM steps are optimized for reproducibility and traceability (immutable digests, provenance, attestation).
