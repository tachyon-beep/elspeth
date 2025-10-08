# Architectural Assessment Report
Generated: 2025-10-07 00:43:02Z

## Executive Summary
- New plugin-driven core replaces the monolithic runner with clear orchestration layers, artifact routing, and extensive validation (`dmp/core/orchestrator.py:17`, `dmp/core/artifact_pipeline.py:24`).
- Legacy statistical tooling and outputs have been modularised into opt-in experiment plugins and sinks, broadening Azure/offline support while reducing direct SDK coupling.
- Primary risks center on Azure-first middleware defaults, partial plugin instantiation in single-run mode, and the learning curve introduced by the richer configuration surface.

## Current Architecture Overview
### Project Structure
- `dmp/` – primary package exposing CLI, config loader, orchestrator, and plugin registries.
  - `cli.py` – CLI entrypoint handling settings validation, suite execution, and sink cloning (`dmp/cli.py:27`).
  - `config.py` – materialises typed `Settings`, merges prompt packs, and instantiates plugins via the registry (`dmp/config.py:17`).
  - `core/` – shared orchestration, prompt, validation, controls, artifact, and security layers.
    - `orchestrator.py`, `experiments/`, `llm/`, `controls/`, `prompts/`, `validation.py`, `artifact_pipeline.py`, `security/`.
  - `datasources/` – Azure Blob loader utilities (`dmp/datasources/blob_store.py:18`).
  - `plugins/` – concrete datasource/LLM/output/experiment implementations with registries wired in module `__init__` files.
- `config/` – YAML suite/settings samples and blob profile definitions.
- `notes/` – design documents for phased refactor roadmap.
- `tests/` – 28 pytest modules covering orchestration, plugins, security, and validation paths.
- `scripts/bootstrap.sh`, `Makefile` – developer automation.

### Key Components
- **Experiment orchestration**: `ExperimentOrchestrator` composes datasource, LLM client, sinks, and runner while injecting rate limiting, cost tracking, retry, and middleware hooks (`dmp/core/orchestrator.py:35`).
- **Experiment runner**: `ExperimentRunner` renders prompts, applies row/aggregation plugins, manages retries, checkpoints, concurrency, and artifact fan-out (`dmp/core/experiments/runner.py:25`).
- **Suite runner**: Builds per-experiment runners, clones sink definitions, wires middleware lifecycle callbacks, and performs baseline comparisons (`dmp/core/experiments/suite_runner.py:18`).
- **Configuration models & validation**: JSON schema-backed validation for suite configs and settings ensures plugin definitions and prompt packs are well formed before execution (`dmp/core/validation.py:14`, `dmp/core/experiments/config.py:14`).
- **Prompt system**: Jinja-backed prompt compilation/validation with legacy-format auto-conversion (`dmp/core/prompts/engine.py:50`).
- **Plugin registries**: Datasource/LLM/output factories with schema validation and artifact declarations, enabling dynamic instantiation from config (`dmp/core/registry.py:37`, `dmp/core/experiments/plugin_registry.py:18`, `dmp/core/llm/registry.py:17`).
- **Controls**: Rate limiters (fixed window/adaptive) and cost trackers surfaced via registries and integrated with runner middleware (`dmp/core/controls/rate_limit.py:15`, `dmp/core/controls/registry.py:32`).
- **Artifact pipeline**: Resolves sink dependencies, security levels, and execution order for chained outputs (`dmp/core/artifact_pipeline.py:24`).
- **Security**: Security level normalisation and signing helpers for classified artifacts (`dmp/core/security/__init__.py:6`, `dmp/plugins/outputs/signed.py:20`).
- **LLM middleware**: Audit logging and prompt shield middleware plus Azure ML telemetry bridge with suite lifecycle callbacks (`dmp/plugins/llms/middleware.py:15`, `dmp/plugins/llms/middleware_azure.py:55`).
- **Metrics plugins**: Row/aggregation/baseline plugins covering extraction, stats, power analysis, agreement, and Bayesian comparisons with optional SciPy/Pingouin integrations (`dmp/plugins/experiments/metrics.py:144`, `dmp/plugins/experiments/metrics.py:258`, `dmp/plugins/experiments/metrics.py:403`).
- **Outputs**: CSV, blob, signed bundle, zip, Excel, GitHub, Azure DevOps sinks with dry-run safety and artifact manifest support (`dmp/plugins/outputs/csv_file.py:16`, `dmp/plugins/outputs/repository.py:41`).

### Technology Stack
- Core dependencies: `openai>=1.12.0`, `azure-identity`, `azure-storage-blob`, `pandas`, `pyyaml`, `jinja2`, `jsonschema`, `requests` (`pyproject.toml`).
- Optional extras: SciPy, Pingouin, Statsmodels, AzureML Core, OpenPyXL for extended metrics and sinks.
- Python 3.12 baseline via `pyproject.toml`.
- Test tooling: `pytest`, `pytest-cov`, `pytest-mock` provided via `dev` extra.

## Legacy Architecture Overview
### Project Structure
- `old/main.py` – monolithic CLI script orchestrating configuration, prompt loading, rate limiting, telemetry, and suite execution directly.
- `old/experiment_runner.py` – legacy suite loader with config validation, baseline selection, execution ordering, and Azure ML logging helpers.
- `old/experiment_stats.py` – statistical analysis toolkit bundling frequentist, bootstrap, and Bayesian routines plus chart generation.

### Key Components
- **Monolithic CLI**: Direct Azure OpenAI client usage, global state, and imperative orchestration with tight coupling to other `dmp` subpackages (`old/main.py:32`).
- **Suite loader**: Manual filesystem walker validating JSON configs via jsonschema and estimating cost/time (`old/experiment_runner.py:22`, `old/experiment_runner.py:115`).
- **Telemetry & archiving**: Inline Azure ML run detection, DevOps archiver hooks, and audit logging embedded in CLI (`old/main.py:86`, `old/main.py:75`).
- **Statistical analysis**: `StatsAnalyzer` performing t-tests, bootstrap Bayesian analysis, agreement metrics, and plotting with optional sklearn/pingouin (`old/experiment_stats.py:1`, `old/experiment_stats.py:116`).
- **Concurrency & retry**: Thread pool orchestration for case-study processing with manual backoff wrappers referencing `dmp.llm_client` helpers (`old/main.py:206`).

### Technology Stack
- Direct dependencies surfaced in code: `openai`, `azureml`, `jsonschema`, `pandas`, `numpy`, `scipy`, `pingouin`, `statsmodels`, `sklearn`, `matplotlib`, `requests`, `yaml`, `zipfile` (`old/main.py:1`, `old/experiment_stats.py:1`).
- Heavy reliance on local `dmp.*` modules (rate_limit, prompts, heuristics, monitoring) without an explicit packaging boundary.

## Comparative Analysis

### Feature Comparison Matrix
| Feature/Component | Old Version | New Version | Status | Notes |
|------------------|-------------|-------------|---------|-------|
| CLI orchestration | Monolithic script with global state (`old/main.py:32`) | Modular CLI invoking orchestrator & suite runner (`dmp/cli.py:91`) | Refactored | Clear separation of validation, single-run, and suite paths. |
| Configuration loading | JSON/YAML parsing with inline validation (`old/experiment_runner.py:41`) | Typed settings with registry-backed plugin instantiation (`dmp/config.py:17`) | Modified | Adds prompt packs, suite defaults, middleware, concurrency options. |
| Prompt management | File-based prompts and manual formatting (`old/main.py:144`) | Jinja prompt engine with validation & defaults (`dmp/core/prompts/engine.py:50`) | Improved | Supports template metadata, aliasing, prompt packs. |
| LLM integration | Direct AzureOpenAI calls wrapped by legacy client (`old/main.py:200`) | Protocol-based clients + middleware + cost/rate controls (`dmp/plugins/llms/azure_openai.py:17`, `dmp/core/experiments/runner.py:316`) | Improved | Middleware pipeline enables audit, shield, Azure telemetry. |
| Retry/backoff & checkpointing | Manual wrappers via `dmp.llm_client` and `ExperimentCheckpoint` (`old/main.py:135`) | Configurable retry/backoff and checkpoint JSONL in runner (`dmp/core/experiments/runner.py:316`, `dmp/core/experiments/runner.py:51`) | Added | Checkpoint resume and middleware-aware retries. |
| Concurrency control | ThreadPoolExecutor usage embedded in CLI (`old/main.py:206`) | Configurable parallelism gated by rate limiter utilisation (`dmp/core/experiments/runner.py:239`) | Modified | Adds backlog thresholds, utilisation pauses, middleware safety. |
| Baseline comparison | Diff logic in suite manager with Azure ML logging (`old/experiment_runner.py:311`) | Baseline plugins plus suite runner comparisons (`dmp/core/experiments/suite_runner.py:236`) | Refactored | Plugins enable multiple comparison strategies. |
| Metrics/statistics | StatsAnalyzer class with plots & Bayesian tests (`old/experiment_stats.py:116`) | Plugin suite covering extraction, stats, recommendation, bayes, power (`dmp/plugins/experiments/metrics.py:144`, `dmp/plugins/experiments/metrics.py:403`) | Modified | Functionality modularised; plotting removed. |
| Output handling | Hand-coded Excel/ZIP/DevOps routines (`old/main.py:52`) | Artifact pipeline + sinks (CSV, blob, bundles, signed, git) (`dmp/core/artifact_pipeline.py:24`, `dmp/plugins/outputs/repository.py:41`) | Improved | Adds dependency-aware execution & security levels. |
| Security & compliance | Minimal; manual signing elsewhere | Security level propagation & signing sink (`dmp/core/security/__init__.py:6`, `dmp/plugins/outputs/signed.py:20`) | Added | Enables clearance-aware artifact routing. |
| Telemetry | Azure ML run logging embedded in CLI (`old/main.py:86`) | Middleware with suite lifecycle callbacks (`dmp/plugins/llms/middleware_azure.py:55`) | Refactored | Centralised telemetry, configurable failure handling. |
| Rate limiting & cost | Global rate limiter & cost tracker objects (`old/main.py:112`, `old/main.py:141`) | Pluggable rate limiter/cost tracker registry + adaptive limiter (`dmp/core/controls/registry.py:32`) | Improved | Supports adaptive token-aware throttling. |
| Testing infrastructure | Not included | 28 pytest files covering core paths (`tests/test_orchestrator.py`, etc.) | Added | Automated regression coverage (~83% per notes). |

### Removed Functionality
⚠️ **Features present in old but missing in new:**
- Heuristic early-stop hook (`dmp.heuristics.should_stop_early`) no longer wired into the orchestrator; experiments always exhaust full row sets.
- Legacy plotting/report generation from `StatsAnalyzer` (Matplotlib charts, Excel consolidation) is absent; new sinks focus on structured artifacts.

### New Functionality
✅ **Features added in new version:**
- Artifact dependency graph enabling chained sinks, security level enforcement, and manifest generation (`dmp/core/artifact_pipeline.py:24`).
- Prompt packs with shared defaults and middleware bundles for suites (`dmp/config.py:58`).
- LLM middleware registry supporting audit logging, prompt shielding, and Azure ML telemetry lifecycles (`dmp/core/llm/registry.py:17`, `dmp/plugins/llms/middleware.py:15`).
- Concurrency configuration with utilisation-aware pausing and restartable checkpoints (`dmp/core/experiments/runner.py:239`, `dmp/core/experiments/runner.py:55`).

### Modified Components
 **Significant changes to existing features:**
- Experiment suite loading now returns dataclass-backed configs with schema validation while maintaining baseline auto-selection (`dmp/core/experiments/config.py:62`).
- Metrics/statistics migrated into configurable plugins with richer schema validation and optional dependencies (`dmp/plugins/experiments/metrics.py:37`).
- Azure integration shifts from CLI logic to middleware and plugin options, reducing hardcoded credentials (`dmp/plugins/llms/azure_openai.py:45`).

## Architectural Improvements
- Modular plugin registries decouple configuration from implementation, enabling environment-specific overrides without code edits.
- Middleware pipeline standardises telemetry, safety, and cost tracking around LLM calls, easing cross-cutting concerns.
- Artifact pipeline enforces dependency ordering and security clearances, supporting repository/bundle sinks safely.
- Extensive validation tooling prevents misconfigured suites before execution, reducing runtime failures.
- Automated testing suite covers orchestration, plugins, and validation paths, improving maintainability.

## Potential Concerns
- Single-run orchestrator constructs placeholder plugin lists but never instantiates configs, so row/aggregation/baseline plugins configured in settings are ignored outside suites (`dmp/core/orchestrator.py:55`).
- Azure environment middleware defaults to `enable_run_logging=True` and `on_error="abort"`, causing hard failures on non-Azure hosts without explicit override (`dmp/plugins/llms/middleware_azure.py:60`).
- Numerous sink plugins perform real network/file operations; dry-run defaults mitigate risk but misconfiguration could still trigger remote writes (`dmp/plugins/outputs/repository.py:41`).
- Retry logic re-raises the last exception without context if all attempts fail, offering limited diagnostics for operational triage (`dmp/core/experiments/runner.py:326`).

## Migration Considerations
- Configuration files must adopt new schema (prompt packs, plugin `plugin/options` blocks, middleware lists); direct reuse of legacy JSON will fail validation.
- Prompt templates should be reviewed for Jinja compatibility—legacy `{field}` formatting auto-converts, but complex formatting may require adjustments.
- Old heuristic hooks (`should_stop_early`, `HealthMonitor`) need replacement via plugins or middleware before removing legacy code paths.
- Data lineage/Excel exports formerly produced by CLI need to be mapped onto new sinks (e.g., `excel`, `local_bundle`) or custom plugins.

## Recommendations
1. Instantiate plugin definitions for single-run orchestrations so metrics and baseline logic behave consistently across modes.
2. Default Azure middleware to `on_error="skip"` or disable run logging in non-Azure profiles to avoid unexpected runtime aborts.
3. Document migration playbook covering prompt pack structure, middleware options, and artifact pipeline to ease onboarding.
4. Reintroduce optional early-stop or sampling heuristics via row plugins or middleware for cost-sensitive suites.
5. Provide sample configurations demonstrating repository sinks in live mode with credential management best practices.

## Appendices
### A. Dependency Comparison
- **Legacy**: `openai`, `azureml`, `jsonschema`, `pandas`, `numpy`, `scipy`, `pingouin`, `statsmodels`, `sklearn`, `matplotlib`, `requests`, `yaml`, `zipfile` (`old/main.py:1`, `old/experiment_stats.py:1`).
- **Current**: `openai`, `azure-identity`, `azure-storage-blob`, `pandas`, `pyyaml`, `jinja2`, `jsonschema`, `requests`; optional SciPy/Pingouin/Statsmodels/AzureML via extras (`pyproject.toml`).

### B. Code Metrics Comparison
- Current codebase: 53 Python modules, ~7,503 LOC under `dmp/`.
- Legacy snapshot: 3 Python files, ~3,565 LOC under `old/`.
- Tests: 28 pytest modules covering new architecture (see `tests/`).

### C. File-by-File Mapping
- `old/main.py` → `dmp/cli.py`, `dmp/core/orchestrator.py`, `dmp/core/experiments/suite_runner.py`, `dmp/plugins/llms/*`, `dmp/plugins/outputs/*`.
- `old/experiment_runner.py` → `dmp/core/experiments/config.py`, `dmp/core/experiments/suite_runner.py`, `dmp/core/validation.py`.
- `old/experiment_stats.py` → `dmp/plugins/experiments/metrics.py`.
