# Remediation Plan

## Quick Wins (days)

- Enforce endpoint allowlisting in HttpOpenAIClient constructor — COMPLETED
  - Implemented: validates `api_base` via `validate_http_api_endpoint()` in `__init__` (defense in depth)
  - Ref: `src/elspeth/plugins/nodes/transforms/llm/openai_http.py`

- Mandate lockfile installs everywhere — PARTIAL
  - Implemented: README updated to require `piptools sync` (developer flow)
  - Next: ensure Makefile/docs consistently reference lockfile sync in all paths
  - Ref: `README.md`, `.github/workflows/ci.yml`

- Add Bandit to CI — COMPLETED (baseline mode)
  - Implemented: Added Bandit with SARIF upload; currently not failing builds (|| true)
  - Next: flip to fail on HIGH after baseline review
  - Ref: `.github/workflows/ci.yml`

- Clarify repository sink dry_run semantics
  - Change: Require explicit `dry_run` in production configs or warn when `True` and not in explicit smoke test
  - Effort: S; Impact: Medium; Ref: `src/elspeth/plugins/nodes/sinks/repository.py`

## Deep Work (weeks)

- Elevate coverage to ≥85% overall; ≥80% in hotspots — IN PROGRESS (83% overall)
  - Completed: Added tests for enums/types; schema inference/model factory; path safety; LLM registry conflicts/unapproved endpoints; blob datasource; visual/excel/csv/zip sinks (skip/sanitize/containment); Azure middleware (env + Content Safety) including retry‑exhausted and mask/abort; reporting helpers/viz skip.
  - Next: Expand analytics/visual sinks HTML/table branches; additional middleware branches; comprehensive reporting generate_all_reports paths.
  - Ref: `tests/core/`, `tests/plugins/`, `tests/middleware/`, `tests/tools/`

- Gradual mypy strictness uplift
  - Change: Enable `disallow_untyped_defs` for core packages; use targeted `# type: ignore` where justified
  - Effort: M; Impact: Medium; Ref: `pyproject.toml`

- Local secret scanning & log retention guidance
  - Change: Add pre-commit gitleaks; document JSONL log retention/cleanup (`make clean-logs`)
  - Effort: S; Impact: Low-Medium

## Verification

- Tests/coverage
  - `python -m pytest -m "not slow" --cov=elspeth --cov-branch`
  - Gate to ≥85% overall; review `coverage.xml`

- Static analysis
  - `ruff check src tests`
  - `mypy src`
  - `bandit -r src -f sarif -o bandit.sarif`

- Supply chain & SBOM
  - `pip-audit -r requirements.lock --require-hashes`
  - `python -m cyclonedx_py requirements requirements.lock --pyproject pyproject.toml --output-file sbom.json --output-format JSON --output-reproducible`

## Conditions for Acceptance (Summary)

1) Add endpoint validation in HttpOpenAIClient constructor.
2) Enforce locked installs in all documented workflows.
3) Raise coverage to ≥85% overall (≥80% in hotspots).
4) Add Bandit (and optionally Semgrep) to CI; fail on HIGH.
