# Legacy Experiment Platform Master Requirements

## Cross-Cutting Expectations
- Preserve backward compatibility with legacy entry points while deferring to refactored `elspeth` packages whenever possible; imports and wrappers should avoid circular dependencies and keep cost low.
- Ensure logging, rate limiting, and Azure ML integrations stay opt-in, fail gracefully when unavailable, and remain safe for concurrent execution across CLI and orchestration paths.
- Keep all filesystem access read-only unless explicitly exporting artifacts, favouring UTF-8 encoding, deterministic ordering, and actionable error surfaces.

## `old/main.py` – Legacy CLI Bridge

### Bootstrapping & Compatibility
- `SRC_DIR` bootstrap: resolve the sibling `src/` directory at import time, append it to `sys.path` only when present, and keep the logic idempotent and platform agnostic so packaging scenarios stay unaffected.
- `StatsAnalyzer` fallback: try importing from `elspeth.stats`, automatically fall back to `experiment_stats.StatsAnalyzer`, expose the resolved symbol without noisy logging, and perform the resolution once per process.
- Compatibility wrappers (`load_configurations`, `validate_*`, `retry_with_backoff`): lazily import refactored implementations on demand, proxy arguments and return values unchanged, surface legacy exceptions, and avoid circular imports or unnecessary runtime cost.

### Logging, Context & Globals
- Logging defaults: call `logging.basicConfig` once per process (respecting existing handlers), expose a module logger via `getLogger(__name__)`, and keep logging usage lightweight and thread-safe.
- Azure ML context probing: attempt to import `azureml.core.Run`, set `azure_run` and `is_azure_ml` based on runtime context, swallow import/runtime errors silently, and run detection only once.
- Global orchestration handles (`safety_manager`, `audit_logger`, `devops_archiver`): expose module-level hooks, eagerly instantiate `AuditLogger`, default other hooks to `None`, support safe reassignment, and avoid heavy side effects during import.
- `cost_tracker` singleton: maintain a shared tracker instance for prompt/LLM cost, tolerate absent initialization, and stay thread-safe and reuse-friendly.

### Runtime Controls & Error Types
- Rate limiting (`rate_limiter`, `safe_rate_limit`): defer initialization to CLI wiring, raise explicit `RuntimeError` when invoked before setup, delegate to `rate_limiter.wait()` otherwise, and ensure messages help operators remediate misconfiguration.
- `LLMQueryError`: provide a lightweight exception derived from `Exception` to differentiate prompt/config retrieval failures without introducing extra state.

### Prompt & Configuration Utilities
- `load_prompts`: fetch prompt bundles through `elspeth.prompts` helpers, cache or clone as required, validate schema, and keep operations idempotent with clear error messaging.
- `parse_score`: normalize numeric scores (including string inputs), guard against malformed data, and raise informative errors without crashing the run.
- `format_user_prompt`: merge prompt templates with row data, respect token limits, log context sparingly, and keep formatting deterministic for tests.

### LLM Invocation & Execution Flow
- `query_llm`: enforce retry/backoff via the injected rate limiter, record token usage on `cost_tracker`, pass through safety/audit hooks, handle Azure vs. local execution, and continue processing rows after recoverable errors.
- `run_single_experiment_with_config`: adapt arguments to `elspeth.runner.execute_single_experiment_with_config`, run imports lazily, and return results unchanged.
- `run_single_experiment`: orchestrate prompt loading, Azure OpenAI client creation, per-call rate limiter (concurrency 1), row iteration with processing and querying hooks, error recording with ISO timestamps, result persistence, and ensure logging avoids sensitive data.
- `run_experiment_suite`: build Azure clients and execution context, swap in context-driven cost tracker, delegate to `execute_experiment_suite` with proper hooks, and preserve thread safety for shared globals.

### CLI Delegation
- `main`: lazily import `elspeth.cli.main` and forward execution/exit codes without side effects.
- `if __name__ == "__main__"` guard: ensure CLI runs only when invoked directly, keeping module safe for import by tooling and tests.

## `old/experiment_runner.py` – Legacy Suite Management

### Module Setup & Validation Schema
- Logger: expose a module-level logger that reuses caller configuration and works under concurrency.
- `ExperimentCheckpoint` import: keep optional checkpoint helpers importable so suite execution can reuse legacy checkpointing without hard dependency.
- `ExperimentConfigSchema` and `CONFIG_SCHEMA`: describe canonical experiment metadata (`name`, `description`, `temperature`, `max_tokens`, `enabled`, `is_baseline`, etc.) in both `TypedDict` and JSON schema form, staying synchronized and extensible.
- `validate_config`: call `jsonschema.validate` against `CONFIG_SCHEMA`, raising `jsonschema.ValidationError`, remaining deterministic, and avoiding extra copies.

### `ExperimentConfig` Model
- Initialization: load experiment folder metadata (`config.json`, optional `configurations.yaml`, prompt markdown files), validate configuration (translate schema errors to `ValueError`), collect semantic validation issues, and surface actionable messages while leaving disk untouched.
- Properties (`name`, `description`, `hypothesis`, `author`, `temperature`, `max_tokens`, `enabled`, `is_baseline`, `tags`, `expected_outcome`, `estimated_cost`): provide typed accessors with sensible defaults, enforce schema bounds (e.g., temperature 0–2), and ensure O(1) retrieval without mutation.
- Validation utilities: aggregate semantic issues via `validate()`, compute deterministic hashes via `stable_hash`, compare experiments with `differs_from`, and serialize full state via `to_dict` for reporting/export.

### Experiment Suite Orchestration
- Experiment discovery (`ExperimentSuite.__init__`, `_discover_experiments`): scan `experiments_root`, skip invalid folders, sort deterministically, instantiate `ExperimentConfig` objects, keep suite usable despite individual failures, and warn about baseline anomalies.
- Baseline management (`get_baseline`): return the configured baseline, fall back to the first experiment when absent, log decisions, and avoid mutating experiment state except when normalizing baseline flags.
- Preflight analysis (`preflight_check`): validate readiness (baseline presence, duplicate names, parameter sanity), estimate call volume/duration/cost for a configurable row count, and return structured diagnostics suitable for CLI reporting.
- Execution planning (`get_execution_order`): order baseline first and sort remaining experiments by `max_tokens` then `temperature`, preserving determinism and leaving the original list untouched.
- Azure ML telemetry (`log_metrics`, `log_experiment_comparison`): emit numeric metrics and comparison tables only when Azure ML contexts are active, ignore non-numeric values, and remain resilient to telemetry failures.
- Export & scaffolding (`export_configuration`, `create_experiment_template`, `get_summary`): serialize suite metadata to YAML/JSON with UTF-8 encoding, create experiment templates with appropriate defaults and logging, summarize suite statistics (cost, flags, tags), and avoid mutating existing configs.

## `old/experiment_stats.py` – Legacy Analytics Engine

### Module Foundations
- Optional dependency flags: probe for `sklearn` and `pingouin` at import time, capture availability via boolean flags, and never crash when libraries are missing.
- Logging & serialization: expose a module logger, implement `NumpyJSONEncoder` to translate NumPy types for JSON, and provide a lightweight `StatisticalResult` dataclass for structured test outputs.
- Core analyzer setup: define tuning constants (`CRITERIA_NAMES`, `SIGNIFICANCE_LEVEL`, `MIN_SAMPLES`, etc.), initialize `StatsAnalyzer` with experiment result dictionaries, detect or infer baselines, build eviction-aware caches, warn when fallbacks are used, and avoid deep copies to conserve memory.

### Data Preparation & Validation
- Score extraction pipeline (`extract_scores`, `_convert_scores`, `_get_paired_scores`, `_get_paired_scores_between`, `_extract_all_scores_from_result`): normalize raw experiment results, align paired samples deterministically, and guard against malformed or sparse data.
- Experiment validation (`validate_experiments`, `calculate_distribution_shift*`, `test_assumptions`): ensure experiments meet minimum sample thresholds, detect distribution drift batch-wise, verify statistical assumptions (normality, variance), and log issues without aborting analysis.
- Consistency inputs (`calculate_consistency`, `_calculate_icc`, `analyze_scoring_consistency`, `analyze_referee_alignment`, `_interpret_referee_alignment`): quantify agreement across raters/criteria, compute ICC/correlations safely, interpret alignment metrics, and tolerate partial data.

### Statistical Analysis & Effect Estimation
- Significance testing suite (`bayesian_comparison`, `_simple_bayesian`, `_interpret_bayesian`, `_safe_wilcoxon_test`, `calculate_cliffs_delta`, `ordinal_logistic_regression`, `calculate_statistical_power`, `required_sample_size`, `calculate_cohens_d_ci`, `_calculate_cohens_d`, `_interpret_cohens_d`, `_calculate_kl_divergence`, `_safe_correlation`): provide robust frequentist and Bayesian comparisons, effect sizes, power analyses, and correlation metrics with clear fallbacks when assumptions fail.
- Criteria and category insights (`analyze_practical_significance`, `_analyze_criteria_effects`, `analyze_category_effects`, `analyze_rationales`, `analyze_score_flips`, `analyze_context_effects`, `model_transformation`, `_calculate_r2`, `_interpret_transformation`): break down performance across criteria/categories, inspect rationale text, detect score flips, analyze context-driven shifts, and model transformations with interpretable summaries.
- Variant ranking (`determine_best_variant`, `_calculate_variant_score`, `generate_recommendations`, `_generate_recommendation`, `_safe_get_numeric`, `_get_basic_stats`, `_get_config_diff`): combine statistical significance, consistency, and configuration diffs to order variants, provide human-readable guidance, and retain deterministic scoring.

### Outlier & Distribution Insights
- Outlier detection (`identify_outliers`, `_create_outliers_dataframe`): surface top anomalous judgments per variant while handling missing data gracefully.
- Distribution metrics (`_calculate_distribution_metrics`, `_create_distribution_dataframe`, `_plot_distributions`, `_plot_mean_comparison`, `_plot_correlation_heatmap`, `_plot_effect_sizes`): compute distribution summaries, visualize score shapes, means, correlations, and effect sizes with consistent styling, and operate even when visualization backends are partially available.

### Reporting, Export & Visualization
- Report generation (`export_analysis_config`, `generate_failure_analysis_report`, `generate_all_reports`, `_generate_individual_stats`, `_generate_comparative_analysis`, `_generate_distribution_csv`, `_create_summary_dataframe`, `_create_advanced_statistics_dataframe`, `_create_statistical_tests_dataframe`, `_create_criteria_analysis_dataframe`): emit JSON, CSV, and DataFrame-backed artifacts summarizing results, with graceful degradation when data is insufficient.
- Excel & document exports (`_generate_excel_report`, `_write_excel_sheets_basic`, `_format_excel_workbook`, `_generate_executive_summary`): write Excel workbooks using preferred engines with openpyxl fallbacks, format sheets for readability, and create markdown executive summaries that highlight findings without leaking sensitive prompt content.
- Visualization pipeline (`_generate_visualizations`): compose composite PNG dashboards (violin plots, mean comparison, correlation heatmap, effect sizes), close figures to prevent leaks, and downgrade gracefully when dependencies or data are missing.
- Caching & performance (`_add_to_cache`, `calculate_distribution_shift_batch`): manage bounded-memory caches, batch expensive computations, and ensure repeated analyses remain performant.
