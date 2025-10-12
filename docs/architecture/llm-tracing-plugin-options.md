# LLM Tracing Plugin Options

<!-- UPDATE 2025-10-12: Initial option catalogue and evaluation -->

## Option A – OpenTelemetry Trace Middleware (`opentelemetry_trace`)

- **Profile**: Official (open-source friendly).
- **Integration Point**: LLM middleware stack (`src/elspeth/core/llm/middleware.py`).
- **Purpose**: Emit OpenTelemetry spans per `generate()` call with structured attributes for prompts, responses, retries, and cost metrics.

### Configuration Surface

| Option | Description |
| --- | --- |
| `exporter` | Target exporter (`otlp_grpc`, `otlp_http`, `jaeger`), defaults to OTLP/HTTP. |
| `endpoint` | Collector endpoint URL; supports environment interpolation (e.g., `${OTEL_EXPORTER_OTLP_ENDPOINT}`). |
| `headers` | Optional headers for collectors requiring auth tokens. |
| `service_name` | Overrides default tracer service name (`elspeth-llm`). |
| `sample_rate` | Probability sampler (0.0–1.0) for high-volume runs. |
| `redact_prompts` | Bool; when true replace prompt/response bodies with hashes while retaining token counts. |
| `include_cost_metrics` | Bool; attach prompt/completion cost metrics when cost tracker is enabled. |

### Fit Considerations

- **Pros**:
  - Portable across on-prem and cloud collectors; aligns with CNCF standards.
  - Reuses existing OpenTelemetry SDKs; dev teams familiar with OTLP pipelines benefit immediately.
  - Fine-grained sampling controls mitigate privacy/performance concerns.
  - Easy to correlate with existing span data from other services.
- **Cons**:
  - Requires operators to run/maintain OTLP collectors; self-hosting adds overhead.
  - Complex attribute sets risk leaking sensitive content if redaction misconfigured.
  - Additional middleware latency from synchronous span exports unless batching enabled.

## Option B – Azure Monitor Trace Middleware (`azure_monitor_trace`)

- **Profile**: Protected (Azure-first).
- **Integration Point**: LLM middleware with dependency on `azure-monitor-opentelemetry`.
- **Purpose**: Push trace spans and cost telemetry to Azure Application Insights / Monitor.

### Configuration Surface

| Option | Description |
| --- | --- |
| `connection_string` | Application Insights connection string; alternative to instrumentation key. |
| `managed_identity` | Bool; when true, use Azure Managed Identity/DefaultAzureCredential. |
| `tenant_id` | Optional tenant hint for managed identity flows. |
| `log_prompts` | Enum (`none`, `hash`, `full`) to control prompt payload capture. |
| `track_dependencies` | Bool; emit dependency spans for downstream HTTP calls (e.g., embeddings). |
| `sampling_percentage` | Percentage-based sampling (0–100). |
| `cost_metric_namespace` | Custom metric namespace for cost telemetry (default `Elspeth/LLM`). |

### Fit Considerations

- **Pros**:
  - Native integration with existing Azure telemetry dashboards and alerting.
  - Managed identity support reduces secret handling for government workloads.
  - Automatic linking with Azure Monitor / Log Analytics for unified reporting.
  - Built-in compliance tooling (Customer Managed Keys, data residency controls).
- **Cons**:
  - Azure-only; limits portability for hybrid/multi-cloud deployments.
  - SDK introduces heavier dependency footprint and potential version conflicts.
  - Application Insights sampling can delay near-real-time analysis at low volumes.
  - Licensing/ingestion costs may rise with high trace volumes.

## Option C – Structured Trace Sink (`structured_trace_sink`)

- **Profile**: Dual-tier (official/protected) as a general-purpose result sink or utility plugin.
- **Integration Point**: Result sink that consumes trace envelopes from middleware via artifact chaining.
- **Purpose**: Persist sanitized request/response envelopes, retry metadata, and decision lineage to signed NDJSON bundles for regulated environments without external telemetry dependencies.

### Configuration Surface

| Option | Description |
| --- | --- |
| `base_path` | Filesystem or object-store base path for trace bundles. |
| `bundle_name` | Optional bundle identifier (defaults to timestamped run id). |
| `include_raw_prompts` | Bool; store full prompt/response content (default `false`). |
| `redaction_rules` | List of regex or JSONPath rules for scrubbing sensitive content. |
| `signing` | Nested configuration enabling `SignedArtifactSink` integration (key ref, algorithm). |
| `rotate_every` | Max records per bundle before rolling to a new file. |
| `retention_days` | Optional auto-expiry metadata for downstream retention tooling. |

### Fit Considerations

- **Pros**:
  - Works fully offline/air-gapped; no external services required.
  - Aligns with existing artifact signing/audit workflows (e.g., sec. controls documentation).
  - Enables bespoke downstream analysis (e.g., Pandas, Splunk) without vendor lock-in.
  - Fine-grained redaction and signing controls reduce accidental data exposure.
- **Cons**:
  - Storage/rotation management falls on operators; large experiment runs can create sizable bundles.
  - Access control and distribution must be managed separately (no built-in query UI).
  - Requires middleware cooperation to emit the structured trace events.
  - Less suited for real-time observability; more of a forensic/compliance tool.

<!-- END UPDATE -->

## Update History

- 2025-10-12 – Documented LLM tracing plugin options (OpenTelemetry middleware, Azure Monitor middleware, structured trace sink) with configuration surfaces and trade-off analysis.
