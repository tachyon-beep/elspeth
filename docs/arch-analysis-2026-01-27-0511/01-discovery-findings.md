# Discovery Findings

## Executive Summary

ELSPETH is a **domain-agnostic framework for auditable Sense/Decide/Act (SDA) pipelines** built for high-stakes accountability. The codebase is in RC-1 status with core architecture complete and active bug hunting underway.

**Key Metrics:**
- **Lines of Code:** ~45,600 Python (src and tests)
- **Python Files:** 133 source files
- **Subsystems Identified:** 11 major cohesive groups
- **Complexity Rating:** High (sophisticated type system, audit trail, DAG execution)

## Directory Structure

```
elspeth-rapid/
├── src/elspeth/          # Main package
│   ├── core/             # Infrastructure subsystems
│   │   ├── landscape/    # Audit trail database
│   │   ├── checkpoint/   # Recovery/resume support
│   │   ├── rate_limit/   # API rate limiting
│   │   ├── retention/    # Payload purge management
│   │   └── security/     # Secret handling
│   ├── engine/           # SDA execution engine
│   ├── plugins/          # Plugin subsystems
│   │   ├── sources/      # Data input (CSV, JSON, Null)
│   │   ├── transforms/   # Processing (mappers, filters, LLM)
│   │   ├── sinks/        # Output (CSV, JSON, Database)
│   │   ├── llm/          # LLM provider integrations
│   │   ├── azure/        # Azure-specific plugins
│   │   ├── batching/     # Batch processing support
│   │   ├── pooling/      # Resource pooling
│   │   └── clients/      # HTTP/API clients
│   ├── contracts/        # Type contracts and protocols
│   └── tui/              # Terminal UI (Textual)
├── tests/                # Comprehensive test suite
│   ├── core/             # Core subsystem tests
│   ├── engine/           # Engine tests
│   ├── plugins/          # Plugin tests (mirrored structure)
│   ├── integration/      # Cross-subsystem tests
│   ├── system/           # End-to-end and recovery tests
│   └── property/         # Hypothesis property tests
├── alembic/              # Database migrations
├── scripts/              # Development/CI tools
├── examples/             # Working pipeline examples
└── docs/                 # Documentation
```

## Technology Stack

### Core Framework

| Component | Technology | Version Constraint |
|-----------|------------|-------------------|
| CLI | Typer | >=0.21,<1 |
| TUI | Textual | >=7.2,<8 |
| Configuration | Dynaconf + Pydantic | >=3.2 / >=2.12 |
| Plugins | pluggy | >=1.6,<2 |
| Data | pandas | >=2.2,<3 |
| Database | SQLAlchemy Core | >=2.0,<3 |
| Migrations | Alembic | >=1.18,<2 |
| Retries | tenacity | >=9.0,<10 |

### Acceleration Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Canonical JSON | rfc8785 | Deterministic hashing (RFC 8785/JCS) |
| DAG Validation | NetworkX | Graph algorithms |
| Observability | OpenTelemetry | Distributed tracing |
| Logging | structlog | Structured events |
| Rate Limiting | pyrate-limiter | API throttling |
| Diffing | DeepDiff | Verify mode comparisons |
| Property Testing | Hypothesis | Automated edge cases |

### Optional Packs

| Pack | Technologies | Use Case |
|------|--------------|----------|
| LLM | Jinja2, OpenAI, LiteLLM | 100+ LLM providers |
| Azure | azure-storage-blob, azure-identity, azure-keyvault-secrets | Cloud integration |

## Entry Points

| Entry Point | File | Purpose |
|-------------|------|---------|
| CLI Main | `src/elspeth/cli.py` | Typer CLI application |
| Package | `src/elspeth/__init__.py` | Package exports |
| Scripts | `scripts/*.py` | Development tools |
| Migrations | `alembic/env.py` | Database schema |

### CLI Commands

- `elspeth run` - Execute pipeline with audit trail
- `elspeth validate` - Validate configuration without execution
- `elspeth explain` - Query lineage (TUI or JSON)
- `elspeth resume` - Resume failed run from checkpoint
- `elspeth purge` - Delete old payloads (retain hashes)
- `elspeth plugins list` - List available plugins
- `elspeth health` - Deployment health check

## Subsystem Identification

### 1. **Landscape (Audit Trail)**
- **Location:** `src/elspeth/core/landscape/`
- **Files:** 13 modules (~170KB)
- **Responsibility:** Complete audit trail with hash integrity
- **Key Patterns:** Repository pattern, SQLAlchemy Core, content hashing

### 2. **Engine (SDA Executor)**
- **Location:** `src/elspeth/engine/`
- **Files:** 14 modules (~280KB)
- **Responsibility:** DAG execution, row processing, orchestration
- **Key Patterns:** State machine, token-based lineage, retry management

### 3. **DAG (Execution Graph)**
- **Location:** `src/elspeth/core/dag.py`
- **Size:** ~38KB single file
- **Responsibility:** Pipeline topology, schema propagation, validation
- **Key Patterns:** NetworkX graph, composite primary keys

### 4. **Configuration**
- **Location:** `src/elspeth/core/config.py`
- **Size:** ~46KB single file
- **Responsibility:** Multi-source config, Pydantic validation
- **Key Patterns:** Dynaconf precedence, environment resolution

### 5. **Plugin Framework**
- **Location:** `src/elspeth/plugins/`
- **Files:** 40+ modules
- **Responsibility:** Extensible sources, transforms, sinks
- **Key Patterns:** pluggy hooks, protocol-based contracts

### 6. **Contracts**
- **Location:** `src/elspeth/contracts/`
- **Files:** 18 modules
- **Responsibility:** Type contracts, enums, result types
- **Key Patterns:** Discriminated unions, frozen dataclasses

### 7. **LLM Integration**
- **Location:** `src/elspeth/plugins/llm/`
- **Files:** 10 modules (~130KB)
- **Responsibility:** Azure OpenAI, OpenRouter, multi-query support
- **Key Patterns:** Template-based prompts, batch processing

### 8. **Azure Integration**
- **Location:** `src/elspeth/plugins/azure/`
- **Files:** 4 modules (~48KB)
- **Responsibility:** Blob storage source/sink, authentication
- **Key Patterns:** Async operations, managed identity

### 9. **Checkpoint/Recovery**
- **Location:** `src/elspeth/core/checkpoint/`
- **Responsibility:** Resume failed runs, topology validation
- **Key Patterns:** Checkpoint state machine, hash-based validation

### 10. **TUI (Explain Interface)**
- **Location:** `src/elspeth/tui/`
- **Files:** 6+ modules
- **Responsibility:** Interactive lineage exploration
- **Key Patterns:** Textual framework, screen navigation

### 11. **Development Tools**
- **Location:** `scripts/`
- **Files:** 10+ scripts
- **Responsibility:** Bug hunting, contract checking, CI/CD
- **Key Patterns:** AST analysis, static analysis

## Orchestration Strategy Decision

**Recommendation: PARALLEL execution** with coordinated subagents.

**Rationale:**
1. **Scale:** 11+ subsystems exceeds sequential threshold (5)
2. **Independence:** Most subsystems have clear boundaries
3. **Size:** 45K+ LOC requires distributed exploration
4. **Dependencies:** Well-defined through contracts

**Agent Allocation:**
- Agent 1: Landscape + Checkpoint (audit critical path)
- Agent 2: Engine + DAG (execution core)
- Agent 3: Plugin Framework + LLM + Azure (plugin ecosystem)
- Agent 4: Contracts + Config + TUI (supporting infrastructure)

## Initial Observations

### Architectural Strengths
1. **Strong Type System:** Pydantic models, Protocol-based contracts
2. **Audit-First Design:** Every decision traceable to source
3. **Clean Separation:** Plugin system isolates concerns
4. **Test Coverage:** Comprehensive test structure mirrors source

### Potential Concerns
1. **Large Single Files:** `dag.py` (38KB), `config.py` (46KB), `orchestrator.py` (92KB)
2. **RC-1 Status:** Active bug hunting suggests instability
3. **Complex Trust Model:** Three-tier data trust requires careful adherence
4. **Hash Integrity:** RFC 8785 dependency is critical path

### CLAUDE.md Directives (Non-Negotiable)
- No defensive programming patterns
- No legacy code or backwards compatibility
- Crash on audit trail anomalies (Tier 1)
- Wrap operations on row values (Tier 2)
- Validate external data at boundary (Tier 3)

## Next Steps

1. Spawn parallel exploration agents for detailed subsystem analysis
2. Generate subsystem catalog with dependency mapping
3. Produce C4 diagrams at system and container levels
4. Synthesize final report with quality assessment
5. Create architect handover for improvement planning
