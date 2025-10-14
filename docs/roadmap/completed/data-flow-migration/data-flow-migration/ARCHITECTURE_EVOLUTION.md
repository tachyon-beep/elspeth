# Architecture Evolution Summary

**Date**: October 14, 2025
**Status**: Design Complete - Ready for Implementation

---

## Executive Summary

This document traces the architectural evolution of Elspeth from an LLM experiment runner to a **general-purpose data flow orchestrator**. The key insight: **Elspeth's core feature is pumping data between nodes**, not running LLM experiments.

**Critical Architectural Principles**:

1. **Orchestrators define topology** (how nodes connect) - the engine
2. **Nodes define transformations** (what happens at each vertex) - the components
3. **LLM is just one node type** - not special, just another transform
4. **Explicit configuration only** - no silent defaults for security/audit
5. **Configuration attributability** - single snapshot per run

---

## Architectural Journey

### Stage 1: Current State (LLM-Centric)

**Mental Model**: "Elspeth is an LLM experiment runner"

**Problems Identified**:

- LLM special-cased as central component
- Experimentation is the only mode (tight coupling)
- 18 separate registry files (organizational debt)
- Mixed concerns (LLM clients + middleware lumped together)
- Unclear boundaries between plugin types
- Silent defaults hide security misconfigurations
- Configuration scattered across multiple files

**Structure**:

```
plugins/
├── datasources/          # Input (special)
├── llms/                 # ★ LLM (special, central)
├── outputs/              # Output (special)
├── experiments/          # Experiment-specific (coupled)
└── utilities/
```

**Registry count**: 18 files

### Stage 2: Initial Refactoring (Functional Grouping)

**Document**: `PLUGIN_SYSTEM_ANALYSIS.md`

**Key Insight**: Group by function, not by accident

**Proposed Structure**:

```
plugins/
├── data_input/           # Where data comes from
├── data_output/          # Where results go
├── llm_integration/      # How to talk to LLMs (still special)
├── experiment_lifecycle/ # Experiment-specific logic
└── utilities/
```

**Registry count**: 9 files (50% reduction)

**Limitation**: Still treats LLM as special integration

### Stage 3: Orchestration-First Design

**Document**: `PLUGIN_SYSTEM_REVISED.md`

**Key Insight**: "Elspeth is an orchestrator that can do experimentation; experimentation is ONE thing it can do"

**Proposed Structure**:

```
plugins/
├── orchestrators/        # ★ NEW: Orchestration modes
│   ├── experiment/       # Experiment is ONE mode
│   ├── batch/            # Future: batch processing
│   └── validation/       # Future: validation-only
├── data_input/           # Universal
├── data_output/          # Universal
├── llm_integration/      # ★ Still separate (universal)
├── processing/           # ★ NEW: Generic transforms
└── utilities/
```

**Registry count**: 8 files (56% reduction)

**Limitation**: LLM still has its own domain ("llm_integration")

### Stage 4: Data Flow Model (Final)

**Document**: `PLUGIN_SYSTEM_DATA_FLOW.md`

**Critical Insight**: "LLM connection is a **function** that any job should be able to do. The core feature is **pumping data between nodes**. Think engine (orchestrator) vs wheels/steering/fuel tank (nodes)."

**Final Structure**:

```
plugins/
├── orchestrators/        # Engines (define topology)
│   ├── experiment/       # One topology pattern
│   ├── batch/            # Another topology pattern
│   └── streaming/        # Future
│
└── nodes/                # Components (define transformations)
    ├── sources/          # Input nodes
    ├── sinks/            # Output nodes
    ├── transforms/       # Processing nodes
    │   ├── llm/          # ★ LLM is just ONE transform type
    │   ├── text/
    │   ├── numeric/
    │   └── structural/
    ├── aggregators/      # Multi-row processing
    └── utilities/        # Cross-cutting helpers
```

**Registry count**: 7 files (61% reduction)

**Breakthrough**: LLM is no longer special - it's just another transform node

---

## Key Architectural Insights

### Insight 1: Orchestration ≠ Experimentation

**Before**: Experimentation was the only mode, orchestration logic tightly coupled to experiment semantics

**After**: Orchestration is about **data flow topology**. Experimentation is ONE topology pattern among many.

**Impact**:

- Can add batch processing orchestrator (simple pipeline)
- Can add streaming orchestrator (continuous flow)
- Can add validation orchestrator (no LLM needed)
- Experiment becomes a special case, not the general case

### Insight 2: LLM is a Processing Node, Not the Center

**Before**: LLM was special-cased in its own domain (`plugins/llms/`)

**After**: LLM is in `plugins/nodes/transforms/llm/` - just one transform type

**Analogy**: In a car:

- **Engine** = Orchestrator (pumps energy/data through the system)
- **Wheels/Steering/Fuel Tank** = Nodes (components that do specific jobs)
- **Fuel injection** = LLM transform (one component, not the whole car)

**Impact**:

- Reduced cognitive load (LLM not special)
- Easier to reason about ("it's just a transform")
- Can compose LLM with other transforms
- Other transforms don't depend on LLM

### Insight 3: Explicit Configuration for Security

**Requirement**: "Every plugin must be fully specified each time or it won't run"

**Rationale**:

1. **Audit trail**: Silent defaults hide what actually ran
2. **Security**: Prevents forgotten `security_level` configurations
3. **Reproducibility**: Config snapshot is complete and sufficient
4. **Clarity**: Forces explicit thinking about every setting

**Implementation**:

```python
# BAD: Silent default
model = options.get("model", "gpt-4")  # ❌ Hides configuration

# GOOD: Explicit required
model = options.get("model")
if not model:
    raise ConfigurationError("'model' is required")  # ✅ Forces explicit config
```

**Impact**:

- Better security posture
- Clearer audit trails
- Self-contained configuration snapshots
- Easier to spot misconfigurations in review

### Insight 4: Configuration Attributability

**Requirement**: "All configuration for a run must be colocated for attributability"

**Problem**: Current system has configuration scattered:

- Suite defaults in `settings.yaml`
- Prompt pack in `packs/baseline.yaml`
- Experiment config in experiment definition
- Plugin defaults in factory functions

**Solution**: `ResolvedConfiguration` snapshot

- Single artifact capturing complete config
- Provenance tracking (where each value came from)
- Self-contained (can re-run from snapshot alone)

**Impact**:

- Compliance/audit requirements met
- Reproducibility guaranteed
- Clear chain of custody for settings
- Single source of truth per run

---

## Architectural Principles

### Principle 1: Separation of Concerns

**Orchestrators** (topology) and **Nodes** (transformations) are separate concerns:

- **Orchestrator's job**: Define how data flows through the graph (edges)
- **Node's job**: Transform data at a vertex (processing logic)

**Example**:

```python
# Experiment orchestrator defines topology
graph.add_edge("source", "llm_transform")
graph.add_edge("llm_transform", "validator")
graph.add_edge("validator", "sink")

# LLM transform node does the work
llm_result = llm_node.transform(data, context=ctx)
```

### Principle 2: Universal Reusability

Nodes should work in **any orchestrator**:

- `csv_local` source: works in experiment, batch, validation, streaming
- `llm_transform`: works in experiment, batch, streaming (where needed)
- `text_cleaning`: works in any orchestrator that processes text
- `statistics` aggregator: works in any orchestrator that aggregates

**Example**:

```python
# Text cleaning used in experiment
experiment_graph.add_node("clean", NodeType.TRANSFORM, {
    "plugin": "text_cleaning",
    "strip_whitespace": True
})

# Same text cleaning used in batch
batch_graph.add_node("clean", NodeType.TRANSFORM, {
    "plugin": "text_cleaning",
    "strip_whitespace": True
})
```

### Principle 3: No Special Cases

**Before**: LLM, datasources, sinks were all special-cased

**After**: Everything is a node with a clear protocol:

- Sources implement `DataSource` protocol
- Sinks implement `ResultSink` protocol
- Transforms (including LLM) implement `TransformNode` protocol
- Aggregators implement `AggregatorNode` protocol

**Impact**: Simpler mental model, easier to extend

### Principle 4: Configuration as Code (Explicit)

**No silent defaults anywhere**:

- All critical fields marked as `required` in JSONSchema
- Factory functions raise `ConfigurationError` for missing fields
- Configuration snapshot is complete and runnable as-is

**Impact**: Security, auditability, reproducibility

---

## Registry Consolidation Journey

### Before: 18 Registries (Fragmented)

```
src/elspeth/
├── core/
│   ├── registry.py                           # 1. Main datasource/llm/sink registry
│   ├── datasource_registry.py                # 2. Datasource registry
│   ├── llm_registry.py                       # 3. LLM registry
│   ├── sink_registry.py                      # 4. Sink registry
│   ├── controls/
│   │   ├── registry.py                       # 5. Controls registry
│   │   ├── cost_tracker_registry.py          # 6. Cost tracker registry
│   │   └── rate_limiter_registry.py          # 7. Rate limiter registry
│   └── experiments/
│       ├── plugin_registry.py                # 8. Experiment plugin registry
│       ├── row_plugin_registry.py            # 9. Row plugin registry
│       ├── aggregation_plugin_registry.py    # 10. Aggregation plugin registry
│       ├── validation_plugin_registry.py     # 11. Validation plugin registry
│       ├── baseline_plugin_registry.py       # 12. Baseline plugin registry
│       └── early_stop_plugin_registry.py     # 13. Early stop plugin registry
│
└── plugins/
    ├── llms/
    │   └── middleware/
    │       └── registry.py                   # 14. LLM middleware registry
    └── utilities/
        └── registry.py                       # 15. Utilities registry
```

**Plus 3 more**: Configuration-specific registries

**Total**: 18 registry files

### After: 7 Registries (Consolidated)

```
src/elspeth/plugins/
├── orchestrators/
│   └── registry.py                           # 1. Orchestrator registry
│
└── nodes/
    ├── sources/
    │   └── registry.py                       # 2. Source node registry
    ├── sinks/
    │   └── registry.py                       # 3. Sink node registry
    ├── transforms/
    │   └── registry.py                       # 4. Transform node registry
    │       └── llm/                          #    (includes LLM clients, middleware, controls)
    ├── aggregators/
    │   └── registry.py                       # 5. Aggregator node registry
    ├── utilities/
    │   └── registry.py                       # 6. Utility node registry
    └── orchestrators/experiment/
        └── registry.py                       # 7. Experiment-specific registry
```

**Reduction**: 18 → 7 (61% reduction)

**Benefits**:

- Easier to find plugins (clear domain organization)
- Less cognitive overhead (fewer registry locations)
- Clearer boundaries (orchestrator-specific vs universal)

---

## Migration Path

See `MIGRATION_TO_DATA_FLOW.md` for detailed migration steps.

**Summary**:

1. **Phase 1**: Add orchestration abstraction (3-4h)
2. **Phase 2**: Reorganize nodes (3-4h)
3. **Phase 3**: Enforce explicit config (2-3h)
4. **Phase 4**: Consolidate protocols (2-3h)
5. **Phase 5**: Update docs/tests (2-3h)

**Total**: 12-17 hours

**Safety**: Backward compatibility shims, all 545 tests must pass

---

## Success Criteria

### Functional Criteria

- [ ] All 545 tests pass
- [ ] Mypy: 0 errors
- [ ] Ruff: passing
- [ ] Sample suite runs: `make sample-suite` succeeds

### Architectural Criteria

- [ ] Can add batch orchestrator in <2 hours
- [ ] LLM is in `plugins/nodes/transforms/llm/` (not special-cased)
- [ ] Registry count: 7 files (down from 18)
- [ ] No silent defaults in any plugin factory
- [ ] Configuration snapshot is complete and self-contained

### Documentation Criteria

- [ ] Plugin catalogue updated
- [ ] Orchestrator development guide created
- [ ] Node development guide created
- [ ] Architecture diagrams show data flow model
- [ ] All tests reorganized to mirror structure

### Security Criteria

- [ ] All schemas mark critical fields as `required`
- [ ] All factory functions validate required fields
- [ ] P0 security regression tests added
- [ ] Configuration attributability implemented

---

## Comparison Table

| Aspect | Current | Stage 2 (Functional) | Stage 3 (Orchestration) | Stage 4 (Data Flow) |
|--------|---------|---------------------|------------------------|---------------------|
| **Mental Model** | "LLM experiment runner" | "Functional plugin system" | "Orchestrator with modes" | "Data flow engine" |
| **LLM Status** | Special domain | Still special | Still special | Just another node |
| **Top Domains** | 5 (mixed) | 5 (functional) | 6 (orchestrator added) | 2 (orchestrators + nodes) |
| **Registry Files** | 18 | 9 | 8 | 7 |
| **Extensibility** | Add experiment plugins | Add to domains | Add orchestrators | Add orchestrators OR nodes |
| **Configuration** | Some defaults | Some defaults | Some defaults | ❌ NO DEFAULTS |
| **Attributability** | Scattered | Scattered | Scattered | ✅ Single snapshot |

---

## Conceptual Breakthroughs

### 1. The Car Analogy

**Elspeth is a car**:

- **Engine** = Orchestrator (pumps data through the system)
- **Wheels** = Source/Sink nodes (I/O)
- **Steering** = Transform nodes (data processing)
- **Fuel Tank** = LLM transform (just fuel, not the whole car)

**Key Point**: The engine doesn't care what fuel you use (LLM, regex, ML). It just pumps data through the system.

### 2. Graph Topology vs Vertex Transformations

**Orchestrator** = Graph topology (edges: how data flows)
**Nodes** = Vertex transformations (what happens at each point)

**Example**:

```
Experiment topology:
source → row_transforms → llm → validators → aggregators → sinks

Batch topology:
source → transforms → sink

Streaming topology:
source → buffer → transforms → filter → sink
(with feedback loop for backpressure)
```

**Key Point**: Different orchestrators = different topology patterns. Same nodes can be reused across patterns.

### 3. Explicit > Implicit (Security)

**Silent defaults are security vulnerabilities**:

- Hide what actually ran (audit trail gap)
- Allow forgotten configurations (security_level omission)
- Prevent reproducibility (incomplete config)

**Solution**: Fail fast with explicit errors

- Forces user to think about every setting
- Makes audit trail complete
- Enables true reproducibility

---

## Next Steps

1. **Review**: Stakeholder sign-off on data flow model
2. **Implement**: Follow migration guide (12-17 hours)
3. **Verify**: All success criteria met
4. **Document**: Update all architectural docs
5. **Communicate**: Update developer onboarding

---

## References

- **Current Analysis**: `PLUGIN_SYSTEM_ANALYSIS.md`
- **Orchestration Model**: `PLUGIN_SYSTEM_REVISED.md`
- **Data Flow Model**: `PLUGIN_SYSTEM_DATA_FLOW.md` ← **Target Architecture**
- **Migration Guide**: `MIGRATION_TO_DATA_FLOW.md`
- **Configuration Design**: `CONFIGURATION_ATTRIBUTABILITY.md`

---

## Conclusion

**Elspeth's essence**: A secure, auditable **data flow orchestrator** where:

- **Orchestrators** define how data flows (topology/engine)
- **Nodes** define what happens to data (transformations/components)
- **LLM** is just one node type among many (not special)
- **Configuration** is explicit, complete, and attributable (no defaults)

This architecture enables:

- Multiple orchestration modes (experiment, batch, streaming, validation)
- Universal node reusability (same nodes across modes)
- Clear separation of concerns (topology vs transformation)
- Security by design (explicit config, complete audit trail)
- True modularity (mix and match orchestrators + nodes)

**The paradigm shift**: From "Elspeth runs LLM experiments" to "Elspeth orchestrates data flow through processing nodes (LLM being one option)."
