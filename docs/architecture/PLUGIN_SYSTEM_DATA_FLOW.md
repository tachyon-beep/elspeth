# Plugin System Architecture: Data Flow Model

**Date**: October 14, 2025
**Status**: DRAFT - Reframes Elspeth as data flow orchestrator
**Supersedes**: PLUGIN_SYSTEM_REVISED.md

---

## Core Principle

**Elspeth's core feature is pumping data between nodes.**

The orchestrator is the **engine** that defines how data flows through a graph. Plugins are **nodes** that process data at each vertex. LLM integration is just one type of processing node, not the defining characteristic.

**Separation of Concerns**:
- **Orchestrators** = Engine (defines topology: how nodes connect)
- **Nodes** = Components (defines transformations: what happens at each vertex)

Think of it like a car:
- **Engine** = Orchestrator (pumps energy through the system)
- **Wheels/Steering/Fuel Tank** = Nodes (components that do specific jobs)

---

## Mental Model

### Current (Incorrect) View
```
"Elspeth orchestrates LLM experiments"
- LLM is central, special-cased
- Experimentation is the only mode
- Data flows around the LLM
```

### Correct View
```
"Elspeth orchestrates data flow through processing nodes"
- Data flow is central
- LLM is just one type of processing node
- Experimentation is one topology pattern
- Any orchestrator can use any processing capability (LLM, transform, validation, etc.)
```

---

## Top-Level Architecture

```
src/elspeth/
├── core/
│   ├── protocols.py              # ALL plugin protocols
│   ├── orchestration/            # Orchestration framework
│   │   ├── base.py               # Orchestrator protocol
│   │   ├── graph.py              # Data flow graph abstractions
│   │   └── context.py            # Execution context
│   └── registry/
│       ├── base.py               # BasePluginRegistry
│       └── ...
│
└── plugins/
    ├── orchestrators/            # Data flow engines (topology definitions)
    │   ├── experiment/           # DAG: source → row → llm → validate → aggregate → sink
    │   ├── batch/                # Pipeline: source → llm → sink
    │   ├── streaming/            # Stream: source → buffer → llm → filter → sink
    │   └── validation/           # Pipeline: source → validate → sink
    │
    └── nodes/                    # Processing units (graph vertices)
        ├── sources/              # Data ingress (where data comes from)
        ├── sinks/                # Data egress (where results go)
        ├── transforms/           # Data transformations
        │   ├── llm/              # LLM-based transforms (just another transform type!)
        │   ├── text/             # Text processing
        │   ├── numeric/          # Numeric transforms
        │   └── structural/       # Schema validation, filtering
        ├── aggregators/          # Multi-row aggregations
        └── utilities/            # Cross-cutting helpers (retrieval, caching)
```

---

## Key Architectural Shift

### Before: LLM-Centric

```python
# Old structure treats LLM as special
plugins/
├── datasources/          # Input
├── llms/                 # ★ SPECIAL: The main thing
├── outputs/              # Output
└── experiments/          # Experiment-specific logic
```

**Problem**: This architecture says "Elspeth is for LLM experimentation." It makes LLM integration special and hard-codes experimentation as the only mode.

### After: Data Flow-Centric

```python
# New structure treats LLM as one processing node
plugins/
├── orchestrators/        # Engines (how data flows)
│   ├── experiment/       # One topology pattern
│   ├── batch/            # Another topology pattern
│   └── ...
│
└── nodes/                # Components (what processes data)
    ├── sources/          # Input nodes
    ├── sinks/            # Output nodes
    └── transforms/       # Processing nodes
        ├── llm/          # ★ LLM is just ONE transform type
        ├── text/         # Another transform type
        └── ...
```

**Solution**: This architecture says "Elspeth orchestrates data flow." Any orchestrator can use any node type. LLM is just one processing capability.

---

## 1. Orchestrators Domain

**Purpose**: Define data flow topology (the engine)

**Location**: `plugins/orchestrators/`

**Protocol**:
```python
# core/orchestration/base.py
from typing import Protocol, Any
from elspeth.core.orchestration.graph import DataFlowGraph

class Orchestrator(Protocol):
    """Base protocol for all orchestration modes.

    An orchestrator defines HOW data flows through nodes,
    not WHAT transformations are applied (that's the nodes' job).
    """

    name: str

    def build_graph(self, config: dict[str, Any]) -> DataFlowGraph:
        """Build the data flow graph from configuration.

        Returns:
            DataFlowGraph defining topology (nodes and edges)
        """
        ...

    def execute(
        self,
        graph: DataFlowGraph,
        *,
        context: OrchestrationContext,
    ) -> dict[str, Any]:
        """Execute the data flow graph and return results."""
        ...
```

### 1.1 Experiment Orchestrator (Current)

**Topology**: DAG with multiple stages

```python
# plugins/orchestrators/experiment/runner.py
class ExperimentOrchestrator:
    """Experiment orchestration mode.

    Defines a specific data flow topology:
    1. Load data from source node
    2. For each row:
       a. Apply row-level transform nodes (optional)
       b. Apply LLM transform node (if configured)
       c. Apply validation nodes (optional)
       d. Store row result
    3. Apply aggregation nodes
    4. Apply baseline comparison nodes (optional)
    5. Write to sink nodes

    This is ONE way to orchestrate data. Other orchestrators define
    different topologies for different use cases.
    """

    name = "experiment"

    def build_graph(self, config: dict[str, Any]) -> DataFlowGraph:
        graph = DataFlowGraph()

        # Stage 1: Source
        graph.add_node("source", NodeType.SOURCE, config["datasource"])

        # Stage 2: Row processing (optional transforms)
        for idx, transform_def in enumerate(config.get("row_transforms", [])):
            node_id = f"row_transform_{idx}"
            graph.add_node(node_id, NodeType.TRANSFORM, transform_def)
            graph.add_edge(f"row_transform_{idx-1}" if idx > 0 else "source", node_id)

        # Stage 3: LLM transform (if configured)
        if config.get("llm"):
            graph.add_node("llm", NodeType.TRANSFORM, config["llm"])
            graph.add_edge("row_transform_last" or "source", "llm")

        # Stage 4: Validation (optional)
        for idx, validator_def in enumerate(config.get("validators", [])):
            node_id = f"validator_{idx}"
            graph.add_node(node_id, NodeType.TRANSFORM, validator_def)
            graph.add_edge("llm", node_id)

        # Stage 5: Aggregation (optional)
        for idx, agg_def in enumerate(config.get("aggregators", [])):
            node_id = f"aggregator_{idx}"
            graph.add_node(node_id, NodeType.AGGREGATOR, agg_def)
            graph.add_edge("validator_last" or "llm", node_id)

        # Stage 6: Sinks
        for idx, sink_def in enumerate(config["sinks"]):
            node_id = f"sink_{idx}"
            graph.add_node(node_id, NodeType.SINK, sink_def)
            graph.add_edge("aggregator_last" or "validator_last" or "llm", node_id)

        return graph
```

**Key Point**: The experiment orchestrator defines a **specific topology**. It's not about "running experiments" - it's about a DAG flow pattern that happens to be useful for experimentation.

### 1.2 Batch Orchestrator (Future)

**Topology**: Simple pipeline

```python
# plugins/orchestrators/batch/runner.py
class BatchOrchestrator:
    """Batch processing orchestration mode.

    Defines a simpler topology:
    1. Load data from source
    2. Apply transform nodes in sequence (including LLM if configured)
    3. Write to sink

    No aggregation, no baselines, no early stopping.
    Just: source → transforms → sink
    """

    name = "batch"

    def build_graph(self, config: dict[str, Any]) -> DataFlowGraph:
        graph = DataFlowGraph()

        # Source
        graph.add_node("source", NodeType.SOURCE, config["datasource"])

        # Transforms (LLM is just one option)
        prev_node = "source"
        for idx, transform_def in enumerate(config["transforms"]):
            node_id = f"transform_{idx}"
            graph.add_node(node_id, NodeType.TRANSFORM, transform_def)
            graph.add_edge(prev_node, node_id)
            prev_node = node_id

        # Sink
        graph.add_node("sink", NodeType.SINK, config["sink"])
        graph.add_edge(prev_node, "sink")

        return graph
```

**Key Point**: LLM is just one transform in the pipeline. Not special. The orchestrator doesn't know or care if a transform uses LLM, regex, or machine learning - it just pumps data through.

### 1.3 Streaming Orchestrator (Future)

**Topology**: Stream processing

```python
# plugins/orchestrators/streaming/runner.py
class StreamingOrchestrator:
    """Streaming orchestration mode.

    Defines continuous data flow:
    1. Subscribe to streaming source
    2. Buffer rows
    3. Apply transform nodes (batch or individual)
    4. Filter results
    5. Write to streaming sink

    Topology: source → buffer → transforms → filter → sink
    (with feedback loops for backpressure)
    """

    name = "streaming"
    # ... implementation
```

---

## 2. Nodes Domain

**Purpose**: Processing units at each vertex (the components)

**Location**: `plugins/nodes/`

### 2.1 Sources (Data Ingress)

**Purpose**: Where data comes from

**Location**: `plugins/nodes/sources/`

**Protocol**: `DataSource` (unchanged)

```
plugins/nodes/sources/
├── __init__.py
├── registry.py
├── csv_local.py
├── csv_blob.py
├── azure_blob.py
├── postgres.py         # Future
├── kafka.py            # Future: streaming source
└── s3.py               # Future
```

**Used by**: ALL orchestrators

### 2.2 Sinks (Data Egress)

**Purpose**: Where results go

**Location**: `plugins/nodes/sinks/`

**Protocol**: `ResultSink` (unchanged)

```
plugins/nodes/sinks/
├── __init__.py
├── registry.py
├── csv_file.py
├── excel.py
├── azure_blob.py
├── signed_artifact.py
├── analytics_report.py       # Experiment-aware (checks result structure)
├── visual_report.py
├── embeddings_store.py
├── repository.py             # GitHub/Azure DevOps
├── kafka.py                  # Future: streaming sink
└── prometheus.py             # Future: telemetry
```

**Used by**: ALL orchestrators

**Note**: Some sinks are orchestrator-aware (e.g., `analytics_report` checks if results have experiment structure) but they're still universal nodes.

### 2.3 Transforms (Data Processing)

**Purpose**: Transform data at a vertex

**Location**: `plugins/nodes/transforms/`

**Protocol**:
```python
# core/protocols.py
class TransformNode(Protocol):
    """Transform data during orchestration.

    This is the base protocol for ANY data transformation,
    whether it uses LLM, regex, ML models, or simple logic.
    """

    name: str

    def transform(
        self,
        data: dict[str, Any],
        *,
        context: NodeContext,
    ) -> dict[str, Any]:
        """Transform input data and return result."""
        ...
```

#### 2.3.1 LLM Transforms

**Location**: `plugins/nodes/transforms/llm/`

**Key Point**: LLM transforms are just ONE type of transform. Not special.

```
plugins/nodes/transforms/llm/
├── __init__.py
├── registry.py
│
├── clients/                    # LLM client implementations
│   ├── azure_openai.py
│   ├── openai_http.py
│   ├── anthropic.py            # Future
│   ├── bedrock.py              # Future
│   └── mock.py
│
├── middleware/                 # LLM-specific middleware
│   ├── audit_logger.py
│   ├── prompt_shield.py
│   ├── content_safety_azure.py
│   └── health_monitor.py
│
└── controls/                   # LLM-specific controls
    ├── rate_limiter.py
    └── cost_tracker.py
```

**Example LLM Transform**:
```python
# plugins/nodes/transforms/llm/transform.py
class LLMTransform:
    """LLM-based data transformation.

    This is a TransformNode that happens to use an LLM client.
    From the orchestrator's perspective, it's just another transform.
    """

    name = "llm_transform"

    def __init__(
        self,
        client: LLMClientProtocol,
        middleware: list[LLMMiddleware],
        rate_limiter: RateLimiter | None = None,
        cost_tracker: CostTracker | None = None,
    ):
        self.client = client
        self.middleware = middleware
        self.rate_limiter = rate_limiter
        self.cost_tracker = cost_tracker

    def transform(
        self,
        data: dict[str, Any],
        *,
        context: NodeContext,
    ) -> dict[str, Any]:
        """Apply LLM transformation."""
        # Apply middleware chain
        request = self._build_request(data, context)
        for mw in self.middleware:
            request = mw.before_request(request)

        # Rate limiting
        with self.rate_limiter.acquire() if self.rate_limiter else nullcontext():
            response = self.client.generate(**request)

        # Track cost
        if self.cost_tracker:
            response = self.cost_tracker.record(response)

        # Apply middleware
        for mw in reversed(self.middleware):
            response = mw.after_response(response)

        return response
```

**Key Point**: The orchestrator calls `transform()` - it doesn't know or care that this uses an LLM. It's just data in, data out.

#### 2.3.2 Text Transforms

**Location**: `plugins/nodes/transforms/text/`

```
plugins/nodes/transforms/text/
├── __init__.py
├── registry.py
├── cleaning.py               # Normalize whitespace, case, etc.
├── tokenization.py
├── pii_redaction.py
├── translation.py            # Future
└── sentiment.py              # Future
```

#### 2.3.3 Structural Transforms

**Location**: `plugins/nodes/transforms/structural/`

```
plugins/nodes/transforms/structural/
├── __init__.py
├── registry.py
├── schema_validation.py      # Validate against JSON/Pydantic schemas
├── filtering.py              # Row filtering
├── projection.py             # Column selection
└── json_extraction.py        # Extract fields from JSON strings
```

#### 2.3.4 Numeric Transforms

**Location**: `plugins/nodes/transforms/numeric/`

```
plugins/nodes/transforms/numeric/
├── __init__.py
├── registry.py
├── normalization.py
├── scoring.py                # Extract scores from text
└── statistics.py
```

**Note**: Current `score_extractor` experiment row plugin could be refactored as a generic `scoring` transform node.

### 2.4 Aggregators (Multi-Row Processing)

**Purpose**: Compute aggregates across multiple rows

**Location**: `plugins/nodes/aggregators/`

**Protocol**:
```python
# core/protocols.py
class AggregatorNode(Protocol):
    """Aggregate data across multiple rows."""

    name: str

    def aggregate(
        self,
        records: list[dict[str, Any]],
        *,
        context: NodeContext,
    ) -> dict[str, Any]:
        """Compute aggregate and return summary."""
        ...
```

```
plugins/nodes/aggregators/
├── __init__.py
├── registry.py
├── statistics.py             # Mean, median, percentiles
├── recommendations.py        # Recommend best variant
├── ranking.py                # Rank variants by metric
├── agreement.py              # Inter-rater agreement
└── power_analysis.py         # Statistical power
```

**Used by**: Any orchestrator that needs aggregation (experiment, batch with summary, etc.)

### 2.5 Utilities (Cross-Cutting)

**Purpose**: Helpers that any node can use

**Location**: `plugins/nodes/utilities/`

```
plugins/nodes/utilities/
├── __init__.py
├── registry.py
├── retrieval.py              # Vector search for RAG
├── caching.py                # Result caching
├── tracing.py                # Distributed tracing
└── monitoring.py             # Metrics collection
```

**Used by**: Any node type (sources, sinks, transforms, aggregators)

**Example**: `retrieval` utility can be used by:
- LLM transform (enrich prompts with context)
- Text transform (fetch reference documents)
- Validation transform (compare against knowledge base)

---

## Protocol Consolidation

**File**: `core/protocols.py` (ALL protocols in one place)

```python
# core/protocols.py
"""All plugin protocols for Elspeth."""

from typing import Protocol, Any, ContextManager
import pandas as pd

# ============================================================================
# Orchestrator Protocols
# ============================================================================

class Orchestrator(Protocol):
    """Define data flow topology."""
    name: str
    def build_graph(self, config: dict[str, Any]) -> DataFlowGraph: ...
    def execute(self, graph: DataFlowGraph, **kwargs) -> dict[str, Any]: ...

# ============================================================================
# Node Protocols (Universal)
# ============================================================================

class DataSource(Protocol):
    """Source node: where data comes from."""
    def load(self) -> pd.DataFrame: ...

class ResultSink(Protocol):
    """Sink node: where results go."""
    def write(self, results: dict[str, Any], **kwargs) -> None: ...

class TransformNode(Protocol):
    """Transform node: process data at a vertex."""
    name: str
    def transform(self, data: dict[str, Any], **kwargs) -> dict[str, Any]: ...

class AggregatorNode(Protocol):
    """Aggregator node: compute multi-row aggregates."""
    name: str
    def aggregate(self, records: list[dict[str, Any]], **kwargs) -> dict[str, Any]: ...

# ============================================================================
# LLM Transform Protocols (Specific to LLM transforms)
# ============================================================================

class LLMClientProtocol(Protocol):
    """LLM client for LLM transform nodes."""
    def generate(self, *, system_prompt: str, user_prompt: str, **kwargs) -> dict[str, Any]: ...

class LLMMiddleware(Protocol):
    """Middleware for LLM transform nodes."""
    name: str
    def before_request(self, request: Any) -> Any: ...
    def after_response(self, response: Any) -> Any: ...

class RateLimiter(Protocol):
    """Rate limiting for LLM transforms."""
    def acquire(self, **kwargs) -> ContextManager[None]: ...

class CostTracker(Protocol):
    """Cost tracking for LLM transforms."""
    def record(self, response: dict[str, Any], **kwargs) -> dict[str, Any]: ...
    def summary(self) -> dict[str, Any]: ...

# ============================================================================
# Utility Protocols
# ============================================================================

class RetrievalUtility(Protocol):
    """Vector search utility."""
    def search(self, query: str, **kwargs) -> list[dict[str, Any]]: ...

class CachingUtility(Protocol):
    """Result caching utility."""
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, **kwargs) -> None: ...
```

**Note**: Experiment-specific protocols (validation, baseline comparison, early stopping) would move to `plugins/orchestrators/experiment/protocols.py` since they're topology-specific, not universal.

---

## Registry Consolidation

**Before**: 18 registry files
**After**: 7 registry files (61% reduction)

| Domain | Registry File | Purpose |
|--------|--------------|---------|
| Orchestrators | `plugins/orchestrators/registry.py` | Register orchestration modes |
| Sources | `plugins/nodes/sources/registry.py` | Data ingress nodes |
| Sinks | `plugins/nodes/sinks/registry.py` | Data egress nodes |
| Transforms | `plugins/nodes/transforms/registry.py` | Transformation nodes (includes LLM, text, numeric, structural) |
| Aggregators | `plugins/nodes/aggregators/registry.py` | Multi-row aggregation nodes |
| Utilities | `plugins/nodes/utilities/registry.py` | Cross-cutting helpers |
| Experiment (sub) | `plugins/orchestrators/experiment/registry.py` | Experiment-specific topology plugins |

**Key Change**: LLM clients, middleware, and controls are now registered in the **transforms registry** under the `llm/` subtree. They're not special - just one category of transform.

---

## Security Requirements

### Explicit Configuration Only (No Defaults)

**Principle**: Every plugin must be fully specified in configuration or it won't run.

**Rationale**:
1. **Audit Trail**: Silent defaults hide what actually ran
2. **Security**: Prevents "oops I forgot to configure security_level" issues
3. **Reproducibility**: Configuration snapshot is complete and sufficient
4. **Clarity**: Forces users to think about every setting

**Implementation**:
```python
# BAD: Silent default
def create_llm_client(options: dict[str, Any]) -> LLMClient:
    model = options.get("model", "gpt-4")  # ❌ WRONG: Silent default
    return AzureOpenAIClient(model=model)

# GOOD: Explicit required
def create_llm_client(options: dict[str, Any]) -> LLMClient:
    model = options.get("model")
    if not model:
        raise ConfigurationError("LLM client requires explicit 'model' in configuration")
    return AzureOpenAIClient(model=model)
```

**Enforcement Points**:
1. **Registry validation**: All registries validate required fields before plugin creation
2. **Schema validation**: JSONSchema marks fields as `required` (no defaults)
3. **Security level**: Always required, never defaulted (enforced in `plugin_helpers.py`)
4. **Configuration snapshot**: Saved config must be complete and runnable as-is

**Example**:
```yaml
# BAD: Incomplete configuration
orchestrator: experiment
datasource:
  plugin: csv_local
  # ❌ Missing: path, security_level

# GOOD: Complete configuration
orchestrator: experiment
datasource:
  plugin: csv_local
  path: /data/customers.csv
  security_level: internal
  encoding: utf-8
  has_header: true
```

**Benefits**:
- Configuration snapshot is self-contained
- No surprises from hidden defaults
- Audit trail shows exactly what ran
- Easier to spot misconfigurations in review

---

## Configuration Attributability

**Requirement**: All configuration for a run must be colocated in a single snapshot.

See `docs/architecture/CONFIGURATION_ATTRIBUTABILITY.md` for detailed design.

**Key Points**:
1. **Single artifact**: One `ResolvedConfiguration` object per run
2. **Complete**: Contains all settings needed to reproduce the run
3. **Provenance**: Records where each value came from (defaults, pack, experiment)
4. **Self-contained**: Can re-run from snapshot alone
5. **Audit trail**: Clear record of what actually ran

**Example**:
```json
{
  "version": "2.0",
  "orchestrator": "experiment",
  "run_id": "exp-20251014-143022",
  "resolved_config": {
    "datasource": {
      "plugin": "csv_local",
      "path": "/data/customers.csv",
      "security_level": "internal",
      "encoding": "utf-8"
    },
    "llm": {
      "plugin": "azure_openai",
      "model": "gpt-4",
      "temperature": 0.7,
      "security_level": "internal"
    },
    "sinks": [...]
  },
  "provenance": {
    "datasource.plugin": "experiment_config",
    "datasource.path": "experiment_config",
    "datasource.security_level": "experiment_config",
    "llm.temperature": "prompt_pack:baseline"
  }
}
```

---

## Comparison to Current Architecture

| Aspect | Current | Proposed |
|--------|---------|----------|
| **Mental Model** | "Elspeth orchestrates LLM experiments" | "Elspeth orchestrates data flow through nodes" |
| **LLM Status** | Special-cased domain | One transform type among many |
| **Extensibility** | Add experiment plugins | Add orchestrators OR add nodes |
| **Top-level domains** | 5 (datasources, llms, outputs, experiments, utilities) | 2 (orchestrators, nodes) |
| **Registry files** | 18 | 7 |
| **Experiment coupling** | High - experiment concepts everywhere | Low - experiment is one orchestrator |
| **Configuration defaults** | Some silent defaults exist | ❌ NO DEFAULTS - explicit configuration required |

---

## Migration Strategy

### Phase 1: Orchestration Abstraction (3-4 hours)
1. Create `core/orchestration/base.py` with `Orchestrator` protocol
2. Create `core/orchestration/graph.py` with `DataFlowGraph` abstraction
3. Move `ExperimentRunner` to `plugins/orchestrators/experiment/runner.py`
4. Implement `ExperimentOrchestrator.build_graph()` to define topology
5. Update `core/orchestrator.py` to use orchestrator plugin

### Phase 2: Node Reorganization (3-4 hours)
1. Create `plugins/nodes/` structure
2. Move datasources to `plugins/nodes/sources/`
3. Move sinks to `plugins/nodes/sinks/`
4. Create `plugins/nodes/transforms/` structure:
   - Move LLM clients/middleware/controls to `transforms/llm/`
   - Create `transforms/text/`, `transforms/numeric/`, `transforms/structural/`
   - Extract reusable transforms from experiment row plugins
5. Move aggregators to `plugins/nodes/aggregators/`
6. Move utilities to `plugins/nodes/utilities/`

### Phase 3: Protocol Consolidation (2-3 hours)
1. Create `core/protocols.py` with all universal protocols
2. Move experiment-specific protocols to `orchestrators/experiment/protocols.py`
3. Update all imports

### Phase 4: Security Hardening (2-3 hours)
1. Remove all silent defaults from plugin factories
2. Add schema `required` fields for all critical settings
3. Update validation to enforce explicit configuration
4. Add tests for missing configuration errors

### Phase 5: Documentation & Tests (2-3 hours)
1. Update plugin catalogue
2. Create orchestrator developer guide
3. Create node developer guide
4. Reorganize tests to mirror structure
5. Update architecture diagrams

**Total**: 12-17 hours

---

## Benefits of Data Flow Model

### 1. Conceptual Clarity
- **"What is Elspeth?"** → A data flow orchestrator
- **"What makes it special?"** → Pumps data between nodes with security/compliance built in
- **"Where does LLM fit?"** → One type of transform node

### 2. True Modularity
- Any orchestrator can use any node type
- LLM transforms can be used in experiment, batch, streaming, validation modes
- No special coupling between orchestration and LLM

### 3. Extensibility
- **Add orchestrator**: Define new topology (how nodes connect)
- **Add node**: Add processing capability (what happens at a vertex)
- **Mix and match**: Any orchestrator + any node combination

### 4. Security
- Explicit configuration (no silent defaults)
- Complete audit trail in config snapshot
- Clear provenance tracking
- Security levels flow through graph edges

### 5. Reduced Cognitive Load
- Two top-level concepts: orchestrators and nodes
- Clear separation: topology vs transformation
- LLM not special - reduces mental overhead

---

## Example: Adding a New Batch Orchestrator

**Use Case**: "Process 10,000 customer reviews through GPT-4, extract sentiment, write to database"

**Implementation Time**: <2 hours (because nodes are reusable)

```python
# plugins/orchestrators/batch/runner.py
class BatchOrchestrator:
    """Simple batch processing with minimal coordination."""

    name = "batch"

    def build_graph(self, config: dict[str, Any]) -> DataFlowGraph:
        graph = DataFlowGraph()

        # Source: CSV file
        graph.add_node("source", NodeType.SOURCE, {
            "plugin": "csv_local",
            "path": config["input_path"],
            "security_level": "internal"
        })

        # Transform 1: Text cleaning (reusable node)
        graph.add_node("clean", NodeType.TRANSFORM, {
            "plugin": "text_cleaning",
            "strip_whitespace": True,
            "lowercase": True
        })
        graph.add_edge("source", "clean")

        # Transform 2: LLM sentiment extraction (reusable node)
        graph.add_node("llm", NodeType.TRANSFORM, {
            "plugin": "llm_transform",
            "client": "azure_openai",
            "model": "gpt-4",
            "prompt_template": "Extract sentiment: {{text}}",
            "security_level": "internal"
        })
        graph.add_edge("clean", "llm")

        # Sink: Database
        graph.add_node("sink", NodeType.SINK, {
            "plugin": "postgres_sink",
            "table": "customer_sentiments",
            "security_level": "internal"
        })
        graph.add_edge("llm", "sink")

        return graph
```

**Key Point**:
- Reused `csv_local` source (already exists)
- Reused `text_cleaning` transform (extract from experiment row plugins)
- Reused `llm_transform` node (just configured differently)
- Reused `postgres_sink` sink (future addition)
- **Total new code**: ~50 lines to define topology

---

## Next Steps

1. **Review data flow model** - Does the engine/nodes separation make sense?
2. **Validate security requirement** - Agree on "no defaults" policy
3. **Approve migration plan** - Get stakeholder buy-in
4. **Begin Phase 1** - Implement orchestration abstraction

**Success Criteria**:
- [ ] Can add batch orchestrator in <2 hours (reusing nodes)
- [ ] LLM is just another transform (not special-cased)
- [ ] Configuration snapshot is complete and self-contained
- [ ] All 545 tests still pass
- [ ] No silent defaults anywhere in codebase
