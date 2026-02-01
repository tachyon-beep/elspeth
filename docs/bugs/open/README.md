# Open Bugs - Organized by Subsystem

This directory contains all open bugs organized by the subsystem they affect. This structure enables:
- **Systematic fixing**: Tackle related bugs together
- **Developer assignment**: Assign subsystem experts to relevant bugs
- **Quality insights**: See where bugs cluster

## Directory Structure

```
open/
├── cli/                      # Command-line interface (0 P1, 1 P2, 1 P3)
├── contracts/                # Contract validation (3 P2, 2 P3)
├── core-canonical/           # Canonicalization (1 P2)
├── core-checkpoint/          # Checkpointing/recovery (2 P2, 2 P3)
├── core-config/              # Configuration system (2 P2, 1 P3)
├── core-dag/                 # DAG validation, graph construction (1 P1, 1 P2)
├── core-landscape/           # Audit trail, recovery, verifier (8 P2, 2 P3)
├── core-logging/             # Logging/telemetry output (1 P2)
├── core-rate-limit/          # Rate limiters (1 P2)
├── core-retention/           # Retention/purge (2 P2)
├── core-security/            # Secret handling (1 P2, 1 P3)
├── engine-coalesce/          # Fork/join/merge logic (1 P1)
├── engine-executors/         # Executor flow (1 P2)
├── engine-expression-parser/ # Expression parsing (1 P1)
├── engine-orchestrator/      # Pipeline execution, routing (1 P1, 3 P2, 2 P3)
├── engine-pooling/           # Pooling infrastructure (1 P2, 2 P3)
├── engine-processor/         # Token management, outcomes (1 P2, 2 P3)
├── engine-retry/             # Retry logic (1 P2, 2 P3)
├── engine-spans/             # Observability, tracing (2 P2, 1 P3)
├── engine-tokens/            # Token lineage (1 P2)
├── engine-triggers/          # Trigger evaluation (1 P2)
├── mcp/                      # MCP tooling (2 P2)
├── plugins-azure/            # Azure plugin pack (1 P2, 1 P3)
├── plugins-llm/              # Base LLM transforms (5 P2, 1 P3)
├── plugins-sinks/            # Sink implementations (2 P2, 1 P3)
├── plugins-sources/          # Source implementations (1 P3)
└── plugins-transforms/       # Transform implementations (1 P1)
```

## Bug Counts by Subsystem

| Subsystem | P1 Bugs | P2 Bugs | P3 Bugs | Total | Notes |
|-----------|---------|---------|---------|-------|-------|
| **core-landscape** | 0 | 8 | 2 | 10 | Export + verifier gaps |
| **engine-orchestrator** | 1 | 3 | 2 | 6 | Run lifecycle + cleanup |
| **contracts** | 0 | 3 | 2 | 5 | Schema/contract validation |
| **plugins-llm** | 0 | 5 | 1 | 6 | LLM audit + semantics |
| **engine-coalesce** | 1 | 0 | 0 | 1 | Fork/join timeouts |
| **core-checkpoint** | 0 | 2 | 2 | 4 | Resume + checkpoint format |
| **core-config** | 0 | 2 | 1 | 3 | Plugin config validation |
| **engine-pooling** | 0 | 1 | 2 | 3 | Pooling/batching |
| **engine-processor** | 0 | 1 | 2 | 3 | Token handling |
| **engine-retry** | 0 | 1 | 2 | 3 | Retry semantics |
| **engine-spans** | 0 | 2 | 1 | 3 | Tracing |
| **core-rate-limit** | 0 | 1 | 0 | 1 | Rate limiter correctness |
| **plugins-sinks** | 0 | 2 | 1 | 3 | Sink validation |
| **cli** | 0 | 1 | 1 | 2 | CLI behavior |
| **core-dag** | 1 | 1 | 0 | 2 | DAG validation |
| **core-payload** | 0 | 0 | 0 | 0 | Payload storage (all fixed) |
| **core-retention** | 0 | 2 | 0 | 2 | Retention |
| **core-security** | 0 | 1 | 1 | 2 | Secret handling |
| **engine-executors** | 0 | 1 | 0 | 1 | Executor failures |
| **mcp** | 0 | 2 | 0 | 2 | MCP tooling |
| **plugins-azure** | 0 | 1 | 1 | 2 | Azure plugin pack |
| **core-canonical** | 0 | 1 | 0 | 1 | Canonicalization |
| **core-logging** | 0 | 1 | 0 | 1 | Logging output |
| **engine-expression-parser** | 1 | 0 | 0 | 1 | Expression errors |
| **engine-tokens** | 0 | 1 | 0 | 1 | Token lineage |
| **engine-triggers** | 0 | 1 | 0 | 1 | Trigger conditions |
| **plugins-sources** | 0 | 0 | 1 | 1 | Source validation |
| **plugins-transforms** | 1 | 0 | 0 | 1 | Transform audit |
| **TOTAL** | **3** | **43** | **21** | **67** | All bugs organized |

## Recommended Fix Order

### Phase 1: Critical Data Integrity (P1 - Fix This Sprint)
1. **engine-coalesce/P1-2026-01-30-require-all-timeout-ignored** - Non-terminal rows in streaming
2. **engine-expression-parser/P1-2026-01-31-expression-errors-bubble-raw** - Hard crash + opaque errors
3. **plugins-transforms/P1-2026-01-31-context-record-call-bypasses-allocator** - call_index collisions

Note: P1s closed during RC1 bug hunt:
- **core-payload/P1-2026-01-31-payload-store-path-traversal** - Fixed with hash validation + containment
- **cli/P1-2026-01-31-settings-path-missing-silent-fallback** - Already fixed in commit 8ab8fb36
- **engine-orchestrator/P1-2026-01-31-quarantine-outcome-before-durability** - Fixed in commit e039498b
- **core-dag/P1-2026-01-31-gate-drops-computed-schema-guarantees** - Fixed in commit 08cec258

### Phase 2: Audit Trail Completeness (Fix This Sprint/Next)
- **core-landscape/** - Exporter completeness, verifier correctness
- **contracts/** - Schema compatibility and enum validation
- **engine-orchestrator/** - Cleanup error surfacing + output canonical validation
- **plugins-llm/** - Azure/OpenRouter call recording and retry semantics

### Phase 3: Quality & Observability (Next Sprint)
- **engine-spans/** - Span naming/metadata issues
- **engine-pooling/** - Pool stats + batching examples
- **core-logging/** - JSON log output consistency

## Subsystem Ownership

### CORE Subsystem
**Owner:** Systems architect
**Files:** `src/elspeth/core/`
- `landscape/` - export, verifier, run repository
- `checkpoint/` - resume + checkpoint format
- `dag.py` - edge compatibility + coalesce validation
- `payload_store.py` - path traversal + required payload storage
- `rate_limit/` - atomicity + stale counters

### ENGINE Subsystem
**Owner:** Pipeline execution expert
**Files:** `src/elspeth/engine/`
- `coalesce_executor.py` - timeouts + branch handling
- `orchestrator.py` - cleanup + quarantine durability ordering
- `executors.py` - config gate missing-edge handling
- `processor.py` - token span + outcome handling

### PLUGINS Subsystem
**Owner:** Plugin developer
**Files:** `src/elspeth/plugins/`
- `llm/` - multi-query output semantics, call recording
- `transforms/` - call_index allocation
- `sinks/` - schema validation, payload size issues

## Verification Status

**Open bugs (as of 2026-02-01): 3 P1, 43 P2, 21 P3 = 67 total.**

**Triage updates (2026-02-01):**
- Removed 17 open entries that already existed under `docs/bugs/closed/` (duplicates).
- Moved `P3-2026-01-21-verifier-ignore-order-hides-drift.md` to closed (Phase 1 implemented).
- Normalized four misfiled bugs into subsystem folders with standard filenames.
- Verified all remaining P1s; closed two that are now fixed (`P1-2026-01-30-payload-store-optional`, `P1-2026-01-31-sink-flush-failure-leaves-open-states`).
- Closed `P2-2026-01-22-coalesce-timeout-failures-unrecorded` (fixed coalesce failure recording).
- Closed `P3-2026-01-22-engine-artifacts-legacy-shim` (removed legacy re-export).
- Closed `P3-2026-01-31-payload-store-legacy-reexport` (removed legacy re-export).
- Closed `P3-2026-01-31-rowresult-legacy-accessors` (removed legacy accessors).

**Reports:**
- Original verification: `docs/bugs/VERIFICATION-REPORT-2026-01-25.md`
- Pending verification: `docs/bugs/VERIFICATION-REPORT-PENDING-2026-01-25.md`
