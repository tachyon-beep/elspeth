# Migration Guide: Legacy Stack → Plugin Architecture

This guide helps teams upgrade from the legacy `old/` implementation to the modern plugin-driven ELSPETH.

## Prerequisites

- Python 3.12+
- `pip install -e .[dev,analytics-visual]` to pull dependencies.
- Review `README.md` for project overview and setup notes.

## High-Level Mapping

| Legacy Concept | New Location | Notes |
|----------------|--------------|-------|
| `old/main.py` CLI | `src/elspeth/cli.py` | All execution flows funnel through the CLI using config-driven plugins. |
| Safety manager / prompt shields | LLM middleware: `prompt_shield`, `azure_content_safety` | Configure in `llm_middlewares` to replicate legacy safety checks. |
| Health monitor | `health_monitor` middleware | Emits heartbeat logs similar to legacy `HealthMonitor`. |
| Experiment stats / analytics | Plugins in `src/elspeth/plugins/experiments/metrics.py` | Metrics, practical significance, Cliff’s delta, reporting sink replace legacy `StatsAnalyzer`. |
| Azure DevOps archiving | Repository sink (`azure_devops_repo`) | Configure in sinks section of settings. |
| Azure telemetry logging | `azure_environment` middleware | Handles Azure ML run interaction; defaults to skip when no run context. |
| Retry/cost telemetry | Runner metadata + analytics/reporting sinks | `retry_summary`, `cost_summary`, and `early_stop` metadata surface in payloads and downstream artefacts. |
| Concurrency / checkpointing | `concurrency` & `checkpoint` settings | Configure thread pool thresholds and resumable IDs to match legacy behaviour. |

## Configuration Migration

Refer to `notes/config-migration.md` for key renames. Typical steps:

1. Rename `promptPack` → `prompt_pack`, `middlewares` → `llm_middlewares`, etc.
2. Define prompt packs under `prompt_packs` and reference via `prompt_pack` at settings or experiment level.
3. For each legacy plugin (metrics, sinks, middleware), declare the equivalent in `settings.yaml`:

   ```yaml
   default:
     llm:
       plugin: azure_openai
       options:
         deployment: ${AZURE_OPENAI_DEPLOYMENT}
         config:
           api_key: ${AZURE_OPENAI_KEY}
           endpoint: ${AZURE_OPENAI_ENDPOINT}
     llm_middlewares:
       - name: prompt_shield
         options:
           denied_terms: ["internal use only"]
           on_violation: mask
       - name: azure_content_safety
         options:
           endpoint: ${AZURE_CONTENT_SAFETY_ENDPOINT}
           key_env: AZURE_CONTENT_SAFETY_KEY
           severity_threshold: 4
           on_violation: abort
     sinks:
       - plugin: csv
         options:
           path: outputs/sample_suite/latest_results.csv
       - plugin: analytics_report
         options:
           base_path: outputs/sample_suite/analytics
     prompt_packs:
       sample:
         prompts:
           system: |
             You are an evaluation assistant...
           user: |
             Evaluate {{ APPID }}...
         prompt_fields:
           - APPID
           - title
         criteria:
           - name: analysis
             template: |
               Provide analysis for {{ APPID }}.
     suite_defaults:
       llm_middlewares:
         - name: prompt_shield
       early_stop_plugins:
         - name: threshold
           options:
             metric: scores.analysis
             threshold: 0.75
             min_rows: 2
   ```

## Replacing Legacy Safety Checks

- **Prompt shield**: `prompt_shield` middleware now supports `abort`, `mask`, or `log` actions when encountering banned terms.
- **Azure Content Safety**: `azure_content_safety` middleware performs severity checks; set `on_violation` to `abort`, `mask`, or `log`.
- **Health Monitor**: Add `health_monitor` to emit heartbeat logs (`requests`, `failures`, latency stats).

## Analytics & Reporting

- Configure experiment-level metrics via `row_plugins`, `aggregator_plugins`, and `baseline_plugins`.
- `analytics_report` sink writes JSON/Markdown summaries of results, aggregators, and baseline comparisons.
- Sample configuration: `config/sample_suite/` demonstrates early stop, analytics, and reporting sinks.[^migration-sample-suite-2025-10-12]
<!-- UPDATE 2025-10-12: Suite reporting commands (`--reports-dir`) now generate comparative analysis, validation summaries, and recommendations mirroring legacy Excel dashboards (`src/elspeth/tools/reporting.py:33`). -->
- **Visual analytics parity** – Configure `visual_report` sink (requires the `analytics-visual` extra) to regenerate PNG/HTML dashboards that previously relied on bespoke plotting scripts:

  ```yaml
  sinks:
    - plugin: visual_report
      options:
        base_path: outputs/sample_suite/visual
        formats: ["png", "html"]
        chart_title: "Mean Scores by Criterion"
  ```

  Install extras with `pip install -e .[dev,analytics-visual]` to pull `matplotlib`/`seaborn` (`src/elspeth/plugins/outputs/visual_report.py:17`).[^migration-visual-2025-10-12]
<!-- UPDATE 2025-10-12: Visual sink module relocation -->
Update 2025-10-12: Visual analytics sink lives in `src/elspeth/plugins/nodes/sinks/visual_report.py`.
<!-- END UPDATE -->
- **Suite report exports** – Pass `--reports-dir outputs/sample_suite/reports` to re-create executive summaries, validation JSON, comparative analysis, recommendations, and Excel dashboards without custom notebooks (`src/elspeth/cli.py:392`, `src/elspeth/tools/reporting.py:138`).[^migration-suite-reports-2025-10-12]
<!-- UPDATE 2025-10-12: Suite report citation refresh -->
Update 2025-10-12: Report generation dispatch now resides at `src/elspeth/cli.py:395-458` with implementation in `src/elspeth/tools/reporting.py:26-199`.
<!-- END UPDATE -->

## Azure-Specific Features

- **Azure ML telemetry**: Use `azure_environment` middleware in specific experiments or suite defaults. Set `on_error` to `skip` for local runs.
- **Azure DevOps repository sink**: Add `azure_devops_repo` to sinks with organization/project/repository options. Works best with `--live-outputs`.
- **Content Safety**: Set `AZURE_CONTENT_SAFETY_ENDPOINT` and `AZURE_CONTENT_SAFETY_KEY` env variables for middleware to authenticate.
- **Credential migration**: Replace legacy hard-coded SAS/keys with environment variables referenced via `_env` options, or rely on managed identity defaults added in the plugin refactor (`src/elspeth/plugins/outputs/blob.py:210`, `src/elspeth/plugins/outputs/signed.py:107`).[^migration-azure-creds-2025-10-12]

## Sample Migration Steps

1. Copy legacy experiment JSON folders into `config/sample_suite/<experiment>/` and ensure each has `config.json`, `system_prompt.md`, `user_prompt.md`.
2. Update `config.json` to include `prompt_pack`, plugin definitions, and any experiment-specific middleware or sinks.
3. Run validation: `python -m elspeth.cli --settings config/sample_suite/settings.yaml --suite-root config/sample_suite --head 3`.
4. Inspect outputs under `outputs/sample_suite/` and analytics reports for parity.

## Reference Material

- `README.md` – Plugin overview and configuration examples.
- `config/sample_suite/README.md` – Details of sample experiments and sinks.
- `notes/stats-analytics-inventory.md` – Analytics plugin coverage.
- `notes/stats-refactor-plan.md` – Future analytics enhancements.
- `notes/azure-middleware.md` – Azure middleware usage notes.
<!-- UPDATE 2025-10-12: `notes/config-migration.md` now lists normalized `concurrency`, `early_stop_plugins`, and `checkpoint` keys to map legacy runner flags. -->

## Support Channels

- Run `elspeth list plugins` (future enhancement) or browse `src/elspeth/plugins/` for available plugins.
- Unit tests in `tests/` illustrate configuration patterns and middleware/sink behavior.

## Added 2025-10-12 – Concurrency & Early-stop Parity Checklist

- Enable threaded execution by defining:[^migration-concurrency-2025-10-12]

  ```yaml
  concurrency:
    enabled: true
    max_workers: 6
    backlog_threshold: 25
    utilization_pause: 0.85
  checkpoint:
    path: checkpoints/latest.jsonl
    field: APPID
  ```

  This mirrors the legacy runner’s parallel mode and resume semantics (`src/elspeth/core/experiments/runner.py:365`, `src/elspeth/core/experiments/runner.py:280`).
- Map legacy early-stop flags (`runner.earlyStop`) to the normalized plugin definition:[^migration-early-stop-2025-10-12]

  ```yaml
  early_stop_plugins:
    - name: threshold
      options:
        metric: metrics.scores.analysis
        threshold: 0.8
        comparison: gte
        min_rows: 3
  ```

  (`src/elspeth/plugins/experiments/early_stop.py:17`, `src/elspeth/core/experiments/plugin_registry.py:298`).
- Translate analytics/reporting scripts to CLI calls that include `--reports-dir` so consolidated JSON, Markdown, and Excel assets replace bespoke notebook workflows (`src/elspeth/cli.py:240`, `src/elspeth/tools/reporting.py:94`).[^migration-suite-reporting-2025-10-12]
- Enable analytics and visual extras via `pip install .[stats-core,stats-agreement,analytics-visual]` when migrating legacy statistical notebooks; document the chosen extras in accreditation runbooks to ensure dependency parity (`pyproject.toml:39`, `pyproject.toml:56`).[^migration-analytics-extras-2025-10-12]

## Update History

- 2025-10-12 – Documented concurrency, checkpoint, early-stop migration steps and noted suite reporting parity with legacy dashboards.
- 2025-10-12 – Update 2025-10-12: Added references to sample suites, concurrency governance, and suite reporting CLI flows.

[^migration-sample-suite-2025-10-12]: Update 2025-10-12: Sample suite coverage aligns with docs/reporting-and-suite-management.md (Update 2025-10-12: Suite Report Generator).
[^migration-concurrency-2025-10-12]: Update 2025-10-12: Concurrency guidance ties to docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Parallel Execution Gate).
[^migration-early-stop-2025-10-12]: Update 2025-10-12: Early-stop plugins normalised per docs/architecture/plugin-security-model.md (Update 2025-10-12: Early-Stop Lifecycle).
[^migration-suite-reporting-2025-10-12]: Update 2025-10-12: Suite reporting flows elaborated in docs/reporting-and-suite-management.md (Update 2025-10-12: Suite Export Tooling).
[^migration-visual-2025-10-12]: Update 2025-10-12: Visual analytics sink usage matches docs/reporting-and-suite-management.md (Update 2025-10-12: Visual Analytics Sink).
[^migration-suite-reports-2025-10-12]: Update 2025-10-12: Suite reports inventory detailed in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Suite Reporting Export Flow).
[^migration-azure-creds-2025-10-12]: Update 2025-10-12: Azure credential handling cross-referenced in docs/architecture/security-controls.md (Update 2025-10-12: Secret Management).
[^migration-analytics-extras-2025-10-12]: Update 2025-10-12: Optional extras documented in docs/architecture/dependency-analysis.md (Update 2025-10-12: Optional Extras).
