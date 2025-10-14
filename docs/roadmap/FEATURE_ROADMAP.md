# Feature Roadmap & Plugin Taxonomy

This roadmap outlines the planned expansion of Elspeth’s capabilities so stakeholders can track feature coverage, vendor alignment, and upcoming workstreams. It complements the compliance roadmap by focusing on functional growth across datasources, LLM clients, middleware, metrics, sinks, and observability.

## 1. Feature-Oriented Taxonomy

| Feature Area | Current Coverage | Gaps & Opportunities | Backlog Actions |
|--------------|-----------------|----------------------|-----------------|
| **Datasources** | Local CSV (`csv_local`), Azure Blob (`blob`) | No connectors for AWS S3, Google Cloud Storage, databases, or streaming feeds. Security labelling is Azure-centric. | • Add S3 and GCS plugins with security tagging parity.<br>• Introduce read-only JDBC datasource (Postgres/SQL Server) with query allowlists.<br>• Publish datasource capability and threat matrix. |
| **LLM Clients** | Azure OpenAI (`azure_openai`), Mock (`mock`) | Missing OpenAI REST, Anthropic Claude, AWS Bedrock, Google Vertex AI, Cohere, and OSS inference runners (Hugging Face TGI, vLLM). | • Implement vendor adapters with credential isolation.<br>• Normalise moderation/safety metadata across clients.<br>• Document regional endpoints and logging behaviour. |
| **Request Middleware** | Prompt shield, audit logger, Azure content safety, health monitor | No vendor-neutral moderation, policy-as-code enforcement, or dynamic routing. Limited telemetry streaming. | • Add moderation middleware for OpenAI, Google Safety, AWS Guardrails.<br>• Integrate policy engine (OPA/Rego or Cedar) for Allow/Deny checks.<br>• Build real-time telemetry exporter (OpenTelemetry OTLP). |
| **Row Plugins / Metrics** | Score extractor, score stats, recommendation, agreement/power/distribution extras | Missing cost/latency analytics, fairness metrics, human QA outcomes. | • Add cost summary aggregator (tokens, currency).<br>• Ship latency/reliability tracker.<br>• Introduce fairness/bias metrics plugin. |
| **Baselines & Comparisons** | Frequentist (t-tests, effect size), Bayesian (optional extras) | No sequential testing, counterfactual modelling, or KPI reconciliation. | • Implement sequential probability ratio baseline.<br>• Add business KPI comparison plugin with custom formulas.<br>• Document usage patterns in analytics docs. |
| **Early Stop Logic** | Threshold-based plugin | No multi-metric policies, hysteresis, or manual override channel. | • Build composite early-stop (multi metric + hysteresis).<br>• Expose CLI/API control to pause/resume suites.<br>• Log early-stop decisions in telemetry stream. |
| **Artifact Sinks** | CSV, Excel, signed bundle, Azure blob, repo exporters, zip, analytics JSON/Markdown, visual analytics (PNG/HTML) | No streaming sink, no PDF generator, limited support for gov record systems (SharePoint/PROTECTED). | • Create OpenTelemetry/Prometheus streaming sink.<br>• Add PDF/HTML summary sink (WeasyPrint/Sphinx pipeline).<br>• Explore SharePoint/OneDrive/GovCMS sinks with clearance checks. |
| **Suite Orchestration** | Template creation, config export, suite defaults merge | No scheduler, resume-from-checkpoint, or cross-suite dependencies. | • Implement suite scheduler with deferred runs.<br>• Add checkpoint/resume support for partial suites.<br>• Visualise suite dependency graphs. |
| **Governance & Compliance** | Signed bundles, manifest metadata | No plugin provenance attestations, approval workflow, or compliance exporter. | • Enforce plugin signing/attestation metadata.<br>• Build compliance exporter (ISM/Essential Eight evidence zip).<br>• Publish certification checklist for new plugins (see [plugin hardening principles](notes/plugin-hardening-principles.md)). |
| **Observability** | CLI logs, retry summaries in payload metadata | No central telemetry, dashboards, or alerting hooks. | • Deliver telemetry middleware & sink (see §3).<br>• Provide Grafana dashboards/alert rules.<br>• Update ops docs with observability runbook. |

## 2. Vendor-Oriented Taxonomy

| Plugin Type | Current Vendors | High-Priority Additions | Notes |
|-------------|----------------|-------------------------|-------|
| **LLM Providers** | Azure OpenAI, mock | OpenAI (REST), Anthropic Claude, AWS Bedrock, Google Vertex AI, Cohere, Hugging Face TGI/vLLM, llama.cpp API | Align adapters with `LLMClientProtocol`, secure credential handling, and moderation hooks. |
| **Content Safety** | Azure Content Safety | OpenAI Moderation, Google Cloud Content Safety, AWS Guardrails/Comprehend, Hugging Face moderation models | Deliver as middleware so safety events share a common schema. |
| **Datasources** | Azure Blob, local filesystem | AWS S3, Google Cloud Storage, Azure Data Lake Gen2, Postgres/SQL Server, BigQuery | Ensure each connector enforces security labelling and supports managed identities or workload identities. |
| **Telemetry & Monitoring** | None | OpenTelemetry OTLP, Prometheus pushgateway, Elastic APM, Grafana Alloy | Provide both middleware (request metrics) and sinks (artifact metrics), with TLS/auth options. |
| **Artifact Destinations** | Local (CSV/Excel/ZIP), Azure Blob, GitHub/Azure DevOps repos | AWS S3, Google Cloud Storage, SharePoint/OneDrive, Gov record-keeping APIs | Honour security levels; support signed uploads where mandated. |
| **Secrets & Identity** | Environment variables, Azure managed identity | AWS IAM roles, GCP service accounts, HashiCorp Vault, Azure Key Vault secret resolvers | Extend plugin configuration to reference secret providers uniformly. |
| **Cost/Billing** | Custom cost tracker | OpenAI usage API, Anthropic usage, AWS Cost Explorer, Google Cloud billing | Reconcile real vendor bills with orchestrator estimates; expose deltas via aggregators. |

## 3. Telemetry Plugin Blueprint

To provide real-time observability, we will deliver a telemetry middleware and optional sink that stream structured metrics into open-source telemetry backends.

### Middleware

- `TelemetryMiddleware` implements `LLMClientMiddlewareProtocol`.
- Captures request/response timestamps, token counts, retries, status codes, security level.
- Emits spans and metrics via the OpenTelemetry SDK (OTLP over HTTP/gRPC).
- Configurable redaction (omit prompt/response bodies) and attribute schema (`suite`, `experiment`, `run_id`).

### Sink

- `TelemetryResultSink` listens to artifact pipeline events.
- Streams aggregate counters (artifacts produced, sink failures, size) and run-level summaries.
- Supports Prometheus pushgateway or OTLP metrics export.

### Collector & Dashboards

- Ship sample configuration for Grafana Tempo (traces), Prometheus (metrics), and Loki (logs).
- Provide Grafana dashboard JSON (latency, cost, error rates) and Alertmanager rule examples.
- Document secure deployment (TLS, authentication, network segregation).

### Security Considerations

- Allow disabling telemetry per security level (e.g., `SECRET` runs stay offline).
- Ensure TLS/mtls configuration for collectors and redact sensitive payloads by default.
- Record telemetry policy decisions in observability documentation.

## 4. Implementation Plan

1. **Taxonomy Inventory Refresh**  
   - Update `docs/architecture/plugin-catalogue.md` to reflect current and planned plugins, marking status (`GA`, `Beta`, `Planned`).
   - Publish a capability matrix in the future Sphinx docs using the tables above.

2. **Backlog Kick-off**  
   - Prioritise telemetry middleware, non-Azure LLM adapters, and multi-cloud datasources for the next release train.  
   - Produce engineering specs for each plugin (requirements, dependencies, security checks, test plan).

3. **Vendor Alignment**  
   - Track vendor API updates (Anthropic, Bedrock, Vertex).  
   - Ensure data residency and logging behaviour align with government obligations (AU regions, audit logging disabled or redirected).

4. **Governance & Certification**  
   - Create a plugin certification checklist covering coding standards, security review, documentation, and automated tests.  
   - Record plugin provenance (version, maintainer, signature) in the registry metadata.

5. **Documentation & Communication**  
   - Integrate this roadmap into the future Sphinx site under a “Plugins” section.  
   - Update release notes with plugin milestones and telemetry rollout status.  
   - Share Grafana dashboards and telemetry runbooks with operations teams once available.

This feature roadmap should be reviewed quarterly and coordinated with agency stakeholders to ensure development priorities align with operational needs and vendor onboarding timelines.
