# ELSPETH Architecture Overview

## Core Principles

- **Defense by design** – All external integrations are fronted by typed protocols so untrusted components can be swapped without touching orchestration logic (`src/elspeth/core/interfaces.py:11`, `src/elspeth/core/interfaces.py:22`, `src/elspeth/core/interfaces.py:37`).[^defense-2025-10-12]
- **Configuration as code** – Profiles are hydrated through validated YAML and merged prompt packs, preventing runtime surprises and enabling fail-fast feedback (`src/elspeth/config.py:41`, `src/elspeth/core/validation.py:271`, `src/elspeth/core/validation.py:1012`).[^config-2025-10-12]
- **Traceable execution** – The orchestrator records retries, aggregates, costs, and security classifications on every run so sinks and auditors receive consistent metadata (`src/elspeth/core/experiments/runner.py:162`, `src/elspeth/core/experiments/runner.py:198`, `src/elspeth/core/experiments/runner.py:218`).[^trace-2025-10-12]
<!-- UPDATE 2025-10-12: Trace metadata now includes `retry_summary`, `cost_summary`, and `early_stop` payloads surfaced to sinks and middleware via `src/elspeth/core/experiments/runner.py:176`, `src/elspeth/core/experiments/runner.py:198`, `src/elspeth/core/experiments/runner.py:212`. -->
- **Least privilege propagation** – Data, middleware, and artifact flows carry explicit security levels allowing downstream sinks to enforce clearance before consuming artifacts (`src/elspeth/core/security/__init__.py:14`, `src/elspeth/core/experiments/runner.py:208`, `src/elspeth/core/artifact_pipeline.py:192`).[^least-privilege-2025-10-12]

## Component Layers

- **Ingress** – Datasources load tabular experiments, tagging each frame with its classification. Local CSV, CSV-blob stand-ins, and Azure blob sources all normalize security levels and support `on_error` policies (`src/elspeth/plugins/datasources/csv_local.py:17`, `src/elspeth/plugins/datasources/csv_blob.py:17`, `src/elspeth/plugins/datasources/blob.py:17`).[^ingress-2025-10-12]
- **Configuration Loader** – Profiles compose datasource/LLM/sink stacks, merge prompt packs, and resolve suite defaults before instantiating runtime dependencies (`src/elspeth/config.py:52`, `src/elspeth/config.py:78`, `src/elspeth/config.py:121`).[^config-loader-2025-10-12]
- **Orchestrator** – Binds a datasource, LLM client, sinks, and optional rate/cost/validation plugins into a cohesive experiment with shared middleware and retry settings (`src/elspeth/core/orchestrator.py:43`, `src/elspeth/core/orchestrator.py:80`).[^orchestrator-2025-10-12]
- **Experiment Runner** – Compiles prompts with strict rendering, enforces per-row middleware chains, handles concurrency, retries, validation plugins, and aggregates before dispatching results into the artifact pipeline (`src/elspeth/core/experiments/runner.py:65`, `src/elspeth/core/experiments/runner.py:126`, `src/elspeth/core/experiments/runner.py:464`).[^runner-2025-10-12]
- **Artifact Pipeline** – Orders sinks by declared dependencies, enforces security clearances, and allows chaining of produced artifacts (CSV, signed bundles, repo uploads) for downstream consumers (`src/elspeth/core/artifact_pipeline.py:153`, `src/elspeth/core/artifact_pipeline.py:192`, `src/elspeth/core/artifact_pipeline.py:218`).[^pipeline-2025-10-12]
- **Plugin Controls** – Rate limiting and cost tracking are pluggable, with schema validation guarding misconfiguration and adaptive logic that tracks both requests and token budgets (`src/elspeth/core/controls/registry.py:36`, `src/elspeth/core/controls/rate_limit.py:104`, `src/elspeth/core/controls/cost_tracker.py:36`).[^controls-2025-10-12]
<!-- UPDATE 2025-10-12: Plugin registries also normalise baseline comparison and early-stop definitions; see `src/elspeth/core/experiments/plugin_registry.py:34` and `src/elspeth/core/experiments/plugin_registry.py:142` for baseline/early-stop creation paths. -->

## Security Posture Highlights

- **Prompt hygiene** – Prompts render through a `StrictUndefined` Jinja environment and raise explicit errors when required fields are missing (`src/elspeth/core/prompts/engine.py:33`, `src/elspeth/core/prompts/template.py:24`).[^prompt-hygiene-2025-10-12]
- **Middleware stack** – Request/response middlewares apply audit logging, prompt shielding, Azure Content Safety scans, health telemetry, and Azure ML run reporting without modifying the core runner (`src/elspeth/plugins/llms/middleware.py:70`, `src/elspeth/plugins/llms/middleware.py:124`, `src/elspeth/plugins/llms/middleware.py:206`, `src/elspeth/plugins/llms/middleware_azure.py:76`).[^middleware-2025-10-12]
- **Output sanitisation and signing** – Spreadsheet guards neutralise leading formula characters, while signed bundles embed HMAC manifests for tamper evidence (`src/elspeth/plugins/outputs/csv_file.py:49`, `src/elspeth/plugins/outputs/_sanitize.py:18`, `src/elspeth/plugins/outputs/signed.py:37`).[^sanitisation-2025-10-12]
- **Suite-level governance** – Suite runners merge defaults, instantiate experiment-specific sink stacks, and notify shared middleware about lifecycle events, ensuring telemetry and baseline comparisons stay consistent (`src/elspeth/core/experiments/suite_runner.py:35`, `src/elspeth/core/experiments/suite_runner.py:118`, `src/elspeth/core/experiments/suite_runner.py:208`).[^suite-governance-2025-10-12]
<!-- UPDATE 2025-10-12: Suite governance now emits baseline comparison payloads and retry/early-stop telemetry to middleware hooks (`src/elspeth/core/experiments/suite_runner.py:302`, `src/elspeth/plugins/llms/middleware_azure.py:208`). -->

Update 2025-10-12: Concurrency, Checkpoints, and Retry Telemetry — See docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Parallel Execution Gate) for sequence diagrams.

## Added 2025-10-12 – Concurrency, Checkpoints, and Retry Telemetry

- **Threaded execution controls** – `ExperimentRunner` evaluates `concurrency_config.enabled`, `max_workers`, `backlog_threshold`, and utilisation pause settings to decide whether to launch a `ThreadPoolExecutor` while honouring rate limiter saturation (`src/elspeth/core/experiments/runner.py:365`, `src/elspeth/core/experiments/runner.py:392`, `src/elspeth/core/controls/rate_limit.py:118`).[^concurrency-2025-10-12]
- **Checkpoint recovery** – Runs that provide `checkpoint_config.path` and `checkpoint_config.field` skip previously processed identifiers and append progress incrementally, minimising replays during resumptions (`src/elspeth/core/experiments/runner.py:75`, `src/elspeth/core/experiments/runner.py:280`).[^checkpoint-2025-10-12]
- **Structured retry history** – Successful rows surface retry attempts under `record["retry"]`, while exhausted failures capture `history`, `attempts`, and `error_type` for sinks and telemetry middleware (`src/elspeth/core/experiments/runner.py:170`, `src/elspeth/core/experiments/runner.py:214`, `src/elspeth/plugins/llms/middleware_azure.py:233`).[^retry-2025-10-12]
- **Cost/usage summaries** – Cost trackers contribute aggregated totals in `payload["cost_summary"]`, enabling downstream sinks (e.g., analytics, signing manifests) to embed spend metadata for auditors (`src/elspeth/core/experiments/runner.py:198`, `src/elspeth/plugins/outputs/signed.py:58`).[^cost-2025-10-12]
<!-- UPDATE 2025-10-12: Retry exhaustion notifications captured below ensure telemetry parity across middleware. -->
- **Retry exhaustion hooks** – `_notify_retry_exhausted` publishes the final attempt metadata to loggers and middleware `on_retry_exhausted` handlers, ensuring Azure telemetry captures failure context for accreditation review (`src/elspeth/core/experiments/runner.py:520`, `src/elspeth/plugins/llms/middleware_azure.py:233`). <!-- UPDATE 2025-10-12: Highlights structured failure reporting requested by security reviewers. -->

Update 2025-10-12: Early Stop and Baseline Analytics — Refer to docs/architecture/plugin-security-model.md (Update 2025-10-12: Early-Stop Lifecycle) and docs/architecture/audit-logging.md (Update 2025-10-12: Baseline Diff Logging) for complementary details.

## Added 2025-10-12 – Early Stop and Baseline Analytics

- **Early-stop lifecycle** – The runner initialises declared early-stop plugins, sharing retry and metric metadata per row; when a plugin triggers it records `metadata["early_stop"]` and halts queue submission, keeping failure windows tight (`src/elspeth/core/experiments/runner.py:223`, `src/elspeth/core/experiments/runner.py:248`, `src/elspeth/plugins/experiments/early_stop.py:17`).[^early-stop-2025-10-12]
- **Baseline comparisons** – Suite execution now invokes baseline comparison plugins after each variant, attaching structured diffs at `payload["baseline_comparison"]` for sinks and middleware consumers (`src/elspeth/core/experiments/suite_runner.py:304`, `src/elspeth/core/experiments/plugin_registry.py:158`).[^baseline-2025-10-12]
- **Analytics sinks** – `AnalyticsReportSink` materialises JSON/Markdown summaries of aggregates, failures, retry data, and baseline comparisons, providing accreditation-ready reports without replacing existing sinks (`src/elspeth/plugins/outputs/analytics_report.py:11`, `src/elspeth/plugins/outputs/analytics_report.py:69`).[^analytics-2025-10-12]
- **Visual analytics sink** – `VisualAnalyticsSink` converts score statistics into PNG/HTML artifacts using optional plotting libraries, embedding retry/cost metadata for reviewers (`src/elspeth/plugins/outputs/visual_report.py:11`, `src/elspeth/plugins/outputs/visual_report.py:63`).[^visual-2025-10-12]
- **Suite reporting pipeline** – `SuiteReportGenerator` drives consolidated artifacts (comparative analysis, recommendations, validation exports) when CLI callers pass `--reports-dir`, reusing experiment payloads while preserving run metadata (`src/elspeth/tools/reporting.py:19`, `src/elspeth/cli.py:266`).[^suite-report-2025-10-12]
<!-- UPDATE 2025-10-12: Suite report generation dispatch currently lives at `src/elspeth/cli.py:392`; retain historical reference while newer line numbers propagate through annexes. -->

## Added 2025-10-12 – Metrics and Statistical Plugins

- **Score extraction and thresholding** – `ScoreExtractorPlugin` normalises numeric responses, flags threshold breaches, and emits structured metrics for sinks and analytics reports (`src/elspeth/plugins/experiments/metrics.py:63`, `src/elspeth/plugins/experiments/metrics.py:113`). <!-- UPDATE 2025-10-12: Establishes provenance for row-level scoring data reviewed during security accreditation. -->
- **Statistical aggregators** – Aggregation plugins such as `score_stats`, `score_significance`, and `score_distribution` compute descriptive statistics, hypothesis tests, and drift checks backing Suite and analytics outputs (`src/elspeth/plugins/experiments/metrics.py:146`, `src/elspeth/plugins/experiments/metrics.py:214`, `src/elspeth/plugins/experiments/metrics.py:268`). <!-- UPDATE 2025-10-12: Documents how statistical claims in reports tie back to code. -->
- **Agreement and planning analysis** – Optional extras (`stats-agreement`, `stats-planning`) introduce inter-rater agreement, power analysis, and planning utilities, each schema-validated to prevent unsafe runtime options (`src/elspeth/plugins/experiments/metrics.py:238`, `src/elspeth/plugins/experiments/metrics.py:312`). <!-- UPDATE 2025-10-12: Captures configuration controls when enabling advanced analytics paths. -->
- **Bayesian and baseline comparisons** – Bayesian score aggregators and delta plugins (`score_bayesian`, `score_delta`) quantify posterior intervals and baseline variance, supplying structured diffs to analytics and Suite reports (`src/elspeth/plugins/experiments/metrics.py:280`, `src/elspeth/plugins/experiments/metrics.py:338`). <!-- UPDATE 2025-10-12: Adds traceability for probabilistic comparison features introduced post original draft. -->

Update 2025-10-12: Artifact Chaining and Classification Guarantees — Additional visuals in docs/architecture/component-diagram.md (Update 2025-10-12: Artifact Pipeline) highlight dependency edges.

## Added 2025-10-12 – Artifact Chaining and Classification Guarantees

- **Artifact descriptors** – Sinks declare produced artifacts (type, alias, persistence) and consume upstream tokens via `ArtifactDescriptor` and `ArtifactRequestParser`, enabling DAG-style execution without breaking existing single-sink flows (`src/elspeth/core/interfaces.py:37`, `src/elspeth/core/artifact_pipeline.py:137`).[^artifact-descriptors-2025-10-12]
- **Security-level enforcement** – The pipeline normalises sink clearances and rejects dependency resolutions that would downgrade data, ensuring classification never escalates silently (`src/elspeth/core/artifact_pipeline.py:167`, `src/elspeth/core/artifact_pipeline.py:205`, `src/elspeth/core/security/__init__.py:27`).[^security-enforcement-2025-10-12]
- **Reusable artifacts** – Downstream sinks (e.g., `file_copy`, `zip_bundle`, Azure blob) can request `file/*` or aliased artifacts, and sanitisation metadata rides alongside to maintain audit provenance (`src/elspeth/plugins/outputs/csv_file.py:102`, `src/elspeth/plugins/outputs/blob.py:208`).[^reusable-artifacts-2025-10-12]
- **Visual evidence** – Chart artifacts produced by the visual analytics sink inherit security levels and include inline summary tables for audits, while HTML outputs embed base64 PNG data to avoid external links (`src/elspeth/plugins/outputs/visual_report.py:153`, `src/elspeth/plugins/outputs/visual_report.py:255`).[^visual-evidence-2025-10-12]
<!-- UPDATE 2025-10-12: Excel, file copy, local bundle, and zip sinks (`src/elspeth/plugins/outputs/excel.py`, `src/elspeth/plugins/outputs/file_copy.py`, `src/elspeth/plugins/outputs/local_bundle.py`, `src/elspeth/plugins/outputs/zip_bundle.py`) consume these artifacts to package sanitised datasets, manifests, and signed bundles for downstream accreditation workflows. -->

## Areas to Monitor

- **Credential sources** – Azure, GitHub, DevOps, and signing sinks rely on environment-provided secrets; ensure deployment pipelines inject these via secure stores rather than committed config (`src/elspeth/plugins/outputs/blob.py:187`, `src/elspeth/plugins/outputs/repository.py:149`, `src/elspeth/plugins/outputs/signed.py:107`).
- **Optional extras** – Statistical and Excel extras pull in additional scientific libraries; pinning and vulnerability monitoring should accompany their use (`pyproject.toml:25`).
- **Network middleware** – Azure Content Safety and repository sinks make outbound HTTP calls; configure outbound firewall rules and timeouts appropriately (`src/elspeth/plugins/llms/middleware.py:249`, `src/elspeth/plugins/outputs/repository.py:106`).

## Update History

- 2025-10-12 – Documented concurrency controls, retry/early-stop telemetry, analytics reporting surfaces, and artifact dependency enforcement for accreditation traceability.
- 2025-10-12 – Update 2025-10-12: Added footnoted cross-references to component, data-flow, security, and logging documentation; reviewers should confirm regression coverage via `tests/test_reporting.py`, `tests/test_outputs_visual.py`, and `tests/test_integration_visual_suite.py`.
- 2025-10-12 – Update 2025-10-12: Captured metrics plugin inventory, suite reporting CLI relocation, retry exhaustion hooks, and chained sink consumers to align documentation with current codebase.

[^defense-2025-10-12]: Update 2025-10-12: Cross-referenced in docs/architecture/component-diagram.md (Update 2025-10-12: System Interfaces) to ensure protocol coverage matches registry factories.
[^config-2025-10-12]: Update 2025-10-12: Aligns with docs/architecture/configuration-security.md (Update 2025-10-12: Profile Validation Chain) for schema-validated configuration paths.
[^trace-2025-10-12]: Update 2025-10-12: Linked to docs/architecture/audit-logging.md (Update 2025-10-12: Retry Summaries) to confirm metadata propagation into telemetry.
[^least-privilege-2025-10-12]: Update 2025-10-12: Refer to docs/architecture/security-controls.md (Update 2025-10-12: Clearance Enforcement) for control mappings.
[^ingress-2025-10-12]: Update 2025-10-12: Detailed datasource alignment in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Ingress Classification Flow).
[^config-loader-2025-10-12]: Update 2025-10-12: Configuration merge paths illustrated in docs/architecture/component-diagram.md (Update 2025-10-12: Configuration Loader).
[^orchestrator-2025-10-12]: Update 2025-10-12: Orchestrator bindings mapped in docs/architecture/component-diagram.md (Update 2025-10-12: Orchestrator Core) and docs/architecture/plugin-security-model.md (Update 2025-10-12: Binding Lifecycle).
[^runner-2025-10-12]: Update 2025-10-12: Execution stages elaborated in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Runner Pipeline).
[^pipeline-2025-10-12]: Update 2025-10-12: Artifact dependency DAGs rendered in docs/architecture/component-diagram.md (Update 2025-10-12: Artifact Pipeline).
[^controls-2025-10-12]: Update 2025-10-12: Rate/cost control validation paths tied to docs/architecture/plugin-security-model.md (Update 2025-10-12: Control Registry).
[^prompt-hygiene-2025-10-12]: Update 2025-10-12: Prompt sanitation safeguards annotated in docs/architecture/security-controls.md (Update 2025-10-12: Prompt Hygiene).
[^middleware-2025-10-12]: Update 2025-10-12: Middleware chain sequencing shown in docs/architecture/component-diagram.md (Update 2025-10-12: Middleware Chain) and telemetry coverage in docs/architecture/audit-logging.md (Update 2025-10-12: Middleware Telemetry).
[^sanitisation-2025-10-12]: Update 2025-10-12: Sanitisation controls cross-referenced in docs/architecture/security-controls.md (Update 2025-10-12: Output Sanitisation) and docs/architecture/CONTROL_INVENTORY.md (Update 2025-10-12: Sanitisation Controls).
[^suite-governance-2025-10-12]: Update 2025-10-12: Suite lifecycle alignment described in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Suite Lifecycle) and docs/reporting-and-suite-management.md.
[^concurrency-2025-10-12]: Update 2025-10-12: Concurrency decision tree diagrammed in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Parallel Execution Gate).
[^checkpoint-2025-10-12]: Update 2025-10-12: Checkpoint resume flows covered in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Checkpoint Loop).
[^retry-2025-10-12]: Update 2025-10-12: Retry instrumentation tied to docs/architecture/audit-logging.md (Update 2025-10-12: Retry Exhaustion Events).
[^cost-2025-10-12]: Update 2025-10-12: Cost propagation linked to docs/architecture/dependency-analysis.md (Update 2025-10-12: Cost Tracker Dependencies).
[^early-stop-2025-10-12]: Update 2025-10-12: Early-stop plugin lifecycle mapped in docs/architecture/plugin-security-model.md (Update 2025-10-12: Early-Stop Lifecycle).
[^baseline-2025-10-12]: Update 2025-10-12: Baseline comparison outputs referenced in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Baseline Evaluation).
[^analytics-2025-10-12]: Update 2025-10-12: Analytics sinks catalogued in docs/reporting-and-suite-management.md (Update 2025-10-12: Analytics Outputs).
[^visual-2025-10-12]: Update 2025-10-12: Visual sink artefacts referenced in docs/examples_colour_animals.md (Update 2025-10-12: Visual Analytics Usage).
[^suite-report-2025-10-12]: Update 2025-10-12: Suite reporting cross-referenced in docs/reporting-and-suite-management.md (Update 2025-10-12: Suite Report Generator).
[^artifact-descriptors-2025-10-12]: Update 2025-10-12: Artifact descriptor requirements shown in docs/architecture/component-diagram.md (Update 2025-10-12: Artifact Tokens).
[^security-enforcement-2025-10-12]: Update 2025-10-12: Security enforcement control listed in docs/architecture/security-controls.md (Update 2025-10-12: Artifact Clearance).
[^reusable-artifacts-2025-10-12]: Update 2025-10-12: Reuse patterns detailed in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Artifact Rehydration).
[^visual-evidence-2025-10-12]: Update 2025-10-12: Visual analytics evidence retention summarised in docs/architecture/audit-logging.md (Update 2025-10-12: Visual Evidence Logging).
