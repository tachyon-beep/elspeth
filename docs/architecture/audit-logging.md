# Audit Logging & Telemetry

## Logging Sources
- **CLI validation** – Configuration validation emits warnings for missing plugins or schema violations before execution begins, ensuring anomalies are captured in operator logs (`src/elspeth/cli.py:83`, `src/elspeth/core/validation.py:271`).
- **Experiment runner** – Row-level failures, retry exhaustion, and early-stop triggers are logged with structured metadata for later analysis (`src/elspeth/core/experiments/runner.py:223`, `src/elspeth/core/experiments/runner.py:584`, `src/elspeth/core/experiments/runner.py:575`).
- **Middleware telemetry** – Audit middleware logs request metadata (optionally including prompts), health monitoring emits rolling latency/failure metrics, and Azure environment middleware streams events to Azure ML run tables or standard logs (`src/elspeth/plugins/llms/middleware.py:70`, `src/elspeth/plugins/llms/middleware.py:124`, `src/elspeth/plugins/llms/middleware_azure.py:180`).
- **Content safety** – Azure Content Safety violations and errors are surfaced with channelised warnings so SOC teams can filter on `elspeth.azure_content_safety` events (`src/elspeth/plugins/llms/middleware.py:232`).
<!-- UPDATE 2025-10-12: Retry exhaustion logs include serialized attempt history and last error context via middleware callbacks, coordinating with Azure ML tables for alerting (`src/elspeth/core/experiments/runner.py:531`, `src/elspeth/plugins/llms/middleware_azure.py:233`). -->

## Artifact-level Metadata
- **Retry summaries** – Result payloads include retry histories, exhausted counts, and attempt metrics that downstream sinks persist for forensic review (`src/elspeth/core/experiments/runner.py:177`, `src/elspeth/core/experiments/runner.py:534`).
- **Cost reporting** – Cost trackers populate per-response metrics and run-level summaries, enabling cross-checking against vendor invoices (`src/elspeth/core/controls/cost_tracker.py:47`, `src/elspeth/core/experiments/runner.py:198`).
- **Security classification** – Metadata exported with artifacts records the effective security level and sanitisation flags, informing downstream storage policies (`src/elspeth/core/experiments/runner.py:208`, `src/elspeth/plugins/outputs/csv_file.py:106`).
<!-- UPDATE 2025-10-12: Visual analytics sink metadata captures chart inputs and pass rates for audit trails alongside PNG/HTML outputs (`src/elspeth/plugins/outputs/visual_report.py:182`). -->

## External Telemetry Channels
- **Azure ML integration** – When running inside Azure ML, middleware writes tables (`log_table`) and rows (`log_row`) containing experiment summaries, failures, and baseline comparisons for later retrieval via workspace diagnostics (`src/elspeth/plugins/llms/middleware_azure.py:208`, `src/elspeth/plugins/llms/middleware_azure.py:250`).
- **Repository manifests** – Dry-run payloads include manifest data that can be archived as audit evidence without committing to remote repositories (`src/elspeth/plugins/outputs/repository.py:70`, `src/elspeth/plugins/outputs/repository.py:135`).
- **Signed bundles** – Signatures embed generated timestamps, cost summaries, and digests, providing tamper-evident audit artefacts ready for accreditation packages (`src/elspeth/plugins/outputs/signed.py:48`, `src/elspeth/plugins/outputs/signed.py:75`).

## Operational Guidance
- Configure logging handlers to ship `elspeth.*` channels to central SIEM storage; the middleware channel names (`elspeth.audit`, `elspeth.prompt_shield`, `elspeth.azure_content_safety`, `elspeth.health`) are designed for targeted filters (`src/elspeth/plugins/llms/middleware.py:74`, `src/elspeth/plugins/llms/middleware.py:101`, `src/elspeth/plugins/llms/middleware.py:226`, `src/elspeth/plugins/llms/middleware.py:136`).
- Maintain retention for retry histories and cost summaries, as these satisfy many accreditation evidence requirements (e.g., demonstrating adherence to rate-limit policies).
- When operating offline or in restricted environments, enable dry-run sinks and signed bundles to capture audit-friendly artefacts without contacting external services.

## Added 2025-10-12 – Extended Telemetry Streams
- **Azure ML run tables** – `AzureEnvironmentMiddleware` captures suite inventories, experiment summaries, baseline comparisons, and retry exhaustion events using `log_row/log_table`, creating an immutable evidence trail inside the workspace (`src/elspeth/plugins/llms/middleware_azure.py:219`, `src/elspeth/plugins/llms/middleware_azure.py:250`).
- **Analytics reports** – The analytics sink serialises retry summaries, failure exemplars, cost totals, and baseline diffs into JSON/Markdown, allowing SOC teams to diff report metadata alongside raw artifacts (`src/elspeth/plugins/outputs/analytics_report.py:69`, `src/elspeth/plugins/outputs/analytics_report.py:116`).
- **Suite reporting pipeline** – CLI report generation writes validation results, failure analysis, and comparative insights to disk while logging each path; ensure those logs are ingested or signed when used for accreditation review (`src/elspeth/tools/reporting.py:53`, `src/elspeth/cli.py:258`).

## Update History
- 2025-10-12 – Captured Azure telemetry enhancements, analytics report logging, and structured retry exhaustion evidence for accreditation logging requirements.
