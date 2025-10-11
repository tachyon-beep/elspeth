# Azure Environment Middleware Design

## Context
- Azure-specific concerns span multiple surfaces: invoking Azure OpenAI deployments, logging experiment telemetry to Azure Machine Learning, and persisting artefacts in Azure storage.
- Current architecture already separates these concerns into specialised plugin families (LLM clients, datasources, sinks, middleware).
- We need a reusable extension point that can light up Azure platform features without coupling them to the Azure OpenAI client or to sinks.

## Goals
- Provide a middleware package (`azure_environment`) that can be activated via settings to enable Azure ML telemetry and other environment integrations.
- Keep Azure OpenAI client focused on request execution (auth, deployment lookup, SDK interaction).
- Allow the same middleware to operate with non-Azure LLM providers if we ever want Azure ML telemetry with different models.
- Preserve data ingress/egress isolation: datasources and sinks remain the only components that touch storage or artefact movement.

## Responsibilities
- Detect Azure ML run context (`azureml.core.Run.get_context()` or newer SDK) and log key events:
  - before request: capture metadata (experiment name, row id, attempt) and optionally prompts when configured.
  - after response: log metrics (tokens, scores, latency) and errors.
  - exhausted retries: log a `llm_retry_exhausted` row with attempt history and error details.
- Suite lifecycle telemetry: log experiment inventory, preflight results, per-experiment summaries, baseline comparisons, and final suite totals to Azure ML tables/rows.
- Emit run-level metadata on teardown (e.g., record number of successes/failures, aggregate metrics).
- Surface configuration toggles for operators (enable prompt logging, fields to redact, summary cadence).
- Expose hooks for future Azure-specific behaviours (e.g., posting cost summaries to Azure Monitor) without editing other layers.

## Integration Plan
1. Implement `AzureEnvironmentMiddleware` under `src/elspeth/plugins/llms/middleware_azure.py` (name TBD) registering with the middleware registry. Constructor accepts flags for telemetry features.
2. Middleware `before_request` / `after_response` interact with Azure ML SDK guarded behind optional imports; degrade gracefully when SDK is absent or context is offline.
3. Update configuration docs to show enabling the middleware via profile defaults or prompt packs:
   ```yaml
   llm_middlewares:
     - plugin: azure_environment
       options:
         log_prompts: false
         summary_interval: 50
   ```
4. Leave Azure OpenAI client untouched except for exposing metadata useful to the middleware (already available via request metadata / response metrics in runner).
5. Consider follow-up aggregation or sink plugins for Azure Storage/DevOps outputs separately; middleware should not write artefacts.
<!-- UPDATE 2025-10-12: Steps 1–4 are now complete; `AzureEnvironmentMiddleware` implements lifecycle hooks, retry logging, and suite summaries (`src/elspeth/plugins/llms/middleware_azure.py`). -->

## Open Questions
- Which Azure ML SDK flavour to target (`azureml-core` vs. `azure-ai-ml`)? Initial implementation can rely on `azureml-core` with optional dependency guard.
- Do we need structured schemas for telemetry payloads? Legacy runner logged metric rows; we can start with parity and iterate.
- How should run completion summaries be triggered? Possibly via `atexit` hook or suite-level aggregator once we have more visibility.

## Dependencies & Fail-fast Behaviour
- Middleware requires the Azure ML runtime (`azureml-core`) to be installed and a live run context available. When invoked without these prerequisites it now defaults to `on_error="skip"` which logs a message and disables telemetry instead of raising, using environment-variable heuristics to decide whether Azure ML is expected.
- Configurations that reference the middleware should run inside Azure ML when telemetry is required. Set `on_error="abort"` to fail fast if the run context is missing; otherwise local executions degrade gracefully.
<!-- UPDATE 2025-10-12: Middleware now logs fallback behaviour at INFO/WARNING when `on_error="skip"`; tests cover these scenarios in `tests/test_llm_middleware.py`. -->

## Next Steps
1. Scaffold middleware class and register it.
2. Add unit tests exercising telemetry hooks with mocked Azure ML Run.
3. Document configuration usage in README / notes after implementation.
<!-- UPDATE 2025-10-12: Completed. Future enhancements include optional Azure Monitor webhooks and richer suite summary metrics. -->

## Update History
- 2025-10-12 – Noted completion of middleware implementation and highlighted future telemetry enhancements.
