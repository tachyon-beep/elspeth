# Agent Orientation

This document helps future agents and contributors reorient quickly after a memory compact.

## Project Snapshot
- **Repository**: Domain Model Platform (new plugin-driven experiment runner)
- **Status**: Core refactor through Phase 4 complete (retry/backoff, checkpointing, baseline comparisons).
- **Python**: 3.12.x (ensure local runtime matches `pyproject.toml`).

## Virtual Environment
- Preferred environment lives at `.venv/` in the repo root.
- Activate with `source .venv/bin/activate`.
- Includes dev extras (`pytest`, `pytest-cov`, etc.); reinstall via `pip install -e .[dev]` if needed.

## Key Entry Points
- `dmp/cli.py` – main CLI driving orchestrator and suite operations (`--disable-metrics`, `--live-outputs`).
- `dmp/core/experiments/runner.py` – row execution with retries/checkpoints.
- `dmp/core/experiments/suite_runner.py` – baseline-first suite orchestration.
- `dmp/core/prompts/` – templating engine (Jinja-backed) with validation/cloning helpers.
- `dmp/plugins/experiments/metrics.py` – default metrics plugins (`score_extractor`, `score_stats`, `score_recommendation`, `score_delta`).
- `dmp/plugins/outputs/` – sinks for CSV, blob, local bundles, GitHub/Azure DevOps repos, and signed artifacts.
- `config/sample_suite/` – runnable sample suite using local CSV datasource + mock LLM.
- `dmp/core/llm/` – middleware registry (audit logging, prompt shield) and concurrency helpers.

## Tooling & Testing
- `make bootstrap` (or `scripts/bootstrap.sh`) prepares `.venv`, installs deps, and runs pytest.
- `make sample-suite` executes the mock-LLM sample suite with CSV outputs.
- Run `source .venv/bin/activate && python -m pytest` for the full suite with coverage (61 tests, ~83% coverage as of latest run).
- Concurrency is configurable via `concurrency` blocks in settings/prompt packs; ExperimentRunner spawns threads subject to rate limiter utilization thresholds.

## Active Roadmap
- **Phase 5**: Metrics/statistical experiment plugins (row + aggregation).
- **Phase 6**: Output & archival sinks (Excel/zip/DevOps) and metadata capture.
- **Phase 7**: Tooling/documentation/bootstrap scripts.

Reference `notes/plugin-architecture.md` for detailed planning and historical decisions.
