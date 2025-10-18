# Remediation Plan

## Quick Wins (days)

Status: IMPLEMENTED and validated (pytest green; coverage updated).

- Enforce locked installs everywhere (S, High impact)
  - Mandate `piptools sync` + `--require-hashes` for all environments; update README/runbooks and Makefile snippets.
  - Evidence/patched in findings: `README.md` note to require lockfile installs.

- Add HTTP retries/backoff to Azure Content Safety (S, Medium) — DONE
  - Three attempts with exponential backoff + jitter for idempotent screening.
  - File: `src/elspeth/plugins/nodes/transforms/llm/middleware/azure_content_safety.py`.

- Add HTTPAdapter with Retry to repository sinks (S, Medium) — DONE
  - Mount `HTTPAdapter(Retry(...))` on the sink session for 429/5xx.
  - File: `src/elspeth/plugins/nodes/sinks/repository.py`.

- Serialise checkpoint appends (S, Medium) — DONE
  - Guard `_append_checkpoint` with a lightweight `threading.Lock` to avoid line interleaving in parallel mode.
  - File: `src/elspeth/core/experiments/runner.py`.

- Serialise JSONL log writes (S, Low/Medium) — DONE
  - Add a per‑logger `threading.Lock` in `_write_log_entry` to ensure one‑line atomicity across threads.
  - File: `src/elspeth/core/utils/logging.py`.

- Harden endpoint overrides policy (S, Medium) — DONE (now disallowed in STRICT; allowed with warning in STANDARD; allowed in DEVELOPMENT)
  - Ignore `ELSPETH_APPROVED_ENDPOINTS` unless in DEVELOPMENT mode; prevents policy drift in prod.
  - File: `src/elspeth/core/security/approved_endpoints.py`.

## Deep Work (weeks)

- Error taxonomy and targeted handling (M)
  - Replace broad `except Exception` in critical paths with specific exceptions (e.g., `requests.RequestException`, `json.JSONDecodeError`); tag `error_type` and enrich telemetry.

- Observability enrichment (M)
  - Add counters for retry attempts, exhausted retries, and sink/client failure rates; consider an optional OTLP exporter.

- Policy hardening for production (M)
  - Default STRICT in production configs; add a config lint step that fails on missing security_level/allowed_base in STRICT; document runbooks.

## Verification & Evidence Capture

- Tests: `python -m pytest -m "not slow" --cov=elspeth --cov-branch`; all tests passed locally (864 passed, 1 skipped); `coverage.xml` regenerated.
- Static analysis: `ruff check`, `mypy src`, `bandit -q -r src --severity-level high --confidence-level high` (upload SARIF).
- Supply chain: `pip-audit -r requirements.lock --require-hashes`; attach JSON.
- SBOM: `cyclonedx_py ... --output-reproducible`; attach `sbom.json`.

## Acceptance Conditions (to move to ACCEPT)

1) Lockfile‑based installs enforced and documented.
2) HTTP retries/backoff added to Azure Content Safety and repository sinks.
3) Checkpoint and JSONL writes serialised.
4) Endpoint env overrides disabled outside DEVELOPMENT.

## Way Forward (90‑Day Plan)

- Weeks 0–1: Implement quick wins above; run CI; archive artefacts (coverage, SBOM, audit) in release.
- Weeks 2–4: Address deep‑work items for error taxonomy and telemetry; raise branch coverage in identified modules.
- Weeks 5–8: Enforce STRICT defaults in prod; add config linting and policy documentation.
