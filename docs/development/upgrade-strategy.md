# Upgrade & Dependency Strategy

## Dependency Inventory

- Canonical requirements live in `pyproject.toml:13-55`, splitting runtime vs optional extras (Azure ML telemetry, advanced statistics, Excel sinks).
- Development tooling (`pytest`, `ruff`, `pytype`) is pinned for deterministic CI (`pyproject.toml:26-33`).
- Bootstrap installs the editable package plus dev extras, then executes the whole pytest suite (`scripts/bootstrap.sh:16`), ensuring compatibility before promoting new builds.

## Upgrade Workflow

1. **Assess advisories** – Monitor vendor feeds for `azure-storage-blob`, `azure-identity`, `openai`, `requests`, and `jinja2`. Record findings in `docs/` or issue tracker.
2. **Bump versions** – Update `pyproject.toml` entries, keeping major upgrades isolated per commit for traceability.
3. **Recreate virtualenv** – Run `make bootstrap` to rebuild `.venv/` and run tests using the refreshed dependency graph (`Makefile:4`).
4. **Smoke test suites** – Execute representative suites such as the sample suite (`Makefile:9`) to validate runtime compatibility with signed sinks and repositories (`config/settings.yaml:34-75`).
5. **Review transitive licenses** – For regulated environments, capture `pip freeze` output and attach to accreditation artifacts.
6. **Update documentation** – Reflect changes in `docs/architecture/dependency-analysis.md` and note any new configuration requirements (e.g., additional env vars introduced by upstream SDKs).

## Regression Gates

- **Automated tests** – The security-focused tests (middleware, sanitisation, signing) should be part of the gating checklist (`tests/test_llm_middleware.py`, `tests/test_sanitize_utils.py`, `tests/test_outputs_signed.py`).
- **Coverage drift** – Verify `coverage.xml` still emits from pytest (`pyproject.toml:65`) and that Sonar/coverage gates remain satisfied.
- **Breaking API detection** – Watch for changes in Azure SDK request semantics; the wrapper classes (`src/elspeth/plugins/llms/azure_openai.py:25`, `src/elspeth/plugins/outputs/blob.py:64`) intentionally isolate version-specific logic, so unit tests should flag incompatibilities early.

## Rollback Plan

- Maintain tagged releases of `pyproject.toml` and lockfiles (if generated) within version control.
- When a regression lands, revert the dependency bump commit and re-run `make bootstrap`; the editable install model allows immediate rollback without repackaging.
