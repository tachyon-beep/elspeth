# Architectural Principles & Decisions

**Core principles and design decisions for the data flow architecture**

---

## The Core Insight

> **"The core feature is pumping data between nodes. LLM is just one of those nodes."**

This is the fundamental shift: Elspeth is NOT an "LLM experiment runner." It is a **data flow orchestrator** where LLM happens to be one processing capability among many.

---

## The Car Analogy

**Elspeth is like a car**:

- **Engine** = Orchestrator (pumps data through the system)
- **Wheels** = Source/Sink nodes (I/O)
- **Steering** = Transform nodes (processing)
- **Fuel Tank** = LLM transform (just fuel, not the whole car)

**Key Point**: The engine doesn't care what fuel you use (LLM, regex, ML, manual). It just pumps data through the system.

---

## Four Architectural Stages

### Stage 1: Current (LLM-Centric)

**Mental Model**: "Elspeth is an LLM experiment runner"

- LLM special-cased as central component
- Experimentation is the only mode
- 18 separate registry files
- Mixed concerns

### Stage 2: Functional Grouping

**Mental Model**: "Organize by function"

- Group by: data_input, data_output, llm_integration, experiment_lifecycle
- Registry consolidation: 18 → 9
- LLM still special

### Stage 3: Orchestration-First

**Mental Model**: "Elspeth is an orchestrator with modes"

- Orchestrators as first-class concept
- Experimentation is ONE mode
- LLM still in separate domain
- Registry consolidation: 18 → 8

### Stage 4: Data Flow Model (TARGET)

**Mental Model**: "Elspeth orchestrates data flow through nodes"

- **Orchestrators** = Engines (define topology)
- **Nodes** = Components (define transformations)
- LLM is just another transform node
- Registry consolidation: 18 → 7
- **THIS IS THE TARGET**

---

## Key Architectural Principles

### 1. Separation of Concerns: Topology vs Transformation

**Orchestrators define topology** (how data flows):

- Experiment orchestrator: DAG pattern (source → row → llm → validate → aggregate → sinks)
- Batch orchestrator: Pipeline pattern (source → transforms → sink)
- Streaming orchestrator: Stream pattern (source → buffer → transforms → filter → sink)

**Nodes define transformations** (what happens at vertices):

- Sources: Load data (CSV, blob, database, stream)
- Transforms: Process data (LLM, text cleaning, validation, filtering)
- Aggregators: Compute aggregates (statistics, ranking, recommendations)
- Sinks: Persist results (CSV, Excel, blob, database)

**Why**: This separation allows:

- Same nodes work in different orchestrators
- New orchestrators can reuse existing nodes
- Easier to reason about: "what flows where" vs "what transforms how"

### 2. LLM is Not Special

**Before**: `plugins/llms/` (special domain)
**After**: `plugins/nodes/transforms/llm/` (just one transform type)

**Why**:

- Reduces cognitive load (LLM not special)
- Enables non-LLM orchestrators (validation-only, text processing)
- Makes it clear: LLM is optional, not central
- Easier composition (LLM + text cleaning + validation)

**Example**: A batch orchestrator might use:

- Text cleaning transform (no LLM)
- Schema validation transform (no LLM)
- LLM sentiment extraction transform (uses LLM)
- All are equal: just transforms in the pipeline

### 3. Explicit Configuration Only (Security)

**Principle**: "Every plugin must be fully specified each time or it won't run"

**Why**:

1. **Audit Trail**: Silent defaults hide what actually ran
2. **Security**: Prevents forgotten security_level configurations
3. **Reproducibility**: Config snapshot is complete and sufficient
4. **Clarity**: Forces explicit thinking about every setting

**Implementation**:

- NO `.get(key, default)` with defaults in factory functions
- All critical fields marked `required` in JSONSchema
- Factory functions raise `ConfigurationError` for missing fields
- Configuration snapshot must be runnable as-is

**Example**:

```python
# BAD
model = options.get("model", "gpt-4")  # Silent default hides configuration

# GOOD
model = options.get("model")
if not model:
    raise ConfigurationError("'model' is required")
```

### 4. Configuration Attributability

**Principle**: "All configuration for a run must be colocated for attributability"

**Why**:

- **Compliance**: Audit requires single source of truth
- **Reproducibility**: Can re-run from snapshot alone
- **Debugging**: Know exactly what ran
- **Provenance**: Track where each value came from

**Implementation**:

- `ResolvedConfiguration` dataclass captures complete config
- Provenance dict tracks source of each value (defaults, pack, experiment)
- Config snapshot saved as artifact
- Can run: `elspeth --from-snapshot run-20251014.json`

**Example**:

```json
{
  "version": "2.0",
  "run_id": "exp-20251014",
  "resolved_config": {
    "datasource": {"plugin": "csv_local", "path": "/data/test.csv", ...},
    "llm": {"plugin": "azure_openai", "model": "gpt-4", ...}
  },
  "provenance": {
    "datasource.plugin": "experiment_config",
    "llm.model": "prompt_pack:baseline",
    "llm.temperature": "suite_defaults"
  }
}
```

### 5. Universal Reusability

**Principle**: Nodes should work in ANY orchestrator

**Why**:

- Reduces duplication
- Enables composition
- Easier testing (test once, use everywhere)
- Future-proof (new orchestrators can reuse existing nodes)

**Examples**:

- `csv_local` source: works in experiment, batch, validation, streaming
- `text_cleaning` transform: works in any orchestrator that processes text
- `statistics` aggregator: works in any orchestrator that aggregates
- `llm_transform`: works in experiment, batch, streaming (where LLM is needed)

### 6. No Special Cases

**Principle**: Everything is a node with a clear protocol

**Before**: Datasources, LLMs, sinks were all special-cased
**After**: All follow node protocols

**Why**:

- Simpler mental model (fewer concepts)
- Easier to extend (implement protocol, register, done)
- Consistent behavior (all nodes behave the same way)
- Better composition (nodes compose naturally)

**Protocols**:

```python
class DataSource(Protocol):
    """Source node protocol."""
    def load(self) -> pd.DataFrame: ...

class TransformNode(Protocol):
    """Transform node protocol (LLM is one implementation)."""
    name: str
    def transform(self, data: dict[str, Any], **kwargs) -> dict[str, Any]: ...

class AggregatorNode(Protocol):
    """Aggregator node protocol."""
    name: str
    def aggregate(self, records: list[dict[str, Any]], **kwargs) -> dict[str, Any]: ...

class ResultSink(Protocol):
    """Sink node protocol."""
    def write(self, results: dict[str, Any], **kwargs) -> None: ...
```

---

## Design Decisions & Rationale

### Decision 1: Move LLM to nodes/transforms/llm/

**Rationale**:

- LLM is just one type of transform
- No reason to special-case it
- Makes Elspeth useful for non-LLM workflows
- Reduces coupling to LLM concept

**Alternatives Considered**:

- Keep LLM in separate domain → Rejected (perpetuates LLM-centric view)
- Move to llm_integration → Rejected (still special-cases LLM)

### Decision 2: Orchestrators as Plugins

**Rationale**:

- Experimentation is ONE orchestration mode, not THE mode
- Other modes (batch, streaming, validation) are equally valid
- Makes extensibility clear: add orchestrator OR add node
- Aligns with roadmap (batch processing, streaming)

**Alternatives Considered**:

- Hard-code experiment orchestrator → Rejected (limits extensibility)
- Make orchestrator config-driven only → Rejected (complex, hard to reason about)

### Decision 3: 7 Registries (not fewer)

**Rationale**:

- Each registry has clear domain responsibility
- 7 is manageable (down from 18)
- Further consolidation would mix concerns

**Registry breakdown**:

1. Orchestrators (orchestration modes)
2. Sources (data ingress)
3. Sinks (data egress)
4. Transforms (processing nodes, including LLM)
5. Aggregators (multi-row processing)
6. Utilities (cross-cutting)
7. Experiment (experiment-specific topology plugins)

**Alternatives Considered**:

- 5 registries (merge transforms + aggregators) → Rejected (different protocols)
- 10+ registries (split transforms by type) → Rejected (too granular)

### Decision 4: Backward Compatibility Shims

**Rationale**:

- External code depends on current import paths
- Breaking changes are costly
- Shims allow gradual migration
- Deprecation can happen later

**Implementation**:

- Old import paths still work (re-export from new locations)
- Optional: Add deprecation warnings
- Timeline: Remove shims in v3.0 (future)

**Alternatives Considered**:

- Breaking changes → Rejected (too risky)
- Feature flags for gradual rollout → Optional (recommended but not required)

### Decision 5: Explicit Config Enforcement

**Rationale**:

- User requirement: "always run from config"
- Security: Prevents forgotten security_level
- Audit: Config snapshot shows exactly what ran
- Clarity: Forces explicit thinking

**Implementation**:

- Remove all silent defaults
- Mark critical fields as `required` in schemas
- Raise ConfigurationError for missing fields

**Alternatives Considered**:

- Keep some defaults for convenience → Rejected (security risk)
- Make defaults opt-in per plugin → Rejected (inconsistent behavior)

---

## Success Criteria

### Architectural Goals

- [ ] Can add batch orchestrator in <2 hours (proof of extensibility)
- [ ] LLM is in `plugins/nodes/transforms/llm/` (not special)
- [ ] Registry count: 7 files (down from 18)
- [ ] All nodes reusable across orchestrators

### Security Goals

- [ ] Zero silent defaults anywhere
- [ ] All critical fields marked `required`
- [ ] Configuration snapshot is complete
- [ ] Audit trail is clear

### Quality Goals

- [ ] All 545+ tests pass
- [ ] Mypy: 0 errors
- [ ] Ruff: passing
- [ ] Sample suite runs
- [ ] Coverage >85%

### Extensibility Goals

- [ ] Adding new orchestrator is straightforward
- [ ] Adding new node follows clear pattern
- [ ] Nodes compose naturally
- [ ] No special cases or magic

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Special-Casing LLM

**Problem**: Treating LLM differently from other transforms
**Why Bad**: Couples architecture to LLM concept, limits extensibility
**Solution**: LLM is just another transform node

### Anti-Pattern 2: Silent Defaults

**Problem**: Using `.get(key, default)` in factory functions
**Why Bad**: Hides configuration, security risk, breaks audit trail
**Solution**: Always raise ConfigurationError for missing required fields

### Anti-Pattern 3: Mixing Topology and Transformation

**Problem**: Orchestrator implements transformation logic
**Why Bad**: Can't reuse transformations, hard to test, tight coupling
**Solution**: Orchestrator defines graph, nodes do transformations

### Anti-Pattern 4: Breaking Backward Compatibility

**Problem**: Moving files without shims
**Why Bad**: Breaks external code, costly rollback
**Solution**: Always provide backward compatibility shims

### Anti-Pattern 5: Incomplete Config Snapshots

**Problem**: Config snapshot missing values (relies on defaults)
**Why Bad**: Can't reproduce, audit trail incomplete
**Solution**: Snapshot must be complete and runnable as-is

---

## Key Quotes from User

1. **On orchestration**: "this is an orchestrator that can do experimentation, experimentation is just one thing it can do"

2. **On LLM**: "llm connection is a **function** that any job should be able to do... the core feature is **pumping data between nodes**, the LLM can be one of those nodes"

3. **On configuration**: "all the configuration for a particular orchestration run has to be colocated for attributability"

4. **On security**: "every plugin must be fully specified each time or it won't run"

5. **On the engine analogy**: "think of separating the engine from the wheels and steering wheel and fuel tank"

---

## Remember

1. **Data flow is central, not LLM** - This is the core insight
2. **Orchestrators define how, nodes define what** - Clear separation
3. **No silent defaults, ever** - Security and audit requirement
4. **Backward compatibility is essential** - External code depends on us
5. **Each phase must work** - No half-migrated states

**The paradigm shift**: From "Elspeth runs LLM experiments" to "Elspeth orchestrates data flow through processing nodes (LLM being one option)."
