# Lint Burn-down (folder-by-folder)

This document collects findings from folder-scoped Codacy, Pylance, and Sonar analyses and provides a prioritized burn-down checklist to prepare the project for 1.0. Runs performed: folder-scoped Codacy analyses for `src/`, `tests/`, `scripts/`, `config/`, `docs/`, `audit_data/`, `external/`, `htmlcov/`, `logs/`, `orchestration_packs/`, `outputs/`, and subfolders under `src/elspeth/` (adapters, core, plugins, retrieval, tools). Pylance syntax checks and Sonar file analysis were triggered for targeted files (for example `pii_shield.py`).

## Summary (high level)

- Total folders scanned (folder-scoped Codacy): src, tests, scripts, config, docs, audit_data, external, htmlcov, logs, orchestration_packs, outputs, and `src/elspeth/*` (adapters, core, plugins, retrieval, tools).
- Most folders returned no Codacy/Pylint findings in the quick folder scans.
- Notable findings (priority):
  - `src/elspeth/core/validation/__init__.py` — Undefined names listed in `__all__` (Pylint errors).
  - `tests/test_retrieval_embedding.py` — Redefining built-in `input` (warning).
  - `tests/test_retrieval_providers.py` — Redefining built-in `filter` (warning).

> Note: SonarQube analysis was triggered for `src/elspeth/plugins/nodes/transforms/llm/middleware/pii_shield.py`. No Pylance syntax errors were found for that file. Detailed Sonar findings require exporting or using the SonarCloud API/Scanner to collect issues programmatically.

## Findings (prioritized)

### Critical / HIGH

- src/elspeth/core/validation/__init__.py
  - Problem: Undefined variable name(s) in `__all__`.
    - Examples reported:
      - `SuiteValidationReport` (reported at line ~9)
      - `validate_settings` (reported at line ~11)
      - `validate_suite` (reported at line ~12)
  - Why: Pylint treats names in `__all__` as public exports; listing names that don't exist (or aren't imported into the module scope) is an error and fails static checks.
  - Suggested fix: Ensure the exported names actually exist in the module scope. Either:
    - Import the symbols into `__init__.py` from their implementing modules (preferred):
      - e.g. `from .validation import SuiteValidationReport, validate_settings, validate_suite`
    - Or correct/remove names in `__all__` to match the real exported API.
  - Estimated time: 0.25–1.0h (small code edit + quick test run)

### Medium

- tests/test_retrieval_embedding.py
  - Problem: Redefining built-in `input` (warning at line ~29).
  - Why: Test code shadows Python built-in `input`, which can confuse linters and readers.
  - Suggested fix: Rename the local variable or fixture to avoid shadowing (e.g., `user_input`, `mock_input`). Update test accordingly.
  - Estimated time: 0.15–0.5h

- tests/test_retrieval_providers.py
  - Problem: Redefining built-in `filter` (warning at line ~158).
  - Suggested fix: Rename local variable or function to avoid shadowing (e.g., `filter_fn`, `predicate`).
  - Estimated time: 0.15–0.5h

### Low / Informational

- Many folders returned no Pylint results in the quick Codacy folder scans. This is good, but deeper checks (ruff/pyright/pytype, Semgrep with custom rules, SonarCloud) may reveal additional maintainability or security issues.

## Recommendations & next steps (folder-by-folder process)

1. Workflow to continue (repeat per-folder):
   - Run folder-scoped Codacy analyze (we already ran many folders). Collect the JSON output for that folder.
   - Run Pylance full-type/import check for the folder to catch unresolved imports and type problems.
   - Run Sonar scanner or query SonarCloud API for issues in that folder and export results.
   - Aggregate findings into this file and mark items as resolved when fixed.

2. Immediate fixes to apply (middleware/core/tests first):
   - Fix `src/elspeth/core/validation/__init__.py` `__all__` entries (HIGH priority).
   - Fix the two test files that shadow built-ins (MEDIUM priority).

3. CI and automation suggestions to gate 1.0:
   - Add pre-commit hooks (ruff, isort, black) to auto-fix style issues.
   - Add CI steps (ordered to avoid Codacy freezes):
     - Run `ruff` and `isort` (fast). Fail fast on style errors.
     - Run `pyright` / `pytype` (type checks) per-folder or on changed files.
     - Run folder-scoped Codacy analysis in parallel (or sequential per-folder) and fail if new critical issues are introduced.
     - Run unit tests (`pytest -q`) with coverage enforcement.
     - Run SonarCloud analysis as a separate job (or on merge) and block on new critical security issues.

4. SonarCloud/Codacy specifics:
   - Codacy: avoid single-run over the entire repo; run per-folder or only changed folders in CI to prevent timeouts/freezes.
   - SonarCloud: configure the project to report issues in the UI and use API to export issues for automated aggregation.

## Next actions I can take (pick one)

1. Apply the three quick fixes now (edit and run tests):
   - Fix `__all__` in `src/elspeth/core/validation/__init__.py`.
   - Rename shadowed built-ins in the two tests.
   - Re-run folder-scoped Codacy and Pylance checks for verification.

2. Continue scanning other folders with deeper checks (Pylance type checks, Semgrep with rules, SonarCloud exports) and aggregate results into this file.

3. Produce a per-folder markdown checklist with one line per issue and an estimated time column (I can generate this automatically from the collected Codacy output if desired).

---

If you'd like me to apply the quick fixes now, say "fix now" and I will update the files, run the tests, and re-run Codacy for the affected folders. If you'd prefer I continue scanning other folders first, tell me which folder to do next.
