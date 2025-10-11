# Configuration & Secrets Management

## Configuration Entry Points
- **Profile settings** – Primary runtime definitions live in `settings.yaml`, declaring datasource/LLM/sink plugins, prompt packs, and suite defaults (`config/settings.yaml:3`, `config/settings.yaml:76`).
- **Prompt packs** – Reusable prompt bundles include row/aggregate plugins and middleware defaults, enabling centralised policy updates across suites (`config/settings.yaml:4`, `src/elspeth/config.py:78`).
- **Suite overrides** – Individual experiments provide JSON configs with per-experiment sinks, middleware, rate limiters, and early-stop definitions (`config/sample_suite/slow_rate_limit_demo/config.json:13`, `src/elspeth/core/experiments/config.py:82`).
<!-- UPDATE 2025-10-12: Profiles also expose `concurrency`, `early_stop`, and `checkpoint` sections that are normalised via `normalize_early_stop_definitions` to align with plugin schemas (`src/elspeth/config.py:66`, `src/elspeth/core/experiments/plugin_registry.py:298`). -->

## Secret Resolution
- **Environment variables** – LLM clients, repository sinks, and signing bundles resolve credentials via `_env` keys or well-known variables, keeping secrets out of config artefacts (`src/elspeth/plugins/llms/azure_openai.py:66`, `src/elspeth/plugins/outputs/repository.py:149`, `src/elspeth/plugins/outputs/signed.py:107`).
- **Azure identity** – Blob datasources fall back to `DefaultAzureCredential` when SAS tokens are absent, supporting managed identity deployments without patching configuration (`src/elspeth/datasources/blob_store.py:125`, `src/elspeth/datasources/blob_store.py:157`).
- **Sample artefacts** – Repository includes illustrative SAS tokens; accreditation deployments must replace these with tenant-specific secure stores and treat checked-in values as non-production (`config/blob_store.yaml:4`).

## Validation & Fail-fast Behaviour
- **Schema enforcement** – Loader passes raw configuration through schema validators before instantiating plugins, catching typoed plugin names or missing options early (`src/elspeth/core/validation.py:271`, `src/elspeth/core/registry.py:98`, `src/elspeth/core/controls/registry.py:36`).
- **Early-stop normalisation** – User-friendly structures are converted into canonical plugin definitions, reducing ambiguity around threshold plugins (`src/elspeth/core/experiments/plugin_registry.py:298`, `src/elspeth/core/config.py:69`).
- **Suite audits** – `validate_suite` collects experiment metadata, checks for duplicate names/baselines, and surfaces aggregate risk estimations before orchestration begins (`src/elspeth/core/validation.py:407`, `src/elspeth/core/experiments/suite_runner.py:74`).

## Runtime Configuration Controls
- **Dry-run toggles** – Repository sinks respect `dry_run`, allowing accreditation teams to inspect payloads without mutating upstream repositories (`config/settings.yaml:64`, `src/elspeth/plugins/outputs/repository.py:70`).
- **On-error policies** – Datasources and sinks accept `"abort"` or `"skip"` to tailor resilience vs. strictness; combine with telemetry to ensure skipped components are investigated (`src/elspeth/plugins/datasources/csv_local.py:30`, `src/elspeth/plugins/outputs/blob.py:64`, `src/elspeth/plugins/outputs/excel.py:52`).
- **Security levels** – Datasources, sinks, and suite defaults can specify classifications that propagate through the artifact pipeline, enabling downstream segregation of outputs (`src/elspeth/plugins/datasources/csv_blob.py:25`, `src/elspeth/core/experiments/suite_runner.py:116`, `src/elspeth/core/artifact_pipeline.py:192`).
<!-- UPDATE 2025-10-12: `concurrency.enabled`, `max_workers`, and `utilization_pause` settings guard thread pools, while `checkpoint.path`/`field` control resumable runs; ensure these paths point to hardened storage (`src/elspeth/core/experiments/runner.py:365`, `src/elspeth/core/experiments/runner.py:280`). -->

## Recommendations
- Store operational secrets (API keys, SAS tokens, signing keys) in managed secret stores and inject them at runtime through environment variables or workload identities.
- Maintain a signed baseline of accreditation-approved configuration bundles; use the signed artifact sink to capture canonical run manifests (`src/elspeth/plugins/outputs/signed.py:48`).
- Extend validation to enforce minimum middleware stacks (e.g., prompt shield + content safety) for high-assurance suites to avoid configuration drift.

## Added 2025-10-12 – Suite Management & Export Pathing
- **Suite exports** – CLI flags `--export-suite-config`, `--create-experiment-template`, and `--reports-dir` reuse hydrated settings to write artefacts under operator-defined paths; treat exported JSON/YAML and analytics reports as configuration evidence requiring signing or checksum capture (`src/elspeth/cli.py:161`, `src/elspeth/cli.py:201`, `src/elspeth/tools/reporting.py:33`).
- **Prompt pack inheritance** – Prompt packs can override concurrency, middleware, sinks, and early-stop defaults; ensure packs shipped for production omit development-only plugins (`src/elspeth/config.py:92`, `src/elspeth/core/experiments/suite_runner.py:55`).
- **Plugin whitelisting** – Registries validate plugin names against in-memory maps. Harden builds by avoiding dynamic imports at runtime and auditing prompt packs/suite defaults for unexpected plugin references (`src/elspeth/core/registry.py:69`, `src/elspeth/core/experiments/plugin_registry.py:52`).

## Update History
- 2025-10-12 – Captured concurrency/checkpoint configuration impacts, suite export considerations, and plugin inheritance safeguards.
