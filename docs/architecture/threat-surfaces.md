# Threat Surfaces & Trust Boundaries

## Trust Zones
- **Operator Zone** – Local CLI execution validates configuration before any network activity, acting as the first guard against malformed profiles (`src/elspeth/cli.py:83`, `src/elspeth/core/validation/settings.py and src/elspeth/core/validation/suite.py`).[^threat-operator-2025-10-12]
<!-- UPDATE 2025-10-12: CLI validation citation refresh -->
Update 2025-10-12: Configuration validation warnings surface at `src/elspeth/cli.py:369-380`.
<!-- END UPDATE -->
- **Core Orchestrator Zone** – Trusted runtime processes data in memory, applies middleware, and enforces retry logic; tampering here would require code execution on the host (`src/elspeth/core/orchestrator.py:43`, `src/elspeth/core/experiments/runner.py:65`).[^threat-orchestrator-2025-10-12]
- **Plugin Zone** – Pluggable datasources, LLM clients, sinks, and experiment plugins sit at the boundary of trusted code and external services; schema validation and runtime guards constrain their behaviour (`src/elspeth/core/registries/__init__.py:91`, `src/elspeth/core/experiments/plugin_registry.py:93`).[^threat-plugin-2025-10-12]
- **External Service Zone** – Azure storage, Azure/OpenAI endpoints, and repository APIs operate outside ELSPETH’s control and are treated as untrusted data producers/consumers (`src/elspeth/datasources/blob_store.py:200`, `src/elspeth/plugins/llms/azure_openai.py:77`, `src/elspeth/plugins/outputs/repository.py:124`).[^threat-external-2025-10-12]
<!-- UPDATE 2025-10-12: External service path alignment -->
Update 2025-10-12: Blob adapters reside in `src/elspeth/adapters/blob_store.py` and datasource/sink edges in `src/elspeth/plugins/nodes/{sources,sinks}/`.
<!-- END UPDATE -->
<!-- Update 2025-10-12: Azure ML telemetry (middleware_azure) and analytics report exports introduce additional edges that must be governed via workspace RBAC and report storage ACLs (`src/elspeth/plugins/llms/middleware_azure.py:180`, `src/elspeth/plugins/outputs/analytics_report.py:69`). -->

### Update 2025-10-12: Storage Interfaces
- Blob datasources and sinks should rely on managed identity where possible; SAS rotation windows must be short for accreditation deployments (`src/elspeth/plugins/datasources/blob.py:52`, `src/elspeth/plugins/outputs/blob.py:210`).
<!-- UPDATE 2025-10-12: Storage module relocation -->
Update 2025-10-12: Blob datasource and sink implementations live in `src/elspeth/plugins/nodes/sources/blob.py` and `src/elspeth/plugins/nodes/sinks/blob.py`.
<!-- END UPDATE -->

### Update 2025-10-12: LLM Providers
- Azure OpenAI adapters inject metadata (`retry`, `cost_summary`) and should be configured with per-deployment rate limits; maintain allowlisted deployments (`src/elspeth/plugins/llms/azure_openai.py:77`, `src/elspeth/core/experiments/runner.py:198`).
<!-- UPDATE 2025-10-12: LLM adapter path alignment -->
Update 2025-10-12: Azure OpenAI adapters reside in `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py`.
<!-- END UPDATE -->

### Update 2025-10-12: Repository Interfaces
- Repository sinks require PAT scopes limited to the target path; dry-run paths should be read-only when accreditation packages are prepared (`src/elspeth/plugins/outputs/repository.py:124`, `src/elspeth/plugins/outputs/repository.py:193`).
<!-- UPDATE 2025-10-12: Repository sink module relocation -->
Update 2025-10-12: Repository sinks live in `src/elspeth/plugins/nodes/sinks/repository.py` following the namespace migration.
<!-- END UPDATE -->

## Input Threats
- **Poisoned datasets** – CSV/Blob datasources read untrusted files; normalised security levels in dataframe metadata help classify downstream results, but content validation depends on experiment-specific plugins (`src/elspeth/plugins/datasources/csv_blob.py:35`, `src/elspeth/core/experiments/runner.py:208`).[^threat-poisoned-2025-10-12]
<!-- UPDATE 2025-10-12: Datasource module relocation -->
Update 2025-10-12: Datasource implementations are under `src/elspeth/plugins/nodes/sources/`.
<!-- END UPDATE -->
- **Prompt injection** – User-provided fields can attempt to override instructions. Strict prompt rendering and middleware-based term blocking/content safety mitigate common injection patterns (`src/elspeth/core/prompts/engine.py:33`, `src/elspeth/plugins/llms/middleware.py:110`, `src/elspeth/plugins/llms/middleware.py:232`).[^threat-prompt-2025-10-12]
<!-- UPDATE 2025-10-12: Middleware module relocation -->
Update 2025-10-12: Middleware protections now live in `src/elspeth/plugins/nodes/transforms/llm/middleware*.py`.
<!-- END UPDATE -->
- **Configuration spoofing** – Invalid plugin names or options are caught before instantiation; however, accreditation deployments should sign configuration bundles to prevent tampering at rest (`src/elspeth/core/validation/settings.py and src/elspeth/core/validation/suite.py`, `src/elspeth/core/registries/__init__.py:202`).[^threat-config-2025-10-12]
- **Suite configuration drift** – Prompt pack merges and suite defaults can silently introduce outdated plugins; monitor `suite_defaults` and prompt pack digests, and sign exported configs (`src/elspeth/config.py:52`, `src/elspeth/core/experiments/suite_runner.py:69`).[^threat-suite-config-2025-10-12]

## Output Threats
- **Spreadsheet exploits** – CSV/Excel sinks neutralise formula prefixes and record sanitiser metadata. For high-assurance contexts, retain sanitisation artifacts alongside exports for auditability (`src/elspeth/plugins/outputs/_sanitize.py:18`, `src/elspeth/plugins/outputs/excel.py:41`).[^threat-spreadsheet-2025-10-12]
- **Artifact exfiltration** – Artifact pipeline enforces security levels so a sink with lower clearance cannot consume classified outputs; misconfigured security levels remain a residual risk (`src/elspeth/core/security/__init__.py:14`, `src/elspeth/core/pipeline/artifact_pipeline.py:192`).[^threat-artifact-2025-10-12]
- **Repository drift** – Dry-run support reduces risk of accidental commits, but enabling live pushes requires rotating PAT tokens and enforcing branch protection server-side (`src/elspeth/plugins/outputs/repository.py:70`, `src/elspeth/plugins/outputs/repository.py:149`).[^threat-repo-2025-10-12]
- **Suite reporting artefacts** – Consolidated analytics, visual, and Excel outputs reside on local disk before signing; ensure `--reports-dir` targets a restricted path and artefacts are signed or hashed (`src/elspeth/tools/reporting.py:33`, `src/elspeth/tools/reporting.py:170`).[^threat-suite-report-2025-10-12]
<!-- Update 2025-10-12: Analytics reports and signed bundles persist locally before handoff; ensure filesystem permissions restrict tampering of `outputs/` directories that later feed accreditation packages (`src/elspeth/plugins/outputs/analytics_report.py:92`, `src/elspeth/plugins/outputs/signed.py:64`). -->
<!-- Update 2025-10-12: Visual analytics outputs embed PNG data inside HTML; treat generated files as sensitive artefacts, avoid hosting them on unauthenticated endpoints, and keep base64 images to prevent mixed-content risks (`src/elspeth/plugins/outputs/visual_report.py:208`). -->

### Update 2025-10-12: Analytics Exports
- Analytics and visual reports should inherit signed artifact workflows or be re-signed prior to distribution (`src/elspeth/plugins/outputs/analytics_report.py:112`, `src/elspeth/plugins/outputs/visual_report.py:208`).

## Service Abuse
- **LLM overuse** – Adaptive rate limiters throttle token and request rates, while retries capture exhaustive histories for alerting; ensure limits align with vendor SLAs to prevent throttling attacks (`src/elspeth/core/controls/rate_limit.py:104`, `src/elspeth/core/experiments/runner.py:542`).[^threat-llm-2025-10-12]
- **Cost escalation** – Cost trackers publish aggregate spend, enabling off-platform alerting or kill switches if thresholds are exceeded (`src/elspeth/core/controls/cost_tracker.py:36`, `src/elspeth/core/experiments/runner.py:198`).[^threat-cost-2025-10-12]
- **Middleware failure** – Azure Content Safety and Azure telemetry middleware log and optionally abort on errors. When configured with `on_error=skip`, deployers must ensure fallback logging is monitored (`src/elspeth/plugins/llms/middleware.py:232`, `src/elspeth/plugins/llms/middleware_azure.py:102`).[^threat-middleware-2025-10-12]
<!-- Update 2025-10-12: Suite-level concurrency can amplify LLM load; monitor rate limiter utilisation metrics exposed by `AdaptiveRateLimiter.utilization()` to prevent starvation-induced denial of service (`src/elspeth/core/controls/rate_limit.py:149`). -->

### Update 2025-10-12: Suite Concurrency
- Concurrency thresholds should align with rate limiter saturation signals; consider circuit-breaker middleware for repeated 429/5xx responses (`src/elspeth/core/experiments/runner.py:365`, `src/elspeth/core/controls/rate_limit.py:146`).

## Residual Risks & Recommendations
- **Secret sprawl** – Sample configurations contain placeholder SAS tokens and should never be deployed as-is; integrate with managed secret stores or environment provisioning pipelines (`config/blob_store.yaml:4`, `src/elspeth/plugins/outputs/signed.py:107`).[^threat-secret-2025-10-12]
- **Plugin supply chain** – Plugins execute within the orchestrator process. Establish an allowlist and code signing process for new plugins, especially when onboarding third-party analytics (`src/elspeth/core/experiments/plugin_registry.py:298`).[^threat-supply-2025-10-12]
- **Concurrency interactions** – High parallelism combined with strict rate limits can lead to starvation loops; monitor utilisation telemetry and consider circuit-breaker middleware for repeated failures (`src/elspeth/core/experiments/runner.py:126`, `src/elspeth/core/controls/rate_limit.py:126`).[^threat-concurrency-2025-10-12]

### Update 2025-10-12: Plugin Catalogue
- Seal plugin registries during accreditation builds and require code review for new entries (`src/elspeth/core/experiments/plugin_registry.py:34`, `src/elspeth/core/registries/__init__.py:91`).

## Added 2025-10-12 – Emerging External Interfaces
- **Azure ML run logging** – `AzureEnvironmentMiddleware` posts artefacts and comparison tables to the workspace run context. Harden by constraining service principal permissions and auditing `log_table` payloads for sensitive data (`src/elspeth/plugins/llms/middleware_azure.py:219`, `src/elspeth/plugins/llms/middleware_azure.py:250`).[^threat-azureml-2025-10-12]
- **Suite reporting artefacts** – CLI report generation writes comparative analytics, validation summaries, and recommendations under operator-controlled paths. Treat report directories as sensitive exports and wipe or re-sign before redistribution (`src/elspeth/tools/reporting.py:33`, `src/elspeth/tools/reporting.py:113`).[^threat-suite-report-2025-10-12]
- **LLM HTTP endpoints** – HTTP clients (e.g., Azure OpenAI, mock/http adapters) operate over TLS but remain untrusted; maintain allowlists and per-endpoint throttles to contain prompt leakage (`src/elspeth/plugins/nodes/transforms/llm/azure_openai.py:77`, `src/elspeth/core/controls/rate_limit.py:118`).[^threat-llm-2025-10-12]
- **Plugin discovery** – Experiments can request custom plugins via JSON config; ensure registries remain immutable in accreditation builds or gate additions by deploying with a sealed plugin catalogue (`src/elspeth/core/experiments/plugin_registry.py:34`, `src/elspeth/plugins/experiments/__init__.py:1`).[^threat-plugin-discovery-2025-10-12]

## Update History
- 2025-10-12 – Update 2025-10-12: Added suite configuration drift and suite reporting export threats to reflect new governance surfaces.
- 2025-10-12 – Highlighted Azure ML telemetry surfaces, analytics export risks, and dynamic plugin onboarding considerations for threat modelling.
- 2025-10-12 – Update 2025-10-12: Added storage/LLM/provider annotations, analytics export guidance, and concurrency safeguards with cross-document references.

[^threat-operator-2025-10-12]: Update 2025-10-12: Operator zone validation mapped in docs/architecture/configuration-security.md.
[^threat-orchestrator-2025-10-12]: Update 2025-10-12: Orchestrator trust model detailed in docs/architecture/architecture-overview.md.
[^threat-plugin-2025-10-12]: Update 2025-10-12: Plugin boundaries described in docs/architecture/plugin-security-model.md.
[^threat-external-2025-10-12]: Update 2025-10-12: External service interactions visualised in docs/architecture/component-diagram.md.
[^threat-poisoned-2025-10-12]: Update 2025-10-12: Sanitisation and validation pipelines shown in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Ingress Classification Flow).
[^threat-prompt-2025-10-12]: Update 2025-10-12: Prompt shielding controls catalogued in docs/architecture/security-controls.md (Update 2025-10-12: Middleware Safeguards).
[^threat-config-2025-10-12]: Update 2025-10-12: Configuration signing recommendation links to docs/compliance/CONTROL_INVENTORY.md.
[^threat-spreadsheet-2025-10-12]: Update 2025-10-12: Spreadsheet sanitisation captured in docs/architecture/security-controls.md (Update 2025-10-12: Output Sanitisation).
[^threat-artifact-2025-10-12]: Update 2025-10-12: Artifact clearance process described in docs/architecture/security-controls.md (Update 2025-10-12: Artifact Clearance).
[^threat-repo-2025-10-12]: Update 2025-10-12: Repository guidance elaborated in docs/reporting-and-suite-management.md.
[^threat-llm-2025-10-12]: Update 2025-10-12: Rate limiter telemetry mapped in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Parallel Execution Gate).
[^threat-cost-2025-10-12]: Update 2025-10-12: Cost tracking outputs referenced in docs/architecture/audit-logging.md.
[^threat-middleware-2025-10-12]: Update 2025-10-12: Middleware failure handling detailed in docs/architecture/security-controls.md (Update 2025-10-12: Middleware Safeguards).
[^threat-secret-2025-10-12]: Update 2025-10-12: Secret rotation strategy linked to docs/architecture/configuration-security.md (Update 2025-10-12: Secret Management).
[^threat-supply-2025-10-12]: Update 2025-10-12: Plugin supply chain governance tied to docs/architecture/plugin-security-model.md (Update 2025-10-12: Plugin Lifecycle).
[^threat-concurrency-2025-10-12]: Update 2025-10-12: Concurrency mitigation described in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Suite Concurrency).
[^threat-azureml-2025-10-12]: Update 2025-10-12: Azure ML surfaces cross-referenced in docs/architecture/audit-logging.md (Update 2025-10-12: Azure Telemetry).
[^threat-suite-report-2025-10-12]: Update 2025-10-12: Suite reporting exports and artefact handling detailed in docs/reporting-and-suite-management.md (Update 2025-10-12: Suite Reporting Exports).
[^threat-plugin-discovery-2025-10-12]: Update 2025-10-12: Plugin discovery guardrails summarised in docs/architecture/plugin-security-model.md (Update 2025-10-12: Registry Enforcement).
[^threat-suite-config-2025-10-12]: Update 2025-10-12: Suite governance safeguards detailed in docs/architecture/security-controls.md (Update 2025-10-12: Suite governance).
