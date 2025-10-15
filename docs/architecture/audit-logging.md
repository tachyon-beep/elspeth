# Audit Logging & Telemetry

## Logging Sources

- **CLI validation** – Configuration validation emits warnings for missing plugins or schema violations before execution begins, ensuring anomalies are captured in operator logs (`src/elspeth/cli.py:83`, `src/elspeth/core/validation.py:271`).[^audit-cli-2025-10-12]
<!-- UPDATE 2025-10-12: CLI validation citation refresh -->
Update 2025-10-12: Validation warnings are emitted during `_load_settings_from_args` at `src/elspeth/cli.py:369-380`.
<!-- END UPDATE -->
- **Experiment runner** – Row-level failures, retry exhaustion, and early-stop triggers are logged with structured metadata for later analysis (`src/elspeth/core/experiments/runner.py:223`, `src/elspeth/core/experiments/runner.py:584`, `src/elspeth/core/experiments/runner.py:575`).[^audit-runner-2025-10-12]
<!-- UPDATE 2025-10-12: Runner logging citation refresh -->
Update 2025-10-12: Failure and retry logs surface from `src/elspeth/core/experiments/runner.py:534-678`.
<!-- END UPDATE -->
- **Middleware telemetry** – Audit middleware logs request metadata (optionally including prompts), health monitoring emits rolling latency/failure metrics, and Azure environment middleware streams events to Azure ML run tables or standard logs (`src/elspeth/plugins/llms/middleware.py:70`, `src/elspeth/plugins/llms/middleware.py:124`, `src/elspeth/plugins/llms/middleware_azure.py:180`).[^audit-middleware-2025-10-12]
<!-- UPDATE 2025-10-12: Middleware module relocation -->
Update 2025-10-12: Middleware packages are housed in `src/elspeth/plugins/nodes/transforms/llm/middleware*.py`.
<!-- END UPDATE -->
- **Content safety** – Azure Content Safety violations and errors are surfaced with channelised warnings so SOC teams can filter on `elspeth.azure_content_safety` events (`src/elspeth/plugins/llms/middleware.py:232`).[^audit-content-safety-2025-10-12]
<!-- UPDATE 2025-10-12: Content safety module relocation -->
Update 2025-10-12: Azure content safety logging occurs in `src/elspeth/plugins/nodes/transforms/llm/middleware.py:297-320`.
<!-- END UPDATE -->
<!-- UPDATE 2025-10-12: Early-stop telemetry -->
- **Early-stop telemetry** – Early-stop plugins emit structured log records capturing trigger metrics and reasons alongside experiment metadata (`src/elspeth/core/experiments/runner.py:223`, `src/elspeth/plugins/experiments/early_stop.py:68`).
<!-- END UPDATE -->
<!-- Update 2025-10-12: Retry exhaustion logs include serialized attempt history and last error context via middleware callbacks, coordinating with Azure ML tables for alerting (`src/elspeth/core/experiments/runner.py:531`, `src/elspeth/plugins/llms/middleware_azure.py:233`). -->

### Update 2025-10-12: Retry Exhaustion Events

- Middleware `on_retry_exhausted` hooks capture attempt histories and errors for SOC alerting (`src/elspeth/core/experiments/runner.py:531`, `src/elspeth/plugins/llms/middleware_azure.py:233`).

### Update 2025-10-12: Middleware Telemetry

- Channel names (`elspeth.audit`, `elspeth.prompt_shield`, `elspeth.health`, `elspeth.azure_content_safety`) enable targeted SIEM filters; ensure handlers forward structured JSON payloads.

- **Retry summaries** – Result payloads include retry histories, exhausted counts, and attempt metrics that downstream sinks persist for forensic review (`src/elspeth/core/experiments/runner.py:177`, `src/elspeth/core/experiments/runner.py:534`).[^audit-retry-summary-2025-10-12]
<!-- UPDATE 2025-10-12: Retry summary citation refresh -->
Update 2025-10-12: Retry metadata is constructed at `src/elspeth/core/experiments/runner.py:187-214` and `src/elspeth/core/experiments/runner.py:547-676`.
<!-- END UPDATE -->
- **Cost reporting** – Cost trackers populate per-response metrics and run-level summaries, enabling cross-checking against vendor invoices (`src/elspeth/core/controls/cost_tracker.py:47`, `src/elspeth/core/experiments/runner.py:198`).[^audit-cost-2025-10-12]
- **Security classification** – Metadata exported with artifacts records the effective security level and sanitisation flags, informing downstream storage policies (`src/elspeth/core/experiments/runner.py:208`, `src/elspeth/plugins/outputs/csv_file.py:106`).[^audit-security-2025-10-12]
<!-- UPDATE 2025-10-12: CSV sink module relocation -->
Update 2025-10-12: CSV sink sanitisation metadata attaches at `src/elspeth/plugins/nodes/sinks/csv_file.py:95-123`.
<!-- END UPDATE -->
<!-- Update 2025-10-12: Visual analytics sink metadata captures chart inputs and pass rates for audit trails alongside PNG/HTML outputs (`src/elspeth/plugins/outputs/visual_report.py:182`). -->

### Update 2025-10-12: Visual Evidence Logging

- Visual analytics sinks log chart inputs, pass rates, and inline PNG data for auditors (`src/elspeth/plugins/outputs/visual_report.py:182`).
<!-- UPDATE 2025-10-12: Visual sink module relocation -->
Update 2025-10-12: Visual analytics artefact logging occurs in `src/elspeth/plugins/nodes/sinks/visual_report.py:115-199`.
<!-- END UPDATE -->

- **Azure ML integration** – When running inside Azure ML, middleware writes tables (`log_table`) and rows (`log_row`) containing experiment summaries, failures, and baseline comparisons for later retrieval via workspace diagnostics (`src/elspeth/plugins/llms/middleware_azure.py:208`, `src/elspeth/plugins/llms/middleware_azure.py:250`).[^audit-azureml-2025-10-12]
- **Repository manifests** – Dry-run payloads include manifest data that can be archived as audit evidence without committing to remote repositories (`src/elspeth/plugins/outputs/repository.py:70`, `src/elspeth/plugins/outputs/repository.py:135`).[^audit-repo-2025-10-12]
- **Signed bundles** – Signatures embed generated timestamps, cost summaries, and digests, providing tamper-evident audit artefacts ready for accreditation packages (`src/elspeth/plugins/outputs/signed.py:48`, `src/elspeth/plugins/outputs/signed.py:75`).[^audit-signed-2025-10-12]

### Update 2025-10-12: Azure Telemetry

- Azure ML run logging persists suite summaries, aggregates, and retry events for downstream workspace diagnostics (`src/elspeth/plugins/llms/middleware_azure.py:219`).

## Added 2025-10-12 – Suite Reporting Audit Trail

- **Report generation** – `SuiteReportGenerator` logs the consolidated output directory and writes validation/failure/comparative artefacts that should be hashed or signed for accreditation submissions (`src/elspeth/tools/reporting.py:31`, `src/elspeth/tools/reporting.py:138`, `src/elspeth/tools/reporting.py:207`).[^audit-suite-generator-2025-10-12]
<!-- UPDATE 2025-10-12: SuiteReportGenerator citation refresh -->
Update 2025-10-12: Suite reporting telemetry spans `src/elspeth/tools/reporting.py:26-199`.
<!-- END UPDATE -->
- **Export inventory** – CLI `--export-suite-config` and `--create-experiment-template` commands emit hydrated configuration artefacts; capture stdout/stderr and sign the exported files to maintain provenance (`src/elspeth/cli.py:137`, `src/elspeth/cli.py:201`).[^audit-suite-export-2025-10-12]
<!-- UPDATE 2025-10-12: Suite export citation refresh -->
Update 2025-10-12: Export/template options reside at `src/elspeth/cli.py:80-105` and suite reporting dispatch at `src/elspeth/cli.py:395-458`.
<!-- END UPDATE -->
- **Analytics artefacts** – Report sinks reuse analytics/visual/Excel plugins, so the resulting JSON/Markdown/PNG/XLSX outputs inherit retry/cost metadata and should be retained alongside run logs (`src/elspeth/plugins/outputs/analytics_report.py:69`, `src/elspeth/plugins/outputs/visual_report.py:205`, `src/elspeth/plugins/outputs/excel.py:134`).[^audit-suite-artifacts-2025-10-12]
<!-- UPDATE 2025-10-12: Output sink module relocation -->
Update 2025-10-12: Analytics, visual, and Excel sinks reside in `src/elspeth/plugins/nodes/sinks/`.
<!-- END UPDATE -->

## Operational Guidance

- Configure logging handlers to ship `elspeth.*` channels to central SIEM storage; the middleware channel names (`elspeth.audit`, `elspeth.prompt_shield`, `elspeth.azure_content_safety`, `elspeth.health`) are designed for targeted filters (`src/elspeth/plugins/llms/middleware.py:74`, `src/elspeth/plugins/llms/middleware.py:101`, `src/elspeth/plugins/llms/middleware.py:226`, `src/elspeth/plugins/llms/middleware.py:136`).
<!-- UPDATE 2025-10-12: Middleware module relocation -->
Update 2025-10-12: Channel constants live in `src/elspeth/plugins/nodes/transforms/llm/middleware.py` post namespace migration.
<!-- END UPDATE -->
- Maintain retention for retry histories and cost summaries, as these satisfy many accreditation evidence requirements (e.g., demonstrating adherence to rate-limit policies).
- When operating offline or in restricted environments, enable dry-run sinks and signed bundles to capture audit-friendly artefacts without contacting external services.

- **Azure ML run tables** – `AzureEnvironmentMiddleware` captures suite inventories, experiment summaries, baseline comparisons, and retry exhaustion events using `log_row/log_table`, creating an immutable evidence trail inside the workspace (`src/elspeth/plugins/llms/middleware_azure.py:219`, `src/elspeth/plugins/llms/middleware_azure.py:250`).[^audit-azure-run-2025-10-12]
- **Analytics reports** – The analytics sink serialises retry summaries, failure exemplars, cost totals, and baseline diffs into JSON/Markdown, allowing SOC teams to diff report metadata alongside raw artifacts (`src/elspeth/plugins/outputs/analytics_report.py:69`, `src/elspeth/plugins/outputs/analytics_report.py:116`).[^audit-analytics-2025-10-12]
- **Suite reporting pipeline** – CLI report generation writes validation results, failure analysis, and comparative insights to disk while logging each path; ensure those logs are ingested or signed when used for accreditation review (`src/elspeth/tools/reporting.py:53`, `src/elspeth/cli.py:258`).[^audit-suite-report-2025-10-12]

## Update History

- 2025-10-12 – Update 2025-10-12: Added suite reporting audit considerations covering CLI exports, analytics artefacts, and report generator logging.
- 2025-10-12 – Captured Azure telemetry enhancements, analytics report logging, and structured retry exhaustion evidence for accreditation logging requirements.
- 2025-10-12 – Update 2025-10-12: Added retry exhaustion, middleware telemetry, and visual evidence annotations with cross-document references.

[^audit-cli-2025-10-12]: Update 2025-10-12: CLI validation logging connects to docs/architecture/configuration-security.md.
[^audit-runner-2025-10-12]: Update 2025-10-12: Runner logging aligned with docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Retry, Early Stop, and Telemetry Flow).
[^audit-middleware-2025-10-12]: Update 2025-10-12: Middleware telemetry described in docs/architecture/security-controls.md (Update 2025-10-12: Middleware Safeguards).
[^audit-content-safety-2025-10-12]: Update 2025-10-12: Content safety controls catalogued in docs/architecture/security-controls.md.
[^audit-retry-summary-2025-10-12]: Update 2025-10-12: Retry metadata referenced in docs/architecture/architecture-overview.md (Update 2025-10-12: Concurrency, Checkpoints, and Retry Telemetry).
[^audit-cost-2025-10-12]: Update 2025-10-12: Cost summaries linked to docs/architecture/security-controls.md (Update 2025-10-12: Rate Limiting & Cost Controls).
[^audit-security-2025-10-12]: Update 2025-10-12: Security classification metadata tied to docs/architecture/security-controls.md (Update 2025-10-12: Artifact Clearance).
[^audit-azureml-2025-10-12]: Update 2025-10-12: Azure ML integration cross-referenced in docs/architecture/threat-surfaces.md (Update 2025-10-12: Azure Telemetry).
[^audit-repo-2025-10-12]: Update 2025-10-12: Repository manifests referenced in docs/architecture/threat-surfaces.md (Update 2025-10-12: Repository Interfaces).
[^audit-signed-2025-10-12]: Update 2025-10-12: Signed bundle evidence detailed in docs/architecture/security-controls.md (Update 2025-10-12: Artifact Signing).
[^audit-azure-run-2025-10-12]: Update 2025-10-12: Azure run tables align with docs/architecture/threat-surfaces.md (Update 2025-10-12: Azure ML run logging).
[^audit-analytics-2025-10-12]: Update 2025-10-12: Analytics report telemetry linked to docs/reporting-and-suite-management.md (Update 2025-10-12: Analytics Outputs).
[^audit-suite-report-2025-10-12]: Update 2025-10-12: Suite reporting pipeline logging documented in docs/reporting-and-suite-management.md (Update 2025-10-12: Suite Report Generator).
[^audit-suite-generator-2025-10-12]: Update 2025-10-12: Report generator evidence captured in docs/architecture/component-diagram.md (Update 2025-10-12: Suite reporting outputs).
[^audit-suite-export-2025-10-12]: Update 2025-10-12: Export tooling guidance cross-referenced in docs/architecture/configuration-security.md (Update 2025-10-12: Suite Management & Export Pathing).
[^audit-suite-artifacts-2025-10-12]: Update 2025-10-12: Artefact retention guidance linked to docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Suite Reporting Export Flow).
