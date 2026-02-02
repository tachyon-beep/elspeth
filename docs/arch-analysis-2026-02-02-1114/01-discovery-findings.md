# Discovery Findings: ELSPETH Architecture

## Executive Summary

ELSPETH is a **domain-agnostic framework for auditable Sense/Decide/Act (SDA) pipelines** targeting high-stakes accountability environments. The codebase is mature (~58K LOC), well-structured, and implements a comprehensive audit trail system called "Landscape" that makes every processing decision traceable to its source.

**Current Status:** RC-2 (Release Candidate 2) - Core architecture complete, stabilization fixes integrated.

## Technology Stack

| Category | Technology | Purpose |
|----------|------------|---------|
| **Language** | Python 3.12+ | Core runtime |
| **CLI** | Typer | Type-safe command interface |
| **TUI** | Textual | Interactive terminal UI |
| **Configuration** | Dynaconf + Pydantic | Multi-source config with validation |
| **Plugin System** | pluggy | Extensible source/transform/sink plugins |
| **Data Handling** | pandas | Tabular data operations |
| **Database** | SQLAlchemy Core | Audit storage (no ORM) |
| **Migrations** | Alembic | Schema versioning |
| **DAG Operations** | NetworkX | Graph validation and traversal |
| **JSON Canonicalization** | rfc8785 | Deterministic hashing (RFC 8785/JCS) |
| **Retries** | tenacity | Industry-standard backoff |
| **Observability** | OpenTelemetry, structlog | Telemetry and logging |
| **Rate Limiting** | pyrate-limiter | External call throttling |

## Core Architecture Pattern: SDA Model

```
SENSE (Sources) → DECIDE (Transforms/Gates) → ACT (Sinks)
     │                    │                        │
     └─────────── Landscape (Audit Trail) ─────────┘
```

Every decision is recorded in the Landscape audit database with full lineage.

## Identified Subsystems

Based on directory analysis and code inspection, the following major subsystems were identified:

### Tier 1: Core Framework (High Coupling)

| # | Subsystem | Location | Responsibility |
|---|-----------|----------|----------------|
| 1 | **Engine** | `engine/` | Pipeline execution orchestration |
| 2 | **Landscape** | `core/landscape/` | Audit trail backbone |
| 3 | **Contracts** | `contracts/` | Cross-boundary type definitions |
| 4 | **DAG** | `core/dag.py` | Execution graph construction |
| 5 | **Configuration** | `core/config.py` + `contracts/config/` | Settings validation and runtime config |

### Tier 2: Infrastructure Services

| # | Subsystem | Location | Responsibility |
|---|-----------|----------|----------------|
| 6 | **Telemetry** | `telemetry/` | Operational visibility and export |
| 7 | **Plugin System** | `plugins/` (base, protocols, manager) | Plugin discovery and management |
| 8 | **Checkpoint** | `core/checkpoint/` | Crash recovery |
| 9 | **Payload Store** | `core/payload_store.py` | Content-addressable blob storage |
| 10 | **Rate Limiting** | `core/rate_limit/` | External call throttling |

### Tier 3: Plugin Implementations

| # | Subsystem | Location | Responsibility |
|---|-----------|----------|----------------|
| 11 | **Sources** | `plugins/sources/` | CSV, JSON, Null source plugins |
| 12 | **Transforms** | `plugins/transforms/` | Field mapping, filtering, passthrough |
| 13 | **Sinks** | `plugins/sinks/` | CSV, JSON, Database output |
| 14 | **LLM Plugins** | `plugins/llm/` | Azure OpenAI, OpenRouter integration |
| 15 | **Clients** | `plugins/clients/` | HTTP, LLM, Replayer, Verifier |

### Tier 4: User Interfaces

| # | Subsystem | Location | Responsibility |
|---|-----------|----------|----------------|
| 16 | **CLI** | `cli.py`, `cli_helpers.py` | Command-line interface |
| 17 | **TUI** | `tui/` | Textual-based explain UI |
| 18 | **MCP Server** | `mcp/` | Model Context Protocol for analysis |

### Tier 5: Testing Infrastructure

| # | Subsystem | Location | Responsibility |
|---|-----------|----------|----------------|
| 19 | **ChaosLLM** | `testing/chaosllm/` | LLM testing server |
| 20 | **Testing Utils** | `testing/` | Test helpers |

## Key Entry Points

1. **CLI Entry**: `cli.py` → `app = typer.Typer()` → commands (run, resume, validate, explain)
2. **Pipeline Execution**: `cli.py` → `Orchestrator.execute()` → `RowProcessor.process_row()`
3. **Audit Queries**: `Landscape.explain()` → `LandscapeRecorder` → SQLAlchemy queries
4. **MCP Analysis**: `mcp/server.py` → Read-only audit database tools

## Architectural Patterns Observed

### 1. Three-Tier Trust Model
- **Tier 1 (Full Trust)**: Audit database - crash on any anomaly
- **Tier 2 (Elevated Trust)**: Pipeline data - validated but wrap operations
- **Tier 3 (Zero Trust)**: External data - validate at boundary

### 2. Settings → Runtime Configuration Pattern
Explicit two-layer conversion to prevent field orphaning:
```
Settings (Pydantic) → from_settings() → RuntimeConfig (dataclass) → Engine
```

### 3. Protocol-Based Plugin System
Plugins implement protocols (`SourceProtocol`, `TransformProtocol`, `SinkProtocol`, `GateProtocol`) discovered via pluggy hooks.

### 4. DAG-Based Execution
Pipelines compile to NetworkX DAGs with:
- Token-based row identity tracking
- Fork/Join support for parallel paths
- Coalesce points for merging branches

### 5. Composite Primary Keys
The `nodes` table uses `(node_id, run_id)` composite key - queries must use both keys.

## Codebase Statistics

| Metric | Value |
|--------|-------|
| Total Python LOC | ~58,000 |
| Source directories | 20 |
| Python files | 100+ |
| Subsystems identified | 20 |

## Complexity Assessment

- **Overall Complexity**: HIGH
- **Coupling**: Moderate (contracts isolate boundaries)
- **Cohesion**: High (clear subsystem responsibilities)
- **Documentation**: Extensive (CLAUDE.md is comprehensive)

## Recommended Orchestration Strategy

Given:
- 20 subsystems identified
- High interdependencies in core tier
- Large codebase (58K LOC)

**Recommendation: PARALLEL analysis** with subsystem grouping:

| Group | Subsystems | Rationale |
|-------|------------|-----------|
| A | Engine + DAG + Processor | Tightly coupled execution layer |
| B | Landscape + Contracts | Audit and type contracts |
| C | Plugins (Sources/Transforms/Sinks) | Independent implementations |
| D | Telemetry + Checkpoint + Rate Limit | Infrastructure services |
| E | CLI + TUI + MCP | User interfaces |

## Risk Areas Identified

1. **Composite Key Complexity**: `nodes` table requires careful join handling
2. **Trust Model Enforcement**: Three-tier requires consistent application
3. **Settings→Runtime Mapping**: Field orphaning risk without CI verification
4. **No Legacy Code Policy**: Strict - any backwards compatibility is forbidden

## Next Steps

1. Generate detailed subsystem catalog entries
2. Analyze inter-subsystem dependencies
3. Create C4 architecture diagrams
4. Produce code quality assessment
5. Prepare architect handover document
