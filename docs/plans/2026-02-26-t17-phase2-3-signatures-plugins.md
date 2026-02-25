# T17 Phase 2-3: Update Plugin Signatures & Implementations

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Narrow all plugin method signatures from `PluginContext` to the appropriate phase-based protocol type.

**Architecture:** Update plugin protocols (`plugins/protocols.py`), base classes (`plugins/base.py`), and all concrete plugin implementations. Each plugin's `process()`/`load()`/`write()` accepts its phase-specific context, and `on_start()`/`on_complete()` accept `LifecycleContext`.

**Tech Stack:** Protocol type annotations, mypy strict mode for verification

**Prerequisite:** Phase 1 complete (protocols defined and tested)

---

## Task 1: Update plugin protocols (`plugins/protocols.py`)

**Files:**
- Modify: `src/elspeth/plugins/protocols.py`

**Step 1: Add imports**

At the top of `src/elspeth/plugins/protocols.py`, add to the TYPE_CHECKING block:

```python
if TYPE_CHECKING:
    from elspeth.contracts.contexts import LifecycleContext, SinkContext, SourceContext, TransformContext
    # Keep existing PluginContext import for backwards reference if needed
    from elspeth.contracts.plugin_context import PluginContext
```

**Step 2: Update SourceProtocol signatures**

Change these method signatures in `SourceProtocol`:

```python
# Line 84: load()
def load(self, ctx: "SourceContext") -> Iterator["SourceRow"]: ...

# Line 106: on_start()
def on_start(self, ctx: "LifecycleContext") -> None: ...

# Line 110: on_complete()
def on_complete(self, ctx: "SourceContext") -> None: ...
```

**Step 3: Update TransformProtocol signatures**

```python
# Line 232-236: process()
def process(
    self,
    row: "PipelineRow",
    ctx: "TransformContext",
) -> "TransformResult": ...

# Line 258: on_start()
def on_start(self, ctx: "LifecycleContext") -> None: ...

# Line 262: on_complete()
def on_complete(self, ctx: "TransformContext") -> None: ...
```

**Step 4: Update BatchTransformProtocol signatures**

```python
# Line 343-346: process()
def process(
    self,
    rows: list["PipelineRow"],
    ctx: "TransformContext",
) -> "TransformResult": ...

# Line 365: on_start()
def on_start(self, ctx: "LifecycleContext") -> None: ...

# Line 369: on_complete()
def on_complete(self, ctx: "TransformContext") -> None: ...
```

**Step 5: Update SinkProtocol signatures**

```python
# Line 461-464: write()
def write(
    self,
    rows: list[dict[str, Any]],
    ctx: "SinkContext",
) -> "ArtifactDescriptor": ...

# Line 507: on_start()
def on_start(self, ctx: "LifecycleContext") -> None: ...

# Line 511: on_complete()
def on_complete(self, ctx: "SinkContext") -> None: ...
```

**Step 6: Run mypy on just this file**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/protocols.py`
Expected: Clean (protocol definitions don't need concrete class compatibility yet)

---

## Task 2: Update base classes (`plugins/base.py`)

**Files:**
- Modify: `src/elspeth/plugins/base.py`

**Step 1: Update imports**

Replace the PluginContext import (line 45):

```python
# Old:
from elspeth.contracts.plugin_context import PluginContext

# New:
from elspeth.contracts.contexts import LifecycleContext, SinkContext, SourceContext, TransformContext
from elspeth.contracts.plugin_context import PluginContext  # Keep for engine-facing code
```

**Step 2: Update BaseTransform signatures**

```python
# Line 226-229: process()
def process(
    self,
    row: PipelineRow,
    ctx: TransformContext,
) -> TransformResult:

# Line 281: on_start()
def on_start(self, ctx: LifecycleContext) -> None:

# Line 294: on_complete()
def on_complete(self, ctx: LifecycleContext) -> None:
```

Note: `on_start()` and `on_complete()` both use `LifecycleContext` on `BaseTransform` because the base `on_start()` only sets `self._on_start_called = True` (no field access), and `on_complete()` is an empty hook. Subclasses that override these will access LifecycleContext fields.

**Step 3: Update BaseSink signatures**

```python
# Line 449-452: write()
def write(
    self,
    rows: list[dict[str, Any]],
    ctx: SinkContext,
) -> ArtifactDescriptor:

# Line 506: on_start()
def on_start(self, ctx: LifecycleContext) -> None:

# Line 515: on_complete()
def on_complete(self, ctx: LifecycleContext) -> None:
```

**Step 4: Update BaseSource signatures**

```python
# Line 598: load()
def load(self, ctx: SourceContext) -> Iterator[SourceRow]:

# Line 649: on_start()
def on_start(self, ctx: LifecycleContext) -> None:

# Line 660: on_complete()
def on_complete(self, ctx: LifecycleContext) -> None:
```

**Step 5: Update docstrings and examples**

Update the class docstrings and code examples that reference `PluginContext` in method signatures to use the new protocol types.

**Step 6: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/base.py src/elspeth/plugins/protocols.py`
Expected: Clean (or may show errors in concrete plugins that still use PluginContext — those are fixed next)

---

## Task 3: Update source plugins (4 files)

**Files:**
- Modify: `src/elspeth/plugins/sources/csv_source.py:105`
- Modify: `src/elspeth/plugins/sources/json_source.py:144`
- Modify: `src/elspeth/plugins/sources/null_source.py:75`
- Modify: `src/elspeth/plugins/azure/blob_source.py:383`

**Step 1: Update imports in each file**

In each source file, replace:
```python
from elspeth.contracts.plugin_context import PluginContext
```
with:
```python
from elspeth.contracts.contexts import LifecycleContext, SourceContext
```

If the file uses `PluginContext` in TYPE_CHECKING, update there too.

**Step 2: Update method signatures**

For each source file, change:
- `def load(self, ctx: PluginContext)` → `def load(self, ctx: SourceContext)`
- `def on_start(self, ctx: PluginContext)` → `def on_start(self, ctx: LifecycleContext)`
- `def on_complete(self, ctx: PluginContext)` → `def on_complete(self, ctx: LifecycleContext)`

Also update any internal helper methods that pass ctx:
- `csv_source.py`: `_load_from_file(self, ..., ctx: SourceContext)` and any ctx-accepting helpers
- `json_source.py`: `_load_jsonl`, `_load_json_array`, `_validate_and_yield` — all accept ctx
- `blob_source.py`: `_load_csv`, `_load_json_array`, `_load_jsonl`, `_validate_and_yield`

**Step 3: Run tests for sources**

Run: `.venv/bin/python -m pytest tests/unit/plugins/sources/ tests/integration/plugins/sources/ -v --timeout=60`
Expected: All pass

**Step 4: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/sources/ src/elspeth/plugins/azure/blob_source.py`
Expected: Clean

---

## Task 4: Update simple transform plugins (5 files)

**Files:**
- Modify: `src/elspeth/plugins/transforms/passthrough.py:58`
- Modify: `src/elspeth/plugins/transforms/field_mapper.py:101`
- Modify: `src/elspeth/plugins/transforms/truncate.py:88`
- Modify: `src/elspeth/plugins/transforms/json_explode.py:123`
- Modify: `src/elspeth/plugins/transforms/keyword_filter.py`

**Step 1: Update imports in each file**

Replace `PluginContext` import with:
```python
from elspeth.contracts.contexts import TransformContext
```

These files don't have `on_start`/`on_complete` overrides, so no `LifecycleContext` needed.

**Step 2: Update method signatures**

For each file, change:
- `def process(self, row: PipelineRow, ctx: PluginContext)` → `def process(self, row: PipelineRow, ctx: TransformContext)`

These transforms don't access ctx at all, so this is purely a signature change.

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/ -v --timeout=60 -k "passthrough or field_mapper or truncate or json_explode or keyword"`
Expected: All pass

**Step 4: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/transforms/passthrough.py src/elspeth/plugins/transforms/field_mapper.py src/elspeth/plugins/transforms/truncate.py src/elspeth/plugins/transforms/json_explode.py src/elspeth/plugins/transforms/keyword_filter.py`
Expected: Clean

---

## Task 5: Update complex transforms (3 files)

**Files:**
- Modify: `src/elspeth/plugins/transforms/web_scrape.py:180`
- Modify: `src/elspeth/plugins/transforms/azure/prompt_shield.py:175,213`
- Modify: `src/elspeth/plugins/transforms/azure/content_safety.py:204,242`

**Step 1: Update imports**

Replace `PluginContext` import with:
```python
from elspeth.contracts.contexts import LifecycleContext, TransformContext
```

**Step 2: Update method signatures**

For `web_scrape.py`:
- `def process(self, row: PipelineRow, ctx: PluginContext)` → `ctx: TransformContext`
- Internal `_fetch_url` and other ctx-accepting helpers: `ctx: TransformContext`
- If `on_start`/`on_complete` exist: `ctx: LifecycleContext`

For `prompt_shield.py`:
- `def on_start(self, ctx: PluginContext)` → `ctx: LifecycleContext`
- `def accept(self, row: PipelineRow, ctx: PluginContext)` → `ctx: TransformContext`
- Internal `_do_work` and helpers: `ctx: TransformContext`

For `content_safety.py`:
- Same pattern as prompt_shield

**Step 3: Handle cross-protocol access**

These transforms access `ctx.landscape`, `ctx.rate_limit_registry`, etc. in `on_start()` and store them as instance vars. Verify that:
- `on_start()` only accesses fields in `LifecycleContext`
- `process()`/`accept()` only accesses fields in `TransformContext`

If a method needs fields from both, it should capture them in `on_start()` (LifecycleContext) and use the captured instance vars in `process()` (TransformContext).

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/ -v --timeout=60 -k "web_scrape or prompt_shield or content_safety"`
Expected: All pass

**Step 5: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/transforms/web_scrape.py src/elspeth/plugins/transforms/azure/`
Expected: Clean

---

## Task 6: Update LLM transforms (3 files)

**Files:**
- Modify: `src/elspeth/plugins/llm/transform.py:633,677,683`
- Modify: `src/elspeth/plugins/llm/openrouter_batch.py:242`
- Modify: `src/elspeth/plugins/llm/azure_batch.py:224`

**Step 1: Update imports**

In each LLM transform file, replace PluginContext import with:
```python
from elspeth.contracts.contexts import LifecycleContext, TransformContext
```

**Step 2: Update method signatures**

For `transform.py` (LLMTransform):
- `def on_start(self, ctx: PluginContext)` → `ctx: LifecycleContext`
- `def accept(self, row: PipelineRow, ctx: PluginContext)` → `ctx: TransformContext`
- `def process(self, row: PipelineRow, ctx: PluginContext)` → `ctx: TransformContext`
- Internal methods `_single_query_process`, `_multi_query_process`, `_process_row`: `ctx: TransformContext`

For `openrouter_batch.py`:
- `def on_start(self, ctx: PluginContext)` → `ctx: LifecycleContext`
- Internal methods that accept ctx: verify which protocol each needs

For `azure_batch.py`:
- `def on_start(self, ctx: PluginContext)` → `ctx: LifecycleContext`
- Checkpoint methods access `ctx.get_checkpoint()`, `ctx.set_checkpoint()`, `ctx.clear_checkpoint()` — these are in `TransformContext`, so process-time methods need `TransformContext`
- Internal methods that accept ctx: verify which protocol each needs

**Step 3: Handle LLM-specific patterns**

LLM transforms capture infrastructure in `on_start()`:
```python
def on_start(self, ctx: LifecycleContext) -> None:
    self._recorder = ctx.landscape
    self._run_id = ctx.run_id
    self._telemetry_emit = ctx.telemetry_emit
    self._limiter = ctx.rate_limit_registry
```

Then in `process()` they use `ctx.state_id`, `ctx.token` (TransformContext) plus the captured instance vars. This pattern works naturally with the split.

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/ -v --timeout=120`
Expected: All pass

**Step 5: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/llm/`
Expected: Clean

---

## Task 7: Update sink plugins (4 files)

**Files:**
- Modify: `src/elspeth/plugins/sinks/csv_sink.py:219,623,632`
- Modify: `src/elspeth/plugins/sinks/json_sink.py:249,580,589`
- Modify: `src/elspeth/plugins/sinks/database_sink.py:416,546,550`
- Modify: `src/elspeth/plugins/azure/blob_sink.py:547,701,705`

**Step 1: Update imports**

In each sink file, replace PluginContext import with:
```python
from elspeth.contracts.contexts import LifecycleContext, SinkContext
```

**Step 2: Update method signatures**

For each sink:
- `def write(self, rows: ..., ctx: PluginContext)` → `ctx: SinkContext`
- `def on_start(self, ctx: PluginContext)` → `ctx: LifecycleContext`
- `def on_complete(self, ctx: PluginContext)` → `ctx: LifecycleContext`
- Internal helpers that accept ctx: use `SinkContext` for write-time, `LifecycleContext` for lifecycle

Specific files:
- `csv_sink.py`: `_resolve_contract`, `_resolve_display_headers` helpers accept ctx — use `SinkContext`
- `json_sink.py`: Same pattern as csv_sink
- `database_sink.py`: `_ensure_table`, `_drop_table` helpers accept ctx
- `blob_sink.py`: `_render_blob_path`, `_get_or_init` helpers accept ctx

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/sinks/ tests/integration/plugins/sinks/ -v --timeout=60`
Expected: All pass

**Step 4: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/sinks/ src/elspeth/plugins/azure/blob_sink.py`
Expected: Clean

---

## Task 8: Update batching infrastructure

**Files:**
- Modify: `src/elspeth/plugins/batching/mixin.py`

**Step 1: Update imports**

Replace PluginContext TYPE_CHECKING import with:
```python
from elspeth.contracts.contexts import TransformContext
```

**Step 2: Update method signatures**

- `accept_row(self, row, ctx: TransformContext, ...)` (line 173)
- Any internal methods that pass ctx: use `TransformContext`

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/ -v --timeout=60 -k "batch"'
Expected: All pass

**Step 4: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/batching/`
Expected: Clean

---

## Task 9: Commit Phase 2-3

**Step 1: Commit**

```bash
git add src/elspeth/plugins/ src/elspeth/contracts/
git commit -m "refactor(T17): Phase 2-3 — narrow all plugin signatures to phase-based protocols

Update SourceProtocol/TransformProtocol/SinkProtocol and all base classes
to accept SourceContext/TransformContext/SinkContext/LifecycleContext instead
of PluginContext. Update all 19 concrete plugin implementations.

process()/write()/load() accept per-phase context.
on_start()/on_complete() accept LifecycleContext."
```

**Step 2: Full verification**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q && .venv/bin/python -m mypy src/ && .venv/bin/python -m ruff check src/ && .venv/bin/python -m scripts.check_contracts`
Expected: All pass
