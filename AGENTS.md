# Repository Guidelines

## Project Structure & Module Organization
Source code lives in `src/elspeth/`, with `core/` handling orchestration, `plugins/` providing metrics and output sinks, and `cli.py` as the entrypoint. Plugins follow the Phase 2 layout under `src/elspeth/plugins/nodes/{sources,transforms,sinks}/` and `src/elspeth/plugins/experiments/`; update imports to match. Sample configs are in `config/sample_suite/`, scripts in `scripts/`, docs in `notes/`, and tests mirror the package shape under `tests/`.

## Build, Test, and Development Commands
- Always activate the project virtualenv (`source .venv/bin/activate`) before running `make`, CLI entrypoints, or scripts; all tooling assumes execution inside `.venv/`.
- `make bootstrap` (or `scripts/bootstrap.sh`): create `.venv/`, install extras, run the sanity pytest pass.
- `source .venv/bin/activate` then `pip install -e .[dev,analytics-visual]`: refresh dependencies.
- `make sample-suite`: run the CSV datasource + mock LLM demo.
- ```bash
  python -m elspeth.cli \
    --settings config/sample_suite/settings.yaml \
    --suite-root config/sample_suite \
    --reports-dir outputs/sample_suite_reports \
    --head 0
  ``` regenerates reporting artefacts for analytics/review.

## Coding Style & Naming Conventions
Target Python 3.12, 4-space indentation, and type hints across public APIs. Use snake_case for functions and variables, PascalCase for classes, and descriptive module names (`metrics_*.py`, `suite_runner.py`). Format and lint with `ruff`; run `pytype` via `make lint` before submitting.

## Testing Guidelines
Pytest drives the suite, aiming to sustain ~83% coverage. Place new cases in `tests/` mirroring the source layout (e.g., `tests/core/test_runner.py`). Prefer parametrized tests for concurrency, backoff, and plugin registration edges. Use `python -m pytest -m "not slow" --maxfail=1 --disable-warnings` for rapid iterations, and add analytics/reporting regressions when touching suite reporting or visual sinks (`tests/test_reporting.py`, `tests/test_outputs_visual.py`, `tests/test_integration_visual_suite.py`).
- Always activate the project virtualenv (`source .venv/bin/activate`) before running tests; `pytest` and its plugins are only installed there.

## Commit & Pull Request Guidelines
Write imperative commits (`Add`, `Refine`, `Fix`) focused on a single logical change, and include context when altering orchestration or configs. Pull requests should link roadmap issues, summarize impact, list verification commands (pytest, sample suite, reporting run), and attach key artefacts or screenshots when outputs differ.

## Security & Configuration Tips
Keep secrets outside the repo and feed adapters via environment variables. Treat `config/sample_suite/` as reference-only; create project-specific forks for deployments. When adjusting concurrency, retry, early-stop logic, or analytics sinks, update relevant docs in `notes/` and regenerate signed/visual artefacts for accreditation records.
