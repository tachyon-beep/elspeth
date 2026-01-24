# Open Bugs - Organized by Subsystem

This directory contains all open bugs organized by the subsystem they affect. This structure enables:
- **Systematic fixing**: Tackle related bugs together
- **Developer assignment**: Assign subsystem experts to relevant bugs
- **Quality insights**: See where bugs cluster

## Directory Structure

```
open/
├── cli/                  # Command-line interface (1 P1, 2 P3)
├── core-config/          # Configuration system (4 P2, 6 P3)
├── core-dag/             # DAG validation, graph construction (1 P1)
├── core-landscape/       # Audit trail, recovery, run repository (4 P1, 5 P2, 3 P3)
├── cross-cutting/        # Schema validation, multi-subsystem (1 P1, 3 P2, 1 P3)
├── engine-coalesce/      # Fork/join/merge logic (3 P1, 4 P2)
├── engine-orchestrator/  # Pipeline execution, routing (6 P1, 8 P2, 4 P3)
├── engine-pooling/       # Pooling infrastructure (2 P2, 3 P3)
├── engine-processor/     # Token management, outcomes (2 P1, 3 P2)
├── engine-retry/         # Retry logic (3 P2, 2 P3)
├── engine-spans/         # Observability, tracing (2 P2, 1 P3)
├── llm-azure/            # Azure LLM integration (3 P1, 8 P2, 1 P3)
├── plugins-llm/          # Base LLM transforms (4 P1, 1 P2, 2 P3)
├── plugins-sinks/        # Sink implementations (3 P1, 2 P2, 1 P3)
├── plugins-sources/      # Source implementations (2 P2, 1 P3)
└── plugins-transforms/   # Transform implementations (2 P1, 2 P2)
```

## Bug Counts by Subsystem

| Subsystem | P1 Bugs | P2 Bugs | P3 Bugs | Total | Focus Area |
|-----------|---------|---------|---------|-------|------------|
| **engine-orchestrator** | 6 | 8 | 4 | 18 | Aggregations, routing, quarantine ⚠️ LARGEST HOTSPOT |
| **llm-azure** | 3 | 8 | 1 | 12 | Azure integration, error handling ⚠️ HOTSPOT |
| **core-landscape** | 4 | 5 | 3 | 12 | Audit trail, recovery, verifier ⚠️ HOTSPOT |
| **core-config** | 0 | 4 | 6 | 10 | Expression validation, config contracts |
| **engine-coalesce** | 3 | 4 | 0 | 7 | Fork/join semantics, timeouts |
| **plugins-llm** | 4 | 1 | 2 | 7 | Client infrastructure, audit recording |
| **plugins-sinks** | 3 | 2 | 1 | 6 | Schema validation, mode handling |
| **engine-pooling** | 0 | 2 | 3 | 5 | Pooling infrastructure (NEW) |
| **engine-processor** | 2 | 3 | 0 | 5 | Token management, outcomes |
| **engine-retry** | 0 | 3 | 2 | 5 | Retry logic, backoff, audit |
| **cross-cutting** | 1 | 3 | 1 | 5 | Schema architecture, code quality |
| **plugins-transforms** | 2 | 2 | 0 | 4 | Type coercion, batch operations |
| **cli** | 1 | 0 | 2 | 3 | Command-line UX, explain command |
| **engine-spans** | 0 | 2 | 1 | 3 | Observability, tracing |
| **plugins-sources** | 0 | 2 | 1 | 3 | JSON parsing, validation |
| **core-dag** | 1 | 0 | 0 | 1 | Branch name validation |
| **TOTAL** | **30** | **49** | **27** | **106** | All bugs organized |

**Note:** Total includes bugs from both original triage (73) and pending verification (33 STILL VALID).

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

**All bugs (30 P1, 49 P2, 27 P3 = 106 total) verified and organized by subsystem (2026-01-25):**
- ✅ **93% STILL VALID** (99/107 bugs) - Real technical debt, accurate triage
- 🔄 **5 OBE** - Fixed by refactors or documentation-only
- ❌ **0 LOST** - No bugs invalidated by code changes
- ✅ **Detailed verification reports** - Each bug has comprehensive code analysis
- ✅ **Fix guidance** - Each bug has recommended fix with examples

**Verification Sources:**
- **Original triage (73 bugs):** 66 STILL VALID, 4 OBE (94% validation rate)
- **Pending triage (34 bugs):** 33 STILL VALID, 1 OBE (97% validation rate)
- **Combined:** 99 STILL VALID, 5 OBE (93% validation rate)

**Results by Priority:**
- **P1:** 29/30 STILL VALID (97%) - Nearly all critical bugs remain unfixed
- **P2:** 46/49 STILL VALID (94%) - High validation rate
- **P3:** 24/27 STILL VALID (89%) - Quality/enhancement issues

**Reports:**
- Original verification: `docs/bugs/VERIFICATION-REPORT-2026-01-25.md`
- Pending verification: `docs/bugs/VERIFICATION-REPORT-PENDING-2026-01-25.md`
