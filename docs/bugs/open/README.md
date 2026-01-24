# Open Bugs - Organized by Subsystem

This directory contains all open bugs organized by the subsystem they affect. This structure enables:
- **Systematic fixing**: Tackle related bugs together
- **Developer assignment**: Assign subsystem experts to relevant bugs
- **Quality insights**: See where bugs cluster

## Directory Structure

```
open/
├── core-landscape/       # Audit trail, recovery, run repository (3 bugs)
├── core-dag/             # DAG validation, graph construction (1 bug)
├── engine-coalesce/      # Fork/join/merge logic (4 bugs: 3 P1, 1 P2)
├── engine-orchestrator/  # Pipeline execution, routing (2 bugs)
├── engine-processor/     # Token management, outcomes (1 bug)
├── plugins-transforms/   # Transform implementations (2 bugs)
├── plugins-sinks/        # Sink implementations (3 bugs)
├── llm-azure/            # Azure LLM integration (3 bugs)
└── cross-cutting/        # Schema validation, multi-subsystem (2 bugs)
```

## Bug Counts by Subsystem

| Subsystem | P1 Bugs | P2 Bugs | P3 Bugs | Total | Focus Area |
|-----------|---------|---------|---------|-------|------------|
| **llm-azure** | 3 | 9 | 1 | 13 | Azure integration, error handling ⚠️ LARGEST |
| **engine-coalesce** | 3 | 4 | 0 | 7 | Fork/join semantics, timeouts ⚠️ HOTSPOT |
| **core-landscape** | 3 | 2 | 2 | 7 | Recovery, audit integrity |
| **engine-orchestrator** | 2 | 4 | 2 | 8 | Aggregation, quarantine, resume |
| **plugins-sinks** | 3 | 2 | 1 | 6 | Schema validation, mode handling |
| **plugins-transforms** | 2 | 2 | 0 | 4 | Type coercion, batch operations |
| **cross-cutting** | 1 | 3 | 0 | 4 | Schema architecture |
| **engine-processor** | 1 | 3 | 0 | 4 | Token management, spans |
| **plugins-sources** | 0 | 2 | 1 | 3 | JSON parsing, validation |
| **core-config** | 0 | 2 | 1 | 3 | Config contracts, metadata |
| **engine-retry** | 0 | 2 | 2 | 4 | Retry logic, backoff |
| **engine-spans** | 0 | 2 | 1 | 3 | Observability, tracing |
| **core-dag** | 1 | 0 | 0 | 1 | Branch name validation |

## Recommended Fix Order

### Phase 1: Critical Data Integrity (P0 Severity - Fix This Week)
1. **plugins-sinks/P1-databasesink-noncanonical-hash** - Audit integrity violation
2. **engine-coalesce/P1-coalesce-timeouts-never-fired** - Feature completely broken
3. **engine-coalesce/P1-coalesce-late-arrivals-duplicate-merge** - Data corruption
4. **llm-azure/P1-azure-batch-missing-audit-payloads** - Auditability violation
5. **core-dag/P1-duplicate-branch-names-break-coalesce** - Silent data loss
6. **engine-orchestrator/P1-orchestrator-aggregation-flush-output-mode-ignored** - Token identity broken
7. **core-landscape/P1-recovery-skips-rows-multi-sink** - Recovery broken

### Phase 2: Audit Trail Completeness (Fix This Sprint)
- **engine-coalesce/** - Fix all 4 coalesce bugs together
- **llm-azure/** - Fix all 3 Azure audit tracking bugs
- **engine-orchestrator/** - Fix quarantine outcomes
- **engine-processor/** - Fix group ID propagation

### Phase 3: Type Safety & Validation (Next Sprint)
- **plugins-transforms/** - Remove type coercion from transforms
- **plugins-sinks/** - Add schema/mode validation
- **cross-cutting/** - Design hybrid schema system
- **core-landscape/** - Fix export status enum validation

## Subsystem Ownership

### CORE Subsystem
**Owner:** Systems architect
**Files:** `src/elspeth/core/`
- `landscape/` - 3 bugs (recovery, run repository, reproducibility)
- `dag.py` - 1 bug (branch name validation)

### ENGINE Subsystem
**Owner:** Pipeline execution expert
**Files:** `src/elspeth/engine/`
- `coalesce_executor.py` - 4 bugs (timeouts, duplicates, outcomes, metadata)
- `orchestrator.py` - 2 bugs (quarantine outcomes, flush modes)
- `processor.py` - 1 bug (token group IDs)

### PLUGINS Subsystem
**Owner:** Plugin developer
**Files:** `src/elspeth/plugins/`
- `transforms/batch_*.py` - 2 bugs (type coercion violations)
- `sinks/csv_sink.py` - 2 bugs (append schema, mode validation)
- `sinks/database_sink.py` - 1 bug (canonical hash)

### LLM Integration
**Owner:** LLM/Azure specialist
**Files:** `src/elspeth/plugins/llm/`, `src/elspeth/plugins/transforms/azure/`
- `azure_batch.py` - 1 bug (missing audit payloads)
- `azure/content_safety.py`, `azure/prompt_shield.py` - 1 bug (global call_index)
- `azure_multi_query.py` - 1 bug (synthetic state_id)

### CROSS-CUTTING
**Owner:** Architecture team
**Files:** Multiple subsystems
- Schema validation system - 2 bugs (dynamic schema skipping, config-dependent fields)

## Verification Status

**All 18 P1 bugs have been verified against current codebase (2026-01-25):**
- ✅ **100% STILL VALID** - All bugs are real, none are OBE or lost
- ✅ **Detailed verification reports** - Each bug has comprehensive code analysis
- ✅ **Fix guidance** - Each bug has recommended fix with examples

See `docs/bugs/BUG-TRIAGE-REPORT-2026-01-24.md` for full triage analysis.
