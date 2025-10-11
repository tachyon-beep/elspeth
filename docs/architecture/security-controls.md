# Security Controls Inventory

## Authentication & Authorization
- **Azure storage ingestion** – Blob datasources accept SAS tokens, explicit credentials, or managed identity through `azure-identity`, failing closed when secrets are absent (`src/elspeth/plugins/datasources/blob.py:17`, `src/elspeth/datasources/blob_store.py:125`).
- **LLM credentials** – Azure OpenAI clients read keys, endpoints, and deployment IDs from configuration or environment variables, ensuring deployments can lock credentials outside source control (`src/elspeth/plugins/llms/azure_openai.py:25`, `src/elspeth/plugins/llms/azure_openai.py:60`).
- **Repository sinks** – GitHub and Azure DevOps sinks resolve personal-access tokens on demand and optionally dry-run commits, reducing exposure during review cycles (`src/elspeth/plugins/outputs/repository.py:149`, `src/elspeth/plugins/outputs/repository.py:178`).
- **Signed artifacts** – The signing sink enforces key presence (with legacy aliases) and never writes unsigned bundles when secrets are missing (`src/elspeth/plugins/outputs/signed.py:37`, `src/elspeth/plugins/outputs/signed.py:107`).

## Input Validation
- **Configuration schemas** – Settings profiles, plugin definitions, and suite experiments are validated against JSON-schema-like definitions before execution (`src/elspeth/core/validation.py:271`, `src/elspeth/core/validation.py:1012`, `src/elspeth/core/validation.py:1034`).
- **Prompt compilation** – Prompts render with `StrictUndefined`, raising `PromptValidationError` when required variables are missing and preventing silent template failures (`src/elspeth/core/prompts/engine.py:33`, `src/elspeth/core/prompts/template.py:24`).
- **Response validation plugins** – Regex, JSON, and LLM-guard validators reject responses that fail format or policy checks, isolating untrusted LLM output from downstream pipelines (`src/elspeth/plugins/experiments/validation.py:20`, `src/elspeth/plugins/experiments/validation.py:47`, `src/elspeth/plugins/experiments/validation.py:100`).
- **Suite governance** – Suite validation aggregates experiment metadata, enforces presence of sinks, and reports baseline consistency before any run is accepted (`src/elspeth/core/experiments/suite_runner.py:208`, `src/elspeth/core/validation.py:471`).

## Output Sanitisation
- **CSV and Excel guards** – Tabular sinks prefix dangerous characters and record sanitisation metadata for audits, mitigating spreadsheet formula injection (`src/elspeth/plugins/outputs/_sanitize.py:18`, `src/elspeth/plugins/outputs/csv_file.py:49`, `src/elspeth/plugins/outputs/excel.py:41`).
- **Manifest hygiene** – Excel and signed sinks capture security level, cost summary, and retry failure samples so downstream consumers can filter sensitive outputs (`src/elspeth/plugins/outputs/excel.py:134`, `src/elspeth/plugins/outputs/signed.py:75`).
- **Repository payloads** – GitHub/Azure DevOps uploads serialise JSON payloads and can stay in dry-run mode for inspection, limiting exposure when accreditation environments disallow external commits (`src/elspeth/plugins/outputs/repository.py:57`, `src/elspeth/plugins/outputs/repository.py:135`).

## Rate Limiting & Cost Controls
- **Pluggable limiters** – Fixed-window and adaptive limiters bound request and token rates, with utilisation feedback gating the runner’s parallel workers (`src/elspeth/core/controls/rate_limit.py:61`, `src/elspeth/core/controls/rate_limit.py:126`, `src/elspeth/core/experiments/runner.py:430`).
- **Cost accounting** – Fixed-price trackers accumulate token usage and expose aggregate costs for audit logs, enabling guardrails against runaway spending (`src/elspeth/core/controls/cost_tracker.py:36`, `src/elspeth/core/experiments/runner.py:198`).
- **Suite overrides** – Experiments can override default rate/cost policies, while validation ensures plugin names/options are recognised before execution (`config/sample_suite/slow_rate_limit_demo/config.json:9`, `src/elspeth/core/controls/registry.py:102`).

## Middleware Security Features
- **Prompt Shielding** – Denied term lists can mask or block prompts before model invocation, surfacing violations via structured logs (`src/elspeth/plugins/llms/middleware.py:91`, `src/elspeth/plugins/llms/middleware.py:110`).
- **Content Safety** – Azure Content Safety middleware screens prompts with severity thresholds and configurable failure handling, acting as an external policy oracle (`src/elspeth/plugins/llms/middleware.py:206`, `src/elspeth/plugins/llms/middleware.py:232`).
- **Audit Logging & Telemetry** – Middleware publishes request metadata, retry exhaustion, and experiment summaries to logs or Azure ML run tables for defensible evidence (`src/elspeth/plugins/llms/middleware.py:70`, `src/elspeth/plugins/llms/middleware_azure.py:180`, `src/elspeth/core/experiments/runner.py:575`).
- **Health Monitoring** – Rolling latency and failure metrics are emitted on a heartbeat, aiding blue-team alerting and availability monitoring (`src/elspeth/plugins/llms/middleware.py:124`, `src/elspeth/plugins/llms/middleware.py:178`).

## Signing & Verification
- **HMAC signing** – Signed bundles produce SHA-256 (or SHA-512) digests and store signature manifests alongside results for later verification (`src/elspeth/core/security/signing.py:17`, `src/elspeth/plugins/outputs/signed.py:48`).
- **Security level enforcement** – Artifacts inherit classifications and sinks must possess sufficient clearance before consuming upstream outputs (`src/elspeth/core/security/__init__.py:14`, `src/elspeth/core/artifact_pipeline.py:192`).
- **Artifact dependency validation** – The pipeline validates declared artifact types and rejects cycles, ensuring that only declared flows are allowed (`src/elspeth/core/artifact_pipeline.py:171`, `src/elspeth/core/artifact_pipeline.py:201`).

## Retry, Error Handling & Observability
- **Deterministic retries** – The runner records attempt histories, exponential backoff, and final errors, raising structured exceptions when exhaustion occurs (`src/elspeth/core/experiments/runner.py:464`, `src/elspeth/core/experiments/runner.py:544`, `src/elspeth/core/experiments/runner.py:575`).
- **Checkpointing** – Long-running suites can resume from checkpoints without reprocessing previously signed rows, limiting attack windows on idempotent outputs (`src/elspeth/core/experiments/runner.py:70`, `src/elspeth/core/experiments/runner.py:624`).
- **Early-stop governance** – Threshold plugins can halt execution once success/failure criteria are met, reducing unnecessary exposure to external services (`src/elspeth/plugins/experiments/early_stop.py:17`, `src/elspeth/core/experiments/runner.py:223`).
- **Failure containment** – `on_error` policies across plugins downgrade fatal errors to warnings when configured, supporting best-effort runs during accreditation rehearsals (`src/elspeth/plugins/datasources/csv_local.py:30`, `src/elspeth/plugins/outputs/blob.py:64`, `src/elspeth/plugins/outputs/excel.py:52`).

## Gaps & Hardening Opportunities
- **Credential rotation** – Secrets are currently read directly from environment variables; integration with managed secret stores (e.g., Azure Key Vault) or signed credential files should be prioritised (`config/blob_store.yaml:4`, `src/elspeth/plugins/outputs/signed.py:107`).
- **Middleware execution order** – Middleware is executed in the order defined by configuration; formalising precedence or conflict detection would prevent misconfiguration when multiple enforcement layers are active (`src/elspeth/core/experiments/runner.py:493`).
- **LLM response sanitisation** – While validation plugins exist, default stacks do not enforce JSON schemes. Accrediting authorities may require baseline validators for each prompt pack instead of optional opt-in (`src/elspeth/plugins/experiments/validation.py:47`).
