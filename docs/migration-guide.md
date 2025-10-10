# Migration Guide: Legacy Stack → Plugin Architecture

This guide helps teams upgrade from the legacy `old/` implementation to the modern plugin-driven ELSPETH.

## Prerequisites
- Python 3.12+
- `pip install -e .[dev]` to pull dependencies.
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
- Sample configuration: `config/sample_suite/` demonstrates early stop, analytics, and reporting sinks.

## Azure-Specific Features
- **Azure ML telemetry**: Use `azure_environment` middleware in specific experiments or suite defaults. Set `on_error` to `skip` for local runs.
- **Azure DevOps repository sink**: Add `azure_devops_repo` to sinks with organization/project/repository options. Works best with `--live-outputs`.
- **Content Safety**: Set `AZURE_CONTENT_SAFETY_ENDPOINT` and `AZURE_CONTENT_SAFETY_KEY` env variables for middleware to authenticate.

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

## Support Channels
- Run `elspeth list plugins` (future enhancement) or browse `src/elspeth/plugins/` for available plugins.
- Unit tests in `tests/` illustrate configuration patterns and middleware/sink behavior.
