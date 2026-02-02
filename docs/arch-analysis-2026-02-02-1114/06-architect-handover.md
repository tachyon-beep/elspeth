# ELSPETH Architect Handover Document

This document enables transition from architecture analysis to improvement planning.

---

## Current State Summary

### Architecture Maturity: HIGH

ELSPETH is a well-architected RC-2 framework with:
- ~58K production LOC across 20 subsystems
- Complete audit trail (Landscape)
- Three-tier trust model
- Protocol-based plugin system
- Extensive test coverage (187K LOC)

### Critical Files

| File | Lines | Criticality | Notes |
|------|-------|-------------|-------|
| `engine/orchestrator.py` | 3100 | Critical | Run lifecycle, all orchestration |
| `engine/processor.py` | 1918 | Critical | DAG traversal, fork/join |
| `core/landscape/recorder.py` | 2700 | Critical | All audit recording |
| `core/dag.py` | 1000 | Critical | Graph construction/validation |
| `contracts/__init__.py` | 140 | High | Type export surface |

### Key Patterns to Preserve

1. **Three-Tier Trust Model** - MUST NOT introduce defensive patterns
2. **Settings→Runtime Mapping** - MUST use `from_settings()` pattern
3. **Contracts as Leaf Module** - NO outbound dependencies
4. **No Legacy Code Policy** - NO backwards compatibility
5. **Test Path Integrity** - USE production factories

---

## Improvement Roadmap

### Phase 1: Immediate (Pre-Release Stabilization)

| ID | Task | Priority | Effort | Risk |
|----|------|----------|--------|------|
| P1-01 | Validate all composite PK queries | High | 2h | Low |
| P1-02 | Run mutation testing on processor | High | 4h | Low |
| P1-03 | Verify aggregation checkpoint restore | High | 2h | Medium |
| P1-04 | Review error routing paths | Medium | 3h | Low |

### Phase 2: Post-Release (Technical Debt)

| ID | Task | Priority | Effort | Risk |
|----|------|----------|--------|------|
| P2-01 | Extract orchestrator modules | Medium | 8h | Medium |
| P2-02 | Refactor aggregation state machine | Medium | 12h | Medium |
| P2-03 | Generate API documentation | Low | 4h | Low |
| P2-04 | Add SQL query linting | Low | 6h | Low |
| P2-05 | Create plugin development guide | Low | 8h | Low |

### Phase 3: Future Enhancements

| ID | Task | Priority | Effort | Risk |
|----|------|----------|--------|------|
| P3-01 | Horizontal scaling patterns | Low | 40h | High |
| P3-02 | Real-time dashboard integration | Low | 20h | Medium |
| P3-03 | Streaming source support | Low | 30h | Medium |
| P3-04 | Multi-run comparison tooling | Low | 16h | Low |

---

## Architectural Constraints

### MUST NOT Change

1. **Landscape Schema** without migration
   - All audit data is permanent
   - Schema changes require Alembic migrations
   - Composite PK `(node_id, run_id)` is fundamental

2. **Three-Tier Trust Model**
   - Tier 1 crashes are intentional (not bugs)
   - Tier 3 boundary validation is required
   - No defensive `.get()` patterns

3. **Settings→Runtime Pattern**
   - Every Settings field MUST map to RuntimeConfig
   - `from_settings()` is the ONLY conversion path
   - FIELD_MAPPINGS documents renames

4. **Contracts Leaf Module**
   - NO imports from core/ or engine/
   - All types flow outward
   - Settings classes stay in core.config

### MAY Change

1. **Large file organization** - Can extract modules
2. **Internal helper functions** - Can refactor
3. **Test organization** - Can restructure
4. **Documentation format** - Can add generated docs
5. **Telemetry exporters** - Can add new exporters

---

## Known Technical Debt

### High Priority

| ID | Description | Impact | Location |
|----|-------------|--------|----------|
| TD-01 | Aggregation complexity | Maintainability | processor.py:400-700 |
| TD-02 | Large orchestrator file | Readability | orchestrator.py |
| TD-03 | Inline SQL in recorder | Consistency | recorder.py |

### Medium Priority

| ID | Description | Impact | Location |
|----|-------------|--------|----------|
| TD-04 | Missing API docs | Onboarding | N/A |
| TD-05 | Composite PK query patterns | Reliability | Multiple |
| TD-06 | Event type proliferation | Complexity | events.py |

### Low Priority

| ID | Description | Impact | Location |
|----|-------------|--------|----------|
| TD-07 | Plugin dev guide | Adoption | N/A |
| TD-08 | Performance benchmarks | Optimization | N/A |
| TD-09 | Troubleshooting consolidation | Operations | docs/runbooks |

---

## Extension Points

### Adding New Sources

1. Create class implementing `SourceProtocol`
2. Add configuration class extending `SourceConfig`
3. Register in `plugins/sources/__init__.py`
4. Add tests in `tests/plugins/sources/`

```python
class MySource:
    name = "my_source"
    determinism = Determinism.IO_READ

    def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
        ...

    def close(self) -> None:
        ...
```

### Adding New Transforms

1. Create class implementing `TransformProtocol`
2. For batch-aware: add `BatchTransformMixin`
3. Add configuration extending `TransformConfig`
4. Register in `plugins/transforms/__init__.py`

### Adding New Telemetry Exporters

1. Create class implementing `ExporterProtocol`
2. Register in `telemetry/factory.py` BUILTIN_EXPORTERS
3. Add configuration handling
4. Test with TelemetryManager

### Adding New MCP Tools

1. Add function in `mcp/server.py`
2. Register with `@server.tool()`
3. Follow existing patterns (read-only, repository access)
4. Return JSON-serializable results

---

## Critical Invariants

### Run Invariants

1. **One run_id = one configuration**
   - Full topology hash validated on resume
   - Any change invalidates checkpoint

2. **Every token reaches terminal state**
   - COMPLETED, ROUTED, FORKED, FAILED, QUARANTINED
   - CONSUMED_IN_BATCH, COALESCED, EXPANDED

3. **Landscape before Telemetry**
   - Audit recorded FIRST
   - Telemetry emitted AFTER

### Plugin Invariants

1. **Plugins are system-owned**
   - Not user extensions
   - Bugs are system bugs

2. **Determinism must be declared**
   - Every plugin has determinism property
   - No "unknown" default

3. **node_id set by orchestrator**
   - Plugins define `node_id: str | None`
   - Orchestrator populates after registration

---

## Subsystem Ownership Guide

### High-Touch Subsystems (Careful Changes)

| Subsystem | Reason | Contact Pattern |
|-----------|--------|-----------------|
| Engine | Core execution | Full review required |
| Landscape | Audit integrity | Migration required |
| Contracts | Type surface | Breaking change review |
| DAG | Graph correctness | Validation required |

### Medium-Touch Subsystems

| Subsystem | Reason |
|-----------|--------|
| Telemetry | Operational visibility |
| Checkpoint | Recovery correctness |
| Plugin System | Discovery reliability |

### Low-Touch Subsystems

| Subsystem | Reason |
|-----------|--------|
| CLI | User interface |
| TUI | Visualization |
| MCP | Analysis tooling |
| Plugin Impls | Independent modules |

---

## Testing Requirements

### Before Merging

1. **Unit tests pass** - `pytest tests/unit/`
2. **Integration tests pass** - `pytest tests/integration/`
3. **Type check passes** - `mypy src/`
4. **Lint passes** - `ruff check src/`

### For Critical Subsystems

1. **Engine changes** - Full test suite + mutation testing
2. **Landscape changes** - Schema migration + data preservation
3. **Contracts changes** - Protocol compatibility verification

### Test Path Integrity

```python
# CORRECT - Use production factory
graph = ExecutionGraph.from_plugin_instances(
    source=source, transforms=transforms, ...
)

# WRONG - Manual construction bypasses validation
graph = ExecutionGraph()
graph.add_node(...)  # Bypasses from_plugin_instances logic
```

---

## Handover Checklist

### For New Developers

- [ ] Read CLAUDE.md completely
- [ ] Understand three-tier trust model
- [ ] Review Settings→Runtime pattern
- [ ] Run full test suite
- [ ] Explore with MCP server

### For Architecture Changes

- [ ] Document in ADR
- [ ] Review against constraints
- [ ] Update CLAUDE.md if patterns change
- [ ] Validate no legacy code introduced
- [ ] Full test suite + mutation testing

### For Release

- [ ] All P1 tasks complete
- [ ] Composite PK queries validated
- [ ] Aggregation checkpoint tested
- [ ] Documentation current
- [ ] CHANGELOG updated

---

## Contact Points

### Decision Escalation

| Decision Type | Review Required |
|---------------|-----------------|
| Schema changes | Migration + data audit |
| Trust model changes | Architecture review |
| New plugin protocols | Interface review |
| Breaking changes | Full team review |

### Documentation

| Document | Purpose |
|----------|---------|
| CLAUDE.md | Architecture guide |
| ADRs | Decision records |
| Runbooks | Operations |
| This document | Improvement planning |

---

## Summary

ELSPETH is **production-ready** with a **strong architecture**. The improvement roadmap focuses on:

1. **Immediate**: Validation and testing of critical paths
2. **Short-term**: Complexity reduction in large files
3. **Long-term**: Scalability and operational enhancements

Key success factors:
- Preserve three-tier trust model
- Maintain Settings→Runtime pattern
- Keep contracts as leaf module
- Follow no-legacy-code policy

The architecture provides a solid foundation for continued development with clear extension points and well-defined constraints.
