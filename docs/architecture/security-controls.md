# Security Controls Inventory

## Authentication & Authorization
- **Azure storage ingestion** – Blob datasources accept SAS tokens, explicit credentials, or managed identity through `azure-identity`, failing closed when secrets are absent (`src/elspeth/plugins/datasources/blob.py:17`, `src/elspeth/datasources/blob_store.py:125`).[^sec-azure-ingest-2025-10-12]
<!-- UPDATE 2025-10-12: Datasource path alignment -->
Update 2025-10-12: Blob datasource implementations live in `src/elspeth/plugins/nodes/sources/blob.py`; legacy module references are preserved for audits predating the namespace migration.
<!-- END UPDATE -->
- **LLM credentials** – Azure OpenAI clients read keys, endpoints, and deployment IDs from configuration or environment variables, ensuring deployments can lock credentials outside source control (`src/elspeth/plugins/llms/azure_openai.py:25`, `src/elspeth/plugins/llms/azure_openai.py:60`).[^sec-llm-2025-10-12]
<!-- UPDATE 2025-10-12: LLM client path alignment -->
Update 2025-10-12: Azure OpenAI transport resides at `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py`.
<!-- END UPDATE -->
- **Repository sinks** – GitHub and Azure DevOps sinks resolve personal-access tokens on demand and optionally dry-run commits, reducing exposure during review cycles (`src/elspeth/plugins/outputs/repository.py:149`, `src/elspeth/plugins/outputs/repository.py:178`).[^sec-repo-2025-10-12]
<!-- UPDATE 2025-10-12: Repository sink module relocation -->
Update 2025-10-12: Repository sinks are implemented in `src/elspeth/plugins/nodes/sinks/repository.py` with identical security semantics.
<!-- END UPDATE -->
- **Signed artifacts** – The signing sink enforces key presence (with legacy aliases) and never writes unsigned bundles when secrets are missing (`src/elspeth/plugins/outputs/signed.py:37`, `src/elspeth/plugins/outputs/signed.py:107`).[^sec-signed-auth-2025-10-12]
<!-- UPDATE 2025-10-12: Signed sink module relocation -->
Update 2025-10-12: Signed artifact enforcement resides in `src/elspeth/plugins/nodes/sinks/signed.py`.
<!-- END UPDATE -->
- **Plugin-scoped endpoint allowlists** – Each outbound plugin (Azure/OpenAI clients, retrieval connectors, sinks) embeds its own certified endpoint allowlist and validation logic so updates to approved infrastructure are versioned with the component, not centralised in shared configuration. The current configuration limits outbound traffic to the Australian public Azure cloud (`src/elspeth/plugins/nodes/transforms/llm/azure_openai.py`, `src/elspeth/retrieval/providers.py`, `src/elspeth/core/security/approved_endpoints.py`). (Update 2025-10-17)

## Pipeline Security Model

- **Clearance enforcement (traditional MLS)** – Components may only consume data whose
  classification is less than or equal to their declared `security_level`. An
  `UNOFFICIAL` sink can only receive `UNOFFICIAL` data, whereas a `SECRET` sink can handle
  anything up to `SECRET`.
- **Pipeline-wide minimum evaluation (proactive prevention)** – Before execution the suite
  runner evaluates the minimum security level across all configured components (datasource,
  LLM, middleware, sinks). If any component has lower clearance than the pipeline requires,
  that component refuses to operate (Bell-LaPadula "no read up"). Components with higher
  clearance are trusted to operate at lower levels, filtering data appropriately.

```yaml
# Example: UNOFFICIAL datasource in SECRET pipeline - FAILS
datasource: TestDB       # security_level: UNOFFICIAL (insufficient clearance)
sinks:
  - EncryptedVault       # security_level: SECRET
  - SecureStorage        # security_level: SECRET
# Pipeline minimum = UNOFFICIAL, but FAILS because datasource can't be upgraded to SECRET

# Example: SECRET datasource with UNOFFICIAL sink - SUCCEEDS at UNOFFICIAL level
datasource: SecretDB     # security_level: SECRET (can operate at lower levels)
sinks:
  - EncryptedVault       # security_level: SECRET
  - DebugLogger          # security_level: UNOFFICIAL  ← lowers pipeline to UNOFFICIAL
# Pipeline minimum = UNOFFICIAL, SecretDB filters data to UNOFFICIAL, pipeline succeeds
```

This defence-in-depth pairing stops both inadvertent misconfigurations and malicious downgrade
attempts.

### Update 2025-10-12: Managed Identity
- Azure datasources/outputs default to `DefaultAzureCredential`, falling back to SAS tokens when managed identity is unavailable (`src/elspeth/datasources/blob_store.py:125`, `src/elspeth/plugins/outputs/blob.py:210`).

## Input Validation
- **Configuration schemas** – Settings profiles, plugin definitions, and suite experiments are validated against JSON-schema-like definitions before execution (`src/elspeth/core/validation/settings.py and src/elspeth/core/validation/suite.py`, `src/elspeth/core/validation/settings.py and src/elspeth/core/validation/suite.py`, `src/elspeth/core/validation/settings.py and src/elspeth/core/validation/suite.py`).[^sec-config-validation-2025-10-12]
<!-- UPDATE 2025-10-12: Validation citation refresh -->
Update 2025-10-12: Validation helpers span `src/elspeth/core/validation/settings.py and src/elspeth/core/validation/suite.py-512` with suite schema enforcement in `src/elspeth/core/config/schema.py:17-198`.
<!-- END UPDATE -->
- **Prompt compilation** – Prompts render with `StrictUndefined`, raising `PromptValidationError` when required variables are missing and preventing silent template failures (`src/elspeth/core/prompts/engine.py:33`, `src/elspeth/core/prompts/template.py:24`).[^sec-prompt-2025-10-12]
- **Response validation plugins** – Regex, JSON, and LLM-guard validators reject responses that fail format or policy checks, isolating untrusted LLM output from downstream pipelines (`src/elspeth/plugins/experiments/validation.py:20`, `src/elspeth/plugins/experiments/validation.py:47`, `src/elspeth/plugins/experiments/validation.py:100`).[^sec-validation-plugins-2025-10-12]
- **Suite governance** – Suite validation aggregates experiment metadata, enforces presence of sinks, and reports baseline consistency before any run is accepted (`src/elspeth/core/experiments/suite_runner.py:208`, `src/elspeth/core/validation/settings.py and src/elspeth/core/validation/suite.py`).[^sec-suite-governance-2025-10-12]
<!-- UPDATE 2025-10-12: Suite governance line update -->
Update 2025-10-12: Suite validation and baseline checks occur at `src/elspeth/core/experiments/suite_runner.py:295-382` and `src/elspeth/core/validation/settings.py and src/elspeth/core/validation/suite.py-512`.
<!-- END UPDATE -->
<!-- Update 2025-10-12: Experiment configs now run through `src/elspeth/core/config/schema.py:17`, ensuring renamed keys (e.g., `prompt_pack`, `concurrency`, `early_stop_plugins`) conform to normalized schemas before execution. -->

### Update 2025-10-12: Prompt Hygiene
- Prompt defaults and strict templates prevent missing variables, aligning with docs/architecture/architecture-overview.md Core Principles and data flow ingress controls.

## Middleware Safeguards
- **Prompt shield** – Request prompts are scanned for denied terms and either aborted, masked, or logged based on policy, preventing high-risk inputs from reaching the model (`src/elspeth/plugins/llms/middleware.py:91`, `src/elspeth/plugins/llms/middleware.py:112`).[^sec-prompt-shield-2025-10-12]
<!-- UPDATE 2025-10-12: Middleware module relocation -->
Update 2025-10-12: Prompt shield middleware now resides in `src/elspeth/plugins/nodes/transforms/llm/middleware.py`.
<!-- END UPDATE -->
- **Azure Content Safety** – Outbound prompts are inspected against Azure categories and severity thresholds; violations can abort or mask, and errors respect configurable `on_error` behaviour (`src/elspeth/plugins/llms/middleware.py:206`, `src/elspeth/plugins/llms/middleware_azure.py:95`).[^sec-content-safety-2025-10-12]
<!-- UPDATE 2025-10-12: Azure middleware module relocation -->
Update 2025-10-12: Content safety checks are implemented in `src/elspeth/plugins/nodes/transforms/llm/middleware.py` and `_azure.py`.
<!-- END UPDATE -->
- **Audit logger** – Metadata-only logging offers traceability for every LLM call without exposing sensitive prompts unless explicitly enabled (`src/elspeth/plugins/llms/middleware.py:70`, `src/elspeth/plugins/llms/middleware.py:101`).[^sec-audit-2025-10-12]
<!-- UPDATE 2025-10-12: Middleware module relocation -->
Update 2025-10-12: Audit logging middleware located at `src/elspeth/plugins/nodes/transforms/llm/middleware.py` retains the same hooks.
<!-- END UPDATE -->
- **Health monitor** – Rolling latency/failure metrics provide heartbeat telemetry, making saturation or outage detection observable (`src/elspeth/plugins/llms/middleware.py:120`, `src/elspeth/plugins/llms/middleware.py:144`).[^sec-health-monitor-2025-10-12]
- **Azure environment telemetry** – When running under Azure ML, middleware writes structured rows/tables (suite inventory, experiment summaries, retry exhaustion) to the run context for immutable audit trails (`src/elspeth/plugins/llms/middleware_azure.py:180`, `src/elspeth/plugins/llms/middleware_azure.py:250`).[^audit-azure-run-2025-10-12]
- **Retry exhaustion hooks** – `_notify_retry_exhausted` and middleware callbacks emit structured attempt histories whenever retries are exhausted, ensuring SOC teams receive actionable evidence (`src/elspeth/core/experiments/runner.py:520`, `src/elspeth/plugins/llms/middleware_azure.py:233`).[^sec-retry-2025-10-12]

## Output Sanitisation
- **CSV and Excel guards** – Tabular sinks prefix dangerous characters and record sanitisation metadata for audits, mitigating spreadsheet formula injection (`src/elspeth/plugins/outputs/_sanitize.py:18`, `src/elspeth/plugins/outputs/csv_file.py:49`, `src/elspeth/plugins/outputs/excel.py:41`).[^sec-output-sanitize-2025-10-12]
- **Manifest hygiene** – Excel and signed sinks capture security level, cost summary, and retry failure samples so downstream consumers can filter sensitive outputs (`src/elspeth/plugins/outputs/excel.py:134`, `src/elspeth/plugins/outputs/signed.py:75`).[^sec-manifest-2025-10-12]
- **Repository payloads** – GitHub/Azure DevOps uploads serialise JSON payloads and can stay in dry-run mode for inspection, limiting exposure when accreditation environments disallow external commits (`src/elspeth/plugins/outputs/repository.py:57`, `src/elspeth/plugins/outputs/repository.py:135`).[^sec-repo-payload-2025-10-12]
<!-- Update 2025-10-12: Visual analytics sink embeds charts via base64 PNGs and inlined tables, avoiding external links and inheriting artifact security levels (`src/elspeth/plugins/outputs/visual_report.py:150`, `src/elspeth/plugins/outputs/visual_report.py:208`). -->

### Update 2025-10-12: Output Sanitisation
- Sanitisation metadata is captured in analytics and signed manifests, ensuring downstream auditors can verify formula neutralisation (`src/elspeth/plugins/outputs/analytics_report.py:112`, `src/elspeth/plugins/outputs/signed.py:94`).

## Rate Limiting & Cost Controls
- **Pluggable limiters** – Fixed-window and adaptive limiters bound request and token rates, with utilisation feedback gating the runner’s parallel workers (`src/elspeth/core/controls/rate_limit.py:61`, `src/elspeth/core/controls/rate_limit.py:126`, `src/elspeth/core/experiments/runner.py:430`).[^sec-rate-limiters-2025-10-12]
- **Cost accounting** – Fixed-price trackers accumulate token usage and expose aggregate costs for audit logs, enabling guardrails against runaway spending (`src/elspeth/core/controls/cost_tracker.py:36`, `src/elspeth/core/experiments/runner.py:198`).[^sec-cost-tracker-2025-10-12]
- **Suite overrides** – Experiments can override default rate/cost policies, while validation ensures plugin names/options are recognised before execution (`config/sample_suite/slow_rate_limit_demo/config.json:9`, `src/elspeth/core/controls/registry.py:102`).[^sec-suite-overrides-2025-10-12]

## Middleware Security Features
- **Prompt Shielding** – Denied term lists can mask or block prompts before model invocation, surfacing violations via structured logs (`src/elspeth/plugins/llms/middleware.py:91`, `src/elspeth/plugins/llms/middleware.py:110`).[^sec-prompt-shield-2025-10-12]
- **Content Safety** – Azure Content Safety middleware screens prompts with severity thresholds and configurable failure handling, acting as an external policy oracle (`src/elspeth/plugins/llms/middleware.py:206`, `src/elspeth/plugins/llms/middleware.py:232`).[^sec-content-safety-2025-10-12]
- **Audit Logging & Telemetry** – Middleware publishes request metadata, retry exhaustion, and experiment summaries to logs or Azure ML run tables for defensible evidence (`src/elspeth/plugins/llms/middleware.py:70`, `src/elspeth/plugins/llms/middleware_azure.py:180`, `src/elspeth/core/experiments/runner.py:575`).[^sec-audit-2025-10-12]
<!-- UPDATE 2025-10-12: Runner retry citation update -->
Update 2025-10-12: Retry exhaustion handling occurs at `src/elspeth/core/experiments/runner.py:657-678`.
<!-- END UPDATE -->
- **Health Monitoring** – Rolling latency and failure metrics are emitted on a heartbeat, aiding blue-team alerting and availability monitoring (`src/elspeth/plugins/llms/middleware.py:124`, `src/elspeth/plugins/llms/middleware.py:178`).[^sec-health-monitor-2025-10-12]
<!-- Update 2025-10-12: `AzureEnvironmentMiddleware` now logs suite inventories, baseline comparisons, and `llm_retry_exhausted` events, providing structured evidence for accreditation reviews (`src/elspeth/plugins/llms/middleware_azure.py:219`, `src/elspeth/plugins/llms/middleware_azure.py:243`). -->

### Update 2025-10-12: Middleware Safeguards
- Middleware ordering should preserve blocking policies (prompt shield/content safety) ahead of telemetry; see docs/architecture/data-flow-diagrams.md for trust boundary sequences.

## Signing & Verification
- **HMAC signing** – Signed bundles produce SHA-256 (or SHA-512) digests and store signature manifests alongside results for later verification (`src/elspeth/core/security/signing.py:17`, `src/elspeth/plugins/outputs/signed.py:48`).[^sec-hmac-2025-10-12]
- **Security level enforcement** – Artifacts inherit classifications and sinks must possess sufficient clearance before consuming upstream outputs (`src/elspeth/core/security/__init__.py:14`, `src/elspeth/core/pipeline/artifact_pipeline.py:192`).[^sec-clearance-2025-10-12]
- **Artifact dependency validation** – The pipeline validates declared artifact types and rejects cycles, ensuring that only declared flows are allowed (`src/elspeth/core/pipeline/artifact_pipeline.py:171`, `src/elspeth/core/pipeline/artifact_pipeline.py:201`).[^sec-artifact-deps-2025-10-12]

### Update 2025-10-12: Artifact Signing
- Signed manifests capture cost summaries, retry metadata, and security levels to support accreditation evidence (`src/elspeth/plugins/outputs/signed.py:67`).

### Update 2025-10-12: Artifact Clearance
- `ArtifactPipeline` invokes `is_security_level_allowed` before resolving dependencies, preventing clearance downgrades (`src/elspeth/core/pipeline/artifact_pipeline.py:205`, `src/elspeth/core/security/__init__.py:32`).

## Retry, Error Handling & Observability
- **Deterministic retries** – The runner records attempt histories, exponential backoff, and final errors, raising structured exceptions when exhaustion occurs (`src/elspeth/core/experiments/runner.py:464`, `src/elspeth/core/experiments/runner.py:544`, `src/elspeth/core/experiments/runner.py:575`).[^sec-retry-2025-10-12]
<!-- UPDATE 2025-10-12: Retry flow citation refresh -->
Update 2025-10-12: Core retry loop currently spans `src/elspeth/core/experiments/runner.py:547-676`.
<!-- END UPDATE -->
- **Checkpointing** – Long-running suites can resume from checkpoints without reprocessing previously signed rows, limiting attack windows on idempotent outputs (`src/elspeth/core/experiments/runner.py:70`, `src/elspeth/core/experiments/runner.py:624`).[^sec-checkpoint-2025-10-12]
<!-- UPDATE 2025-10-12: Checkpoint citation refresh -->
Update 2025-10-12: Checkpoint load/append helpers live at `src/elspeth/core/experiments/runner.py:695-709`.
<!-- END UPDATE -->
- **Early-stop governance** – Threshold plugins can halt execution once success/failure criteria are met, reducing unnecessary exposure to external services (`src/elspeth/plugins/experiments/early_stop.py:17`, `src/elspeth/core/experiments/runner.py:223`).[^sec-early-stop-2025-10-12]
- **Failure containment** – `on_error` policies across plugins downgrade fatal errors to warnings when configured, supporting best-effort runs during accreditation rehearsals (`src/elspeth/plugins/datasources/csv_local.py:30`, `src/elspeth/plugins/outputs/blob.py:64`, `src/elspeth/plugins/outputs/excel.py:52`).[^sec-failure-2025-10-12]
<!-- UPDATE 2025-10-12: Output sink path alignment -->
Update 2025-10-12: Output sink implementations referenced above live under `src/elspeth/plugins/nodes/sinks/`.
<!-- END UPDATE -->

## Added 2025-10-12 – Telemetry & Analytics Controls
- **Retry exhaustion evidence** – Middleware invokes `on_retry_exhausted` hooks with serialized history, emitting `llm_retry_exhausted` rows that include attempts, errors, and trace IDs for SOC pipelines (`src/elspeth/core/experiments/runner.py:531`, `src/elspeth/plugins/llms/middleware_azure.py:233`).[^sec-retry-evidence-2025-10-12]
- **Analytics provenance** – The analytics report sink consolidates retry summaries, cost totals, early-stop reasons, and baseline comparisons so auditors receive a single tamper-evident package (`src/elspeth/plugins/outputs/analytics_report.py:69`, `src/elspeth/plugins/outputs/analytics_report.py:116`).[^sec-analytics-provenance-2025-10-12]
- **Classification propagation** – Artifact bindings enforce security level compatibility at dependency resolution time, preventing low-clearance sinks from accessing sensitive artifacts even when chained (`src/elspeth/core/pipeline/artifact_pipeline.py:167`, `src/elspeth/core/security/__init__.py:27`).[^sec-classification-2025-10-12]

## Suite Reporting & Evidence
- **Consolidated validation** – Suite reporting writes validation results, comparative analysis, failure breakdowns, and executive summaries to immutable files for accreditation reviews (`src/elspeth/tools/reporting.py:33`, `src/elspeth/tools/reporting.py:117`, `src/elspeth/tools/reporting.py:207`).[^sec-suite-reporting-2025-10-12]
- **Evidence parity** – Generated analytics/visual/Excel artifacts mirror sink outputs, ensuring the same sanitisation and security metadata appears in both real-time pipeline runs and offline accreditation packages (`src/elspeth/tools/reporting.py:138`, `src/elspeth/tools/reporting.py:170`).[^sec-analytics-provenance-2025-10-12]
- **CLI gating** – Report generation is only enabled when `--reports-dir` is supplied, making it explicit when accreditation artefacts are produced and ensuring logs capture the destination (`src/elspeth/cli.py:392`).[^sec-suite-reporting-2025-10-12]

## Gaps & Hardening Opportunities
- **Credential rotation** – Secrets are currently read directly from environment variables; integration with managed secret stores (e.g., Azure Key Vault) or signed credential files should be prioritised (`config/blob_store.yaml:4`, `src/elspeth/plugins/outputs/signed.py:107`).
- **Middleware execution order** – Middleware is executed in the order defined by configuration; formalising precedence or conflict detection would prevent misconfiguration when multiple enforcement layers are active (`src/elspeth/core/experiments/runner.py:493`).
- **LLM response sanitisation** – While validation plugins exist, default stacks do not enforce JSON schemes. Accrediting authorities may require baseline validators for each prompt pack instead of optional opt-in (`src/elspeth/plugins/experiments/validation.py:47`).

## Update History
- 2025-10-12 – Update 2025-10-12: Added middleware safeguard inventory, suite reporting evidence controls, and Azure telemetry references aligned with updated architecture diagrams.
- 2025-10-12 – Documented Azure telemetry audit hooks, analytics reporting controls, and schema validation enhancements supporting accreditation evidence.
- 2025-10-12 – Update 2025-10-12: Added managed identity, prompt hygiene, artifact clearance, and middleware safeguard annotations with cross-document footnotes.

[^sec-azure-ingest-2025-10-12]: Update 2025-10-12: Also referenced in docs/architecture/threat-surfaces.md (Update 2025-10-12: Storage Interfaces).
[^sec-llm-2025-10-12]: Update 2025-10-12: Credential handling aligns with docs/architecture/threat-surfaces.md (Update 2025-10-12: LLM Providers).
[^sec-repo-2025-10-12]: Update 2025-10-12: Repository hardening further detailed in docs/architecture/plugin-security-model.md (Update 2025-10-12: Output Sinks).
[^sec-signed-auth-2025-10-12]: Update 2025-10-12: Signing key enforcement tied to docs/compliance/CONTROL_INVENTORY.md.
[^sec-config-validation-2025-10-12]: Update 2025-10-12: Schema pipeline shown in docs/architecture/configuration-security.md (Update 2025-10-12: Loader Safeguards).
[^sec-prompt-2025-10-12]: Update 2025-10-12: Prompt hygiene flow connected to docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Runner Pipeline).
[^sec-validation-plugins-2025-10-12]: Update 2025-10-12: Validation plugin lifecycle outlined in docs/architecture/plugin-security-model.md (Update 2025-10-12: Validation Plugins).
[^sec-suite-governance-2025-10-12]: Update 2025-10-12: Suite validation path cross-referenced in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Suite Lifecycle).
[^sec-output-sanitize-2025-10-12]: Update 2025-10-12: Sanitisation coverage mirrored in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Artifact Rehydration).
[^sec-manifest-2025-10-12]: Update 2025-10-12: Manifest hygiene summarised in docs/architecture/component-diagram.md (Update 2025-10-12: Artifact Tokens).
[^sec-repo-payload-2025-10-12]: Update 2025-10-12: Dry-run guidance linked to docs/reporting-and-suite-management.md (Update 2025-10-12: Repository Outputs).
[^sec-rate-limiters-2025-10-12]: Update 2025-10-12: Concurrency gating visualised in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Parallel Execution Gate).
[^sec-cost-tracker-2025-10-12]: Update 2025-10-12: Cost summaries surfaced in docs/architecture/audit-logging.md (Update 2025-10-12: Cost Telemetry).
[^sec-suite-overrides-2025-10-12]: Update 2025-10-12: Suite override mechanics described in docs/architecture/plugin-security-model.md (Update 2025-10-12: Control Registry).
[^sec-prompt-shield-2025-10-12]: Update 2025-10-12: Prompt shield policies depicted in docs/architecture/component-diagram.md (Update 2025-10-12: Middleware Chain).
[^sec-content-safety-2025-10-12]: Update 2025-10-12: Content safety trust boundary shown in docs/architecture/data-flow-diagrams.md sequence diagrams.
[^sec-audit-2025-10-12]: Update 2025-10-12: Audit telemetry recorded in docs/architecture/audit-logging.md (Update 2025-10-12: Middleware Telemetry).
[^sec-health-monitor-2025-10-12]: Update 2025-10-12: Health metrics referenced in docs/architecture/audit-logging.md (Update 2025-10-12: Health Monitoring).
[^sec-hmac-2025-10-12]: Update 2025-10-12: Signing implementation expanded in docs/compliance/CONTROL_INVENTORY.md.
[^sec-clearance-2025-10-12]: Update 2025-10-12: Clearance model visualised in docs/architecture/component-diagram.md (Update 2025-10-12: Artifact Pipeline).
[^sec-artifact-deps-2025-10-12]: Update 2025-10-12: Dependency validation sequence in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Artifact Rehydration).
[^sec-retry-2025-10-12]: Update 2025-10-12: Retry recording flow tracked in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Retry, Early Stop, and Telemetry Flow).
[^sec-checkpoint-2025-10-12]: Update 2025-10-12: Checkpoint handling mapped in docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Checkpoint Loop).
[^sec-early-stop-2025-10-12]: Update 2025-10-12: Early-stop plugins catalogued in docs/architecture/plugin-security-model.md (Update 2025-10-12: Early-Stop Lifecycle).
[^sec-failure-2025-10-12]: Update 2025-10-12: Failure containment mirrored in docs/architecture/migration-guide.md (Update 2025-10-12: on_error Behaviour).
[^sec-retry-evidence-2025-10-12]: Update 2025-10-12: Retry evidence logging summarised in docs/architecture/audit-logging.md (Update 2025-10-12: Retry Exhaustion Events).
[^sec-analytics-provenance-2025-10-12]: Update 2025-10-12: Analytics provenance described in docs/reporting-and-suite-management.md (Update 2025-10-12: Analytics Outputs).
[^sec-classification-2025-10-12]: Update 2025-10-12: Classification propagation tied to docs/architecture/component-diagram.md (Update 2025-10-12: Artifact Pipeline).
[^sec-suite-reporting-2025-10-12]: Update 2025-10-12: Suite reporting CLI usage and artefact inventory detailed in docs/reporting-and-suite-management.md (Update 2025-10-12: Suite Reporting Exports).
