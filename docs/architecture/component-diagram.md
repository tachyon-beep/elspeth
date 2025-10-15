# Component Relationships

```mermaid
graph TD
    subgraph Operator Workstation
        CLI[CLI (`python -m elspeth.cli`)]
    end

    subgraph Core Runtime
        ConfigLoader[Settings Loader]
        Orchestrator[ExperimentOrchestrator]
        Runner[ExperimentRunner]
        Pipeline[ArtifactPipeline]
    end

    subgraph Plugin Layer
        Datasource[Datasource Plugin]
        Controls[Rate/Cost Controls]
        Middleware[LLM Middleware Stack]
        LLMClient[LLM Client Plugin]
        Sinks[Result Sink Plugins]
    end

    subgraph External Services
        AzureBlob[(Azure Blob Storage)]
        AzureOpenAI[(Azure OpenAI / HTTP LLM)]
        RepoTargets[(GitHub / Azure DevOps / Local Bundle)]
    end

    CLI --> ConfigLoader
    ConfigLoader --> Datasource
    ConfigLoader --> LLMClient
    ConfigLoader --> Sinks
    ConfigLoader --> Controls
    ConfigLoader --> Middleware

    Datasource --> Orchestrator
    LLMClient --> Orchestrator
    Sinks --> Orchestrator
    Controls --> Orchestrator
    Middleware --> Orchestrator

    Orchestrator --> Runner
    Runner --> Pipeline
    Pipeline --> Sinks

    Datasource -.reads .-> AzureBlob
    LLMClient -.invokes .-> AzureOpenAI
    Sinks -.persist .-> RepoTargets

    classDef boundary stroke-dasharray: 5 5,stroke-width:2px,stroke:#888;
    class Operator\ Workstation,External\ Services boundary;
```

<!-- UPDATE 2025-10-12: Plugin namespace migration -->
Update 2025-10-12: Datasource, middleware, and sink nodes correspond to `src/elspeth/plugins/nodes/{sources,transforms,sinks}/` after repository reorganisation; legacy diagram labels are preserved for continuity with prior accreditation artefacts.
<!-- END UPDATE -->

<!-- Update 2025-10-12: Added suite orchestration, middleware lifecycle, analytics sinks, and artifact chaining -->
```mermaid
graph TD
    SuiteRunner[ExperimentSuiteRunner] -->|instantiates| ExperimentRunner
    SuiteRunner -->|baseline plugins| BaselinePlugins[Baseline Plugins]
    SuiteRunner -->|suite telemetry| AzureMiddleware[Azure Environment Middleware]
    ExperimentRunner -->|threads & checkpoints| Concurrency[Concurrency / Checkpoint Engine]
    ExperimentRunner -->|applies| EarlyStop[Early Stop Plugins]
    ExperimentRunner -->|routes metadata| RateLimiter
    ExperimentRunner -->|routes metadata| CostTracker
    ExperimentRunner -->|dispatches| MiddlewareChain[LLM Middleware Chain]
    MiddlewareChain --> LLMClient
    RateLimiter -.utilization.-> Concurrency
    CostTracker -.summary.-> AnalyticsSink[Analytics Report Sink]
    EarlyStop -.signals.-> SuiteRunner
    ExperimentRunner -->|payload| ArtifactPipeline
    ArtifactPipeline --> CsvSink
    ArtifactPipeline --> SignedSink[Signed Artifact]
    ArtifactPipeline --> RepoSink[Repository Sink]
    ArtifactPipeline --> AnalyticsSink
    ArtifactPipeline --> ZipSink[Zip Bundle]
    ArtifactPipeline --> VisualSink[Visual Analytics Sink]
    PluginRegistry[Core Registry] --> Datasource
    PluginRegistry --> Sinks
    PluginRegistry --> Controls
    SuiteRunner -->|builds| PluginRegistry
    AzureMiddleware -->|log_row/log_table| AzureML[(Azure ML Run)]
    CsvSink -.produces file/csv.-> ArtifactPipeline
    SignedSink -.produces bundle.-> ArtifactPipeline
    RepoSink -.produces data/json.-> ArtifactPipeline
    AnalyticsSink -.produces reports.-> ArtifactPipeline
    VisualSink -.produces image/png.-> ArtifactPipeline
```

<!-- UPDATE 2025-10-12: Prompt rendering, validation, and signing pipeline -->
```mermaid
graph LR
    Config[Configuration & Prompt Packs] --> Engine[PromptEngine]
    Engine --> Templates[Compiled Prompt Templates]
    Templates --> RunnerInputs[Runner Prompt Context]
    RunnerInputs --> Validators[Validation Plugins]
    Validators --> RunnerCore[ExperimentRunner]
    RunnerCore --> Sanitizer[Sanitisation Guards]
    Sanitizer --> Signing[SignedArtifactSink]
    RunnerCore --> Analytics[Analytics & Visual Sinks]
    RunnerCore --> SuiteReports[SuiteReportGenerator]
    Signing -->|HMAC manifest| AuditTrail[Audit Artefacts]
    Analytics --> Evidence[Analytics Evidence]
    SuiteReports --> Evidence
```

<!-- Update 2025-10-12: Middleware chain stages, artifact security gates, and reporting components -->
```mermaid
flowchart LR
    subgraph LLM Middleware Chain
        Audit[Audit Logger]
        Shield[Prompt Shield]
        ContentSafety[Azure Content Safety]
        Health[Health Monitor]
        AzureEnv[Azure Environment]
    end

    subgraph Runner Execution
        RunnerCore[ExperimentRunner]
        RetryMgr[Retry Manager]
        EarlyStop[Early Stop Plugins]
        Concurrency[Concurrency Controller]
    end

    subgraph Artifact Pipeline
        Resolver[Artifact Resolver]
        SecurityGate[Security Clearance Gate]
        Collector[Artifact Collector]
    end

    subgraph Reporting Sinks
        CsvSink[CSV Sink]
        SignedSink[Signed Bundle]
        AnalyticsSink[Analytics Report Sink]
        VisualSink[Visual Analytics Sink]
        RepoSink[Repository Sink]
    end

    RunnerCore --> RetryMgr
    RunnerCore --> EarlyStop
    RunnerCore --> Concurrency
    RunnerCore --> Audit
    Audit --> Shield --> ContentSafety --> Health --> AzureEnv --> LLM[LLM Client]
    RetryMgr --> RunnerCore
    Concurrency --> RunnerCore
    RunnerCore --> Resolver
    Resolver --> SecurityGate --> Collector
    Collector --> CsvSink
    Collector --> SignedSink
    Collector --> AnalyticsSink
    Collector --> VisualSink
    Collector --> RepoSink
    AnalyticsSink --> Telemetry[(Telemetry / Azure ML)]
    VisualSink --> Telemetry
```

<!-- UPDATE 2025-10-12: Suite reporting pipeline and analytics exports -->
```mermaid
flowchart LR
    CLI["CLI (`python -m elspeth.cli`)"] -->|--reports-dir| SuiteRunner
    SuiteRunner[ExperimentSuiteRunner] --> ResultsMap["Experiment Payload Map"]
    ResultsMap --> SuiteReport[SuiteReportGenerator.generate_all_reports]
    SuiteReport --> Consolidated["consolidated/*.json"]
    SuiteReport --> ExecSummary["executive_summary.md"]
    SuiteReport --> FailureReport["failure_analysis.json"]
    SuiteReport --> Comparative["comparative_analysis.json"]
    SuiteReport --> Recommendations["recommendations.json"]
    SuiteReport --> ExcelReport["analysis.xlsx"]
    SuiteReport --> VisualOutputs["visual_report/*.png / *.html"]
    SuiteReport --> AnalyticsOutputs["analytics_report.json / .md"]
    SuiteReport --> Validation["consolidated/validation_results.json"]
    VisualOutputs --> TelemetryFeed["Azure telemetry (optional)"]
    classDef derived fill:#f7faff,stroke:#4082ff,stroke-width:1px;
    class SuiteReport,Consolidated,ExecSummary,FailureReport,Comparative,Recommendations,ExcelReport,VisualOutputs,AnalyticsOutputs,Validation derived;
```

<!-- UPDATE 2025-10-12: Plugin registry boundaries -->
```mermaid
graph TD
    CoreRegistry["core.registry.Registry"] --> DatasourceFactory["create_datasource"]
    CoreRegistry --> SinkFactory["create_sink"]
    CoreRegistry --> LLMFactory["create_llm"]
    MiddlewareRegistry["core.llm.registry"] --> MiddlewareFactory["create_middleware"]
    ControlRegistry["core.controls.registry"] --> RateLimiterFactory["create_rate_limiter"]
    ControlRegistry --> CostTrackerFactory["create_cost_tracker"]
    ExperimentRegistry["core.experiments.plugin_registry"] --> RowFactory["create_row_plugin"]
    ExperimentRegistry --> AggregationFactory["create_aggregation_plugin"]
    ExperimentRegistry --> BaselineFactory["create_baseline_plugin"]
    ExperimentRegistry --> EarlyStopFactory["create_early_stop_plugin"]
    ExperimentRegistry --> ValidationFactory["create_validation_plugin"]
    ConfigLoader --> CoreRegistry
    ConfigLoader --> MiddlewareRegistry
    ConfigLoader --> ControlRegistry
    ConfigLoader --> ExperimentRegistry
    SuiteRunner -->|normalises definitions| ExperimentRegistry
    classDef registry fill:#fdf6e3,stroke:#b58900,stroke-width:1px;
    class CoreRegistry,ControlRegistry,ExperimentRegistry,MiddlewareRegistry registry;
```

## Diagram Notes
- **Configuration flow** – The CLI validates settings, merges prompt packs, and instantiates plugins before handing them to the orchestrator (`src/elspeth/cli.py:65`, `src/elspeth/config.py:52`, `src/elspeth/core/validation.py:271`).[^diagram-config-2025-10-12]
- **Orchestration core** – The orchestrator wires datasource, LLM, sinks, middleware, and optional controls into a single runner instance (`src/elspeth/core/orchestrator.py:46`, `src/elspeth/core/orchestrator.py:80`).[^diagram-orchestrator-2025-10-12]
- **Execution pipeline** – `ExperimentRunner` processes each row, invoking middleware, rate/cost controls, retries, and validation before handing artifacts to the dependency-aware pipeline (`src/elspeth/core/experiments/runner.py:126`, `src/elspeth/core/experiments/runner.py:464`, `src/elspeth/core/artifact_pipeline.py:201`).[^diagram-runner-2025-10-12]
- **Plugin boundaries** – Plugin registries enforce schema validation for datasources, sinks, LLM clients, and experiment plugins, encapsulating external credentials and behaviours (`src/elspeth/core/registry.py:91`, `src/elspeth/core/experiments/plugin_registry.py:93`, `src/elspeth/core/controls/registry.py:36`).[^diagram-registry-2025-10-12]
- **External integrations** – Datasources and sinks interact with Azure storage, repository APIs, or local file systems, while LLM clients communicate with Azure OpenAI or other HTTP-compatible endpoints (`src/elspeth/plugins/nodes/sources/blob.py:35`, `src/elspeth/plugins/nodes/transforms/llm/azure_openai.py:77`, `src/elspeth/plugins/nodes/sinks/repository.py:137`).[^diagram-integrations-2025-10-12]
- **Security overlays** – Middleware applies audit logging, prompt shielding, and Azure Content Safety scanning, while security levels propagate into the artifact pipeline to gate downstream consumption (`src/elspeth/plugins/nodes/transforms/llm/middleware.py:70`, `src/elspeth/core/experiments/runner.py:208`, `src/elspeth/core/artifact_pipeline.py:192`).[^diagram-security-2025-10-12]
- **Suite reporting outputs** – `SuiteReportGenerator` consolidates suite payloads, writes consolidated/visual/Excel artifacts, and surfaces analytics-ready summaries for accreditation reviewers (`src/elspeth/tools/reporting.py:19`, `src/elspeth/cli.py:392`, `src/elspeth/plugins/nodes/sinks/visual_report.py:11`, `src/elspeth/plugins/nodes/sinks/analytics_report.py:11`, `src/elspeth/plugins/nodes/sinks/excel.py:19`).[^diagram-suite-2025-10-12]
<!-- Update 2025-10-12: Concurrency, early-stop, analytics-reporting, visual sink, and Azure telemetry flows are captured in the extended diagram above (see `src/elspeth/core/experiments/runner.py:365`, `src/elspeth/plugins/nodes/sinks/analytics_report.py:11`, `src/elspeth/plugins/nodes/sinks/visual_report.py:11`, `src/elspeth/plugins/nodes/transforms/llm/middleware_azure.py:180`). -->

### Update 2025-10-12: System Interfaces
- `DataSource`, `LLMClientProtocol`, and `ResultSink` protocols (`src/elspeth/core/protocols.py:11`, `src/elspeth/core/protocols.py:37`) remain the authoritative contracts, matching the module boundaries depicted in the diagrams. Cross-reference docs/architecture/architecture-overview.md Core Principles for rationale.

### Update 2025-10-12: Configuration Loader
- `load_settings` resolves prompt packs, middleware, and early-stop definitions while preserving security levels (`src/elspeth/config.py:52`, `src/elspeth/config.py:146`). Validation flow ties into docs/architecture/configuration-security.md.

### Update 2025-10-12: Orchestrator Core
- `ExperimentOrchestrator` composes plugins and propagates concurrency / early-stop configs into `ExperimentRunner` (`src/elspeth/core/orchestrator.py:46`, `src/elspeth/core/orchestrator.py:93`). Diagram nodes show dependency injection order.

### Update 2025-10-12: Middleware Chain
- Middleware sequence (audit logger → prompt shield → content safety → health monitor → Azure environment) is registered via `elspeth.plugins.nodes.transforms.llm.middleware` / `_azure` modules; see docs/architecture/audit-logging.md for telemetry coverage.

### Update 2025-10-12: Artifact Pipeline
- `ArtifactPipeline` enforces security gates and resolves sink dependencies via `SinkBinding` ordering (`src/elspeth/core/artifact_pipeline.py:137`, `src/elspeth/core/artifact_pipeline.py:218`). Artifact flow aligns with docs/architecture/data-flow-diagrams.md Update 2025-10-12: Artifact Rehydration.

### Update 2025-10-12: Suite Reporting Pipeline
- `SuiteReportGenerator.generate_all_reports` materialises consolidated JSON, Markdown, Excel, and visual artifacts derived from suite execution payloads, gated by the `--reports-dir` CLI flag (`src/elspeth/tools/reporting.py:19`, `src/elspeth/cli.py:392`). Outputs align with analytics and visual sink formats so accreditation reviewers can diff pipeline- and suite-generated evidence (`src/elspeth/plugins/nodes/sinks/visual_report.py:11`, `src/elspeth/plugins/nodes/sinks/analytics_report.py:11`, `src/elspeth/plugins/nodes/sinks/excel.py:19`).
<!-- UPDATE 2025-10-12: CLI dispatch citation refresh -->
Update 2025-10-12: `--reports-dir` handling currently occurs at `src/elspeth/cli.py:395-458` following suite execution.
<!-- END UPDATE -->

### Update 2025-10-12: Registry Boundaries
- Core, control, middleware, and experiment registries split responsibilities for datasources, sinks, rate/cost controls, and row/aggregation/baseline/early-stop plugins (`src/elspeth/core/registry.py:91`, `src/elspeth/core/controls/registry.py:36`, `src/elspeth/core/llm/registry.py:17`, `src/elspeth/core/experiments/plugin_registry.py:93`). Suite runner normalises configuration entries before delegation, matching the diagram wiring (`src/elspeth/core/experiments/suite_runner.py:69`).

### Update 2025-10-12: Control Registry
- Rate and cost control registries normalise security levels and schema validation before attaching to the runner (`src/elspeth/core/controls/registry.py:36`, `src/elspeth/core/controls/rate_limit.py:104`). See docs/architecture/plugin-security-model.md Update 2025-10-12: Control Registry.

### Update 2025-10-12: Artifact Tokens
- Sinks advertise artifacts via `ArtifactDescriptor` and runtime metadata (`src/elspeth/core/interfaces.py:83`, `src/elspeth/core/artifact_pipeline.py:153`), enabling analytics and signing sinks to consume upstream assets. Controls are catalogued in docs/architecture/CONTROL_INVENTORY.md.
<!-- UPDATE 2025-10-12: Artifact descriptor relocation -->
Update 2025-10-12: Artifact descriptor definitions reside in `src/elspeth/core/protocols.py:237-309`; request parsing and binding resolution continue in `src/elspeth/core/artifact_pipeline.py:120-219`.
<!-- END UPDATE -->

## Update History
- 2025-10-12 – Added extended component diagram highlighting suite orchestration, concurrency controls, analytics sinks, and Azure telemetry touchpoints.
- 2025-10-12 – Update 2025-10-12: Introduced middleware/pipeline detail diagram, added cross-referenced section anchors, and verified plugin registry edges against `src/elspeth/core/experiments/plugin_registry.py`.
- 2025-10-12 – Update 2025-10-12: Documented suite reporting exports, registry boundaries, and derived accreditation artifacts through additional diagrams and notes.

[^diagram-config-2025-10-12]: Update 2025-10-12: See docs/architecture/configuration-security.md (Update 2025-10-12: Profile Validation Chain) for validation details.
[^diagram-orchestrator-2025-10-12]: Update 2025-10-12: Cross-referenced with docs/architecture/architecture-overview.md Core Principles.
[^diagram-runner-2025-10-12]: Update 2025-10-12: Execution details synchronised with docs/architecture/data-flow-diagrams.md (Update 2025-10-12: Runner Pipeline).
[^diagram-registry-2025-10-12]: Update 2025-10-12: Registry boundaries elaborated in docs/architecture/plugin-security-model.md (Update 2025-10-12: Registry Enforcement).
[^diagram-integrations-2025-10-12]: Update 2025-10-12: External endpoints documented in docs/architecture/threat-surfaces.md (Update 2025-10-12: External Integrations).
[^diagram-security-2025-10-12]: Update 2025-10-12: Security overlay ties to docs/architecture/security-controls.md (Update 2025-10-12: Middleware Safeguards).
[^diagram-suite-2025-10-12]: Update 2025-10-12: Cross-reference docs/reporting-and-suite-management.md (Update 2025-10-12: Suite Reporting Exports) for CLI usage, output structure, and visual/analytics examples.
