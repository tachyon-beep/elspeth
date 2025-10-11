# Initial Assessment (2024-05)
<!-- UPDATE 2025-10-12: ELSPETH core package, plugin architecture, and sample suite are now fully implemented under `src/elspeth/`. The legacy `old/` scripts remain archival; current orchestration flows live in `src/elspeth/core/experiments/runner.py`, `src/elspeth/cli.py`, and associated plugins. -->

## Repository Snapshot
- Current tree only exposes `old/` with three Python entry points: `main.py`, `experiment_runner.py`, and `experiment_stats.py`.
- `main.py` is now a thin façade over an external `elspeth` package (expects `elspeth.cli`, `elspeth.runner`, etc.); those modules are **not** present in this repo, so executing `python old/main.py` will immediately fail with `ModuleNotFoundError`.
- Legacy helpers (`experiment_runner.py`, `experiment_stats.py`) still implement substantial logic but import shared utilities from the missing `elspeth` package as well.
<!-- UPDATE 2025-10-12: The modern stack lives in `src/elspeth/` with equivalent functionality; see `docs/architecture/architecture-overview.md` for the current system design. -->

## Runtime Expectations
- Core dependencies from direct imports:
  - Data stack: `pandas`, `numpy`, `scipy`, `matplotlib`, `pyyaml`, `jsonschema`.
  - Azure/OpenAI: `openai` (Azure client), `azureml-core` (optional telemetry), `requests`.
  - Statistical extras referenced optionally: `scikit-learn`, `statsmodels`, `pingouin`, `pymc3`, `krippendorff`.
- The code assumes access to Azure OpenAI credentials (`api_key`, `api_version`, `azure_endpoint`, deployment name) via CLI arguments/environment.
- File layout expectations: experiments directory with subfolders containing `config.json`, `system_prompt.md`, `user_prompt.md`; shared `prompts/` folder; configuration YAMLs. None of these assets are currently committed.

## Gaps to Address for Local Execution
1. Provide or recreate the `elspeth` package (or refactor the legacy scripts to run without it). Without these modules the runtime cannot start.
2. Assemble configuration + prompt assets under the expected paths so that experiment discovery does not error out.
3. Curate a `requirements.txt` (Python 3.12 compatible) covering mandatory libraries above; confirm availability of heavier scientific packages or decide which to mark optional.
4. Document/automate Azure credential loading for local runs (env vars, `.env`, or config file) before we can hit Azure OpenAI.
5. Clarify data inputs (CSV schema consumed by `process_data`) because nothing in `old/` defines it anymore; likely lives in the missing package.

## Open Questions / Next Actions
- Do we have an archived copy of the `elspeth` package or should we rebuild equivalent functionality within this repo?
- Are we expected to run purely locally (mocking Azure services) or will the VM have network + Azure credentials available during development?
- Need confirmation on experiment assets location before scripting bootstrap.

## Additional Context (User 2024-05-??)
- `elspeth` package and experiment assets are not yet available; the user will supply representative snippets later for testing.
- Final solution must read the experiment input data directly from Azure Blob Storage (not local CSV). Bootstrap stack needs to account for blob access and auth.

## Blob Loader Module (WIP)
- Added `src/elspeth/datasources/blob_store.py` with `BlobConfig` + `BlobDataLoader` to fetch CSV inputs using `azure-storage-blob` and `azure-identity` (DefaultAzureCredential).
- Configuration stored in `config/blob_store.yaml`; supports multiple profiles with the provided Azure ML datastore URI and raw blob URI.
- Usage example:
  ```python
  from elspeth.datasources import load_blob_config, BlobDataLoader

  cfg = load_blob_config("config/blob_store.yaml", profile="default")
  loader = BlobDataLoader(cfg)
  df = loader.load_csv()
  ```
- Dependencies to add to requirements: `azure-storage-blob`, `azure-identity`, `pyyaml`, `pandas` (if CSV parsing needed).

## Project Infrastructure
- Introduced `pyproject.toml` using PEP 621 metadata; pins Python >=3.12 and runtime deps (`azure-identity`, `azure-storage-blob`, `pandas`, `pyyaml`). Dev extras include `pytest` + `pytest-mock`.
- Added pytest suite under `tests/` with coverage for config parsing and blob loader client wiring (stubs azure SDK to avoid network calls).
- Capture remaining setup gap: local environment still needs dependencies installed before running `pytest` or connecting to Azure.
- Local `.venv` created; package installed in editable mode (`.venv/bin/pip install -e .[dev]`).
- `pytest` suite (`.venv/bin/pytest`) passes with blob loader tests.
- Added `load_blob_csv` convenience helper in `src/elspeth/datasources/blob_store.py` wired to config + loader.
- Extended pytest coverage (`tests/test_blob_store.py`) to validate helper wiring and kwargs propagation.
- `.venv/bin/pytest` now reports 4 passing tests.
- Blob loader supports SAS tokens and split account/container/blob configuration; updated config to point at `elspethsyntheticdata`/`elspethdatasource` with provided SAS (expires 2025-10-03).
- Tests extended to cover SAS credential usage and component-based config; suite now reports 6 passing tests.
- Verified live blob download via `.venv/bin/python -m elspeth...` (SyntheticData.csv); data frame preview captured in console.
- Implemented `src/elspeth/cli.py` providing a bootstrap CLI that loads blob data via `load_blob_csv`, prints a preview, and can persist to CSV; includes logging controls for future expansion.
- Added tests in `tests/test_cli.py` covering parser defaults, run-path side effects, and CLI invocation; total pytest count now 9.

## Architecture Principles (2024-05-User)
- Treat each integration point as a plugin surface area: LLM client, data sources, output sinks, etc. should be swappable with minimal friction.
- Output channel (currently blob) must become a pluggable interface capable of targeting alternatives such as GitHub, flat files, or Oracle DB via simple plugin swaps.
- Added `pytest-cov` to dev tooling (pyproject + venv) and enabled `--cov` reporting via pytest.ini settings; current coverage 87% overall.
- `config/settings.yaml` now uses the CSV sink (`outputs/latest_results.csv`) and parameterizes Azure OpenAI credentials via env vars (`ELSPETH_AZURE_OPENAI_KEY`, `ELSPETH_AZURE_OPENAI_ENDPOINT`).
- End-to-end smoke: `ELSPETH_AZURE_OPENAI_KEY=dummy ELSPETH_AZURE_OPENAI_ENDPOINT=https://example.openai.azure.com .venv/bin/python ...` running the orchestrator with a dummy LLM produced 19-row CSV at `outputs/latest_results.csv`.
- Added `.env.example` for Azure OpenAI (`ELSPETH_AZURE_OPENAI_KEY`, `ELSPETH_AZURE_OPENAI_ENDPOINT`, `ELSPETH_AZURE_OPENAI_DEPLOYMENT`) and ignored `.env` in git.
- Attempted live Azure OpenAI call using `.env` credentials; received `DeploymentNotFound` (HTTP 404), indicating the configured deployment name (`ELSPETH_AZURE_OPENAI_DEPLOYMENT` currently `gpt-4o`) may not exist on the target endpoint.
- Live LLM test still fails with `DeploymentNotFound`; need to confirm the deployment name via `az openai deployment list` or portal and update `ELSPETH_AZURE_OPENAI_DEPLOYMENT` accordingly.
- With updated config (`deployment_env` + API version 2024-12-01-preview) and `.env` values (deployment `gpt-4o`), live Azure OpenAI call succeeded; orchestrator produced 19 responses and CSV sink captured outputs.

## Remaining Work (2024-05)
- Port legacy experiment logic: prompt packs, baseline comparisons, templates, and checkpointing from `old/` into new plugin architecture.
- Implement concrete experiment metrics/statistical plugins based on legacy `experiment_stats.py` (score parsing, aggregations, significance tests).
- Enhance cost/rate plugin configuration with provider presets; consider surface in suite defaults.
- Broaden sink support (multi-experiment reporting, DevOps/DB output) and document suite CLI usage.
- Provide bootstrap tooling (setup script, sample suite) and finalize documentation for plugin configuration and suite mode.
<!-- UPDATE 2025-10-12: Phases 5–7 delivered metrics plugins, analytics reporting, Azure telemetry middleware, and documentation/CLI tooling. Remaining roadmap items live in `notes/phase7-docs.md` and subsequent phase notes. -->

## Update History
- 2025-10-12 – Annotated legacy assessment with current implementation status and pointers to the rebuilt ELSPETH package.
