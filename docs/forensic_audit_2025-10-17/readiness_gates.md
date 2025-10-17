| Gate | Status | Evidence |
| ---- | ------ | -------- |
| tests_pass | **PASS** | Full regression suite green (`test_results.txt:1-12`, 698 passed / 2 skipped). |
| coverage_threshold (target ≥85% lines) | **PASS** | Observed 85.0% line / 71.7% branch coverage (`coverage.xml:2`). |
| secrets_scan_clean | **PASS** | GitHub Actions `ci.yml` secrets-scan job uploads `gitleaks-report` artefact (`.github/workflows/ci.yml:11-32`). |
| sbom_vulns | **PASS** | CycloneDX SBOM and pip-audit outputs checked in (`sbom.json`, `requirements.lock`, `requirements-dev.lock`). |
| reproducible_build | **PASS** | Hash-locked requirements and bootstrap script ensure deterministic sync (`scripts/bootstrap.sh:13-24`, `requirements-dev.lock:1-512`). |
| container_hygiene | **N/A** | Repository ships no container manifests (no Dockerfile under project root); gate not applicable. |
| observability_minimums | **PASS** | Retry/cost tracking and warning logs emitted on exhaustion provide baseline telemetry (`src/elspeth/core/experiments/runner.py:661-682`). |
