| Gate | Status | Evidence |
| ---- | ------ | -------- |
| tests_pass | **FAIL** | Six regression failures in the default pytest run (`test_results.txt:1-146`, details at `test_results.txt:71-112`). |
| coverage_threshold (target ≥85% lines) | **PASS** | Observed 89.9% line / 67.4% branch coverage from latest report (`coverage.xml:2`). |
| secrets_scan_clean | **N/A** | No automated secret-scanning artefacts captured during this audit; manual spot checks only—run gitleaks/trufflehog in CI. |
| sbom_vulns | **FAIL** | No SBOM or vulnerability scan outputs; dependency list remains unpinned (`pyproject.toml:12-34`). |
| reproducible_build | **FAIL** | Lower-bound dependency specs plus bootstrap upgrades prevent deterministic environments (`pyproject.toml:12-34`, `scripts/bootstrap.sh:16-17`). |
| container_hygiene | **N/A** | Repository ships no container manifests (no Dockerfile under project root); gate not applicable. |
| observability_minimums | **PASS** | Retry/cost tracking and warning logs emitted on exhaustion provide baseline telemetry (`src/elspeth/core/experiments/runner.py:661-682`). |
