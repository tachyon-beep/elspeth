# Plugin Architecture Sketch

## Core Service Layers
- **Ingestion**: abstract `DataSource` interface with `load()` -> DataFrame; implementations include AzureBlobSource (current), LocalCSVSource, AzureSQLSource.
- **LLM Client**: `LLMClient` protocol exposing `generate(prompt, config) -> LLMResult`; plugins for Azure OpenAI (default), OpenAI API, local llama.cpp, mock.
- **Experiment Orchestrator**: orchestrates data -> prompts -> scoring; depends on `PromptFormatter`, `LLMClient`, `RateLimiter`, `CostTracker`.
- **Output Sink**: `ResultSink` interface with `write(results, metadata)`; implementations for Azure Blob, GitHub PR, text file, Oracle DB. Config drives which sink(s) activate.
- **Monitoring/Logging**: plugin hooks for audit logging, health checks.

## Module Layout Proposal
- `src/elspeth/core/` high-level orchestration (experiment runner, stats)
- `src/elspeth/plugins/`
  - `datasources/` (blob, csv, ado)
  - `llms/` (azure_openai, openai, mock)
  - `outputs/` (blob, filesystem, github, oracle)
  - `monitoring/`
- `src/elspeth/config/` load config and resolve plugins via entrypoints or registry
- `src/elspeth/cli.py` orchestrates using config-driven plugin selection

## Configuration Concepts
- Central `config/settings.yaml` with sections:
  ```yaml
  data_source:
    plugin: azure_blob
    options: {...}
  llm:
    plugin: azure_openai
    options: {...}
  outputs:
    - plugin: azure_blob
      options: {...}
    - plugin: github
      options: {...}
  ```
- Provide env var overrides for secrets; support `.env` or Azure Key Vault integration.

## Next Refactor Steps
1. Define plugin interfaces as `Protocol` / abstract base classes.
2. Implement minimal default plugins (blob datasource, Azure OpenAI LLM, blob output).
3. Refactor `old/main.py` into new orchestrator consuming these interfaces.
4. Add plugin registry/loader with config parsing.

## Refactor Roadmap
1. **Baseline Extraction**
   - Move legacy experiment runner/stat analyzer into `src/elspeth/core` modules with minimal changes; stub external `elspeth` dependencies.
   - Replace direct imports in `old/` scripts with new `elspeth.core` modules, using the CLI as primary entry point.
2. **Interface Definition**
   - Introduce `DataSource`, `LLMClientProtocol`, `ResultSink` protocols and register default implementations.
   - Create a plugin registry (simple mapping keyed by name) to instantiate plugins from YAML config.
3. **Configuration Layer**
   - Add `config/settings.yaml` with plugin selections; support environment overrides.
   - Implement loader that merges default + profile-specific settings.
4. **Orchestrator Refactor**
   - Refactor experiment execution to depend solely on interfaces (no direct Azure/OpenAI imports inside core logic).
   - Call `datasource.load()` for inputs; pass results to orchestrator; write outputs via configured sinks.
5. **Testing & Bootstrap**
   - Add unit tests for plugin selection and orchestrator using mock implementations.
   - Update CLI to drive the orchestrator and allow selecting profiles/plugins via flags.
6. **Cleanup**
   - Deprecate `old/` entry points once new architecture validated; maintain notes for remaining gaps.

## Progress 2024-05
- Created `src/elspeth/core/interfaces.py` defining `DataSource`, `LLMClientProtocol`, `ResultSink`, and `ExperimentContext` dataclass.
- Added blob datasource plugin (`src/elspeth/plugins/datasources/blob.py`) wrapping existing loader plus registry entry (`src/elspeth/core/registry.py`).
- Tests (`tests/test_registry.py`) ensure registry resolves the blob datasource via config options; pytest suite now at 10 passing tests.
- Extended plugin registry to cover LLM (`azure_openai`) and result sinks (placeholder `BlobResultSink`); interfaces updated to capture structured prompts.
- Registry tests now validate error handling and custom plugin registration (total pytest count 12).
- Added orchestrator (`src/elspeth/core/orchestrator.py`) connecting datasource, LLM, and sinks with formatting prompts.
- Introduced config loader (`src/elspeth/config.py`) + default `config/settings.yaml`; CLI now loads settings, runs orchestrator, and writes preview.
- Tests updated (`tests/test_orchestrator.py`, `tests/test_config.py`, CLI tests) with suite at 14 passes.

## Upcoming Refactor Tasks
1. **Port Core Utilities**
   - Extract essential logic from `old/` (process_data, prompt formatting stubs) into `src/elspeth/core` modules compatible with new interfaces.
   - Build placeholder implementations where external `elspeth.*` packages were expected.
2. **LLM Plugin Implementation**
   - Flesh out `AzureOpenAIClient` with actual SDK usage (config-driven credentials, rate limiter hook).
   - Add unit tests using mocked Azure client to ensure prompt flow.
3. **Result Sink Implementation**
   - Implement `BlobResultSink` to serialize results to blob storage (reuse existing loader for upload); create alternative filesystem sink for testing.
4. **Orchestrator Integration**
   - Replace simple prompt formatting with structured experiment runner logic (criteria loops, cost tracking) adapted from `old/main.py`.
   - Introduce plugin injection for prompt formatters and safety checks.
5. **Legacy Compatibility**
   - Update CLI/entry to allow running the new orchestrator while leaving `old/` for reference.
   - Document migration status and deprecate old modules once parity achieved.
- Introduced `prepare_prompt_context` helper to control row-to-prompt mapping and wired it into the orchestrator/config (supports field filtering + aliases).
- Tests expanded (`tests/test_processing.py`, updated orchestrator/CLI/config tests); suite now 15 passing with coverage ~87%.
- Implemented functional Azure OpenAI plugin (`src/elspeth/plugins/llms/azure_openai.py`) with config/env credential resolution and chat.completions invocation; new tests in `tests/test_llm_azure.py` verify prompt wiring and error handling.
- Updated dependencies to include `openai`.
- Added CSV result sink plugin (`src/elspeth/plugins/outputs/csv_file.py`) and registry support (`src/elspeth/core/registry.py`) plus tests (`tests/test_outputs_csv.py`).
- Suite now 20 passing tests; coverage ~89%.

## Lexicon Update (User Guidance)
- **Sources**: components that provide information (e.g., data loaders).
- **Sinks**: components that consume/persist information (e.g., result writers).
- **Plugins**: transformation/processing units that operate on data between sources and sinks.
- Future consideration: differentiate between transformation plugins (aggregators/stats) versus effect plugins (LLM calls, external actions) once workloads clarify.

## Legacy Experiment Logic Migration Plan
1. **Discovery & Inventory**
   - Review `old/main.py`, `old/experiment_runner.py`, `old/experiment_stats.py` to catalogue key behaviours: data preparation (`process_data`), prompt assembly, experiment suite configuration, cost/rate limiting, stats exports.
   - Identify external dependencies still missing (e.g., `elspeth.runner`, `elspeth.costs`) and decide whether to stub or rebuild.

2. **Module Restructuring**
   - Create `src/elspeth/core/experiments/` package housing:
     * `suite.py`: experiment suite orchestration (multiple configs, baseline handling).
     * `runner.py`: per-experiment execution (criteria loops, retries, checkpointing stubs).
     * `stats.py`: migrate necessary analytics (minimal viable subset first).
   - Define new interfaces if required (e.g., `ExperimentConfigSource`, `PromptFormatter`, `CostTracker`).

3. **Prompt & Context Handling**
   - Port prompt formatting logic from legacy code, ensuring compatibility with plugin-based prompts (system/user). Replace ad-hoc string formatting with structured templates or plugin hooks.
   - Implement context builders that transform raw dataset rows into the criteria-specific payloads expected by the LLM.

4. **Execution Flow Integration**
   - Expand `ExperimentOrchestrator` to support experiment configs (baseline vs variants), multiple criteria, retries, and checkpointing placeholders.
   - Integrate rate limiting/cost tracking stubs so later we can plug in real implementations.
   - Ensure outputs from experiments route through sink plugins (CSV/Blob) without breaking existing tests.

5. **Testing Strategy**
   - Add unit tests for new modules with mocked LLM and sink plugins.
   - Create fixture data mirroring the legacy CSV structure to validate prompt generation and result aggregation.
   - Maintain coverage thresholds; run integration test invoking orchestrator end-to-end with dummy LLM and real data loader.

6. **Incremental Cutover**
   - Once new modules reach parity for a single-experiment path, update CLI to expose experiment profiles (single vs suite).
   - Gradually retire legacy `old/` usage by pointing documentation/notes to the new modules; keep `old/` as archival reference until full parity confirmed.

7. **Future Enhancements**
   - Reintroduce statistics/analysis (from `experiment_stats.py`) as separate plugins or sinks.
   - Add configuration bootstrap script to generate venv, load `.env`, and run smoke tests.
- Introduced `src/elspeth/core/experiments` package with suite loader and basic runner to kick off legacy migration; added tests (`tests/test_experiments.py`). Next steps: expand runner to handle multi-criteria configs, cost tracking, and integrate with orchestrator.
- `ExperimentOrchestrator` now delegates to the new `ExperimentRunner`, keeping prompt handling centralized; runner metadata restored (`rows` + `row_count`).
- ExperimentRunner now supports criteria lists, storing per-criteria responses and passing both aggregated `response` and `responses` maps. CSV sink flattens criteria into `llm_<name>` columns. Updated config to include sample criteria and tests (`tests/test_experiments.py`, `tests/test_orchestrator.py`).
- ExperimentSuite loader now captures prompts/fields/criteria from experiment folders (reading Markdown prompt files when present), enabling future parity with legacy experiment configs. Tests updated to validate prompt extraction.

## Experiment Plugin Concept Draft
- **Definition**: Treat each metric or pack of metrics as an `ExperimentPlugin` responsible for transforming a row of input data (raw or post-LLM results) into derived insights, scores, or additional outputs. Plugins run after the core LLM execution to modularize analytics and keep the main runner lean.
- **Plugin Interface (concept)**:
  ```python
  class ExperimentPlugin(Protocol):
      name: str
      def initialize(self, experiment_config: ExperimentConfig) -> None:
          ...
      def process(self, row: dict, responses: dict) -> dict:
          """Return additional metrics/fields to merge into the sink payload."""
  ```
- **Lifecycle**:
  1. Loader resolves configured plugins per experiment (e.g., `plugins/experiments/metrics/critique.py`).
  2. Each plugin receives experiment-level configuration (e.g., thresholds, prompts) during `initialize`.
  3. During row processing, after LLM responses are captured, `ExperimentRunner` invokes each plugin’s `process` method to compute metrics (e.g., score from criteria content, aggregate stats, heuristics).
  4. Plugin output merges into the result record (e.g., adding `metric_quality=...`, `metric_flags=[...]`).

- **Configuration**: Extend experiment config JSON/YAML to specify plugin stack per experiment:
  ```json
  {
    "name": "baseline",
    "plugins": [
      {"name": "score_parser", "options": {"criteria": ["summary"]}},
      {"name": "token_usage", "options": {}}
    ]
  }
  ```

- **Plugin Categories**:
  - *Metrics*: parse LLM responses into structured scores, flags, or classification outputs.
  - *Aggregators*: compute running stats, compare against baselines, or build experiment-level dashboards.
  - *Post-processors*: redact sensitive data, format outputs, or push to sinks.

- **Benefits**:
  - Aligns with the “source → plugin → sink” architecture, enabling swap-in/out metrics without touching core runner.
  - Supports packs of metrics (a plugin can bundle multiple related calculations via shared options).
  - Simplifies testing: plugin unit tests can focus on narrow behavior with mocked inputs.

- **Integration Roadmap**:
  - Define protocol + base registry similar to existing datasource/LLM/sink registries.
  - Annotate experiment config loader to instantiate plugins per experiment.
  - Update runner to apply plugins sequentially when building result payloads.
  - Extend CSV sink (or other sinks) to capture new metrics automatically.
- Consider two plugin types: row-level processors (per record) and aggregators (dataset-level). Row plugins enrich individual results; aggregators run after all rows to compute suite-level metrics or comparisons. Implementation can expose two protocols or a single plugin with optional hooks (e.g., `process_row`, `finalize`).
- Added experiment plugin protocols (`RowExperimentPlugin`, `AggregationExperimentPlugin`) and wired `ExperimentRunner` to execute row-level plugins and aggregators. Tests (`tests/test_experiments.py`) ensure metrics merge into records and aggregates propagate to sinks.

## Experiment Suite Integration Plan
1. **Suite Configuration**
   - Extend settings/profile to allow selecting either a single prompt setup (current behavior) or a suite root directory containing experiment folders.
   - Each experiment config can override prompts, criteria, and plugin stacks; fallback to global defaults when missing.

2. **Orchestrator Support**
   - Introduce an `ExperimentSuiteRunner` that:
     * Loads the suite (using `ExperimentSuite.load`).
     * Builds an `ExperimentRunner` per experiment, merging global and experiment-specific options (prompts, plugins, sinks).
     * Iterates through baseline and variants, capturing results keyed by experiment name.
   - Provide hooks to plug aggregated results into sinks (e.g., writing multiple CSVs or a combined report).

3. **CLI Flow**
   - Add CLI arguments for `--experiment-suite` or a profile flag to toggle suite mode.
   - When suite mode is active, bypass single-run orchestrator and invoke the suite runner; default sink behavior can create subdirectories per experiment.

4. **Plugin Instantiation**
   - Extend config loader to resolve plugin names via registry; support experiment-specific plugin options.
   - Ensure row/aggregator plugins are instanced per experiment to avoid shared state.

5. **Testing**
   - Add unit tests to validate suite loading, baseline selection, and per-experiment execution (with mocked LLM and sinks).
   - Create integration test running a minimal suite (two experiments) and asserting results structure.

6. **Compatibility**
   - Maintain ability to run single-experiment mode without suite configuration.
   - Document new CLI options and update notes with suite usage guidance.
- Added `ExperimentSuiteRunner` to execute all experiments from a suite with shared defaults; tests ensure per-experiment prompts run via the new runner (`tests/test_experiments.py`).

## CLI & Config Integration Plan for Experiment Suite
1. **Configuration Schema**
   - Extend `config/settings.yaml` profile to allow a `suite_root` entry. When present, the orchestrator switches to suite mode (ignoring single prompt settings unless used as defaults).
   - Allow per-experiment overrides for sinks/plugins by referencing default sink plugin list (e.g., `suite_defaults: { sinks: [...], row_plugins: [...], aggregator_plugins: [...] }`).

2. **CLI Enhancements**
   - Add flags to `src/elspeth/cli.py`: `--suite-root`, `--suite-profile` (if referencing multiple suites). If provided, the CLI loads suite settings and invokes `ExperimentSuiteRunner` instead of single-run orchestrator.
   - Provide optional `--single` flag to force single experiment even when suite config exists (for debugging).

3. **Execution Flow**
   - Modify CLI `run` function to detect suite mode and build `defaults` dict (prompts, criteria, plugins) for the suite runner from settings.
   - For each experiment result, decide how sinks handle outputs: either reuse global sinks (writing combined output) or instantiate per-experiment sink instances (e.g., CSV per experiment). Start simple by appending experiment name to output filenames.

4. **Testing**
   - Create integration test using temporary suite directory with two experiments, run through CLI (via subprocess or direct call), assert outputs contain separate experiment entries.
   - Mock sinks/LLM to avoid network and assert metadata contains experiment names.

5. **Documentation**
   - Update notes (and eventually README) with CLI usage for suite mode, expected config structure, and plugin extension points.
- CLI now supports suite mode (`--suite-root`, `--single-run`); suite execution clones CSV sinks per experiment and logs per-experiment results. Added `tests/test_cli_suite.py` to exercise the flow.
*** End Patch

## Experiment Config Enhancements Plan
1. **Config Schema**
   - Extend `ExperimentConfig` to capture plugin stacks, sink overrides, and LLM overrides (temperature, max_tokens) per experiment.
   - Allow optional fields in `config.json` to specify `row_plugins`, `aggregator_plugins`, and `sinks` (with references to registry names and options).
   - Provide fallback to suite defaults when not specified.

2. **Plugin Registry**
   - Create an experiment plugin registry similar to data sources/LLMs, mapping names to factory functions.
   - Include minimal built-in plugins (e.g., `score_parser`, `noop`) as placeholders; port legacy metrics later.

3. **Runner Wiring**
   - Update `ExperimentSuiteRunner.build_runner` to instantiate plugins per experiment using the registry and merge with defaults.
   - Ensure sinks can be overridden per experiment; implement clone logic for plugin instances to avoid shared state.

4. **Testing**
   - Add tests covering config parsing for plugin and sink overrides, verifying the suite runner attaches correct plugins/sinks for each experiment.
   - Use dummy plugins/sinks in tests to assert behavior (e.g., row plugin increments a counter only for one experiment).

5. **Documentation**
   - Update notes and eventually README with the experiment config schema (JSON structure, plugin references).

- Experiment config now captures per-experiment plugin/sink definitions (`row_plugins`, `aggregator_plugins`, `sinks`). Added plugin registry (`src/elspeth/core/experiments/plugin_registry.py`) with default no-op plugins, and suite runner instantiates plugins/sinks per experiment. Tests cover plugin definition handling and CLI suite flow.

## Rate Limiting & Cost Tracking Plugin Plan
1. **Plugin Interfaces**
   - Define `RateLimiter` protocol with methods like `acquire(metadata)` and `release` / context manager support.
   - Define `CostTracker` protocol capable of recording per-request costs and summarizing totals; allow pluggable pricing strategies.

2. **Configuration**
   - Extend settings (and experiment config) to reference `rate_limiter` and `cost_tracker` plugins with options (e.g., default token-based limiter, fixed price per token).
   - Suite defaults can provide shared rate limiter / cost tracker across experiments.

3. **Registry & Default Implementations**
   - Introduce a registry similar to other plugins for rate limiters and cost trackers.
   - Provide baseline implementations:
     * `simple_window_limiter`: configurable requests per minute/second.
     * `noop_limiter`: no throttling.
     * `fixed_price_tracker`: multiplies prompt/completion tokens by configurable rates.
     * `noop_tracker`: collects no cost.

4. **Integration**
   - Modify `ExperimentRunner` (or LLM client wrapper) to acquire rate limiter before each LLM call and record costs afterward (pull usage from LLM responses if available).
   - Aggregator plugins can access cost summaries (from cost tracker) to emit experiment-level cost aggregates.

5. **Testing**
   - Add unit tests for rate limiter behavior (mock time to simulate windows), and cost tracker calculations.
   - End-to-end tests to ensure rate limiter hooks are invoked, and cost outputs appear in payload metadata/sinks.

6. **Documentation**
   - Update notes/README with plugin configuration examples for rate limiting and cost tracking, enabling provider-specific pricing swap-outs.
- Added rate limiter and cost tracker plugin infrastructure (`src/elspeth/core/controls/*`), wired into orchestrator/runner with config-driven instantiation. Defaults include no-op and fixed window/price implementations. CLI and suite runner now honour `rate_limiter`/`cost_tracker` definitions, and tests cover limiter/cost tracker behavior.

## Legacy Experiment Port Plan
1. Audit & Architecture Mapping
2. Prompt Packs & Config Enhancements
3. Baseline Suite Logic & Comparison
4. Retries, Checkpointing, Failure Handling
5. Stats & Reporting Plugins
6. Legacy Output & Archival Features
7. Documentation, Bootstrapping, Verification
- Added prompt pack support: settings and experiments can reference reusable prompt bundles that supply prompts, criteria, plugins, sinks, and rate/cost defaults. Config loader stores pack definitions, suite runner merges them per experiment, and CLI passes them through.

## Baseline Suite Logic Plan
1. Ensure `ExperimentSuiteRunner` identifies baseline experiment (from config) and runs it first; expose baseline payload to subsequent runs.
2. Provide comparison helpers so plugins can access baseline results (e.g., pass baseline payload into aggregator plugins via context).
3. Implement a baseline comparison aggregation plugin (simple diff metrics for now) and tests verifying baseline vs variant comparisons.
4. Update CLI to report baseline + variant outputs clearly; ensure sinks can include comparison summaries.
- Suite runner now orders experiments with baseline first, exposes baseline payload to variants, and supports baseline comparison plugins (default `row_count`). Prompt packs can define baseline plugins, sinks, and rate/cost controls.

## Legacy Experiment Logic Execution Plan
### Phase 4 – Retries, Checkpointing, Failure Handling
1. Implement retry/backoff configuration per experiment (and global defaults); wrap `_execute_llm` with retry logic.
2. Add checkpoint plugin (write interim results per batch, resume capability via row IDs). Integrate with suite runner to skip processed rows.
3. Capture per-row failures (error message, timestamp) and expose in payload/sinks via failure aggregator plugin.

### Phase 5 – Metrics & Statistical Plugins
0. **Risk Reduction – Legacy Metrics Recon & Dependency Probe**
   - Catalogue the concrete behaviours in `old/experiment_stats.py` and related helpers; flag any external dependencies (numpy/scipy/pingouin/etc.) and decide which are mandatory versus optional extras.
   - Identify representative sample inputs (both numeric scores and free-form rubric responses) that can drive regression-style tests; derive fixtures from existing blob sample or craft synthetic frames.
   - Draft interface notes for how row plugins will expose derived metrics (naming conventions, typing) so sinks/tests remain stable; circulate via `notes/` before implementation.
1. **Row Plugin Implementation**
   - Implement score extraction/validation plugins (e.g., parse JSON-encoded metrics, numeric ranges, categorical flags) with comprehensive unit tests including malformed input handling.
   - Add optional normalisation/threshold plugins to convert raw scores into pass/fail or scaled outputs; ensure configuration-driven thresholds.
2. **Aggregation Plugin Implementation**
   - Port baseline comparison logic (mean deltas, win rates, error counts) into aggregation plugins; support cross-experiment comparisons using existing baseline payload wiring.
   - Provide statistical summary plugins leveraging lightweight dependencies first (pandas/numpy); gate heavier packages behind optional extras and skip tests when unavailable.
3. **Recommendation & Reporting Plugins**
   - Create a narrative summary plugin that collates aggregation outputs into human-readable recommendations, mirroring legacy text.
   - Ensure outputs integrate with result payloads so sinks/CLI can surface them; include snapshot tests for phrasing stability.
4. **Configuration & CLI Wiring**
   - Extend prompt packs and experiment configs with plugin presets, defaults, and optional parameters (thresholds, statistical methods).
   - Update CLI options (e.g., `--enable-metrics-pack`) and documentation so users can toggle new plugins.
5. **Test & Validation Sweep**
   - Expand unit/integration coverage for new plugins, including baseline suite runs covering row + aggregation + recommendation outputs.
   - Run performance sanity checks on medium datasets to confirm no regressions; profile hotspots if statistical calculations become heavy.

**Phase 5 status (2025-05-XX):**
- Implemented default metrics stack under `src/elspeth/plugins/experiments/metrics.py` with row (`score_extractor`), aggregation (`score_stats`, `score_recommendation`), and baseline comparison (`score_delta`) plugins.
- Added configuration wiring in `config/settings.yaml` and CLI toggle `--disable-metrics` to opt-out when required.
- Comprehensive unit coverage in `tests/test_experiment_metrics_plugins.py`; full suite passes with metrics enabled by default.

### Phase 6 – Output & Archival Sinks
0. **Risk Reduction – Sink Surface Audit & Dependency Design**
   - Catalogue required hosting targets (Azure Blob archival, GitHub/Azure DevOps repo commits, signed artifact generation) and identify authentication flows; confirm SDK/library availability and decide on optional extras.
   - Prototype credential interface (env vars, managed identity, PAT) and write threat/risk notes for signing material (key storage, rotation responsibilities).
   - Draft test strategy for external integrations (use fakes/mocks, dry-run modes) to avoid brittle integration tests.
1. **Standard Sink Implementations**
   - Implement enhanced blob sink supporting tiered containers/folders and metadata manifests; ensure compatibility with existing config schema.
   - Introduce filesystem bundle sink producing structured archives (CSV/JSON plus metadata manifest) to support signing and downstream packaging.
2. **Version-Control Output Sinks**
   - Build GitHub/Azure DevOps sink that writes experiment artifacts into a repository via REST API or git push (support dry-run for tests); handle branch naming, PR hooks, and conflict resolution basics.
   - Provide abstraction for repo credentials (PAT/OAuth) and document required scopes; add unit tests with mocked HTTP interactions.
3. **Cryptographic Signing & Integrity**
   - Design signing workflow (e.g., detached signature over archive manifest) using `cryptography`/`pgpy`; support pluggable signing providers (local key, Azure Key Vault).
   - Add verification helper to CLI/tests to validate signatures and include metadata in payloads.
4. **Configuration & CLI Enhancements**
   - Extend settings/prompt packs to choose sink stacks per deployment target (blob, repo, signed file); expose CLI toggles for dry-run vs. live pushes.
   - Ensure suite runner clones per-experiment sink definitions correctly for new sink types.
5. **Testing & Validation**
   - Implement integration-style tests using temporary directories and mocked services for blob/repo sinks; include regression tests for manifest contents.
   - Validate signing output with round-trip verification and document operational runbooks.

**Phase 6 status (2025-05-XX):**
- Shipping sinks now cover Azure Blob, local bundles, GitHub/Azure DevOps repositories (dry-run aware), and HMAC-signed artifacts. Config/CLI wiring allows operators to toggle between dry-run and live modes and switch prompt packs for archival workflows. Unit tests cover blob uploads, bundle generation, repo interactions, signature verification, and CLI toggles.

### Phase 7 – Tooling & Documentation
1. Publish sample suite (prompts, configs, plugins) mirroring legacy structure.
2. Provide bootstrap script/Makefile for venv setup, `.env` loading, suite run, cleanup.
3. Update README/notes comprehensively: plugin architecture, suite CLI usage, configuration examples, extending with new metrics.
4. Optional regression check: compare new output to legacy sample (if available).

**Phase 7 status (2025-05-XX):**
- Added `config/sample_suite/` with local CSV datasource, mock LLM, and three experiments exercising templating, metrics, and rate/cost controls.
- Created `scripts/bootstrap.sh` and `Makefile` targets for environment setup, testing, and running the sample suite.
- Authored a top-level `README.md`, refreshed `AGENTS.md`, and documented onboarding/tooling expectations.
- Introduced LLM middleware (audit logging, prompt shielding) and adaptive rate limiting with threaded execution controls to mirror legacy safety/audit behaviour.
- Outstanding work: Azure ML telemetry hooks, DevOps/Excel archivers, advanced statistics suite, and schema/preflight validation from legacy runner.

## Phase 4 Plan – Retries, Checkpointing, Failure Handling
1. **Retry Configuration**
   - Extend settings/experiment config to accept `retry` options (max attempts, backoff, jitter).
   - Wrap `_execute_llm` with retry logic using exponential/backoff strategy and integrate with rate limiter.
   - Record retry metadata (attempt count, wait times) in response metrics.

2. **Checkpoint Plugin**
   - Create checkpoint sink/plugin (e.g., writes progress after every N rows). Store processed row IDs/timestamps.
   - Update suite runner to load checkpoint data and skip already processed rows.
   - Allow checkpoint plugin to be configured per experiment or via suite defaults.

3. **Failure Handling**
   - Enhance `_execute_llm` to catch exceptions, record failure details (message, timestamp, attempt) in `results`.
   - Add failure summary aggregator plugin (counts per error type, sample messages) for suite-level reporting.

4. **Testing**
   - Unit tests for retry logic (mock LLM to fail first N calls), verifying backoff and metadata.
   - Tests for checkpoint plugin (simulate incomplete run, rerun and ensure skip/merge works).
   - Failure aggregation tests confirming summaries include counts and sample error messages.
- Added retry/backoff configuration, checkpoint handling, and failure tracking to `ExperimentRunner`; suite runner now runs baseline first and applies baseline comparison plugins. Checkpoint files skip processed rows, failure metadata captured, and tests cover retries, failures, and checkpoint resume.
- **Prompt Engine Migration Roadmap**
  1. Inventory legacy templating helpers (cloning, conditional blocks, validation) and map to new abstractions under `src/elspeth/core/prompts/`.
  2. Port template parsing/rendering with support for default values, conditionals, error messaging, and cloning utilities.
  3. Integrate prompt engine into orchestrator/runner, update samples, and document usage.
