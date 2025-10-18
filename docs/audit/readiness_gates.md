# Readiness Gates

| Gate | Status | Target | Observed | Evidence |
| --- | --- | --- | --- | --- |
| tests_pass | PASS | All tests pass | CI green | `.github/workflows/ci.yml` pytest step |
| coverage_threshold | PASS | ≥85% line (mission‑critical) | 86.9% line; 72.1% branch | `coverage.xml` root attributes |
| secrets_scan_clean | PASS | No hard‑coded secrets | Clean | gitleaks in CI (`.github/workflows/ci.yml`) + manual scan |
| sbom_vulns | PASS | No CRITICAL vulns in runtime deps | Clean | pip‑audit in CI; `sbom.json` generated |
| reproducible_build | PASS | Locked, deterministic | Lockfiles + `piptools sync` | `.github/workflows/ci.yml` + `scripts/bootstrap.sh` |
| container_hygiene | N/A | — | — | No Dockerfile/IaC present |
| observability_minimums | PASS | Structured logs/metrics | JSONL per run | `src/elspeth/core/utils/logging.py` |

Notes
- Coverage and SBOM reports are produced by CI and stored as artefacts.
- Evidence references are repository‑relative paths for traceability.

