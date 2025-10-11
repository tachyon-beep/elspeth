# Threat Surfaces & Trust Boundaries

## Trust Zones
- **Operator Zone** – Local CLI execution validates configuration before any network activity, acting as the first guard against malformed profiles (`src/elspeth/cli.py:83`, `src/elspeth/core/validation.py:271`).
- **Core Orchestrator Zone** – Trusted runtime processes data in memory, applies middleware, and enforces retry logic; tampering here would require code execution on the host (`src/elspeth/core/orchestrator.py:43`, `src/elspeth/core/experiments/runner.py:65`).
- **Plugin Zone** – Pluggable datasources, LLM clients, sinks, and experiment plugins sit at the boundary of trusted code and external services; schema validation and runtime guards constrain their behaviour (`src/elspeth/core/registry.py:91`, `src/elspeth/core/experiments/plugin_registry.py:93`).
- **External Service Zone** – Azure storage, Azure/OpenAI endpoints, and repository APIs operate outside ELSPETH’s control and are treated as untrusted data producers/consumers (`src/elspeth/datasources/blob_store.py:200`, `src/elspeth/plugins/llms/azure_openai.py:77`, `src/elspeth/plugins/outputs/repository.py:124`).

## Input Threats
- **Poisoned datasets** – CSV/Blob datasources read untrusted files; normalised security levels in dataframe metadata help classify downstream results, but content validation depends on experiment-specific plugins (`src/elspeth/plugins/datasources/csv_blob.py:35`, `src/elspeth/core/experiments/runner.py:208`).
- **Prompt injection** – User-provided fields can attempt to override instructions. Strict prompt rendering and middleware-based term blocking/content safety mitigate common injection patterns (`src/elspeth/core/prompts/engine.py:33`, `src/elspeth/plugins/llms/middleware.py:110`, `src/elspeth/plugins/llms/middleware.py:232`).
- **Configuration spoofing** – Invalid plugin names or options are caught before instantiation; however, accreditation deployments should sign configuration bundles to prevent tampering at rest (`src/elspeth/core/validation.py:271`, `src/elspeth/core/registry.py:202`).

## Output Threats
- **Spreadsheet exploits** – CSV/Excel sinks neutralise formula prefixes and record sanitiser metadata. For high-assurance contexts, retain sanitisation artifacts alongside exports for auditability (`src/elspeth/plugins/outputs/_sanitize.py:18`, `src/elspeth/plugins/outputs/excel.py:41`).
- **Artifact exfiltration** – Artifact pipeline enforces security levels so a sink with lower clearance cannot consume classified outputs; misconfigured security levels remain a residual risk (`src/elspeth/core/security/__init__.py:14`, `src/elspeth/core/artifact_pipeline.py:192`).
- **Repository drift** – Dry-run support reduces risk of accidental commits, but enabling live pushes requires rotating PAT tokens and enforcing branch protection server-side (`src/elspeth/plugins/outputs/repository.py:70`, `src/elspeth/plugins/outputs/repository.py:149`).

## Service Abuse
- **LLM overuse** – Adaptive rate limiters throttle token and request rates, while retries capture exhaustive histories for alerting; ensure limits align with vendor SLAs to prevent throttling attacks (`src/elspeth/core/controls/rate_limit.py:104`, `src/elspeth/core/experiments/runner.py:542`).
- **Cost escalation** – Cost trackers publish aggregate spend, enabling off-platform alerting or kill switches if thresholds are exceeded (`src/elspeth/core/controls/cost_tracker.py:36`, `src/elspeth/core/experiments/runner.py:198`).
- **Middleware failure** – Azure Content Safety and Azure telemetry middleware log and optionally abort on errors. When configured with `on_error=skip`, deployers must ensure fallback logging is monitored (`src/elspeth/plugins/llms/middleware.py:232`, `src/elspeth/plugins/llms/middleware_azure.py:102`).

## Residual Risks & Recommendations
- **Secret sprawl** – Sample configurations contain placeholder SAS tokens and should never be deployed as-is; integrate with managed secret stores or environment provisioning pipelines (`config/blob_store.yaml:4`, `src/elspeth/plugins/outputs/signed.py:107`).
- **Plugin supply chain** – Plugins execute within the orchestrator process. Establish an allowlist and code signing process for new plugins, especially when onboarding third-party analytics (`src/elspeth/core/experiments/plugin_registry.py:298`).
- **Concurrency interactions** – High parallelism combined with strict rate limits can lead to starvation loops; monitor utilisation telemetry and consider circuit-breaker middleware for repeated failures (`src/elspeth/core/experiments/runner.py:126`, `src/elspeth/core/controls/rate_limit.py:126`).
