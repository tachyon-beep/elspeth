# Plugins Directory Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reorganize `src/elspeth/plugins/` into 4 subfolders — `sources/`, `sinks/`, `transforms/`, `infrastructure/` — aligned with the SDA model, updating all imports codebase-wide.

**Architecture:** Move files via `git mv` in dependency order, then rewrite all import paths using the mapping table from the design doc. No re-exports; all imports use canonical module paths. Parallel agent swarms for import rewriting and verification.

**Tech Stack:** Python imports, git mv, ruff, mypy, pytest

**Design doc:** `docs/plans/2026-03-01-plugins-restructure-design.md`

---

## Import Mapping Reference

Every task below rewrites imports using this mapping. The full table is in the design doc. The key patterns:

| Old prefix | New prefix |
|---|---|
| `elspeth.plugins.base` | `elspeth.plugins.infrastructure.base` |
| `elspeth.plugins.config_base` | `elspeth.plugins.infrastructure.config_base` |
| `elspeth.plugins.protocols` | `elspeth.plugins.infrastructure.protocols` |
| `elspeth.plugins.hookspecs` | `elspeth.plugins.infrastructure.hookspecs` |
| `elspeth.plugins.manager` | `elspeth.plugins.infrastructure.manager` |
| `elspeth.plugins.discovery` | `elspeth.plugins.infrastructure.discovery` |
| `elspeth.plugins.validation` | `elspeth.plugins.infrastructure.validation` |
| `elspeth.plugins.schema_factory` | `elspeth.plugins.infrastructure.schema_factory` |
| `elspeth.plugins.results` | `elspeth.plugins.infrastructure.results` |
| `elspeth.plugins.sentinels` | `elspeth.plugins.infrastructure.sentinels` |
| `elspeth.plugins.utils` | `elspeth.plugins.infrastructure.utils` |
| `elspeth.plugins.clients` | `elspeth.plugins.infrastructure.clients` |
| `elspeth.plugins.batching` | `elspeth.plugins.infrastructure.batching` |
| `elspeth.plugins.pooling` | `elspeth.plugins.infrastructure.pooling` |
| `elspeth.plugins.llm` | `elspeth.plugins.transforms.llm` |
| `elspeth.plugins.azure.auth` | `elspeth.plugins.infrastructure.azure_auth` |
| `elspeth.plugins.azure.blob_source` | `elspeth.plugins.sources.azure_blob_source` |
| `elspeth.plugins.azure.blob_sink` | `elspeth.plugins.sinks.azure_blob_sink` |

---

## Task 1: Create infrastructure/ package and move root-level files

**Context:** 11 Python files at `plugins/` root need to move into `plugins/infrastructure/`. These are the shared base classes, protocols, manager, discovery, validation, schema factory, results, sentinels, and utils. This is the foundation — everything else depends on these files existing at their new locations.

**Files:**
- Create: `src/elspeth/plugins/infrastructure/__init__.py`
- Move: `src/elspeth/plugins/base.py` → `src/elspeth/plugins/infrastructure/base.py`
- Move: `src/elspeth/plugins/config_base.py` → `src/elspeth/plugins/infrastructure/config_base.py`
- Move: `src/elspeth/plugins/protocols.py` → `src/elspeth/plugins/infrastructure/protocols.py`
- Move: `src/elspeth/plugins/hookspecs.py` → `src/elspeth/plugins/infrastructure/hookspecs.py`
- Move: `src/elspeth/plugins/manager.py` → `src/elspeth/plugins/infrastructure/manager.py`
- Move: `src/elspeth/plugins/discovery.py` → `src/elspeth/plugins/infrastructure/discovery.py`
- Move: `src/elspeth/plugins/validation.py` → `src/elspeth/plugins/infrastructure/validation.py`
- Move: `src/elspeth/plugins/schema_factory.py` → `src/elspeth/plugins/infrastructure/schema_factory.py`
- Move: `src/elspeth/plugins/results.py` → `src/elspeth/plugins/infrastructure/results.py`
- Move: `src/elspeth/plugins/sentinels.py` → `src/elspeth/plugins/infrastructure/sentinels.py`
- Move: `src/elspeth/plugins/utils.py` → `src/elspeth/plugins/infrastructure/utils.py`

**Step 1: Create the infrastructure package**

```bash
mkdir -p src/elspeth/plugins/infrastructure
```

**Step 2: Write infrastructure/__init__.py**

```python
# src/elspeth/plugins/infrastructure/__init__.py
"""Plugin infrastructure: base classes, protocols, config, discovery, validation."""
```

**Step 3: Move all 11 files**

```bash
cd src/elspeth/plugins
git mv base.py infrastructure/base.py
git mv config_base.py infrastructure/config_base.py
git mv protocols.py infrastructure/protocols.py
git mv hookspecs.py infrastructure/hookspecs.py
git mv manager.py infrastructure/manager.py
git mv discovery.py infrastructure/discovery.py
git mv validation.py infrastructure/validation.py
git mv schema_factory.py infrastructure/schema_factory.py
git mv results.py infrastructure/results.py
git mv sentinels.py infrastructure/sentinels.py
git mv utils.py infrastructure/utils.py
```

**Do NOT commit yet** — continue to Task 2.

---

## Task 2: Move clients/, batching/, pooling/ under infrastructure/

**Context:** These 3 subsystem packages provide shared concurrency/client infrastructure used by I/O-heavy transforms. They move from `plugins/` root to become subpackages of `infrastructure/`.

**Files:**
- Move: `src/elspeth/plugins/clients/` → `src/elspeth/plugins/infrastructure/clients/`
- Move: `src/elspeth/plugins/batching/` → `src/elspeth/plugins/infrastructure/batching/`
- Move: `src/elspeth/plugins/pooling/` → `src/elspeth/plugins/infrastructure/pooling/`

**Step 1: Move all 3 packages**

```bash
cd src/elspeth/plugins
git mv clients/ infrastructure/clients
git mv batching/ infrastructure/batching
git mv pooling/ infrastructure/pooling
```

**Do NOT commit yet** — continue to Task 3.

---

## Task 3: Move llm/ under transforms/

**Context:** The `llm/` package is a transform implementation (it subclasses BaseTransform). It belongs under `transforms/` per the SDA alignment principle.

**Files:**
- Move: `src/elspeth/plugins/llm/` → `src/elspeth/plugins/transforms/llm/`

**Step 1: Move the package**

```bash
cd src/elspeth/plugins
git mv llm/ transforms/llm
```

**Do NOT commit yet** — continue to Task 4.

---

## Task 4: Split azure/ into sources/, sinks/, infrastructure/

**Context:** The `azure/` folder currently mixes a source, a sink, and shared auth. Split it by SDA role: blob_source → sources, blob_sink → sinks, auth → infrastructure. Files are renamed to include the `azure_` prefix since they lose their directory context.

**Files:**
- Move: `src/elspeth/plugins/azure/blob_source.py` → `src/elspeth/plugins/sources/azure_blob_source.py`
- Move: `src/elspeth/plugins/azure/blob_sink.py` → `src/elspeth/plugins/sinks/azure_blob_sink.py`
- Move: `src/elspeth/plugins/azure/auth.py` → `src/elspeth/plugins/infrastructure/azure_auth.py`
- Delete: `src/elspeth/plugins/azure/__init__.py` and `src/elspeth/plugins/azure/` directory

**Step 1: Move the 3 files**

```bash
cd src/elspeth/plugins
git mv azure/blob_source.py sources/azure_blob_source.py
git mv azure/blob_sink.py sinks/azure_blob_sink.py
git mv azure/auth.py infrastructure/azure_auth.py
```

**Step 2: Remove the now-empty azure/ directory**

```bash
git rm src/elspeth/plugins/azure/__init__.py
# If azure/__pycache__/ exists, it's untracked and can be removed manually
rm -rf src/elspeth/plugins/azure/__pycache__
rmdir src/elspeth/plugins/azure 2>/dev/null || true
```

**Do NOT commit yet** — continue to Task 5.

---

## Task 5: Strip plugins/__init__.py

**Context:** The top-level `__init__.py` currently re-exports 30+ symbols. Per the design decision, it becomes a bare package marker. The census confirmed no external code uses `from elspeth.plugins import X` — all callers already use specific submodule paths.

**Files:**
- Modify: `src/elspeth/plugins/__init__.py`

**Step 1: Replace with bare package marker**

Write this content to `src/elspeth/plugins/__init__.py`:

```python
# src/elspeth/plugins/__init__.py
"""Plugin system: Sources, Transforms, Sinks via pluggy.

Subpackages:
- infrastructure/: Base classes, protocols, config, clients, batching, pooling
- sources/: Source plugin implementations (CSV, JSON, Azure Blob, etc.)
- sinks/: Sink plugin implementations (CSV, JSON, Database, Azure Blob, etc.)
- transforms/: Transform plugin implementations (field mapper, LLM, Azure safety, etc.)
"""
```

**Step 2: Commit all structural moves (Tasks 1-5)**

```bash
git add -A src/elspeth/plugins/
git commit -m "refactor: restructure plugins/ into sources/sinks/transforms/infrastructure

Move 11 root-level infrastructure files, 3 subsystem packages (clients,
batching, pooling), LLM transforms, and split azure/ by SDA role.

File moves only — imports not yet updated (next commit)."
```

---

## Task 6: Rewrite imports in plugins/infrastructure/ (internal cross-refs)

**Context:** ~130 import lines across ~25 files within the infrastructure package itself. These files reference each other and the moved subsystem packages. This is the highest-priority scope because infrastructure files are imported by everything else.

**Scope:** All `.py` files under `src/elspeth/plugins/infrastructure/` (including `clients/`, `batching/`, `pooling/`).

**Approach:** Mechanical find-replace of every `from elspeth.plugins.<old>` to `from elspeth.plugins.infrastructure.<new>` within these files. Also update `from elspeth.plugins.llm` → `from elspeth.plugins.transforms.llm` and `from elspeth.plugins.azure` → split paths.

**Files to modify (complete list):**

Infrastructure root:
- `infrastructure/__init__.py` — no imports to fix (bare)
- `infrastructure/base.py` — 2 imports: `results`, `schema_factory`
- `infrastructure/config_base.py` — 0 (imports from contracts only)
- `infrastructure/protocols.py` — 1 import: `results` (TYPE_CHECKING)
- `infrastructure/hookspecs.py` — 1 import: `protocols` (TYPE_CHECKING)
- `infrastructure/manager.py` — 4 imports: `hookspecs`, `protocols`, `validation`, `discovery`
- `infrastructure/discovery.py` — 2 imports: `base`, `hookspecs`; also update `PLUGIN_SCAN_CONFIG` paths and `EXCLUDED_FILES`
- `infrastructure/validation.py` — 8+ imports: `config_base`, azure source/sink configs, llm configs
- `infrastructure/schema_factory.py` — 0 (imports from contracts only)
- `infrastructure/results.py` — 0 (imports from contracts only)
- `infrastructure/sentinels.py` — 0
- `infrastructure/utils.py` — 1 import: `sentinels`
- `infrastructure/azure_auth.py` — 0 (check: may only import from Azure SDK)

Clients:
- `infrastructure/clients/__init__.py` — 5 imports: `clients.base`, `clients.http`, `clients.llm`, `clients.replayer`, `clients.verifier`; also docstring examples
- `infrastructure/clients/base.py` — 0 (imports from contracts/core only)
- `infrastructure/clients/http.py` — 1 import: `clients.base`
- `infrastructure/clients/llm.py` — 1 import: `clients.base`
- `infrastructure/clients/replayer.py` — check for internal imports
- `infrastructure/clients/verifier.py` — check for internal imports

Batching:
- `infrastructure/batching/__init__.py` — 3 imports: `batching.mixin`, `batching.ports`, `batching.row_reorder_buffer`
- `infrastructure/batching/mixin.py` — 2 imports: `batching.ports`, `batching.row_reorder_buffer`
- `infrastructure/batching/ports.py` — 0 (imports from contracts only)
- `infrastructure/batching/row_reorder_buffer.py` — 0

Pooling:
- `infrastructure/pooling/__init__.py` — 4 imports: `pooling.config`, `pooling.errors`, `pooling.executor`, `pooling.throttle`
- `infrastructure/pooling/config.py` — 1 import: `pooling.throttle`
- `infrastructure/pooling/executor.py` — 5 imports: `clients.llm`, `pooling.config`, `pooling.errors`, `pooling.reorder_buffer`, `pooling.throttle`
- `infrastructure/pooling/errors.py` — 0
- `infrastructure/pooling/reorder_buffer.py` — 0
- `infrastructure/pooling/throttle.py` — 0

**Replacement rules for this scope:**

```
from elspeth.plugins.base         → from elspeth.plugins.infrastructure.base
from elspeth.plugins.config_base  → from elspeth.plugins.infrastructure.config_base
from elspeth.plugins.protocols    → from elspeth.plugins.infrastructure.protocols
from elspeth.plugins.hookspecs    → from elspeth.plugins.infrastructure.hookspecs
from elspeth.plugins.manager      → from elspeth.plugins.infrastructure.manager
from elspeth.plugins.discovery    → from elspeth.plugins.infrastructure.discovery
from elspeth.plugins.validation   → from elspeth.plugins.infrastructure.validation
from elspeth.plugins.schema_factory → from elspeth.plugins.infrastructure.schema_factory
from elspeth.plugins.results      → from elspeth.plugins.infrastructure.results
from elspeth.plugins.sentinels    → from elspeth.plugins.infrastructure.sentinels
from elspeth.plugins.utils        → from elspeth.plugins.infrastructure.utils
from elspeth.plugins.clients      → from elspeth.plugins.infrastructure.clients
from elspeth.plugins.batching     → from elspeth.plugins.infrastructure.batching
from elspeth.plugins.pooling      → from elspeth.plugins.infrastructure.pooling
from elspeth.plugins.llm          → from elspeth.plugins.transforms.llm
from elspeth.plugins.azure.auth   → from elspeth.plugins.infrastructure.azure_auth
from elspeth.plugins.azure.blob_source → from elspeth.plugins.sources.azure_blob_source
from elspeth.plugins.azure.blob_sink   → from elspeth.plugins.sinks.azure_blob_sink
```

**Special: discovery.py updates beyond imports:**

1. Update `PLUGIN_SCAN_CONFIG` (line ~175):
```python
# Before
PLUGIN_SCAN_CONFIG: dict[str, list[str]] = {
    "sources": ["sources", "azure"],
    "transforms": ["transforms", "transforms/azure", "llm"],
    "sinks": ["sinks", "azure"],
}

# After — paths are relative to plugins/ root, NOT infrastructure/
PLUGIN_SCAN_CONFIG: dict[str, list[str]] = {
    "sources": ["sources"],
    "transforms": ["transforms", "transforms/azure", "transforms/llm"],
    "sinks": ["sinks"],
}
```

2. The `plugins_root` variable at line ~193 (`Path(__file__).parent`) now resolves to `infrastructure/`, but scan paths are relative to `plugins/`. Update to:
```python
plugins_root = Path(__file__).parent.parent  # Go up from infrastructure/ to plugins/
```

3. Update `EXCLUDED_FILES` if needed — remove entries for files no longer in scan paths (e.g., `auth.py` was only relevant for azure/ scanning).

**Special: validation.py deferred import updates:**

The validation module has deferred imports referencing old azure and llm paths. Update these:

```python
# Old
from elspeth.plugins.azure.blob_source import AzureBlobSourceConfig
from elspeth.plugins.azure.blob_sink import AzureBlobSinkConfig
from elspeth.plugins.llm.transform import _PROVIDERS
from elspeth.plugins.llm.base import LLMConfig
from elspeth.plugins.llm.azure_batch import AzureBatchConfig
from elspeth.plugins.llm.openrouter_batch import OpenRouterBatchConfig

# New
from elspeth.plugins.sources.azure_blob_source import AzureBlobSourceConfig
from elspeth.plugins.sinks.azure_blob_sink import AzureBlobSinkConfig
from elspeth.plugins.transforms.llm.transform import _PROVIDERS
from elspeth.plugins.transforms.llm.base import LLMConfig
from elspeth.plugins.transforms.llm.azure_batch import AzureBatchConfig
from elspeth.plugins.transforms.llm.openrouter_batch import OpenRouterBatchConfig
```

**Do NOT commit yet** — continue to next tasks.

---

## Task 7: Rewrite imports in plugins/sources/ and plugins/sinks/

**Context:** ~10 files in sources/ and sinks/ that import infrastructure modules. Mechanical replacement.

**Scope:** All `.py` files under `src/elspeth/plugins/sources/` and `src/elspeth/plugins/sinks/`.

**Files:**
- `sources/csv_source.py` — 3 imports: `base`, `config_base`, `schema_factory`
- `sources/json_source.py` — 3 imports: `base`, `config_base`, `schema_factory`
- `sources/null_source.py` — 1 import: `base`
- `sources/azure_blob_source.py` — 4 imports: `azure.auth` → `infrastructure.azure_auth`, `base`, `config_base`, `schema_factory`
- `sources/field_normalization.py` — check for imports
- `sinks/csv_sink.py` — 3 imports: `base`, `config_base`, `schema_factory`
- `sinks/json_sink.py` — 3 imports: `base`, `config_base`, `schema_factory`
- `sinks/database_sink.py` — 3 imports: `base`, `config_base`, `schema_factory`
- `sinks/azure_blob_sink.py` — 4 imports: `azure.auth` → `infrastructure.azure_auth`, `base`, `config_base`, `schema_factory`

**Replacement rules:** Same as Task 6 mapping table. All `from elspeth.plugins.base` → `from elspeth.plugins.infrastructure.base`, etc.

**Special for azure files:** The internal import `from elspeth.plugins.azure.auth import AzureAuthConfig` changes to `from elspeth.plugins.infrastructure.azure_auth import AzureAuthConfig`.

---

## Task 8: Rewrite imports in plugins/transforms/

**Context:** ~20 files under transforms/ including the llm/ and azure/ subfolders. The llm/ files heavily cross-reference each other (using `elspeth.plugins.llm.X`) — these all become `elspeth.plugins.transforms.llm.X`.

**Scope:** All `.py` files under `src/elspeth/plugins/transforms/` (including `azure/` and `llm/` subfolders).

**Files (transforms root):**
- `transforms/passthrough.py` — 3 imports
- `transforms/field_mapper.py` — 5 imports (includes `sentinels`, `utils`)
- `transforms/truncate.py` — 3 imports
- `transforms/keyword_filter.py` — 3 imports
- `transforms/json_explode.py` — 3 imports
- `transforms/batch_replicate.py` — 3 imports
- `transforms/batch_stats.py` — 3 imports
- `transforms/web_scrape.py` — 5 imports (includes `clients.http`, `schema_factory`)

**Files (transforms/azure/):**
- `transforms/azure/base.py` — 7 imports (includes `batching`, `pooling`, `clients.http`)
- `transforms/azure/content_safety.py` — 1 import: `results`
- `transforms/azure/prompt_shield.py` — 1 import: `results`

**Files (transforms/llm/ — heaviest scope):**
- `transforms/llm/__init__.py` — 3+ imports (internal refs change from `elspeth.plugins.llm.X` to `elspeth.plugins.transforms.llm.X`, plus `schema_factory`)
- `transforms/llm/base.py` — 3 imports: `config_base`, `llm.templates`, `pooling`
- `transforms/llm/transform.py` — 21 imports (!) — `base`, `batching`, `clients.llm`, `llm.*` (many), `pooling`, `schema_factory`
- `transforms/llm/azure_batch.py` — 8 imports
- `transforms/llm/openrouter_batch.py` — 10 imports
- `transforms/llm/multi_query.py` — 2 imports: `config_base`, `llm` (deferred)
- `transforms/llm/validation.py` — 2 imports: `llm.multi_query`, `llm.templates`
- `transforms/llm/langfuse.py` — 1 import: `llm.tracing`
- `transforms/llm/providers/azure.py` — 5 imports: `clients.llm`, `llm.base`, `llm.provider`, `llm.tracing`, `clients.base`
- `transforms/llm/providers/openrouter.py` — 6 imports: `clients.http`, `clients.llm`, `llm.base`, `llm.provider`, `llm.validation`, `clients.base`

**Replacement rules:** Same mapping table. For llm internal refs, the key change is:
```
from elspeth.plugins.llm.X → from elspeth.plugins.transforms.llm.X
```

---

## Task 9: Rewrite imports in engine/

**Context:** 19 import lines across 8 files. Clean boundary — mostly `protocols`, `results`, one each for `clients.llm`, `pooling`, `batching.mixin`.

**Scope:** All `.py` files under `src/elspeth/engine/`.

**Files:**
- `engine/dag_navigator.py` — 1 import: `protocols`
- `engine/processor.py` — 3 imports: `clients.llm`, `pooling`, `protocols`
- `engine/executors/transform.py` — 3 imports: `batching.mixin`, `protocols`, `results`
- `engine/executors/types.py` — 1 import: `results`
- `engine/executors/gate.py` — 1 import: `results`
- `engine/executors/sink.py` — 1 import: `protocols`
- `engine/executors/aggregation.py` — 2 imports: `protocols`, `results`
- `engine/orchestrator/core.py` — 1 import: `protocols`
- `engine/orchestrator/types.py` — 2 imports: `protocols` (TYPE_CHECKING)
- `engine/orchestrator/export.py` — 1 import: `protocols` (TYPE_CHECKING)
- `engine/orchestrator/validation.py` — 1 import: `protocols` (TYPE_CHECKING)
- `engine/orchestrator/aggregation.py` — 1-2 imports: `protocols` (TYPE_CHECKING)

**Replacement rules:** Same mapping table.

---

## Task 10: Rewrite imports in core/, cli*, testing/

**Context:** 12 import lines across 7 files. Very light touch.

**Scope:**
- `src/elspeth/core/dag/models.py` — 1 TYPE_CHECKING import: `protocols`
- `src/elspeth/core/dag/builder.py` — 1 TYPE_CHECKING import: `protocols`
- `src/elspeth/core/dag/graph.py` — 1 TYPE_CHECKING import: `protocols`
- `src/elspeth/cli.py` — 4 imports: `manager` (×2 TYPE_CHECKING), `protocols` (TYPE_CHECKING), `discovery`
- `src/elspeth/cli_helpers.py` — 1 TYPE_CHECKING import: `protocols`
- `src/elspeth/testing/__init__.py` — 4 imports: `results` (TYPE_CHECKING)

**Replacement rules:** Same mapping table.

---

## Task 11: Rewrite imports in tests/unit/

**Context:** The largest scope — 593 import lines across 117 files. All mechanical replacements using the same mapping table.

**Scope:** All `.py` files under `tests/unit/`.

**Approach:** This is the primary target for the parallel agent swarm. Split into sub-scopes by test subdirectory:

- `tests/unit/plugins/` (~70 files) — heaviest; includes llm, transforms, sources, sinks, batching, pooling, clients tests
- `tests/unit/engine/` (~25 files) — executor and orchestrator tests
- `tests/unit/core/` (~15 files) — DAG and config tests
- `tests/unit/contracts/` (~5 files) — minimal
- `tests/unit/` root conftest and other files (~2 files)

**Replacement rules:** Same mapping table. Most common patterns:
```
from elspeth.plugins.base import BaseTransform → from elspeth.plugins.infrastructure.base import BaseTransform
from elspeth.plugins.config_base import TransformDataConfig → from elspeth.plugins.infrastructure.config_base import TransformDataConfig
from elspeth.plugins.results import TransformResult → from elspeth.plugins.infrastructure.results import TransformResult
from elspeth.plugins.protocols import TransformProtocol → from elspeth.plugins.infrastructure.protocols import TransformProtocol
from elspeth.plugins.schema_factory import create_schema_from_config → from elspeth.plugins.infrastructure.schema_factory import create_schema_from_config
from elspeth.plugins.llm.transform import LLMTransform → from elspeth.plugins.transforms.llm.transform import LLMTransform
```

---

## Task 12: Rewrite imports in tests/integration/, e2e/, property/, performance/

**Context:** ~85 import lines across 33 files. Same mechanical replacements.

**Scope:**
- `tests/integration/` — 40 import lines, 17 files
- `tests/e2e/` — 11 import lines, 5 files
- `tests/property/` — 15 import lines, 10 files
- `tests/performance/` — 1 import line, 1 file

**Replacement rules:** Same mapping table.

---

## Task 13: Update config files, docs, and project metadata

**Context:** Several non-Python files reference plugin paths as strings and need updating.

**Files:**
- `config/cicd/enforce_tier_model/plugins.yaml` — ~40 file path entries and 3 wildcard patterns
- `config/cicd/contracts-whitelist.yaml` — ~80 path-string references (if this file exists)
- `pyproject.toml` — 1 entry: `"src/elspeth/plugins/__init__.py" = ["RUF022"]`
- `CLAUDE.md` — Source Layout section showing plugins/ structure

**Step 1: Update enforce_tier_model/plugins.yaml**

Update all path prefixes. Key changes:
```
plugins/batching/    → plugins/infrastructure/batching/
plugins/discovery.py → plugins/infrastructure/discovery.py
plugins/utils.py     → plugins/infrastructure/utils.py
plugins/config_base.py → plugins/infrastructure/config_base.py
plugins/clients/     → plugins/infrastructure/clients/
plugins/pooling/     → plugins/infrastructure/pooling/
plugins/llm/*        → plugins/transforms/llm/*
plugins/azure/*      → split (sources/azure_blob_source, sinks/azure_blob_sink, infrastructure/azure_auth)
plugins/sources/*    → plugins/sources/* (unchanged)
plugins/sinks/*      → plugins/sinks/* (unchanged)
plugins/transforms/* → plugins/transforms/* (unchanged)
```

**Step 2: Update pyproject.toml**

The `__init__.py` is now a bare file. The RUF022 suppression for unsorted `__all__` is no longer needed since there's no `__all__`. Remove the line:
```toml
# Remove this line:
"src/elspeth/plugins/__init__.py" = ["RUF022"]
```

**Step 3: Update CLAUDE.md Source Layout**

Update the `Source Layout` section (in the `## Source Layout` heading) to reflect the new plugins/ structure:
```
├── plugins/
│   ├── infrastructure/ # Shared: base classes, protocols, config, clients, batching, pooling
│   ├── sources/        # CSVSource, JSONSource, NullSource, AzureBlobSource
│   ├── transforms/     # FieldMapper, Passthrough, Truncate, LLM, Azure safety, etc.
│   └── sinks/          # CSVSink, JSONSink, DatabaseSink, AzureBlobSink
```

---

## Task 14: Commit all import rewrites

**Context:** After Tasks 6-13, all imports are updated. Create a single commit.

**Step 1: Stage and commit**

```bash
git add -A
git commit -m "refactor: update all imports for plugins/ restructure

Mechanical import rewriting across ~200 files:
- elspeth.plugins.base → elspeth.plugins.infrastructure.base
- elspeth.plugins.llm → elspeth.plugins.transforms.llm
- elspeth.plugins.azure split across sources/sinks/infrastructure
- Updated discovery.py PLUGIN_SCAN_CONFIG paths
- Updated tier model allowlist file paths
- Updated CLAUDE.md source layout
- Stripped plugins/__init__.py to bare package marker"
```

---

## Task 15: Verification — lint and type check

**Context:** Run ruff and mypy to catch any import path typos or missing modules.

**Step 1: Run ruff**

```bash
.venv/bin/python -m ruff check src/
```

Expected: 0 errors. If errors found, fix and re-run.

**Step 2: Run mypy**

```bash
.venv/bin/python -m mypy src/
```

Expected: 0 errors (beyond any pre-existing). If new errors found, fix and re-run.

---

## Task 16: Verification — unit tests

**Step 1: Run unit tests**

```bash
.venv/bin/python -m pytest tests/unit/ -x --timeout=60
```

Expected: All pass. If failures, they're import path issues — fix and re-run.

---

## Task 17: Verification — integration + property + e2e tests

**Step 1: Run remaining test suites**

```bash
.venv/bin/python -m pytest tests/integration/ tests/property/ tests/e2e/ -x --timeout=120
```

Expected: All pass (minus any pre-existing skips/xfails).

---

## Task 18: Verification — CI checks

**Step 1: Tier model enforcer**

```bash
.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model
```

Expected: Pass (all allowlist paths updated in Task 13).

**Step 2: Config contracts**

```bash
.venv/bin/python -m scripts.check_contracts
```

Expected: Pass.

**Step 3: Stale import grep**

```bash
# These should all return 0 matches (excluding this plan doc and the design doc)
grep -rn "from elspeth\.plugins\.base " src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.config_base " src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.protocols " src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.results " src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.clients\." src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.batching" src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.pooling" src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.llm" src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.azure" src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.hookspecs" src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.manager " src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.discovery " src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.validation " src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.schema_factory " src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.sentinels " src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins\.utils " src/ tests/ --include="*.py" | grep -v __pycache__
grep -rn "from elspeth\.plugins import " src/ tests/ --include="*.py" | grep -v __pycache__
```

Expected: 0 matches for each.

---

## Task 19: Final commit if verification fixes needed

If any fixes were needed during Tasks 15-18, commit them:

```bash
git add -A
git commit -m "fix: resolve import issues from plugins/ restructure verification"
```

---

## Swarm Execution Strategy

Tasks 1-5 are sequential (primary agent, one commit).

Tasks 6-13 are parallelizable via agent swarm:
- **Agent 1:** Task 6 (infrastructure/ internal)
- **Agent 2:** Task 7 (sources/ + sinks/)
- **Agent 3:** Task 8 (transforms/ including llm/)
- **Agent 4:** Task 9 (engine/)
- **Agent 5:** Task 10 (core/ + cli* + testing/)
- **Agent 6:** Task 11 sub-scope: `tests/unit/plugins/`
- **Agent 7:** Task 11 sub-scope: `tests/unit/engine/` + `tests/unit/core/` + `tests/unit/contracts/`
- **Agent 8:** Task 12 (integration + e2e + property + performance tests)
- **Agent 9:** Task 13 (config files + docs)

Tasks 14-18 are sequential (commit, then verify).

Tasks 15-18 verification checks can be parallelized via a second swarm.
