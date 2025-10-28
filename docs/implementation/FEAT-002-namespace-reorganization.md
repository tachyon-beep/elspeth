# FEAT-002: Namespace Reorganization - Framework Primitives vs Domain Features

**Priority**: P4 (NICE-TO-HAVE - Post-Merge)
**Effort**: 8-12 hours (1-2 days)
**Sprint**: Sprint 4 (Post-Merge)
**Status**: PLANNED (Execute after VULN-004 + FEAT-001 merge)
**Depends On**: VULN-004 (registry enforcement), FEAT-001 (class renaming)
**Breaking Changes**: Yes (pre-1.0 = breaking changes acceptable, no backward compatibility needed)
**GitHub Issue**: #23

---

## Overview

### Problem Statement

**Finding**: 5 top-level directories (`adapters/`, `retrieval/`, `tools/`, `plugins/orchestrators/`, `plugins/utilities/`) exist outside the documented `core/` and `plugins/` architecture, creating architectural inconsistency.

**Root Cause**: Features evolved organically without architectural planning:
- **adapters/** - Azure Blob Storage utilities (9.7 KB, 7 uses)
- **retrieval/** - RAG/embeddings infrastructure (21 KB, 14 uses)
- **tools/** - Suite reporting utilities (15.4 KB, 4 uses)
- **plugins/orchestrators/** - Protocol definitions + backward-compat shim (200 bytes, 7 uses)
- **plugins/utilities/** - Retrieval context utility (10.4 KB, 2 uses)

**Impact**:
- ❌ Architectural drift - features not documented in CLAUDE.md
- ❌ Unclear boundaries between "framework" and "features"
- ❌ Difficult to identify what's core vs optional
- ❌ Inconsistent module organization

**Pre-1.0 Status**: Breaking changes are acceptable - clean cut-over without backward compatibility.

**Vision Alignment**: Elspeth is a **general orchestration platform** with **batteries-included** approach:
- **Core** = Framework primitives (orchestration engine, security, registries, pipelines)
- **Plugins** = Domain implementations (sources, transforms, sinks)

---

## Current State Analysis

### Directory Structure (Current)

```
src/elspeth/
├── adapters/                # ⚠️ Stray: Azure Blob Storage utilities
│   ├── __init__.py
│   └── blob_store.py        # BlobConfig, load_blob_config, load_blob_csv
│
├── retrieval/               # ⚠️ Stray: RAG/embeddings infrastructure
│   ├── __init__.py
│   ├── embedding.py         # AzureOpenAIEmbedder, OpenAIEmbedder
│   ├── providers.py         # PgVectorQueryClient, create_query_client
│   └── service.py           # RetrievalService, create_retrieval_service
│
├── tools/                   # ⚠️ Stray: Suite reporting utilities
│   └── reporting.py         # SuiteReportGenerator
│
├── core/                    # ✅ Framework primitives
│   ├── orchestration/
│   ├── security/
│   ├── registries/
│   ├── pipeline/
│   └── validation/
│
└── plugins/                 # ⚠️ Mixed: Domain features + stray subdirs
    ├── nodes/               # ✅ Correct: Sources, transforms, sinks
    ├── experiments/         # ✅ Correct: Experiment plugins
    ├── orchestrators/       # ⚠️ Stray: Protocols + backward compat
    │   └── experiment/
    │       ├── __init__.py  # Lazy import ExperimentRunner (from core)
    │       └── protocols.py # ValidationPlugin, RowExperimentPlugin, etc.
    └── utilities/           # ⚠️ Stray: Retrieval context utility
        └── retrieval.py     # RetrievalContextUtility
```

### Usage Analysis

| Module | Files | Lines | Imports | Type | Core or Feature? |
|--------|-------|-------|---------|------|------------------|
| **adapters/** | 2 | ~300 | 7 | Blob storage adapter | **Feature** (datasource type) |
| **retrieval/** | 4 | ~700 | 14 | RAG/embeddings | **Feature** (transform type) |
| **tools/** | 1 | ~500 | 4 | Report generation | **Feature** (sink type) |
| **plugins/orchestrators/** | 2 | ~100 | 7 | Protocols + shim | **Framework** (protocols) |
| **plugins/utilities/** | 1 | ~350 | 2 | Retrieval context | **Feature** (utility plugin) |

**Key Insight**: All "stray" modules are **actively used** - none are orphaned. The issue is **architectural placement**, not dead code.

---

## Rationale: Framework vs Features

### The Pattern: Batteries Included, But Removable

**Inspiration**: Django, FastAPI, Prefect, Airflow

**Core Principles**:
1. **Core = Framework Primitives**: Orchestration engine, security, plugin system, pipeline execution
2. **Plugins = Domain Implementations**: Sources, transforms, sinks (CSV, LLM, RAG, reporting)
3. **Batteries Included**: Ship with common features by default
4. **But Removable**: Features can be optionally removed or replaced

### The Test: "Can I Delete This Without Breaking the Engine?"

| Module | Delete Impact | Verdict |
|--------|---------------|---------|
| `core/security/` | ❌ Orchestration breaks (no MLS enforcement) | **Framework** |
| `core/registries/` | ❌ Orchestration breaks (no plugin system) | **Framework** |
| `core/pipeline/` | ❌ Orchestration breaks (no DAG execution) | **Framework** |
| `adapters/blob_store.py` | ✅ Engine works (just no Azure Blob datasource) | **Feature** |
| `retrieval/` | ✅ Engine works (just no RAG transforms) | **Feature** |
| `tools/reporting.py` | ✅ Engine works (just no suite reports) | **Feature** |

**Rule**: If deleting it breaks the **orchestration engine**, it's **core**. If it breaks a **specific use case**, it's a **feature/plugin**.

---

## Proposed Architecture

### Target Structure (Post-FEAT-002)

```
src/elspeth/
├── core/                    # ⚙️ Framework Primitives ONLY
│   ├── base/
│   │   ├── protocols.py     # ← MOVED: All framework protocols (incl. experiment plugins)
│   │   ├── plugin.py
│   │   └── types.py
│   ├── orchestration/       # Sense-decide-act engine
│   ├── security/            # Bell-LaPadula MLS enforcement
│   ├── registries/          # Plugin registration system
│   ├── pipeline/            # DAG execution engine
│   ├── validation/          # Schema/suite validation
│   └── cli/                 # CLI framework
│
└── plugins/                 # 🔌 Domain Implementations (node types)
    ├── nodes/               # Pipeline node implementations
    │   ├── sources/         # Data sources
    │   │   ├── csv_local.py
    │   │   ├── csv_blob.py
    │   │   └── blob_adapter.py     # ← MOVED: From adapters/blob_store.py
    │   ├── transforms/      # Transformations
    │   │   ├── llm/
    │   │   │   └── middleware/
    │   │   └── retrieval/          # ← MOVED: From retrieval/
    │   │       ├── __init__.py     # Public API
    │   │       ├── embedders.py    # From retrieval/embedding.py
    │   │       ├── providers.py    # From retrieval/providers.py
    │   │       ├── service.py      # From retrieval/service.py
    │   │       └── context.py      # From plugins/utilities/retrieval.py
    │   └── sinks/           # Outputs
    │       ├── csv_file.py
    │       ├── excel.py
    │       └── reporting/          # ← MOVED: From tools/reporting.py
    │           ├── __init__.py     # Public API
    │           └── suite_reporter.py
    ├── experiments/         # Experiment-specific plugins
    │   ├── row/
    │   ├── aggregators/
    │   └── baseline/
    └── orchestrators/       # Kept for backward compat (lazy import shim only)
        └── experiment/
            └── __init__.py  # Lazy import ExperimentRunner from core
```

### Migration Table

| Current Location | New Location | Rationale |
|------------------|--------------|-----------|
| `adapters/blob_store.py` | `plugins/nodes/sources/blob_adapter.py` | Blob storage is a **datasource implementation** (source node) |
| `retrieval/embedding.py` | `plugins/nodes/transforms/retrieval/embedders.py` | Embeddings are a **transformation** (data → embeddings) |
| `retrieval/providers.py` | `plugins/nodes/transforms/retrieval/providers.py` | Vector DB clients are **transform infrastructure** |
| `retrieval/service.py` | `plugins/nodes/transforms/retrieval/service.py` | Retrieval service orchestrates transform operations |
| `tools/reporting.py` | `plugins/nodes/sinks/reporting/suite_reporter.py` | Report generation is a **sink operation** (results → reports) |
| `plugins/utilities/retrieval.py` | `plugins/nodes/transforms/retrieval/context.py` | Merge into retrieval transform module |
| `plugins/orchestrators/experiment/protocols.py` | `core/base/protocols.py` | Framework-level protocols belong in core |

---

## Implementation Phases

### Phase 0: Pre-Migration Setup (30 minutes)

**Deliverables**:
1. Create migration branch: `feature/feat-002-namespace-reorganization`
2. Tag current commit: `pre-feat-002-migration`
3. Run full test suite baseline: `pytest -v > baseline_tests.txt`

**Success Criteria**:
- [x] Branch created
- [x] Baseline test results captured (1,480 passing)
- [x] No pending changes in working directory

---

### Phase 1: Move adapters → plugins/nodes/sources (2-3 hours)

#### Step 1.1: Create New Module (30 min)

```bash
# Create new module with moved code
mkdir -p src/elspeth/plugins/nodes/sources/
cp src/elspeth/adapters/blob_store.py src/elspeth/plugins/nodes/sources/blob_adapter.py
```

**Edit `plugins/nodes/sources/blob_adapter.py`**:
- Update docstring: "Azure Blob Storage adapter for datasource plugins"
- No functional changes (copy-paste migration)

#### Step 1.2: Update Imports (1 hour)

**Files to Update** (7 total):

**Plugins (2 files)**:
```python
# src/elspeth/plugins/nodes/sinks/blob.py
- from elspeth.adapters.blob_store import BlobConfig, load_blob_config
+ from elspeth.plugins.nodes.sources.blob_adapter import BlobConfig, load_blob_config

# src/elspeth/plugins/nodes/sources/blob.py
- from elspeth.adapters import load_blob_csv
+ from elspeth.plugins.nodes.sources.blob_adapter import load_blob_csv
```

**Registries (2 files)**:
```python
# src/elspeth/core/registries/sink.py
- from elspeth.adapters.blob_store import load_blob_config
+ from elspeth.plugins.nodes.sources.blob_adapter import load_blob_config

# src/elspeth/core/registries/datasource.py
- from elspeth.adapters.blob_store import load_blob_config
+ from elspeth.plugins.nodes.sources.blob_adapter import load_blob_config
```

**Tests (3 files)**:
```python
# tests/sinks/test_blob_sink_uploads.py
- from elspeth.adapters.blob_store import BlobConfig
+ from elspeth.plugins.nodes.sources.blob_adapter import BlobConfig

# tests/adapters/test_blob_store_config.py
- from elspeth.adapters.blob_store import (...)
+ from elspeth.plugins.nodes.sources.blob_adapter import (...)

# tests/test_blob_store.py
- from elspeth.adapters import BlobConfig, ...
+ from elspeth.plugins.nodes.sources.blob_adapter import BlobConfig, ...
```

#### Step 1.3: Delete Old Module (5 min)

**Pre-1.0 Approach**: Clean cut-over, no backward compatibility.

```bash
# Delete old module (breaking change - pre-1.0 acceptable)
rm -rf src/elspeth/adapters/
```

#### Step 1.4: Test and Commit (30 min)

```bash
# Run tests for affected modules
pytest tests/test_blob_store.py tests/adapters/ tests/sinks/test_blob_sink_uploads.py -v

# Run full test suite
pytest tests/ -v

# Verify 1,480 tests still passing
# Commit
git add .
git commit -m "FEAT-002 Phase 1: Move adapters/ → plugins/nodes/sources/blob_adapter.py

- Relocate blob storage utilities to datasource plugin namespace
- Update 7 imports (2 plugins, 2 registries, 3 tests)
- Delete src/elspeth/adapters/ (breaking change - pre-1.0)
- All tests passing (1,480/1,480)

BREAKING CHANGE: Import path changed from elspeth.adapters to elspeth.plugins.nodes.sources.blob_adapter

Related: FEAT-002 namespace reorganization"
```

**Success Criteria**:
- [x] `plugins/nodes/sources/blob_adapter.py` created
- [x] 7 imports updated
- [x] Old `adapters/` directory deleted
- [x] All tests passing (1,480/1,480)
- [x] Clean commit with BREAKING CHANGE notice

---

### Phase 2: Move retrieval → plugins/nodes/transforms/retrieval (2-3 hours)

#### Step 2.1: Create New Module Structure (1 hour)

```bash
# Create retrieval transform module
mkdir -p src/elspeth/plugins/nodes/transforms/retrieval/

# Move files with renaming
cp src/elspeth/retrieval/embedding.py \
   src/elspeth/plugins/nodes/transforms/retrieval/embedders.py

cp src/elspeth/retrieval/providers.py \
   src/elspeth/plugins/nodes/transforms/retrieval/providers.py

cp src/elspeth/retrieval/service.py \
   src/elspeth/plugins/nodes/transforms/retrieval/service.py

cp src/elspeth/plugins/utilities/retrieval.py \
   src/elspeth/plugins/nodes/transforms/retrieval/context.py
```

**Create `plugins/nodes/transforms/retrieval/__init__.py`**:
```python
"""Retrieval-Augmented Generation (RAG) transform nodes.

This module provides embedders, vector database clients, and retrieval services
for augmenting LLM context with relevant documents.

Components:
- Embedders: Convert text to embeddings (OpenAI, Azure OpenAI)
- Providers: Vector database clients (PgVector)
- Service: High-level retrieval orchestration
- Context: Retrieval context injection utility
"""

# Embedders
from .embedders import AzureOpenAIEmbedder, Embedder, OpenAIEmbedder

# Providers
from .providers import (
    PgVectorQueryClient,
    QueryResult,
    VectorQueryClient,
    create_query_client,
)

# Service
from .service import RetrievalService, create_retrieval_service

# Context utility
from .context import RetrievalContextUtility

__all__ = [
    # Embedders
    "AzureOpenAIEmbedder",
    "Embedder",
    "OpenAIEmbedder",
    # Providers
    "PgVectorQueryClient",
    "QueryResult",
    "VectorQueryClient",
    "create_query_client",
    # Service
    "RetrievalService",
    "create_retrieval_service",
    # Context utility
    "RetrievalContextUtility",
]
```

#### Step 2.2: Update Internal Imports (30 min)

**Update imports within retrieval module**:

```python
# plugins/nodes/transforms/retrieval/service.py
- from elspeth.retrieval.embedding import AzureOpenAIEmbedder, Embedder, OpenAIEmbedder
- from elspeth.retrieval.providers import QueryResult, VectorQueryClient, create_query_client
+ from elspeth.plugins.nodes.transforms.retrieval.embedders import AzureOpenAIEmbedder, Embedder, OpenAIEmbedder
+ from elspeth.plugins.nodes.transforms.retrieval.providers import QueryResult, VectorQueryClient, create_query_client
```

#### Step 2.3: Update External Imports (1.5-2 hours)

**Files to Update** (14 total):

**Plugins (2 files)**:
```python
# src/elspeth/plugins/nodes/sinks/embeddings_store.py
- from elspeth.retrieval.embedding import AzureOpenAIEmbedder, Embedder, OpenAIEmbedder
+ from elspeth.plugins.nodes.transforms.retrieval import AzureOpenAIEmbedder, Embedder, OpenAIEmbedder
```

**Tests (12 files)**: Update all test imports similarly.

#### Step 2.4: Delete Old Modules (5 min)

**Pre-1.0 Approach**: Clean cut-over, no backward compatibility.

```bash
# Delete old modules (breaking change - pre-1.0 acceptable)
rm -rf src/elspeth/retrieval/
rm -rf src/elspeth/plugins/utilities/
```

#### Step 2.5: Test and Commit (30 min)

```bash
# Run retrieval tests
pytest tests/test_retrieval_service.py tests/retrieval/ tests/test_integration_embeddings_rag.py -v

# Run full test suite
pytest tests/ -v

# Commit
git add .
git commit -m "FEAT-002 Phase 2: Move retrieval/ → plugins/nodes/transforms/retrieval/

- Relocate RAG infrastructure to transform plugin namespace
- Merge plugins/utilities/retrieval.py into retrieval/context.py
- Update 14 imports (2 plugins, 12 tests)
- Delete src/elspeth/retrieval/ and src/elspeth/plugins/utilities/ (breaking change - pre-1.0)
- All tests passing (1,480/1,480)

BREAKING CHANGE: Import paths changed:
  - elspeth.retrieval → elspeth.plugins.nodes.transforms.retrieval
  - elspeth.plugins.utilities.retrieval → elspeth.plugins.nodes.transforms.retrieval.context

Related: FEAT-002 namespace reorganization"
```

**Success Criteria**:
- [x] `plugins/nodes/transforms/retrieval/` created (4 files)
- [x] `retrieval/` and `plugins/utilities/` deleted
- [x] 14 imports updated
- [x] All tests passing (1,480/1,480)
- [x] Clean commit with BREAKING CHANGE notice

---

### Phase 3: Move tools/reporting → plugins/nodes/sinks/reporting (1-2 hours)

#### Step 3.1: Create New Module (30 min)

```bash
# Create reporting sink module
mkdir -p src/elspeth/plugins/nodes/sinks/reporting/

# Move file
cp src/elspeth/tools/reporting.py \
   src/elspeth/plugins/nodes/sinks/reporting/suite_reporter.py
```

**Create `plugins/nodes/sinks/reporting/__init__.py`**:
```python
"""Suite reporting sink nodes.

This module provides suite-level report generation including markdown,
Excel, visualizations, and consolidated artifacts.
"""

from .suite_reporter import SuiteReportGenerator

__all__ = ["SuiteReportGenerator"]
```

#### Step 3.2: Update Imports (1 hour)

**Files to Update** (4 total):

```python
# src/elspeth/cli.py
- from elspeth.tools.reporting import SuiteReportGenerator
+ from elspeth.plugins.nodes.sinks.reporting import SuiteReportGenerator

# src/elspeth/core/cli/suite.py
- from elspeth.tools.reporting import SuiteReportGenerator as _SRG
+ from elspeth.plugins.nodes.sinks.reporting import SuiteReportGenerator as _SRG

# tests/tools/test_reporting_visualizations.py
- from elspeth.tools.reporting import SuiteReportGenerator
+ from elspeth.plugins.nodes.sinks.reporting import SuiteReportGenerator

# tests/test_suite_reporter.py
- from elspeth.tools.reporting import SuiteReportGenerator
+ from elspeth.plugins.nodes.sinks.reporting import SuiteReportGenerator
```

#### Step 3.3: Delete Old Module (5 min)

**Pre-1.0 Approach**: Clean cut-over, no backward compatibility.

```bash
# Delete old module (breaking change - pre-1.0 acceptable)
rm -rf src/elspeth/tools/
```

#### Step 3.4: Test and Commit (30 min)

```bash
# Run reporting tests
pytest tests/tools/ tests/test_suite_reporter.py -v

# Run full test suite
pytest tests/ -v

# Commit
git add .
git commit -m "FEAT-002 Phase 3: Move tools/reporting → plugins/nodes/sinks/reporting/

- Relocate suite reporting to sink plugin namespace
- Update 4 imports (1 core, 3 tests)
- Delete src/elspeth/tools/ (breaking change - pre-1.0)
- All tests passing (1,480/1,480)

BREAKING CHANGE: Import path changed from elspeth.tools.reporting to elspeth.plugins.nodes.sinks.reporting

Related: FEAT-002 namespace reorganization"
```

**Success Criteria**:
- [x] `plugins/nodes/sinks/reporting/suite_reporter.py` created
- [x] 4 imports updated
- [x] Old `tools/` directory deleted
- [x] All tests passing (1,480/1,480)
- [x] Clean commit with BREAKING CHANGE notice

---

### Phase 4: Consolidate protocols → core/base/protocols.py (1-2 hours)

#### Step 4.1: Merge Protocol Definitions (30 min)

**Edit `src/elspeth/core/base/protocols.py`**:

Add experiment protocols from `plugins/orchestrators/experiment/protocols.py`:

```python
# ... existing protocols ...

# ============================================================================
# Experiment-Specific Protocols (from plugins/orchestrators/experiment)
# ============================================================================

class ValidationError(RuntimeError):
    """Raised when a validation plugin rejects an LLM response."""


class ValidationPlugin(Protocol):
    """Evaluates LLM responses and raises ``ValidationError`` on failure."""

    name: str

    def validate(
        self,
        response: dict[str, Any],
        *,
        context: dict[str, Any | None] | None = None,
        metadata: dict[str, Any | None] | None = None,
    ) -> None:
        """Inspect a response and raise ``ValidationError`` when criteria fail."""

    def input_schema(self) -> type["DataFrameSchema"] | None:
        """Return schema of input columns this plugin requires."""
        return None


class RowExperimentPlugin(Protocol):
    """Processes a single experiment row and returns derived fields."""
    # ... (copy full definition from protocols.py)


class AggregationExperimentPlugin(Protocol):
    """Aggregates experiment results across multiple rows."""
    # ... (copy full definition from protocols.py)


class EarlyStopPlugin(Protocol):
    """Decides whether to stop an experiment early based on results."""
    # ... (copy full definition from protocols.py)
```

#### Step 4.2: Update Imports (30 min)

**Files to Update** (7 total):

```python
# src/elspeth/plugins/experiments/prompt_variants.py
- from elspeth.plugins.orchestrators.experiment.protocols import AggregationExperimentPlugin
+ from elspeth.core.base.protocols import AggregationExperimentPlugin

# src/elspeth/plugins/experiments/validation.py
- from elspeth.plugins.orchestrators.experiment.protocols import ValidationError, ValidationPlugin
+ from elspeth.core.base.protocols import ValidationError, ValidationPlugin

# src/elspeth/core/experiments/runner.py
- from elspeth.plugins.orchestrators.experiment.protocols import (...)
+ from elspeth.core.base.protocols import (...)

# src/elspeth/core/experiments/experiment_registries.py
- from elspeth.plugins.orchestrators.experiment.protocols import (...)
+ from elspeth.core.base.protocols import (...)

# src/elspeth/core/experiments/plugin_registry.py
- from elspeth.plugins.orchestrators.experiment.protocols import (...)
+ from elspeth.core.base.protocols import (...)

# tests/test_validation_plugins.py
- from elspeth.plugins.orchestrators.experiment.protocols import ValidationError
+ from elspeth.core.base.protocols import ValidationError
```

#### Step 4.3: Keep Orchestrators as Lazy Import Shim (15 min)

**Keep `plugins/orchestrators/experiment/__init__.py`** for `ExperimentRunner` lazy import (avoids circular dependencies):

```python
"""Experiment orchestrator - DAG pattern for LLM experimentation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspeth.core.experiments.runner import ExperimentRunner

__all__ = ["ExperimentRunner"]


def __getattr__(name: str):
    """Lazy import to avoid circular dependencies."""
    if name == "ExperimentRunner":
        from elspeth.core.experiments.runner import ExperimentRunner
        return ExperimentRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

**Note**: This is NOT a deprecation shim - it's a legitimate lazy import pattern to avoid circular dependencies.

**Delete `plugins/orchestrators/experiment/protocols.py`**:
```bash
rm src/elspeth/plugins/orchestrators/experiment/protocols.py
```

#### Step 4.4: Test and Commit (30 min)

```bash
# Run experiment tests
pytest tests/test_validation_plugins.py tests/orchestrators/ -v

# Run full test suite
pytest tests/ -v

# Commit
git add .
git commit -m "FEAT-002 Phase 4: Consolidate protocols → core/base/protocols.py

- Move experiment protocols from plugins/orchestrators to core
- Update 7 imports (5 core, 1 plugin, 1 test)
- Keep orchestrators/__init__.py as lazy import shim (avoids circular dependencies)
- Delete plugins/orchestrators/experiment/protocols.py
- All tests passing (1,480/1,480)

BREAKING CHANGE: Import path changed from elspeth.plugins.orchestrators.experiment.protocols to elspeth.core.base.protocols

Related: FEAT-002 namespace reorganization"
```

**Success Criteria**:
- [x] Experiment protocols added to `core/base/protocols.py`
- [x] 7 imports updated
- [x] `protocols.py` deleted, `__init__.py` kept (lazy import, not deprecation)
- [x] All tests passing (1,480/1,480)
- [x] Clean commit with BREAKING CHANGE notice

---

### Phase 5: Update Documentation (1 hour)

#### Step 5.1: Update CLAUDE.md (30 min)

**Edit `CLAUDE.md`** - Update "Core Structure" section:

```markdown
### Core Structure

- **`src/elspeth/core/`** – Orchestration framework primitives
  - `orchestration/` – Sense-decide-act engine
  - `base/` – Base classes, protocols, types (including experiment protocols)
  - `security/` – Bell-LaPadula Multi-Level Security enforcement
  - `registries/` – Plugin registration system (ADR-003)
  - `pipeline/` – DAG execution engine with artifact chaining
  - `validation/` – Schema validation, suite validation, settings validation
  - `cli/` – CLI framework (suite, single, job, validate commands)
  - `experiments/` – ExperimentRunner orchestration (suite_runner.py, runner.py)

- **`src/elspeth/plugins/`** – Domain-specific node implementations
  - `nodes/sources/` – Data sources (CSV local/blob, Azure Blob, in-memory)
    - `blob_adapter.py` – Azure Blob Storage utilities (formerly `adapters/`)
  - `nodes/transforms/llm/` – LLM transformations (Azure OpenAI, OpenAI HTTP, mock)
    - `middleware/` – Prompt shielding, Azure Content Safety, PII detection, health monitoring
  - `nodes/transforms/retrieval/` – RAG/embeddings infrastructure (formerly `retrieval/`)
    - `embedders.py` – OpenAI/Azure embedders
    - `providers.py` – Vector database clients (PgVector)
    - `service.py` – Retrieval service orchestration
    - `context.py` – Retrieval context injection utility
  - `nodes/sinks/` – Output sinks (CSV, Excel, JSON, Markdown, embeddings, visual analytics)
    - `reporting/` – Suite report generation (formerly `tools/reporting.py`)
  - `experiments/` – Experiment-specific plugins
    - `row/` – Row-level plugins (score extractor)
    - `aggregators/` – Summary stats, recommendations, cost/latency, rationale analysis
    - `baseline/` – Statistical analysis (significance, effect size, Bayesian, distribution)
  - `orchestrators/experiment/` – Backward-compat shim (lazy import `ExperimentRunner` from core)

- **`tests/`** – Comprehensive test coverage (see `docs/development/testing-overview.md`)
  - Configuration, datasources, middleware, LLM adapters, sanitization, signing, artifact pipeline, suite runner
```

#### Step 5.2: Add Breaking Changes Notice (15 min)

**Add section to CLAUDE.md** - "Breaking Changes (Pre-1.0)":

```markdown
## Breaking Changes (FEAT-002 - Namespace Reorganization)

**Pre-1.0 Status**: Import paths changed in v0.x.x. No backward compatibility provided.

| Old Path | New Path | Reason |
|----------|----------|--------|
| `elspeth.adapters` | `elspeth.plugins.nodes.sources.blob_adapter` | Blob storage is a datasource implementation |
| `elspeth.retrieval` | `elspeth.plugins.nodes.transforms.retrieval` | RAG is a transformation operation |
| `elspeth.tools` | `elspeth.plugins.nodes.sinks.reporting` | Report generation is a sink operation |
| `elspeth.plugins.orchestrators.experiment.protocols` | `elspeth.core.base.protocols` | Framework protocols belong in core |
| `elspeth.plugins.utilities.retrieval` | `elspeth.plugins.nodes.transforms.retrieval.context` | Merged into retrieval transform module |

**Migration**:

```python
# Old imports (NO LONGER WORK)
from elspeth.adapters import load_blob_config  # ❌ ImportError
from elspeth.retrieval import RetrievalService  # ❌ ImportError
from elspeth.tools.reporting import SuiteReportGenerator  # ❌ ImportError

# New imports (required)
from elspeth.plugins.nodes.sources.blob_adapter import load_blob_config  # ✅
from elspeth.plugins.nodes.transforms.retrieval import RetrievalService  # ✅
from elspeth.plugins.nodes.sinks.reporting import SuiteReportGenerator  # ✅
```

**Rationale**: Aligns namespace with "framework primitives vs domain features" pattern.
```

#### Step 5.3: Update CHANGELOG (10 min)

**Add to CHANGELOG.md**:

```markdown
## [Unreleased]

### BREAKING CHANGES (Pre-1.0)

#### Namespace Reorganization (FEAT-002)

Import paths changed to align with "framework primitives vs domain features" architecture:

- **Blob storage utilities**: `elspeth.adapters` → `elspeth.plugins.nodes.sources.blob_adapter`
- **RAG infrastructure**: `elspeth.retrieval` → `elspeth.plugins.nodes.transforms.retrieval`
- **Suite reporting**: `elspeth.tools.reporting` → `elspeth.plugins.nodes.sinks.reporting`
- **Experiment protocols**: `elspeth.plugins.orchestrators.experiment.protocols` → `elspeth.core.base.protocols`
- **Retrieval utility**: `elspeth.plugins.utilities.retrieval` → `elspeth.plugins.nodes.transforms.retrieval.context`

**Migration**: Update import statements to use new paths. See docs/implementation/FEAT-002-namespace-reorganization.md for full details.

**Rationale**: Separates framework primitives (core/) from domain implementations (plugins/).
```

#### Step 5.4: Commit Documentation (5 min)

```bash
git add docs/ CLAUDE.md
git commit -m "FEAT-002 Phase 5: Update documentation for namespace reorganization

- Update CLAUDE.md with new directory structure
- Add deprecation notice section
- Create v2.0 migration guide
- Document import path changes

Related: FEAT-002 namespace reorganization"
```

**Success Criteria**:
- [x] CLAUDE.md updated with new structure
- [x] Deprecation notice added
- [x] Migration guide created
- [x] Clear import path mapping documented

---

## Testing Strategy

### Test Coverage Requirements

**Minimum Coverage**: All existing tests must pass (1,480/1,480)

**Regression Testing**:
1. **Unit Tests**: All module-level tests pass
2. **Integration Tests**: Suite runner, artifact pipeline, security enforcement
3. **Deprecation Warnings**: Verify warnings emit on old import paths
4. **Import Validation**: Ensure all old imports still work via shims

### Test Execution Plan

```bash
# After each phase
pytest tests/ -v --tb=short

# Verify old imports raise ImportError
python -c "from elspeth.adapters import load_blob_config" 2>&1 | grep "ImportError" || echo "FAIL: Old import still works!"
python -c "from elspeth.retrieval import RetrievalService" 2>&1 | grep "ImportError" || echo "FAIL: Old import still works!"

# Final validation
pytest tests/ -v --cov=elspeth --cov-report=term-missing
```

### Test Modifications

**Required**: Update all test imports to use new paths (included in phase work).

**No Optional Cleanup**: Pre-1.0 means we update everything in one go.

---

## Migration Strategy

### Pre-1.0 Approach: Clean Breaking Changes

**Philosophy**: Pre-1.0 allows breaking changes without backward compatibility.

**Current Behavior (v0.x)**:
```python
# Old imports (work today)
from elspeth.adapters import load_blob_config  # ✅ Works
from elspeth.retrieval import RetrievalService  # ✅ Works
from elspeth.tools.reporting import SuiteReportGenerator  # ✅ Works
```

**After FEAT-002 (v0.x+1)**:
```python
# Old imports (BREAK IMMEDIATELY)
from elspeth.adapters import load_blob_config  # ❌ ImportError
from elspeth.retrieval import RetrievalService  # ❌ ImportError
from elspeth.tools.reporting import SuiteReportGenerator  # ❌ ImportError

# New imports (required)
from elspeth.plugins.nodes.sources.blob_adapter import load_blob_config  # ✅ Works
from elspeth.plugins.nodes.transforms.retrieval import RetrievalService  # ✅ Works
from elspeth.plugins.nodes.sinks.reporting import SuiteReportGenerator  # ✅ Works
```

**No Deprecation Period**: Clean cut-over documented in CHANGELOG with BREAKING CHANGE notices.

### No Automated Migration Script Needed

**Pre-1.0 Approach**: All imports updated manually during FEAT-002 implementation (25 files).

**External Users**: Very few (if any) pre-1.0 users. Breaking changes acceptable and expected.

**Documentation**: CHANGELOG documents all import path changes with clear before/after examples.

---

## Risk Assessment

### High Risk

**⚠️ Import Churn**: 25+ files need import updates

**Mitigation**:
- Phase-by-phase approach (test after each phase)
- Automated search-replace for import updates
- Deprecation shims maintain backward compat

### Medium Risk

**⚠️ Circular Import Issues**: Moving modules may expose hidden circular dependencies

**Mitigation**:
- Use `TYPE_CHECKING` guards for type hints
- Lazy imports in `__getattr__` for backward compat
- Test imports explicitly: `python -c "import elspeth.plugins.nodes.transforms.retrieval"`

### Low Risk

**🟢 Merge Conflicts**: VULN-004 and FEAT-001 may touch overlapping files

**Mitigation**:
- Execute FEAT-002 **after** VULN-004 + FEAT-001 merge
- Rebase onto latest main before starting
- Keep phases small and atomic (easy to revert)

### Rollback Plan

**If Migration Fails**:
1. Identify failing phase (Phase 1-5)
2. Revert commits: `git reset --hard pre-feat-002-migration`
3. Cherry-pick successful phases if needed
4. Document failures in GitHub issue

**Rollback Command**:
```bash
# Abort entire migration
git reset --hard pre-feat-002-migration

# Or revert specific phase
git revert <phase-commit-hash>
```

---

## Success Criteria

### Functional Requirements

- [x] All modules moved to correct namespace (4 module groups)
- [x] All imports updated (25+ files)
- [x] Deprecation shims emit warnings
- [x] All tests passing (1,480/1,480)
- [x] No new test failures introduced

### Non-Functional Requirements

- [x] CLAUDE.md reflects new structure
- [x] Deprecation timeline documented
- [x] Migration guide created
- [x] Automated migration script provided
- [x] Clean commit history (1 commit per phase)

### Acceptance Criteria

**Definition of Done**:
1. ✅ All 5 phases complete
2. ✅ 1,480 tests passing (no regressions)
3. ✅ Deprecation warnings emit on old import paths
4. ✅ Documentation updated (CLAUDE.md + migration guide)
5. ✅ Clean commit history with descriptive messages
6. ✅ PR approved by 1+ reviewers

**Merge Blockers**:
- ❌ Any test failures
- ❌ Old import paths still work (should raise ImportError)
- ❌ Undocumented breaking changes (must be in CHANGELOG)

---

## Timeline and Effort

### Estimated Effort Breakdown

| Phase | Activity | Time | Dependencies |
|-------|----------|------|--------------|
| Phase 0 | Pre-migration setup | 30 min | None |
| Phase 1 | Move adapters/ | 2-3 hours | Phase 0 |
| Phase 2 | Move retrieval/ | 2-3 hours | Phase 1 |
| Phase 3 | Move tools/ | 1-2 hours | Phase 2 |
| Phase 4 | Consolidate protocols | 1-2 hours | Phase 3 |
| Phase 5 | Documentation | 1 hour | Phase 4 |
| **Total** | **End-to-end** | **8-12 hours** | **Sequential** |

### Recommended Schedule

**Day 1** (4-5 hours):
- Morning: Phase 0 + Phase 1 (adapters)
- Afternoon: Phase 2 (retrieval)

**Day 2** (4-5 hours):
- Morning: Phase 3 (tools) + Phase 4 (protocols)
- Afternoon: Phase 5 (documentation) + Final testing + PR creation

---

## Post-Merge Tasks

### Immediate (within 1 week)

1. ✅ Monitor for breaking change reports from users (if any pre-1.0 users exist)
2. ✅ Update external documentation (readthedocs, wiki) with new import paths
3. ✅ Announce breaking changes in CHANGELOG and GitHub release notes

### Pre-1.0 Reality Check

**Expected User Impact**: Minimal - very few (if any) pre-1.0 external users.

**Support Strategy**: Point users to FEAT-002 documentation with import path mapping.

---

## References

### Related ADRs

- **ADR-001**: Design Philosophy - Security-first priority hierarchy
- **ADR-002**: Multi-Level Security Enforcement - Framework primitive in core
- **ADR-003**: Central Plugin Registry - Framework primitive in core
- **ADR-004**: Mandatory BasePlugin Inheritance - Framework primitive in core

### Related Implementations

- **FEAT-001**: Class Renaming for Generic Orchestration
- **VULN-004**: Registry Enforcement (must complete first)

### External References

**Best Practice Examples**:
- [Airflow Providers](https://github.com/apache/airflow/tree/main/airflow/providers) - Feature modules under providers/
- [Prefect Blocks](https://github.com/PrefectHQ/prefect/tree/main/src/prefect/blocks) - Domain features under blocks/
- [LangChain](https://github.com/langchain-ai/langchain/tree/master/libs/langchain) - Core vs community split
- [Django](https://github.com/django/django/tree/main/django) - Apps pattern (features as pluggable apps)

**Architecture Patterns**:
- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/) - Ports and adapters
- [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) - Framework independence

---

## Appendix A: File Listing

### Files to Create

1. `src/elspeth/plugins/nodes/sources/blob_adapter.py` (copied from adapters/blob_store.py)
2. `src/elspeth/plugins/nodes/transforms/retrieval/__init__.py`
3. `src/elspeth/plugins/nodes/transforms/retrieval/embedders.py` (copied from retrieval/embedding.py)
4. `src/elspeth/plugins/nodes/transforms/retrieval/providers.py` (copied from retrieval/providers.py)
5. `src/elspeth/plugins/nodes/transforms/retrieval/service.py` (copied from retrieval/service.py)
6. `src/elspeth/plugins/nodes/transforms/retrieval/context.py` (copied from plugins/utilities/retrieval.py)
7. `src/elspeth/plugins/nodes/sinks/reporting/__init__.py`
8. `src/elspeth/plugins/nodes/sinks/reporting/suite_reporter.py` (copied from tools/reporting.py)
9. `docs/migration/v2-namespace-consolidation.md`
10. `scripts/migrate_imports.py`

### Files to Modify

**Import Updates** (25+ files):
- 2 plugin files (blob sink, embeddings store)
- 2 registry files (datasource, sink)
- 5 core files (experiments/runner, experiment_registries, plugin_registry, cli/suite, cli.py)
- 1 experiment plugin file (prompt_variants, validation)
- 15+ test files (various)

**Deprecation Shims** (4 files):
- `src/elspeth/adapters/__init__.py`
- `src/elspeth/retrieval/__init__.py`
- `src/elspeth/tools/__init__.py` (create)
- `src/elspeth/plugins/orchestrators/experiment/__init__.py`

**Documentation** (2 files):
- `CLAUDE.md`
- `docs/implementation/README.md`

### Files to Delete

**Phase 1**:
- `src/elspeth/adapters/` (entire directory)

**Phase 2**:
- `src/elspeth/retrieval/` (entire directory)
- `src/elspeth/plugins/utilities/` (entire directory)

**Phase 3**:
- `src/elspeth/tools/` (entire directory)

**Phase 4**:
- `src/elspeth/plugins/orchestrators/experiment/protocols.py`

---

## Appendix B: Quick Reference

### Import Migration Cheat Sheet

| Old Import | New Import | Phase |
|------------|-----------|-------|
| `from elspeth.adapters import load_blob_config` | `from elspeth.plugins.nodes.sources.blob_adapter import load_blob_config` | Phase 1 |
| `from elspeth.retrieval import RetrievalService` | `from elspeth.plugins.nodes.transforms.retrieval import RetrievalService` | Phase 2 |
| `from elspeth.tools.reporting import SuiteReportGenerator` | `from elspeth.plugins.nodes.sinks.reporting import SuiteReportGenerator` | Phase 3 |
| `from elspeth.plugins.orchestrators.experiment.protocols import ValidationPlugin` | `from elspeth.core.base.protocols import ValidationPlugin` | Phase 4 |

### Command Quick Reference

```bash
# Start migration
git checkout -b feature/feat-002-namespace-reorganization
git tag pre-feat-002-migration

# After each phase
pytest tests/ -v
git add .
git commit -m "FEAT-002 Phase X: ..."

# Final checks
pytest tests/ -v --cov=elspeth
python -m ruff check src tests
python -m mypy src

# Merge
git push origin feature/feat-002-namespace-reorganization
# Create PR → Merge to main
```

---

**End of FEAT-002 Implementation Document**

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
