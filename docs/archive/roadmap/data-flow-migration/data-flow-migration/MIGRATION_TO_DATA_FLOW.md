# Migration Guide: Current Architecture → Data Flow Model

**Date**: October 14, 2025
**Target**: PLUGIN_SYSTEM_DATA_FLOW.md architecture
**Estimated Time**: 12-17 hours

---

## Overview

This guide walks through migrating Elspeth from its current LLM-centric architecture to the data flow model where orchestrators define topology and nodes provide transformations.

**Key Changes**:
1. Reframe mental model from "LLM experiments" to "data flow orchestration"
2. Move LLM from special domain to transform node
3. Separate orchestration (topology) from processing (nodes)
4. Enforce explicit configuration (remove silent defaults)
5. Consolidate 18 registries → 7 registries

---

## Before & After Comparison

### Current Structure
```
src/elspeth/plugins/
├── datasources/              # Input (special)
│   ├── csv_local.py
│   ├── csv_blob.py
│   └── blob.py
│
├── llms/                     # ★ LLM (special, central)
│   ├── azure_openai.py
│   ├── openai_http.py
│   ├── middleware.py
│   ├── middleware_azure.py
│   ├── mock.py
│   └── static.py
│
├── outputs/                  # Output (special)
│   ├── csv_file.py
│   ├── excel.py
│   ├── analytics_report.py
│   └── ...
│
├── experiments/              # Experiment plugins (coupled)
│   ├── metrics.py            # Row, aggregation, baseline all mixed
│   ├── validation.py
│   ├── early_stop.py
│   ├── rag_query.py
│   └── prompt_variants.py
│
└── utilities/
    └── retrieval.py

# Registry files: 18 separate files
```

### Target Structure
```
src/elspeth/plugins/
├── orchestrators/            # ★ NEW: Data flow engines
│   ├── registry.py
│   └── experiment/           # Experiment is ONE orchestrator
│       ├── runner.py
│       ├── protocols.py      # Experiment-specific protocols
│       └── registry.py       # Experiment-specific nodes
│
└── nodes/                    # ★ NEW: Processing units
    ├── sources/              # Data ingress
    │   ├── registry.py
    │   ├── csv_local.py
    │   ├── csv_blob.py
    │   └── azure_blob.py
    │
    ├── sinks/                # Data egress
    │   ├── registry.py
    │   ├── csv_file.py
    │   ├── excel.py
    │   └── analytics_report.py
    │
    ├── transforms/           # Processing nodes
    │   ├── registry.py
    │   ├── llm/              # ★ LLM is just ONE transform type
    │   │   ├── clients/
    │   │   │   ├── azure_openai.py
    │   │   │   ├── openai_http.py
    │   │   │   └── mock.py
    │   │   ├── middleware/
    │   │   │   ├── audit_logger.py
    │   │   │   └── prompt_shield.py
    │   │   └── controls/
    │   │       ├── rate_limiter.py
    │   │       └── cost_tracker.py
    │   ├── text/
    │   │   ├── cleaning.py
    │   │   └── pii_redaction.py
    │   ├── numeric/
    │   │   └── scoring.py    # Extract from metrics.py
    │   └── structural/
    │       ├── schema_validation.py
    │       └── filtering.py
    │
    ├── aggregators/          # Multi-row processing
    │   ├── registry.py
    │   ├── statistics.py     # Extract from metrics.py
    │   ├── recommendations.py
    │   └── ranking.py
    │
    └── utilities/            # Cross-cutting helpers
        ├── registry.py
        ├── retrieval.py
        └── caching.py

# Registry files: 7 files (61% reduction)
```

---

## Phase 1: Orchestration Abstraction (3-4 hours)

### Step 1.1: Create Orchestration Framework

**Create**: `src/elspeth/core/orchestration/base.py`

```python
"""Base orchestration framework."""

from __future__ import annotations

from typing import Protocol, Any

class DataFlowGraph:
    """Represents a data flow graph (nodes and edges)."""

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[tuple[str, str]] = []

    def add_node(
        self,
        node_id: str,
        node_type: NodeType,
        config: dict[str, Any],
    ) -> None:
        """Add a node to the graph."""
        self.nodes[node_id] = GraphNode(
            id=node_id,
            type=node_type,
            config=config,
        )

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add an edge between nodes."""
        self.edges.append((from_node, to_node))

    def topological_sort(self) -> list[str]:
        """Return nodes in topological order."""
        # ... implementation


class Orchestrator(Protocol):
    """Base protocol for all orchestration modes."""

    name: str

    def build_graph(self, config: dict[str, Any]) -> DataFlowGraph:
        """Build data flow graph from configuration."""
        ...

    def execute(
        self,
        graph: DataFlowGraph,
        *,
        context: OrchestrationContext,
    ) -> dict[str, Any]:
        """Execute the data flow graph."""
        ...
```

### Step 1.2: Create Experiment Orchestrator

**Create**: `src/elspeth/plugins/orchestrators/experiment/runner.py`

**Strategy**: Move current `ExperimentRunner` logic but wrap it with orchestrator interface

```python
"""Experiment orchestration mode."""

from __future__ import annotations

from typing import Any
from elspeth.core.orchestration.base import Orchestrator, DataFlowGraph

class ExperimentOrchestrator:
    """Experiment orchestration mode.

    Defines a specific data flow topology optimized for A/B testing
    and comparative analysis.

    Topology:
        source → [row_transforms] → [llm_transform] → [validators]
        → [aggregators] → [baselines] → sinks
    """

    name = "experiment"

    def __init__(self) -> None:
        # Keep most of current ExperimentRunner logic here
        pass

    def build_graph(self, config: dict[str, Any]) -> DataFlowGraph:
        """Build experiment data flow graph."""
        graph = DataFlowGraph()

        # Map current experiment config to graph nodes
        # This is mostly a refactoring of existing logic

        return graph

    def execute(
        self,
        graph: DataFlowGraph,
        *,
        context: OrchestrationContext,
    ) -> dict[str, Any]:
        """Execute experiment graph."""
        # Delegate to current ExperimentRunner.run() logic
        # Most of the existing code can stay the same
        pass
```

**Files to modify**:
- Move `src/elspeth/core/experiments/runner.py` → `src/elspeth/plugins/orchestrators/experiment/runner.py`
- Keep logic mostly the same, just wrap with orchestrator interface
- Update imports in `suite_runner.py`

### Step 1.3: Register Experiment Orchestrator

**Create**: `src/elspeth/plugins/orchestrators/registry.py`

```python
"""Orchestrator registry."""

from elspeth.core.registry import BasePluginRegistry
from elspeth.plugins.orchestrators.experiment.runner import ExperimentOrchestrator

# Create orchestrator registry
orchestrator_registry = BasePluginRegistry[Orchestrator]("orchestrator")

# Register experiment orchestrator
orchestrator_registry.register(
    "experiment",
    factory=lambda opts, ctx: ExperimentOrchestrator(),
    schema={
        "type": "object",
        "properties": {},  # No additional config needed
    },
)

__all__ = ["orchestrator_registry"]
```

### Step 1.4: Update Main Orchestrator

**Modify**: `src/elspeth/core/orchestrator.py`

```python
# Add at top
from elspeth.plugins.orchestrators.registry import orchestrator_registry

class ExperimentOrchestrator:  # This is the OLD top-level orchestrator
    """Top-level orchestrator (delegates to orchestrator plugins)."""

    def run_experiment(self, config: ExperimentConfig) -> dict[str, Any]:
        # NEW: Get orchestrator from registry
        orchestrator_type = config.orchestrator or "experiment"
        orchestrator = orchestrator_registry.create(
            orchestrator_type,
            options={},
            parent_context=self.context,
        )

        # Build graph and execute
        graph = orchestrator.build_graph(config.to_dict())
        return orchestrator.execute(graph, context=self.context)
```

**Backward Compatibility**:
- Keep old class name `ExperimentOrchestrator` in `orchestrator.py`
- It now delegates to orchestrator plugins
- Existing code still works

---

## Phase 2: Node Reorganization (3-4 hours)

### Step 2.1: Create Node Structure

**Create directories**:
```bash
mkdir -p src/elspeth/plugins/nodes/{sources,sinks,transforms,aggregators,utilities}
mkdir -p src/elspeth/plugins/nodes/transforms/{llm,text,numeric,structural}
mkdir -p src/elspeth/plugins/nodes/transforms/llm/{clients,middleware,controls}
```

### Step 2.2: Move Sources

**Move files**:
```bash
# Move datasource files
mv src/elspeth/plugins/datasources/csv_local.py \
   src/elspeth/plugins/nodes/sources/csv_local.py

mv src/elspeth/plugins/datasources/csv_blob.py \
   src/elspeth/plugins/nodes/sources/csv_blob.py

mv src/elspeth/plugins/datasources/blob.py \
   src/elspeth/plugins/nodes/sources/azure_blob.py
```

**Create**: `src/elspeth/plugins/nodes/sources/registry.py`

```python
"""Source node registry."""

from elspeth.core.registry import BasePluginRegistry
from elspeth.core.interfaces import DataSource

# Import source implementations
from .csv_local import create_csv_local_datasource
from .csv_blob import create_csv_blob_datasource
from .azure_blob import create_azure_blob_datasource

# Create sources registry
source_registry = BasePluginRegistry[DataSource]("source")

# Register sources (use existing factory functions and schemas)
source_registry.register("csv_local", create_csv_local_datasource, CSV_LOCAL_SCHEMA)
source_registry.register("csv_blob", create_csv_blob_datasource, CSV_BLOB_SCHEMA)
source_registry.register("azure_blob", create_azure_blob_datasource, AZURE_BLOB_SCHEMA)

__all__ = ["source_registry"]
```

**Backward compatibility shim**: Keep old datasource registry working

```python
# src/elspeth/core/registries/datasource.py (keep existing file)
from elspeth.plugins.nodes.sources.registry import source_registry

# Re-export under old name for backward compatibility
datasource_registry = source_registry

__all__ = ["datasource_registry"]
```

### Step 2.3: Move Sinks

**Move files**:
```bash
# Move output files
mv src/elspeth/plugins/outputs/* \
   src/elspeth/plugins/nodes/sinks/
```

**Create**: `src/elspeth/plugins/nodes/sinks/registry.py`

```python
"""Sink node registry."""

from elspeth.core.registry import BasePluginRegistry
from elspeth.core.interfaces import ResultSink

# Import sink implementations (from existing files)
from .csv_file import create_csv_file_sink
from .excel import create_excel_sink
# ... etc

# Create sinks registry
sink_registry = BasePluginRegistry[ResultSink]("sink")

# Register sinks
sink_registry.register("csv_file", create_csv_file_sink, CSV_FILE_SCHEMA)
sink_registry.register("excel", create_excel_sink, EXCEL_SCHEMA)
# ... etc

__all__ = ["sink_registry"]
```

**Backward compatibility shim**:

```python
# src/elspeth/core/registries/sink.py (keep existing file)
from elspeth.plugins.nodes.sinks.registry import sink_registry

__all__ = ["sink_registry"]
```

### Step 2.4: Move LLM to Transform Nodes

**Move files**:
```bash
# Move LLM clients
mv src/elspeth/plugins/llms/azure_openai.py \
   src/elspeth/plugins/nodes/transforms/llm/clients/azure_openai.py

mv src/elspeth/plugins/llms/openai_http.py \
   src/elspeth/plugins/nodes/transforms/llm/clients/openai_http.py

mv src/elspeth/plugins/llms/mock.py \
   src/elspeth/plugins/nodes/transforms/llm/clients/mock.py

mv src/elspeth/plugins/llms/static.py \
   src/elspeth/plugins/nodes/transforms/llm/clients/static.py

# Move middleware
mv src/elspeth/plugins/llms/middleware.py \
   src/elspeth/plugins/nodes/transforms/llm/middleware/audit_logger.py

mv src/elspeth/plugins/llms/middleware_azure.py \
   src/elspeth/plugins/nodes/transforms/llm/middleware/content_safety_azure.py

# Move controls
mv src/elspeth/core/controls/rate_limit.py \
   src/elspeth/plugins/nodes/transforms/llm/controls/rate_limiter.py

mv src/elspeth/core/controls/cost_tracker.py \
   src/elspeth/plugins/nodes/transforms/llm/controls/cost_tracker.py
```

**Create**: `src/elspeth/plugins/nodes/transforms/llm/registry.py`

```python
"""LLM transform node registry.

LLM transforms are ONE type of transform node.
They're not special - just another way to process data.
"""

from elspeth.core.registry import BasePluginRegistry
from elspeth.core.interfaces import TransformNode

# Import LLM implementations
from .clients.azure_openai import create_azure_openai_client
from .clients.openai_http import create_openai_http_client
from .clients.mock import create_mock_client
from .middleware.audit_logger import create_audit_logger_middleware
from .controls.rate_limiter import create_noop_rate_limiter, create_sliding_window_limiter
from .controls.cost_tracker import create_noop_cost_tracker, create_standard_cost_tracker

# LLM client registry
llm_client_registry = BasePluginRegistry[LLMClientProtocol]("llm_client")
llm_client_registry.register("azure_openai", create_azure_openai_client, AZURE_OPENAI_SCHEMA)
llm_client_registry.register("openai_http", create_openai_http_client, OPENAI_HTTP_SCHEMA)
llm_client_registry.register("mock", create_mock_client, MOCK_SCHEMA)

# LLM middleware registry
llm_middleware_registry = BasePluginRegistry[LLMMiddleware]("llm_middleware")
llm_middleware_registry.register("audit_logger", create_audit_logger_middleware, AUDIT_LOGGER_SCHEMA)
# ... etc

# LLM controls registries
rate_limiter_registry = BasePluginRegistry[RateLimiter]("rate_limiter")
rate_limiter_registry.register("noop", create_noop_rate_limiter, NOOP_SCHEMA)
rate_limiter_registry.register("sliding_window", create_sliding_window_limiter, SLIDING_WINDOW_SCHEMA)

cost_tracker_registry = BasePluginRegistry[CostTracker]("cost_tracker")
cost_tracker_registry.register("noop", create_noop_cost_tracker, NOOP_SCHEMA)
cost_tracker_registry.register("standard", create_standard_cost_tracker, STANDARD_SCHEMA)

__all__ = [
    "llm_client_registry",
    "llm_middleware_registry",
    "rate_limiter_registry",
    "cost_tracker_registry",
]
```

**Backward compatibility shim**:

```python
# src/elspeth/core/registries/llm.py (NEW - backward compat)
"""Backward compatibility shim for LLM registries."""

from elspeth.plugins.nodes.transforms.llm.registry import (
    llm_client_registry,
    llm_middleware_registry,
    rate_limiter_registry,
    cost_tracker_registry,
)

__all__ = [
    "llm_client_registry",
    "llm_middleware_registry",
    "rate_limiter_registry",
    "cost_tracker_registry",
]
```

### Step 2.5: Extract Text/Numeric Transforms

**Create**: `src/elspeth/plugins/nodes/transforms/text/cleaning.py`

```python
"""Text cleaning transform node."""

from __future__ import annotations
from typing import Any

def create_text_cleaning_transform(
    options: dict[str, Any],
    context: PluginContext,
) -> TextCleaningTransform:
    """Create text cleaning transform."""
    return TextCleaningTransform(
        strip_whitespace=options.get("strip_whitespace", True),
        lowercase=options.get("lowercase", False),
        remove_punctuation=options.get("remove_punctuation", False),
        context=context,
    )

class TextCleaningTransform:
    """Clean and normalize text."""

    name = "text_cleaning"

    def transform(self, data: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Apply text cleaning transformations."""
        text = data.get("text", "")

        if self.strip_whitespace:
            text = text.strip()

        if self.lowercase:
            text = text.lower()

        if self.remove_punctuation:
            text = text.translate(str.maketrans("", "", string.punctuation))

        return {**data, "text": text}
```

**Create**: `src/elspeth/plugins/nodes/transforms/numeric/scoring.py`

```python
"""Score extraction transform (extracted from metrics.py row plugins)."""

from __future__ import annotations
from typing import Any
import re

def create_scoring_transform(
    options: dict[str, Any],
    context: PluginContext,
) -> ScoringTransform:
    """Create score extraction transform."""
    return ScoringTransform(
        field=options["field"],
        pattern=options.get("pattern", r"\d+"),
        score_type=options.get("score_type", "int"),
        context=context,
    )

class ScoringTransform:
    """Extract numeric scores from text.

    This is extracted from the score_extractor experiment row plugin,
    generalized to work in any orchestrator.
    """

    name = "scoring"

    def transform(self, data: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Extract score from text field."""
        text = data.get(self.field, "")

        match = re.search(self.pattern, text)
        if match:
            score = int(match.group()) if self.score_type == "int" else float(match.group())
            return {**data, "extracted_score": score}

        return {**data, "extracted_score": None}
```

### Step 2.6: Move Aggregators

**Create**: `src/elspeth/plugins/nodes/aggregators/statistics.py`

```python
"""Statistics aggregator node (extracted from metrics.py)."""

# Extract StatisticsAggregator from current metrics.py
# Make it a standalone aggregator node
```

**Create**: `src/elspeth/plugins/nodes/aggregators/registry.py`

```python
"""Aggregator node registry."""

from elspeth.core.registry import BasePluginRegistry
from elspeth.core.interfaces import AggregatorNode

from .statistics import create_statistics_aggregator
from .recommendations import create_recommendations_aggregator
from .ranking import create_ranking_aggregator

aggregator_registry = BasePluginRegistry[AggregatorNode]("aggregator")

aggregator_registry.register("statistics", create_statistics_aggregator, STATISTICS_SCHEMA)
aggregator_registry.register("recommendations", create_recommendations_aggregator, RECOMMENDATIONS_SCHEMA)
aggregator_registry.register("ranking", create_ranking_aggregator, RANKING_SCHEMA)

__all__ = ["aggregator_registry"]
```

---

## Phase 3: Security Hardening (2-3 hours)

### Step 3.1: Audit Silent Defaults

**Find all silent defaults**:
```bash
# Search for .get() with default values
rg "\.get\(['\"][^'\"]+['\"],\s*[^)]" src/elspeth/plugins/

# Search for "or" fallbacks
rg "\|\|\s*['\"]" src/elspeth/plugins/
```

**Common patterns to remove**:
```python
# BAD: Silent default
model = options.get("model", "gpt-4")
temperature = options.get("temperature", 0.7)
security_level = options.get("security_level", "internal")

# GOOD: Explicit required
model = options.get("model")
if not model:
    raise ConfigurationError("'model' is required")

temperature = options.get("temperature")
if temperature is None:
    raise ConfigurationError("'temperature' is required")

security_level = options.get("security_level")
if not security_level:
    raise ConfigurationError("'security_level' is required")
```

### Step 3.2: Update Schemas

**Mark all critical fields as required**:

```python
# Before
AZURE_OPENAI_SCHEMA = {
    "type": "object",
    "properties": {
        "model": {"type": "string"},
        "temperature": {"type": "number"},
        "security_level": {"type": "string", "enum": SECURITY_LEVELS},
    },
    # No "required" field - allows omissions
}

# After
AZURE_OPENAI_SCHEMA = {
    "type": "object",
    "properties": {
        "model": {"type": "string"},
        "temperature": {"type": "number"},
        "security_level": {"type": "string", "enum": SECURITY_LEVELS},
    },
    "required": ["model", "temperature", "security_level"],  # ← ENFORCE
}
```

### Step 3.3: Add Validation Tests

**Create**: `tests/test_explicit_config_enforcement.py`

```python
"""Test that all plugins require explicit configuration."""

import pytest
from elspeth.core.exceptions import ConfigurationError
from elspeth.plugins.nodes.sources.registry import source_registry
from elspeth.plugins.nodes.sinks.registry import sink_registry
from elspeth.plugins.nodes.transforms.llm.registry import llm_client_registry

def test_datasource_requires_security_level():
    """Test that datasources fail without explicit security_level."""
    with pytest.raises(ConfigurationError, match="security_level"):
        source_registry.create("csv_local", {"path": "/tmp/test.csv"})

def test_llm_requires_model():
    """Test that LLM clients fail without explicit model."""
    with pytest.raises(ConfigurationError, match="model"):
        llm_client_registry.create("azure_openai", {"security_level": "internal"})

def test_llm_requires_temperature():
    """Test that LLM clients fail without explicit temperature."""
    with pytest.raises(ConfigurationError, match="temperature"):
        llm_client_registry.create(
            "azure_openai",
            {"model": "gpt-4", "security_level": "internal"}
        )

# ... more tests for every plugin type
```

---

## Phase 4: Protocol Consolidation (2-3 hours)

### Step 4.1: Create Universal Protocols

**Create**: `src/elspeth/core/base/protocols.py`

```python
"""All universal plugin protocols for Elspeth."""

from __future__ import annotations
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

### Step 4.2: Move Experiment Protocols

**Create**: `src/elspeth/plugins/orchestrators/experiment/protocols.py`

```python
"""Experiment-specific protocols (topology-specific, not universal)."""

from typing import Protocol, Any

class RowExperimentPlugin(Protocol):
    """Experiment row processing."""
    name: str
    def process_row(self, row: dict[str, Any], responses: dict[str, Any]) -> dict[str, Any]: ...

class ValidationPlugin(Protocol):
    """Experiment validation."""
    name: str
    def validate(self, response: dict[str, Any], **kwargs) -> None: ...

class BaselineComparisonPlugin(Protocol):
    """Experiment baseline comparison."""
    name: str
    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]: ...

class EarlyStopPlugin(Protocol):
    """Experiment early stopping."""
    name: str
    def check(self, record: dict[str, Any], **kwargs) -> dict[str, Any] | None: ...
```

---

## Phase 5: Update Documentation & Tests (2-3 hours)

### Step 5.1: Update Plugin Catalogue

**Modify**: `docs/architecture/plugin-catalogue.md`

Reorganize by new structure:
1. Orchestrators
2. Source Nodes
3. Sink Nodes
4. Transform Nodes (with LLM as subsection)
5. Aggregator Nodes
6. Utility Nodes

### Step 5.2: Create Developer Guides

**Create**: `docs/development/orchestrator-development.md`

- How to add a new orchestrator
- Defining topology vs defining transformations
- Example: batch orchestrator

**Create**: `docs/development/node-development.md`

- How to add a new node type
- Source, sink, transform, aggregator patterns
- Security requirements (no defaults)

### Step 5.3: Update Architecture Diagrams

**Create**: Data flow diagram showing:
- Orchestrators (engines) defining topology
- Nodes (components) providing transformations
- LLM as one transform type among many

### Step 5.4: Reorganize Tests

```bash
# Mirror new structure
tests/
├── orchestrators/
│   └── test_experiment_orchestrator.py
├── nodes/
│   ├── sources/
│   │   ├── test_csv_local.py
│   │   └── test_azure_blob.py
│   ├── sinks/
│   │   ├── test_csv_file.py
│   │   └── test_excel.py
│   ├── transforms/
│   │   ├── llm/
│   │   │   ├── test_azure_openai_client.py
│   │   │   └── test_middleware.py
│   │   ├── text/
│   │   │   └── test_cleaning.py
│   │   └── numeric/
│   │       └── test_scoring.py
│   └── aggregators/
│       └── test_statistics.py
└── integration/
    └── test_end_to_end_data_flow.py
```

---

## Verification Checklist

After migration, verify:

- [ ] All 545 tests pass
- [ ] Mypy has 0 errors
- [ ] Ruff linting passes
- [ ] No silent defaults in any plugin factory
- [ ] All schemas mark critical fields as "required"
- [ ] Backward compatibility shims work
- [ ] Can create experiment orchestrator from config
- [ ] Configuration snapshot is complete and self-contained
- [ ] LLM is in `plugins/nodes/transforms/llm/` (not special-cased)
- [ ] Registry count: 7 files (down from 18)
- [ ] Documentation updated
- [ ] Sample suite still runs: `make sample-suite`

---

## Rollback Plan

If migration fails, rollback is straightforward:

1. **Git revert**: All changes are in version control
2. **Backward compatibility shims**: Old imports still work
3. **No breaking changes**: Existing configs still valid
4. **Tests protect**: 545 tests catch regressions

**Rollback command**:
```bash
git revert <migration-commit-range>
make bootstrap  # Re-run tests
```

---

## Post-Migration Benefits

After migration completes:

1. **Clearer mental model**: "Elspeth orchestrates data flow" vs "Elspeth runs LLM experiments"
2. **LLM not special**: Just one transform type, easier to reason about
3. **Fewer registries**: 7 vs 18 (61% reduction)
4. **Explicit config**: No silent defaults, better audit trail
5. **Extensible**: Easy to add new orchestrators (batch, streaming, validation)
6. **Reusable nodes**: Text cleaning, scoring, aggregation work across orchestrators
7. **Security hardened**: Explicit configuration enforced everywhere

---

## Timeline

- **Phase 1** (Orchestration): 3-4 hours
- **Phase 2** (Nodes): 3-4 hours
- **Phase 3** (Security): 2-3 hours
- **Phase 4** (Protocols): 2-3 hours
- **Phase 5** (Docs/Tests): 2-3 hours

**Total**: 12-17 hours

**Recommended approach**: Work in phases, commit after each phase, run full test suite between phases.
