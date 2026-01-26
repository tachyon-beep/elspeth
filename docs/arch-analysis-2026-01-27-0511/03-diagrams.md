# Architecture Diagrams

This document contains C4 architecture diagrams for ELSPETH at multiple abstraction levels.

---

## Level 1: System Context Diagram

Shows ELSPETH in its operating environment with external actors.

```mermaid
C4Context
    title System Context: ELSPETH Auditable Pipeline Framework

    Person(operator, "Pipeline Operator", "Configures and runs data pipelines")
    Person(auditor, "Auditor", "Queries lineage, verifies decisions")

    System(elspeth, "ELSPETH", "Domain-agnostic framework for auditable Sense/Decide/Act pipelines")

    System_Ext(data_sources, "Data Sources", "CSV files, JSON, Azure Blob Storage")
    System_Ext(llm_providers, "LLM Providers", "Azure OpenAI, OpenRouter, LiteLLM")
    System_Ext(data_sinks, "Data Sinks", "CSV files, JSON, Databases, Azure Blob")

    Rel(operator, elspeth, "Configures pipelines, runs jobs", "CLI/YAML")
    Rel(auditor, elspeth, "Queries lineage, explains decisions", "CLI/TUI")

    Rel(elspeth, data_sources, "Reads source data", "File I/O, Azure SDK")
    Rel(elspeth, llm_providers, "Makes classification requests", "HTTPS/REST")
    Rel(elspeth, data_sinks, "Writes processed results", "File I/O, SQL, Azure SDK")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

---

## Level 2: Container Diagram

Shows the major components within ELSPETH.

```mermaid
C4Container
    title Container Diagram: ELSPETH Internal Structure

    Person(operator, "Operator", "Runs pipelines")

    Container_Boundary(elspeth, "ELSPETH Framework") {
        Container(cli, "CLI", "Typer", "Command-line interface for pipeline execution")
        Container(tui, "TUI", "Textual", "Interactive lineage exploration")

        Container(engine, "Engine", "Python", "Orchestrates SDA pipeline execution")
        Container(dag, "DAG", "NetworkX", "Validates and represents execution graph")

        Container(plugins, "Plugin System", "pluggy", "Extensible sources, transforms, sinks")
        Container(landscape, "Landscape", "SQLAlchemy", "Audit trail database with hash integrity")
        Container(checkpoint, "Checkpoint", "Python", "Crash recovery with topology validation")

        Container(canonical, "Canonical JSON", "rfc8785", "Deterministic hashing for audit")
        Container(contracts, "Contracts", "Pydantic/dataclass", "Type-safe interfaces")
    }

    ContainerDb(landscape_db, "Landscape DB", "SQLite/PostgreSQL", "Audit trail storage")
    ContainerDb(payload_store, "Payload Store", "Filesystem", "Large blob storage")

    System_Ext(external, "External Systems", "Data sources, LLM APIs, sinks")

    Rel(operator, cli, "Executes commands", "Terminal")
    Rel(operator, tui, "Explores lineage", "Terminal")

    Rel(cli, engine, "Invokes pipeline")
    Rel(tui, landscape, "Queries lineage")

    Rel(engine, dag, "Validates topology")
    Rel(engine, plugins, "Executes plugins")
    Rel(engine, landscape, "Records audit trail")
    Rel(engine, checkpoint, "Creates checkpoints")

    Rel(plugins, external, "Interacts with", "Various protocols")

    Rel(landscape, landscape_db, "Stores records")
    Rel(landscape, payload_store, "Stores blobs")
    Rel(landscape, canonical, "Computes hashes")

    Rel(checkpoint, landscape_db, "Stores checkpoints")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

---

## Level 3: Component Diagram - Engine

Detailed view of the Engine subsystem.

```mermaid
C4Component
    title Component Diagram: Engine Subsystem

    Container_Boundary(engine, "Engine") {
        Component(orchestrator, "Orchestrator", "orchestrator.py", "Run lifecycle: begin, process, complete")
        Component(processor, "RowProcessor", "processor.py", "Process rows through transforms with work queue")
        Component(executors, "Executors", "executors.py", "Plugin wrappers: Transform, Gate, Aggregation, Sink")
        Component(token_mgr, "TokenManager", "tokens.py", "Token lifecycle: create, fork, coalesce, expand")
        Component(coalesce, "CoalesceExecutor", "coalesce_executor.py", "Stateful barrier for fork-join")
        Component(retry, "RetryManager", "retry.py", "Exponential backoff with jitter")
        Component(batch_adapter, "BatchAdapter", "batch_adapter.py", "Async batch transform coordination")
    }

    Container(dag, "DAG", "ExecutionGraph")
    Container(landscape, "Landscape", "LandscapeRecorder")
    Container(plugins, "Plugins", "Source/Transform/Sink")

    Rel(orchestrator, processor, "Delegates row processing")
    Rel(orchestrator, dag, "Reads topology")
    Rel(orchestrator, landscape, "Records run lifecycle")

    Rel(processor, executors, "Invokes plugin execution")
    Rel(processor, token_mgr, "Manages token lifecycle")
    Rel(processor, coalesce, "Coordinates fork-join")

    Rel(executors, plugins, "Wraps plugin calls")
    Rel(executors, landscape, "Records node states")
    Rel(executors, retry, "Wraps with retry logic")
    Rel(executors, batch_adapter, "Coordinates batch transforms")

    Rel(token_mgr, landscape, "Records token events")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

---

## Level 3: Component Diagram - Landscape

Detailed view of the Landscape (Audit Trail) subsystem.

```mermaid
C4Component
    title Component Diagram: Landscape Subsystem

    Container_Boundary(landscape, "Landscape") {
        Component(recorder, "LandscapeRecorder", "recorder.py", "High-level recording API")
        Component(database, "LandscapeDB", "database.py", "Connection management, WAL config")
        Component(schema, "Schema", "schema.py", "SQLAlchemy table definitions")
        Component(models, "Models", "models.py", "Dataclass audit entities")
        Component(repos, "Repositories", "repositories.py", "Enum coercion at Tier 1 boundary")
        Component(lineage, "Lineage", "lineage.py", "explain() query composition")
        Component(exporter, "Exporter", "exporter.py", "CSV/JSON export with HMAC")
    }

    ContainerDb(db, "Database", "SQLite/PostgreSQL")
    Container(canonical, "Canonical", "Hash computation")
    Container(payload, "PayloadStore", "Blob storage")

    Rel(recorder, database, "Uses connection")
    Rel(recorder, schema, "Writes to tables")
    Rel(recorder, canonical, "Computes hashes")
    Rel(recorder, payload, "Stores large blobs")

    Rel(database, db, "Connects to")
    Rel(database, schema, "Validates schema")

    Rel(repos, models, "Deserializes to")
    Rel(repos, schema, "Reads from")

    Rel(lineage, repos, "Queries via")
    Rel(exporter, repos, "Exports from")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

---

## Level 3: Component Diagram - Plugin System

Detailed view of the Plugin subsystem.

```mermaid
C4Component
    title Component Diagram: Plugin System

    Container_Boundary(plugins, "Plugin System") {
        Component(manager, "PluginManager", "manager.py", "Registration, lookup, validation")
        Component(discovery, "Discovery", "discovery.py", "Dynamic plugin discovery")
        Component(context, "PluginContext", "context.py", "Run metadata, call recording")
        Component(protocols, "Protocols", "protocols.py", "Runtime-checkable interfaces")
        Component(base, "Base Classes", "base.py", "BaseSource, BaseTransform, BaseSink")
    }

    Container_Boundary(sources, "Sources") {
        Component(csv_src, "CSVSource", "csv_source.py")
        Component(json_src, "JSONSource", "json_source.py")
        Component(blob_src, "AzureBlobSource", "blob_source.py")
    }

    Container_Boundary(transforms, "Transforms") {
        Component(mapper, "FieldMapper", "field_mapper.py")
        Component(filter, "KeywordFilter", "keyword_filter.py")
        Component(llm, "LLM Transforms", "llm/*.py")
    }

    Container_Boundary(sinks, "Sinks") {
        Component(csv_sink, "CSVSink", "csv_sink.py")
        Component(json_sink, "JSONSink", "json_sink.py")
        Component(db_sink, "DatabaseSink", "database_sink.py")
    }

    Rel(manager, discovery, "Discovers plugins")
    Rel(manager, protocols, "Validates against")

    Rel(sources, base, "Extends")
    Rel(transforms, base, "Extends")
    Rel(sinks, base, "Extends")

    Rel(sources, context, "Uses")
    Rel(transforms, context, "Uses")
    Rel(sinks, context, "Uses")

    UpdateLayoutConfig($c4ShapeInRow="4", $c4BoundaryInRow="2")
```

---

## Data Flow Diagram

Shows how data flows through the SDA pipeline.

```mermaid
flowchart TD
    subgraph SENSE ["SENSE (Source)"]
        S1[External Data Source]
        S2[CSVSource / JSONSource / BlobSource]
        S3[SourceRow with validation]
    end

    subgraph DECIDE ["DECIDE (Transforms/Gates)"]
        D1[Transform Pipeline]
        D2[Gate Routing]
        D3[Fork/Coalesce]
        D4[Aggregation]
    end

    subgraph ACT ["ACT (Sinks)"]
        A1[CSVSink / JSONSink / DatabaseSink]
        A2[External Destination]
    end

    subgraph AUDIT ["AUDIT (Landscape)"]
        L1[LandscapeRecorder]
        L2[(Landscape DB)]
        L3[PayloadStore]
    end

    S1 -->|"Tier 3: External Data"| S2
    S2 -->|"Coercion + Validation"| S3
    S3 -->|"Tier 2: Pipeline Data"| D1

    D1 --> D2
    D2 -->|"Route Labels"| D3
    D3 --> D4
    D4 -->|"Batched Results"| A1

    D2 -->|"Direct to Sink"| A1

    A1 --> A2

    S2 -.->|"Record row"| L1
    D1 -.->|"Record node_state"| L1
    D2 -.->|"Record routing_event"| L1
    A1 -.->|"Record artifact"| L1

    L1 --> L2
    L1 --> L3

    style SENSE fill:#e1f5fe
    style DECIDE fill:#fff3e0
    style ACT fill:#e8f5e9
    style AUDIT fill:#fce4ec
```

---

## Token Lifecycle Diagram

Shows how tokens track row identity through fork/coalesce operations.

```mermaid
flowchart TD
    subgraph Source ["Source Row"]
        R1["row_id: R001"]
    end

    subgraph InitialToken ["Initial Token"]
        T1["token_id: T001<br/>row_id: R001<br/>branch: null"]
    end

    subgraph Fork ["Fork Gate"]
        F1["Fork to branches A, B"]
    end

    subgraph BranchA ["Branch A"]
        TA1["token_id: T002<br/>row_id: R001<br/>branch: A<br/>fork_group: FG001"]
        TA2["Transform A1"]
        TA3["Transform A2"]
    end

    subgraph BranchB ["Branch B"]
        TB1["token_id: T003<br/>row_id: R001<br/>branch: B<br/>fork_group: FG001"]
        TB2["Transform B1"]
    end

    subgraph Coalesce ["Coalesce"]
        C1["Merge policy: require_all"]
        TC["token_id: T004<br/>row_id: R001<br/>branch: null<br/>join_group: JG001"]
    end

    subgraph Sink ["Output Sink"]
        S1["Final Output"]
    end

    R1 --> T1
    T1 --> F1
    F1 -->|"COPY edge"| TA1
    F1 -->|"COPY edge"| TB1

    TA1 --> TA2 --> TA3
    TB1 --> TB2

    TA3 -->|"Arrive"| C1
    TB2 -->|"Arrive"| C1

    C1 --> TC --> S1

    style Source fill:#e3f2fd
    style Fork fill:#fff3e0
    style Coalesce fill:#e8f5e9
```

---

## Three-Tier Trust Model Diagram

Visualizes the trust boundaries in data handling.

```mermaid
flowchart LR
    subgraph Tier3 ["Tier 3: External Data (Zero Trust)"]
        E1["CSV Files"]
        E2["API Responses"]
        E3["LLM Outputs"]
    end

    subgraph Boundary1 ["Trust Boundary: Source/External Call"]
        B1["Validate + Coerce<br/>Quarantine on failure"]
    end

    subgraph Tier2 ["Tier 2: Pipeline Data (Elevated Trust)"]
        P1["Type-valid row data"]
        P2["Wrap operations<br/>(division, parsing)"]
    end

    subgraph Boundary2 ["Trust Boundary: Landscape Write"]
        B2["No coercion allowed<br/>Crash on anomaly"]
    end

    subgraph Tier1 ["Tier 1: Audit Trail (Full Trust)"]
        A1["Landscape DB"]
        A2["100% pristine<br/>Crash on bad data"]
    end

    E1 --> B1
    E2 --> B1
    E3 --> B1

    B1 -->|"Types normalized"| P1
    P1 --> P2

    P2 --> B2
    B2 -->|"Audit record"| A1
    A1 --> A2

    style Tier3 fill:#ffebee
    style Boundary1 fill:#fff3e0
    style Tier2 fill:#e3f2fd
    style Boundary2 fill:#fff3e0
    style Tier1 fill:#e8f5e9
```

---

## Checkpoint Recovery Diagram

Shows the checkpoint and resume flow.

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant CP as CheckpointManager
    participant L as Landscape
    participant RM as RecoveryManager

    Note over O,L: Normal Execution with Checkpoints

    O->>L: begin_run(run_id)
    loop For each token
        O->>L: record_node_state()
        O->>CP: create_checkpoint(token_id, node_id, seq)
        CP->>CP: compute_upstream_topology_hash()
        CP->>L: INSERT checkpoint
    end

    Note over O,L: Crash Occurs!

    Note over O,RM: Resume Attempt

    O->>RM: can_resume(run_id, current_graph)
    RM->>L: get_latest_checkpoint()
    RM->>RM: validate_topology(checkpoint, graph)
    alt Topology matches
        RM-->>O: ResumeCheck(can_resume=True)
    else Topology changed
        RM-->>O: ResumeCheck(can_resume=False, reason)
    end

    O->>RM: get_resume_point(run_id)
    RM->>L: get_unprocessed_rows()
    RM-->>O: ResumePoint(checkpoint, rows)

    Note over O,L: Resume Execution

    O->>O: Configure sinks for append mode
    loop For each unprocessed row
        O->>L: process_existing_row()
    end
    O->>L: complete_run()
```

---

## DAG Construction Diagram

Shows how the execution graph is built from configuration.

```mermaid
flowchart TD
    subgraph Config ["Configuration (YAML)"]
        C1["source: csv"]
        C2["transforms: [mapper, filter, llm]"]
        C3["gates: [{condition, routes}]"]
        C4["sinks: {output, error}"]
        C5["coalesce: [{name, branches}]"]
    end

    subgraph Factory ["ExecutionGraph.from_plugin_instances()"]
        F1["Generate deterministic node IDs<br/>(canonical hash + sequence)"]
        F2["Add nodes with schemas"]
        F3["Wire edges with labels"]
        F4["Connect gate routes"]
        F5["Setup fork → coalesce"]
    end

    subgraph Validation ["Two-Phase Validation"]
        V1["PHASE 1: Structural<br/>- Acyclicity (NetworkX)<br/>- Exactly 1 source<br/>- ≥1 sink<br/>- Unique edge labels"]
        V2["PHASE 2: Schema<br/>- Field compatibility<br/>- Pass-through inheritance"]
    end

    subgraph Graph ["ExecutionGraph"]
        G1["nodes: MultiDiGraph"]
        G2["get_sink_id_map()"]
        G3["get_branch_to_coalesce_map()"]
        G4["topological_order()"]
    end

    C1 --> F1
    C2 --> F1
    C3 --> F1
    C4 --> F1
    C5 --> F1

    F1 --> F2 --> F3 --> F4 --> F5

    F5 --> V1 --> V2

    V2 --> G1
    G1 --> G2
    G1 --> G3
    G1 --> G4
```

---

## Module Dependency Diagram

Shows inter-module dependencies.

```mermaid
flowchart BT
    subgraph Layer1 ["Layer 1: Contracts (No Dependencies)"]
        contracts["contracts/"]
    end

    subgraph Layer2 ["Layer 2: Core Utilities"]
        canonical["canonical.py"]
        events["events.py"]
        logging["logging.py"]
    end

    subgraph Layer3 ["Layer 3: Core Services"]
        config["config.py"]
        dag["dag.py"]
        landscape["landscape/"]
        checkpoint["checkpoint/"]
        retention["retention/"]
        payload["payload_store.py"]
    end

    subgraph Layer4 ["Layer 4: Plugin System"]
        plugins["plugins/"]
        sources["sources/"]
        transforms["transforms/"]
        sinks["sinks/"]
        llm["llm/"]
        azure["azure/"]
    end

    subgraph Layer5 ["Layer 5: Engine"]
        engine["engine/"]
    end

    subgraph Layer6 ["Layer 6: Interface"]
        cli["cli.py"]
        tui["tui/"]
    end

    canonical --> contracts
    events --> contracts

    config --> contracts
    config --> canonical
    dag --> contracts
    dag --> canonical
    landscape --> contracts
    landscape --> canonical
    checkpoint --> landscape
    retention --> landscape

    plugins --> contracts
    plugins --> landscape
    sources --> plugins
    transforms --> plugins
    sinks --> plugins
    llm --> transforms
    azure --> plugins

    engine --> dag
    engine --> landscape
    engine --> plugins
    engine --> checkpoint

    cli --> engine
    cli --> config
    tui --> landscape
```

---

## Glossary

| Term | Definition |
|------|------------|
| **SDA** | Sense/Decide/Act - the three phases of pipeline execution |
| **Landscape** | The audit trail database |
| **Token** | An instance of a row at a specific point in the DAG |
| **row_id** | Stable source row identifier (never changes) |
| **token_id** | Instance identifier (changes on fork/coalesce) |
| **Fork** | Split one token into multiple parallel tokens |
| **Coalesce** | Merge multiple tokens back into one |
| **Gate** | Routing decision point that may fork or route to sinks |
| **Tier 1/2/3** | Trust levels for data (audit/pipeline/external) |
| **Canonical JSON** | RFC 8785 deterministic JSON for consistent hashing |
