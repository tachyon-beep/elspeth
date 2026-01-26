# ELSPETH Architecture Analysis Report

**Analysis Date:** 2026-01-27
**Status:** RC-1 (Release Candidate 1)
**Analyst:** Claude Architecture Analysis System

---

## Executive Summary

ELSPETH is a **domain-agnostic framework for auditable Sense/Decide/Act (SDA) pipelines** designed for high-stakes accountability scenarios. The architecture is well-designed, type-safe, and built with comprehensive audit trail capabilities. The codebase is in RC-1 status with active bug hunting underway.

### Key Findings

| Category | Assessment |
|----------|------------|
| **Architecture Quality** | High - Clean layered design with clear separation of concerns |
| **Code Quality** | High - Strong type system, comprehensive testing structure |
| **Auditability** | Excellent - Complete traceability with hash integrity |
| **Extensibility** | High - pluggy-based plugin system with protocol contracts |
| **Maintainability** | Medium-High - Some large files need attention |
| **Test Coverage** | Comprehensive - Mirrors source structure with property tests |

### Critical Strengths

1. **Three-Tier Trust Model** - Clear data trust boundaries (External/Pipeline/Audit)
2. **Hash Integrity** - RFC 8785 canonical JSON for deterministic audit hashing
3. **Token-Based Lineage** - Complete traceability through fork/coalesce operations
4. **Type-Safe Contracts** - Pydantic models and Protocol-based interfaces
5. **Crash Recovery** - Checkpoint system with topology validation

### Areas for Attention

1. **Large Single Files** - orchestrator.py (92KB), dag.py (38KB), config.py (46KB)
2. **TUI Incomplete** - Placeholder implementation
3. **Documentation Gaps** - Some edge cases undocumented
4. **RC-1 Bug Status** - Active bug hunting indicates stability work needed

---

## System Overview

### Purpose

ELSPETH provides scaffolding for data processing workflows where every decision must be traceable to its source, regardless of whether the "decide" step is an LLM, ML model, rules engine, or threshold check.

### Core Principles

1. **Attributability** - Every output can be traced to source data, configuration, and code version
2. **No Silent Drops** - Every row reaches a terminal state (COMPLETED, FAILED, QUARANTINED, etc.)
3. **Hash Integrity** - Hashes survive payload deletion for verification
4. **No Inference** - If it's not recorded, it didn't happen

### Architecture Style

- **Layered Architecture** with clear dependency direction
- **Plugin-Based Extensibility** via pluggy hooks
- **Event-Driven Observability** for CLI/TUI consumption
- **Repository Pattern** for audit trail access

---

## Subsystem Analysis Summary

### Core Layer (Audit Infrastructure)

| Subsystem | Purpose | Quality | Risk |
|-----------|---------|---------|------|
| **Landscape** | Audit trail database | High | Low |
| **Checkpoint** | Crash recovery | High | Low |
| **Retention** | Payload purge | High | Low |
| **Canonical JSON** | Deterministic hashing | High | Low |

**Assessment:** Core audit infrastructure is robust with comprehensive hash integrity and topology validation. The Three-Tier Trust Model is consistently applied.

### Engine Layer (Execution)

| Subsystem | Purpose | Quality | Risk |
|-----------|---------|---------|------|
| **Orchestrator** | Run lifecycle | High | Medium |
| **RowProcessor** | Transform execution | High | Medium |
| **Executors** | Plugin wrappers | High | Low |
| **TokenManager** | Lineage tracking | High | Low |
| **CoalesceExecutor** | Fork-join barrier | Medium | Medium |

**Assessment:** Engine is well-designed with clear state machines. The work queue pattern handles fork operations correctly. Main concern is complexity concentration in large files.

### Plugin Layer (Extensibility)

| Subsystem | Purpose | Quality | Risk |
|-----------|---------|---------|------|
| **Plugin Framework** | Registration/discovery | High | Low |
| **Sources** | Data ingestion | High | Low |
| **Transforms** | Processing | High | Low |
| **Sinks** | Output | High | Low |
| **LLM Integration** | AI classification | High | Low |
| **Azure Integration** | Cloud services | Medium | Low |

**Assessment:** Plugin system is well-structured with clear contracts. Protocol-based design allows flexibility without inheritance coupling.

### Interface Layer

| Subsystem | Purpose | Quality | Risk |
|-----------|---------|---------|------|
| **CLI** | Command interface | High | Low |
| **TUI** | Lineage exploration | Low | Medium |
| **Events** | Observability | High | Low |

**Assessment:** CLI is functional but TUI is incomplete (placeholder widgets). Events system is well-designed with Protocol-based bus.

---

## Architectural Patterns

### Pattern 1: Three-Tier Trust Model

```
Tier 3 (External)     →  Tier 2 (Pipeline)     →  Tier 1 (Audit)
Zero Trust               Elevated Trust            Full Trust
Coerce + Validate        Expect Types              Crash on Anomaly
```

**Implementation:** Sources coerce, Transforms expect, Landscape crashes. Consistently applied across all subsystems.

### Pattern 2: Token-Based Lineage

- `row_id` - Stable source identity (never changes)
- `token_id` - Instance at DAG position (changes on fork/coalesce)
- `fork_group_id`, `join_group_id`, `expand_group_id` - Operation tracking

**Implementation:** Clean separation in tokens.py with defensive deepcopy on fork.

### Pattern 3: Deterministic Hashing

- Two-phase canonicalization (normalize → RFC 8785)
- Strict NaN/Infinity rejection
- Topology hashing for checkpoint validation

**Implementation:** canonical.py with explicit rejection of problematic values.

### Pattern 4: Executor Wrapper

```python
begin_node_state() → plugin_call() → complete_node_state()
```

**Implementation:** Consistent across TransformExecutor, GateExecutor, AggregationExecutor, SinkExecutor.

---

## Dependency Analysis

### Layer Dependencies

```
Layer 6: CLI, TUI
    ↓
Layer 5: Engine (Orchestrator, Processor, Executors)
    ↓
Layer 4: Plugins (Sources, Transforms, Sinks, LLM, Azure)
    ↓
Layer 3: Core Services (Config, DAG, Landscape, Checkpoint)
    ↓
Layer 2: Core Utilities (Canonical, Events, Logging)
    ↓
Layer 1: Contracts (Types, Enums, Protocols)
```

**Assessment:** Clean dependency direction with no circular dependencies. TYPE_CHECKING used to avoid import cycles.

### External Dependencies

| Dependency | Purpose | Risk |
|------------|---------|------|
| **pluggy** | Plugin system | Low (battle-tested) |
| **NetworkX** | DAG algorithms | Low (mature) |
| **Pydantic** | Validation | Low (v2 stable) |
| **SQLAlchemy** | Database | Low (mature) |
| **rfc8785** | Canonical JSON | Low (RFC standard) |
| **Textual** | TUI | Medium (evolving API) |

---

## Security Considerations

### Secret Handling

- **SanitizedDatabaseUrl** and **SanitizedWebhookUrl** prevent credential leaks at type level
- HMAC fingerprinting for secrets
- No secrets stored in audit trail

### Trust Boundaries

- External data validated at source boundary
- Pipeline data assumed type-correct
- Audit data crashes on anomaly (evidence tampering prevention)

### Recommendations

1. Document all external call boundaries in transforms
2. Add security review for new plugins
3. Consider rate limiting at source level

---

## Performance Considerations

### Identified Bottlenecks

1. **Deepcopy on Fork** - Could be expensive for large nested structures
2. **Work Queue Iteration** - MAX_WORK_QUEUE_ITERATIONS guard (10,000) suggests potential runaway
3. **Single-Threaded Execution** - No parallel row processing within a run

### Memory Considerations

1. **Batch Buffering** - Large batches held in memory
2. **Payload Storage** - Large blobs separated to PayloadStore
3. **Token Deepcopy** - Each fork creates full copy

### Recommendations

1. Profile deepcopy impact for production workloads
2. Consider streaming for very large sources
3. Evaluate parallel row processing for throughput

---

## Testing Assessment

### Test Structure

```
tests/
├── core/           # Core subsystem tests
├── engine/         # Engine tests
├── plugins/        # Plugin tests (mirrors source)
├── integration/    # Cross-subsystem tests
├── system/         # End-to-end and recovery tests
├── property/       # Hypothesis property tests
└── contracts/      # Contract compliance tests
```

**Assessment:** Comprehensive structure with property-based testing for critical paths.

### Test Patterns

- **Property Tests:** Canonical JSON, contract compliance
- **Integration Tests:** Full pipeline execution
- **System Tests:** Audit verification, crash recovery
- **Contract Tests:** Source/Transform/Sink protocol compliance

### Gaps Identified

1. TUI has minimal tests (placeholder implementation)
2. Some edge cases in coalesce logic untested
3. Performance benchmarks could be added

---

## Technical Debt Inventory

### High Priority

| Item | Location | Impact |
|------|----------|--------|
| orchestrator.py size | engine/ | Maintainability |
| TUI placeholder | tui/ | Feature completeness |
| Coalesce deadlock detection | coalesce_executor.py | Reliability |

### Medium Priority

| Item | Location | Impact |
|------|----------|--------|
| dag.py size | core/ | Maintainability |
| config.py size | core/ | Maintainability |
| Dynamic schema validation | dag.py | Type safety |
| Batch memory limits | batching/ | Scalability |

### Low Priority

| Item | Location | Impact |
|------|----------|--------|
| bytes_freed tracking | retention/ | Observability |
| Node ID hash collision | dag.py | Edge case |
| Sink idempotency defaults | sinks/ | Configuration |

---

## Recommendations Summary

### Immediate (RC-1 Stabilization)

1. Complete TUI implementation or mark as "Preview"
2. Add coalesce timeout/deadlock detection
3. Document all RC-1 known limitations

### Short-Term (Post-RC-1)

1. Extract orchestrator.py into smaller modules
2. Extract dag.py validation into separate module
3. Add performance benchmarks
4. Complete documentation for edge cases

### Long-Term (Future Releases)

1. Evaluate parallel row processing
2. Consider streaming for large sources
3. Add plugin sandboxing for future user plugins
4. Enhance TUI with full lineage exploration

---

## Conclusion

ELSPETH demonstrates a well-architected system for auditable data pipelines. The Three-Tier Trust Model, hash-based integrity, and token-based lineage provide a solid foundation for high-stakes accountability scenarios.

The codebase is in good shape for RC-1 with clear patterns and comprehensive contracts. Main areas for attention are:

1. **Complexity Hotspots** - Large files that should be modularized
2. **Feature Completeness** - TUI needs implementation
3. **Bug Stabilization** - Active bug hunting indicates ongoing refinement

The architecture supports the framework's core mission: *"I don't know what happened" is never an acceptable answer.*

---

## Appendices

- **Appendix A:** [Discovery Findings](01-discovery-findings.md)
- **Appendix B:** [Subsystem Catalog](02-subsystem-catalog.md)
- **Appendix C:** [Architecture Diagrams](03-diagrams.md)
- **Appendix D:** [Quality Assessment](05-quality-assessment.md)
- **Appendix E:** [Architect Handover](06-architect-handover.md)
