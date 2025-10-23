# Data Flow Diagrams

## Experiment Execution Flow
```mermaid
sequenceDiagram
    autonumber
    participant DS as Datasource.load()
    participant OR as ExperimentRunner
    participant MW as Middleware Stack
    participant LLM as LLM Client
    participant AP as ArtifactPipeline
    participant SK as Result Sinks

    DS->>OR: DataFrame + security_level
    OR->>OR: Compile prompts & prepare context
    Note over OR,MW: Update 2025-10-12: Trust boundary – prompts validated before middleware execution
    loop Per Row / Criteria
        OR->>MW: before_request(LLMRequest)
        Note over MW,LLM: Update 2025-10-12: Untrusted LLM provider; middleware applies shield/content safety
        MW->>LLM: generate(system_prompt, user_prompt, metadata)
        LLM-->>MW: response + raw usage
        MW-->>OR: after_response(response)
        OR->>OR: apply retry, validation, cost tracking
    end
    OR->>AP: payload + artifacts metadata
    AP->>SK: ordered write()
    SK-->>AP: collect_artifacts()
```

- Datasources attach classification metadata that is later folded into sink metadata (`src/elspeth/plugins/datasources/csv_local.py:35`, `src/elspeth/core/experiments/runner.py:208`).[^df-classification-2025-10-12]
<!-- UPDATE 2025-10-12: Datasource path alignment -->
Update 2025-10-12: Datasource implementations are housed under `src/elspeth/plugins/nodes/sources/` (`csv_local.py`, `csv_blob.py`, `blob.py`); behaviour remains unchanged.
<!-- END UPDATE -->
- Middleware can veto, mask, or audit prompts before the LLM is contacted, forming the first trust boundary for untrusted input (`src/elspeth/plugins/llms/middleware.py:110`, `src/elspeth/plugins/llms/middleware.py:233`).[^df-middleware-2025-10-12]
<!-- UPDATE 2025-10-12: Middleware module relocation -->
Update 2025-10-12: Middleware hooks reside in `src/elspeth/plugins/nodes/transforms/llm/middleware.py` and `middleware_azure.py` after the namespace migration.
<!-- END UPDATE -->
- Cost tracking and rate limiting wrap each LLM invocation with deterministic retry state (`src/elspeth/core/experiments/runner.py:498`, `src/elspeth/core/experiments/runner.py:520`, `src/elspeth/core/controls/rate_limit.py:74`).[^df-retry-2025-10-12]
- The artifact pipeline enforces dependency ordering and classification-aware access before sinks persist or aggregate results (`src/elspeth/core/pipeline/artifact_pipeline.py:192`, `src/elspeth/core/pipeline/artifact_pipeline.py:201`).[^df-pipeline-2025-10-12]
<!-- UPDATE 2025-10-12: Runner metadata -->
- `ExperimentRunner` attaches `retry_summary`, `cost_summary`, and `early_stop` payloads to the execution metadata so sinks, analytics reports, and telemetry consumers can reproduce control decisions (`src/elspeth/core/experiments/runner.py:170`, `src/elspeth/core/experiments/runner.py:198`, `src/elspeth/core/experiments/runner.py:214`).[^df-runner-metadata-2025-10-12]
<!-- Update 2025-10-12: When concurrency is enabled, rows enter a worker pool governed by `concurrency_config` thresholds, and early-stop plugins can halt submission once metrics breach criteria (`src/elspeth/core/experiments/runner.py:365`, `src/elspeth/core/experiments/runner.py:248`). -->

### Update 2025-10-12: Ingress Classification Flow
- DataFrames inherit `attrs["security_level"]` from datasources; runner resolves the final clearance using `resolve_security_level` before artifact dispatch (`src/elspeth/core/experiments/runner.py:200`, `src/elspeth/core/security/__init__.py:21`).

### Update 2025-10-12: Runner Pipeline
- Prompt compilation, middleware invocation, validation, and artifact emission follow the sequence above, mirroring `ExperimentRunner.run` control flow (`src/elspeth/core/experiments/runner.py:65`, `src/elspeth/core/experiments/runner.py:176`, `src/elspeth/core/experiments/runner.py:464`).

### Update 2025-10-12: Parallel Execution Gate
- `concurrency_config.enabled`, `backlog_threshold`, and rate limiter utilisation guard thread pool submission (`src/elspeth/core/experiments/runner.py:365`, `src/elspeth/core/experiments/runner.py:428`, `src/elspeth/core/controls/rate_limit.py:118`).

### Update 2025-10-12: Checkpoint Loop
- Checkpointed identifiers are read via `_load_checkpoint` and appended on success, preventing duplicate LLM submissions on reruns (`src/elspeth/core/experiments/runner.py:75`, `src/elspeth/core/experiments/runner.py:682`).

Update 2025-10-12: Retry, Early Stop, and Telemetry Flow — Cross-reference docs/architecture/audit-logging.md (Update 2025-10-12: Retry Exhaustion Events) for log emission paths.

## Added 2025-10-12 – Retry, Early Stop, and Telemetry Flow
```mermaid
sequenceDiagram
    autonumber
    participant OR as ExperimentRunner
    participant MW as Middleware Chain
    participant RL as RateLimiter
    participant LLM as LLM Client
    participant ES as EarlyStop Plugins
    participant AP as ArtifactPipeline
    participant AR as Analytics Sink
    participant AZ as AzureEnvironmentMiddleware

    loop Attempt (max_attempts)
        OR->>RL: acquire(metadata)
        RL-->>OR: token context
        OR->>MW: before_request(LLMRequest)
        Note over OR,MW: Update 2025-10-12: Retry metadata captured before leaving trusted boundary
        MW->>LLM: generate(...)
        Note over MW,LLM: Update 2025-10-12: Content safety / prompt shield enforce outbound policy
        LLM-->>MW: response / error
        MW-->>OR: after_response(response)
        OR->>OR: record retry metadata
        alt success
            OR->>ES: check(record.metrics)
            ES-->>OR: continue / trigger(reason)
            OR->>AP: execute(payload, metadata)
            AP->>AR: collect_artifacts()
            AZ->>AZ: log experiment_complete / retry_summary
            break
        else retriable error
            OR-->>OR: backoff & increment attempts
        end
    end
    OR-->>MW: notify_retry_exhausted (metadata)
    MW->>AZ: log llm_retry_exhausted(history)
```

### Update 2025-10-12: Baseline Evaluation
- Suite runners persist baseline payloads and compare variants via configured plugins (`src/elspeth/core/experiments/suite_runner.py:304`, `src/elspeth/core/experiments/plugin_registry.py:158`), emitting telemetry and analytics artifacts downstream.

## Credential and Secret Flow
```mermaid
flowchart LR
    subgraph Config
        SettingsYAML["settings.yaml"]
        PromptPack["Prompt Packs"]
        BlobProfile["blob_store.yaml"]
    end

    subgraph Runtime
        Loader["Config Loader"]
        Registry["Plugin Registry"]
        Plugins["Datasource / LLM / Sink Plugins"]
    end

    subgraph SecretStores
        EnvVars["Environment Variables"]
        Vault["Azure Identity / SAS Tokens"]
    end

    SettingsYAML --> Loader
    PromptPack --> Loader
    BlobProfile --> Loader
    Loader --> Registry
    Registry --> Plugins
    EnvVars -.resolve.-> Plugins
    Vault -.credential.-> Plugins

    classDef secret fill:#ffe9d6,stroke:#f08a24;
    class SecretStores secret;
```

- Loader merges profile and prompt pack settings, then invokes registry factories that validate plugin schemas before instantiation (`src/elspeth/config.py:48`, `src/elspeth/core/registries/__init__.py:91`).[^df-config-loader-2025-10-12]
- Blob datasources resolve SAS tokens or managed identity credentials at runtime, preventing raw secrets from living in code paths; the same pattern is used for GitHub/Azure DevOps tokens and signing keys (`config/blob_store.yaml:4`, `src/elspeth/plugins/outputs/repository.py:149`, `src/elspeth/plugins/outputs/signed.py:107`).[^df-blob-2025-10-12]
- Azure-specific clients rely on `azure-identity` if explicit credentials are absent, aligning with managed identity deployments while still supporting SAS tokens for desktops (`src/elspeth/datasources/blob_store.py:125`, `src/elspeth/plugins/llms/azure_openai.py:25`).[^df-azure-2025-10-12]

### Update 2025-10-12: Suite Lifecycle
- `SuiteReportGenerator.generate_all_reports` and CLI `--reports-dir` invocations reuse the credential graph for analytics, repository, and signing sinks (`src/elspeth/tools/reporting.py:19`, `src/elspeth/cli.py:392`).
<!-- Update 2025-10-12: Suite export/reporting commands inherit the same credential flow when emitting analytics or repository artifacts, so secure stores must cover `analytics_report` and repository PAT tokens (`src/elspeth/cli.py:205`, `src/elspeth/plugins/outputs/analytics_report.py:28`). -->

## Added 2025-10-12 – Suite Reporting Export Flow
```mermaid
flowchart LR
    CLI["CLI (`python -m elspeth.cli --reports-dir`)"] --> SuiteRunner
    SuiteRunner[ExperimentSuiteRunner] --> ResultsMap["Experiment Payload Map"]
    ResultsMap --> SuiteReport[SuiteReportGenerator.generate_all_reports]
    SuiteReport --> Validation["consolidated/validation_results.json"]
    SuiteReport --> Comparative["comparative_analysis.json"]
    SuiteReport --> Recommendations["recommendations.json"]
    SuiteReport --> FailureReport["failure_analysis.json"]
    SuiteReport --> ExecSummary["executive_summary.md"]
    SuiteReport --> ExcelReport["analysis.xlsx"]
    SuiteReport --> AnalyticsArtifacts["analytics_report.json / .md"]
    SuiteReport --> VisualArtifacts["visual_report/*.png / *.html"]
    SuiteReport --> Consolidated["experiment/*/stats.json"]
    VisualArtifacts --> Telemetry["AzureEnvironmentMiddleware (log_table)"]
    AnalyticsArtifacts --> AnalyticsSink
    ExcelReport --> ExcelSink
    classDef suite fill:#eef5ff,stroke:#3a6cf0,stroke-width:1px;
    class SuiteReport,Validation,Comparative,Recommendations,FailureReport,ExecSummary,ExcelReport,AnalyticsArtifacts,VisualArtifacts,Consolidated suite;
```

### Update 2025-10-12: Suite Reporting Outputs
- `SuiteReportGenerator` reuses experiment payloads, aggregates, and baseline comparisons to emit consolidated JSON, Markdown, Excel, and visual artifacts suitable for accreditation packages (`src/elspeth/tools/reporting.py:19`, `src/elspeth/tools/reporting.py:117`, `src/elspeth/tools/reporting.py:207`). The CLI dispatch lives at `src/elspeth/cli.py:392`, and tests assert report structure in `tests/test_suite_reporter.py`.[^df-suite-reporting-2025-10-12]

## Artifact Lifecycle
```mermaid
flowchart TD
    Results["Runner Payload\n(results, aggregates, metadata)"]
    Pipeline["ArtifactPipeline"]
    SinkCSV["CSV Sink\n(sanitises formulas)"]
    SinkSigned["Signed Artifact Bundle"]
    SinkRepo["Repository Sink\n(dry-run or live commit)"]
    SinkAnalytics["Analytics Report Sink"]
    SinkVisual["Visual Analytics Sink"]
    SinkExcel["Excel Result Sink"]
    SinkZip["ZIP Bundle Sink"]
    SinkBlob["Blob Storage Sink"]

    Results --> Pipeline
    Pipeline --> SinkCSV
    Pipeline --> SinkSigned
    Pipeline --> SinkRepo
    Pipeline --> SinkAnalytics
    Pipeline --> SinkVisual
    Pipeline --> SinkExcel
    Pipeline --> SinkZip
    Pipeline --> SinkBlob
    SinkCSV -->|"produces file/csv"| Pipeline
    SinkSigned -->|"produces signed bundle"| Pipeline
    SinkRepo -->|"dry_run manifests"| Pipeline
    SinkAnalytics -->|"produces analytics_report"| Pipeline
    SinkVisual -->|"produces visual artifacts"| Pipeline
    SinkExcel -->|"produces file/xlsx"| Pipeline
    SinkZip -->|"produces file/zip"| Pipeline
    SinkBlob -->|"uploads manifests/artifacts"| Pipeline
```

- CSV outputs escape spreadsheet metacharacters and record sanitisation metadata for downstream auditors (`src/elspeth/plugins/outputs/csv_file.py:49`, `src/elspeth/plugins/outputs/_sanitize.py:18`).[^df-csv-2025-10-12]
- Signed artifacts emit HMAC digests and manifests containing response metadata, enabling tamper detection when results are redistributed (`src/elspeth/plugins/outputs/signed.py:37`, `src/elspeth/plugins/outputs/signed.py:75`).[^df-signed-2025-10-12]
- Repository sinks support dry-run inspection by caching payload manifests, reducing blast radius during accreditation rehearsals (`src/elspeth/plugins/outputs/repository.py:70`, `src/elspeth/plugins/outputs/repository.py:124`).[^df-repo-2025-10-12]
<!-- UPDATE 2025-10-12: Analytics/visual sinks -->
- Analytics report sinks emit JSON/Markdown summaries of retry, cost, aggregate, and baseline data which Suite reports and auditors consume (`src/elspeth/plugins/outputs/analytics_report.py:28`, `src/elspeth/plugins/outputs/analytics_report.py:62`).[^df-analytics-2025-10-12]
- Visual analytics sinks transform aggregate statistics into PNG/HTML artifacts that embed retry and cost metadata for offline evidence (`src/elspeth/plugins/outputs/visual_report.py:63`, `src/elspeth/plugins/outputs/visual_report.py:205`).[^df-visual-2025-10-12]
- Excel outputs consolidate flattened rows, manifests, and aggregate metrics while retaining sanitisation markers (`src/elspeth/plugins/outputs/excel.py:45`, `src/elspeth/plugins/outputs/excel.py:146`).[^df-excel-2025-10-12]
- ZIP bundle sinks package raw results, manifests, CSV excerpts, and collected upstream artifacts with consistent sanitisation metadata (`src/elspeth/plugins/outputs/zip_bundle.py:45`, `src/elspeth/plugins/outputs/zip_bundle.py:132`).[^df-zip-2025-10-12]
- Blob sinks mirror artifact payloads into Azure storage, propagating security level metadata and optional manifests for traceability (`src/elspeth/plugins/outputs/blob.py:127`, `src/elspeth/plugins/outputs/blob.py:173`).[^df-blob-sink-2025-10-12]
<!-- Update 2025-10-12: Analytics sinks and zip bundles now register `produces` descriptors so the pipeline can chain artifacts while enforcing classification gates (`src/elspeth/plugins/outputs/analytics_report.py:62`, `src/elspeth/plugins/outputs/zip_bundle.py:41`, `src/elspeth/core/pipeline/artifact_pipeline.py:167`). -->
<!-- Update 2025-10-12: Visual analytics sink converts score summaries into PNG/HTML charts with inline metadata, inheriting pipeline security levels (`src/elspeth/plugins/outputs/visual_report.py:63`, `src/elspeth/plugins/outputs/visual_report.py:180`). -->

### Update 2025-10-12: Artifact Rehydration
- `ArtifactPipeline` stores produced artifacts and rehydrates them for downstream sinks through `collect_artifacts`, ensuring sanitisation metadata and security levels persist (`src/elspeth/core/pipeline/artifact_pipeline.py:120`, `src/elspeth/core/interfaces.py:101`).
<!-- UPDATE 2025-10-12: Artifact descriptor relocation -->
Update 2025-10-12: Protocol helpers invoked during rehydration are defined in `src/elspeth/core/base/protocols.py:237-309`; `core/interfaces.py` remains for historical reference.
<!-- END UPDATE -->

## Update History
- 2025-10-12 – Update 2025-10-12: Added suite reporting export flow, expanded artifact lifecycle coverage (analytics/visual/excel/zip/blob), and documented runner metadata propagation for accreditation evidence.
- 2025-10-12 – Added retry/early-stop telemetry sequence, documented concurrency impacts, and noted analytics artifact propagation.
- 2025-10-12 – Update 2025-10-12: Annotated trust boundaries, added credential and artifact footnotes, and cross-referenced sanitation/security documentation.

[^df-classification-2025-10-12]: Update 2025-10-12: Classification handling ties to docs/architecture/architecture-overview.md Core Principles.
[^df-middleware-2025-10-12]: Update 2025-10-12: See docs/architecture/security-controls.md (Update 2025-10-12: Middleware Safeguards).
[^df-retry-2025-10-12]: Update 2025-10-12: Retry instrumentation aligns with docs/architecture/audit-logging.md (Update 2025-10-12: Retry Exhaustion Events).
[^df-pipeline-2025-10-12]: Update 2025-10-12: Dependency enforcement depicted in docs/architecture/component-diagram.md (Update 2025-10-12: Artifact Pipeline).
[^df-config-loader-2025-10-12]: Update 2025-10-12: Configuration security elaborated in docs/architecture/configuration-security.md (Update 2025-10-12: Loader Safeguards).
[^df-blob-2025-10-12]: Update 2025-10-12: Secret handling mirrored in docs/architecture/threat-surfaces.md (Update 2025-10-12: Storage Interfaces).
[^df-azure-2025-10-12]: Update 2025-10-12: Azure credential flow documented in docs/architecture/security-controls.md (Update 2025-10-12: Managed Identity).
[^df-csv-2025-10-12]: Update 2025-10-12: Sanitisation controls catalogued in docs/compliance/CONTROL_INVENTORY.md.
[^df-signed-2025-10-12]: Update 2025-10-12: Signing mechanism described in docs/architecture/security-controls.md (Update 2025-10-12: Artifact Signing).
[^df-repo-2025-10-12]: Update 2025-10-12: Repository safeguards outlined in docs/architecture/plugin-security-model.md (Update 2025-10-12: Output Sinks).
[^df-runner-metadata-2025-10-12]: Update 2025-10-12: Metadata propagation aligns with docs/architecture/audit-logging.md (Update 2025-10-12: Retry Summaries) and docs/architecture/architecture-overview.md Added 2025-10-12 – Concurrency, Checkpoints, and Retry Telemetry.
[^df-analytics-2025-10-12]: Update 2025-10-12: Analytics sink outputs detailed in docs/reporting-and-suite-management.md (Update 2025-10-12: Analytics Outputs).
[^df-visual-2025-10-12]: Update 2025-10-12: Visual artifact retention described in docs/architecture/audit-logging.md (Update 2025-10-12: Visual Evidence Logging).
[^df-excel-2025-10-12]: Update 2025-10-12: Excel workbook sanitisation references docs/architecture/security-controls.md (Update 2025-10-12: Spreadsheet Controls).
[^df-zip-2025-10-12]: Update 2025-10-12: ZIP bundle lifecycle cross-referenced in docs/compliance/CONTROL_INVENTORY.md (Update 2025-10-12: Bundle Controls).
[^df-blob-sink-2025-10-12]: Update 2025-10-12: Blob sink enforcement detailed in docs/architecture/threat-surfaces.md (Update 2025-10-12: Storage Surfaces).
[^df-suite-reporting-2025-10-12]: Update 2025-10-12: Suite reporting CLI usage illustrated in docs/reporting-and-suite-management.md (Update 2025-10-12: Suite Reporting Exports).
