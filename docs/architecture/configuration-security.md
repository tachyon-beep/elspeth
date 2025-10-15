# Configuration Security & Validation

This document summarises how ELSPETH validates configuration inputs, hydrates suites, and protects
secret material during orchestration.

## Update 2025-10-12: Validation Pipeline Overview

- **Settings loader** – `load_settings` combines YAML profiles, prompt packs, and command-line
  overrides while instantiating configured plugins (`src/elspeth/config.py:52-210`).
- **Schema enforcement** – `validate_settings` and supporting helpers enforce structural rules,
  coercing security/determinism levels and catching unknown plugin options before execution
  (`src/elspeth/core/validation.py:254-512`, `src/elspeth/core/config_schema.py:17-198`).
- **Suite validation** – `validate_suite` inspects exported suites for missing experiments, sinks,
  or inconsistent defaults prior to runtime (`src/elspeth/core/validation.py:430-512`).

<!-- UPDATE 2025-10-12: Validation pipeline cross-referenced with docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Ingress Classification Flow). -->

## Update 2025-10-12: Secret & Credential Handling

- **Environment resolution** – Datasource and sink plugins read credentials from environment
  variables at runtime (`src/elspeth/plugins/nodes/sources/blob.py:36`,
  `src/elspeth/plugins/nodes/sinks/blob.py:180`, `src/elspeth/plugins/nodes/sinks/signed.py:101`).
  Keep `.env` files outside version control and rotate secrets between accreditation runs.
- **Managed identity** – Azure blobs favour `DefaultAzureCredential`; SAS tokens remain an escape
  hatch and should have tightly scoped permissions (`src/elspeth/adapters/blob_store.py:42`).
- **Repository access** – GitHub/Azure DevOps sinks read tokens on demand and support dry-run
  uploads; store PATs in secret managers and inject via CI rather than committing them
  (`src/elspeth/plugins/nodes/sinks/repository.py:140-219`).

## Update 2025-10-12: Prompt Packs & Suite Defaults

- Prompt packs can define prompts, middleware, sinks, and plugin lists that merge with suite
  defaults and per-experiment overrides (`src/elspeth/config.py:102-188`).
- `ConfigMerger` guarantees deterministic resolution order (defaults ← prompt pack ← experiment)
  before normalising plugin lists (`src/elspeth/core/experiments/suite_runner.py:37-116`).
- Suite defaults should capture shared middleware (audit, prompt shield, content safety) so
  experiments inherit mandatory safeguards.

## Update 2025-10-12: Concurrency, Retry, and Early Stop Configuration

- `concurrency` sections enable threaded execution with `max_workers`, `backlog_threshold`, and
  rate-limiter integration (`src/elspeth/core/experiments/runner.py:137-524`).
- `retry` settings accept `max_attempts`, `initial_delay`, and `backoff_multiplier`; populated
  metadata flows into sink payloads and analytics artefacts (`src/elspeth/core/experiments/runner.py:547-676`).
- Early-stop plugins are defined either under `early_stop_plugins` (normalised via
  `normalize_early_stop_definitions`) or through explicit plugin entries (`src/elspeth/core/experiments/plugin_registry.py:282-454`).

## Update 2025-10-12: Middleware & Control Configuration

- `llm_middlewares` lists ordered middleware definitions drawn from
  `src/elspeth/plugins/nodes/transforms/llm/middleware*.py`; include `prompt_shield`,
  `azure_content_safety`, `health_monitor`, and `azure_environment` for production suites.
- Rate limiters (`rate_limiter`) and cost trackers (`cost_tracker`) are instantiated via control
  registries with schema validation (`src/elspeth/core/controls/registry.py:36-188`).
- Middleware lifecycle hooks (`on_suite_loaded`, `on_retry_exhausted`) require consistent naming;
  ensure custom middleware implements the same interface to integrate with telemetry pipelines.

## Update 2025-10-12: Sink Sanitisation & on_error Policies

- CSV/Excel sinks offer `sanitize_formulas` and `sanitize_guard` options to neutralise spreadsheet
  exploits (`src/elspeth/plugins/nodes/sinks/csv_file.py:18-123`,
  `src/elspeth/plugins/nodes/sinks/excel.py:33-182`).
- `on_error` policies (`abort`/`skip`) exist across datasources and sinks; use `skip` during rehearsal
  runs to collect partial evidence while logging failures, then switch to `abort` for production
  accreditation runs (`src/elspeth/plugins/nodes/sources/csv_local.py:18-118`,
  `src/elspeth/plugins/nodes/sinks/blob.py:160-228`).
- Signed bundle sinks enforce key presence and embed manifests with cost/retry summaries for
  tamper evidence (`src/elspeth/plugins/nodes/sinks/signed.py:32-121`).

## Update 2025-10-12: Suite Export & Governance

- `--export-suite-config` produces JSON exports consolidating experiment definitions for review and
  signing (`src/elspeth/cli.py:390-458`).
- `--create-experiment-template` scaffolds new experiments using existing prompt packs, keeping
  suite configuration immutable until changes are reviewed (`src/elspeth/cli.py:80-105`).
- `SuiteReportGenerator` emits `analysis_config.json` documenting plugin usage and timestamps for
  accreditation archives (`src/elspeth/tools/reporting.py:26-199`).

## Update History

- 2025-10-12 – Introduced configuration security overview covering validation pipeline, secret
  handling, concurrency/retry/early-stop settings, and suite export governance for accreditation.

