# Plugin Catalogue & Interface Matrix

All built-in plugins now receive a `PluginContext` instance during construction. The context carries the resolved security classification, provenance trail, and any parent metadata. Unless explicitly noted, each plugin inherits classification from configuration via this context and requires no further adjustments.

## Datasource Plugins

| Name | Implementation | Purpose | Notable Options | Context Status | Coverage |
| --- | --- | --- | --- | --- | --- |
| `azure_blob` | `src/elspeth/plugins/datasources/blob.py` | Load CSV data from Azure Blob Storage profiles. | `config_path`, `profile`, `pandas_kwargs`, `on_error`. | ✔ Inherits classification from context. | `tests/test_datasource_blob_plugin.py` |
| `csv_blob` | `src/elspeth/plugins/datasources/csv_blob.py` | Fetch CSV directly from blob URIs with retry-aware skips. | `path`, `dtype`, `encoding`, `on_error`. | ✔ Adds DataFrame `security_level` from context. | `tests/test_datasource_csv.py` |
| `local_csv` | `src/elspeth/plugins/datasources/csv_local.py` | Local filesystem CSV reader with skip-on-error mode. | `path`, `dtype`, `encoding`, `on_error`. | ✔ Propagates context level into DataFrame attrs. | `tests/test_datasource_csv.py` |

## LLM Clients

| Name | Implementation | Purpose | Notable Options | Context Status | Coverage |
| --- | --- | --- | --- | --- | --- |
| `azure_openai` | `src/elspeth/plugins/llms/azure_openai.py` | Azure-hosted OpenAI-compatible client. | `config`, `deployment`, `temperature`, `max_tokens`. | ✔ Context sets `security_level` attribute. | `tests/test_llm_azure.py` |
| `http_openai` | `src/elspeth/plugins/llms/openai_http.py` | Generic OpenAI HTTP client. | `api_base`, `api_key/_env`, `model`, `timeout`. | ✔ Context captured for policy enforcement. | `tests/test_llm_http_openai.py` |
| `mock` | `src/elspeth/plugins/llms/mock.py` | Deterministic mock LLM for suites/tests. | `seed`. | ✔ Context stored for downstream audits. | `tests/test_llm_mock.py` |
| `static_test` | `src/elspeth/plugins/llms/static.py` | Returns canned responses/metrics. | `content`, `score`, `metrics`. | ✔ Context attaches classification metadata. | `tests/test_llm_static_plugin.py` |

## LLM Middleware

| Name | Implementation | Purpose | Notable Options | Context Status | Coverage |
| --- | --- | --- | --- | --- | --- |
| `audit_logger` | `src/elspeth/plugins/llms/middleware.py` | Emit structured request/response logs. | `include_prompts`, `channel`. | ✔ Receives context; security-aware logging. | `tests/test_llm_middleware.py` |
| `prompt_shield` | same as above | Mask/abort on banned prompt terms. | `denied_terms`, `mask`, `on_violation`. | ✔ Context propagated. | `tests/test_llm_middleware.py` |
| `health_monitor` | same | Heartbeat telemetry and latency tracking. | `heartbeat_interval`, `stats_window`, `include_latency`. | ✔ Context carried into metrics. | `tests/test_llm_middleware.py` |
| `azure_content_safety` | same | Azure Content Safety screening. | `endpoint`, `key/_env`, `severity_threshold`, `on_violation`, `on_error`. | ✔ Context provides classification for audit logs. | `tests/test_llm_middleware.py` |
| `azure_environment` | `src/elspeth/plugins/llms/middleware_azure.py` | Azure ML run and telemetry integration. | `enable_run_logging`, `log_prompts`, `severity_threshold`, `on_error`. | ✔ Context controls logging classification. | `tests/test_llm_middleware.py` |

## Experiment Plugins

### Row-Level

| Name | Implementation | Purpose | Notable Options | Context Status | Coverage |
| --- | --- | --- | --- | --- | --- |
| `score_extractor` | `src/elspeth/plugins/experiments/metrics.py` | Pull scalar metrics from responses with threshold flagging. | `key`, `criteria`, `threshold`, `threshold_mode`. | ✔ Context passed (unused but available). | `tests/test_experiment_metrics_plugins.py` |
| `noop` | `src/elspeth/core/experiments/plugin_registry.py` | No-op row processing. | None. | ✔ Context applied. | Implicit via registry tests |

### Aggregators

| Name | Implementation | Purpose | Notable Options | Context Status | Coverage |
| --- | --- | --- | --- | --- | --- |
| `score_stats` | `src/elspeth/plugins/experiments/metrics.py` | Compute per-criterion statistics. | `source_field`, `flag_field`, `ddof`. | ✔ Context available. | `tests/test_experiment_metrics_plugins.py` |
| `score_recommendation` | same | Produce recommendation summary. | `thresholds`, `weighting` (per module). | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `score_variant_ranking` | same | Rank variants using aggregated scores. | `metric`, `order`, `top_n`. | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `score_agreement` | same | Agreement metrics across evaluators. | `threshold`, `required_votes`. | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `score_power` | same | Statistical power estimates. | `alpha`, `min_effect`, `min_samples`. | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `score_distribution` | same | Distribution summaries and histograms. | `bins`, `quantiles`. | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `prompt_variants` | `src/elspeth/plugins/experiments/prompt_variants.py` | Generate prompt alternatives via secondary LLM. | `prompt_template`, `variant_llm`, `count`, `max_attempts`. | ✔ Uses `create_llm_from_definition`. | `tests/test_prompt_variants_plugin.py` |
| `noop` | registry default | No aggregation. | None. | ✔ | Registry tests |

### Baseline Comparisons

| Name | Implementation | Purpose | Notable Options | Context Status | Coverage |
| --- | --- | --- | --- | --- | --- |
| `row_count` | `src/elspeth/core/experiments/plugin_registry.py` | Compare result row counts. | `key`. | ✔ | `tests/test_experiments.py` |
| `score_delta` | `src/elspeth/plugins/experiments/metrics.py` | Delta of chosen metric across criteria. | `metric`, `criteria`. | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `score_cliffs_delta` | same | Cliff’s delta effect size. | `criteria`, `min_samples`, `on_error`. | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `score_assumptions` | same | Normality/variance diagnostics. | `criteria`, `alpha`, `min_samples`, `on_error`. | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `score_significance` | same | Hypothesis test significance. | `criteria`, `alpha`, `alternative`. | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `score_practical` | same | Practical significance heuristics. | `threshold`, `criteria`. | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `score_bayes` | same | Bayesian comparison summary. | `credible_interval`, `min_samples`. | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `score_distribution` | same | Baseline distribution comparison. | `criteria`, `bins`. | ✔ | `tests/test_experiment_metrics_plugins.py` |
| `noop` | registry default | No comparison. | None. | ✔ | Registry tests |

### Validation Plugins

| Name | Implementation | Purpose | Notable Options | Context Status | Coverage |
| --- | --- | --- | --- | --- | --- |
| `regex_match` | `src/elspeth/plugins/experiments/validation.py` | Validate response with regex. | `pattern`, `flags`. | ✔ | `tests/test_validation_plugins.py` |
| `json` | same | Ensure JSON structure and optional object type. | `ensure_object`. | ✔ | `tests/test_validation_plugins.py` |
| `llm_guard` | same | Invoke secondary LLM for guardrail verdict. | `validator_llm` definition, prompt templates, tokens. | ✔ Uses context-aware LLM creation. | `tests/test_validation_plugins.py` |

### Early Stop

| Name | Implementation | Purpose | Notable Options | Context Status | Coverage |
| --- | --- | --- | --- | --- | --- |
| `threshold` | `src/elspeth/plugins/experiments/early_stop.py` | Signal when metric crosses threshold. | `metric`, `threshold`, `comparison`, `min_rows`, `label`. | ✔ Context passed to allow auditing. | `tests/test_suite_runner_integration.py` |

## Result Sinks

| Name | Implementation | Purpose | Notable Options | Context Status | Coverage |
| --- | --- | --- | --- | --- | --- |
| `analytics_report` | `src/elspeth/plugins/outputs/analytics_report.py` | Structured JSON/Markdown analytics. | `base_path`, `include_manifest`, `formats`. | ✔ Context drives artifact security. | `tests/test_outputs_analytics_report.py` |
| `analytics_visual` | `src/elspeth/plugins/outputs/visual_report.py` | Visual analytics (PNG/HTML). | `base_path`, `formats`, `dpi`, `figure_size`. | ✔ | `tests/test_outputs_visual.py` |
| `azure_blob` | `src/elspeth/plugins/outputs/blob.py` | Upload results to Azure Blob Storage. | `config_path`, `profile`, `path_template`, `include_manifest`, `credential`. | ✔ | `tests/test_outputs_blob.py` |
| `azure_devops_repo` | `src/elspeth/plugins/outputs/repository.py` | Commit artifacts into Azure DevOps repo. | Repo identifiers, `token_env`, `dry_run`. | ✔ | `tests/test_outputs_repo.py` |
| `csv` | `src/elspeth/plugins/outputs/csv_file.py` | Flat CSV export with sanitisation. | `path`, `sanitize_formulas`, `sanitize_guard`, `overwrite`. | ✔ | `tests/test_outputs_csv.py` |
| `excel_workbook` | `src/elspeth/plugins/outputs/excel.py` | Excel workbook export. | `base_path`, `timestamped`, `include_manifest`, `sanitize_formulas`. | ✔ | `tests/test_outputs_excel.py` |
| `file_copy` | `src/elspeth/plugins/outputs/file_copy.py` | Copy artifacts to filesystem destinations. | `destination`, `overwrite`. | ✔ | `tests/test_sink_chaining.py` |
| `github_repo` | `src/elspeth/plugins/outputs/repository.py` | Commit artifacts into GitHub repository. | `owner`, `repo`, `branch`, `token_env`, `dry_run`. | ✔ | `tests/test_outputs_repo.py` |
| `local_bundle` | `src/elspeth/plugins/outputs/local_bundle.py` | Create local JSON/CSV bundle directories. | `base_path`, `bundle_name`, `timestamped`, `write_json/csv`. | ✔ | `tests/test_outputs_local_bundle.py` |
| `signed_artifact` | `src/elspeth/plugins/outputs/signed.py` | Generate signed artifacts with manifest. | `base_path`, `bundle_name`, `key/_env`, `algorithm`, `on_error`. | ✔ | `tests/test_outputs_signed.py` |
| `zip_bundle` | `src/elspeth/plugins/outputs/zip_bundle.py` | Package results & manifests into zip. | `base_path`, `bundle_name`, `include_manifest`, `include_results`. | ✔ | `tests/test_outputs_archival.py` |

## Controls

| Kind | Name | Implementation | Purpose | Options | Context Status | Coverage |
| --- | --- | --- | --- | --- | --- | --- |
| Rate Limiter | `noop` | `src/elspeth/core/controls/registry.py` | Disable rate limiting. | None. | ✔ | `tests/test_controls.py` |
| Rate Limiter | `fixed_window` | `src/elspeth/core/controls/rate_limit.py` | Enforce request quota per window. | `requests`, `per_seconds`. | ✔ | `tests/test_controls.py` |
| Rate Limiter | `adaptive` | same | Adaptive throttling with token support. | `requests_per_minute`, `tokens_per_minute`, `interval_seconds`. | ✔ | `tests/test_controls.py` |
| Cost Tracker | `noop` | `src/elspeth/core/controls/cost_tracker.py` | Disable cost tracking. | None. | ✔ | `tests/test_controls.py` |
| Cost Tracker | `fixed_price` | same | Fixed-price usage accounting. | `prompt_token_price`, `completion_token_price`. | ✔ | `tests/test_controls.py` |

## Datasink & Middleware Security

- All plugins inherit the security classification resolved by configuration via `PluginContext.security_level`. No builtin plugin hardcodes a classification.
- Artifact generation and sink dependency resolution rely on the same classification to enforce “read-up” restrictions.
- Nested plugin builders (`create_llm_from_definition`, suite runner middleware sharing) ensure subcomponents coalesce parent/child levels consistently.

## Validation & Hardening

Plugin registrations remain schema-validated at instantiation time (`src/elspeth/core/registry.py`, `src/elspeth/core/experiments/plugin_registry.py`, `src/elspeth/core/controls/registry.py`). Harden deployments by importing only approved plugin modules before CLI invocation or by wrapping registries to limit the exposed keys.

## Proposed Plugin Backlog

The orchestrator can support workflows beyond LLM prompting and score aggregation. The following plugin concepts are candidates for development; all should adopt the context-aware factory signature from the outset.

| Type | Working Name | Purpose / Use Case | Key Configuration Ideas | Security Considerations | Status |
| --- | --- | --- | --- | --- | --- |
| Datasource | `sql_query` | Execute parameterised SQL against vetted warehouses to seed experiments with richer tabular data. | `connection_profile`, `query_template`, `parameters`, optional row-level security filter. | Run queries via read-only service accounts; use context level to enforce schema allowlists. | Proposed |
| Datasource | `api_batch` | Pull JSON batches from REST APIs for regression testing agents on live data. | `base_url`, per-endpoint `requests`, `auth_profile`, backoff policy. | Context level maps to API scopes; redact sensitive fields before caching. | Proposed |
| LLM Middleware | `prompt_hash_cache` | Deduplicate prompts/responses across suites to reduce cost; hash and persist by security tier. | `cache_backend`, `ttl`, `hash_fields`, `hit_policy`. | Separate caches per security level to avoid cross-tier leakage. | Proposed |
| LLM Middleware | `pii_scrubber` | Pre-scan prompts for PII/entities and mask before inference. Complements Content Safety with deterministic masking. | `detectors` (regex, ML), `mask_token`, `on_detection` (abort/mask/log). | Tie detector aggressiveness to `context.security_level`; log anonymised evidence only. | Proposed |
| Validation Plugin | `schema_guard` | Validate JSON responses against defined JSON Schema / Pydantic models for downstream automation. | `schema_ref`, `mode` (strict/coerce), `on_failure`. | Store schema per security class; avoid logging raw payloads on failure when marked sensitive. | Proposed |
| Row Plugin | `entity_enricher` | Call secondary knowledge APIs to enrich row context (e.g., domain facts) prior to evaluation. | `enrichment_sources`, `fields`, rate limits. | Use context to fence API keys and redact enriched data when exporting. | Proposed |
| Aggregation Plugin | `cost_summary` | Aggregate cost tracker outputs per experiment, including middleware call stats. | `metrics` (prompt/completion), `include_middlewares`. | Ensures cost visibility by security tier; no additional classification changes. | Proposed |
| Baseline Plugin | `variance_monitor` | Compare variance/volatility between baseline and variant scores to detect instability. | `criteria`, `min_samples`, `alert_threshold`. | Exposes only aggregate numbers; compatible with existing artifact policies. | Proposed |
| Early-Stop Plugin | `budget_guard` | Halt experiment when projected spend or elapsed runtime exceeds policy. | `max_cost`, `max_runtime`, binding to cost tracker context. | Reads cost tracker context; require matching security classification to prevent lower tier from observing higher-tier telemetry. | Proposed |
| Sink | `stream_forwarder` | Publish experiment events or aggregates to Kafka/Kinesis for near-real-time dashboards. | `stream_config`, `serialization` (JSON/Avro), `partition_key`. | Partition streams per security tier; encrypt payloads at rest. | Proposed |
| Sink | `notebook_bundle` | Generate Jupyter notebook artifacts summarising prompts, responses, metrics for human review. | `base_path`, `template_path`, `include_raw_prompts`. | Strip sensitive fields based on context before embedding into notebook. | Proposed |

These backlog items aim to extend the orchestrator into data integration, compliance, and operational observability scenarios. When implementing, ensure each follows the context-aware factory contract, declares schemas for validation, and registers targeted tests mirroring the existing plugin suites.

## Core Engine Extensions (Future Work)

To support broader security, audit, and reliability use cases, we can introduce additional “core” interfaces that sit alongside the current LLM clients while reusing the same context, middleware, and validation pipeline. These concepts should be tracked for future design spikes.

| Core Type | Working Name | Concept | Key Design Notes | Security & Audit Considerations | Status |
| --- | --- | --- | --- | --- | --- |
| Deterministic Transform | `data_transform_core` | Execute deterministic transformations (Pandas/Spark scripts, templated SQL) instead of free-form generations. | Define `TransformCoreProtocol` with a `transform(payload, metadata)` entry point; register via `registry._llms` equivalent or a new core registry. | Enforce read-only connections; log code fingerprints and versioning; respect context security when accessing data sources. | Future design |
| Policy Evaluation | `policy_engine_core` | Evaluate rules/OPA policies over experiment payloads to validate compliance scenarios. | Provide schema for rule bundles, policy modules, decision logs; enable middleware hooks for context injection. | Store policy digests with context; output decisions + rationale for audits. | Future design |
| Simulation / Scoring | `simulation_core` | Run Monte Carlo, financial scoring, or ML inference workloads in place of LLM calls. | Standardize input schema, cost metrics, and deterministic seed handling; integrate cost tracker for compute accounting. | Capture reproducible seeds, model digests; ensure sandboxed execution matching security level. | Future design |
| Workflow Automation | `action_core` | Trigger downstream systems (ticketing, remediation APIs) as part of orchestrated experiments. | Expose idempotent action interface with retry policy; require declarative runbooks/config. | Guard credentials via context; emit signed execution logs; maintain audit artifacts. | Future design |
| Hybrid Decision | `fallback_core` | Combine deterministic guards with LLMs (e.g., rule evaluation before calling model). | Middleware-controlled routing; allow context-driven decision of which core handles the payload. | Record routing decisions with provenance; ensure both branches respect classification. | Future design |

Each core extension should:

1. Define a protocol parallel to `LLMClientProtocol` (e.g., `TransformCoreProtocol`).
2. Register via registry modules with schema validation and context propagation.
3. Reuse the existing middleware, validation, and cost-tracking stack to guarantee auditability and consistent security controls.
4. Supply integration tests and sample configurations demonstrating non-LLM orchestration scenarios.
