# ELSPETH Secure LLM Orchestrator

ELSPETH is a general-purpose, security-focused orchestration layer for large
language model experiments. The platform emphasises pluggable components so
datasources, LLM clients, metrics, and result sinks can be swapped without
touching the core runner while preserving a defensible audit trail.

## Project Structure

- `src/elspeth/core/` – orchestration, prompt engine, controls (rate/cost), registry.
- `src/elspeth/plugins/` – concrete plugins for datasources (Azure blob, local CSV),
  LLM clients (Azure OpenAI, mock), metrics/statistics, and result sinks
  (CSV, blob, repository, signed artifacts with spreadsheet sanitisation).
- `config/` – global settings, sample suite definitions, and blob datastore config.
- `tests/` – pytest suite covering plugins, orchestrator, CLI, and prompt engine.
- `scripts/bootstrap.sh` / `Makefile` – tooling to create the virtual
  environment, install dependencies, and run common commands.

## Quick Start

1. **Bootstrap the environment**

   ```bash
   make bootstrap             # creates .venv, installs deps, runs pytest
   # or skip tests: make bootstrap-no-test
   ```

2. **Run the sample suite** (no external dependencies, uses the mock LLM):

   ```bash
   make sample-suite
   ```

   Outputs are written to `outputs/sample_suite/<experiment>_latest_results.csv`
   with aggregates and baseline comparisons.
3. **Activate the CLI manually** (optional):

   ```bash
   source .venv/bin/activate
   python -m elspeth.cli --help
   ```

### Suite management & reporting

The CLI now supports legacy-friendly suite maintenance tasks:

```bash
# Create a disabled experiment scaffold (copies prompts when baseline available)
python -m elspeth.cli \
  --settings config/settings.yaml \
  --suite-root config/sample_suite \
  --create-experiment-template draft_variant \
  --template-base baseline_experiment \
  --head 0

# Export the full suite definition to JSON/YAML
python -m elspeth.cli \
  --settings config/settings.yaml \
  --suite-root config/sample_suite \
  --export-suite-config outputs/sample_suite_export.yaml \
  --head 0

# Run the suite and generate consolidated analytics artefacts
python -m elspeth.cli \
  --settings config/settings.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/sample_suite_reports \
  --head 0
```

Reports require pandas/openpyxl (for Excel) and matplotlib/seaborn (for PNG charts).
Install them via the dev extra plus matplotlib:[^readme-reporting-2025-10-12]

```bash
pip install -e .[dev]
pip install -e .[analytics-visual]  # installs matplotlib + seaborn for charts
```
<!-- UPDATE 2025-10-12: Alternatively install plotting dependencies via `pip install -e .[analytics-visual]` when enabling the visual analytics sink. -->

## Configuration Overview

Settings files (default: `config/settings.yaml`) describe the runtime:

- `datasource` – plugin + options (e.g. `azure_blob`, `local_csv`).
- `llm` – LLM client (`azure_openai` for real endpoint, `mock` for offline).
- `sinks` – destination plugins; CSV sink is safe for local testing.
- Spreadsheet sinks escape leading `= + - @`, tab, newline, and single-quote characters by default. Configure per sink with `sanitize_formulas` (default `true`) and `sanitize_guard` (default `'`); manifests record the guard for auditing.
- `prompt_packs` – reusable prompt bundles defining system/user prompts,
  criteria, plugin stacks, and defaults.
- `suite_defaults` – values shared across experiments when running suites.
- `concurrency` – optional configuration enabling threaded execution (max workers,
  backlog threshold, pause thresholds) while respecting the configured rate limiter.
- The CLI runs fail-fast validation on settings and suite definitions before
  execution. Validation errors abort immediately; warnings are logged for
  follow-up.
- Datasource/sink (and analytics) plugins accept `on_error: "abort" | "skip"`
  in their options. Use `skip` for best-effort runs when a particular sink or
  datasource failure should not stop the suite; the default remains `abort`.
- Optional extras:
  - `pip install -e .[stats-core]` – enables statistical significance testing.
  - `pip install -e .[stats-agreement]` – enables agreement/reliability metrics.
  - `pip install -e .[stats-bayesian]` – enables Bayesian baseline comparisons.
  - `pip install -e .[stats-planning]` – brings in power/sample-size analytics.
  - `pip install -e .[stats-distribution]` – enables distribution/drift analytics.
  - `pip install -e .[analytics-visual]` – installs matplotlib/seaborn for PNG/HTML analytics charts.[^readme-visual-extra-2025-10-12]

Experiments (`config/sample_suite/*/config.json`) can:

- select a `prompt_pack` or override prompts directly,
- register row/aggregation/baseline plugins,
- define criteria-specific templates and defaults,
- override rate limiter, cost tracker, concurrency, or early-stop definitions.

## Prompt Engine

Prompts are rendered via the new Jinja-based engine:

- Legacy `{FIELD}` syntax is automatically translated to `{{ FIELD }}`.
- Conditionals, filters, and defaults are available
  (e.g. `{{ industry|default('general', boolean=true) }}`).
- Criteria prompts can set their own defaults to specialise variants.
- Rendering failures raise informative `PromptRenderingError` exceptions.

## Plugins

Each plugin type registers with `src/elspeth/core/registry.py`.

- **Datasources**: `azure_blob`, `csv_blob` (local CSV stand-in for blob inputs), `local_csv` (reads local CSV files).
- **LLM clients**: `azure_openai`, `mock` (deterministic hashing), and `static_test` (returns predefined content/metrics for tests and fixtures).
- **Metrics**: `score_extractor`, `score_stats`, `score_recommendation`, `score_delta`, `score_variant_ranking`.

Metrics emitted by the default row plugin live under `record["metrics"]`:
the LLM response contributes raw keys such as `score`/`comment`, while
`score_extractor` adds a `scores` mapping (per-criteria numeric values) and
optional `score_flags` booleans. Aggregators and early-stop plugins should
reference per-criteria values via paths like `scores.analysis`.

- **Baselines**: `score_significance` (effect sizes, t-tests with optional Bonferroni/FDR adjustments), `score_bayes`
  (posterior probability intervals), `score_cliffs_delta`, `score_assumptions`, `score_practical`.
- **Aggregators**: `score_agreement` (Cronbach’s alpha, Krippendorff’s alpha),
  `score_power` (target sample size/power estimates), `score_distribution`
  (distribution shift tests), and `score_variant_ranking` in addition to `score_stats` and `score_recommendation`.
- **Early stop**: `threshold` plugin halts execution when configured metrics cross thresholds; definitions can be provided via `early_stop` shorthand or `early_stop_plugins` arrays (`src/elspeth/plugins/experiments/early_stop.py`).
- **LLM middleware**: `audit_logger`, `prompt_shield`, `azure_content_safety`, `health_monitor`.
- **Sinks**: CSV, Azure blob, local bundles, ZIP bundles, GitHub/Azure DevOps repositories,
  signed artifact bundles, analytics report sink (JSON/Markdown summaries), and analytics visual sink (PNG/HTML charts). Spreadsheet sinks support
  `sanitize_formulas` / `sanitize_guard` options; guard choices propagate to manifest metadata. The visual sink requires `matplotlib` (and optionally `seaborn`) when generating charts.

To add a new plugin, implement the appropriate interface from
`src/elspeth/core/interfaces.py` and register it via the registry helper.

## Testing & Tooling

- Run `make test` (or `python -m pytest`) to execute the suite (61 tests, ~83% coverage).
- Spreadsheet compatibility matrix: `tox -e sanitization-matrix` generates guarded CSV/Excel
  artifacts and validates them with pandas, the stdlib `csv` reader, and openpyxl, recording
  outcomes in `docs/notes/sanitization_compat.md`.
- `scripts/bootstrap.sh` supports idempotent environment setup; set
  `RUN_TESTS=0` to skip the test phase.
- Lint helpers (`make lint`) install and run `black`/`isort` in check mode.
- Scaffold new plugins with `python scripts/plugin_scaffold.py <kind> <name>`;
  available kinds: `row`, `aggregator`, `baseline`, `sink`, `middleware`.
- Enable formatting hooks with `pip install -e .[dev] && pre-commit install`
  (see `.pre-commit-config.yaml`).

## Update History
- 2025-10-12 – Added early-stop plugin catalogue entry, visual analytics sink reference, and aligned documentation with concurrency, analytics, and telemetry enhancements.

## SonarQube Coverage

- Running `python -m pytest` (or `make test`) now emits `coverage.xml` alongside the terminal report so SonarQube/SonarCloud can ingest the data.
- Populate `sonar-project.properties` with your organisation and project identifiers (or override them via `sonar-scanner` flags). The file already enables `sonar.python.coverage.reportPaths=coverage.xml` as described in the [official guide](https://docs.sonarsource.com/sonarqube-cloud/enriching/test-coverage/python-test-coverage).
- Execute the scanner from the project root after setting a `SONAR_TOKEN`, e.g.

  ```bash
  export SONAR_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
  sonar-scanner \
    -Dsonar.login=$SONAR_TOKEN \
    -Dsonar.host.url=https://sonarcloud.io
  ```

  The command reuses values defined in `sonar-project.properties`; override any parameter with additional `-D` flags when needed.

## Retry Observability

- Each LLM invocation records a retry history. Successful responses expose `response["retry"]` detailing attempts, and failures capture the same structure under `payload["failures"][*]["retry"]`.
- CLI single-run output flattens retry statistics (attempt counts and JSON history) alongside metrics, and logs a warning when retries are exhausted.
- Azure telemetry middleware logs a `llm_retry_exhausted` row whenever the retry budget is consumed, capturing error type and serialized history for investigation.

## Working with Real Services

- Populate `.env` or export environment variables (`ELSPETH_AZURE_OPENAI_KEY`,
  `ELSPETH_AZURE_OPENAI_ENDPOINT`, `ELSPETH_AZURE_OPENAI_DEPLOYMENT`, blob SAS tokens,
  etc.) before switching the `llm` or `datasource` plugins.
- Use `--live-outputs` on the CLI to disable dry-run mode for repository sinks.
- Signed artifact sink expects a shared secret via `ELSPETH_SIGNING_KEY` (or
  explicit `key` option).
- Install Azure extras when running inside Azure ML or using Azure telemetry:

  ```bash
  pip install -e .[azure]
  ```

- Enable the Azure environment middleware per experiment to emit telemetry to
  Azure ML Runs:

  ```json
  {
    "name": "prod_suite_variant",
    "prompt_pack": "sample",
    "llm_middlewares": [
      {
        "name": "azure_environment",
        "options": {
          "log_prompts": false,
          "on_error": "abort"
        }
      }
    ]
  }
  ```

  By default the middleware now skips run binding when an Azure ML context is not
  detected, logging to the console instead. Set `on_error` to `"abort"` if you
  want the run to fail when telemetry cannot attach to Azure ML.

## Configuration Migration

- Legacy keys

## Early Stop Heuristics

- Configure `early_stop_plugins` in settings, suite defaults, or individual experiments to halt processing when a metric crosses a threshold. Example:

  ```yaml
  early_stop_plugins:
    - name: threshold
      options:
        metric: scores.analysis
        threshold: 0.8
        comparison: gte   # options: gte, gt, lte, lt
        min_rows: 3       # evaluate after at least 3 rows
  ```

- The legacy `early_stop` mapping remains a shorthand for the `threshold` plugin.
- When triggered, the runner stops scheduling new rows and records the trigger in `metadata['early_stop']` (including the plugin name).
- See `config/sample_suite/early_stop_threshold/` and `config/sample_suite/early_stop_fast_exit/`
  for sample experiments demonstrating conservative and aggressive early-stop settings.

 such as `promptPack`/`promptPacks` and `middlewares` have been renamed.
  A concise mapping is maintained in `notes/config-migration.md` for reference.

- Validators surface actionable messages (unknown prompt packs list available names,
  middleware errors show configured options). Run `elspeth validate --settings <file>` to
  review a configuration before execution.
- When migrating older suites, update prompt pack references and ensure all middleware
  names correspond to registered plugins (see `src/elspeth/plugins/llms/`).

## Further Reading

- `notes/plugin-architecture.md` – architecture and migration notes per phase.
- `notes/phase6-sinks.md` / `notes/phase7-docs.md` – detailed sink and
  documentation planning.
- `AGENTS.md` – orientation for internal contributors.
- `docs/migration-guide.md` – end-to-end migration guide from legacy scripts to the plugin architecture, including prompt packs, middleware, and sink configuration.
- `docs/logging-standards.md` – structured logging expectations for middleware and sinks.
- `docs/release-checklist.md` – pre-release verification steps and governance reminders.
- `docs/reporting-and-suite-management.md` – CLI walkthrough for suite exports, template creation, and analytics reports.
- `docs/examples_colour_animals.md` – end-to-end example using the HTTP OpenAI plugin with a colour→animal dataset.

## Update History
- 2025-10-12 – Update 2025-10-12: Added dependencies/visual extras guidance and linked to reporting documentation for analytics workflows.

[^readme-reporting-2025-10-12]: Update 2025-10-12: Reporting dependencies correspond to docs/reporting-and-suite-management.md (Prerequisites) and docs/architecture/dependency-analysis.md (Optional Extras).
[^readme-visual-extra-2025-10-12]: Update 2025-10-12: Visual analytics extra aligns with docs/architecture/dependency-analysis.md (Optional Extras) and docs/architecture/security-controls.md (Update 2025-10-12: Output Sanitisation).
