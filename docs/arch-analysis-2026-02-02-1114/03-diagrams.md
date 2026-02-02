# ELSPETH Architecture Diagrams

This document contains C4 architecture diagrams at multiple abstraction levels.

---

## C4 Level 1: System Context

```mermaid
graph TB
    subgraph External
        User[fa:fa-user Pipeline Operator]
        LLM[fa:fa-cloud LLM Providers<br/>Azure OpenAI, OpenRouter]
        Blob[fa:fa-database Azure Blob Storage]
        DB[fa:fa-database External Databases]
        Mon[fa:fa-chart-line Monitoring<br/>Datadog, Jaeger, Azure Monitor]
    end

    subgraph ELSPETH
        CLI[CLI / TUI]
        Engine[Pipeline Engine]
        Landscape[Audit Trail<br/>Landscape]
        Plugins[Plugin System]
    end

    User --> CLI
    CLI --> Engine
    Engine --> Landscape
    Engine --> Plugins
    Plugins --> LLM
    Plugins --> Blob
    Plugins --> DB
    Engine --> Mon

    classDef external fill:#f9f,stroke:#333
    classDef elspeth fill:#bbf,stroke:#333
    class User,LLM,Blob,DB,Mon external
    class CLI,Engine,Landscape,Plugins elspeth
```

**System Context Description:**
- **Pipeline Operator**: Configures and runs SDA pipelines via CLI or TUI
- **ELSPETH**: Auditable pipeline framework with complete traceability
- **LLM Providers**: External AI services for classification/analysis
- **Azure Blob Storage**: Cloud storage for source/sink operations
- **External Databases**: SQL databases for source/sink
- **Monitoring**: Operational visibility via telemetry exporters

---

## C4 Level 2: Container Diagram

```mermaid
graph TB
    subgraph CLI_Layer[CLI Layer]
        CLI[elspeth CLI<br/>Typer]
        TUI[Lineage TUI<br/>Textual]
        MCP[MCP Server<br/>Analysis API]
    end

    subgraph Engine_Layer[Engine Layer]
        Orch[Orchestrator<br/>Run Lifecycle]
        Proc[RowProcessor<br/>DAG Traversal]
        Exec[Executors<br/>Transform/Gate/Sink]
        DAG[ExecutionGraph<br/>NetworkX]
    end

    subgraph Audit_Layer[Audit Layer]
        Recorder[LandscapeRecorder<br/>Recording API]
        LandDB[LandscapeDB<br/>SQLAlchemy Core]
        Payload[PayloadStore<br/>Content-Addressed]
    end

    subgraph Plugin_Layer[Plugin Layer]
        Sources[Sources<br/>CSV, JSON, Blob]
        Transforms[Transforms<br/>Field Mapper, LLM]
        Sinks[Sinks<br/>CSV, JSON, DB]
        Clients[Audited Clients<br/>HTTP, LLM]
    end

    subgraph Infra_Layer[Infrastructure]
        Telem[TelemetryManager<br/>Event Export]
        Ckpt[CheckpointManager<br/>Crash Recovery]
        Rate[RateLimitRegistry<br/>Throttling]
        Config[RuntimeConfig<br/>Settings→Runtime]
    end

    CLI --> Orch
    TUI --> Recorder
    MCP --> LandDB

    Orch --> Proc
    Proc --> Exec
    Exec --> DAG

    Exec --> Sources
    Exec --> Transforms
    Exec --> Sinks
    Transforms --> Clients

    Orch --> Recorder
    Exec --> Recorder
    Sources --> Payload
    Sinks --> Payload

    Orch --> Telem
    Orch --> Ckpt
    Clients --> Rate
    Orch --> Config
```

---

## C4 Level 3: Component Diagram - Engine

```mermaid
graph TB
    subgraph Orchestrator
        Run[run<br/>Full Lifecycle]
        Resume[resume<br/>Crash Recovery]
        Validate[validate_routes<br/>Config Check]
    end

    subgraph RowProcessor
        Process[process_row<br/>Work Queue]
        Token[TokenManager<br/>Identity]
        Coalesce[CoalesceExecutor<br/>Fork/Join]
    end

    subgraph Executors
        TransExec[TransformExecutor<br/>Row Processing]
        GateExec[GateExecutor<br/>Routing]
        AggExec[AggregationExecutor<br/>Batching]
        SinkExec[Sink Write<br/>Output]
    end

    subgraph Support
        Retry[RetryManager<br/>Tenacity]
        Spans[SpanFactory<br/>OpenTelemetry]
        Triggers[TriggerEvaluator<br/>Count/Timeout]
        ExprParse[ExpressionParser<br/>AST Eval]
    end

    Run --> Process
    Resume --> Process
    Validate --> Run

    Process --> TransExec
    Process --> GateExec
    Process --> Coalesce
    TransExec --> AggExec
    GateExec --> Token

    TransExec --> Retry
    Process --> Spans
    AggExec --> Triggers
    GateExec --> ExprParse
```

---

## C4 Level 3: Component Diagram - Landscape

```mermaid
graph TB
    subgraph Recording_API
        Recorder[LandscapeRecorder<br/>47+ Methods]
        RunOps[Run Operations<br/>begin/complete]
        NodeOps[Node Operations<br/>register/state]
        TokenOps[Token Operations<br/>create/fork/coalesce]
    end

    subgraph Query_API
        Lineage[explain<br/>Lineage Query]
        Export[LandscapeExporter<br/>Bulk Export]
        Format[Formatters<br/>JSON/CSV/Text]
    end

    subgraph Storage
        DB[LandscapeDB<br/>Connection Pool]
        Schema[Schema<br/>SQLAlchemy Tables]
        Repos[Repositories<br/>Row→Object]
    end

    subgraph Support
        Journal[Journal<br/>JSONL Backup]
        Repro[Reproducibility<br/>Grade Tracking]
        RowData[RowData<br/>State Discrimination]
    end

    Recorder --> RunOps
    Recorder --> NodeOps
    Recorder --> TokenOps

    Lineage --> Repos
    Export --> Format

    RunOps --> DB
    NodeOps --> DB
    TokenOps --> DB

    DB --> Schema
    Schema --> Repos

    Recorder --> Journal
    Recorder --> Repro
    Lineage --> RowData
```

---

## C4 Level 3: Component Diagram - Plugin System

```mermaid
graph TB
    subgraph Discovery
        Manager[PluginManager<br/>Registry]
        Discover[discovery.py<br/>File Scan]
        Hooks[hookspecs.py<br/>pluggy Hooks]
    end

    subgraph Protocols
        SourceP[SourceProtocol<br/>load, close]
        TransP[TransformProtocol<br/>process]
        SinkP[SinkProtocol<br/>write, flush]
        GateP[GateProtocol<br/>evaluate]
    end

    subgraph Sources
        CSV_S[CSVSource]
        JSON_S[JSONSource]
        Blob_S[AzureBlobSource]
        Null_S[NullSource]
    end

    subgraph Transforms
        Pass[Passthrough]
        FMap[FieldMapper]
        Trunc[Truncate]
        LLM[LLM Transforms]
    end

    subgraph Sinks
        CSV_K[CSVSink]
        JSON_K[JSONSink]
        DB_K[DatabaseSink]
        Blob_K[AzureBlobSink]
    end

    subgraph Clients
        HTTP[AuditedHTTPClient]
        LLM_C[AuditedLLMClient]
        Replay[ReplayerClient]
        Verify[VerifierClient]
    end

    Manager --> Discover
    Discover --> Hooks

    SourceP -.-> CSV_S
    SourceP -.-> JSON_S
    SourceP -.-> Blob_S
    SourceP -.-> Null_S

    TransP -.-> Pass
    TransP -.-> FMap
    TransP -.-> Trunc
    TransP -.-> LLM

    SinkP -.-> CSV_K
    SinkP -.-> JSON_K
    SinkP -.-> DB_K
    SinkP -.-> Blob_K

    LLM --> LLM_C
    LLM --> HTTP
```

---

## Data Flow Diagram: Pipeline Execution

```mermaid
sequenceDiagram
    participant CLI
    participant Orch as Orchestrator
    participant Source
    participant Proc as RowProcessor
    participant Trans as Transform
    participant Gate
    participant Sink
    participant Land as Landscape
    participant Telem as Telemetry

    CLI->>Orch: run(config)
    Orch->>Land: begin_run()
    Orch->>Land: register_nodes()

    Orch->>Telem: emit(RunStarted)

    Orch->>Source: load()
    loop For each row
        Source->>Orch: yield row
        Orch->>Land: create_row()
        Orch->>Proc: process_row()
        Proc->>Land: create_token()

        loop For each transform
            Proc->>Trans: process(row, ctx)
            Trans->>Land: open_state()
            Trans-->>Land: complete_state()
            Proc->>Telem: emit(TransformCompleted)
        end

        opt If Gate Present
            Proc->>Gate: evaluate(row)
            Gate->>Land: record_routing()
        end

        Proc-->>Orch: RowResult
    end

    Orch->>Sink: write(rows)
    Sink->>Land: record_artifact()
    Orch->>Land: complete_run()
    Orch->>Telem: emit(RunFinished)
    Orch-->>CLI: RunResult
```

---

## Data Flow Diagram: Fork/Join Processing

```mermaid
sequenceDiagram
    participant Proc as RowProcessor
    participant Gate as Fork Gate
    participant Token as TokenManager
    participant Trans_A as Branch A Transform
    participant Trans_B as Branch B Transform
    participant Coal as CoalesceExecutor
    participant Land as Landscape

    Proc->>Gate: evaluate(row)
    Gate-->>Proc: fork_to_paths([A, B])

    Proc->>Land: record_routing(FORKED)
    Proc->>Token: fork_token(parent, [A, B])
    Token->>Land: create_token(child_A)
    Token->>Land: create_token(child_B)
    Token-->>Proc: [token_A, token_B]

    par Branch A
        Proc->>Trans_A: process(row_A)
        Trans_A-->>Proc: result_A
        Proc->>Coal: accept(token_A, result_A)
    and Branch B
        Proc->>Trans_B: process(row_B)
        Trans_B-->>Proc: result_B
        Proc->>Coal: accept(token_B, result_B)
    end

    Coal->>Coal: _should_merge()
    Coal->>Token: coalesce_tokens([A, B])
    Token->>Land: create_token(merged)
    Land->>Land: update_outcome(A, COALESCED)
    Land->>Land: update_outcome(B, COALESCED)
    Coal-->>Proc: merged_token
```

---

## Dependency Graph: Major Subsystems

```mermaid
graph LR
    subgraph Contracts[contracts/]
        C_Audit[audit.py]
        C_Enums[enums.py]
        C_Config[config/]
    end

    subgraph Core[core/]
        Landscape[landscape/]
        DAG[dag.py]
        Config[config.py]
        Canonical[canonical.py]
        Checkpoint[checkpoint/]
        Payload[payload_store.py]
    end

    subgraph Engine[engine/]
        Orch[orchestrator.py]
        Proc[processor.py]
        Exec[executors.py]
    end

    subgraph Plugins[plugins/]
        Manager[manager.py]
        Sources[sources/]
        Transforms[transforms/]
        Sinks[sinks/]
    end

    subgraph UI[User Interfaces]
        CLI[cli.py]
        TUI[tui/]
        MCP[mcp/]
    end

    %% Dependencies
    Engine --> Contracts
    Engine --> Core
    Plugins --> Contracts
    Plugins --> Core
    UI --> Engine
    UI --> Core

    Core --> Contracts

    %% Leaf module
    Contracts -.- |LEAF - no outbound| Contracts
```

---

## Trust Boundary Diagram

```mermaid
graph TB
    subgraph Tier1[Tier 1: Full Trust - Our Data]
        Landscape[(Landscape DB)]
        Checkpoint[(Checkpoints)]
        InternalState[Internal State]
    end

    subgraph Tier2[Tier 2: Elevated Trust - Pipeline Data]
        RowData[Row Data<br/>Post-Validation]
        TransformOutput[Transform Output]
        GateDecisions[Gate Decisions]
    end

    subgraph Tier3[Tier 3: Zero Trust - External Data]
        SourceInput[Source Files<br/>CSV, JSON]
        LLMResponse[LLM API<br/>Responses]
        HTTPResponse[HTTP API<br/>Responses]
        BlobData[Azure Blob<br/>Contents]
    end

    subgraph Boundaries[Trust Boundaries]
        SourceValidation{Source<br/>Validation}
        LLMValidation{LLM Response<br/>Validation}
        HTTPValidation{HTTP Response<br/>Validation}
    end

    SourceInput --> SourceValidation
    SourceValidation -->|Coerce OK| RowData
    SourceValidation -->|Quarantine| Landscape

    LLMResponse --> LLMValidation
    LLMValidation -->|Validate JSON| TransformOutput

    HTTPResponse --> HTTPValidation
    HTTPValidation -->|Validate Schema| TransformOutput

    RowData --> Landscape
    TransformOutput --> Landscape
    GateDecisions --> Landscape

    style Tier1 fill:#afa,stroke:#0a0
    style Tier2 fill:#ffa,stroke:#aa0
    style Tier3 fill:#faa,stroke:#a00
```

---

## Telemetry Flow Diagram

```mermaid
graph LR
    subgraph Pipeline
        Orch[Orchestrator]
        Proc[RowProcessor]
        Exec[Executors]
        Clients[Audited Clients]
    end

    subgraph TelemetrySystem
        EventBus[EventBus<br/>Sync]
        Manager[TelemetryManager<br/>Async Queue]
        Filter[Granularity<br/>Filter]
    end

    subgraph Exporters
        Console[Console]
        OTLP[OTLP<br/>Jaeger/Tempo]
        Datadog[Datadog]
        Azure[Azure Monitor]
    end

    subgraph External[External Systems]
        Jaeger[fa:fa-search Jaeger]
        DD[fa:fa-dog Datadog]
        AM[fa:fa-cloud Azure]
    end

    Orch --> EventBus
    Proc --> EventBus
    Exec --> EventBus
    Clients --> EventBus

    EventBus --> Manager
    Manager --> Filter
    Filter --> Console
    Filter --> OTLP
    Filter --> Datadog
    Filter --> Azure

    OTLP --> Jaeger
    Datadog --> DD
    Azure --> AM
```

---

## Schema Contract Validation Flow

```mermaid
graph TB
    subgraph PluginInit[Plugin Initialization]
        Source[Source Plugin]
        Transform[Transform Plugin]
        Sink[Sink Plugin]
    end

    subgraph SchemaExtraction[Schema Extraction]
        OutSchema[output_schema<br/>guaranteed_fields]
        InSchema[input_schema<br/>required_fields]
    end

    subgraph DAGConstruction[DAG Construction]
        Graph[ExecutionGraph]
        Nodes[add_node]
        Edges[add_edge]
    end

    subgraph Validation[Validation Phases]
        Phase1[Phase 1: Contract<br/>Field Names]
        Phase2[Phase 2: Types<br/>Schema Compat]
    end

    Source --> OutSchema
    Transform --> InSchema
    Transform --> OutSchema
    Sink --> InSchema

    OutSchema --> Graph
    InSchema --> Graph

    Graph --> Nodes
    Nodes --> Edges

    Edges --> Phase1
    Phase1 -->|guaranteed ⊇ required| Phase2
    Phase1 -->|missing fields| Error1[Schema Contract<br/>Violation]
    Phase2 -->|types compatible| Success[DAG Valid]
    Phase2 -->|type mismatch| Error2[Type<br/>Incompatibility]
```

---

## Summary

These diagrams illustrate:

1. **System Context**: ELSPETH's place in the broader ecosystem
2. **Container View**: Major subsystem organization
3. **Component View**: Internal structure of Engine, Landscape, and Plugins
4. **Data Flow**: Pipeline execution and fork/join processing
5. **Dependencies**: Subsystem relationships and leaf module principle
6. **Trust Boundaries**: Three-tier trust model visualization
7. **Telemetry Flow**: Event routing to exporters
8. **Schema Validation**: Contract enforcement at DAG construction
