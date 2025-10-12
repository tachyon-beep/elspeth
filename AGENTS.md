# Repository Guidelines

## Project Structure & Module Organization
The Python package lives in `src/elspeth/`, with `core/` covering experiment orchestration, `plugins/` hosting metrics and output sinks, and `cli.py` providing the entrypoint. Support material sits in `config/sample_suite/` for runnable demos, `notes/` for decisions and planning, and `scripts/` for bootstrap helpers. Shared tests reside in `tests/`, mirroring module layouts for easy discovery.

## Build, Test, and Development Commands
Run `make bootstrap` (or `scripts/bootstrap.sh`) to create `.venv/`, install extras, and execute the sanity pytest pass. Activate the environment via `source .venv/bin/activate`, then use `pip install -e .[dev]` when dependencies shift. The sample orchestration flow is validated with `make sample-suite`, which exercises the CSV datasource plus mock LLM path. Use `python -m pytest -m "not slow"` for rapid feedback, and append `--maxfail=1 --disable-warnings` during triage.

When introducing changes that touch analytics, reporting, or suite flows, run the consolidated reporting command to regenerate artefacts and verify logs:

```bash
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/sample_suite_reports \
  --head 0
```

Review the resulting artefacts (validation results, analytics/visual reports, Excel workbook) and capture checksum/signature outputs if they form part of accreditation evidence.

## Coding Style & Naming Conventions
Code targets Python 3.12 with 4-space indentation, `typing` annotations, and descriptive module names (`metrics_*.py`, `suite_runner.py`). Use `ruff` for formatting and linting, and run `pytype` for static analysis; the Makefile target `lint` installs pinned versions. Prefer snake_case for functions and variables, PascalCase for classes, and keep docstrings concise but informative, especially around plugin hooks.

## Testing Guidelines
Pytest is the standard; new tests belong under `tests/` using `test_*.py` naming. Mirror package structure (`tests/core/test_runner.py`) to align fixtures with production modules. Aim to maintain the current ~83% coverage; add parametrized cases for concurrency, backoff, and plugin registration edge cases. When adding integration features, supply a CLI exercise under `tests/integration/` and document expected artifacts in assertions.
<!-- UPDATE 2025-10-12: Include analytics/reporting regression tests when touching SuiteReportGenerator, analytics sinks, or the visual analytics sink; see `tests/test_reporting.py`, `tests/test_outputs_visual.py`, and `tests/test_integration_visual_suite.py`. -->

## Commit & Pull Request Guidelines
Commits follow the existing imperative style (`Add`, `Refine`, `Fix`) and concentrate on one logical change. Include concise body context when touching orchestration flows or configuration formats. Pull requests should link tracking issues or roadmap phases, summarize impact, call out migrations/config changes, and list verification commands (pytest, sample suite, or custom scripts). Attach screenshots or artifact snippets when outputs change.

## Security & Configuration Tips
Secrets and API keys must live outside the repo; use environment variables consumed by the LLM adapters. Treat `config/sample_suite/` as non-sensitive reference material and fork configurations for real deployments. Review `notes/plugin-architecture.md` before introducing new plugins to ensure registration settings and audit logging remain compliant.
<!-- UPDATE 2025-10-12: When modifying concurrency, retry, early-stop logic, or analytics sinks (JSON/visual), update the corresponding architecture docs and regenerate signed/visual artefacts if output formats change. -->

## Update History
- 2025-10-12 – Update 2025-10-12: Added reporting artefact regeneration guidance and reiterated analytics regression checks for concurrency/early-stop changes.
