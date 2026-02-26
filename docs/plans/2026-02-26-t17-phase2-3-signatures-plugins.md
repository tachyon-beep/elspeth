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
def on_complete(self, ctx: "LifecycleContext") -> None: ...
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
def on_complete(self, ctx: "LifecycleContext") -> None: ...
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
def on_complete(self, ctx: "LifecycleContext") -> None: ...
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
def on_complete(self, ctx: "LifecycleContext") -> None: ...
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

> **[N9] Note:** Source plugin line numbers below were not verified by the Reality Checker.
> These are edit guidance for where `load()` is defined. Spot-check before executing.

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

## Task 4: Update simple transform plugins (7 files)

**Files:**
- Modify: `src/elspeth/plugins/transforms/passthrough.py:58`
- Modify: `src/elspeth/plugins/transforms/field_mapper.py:101`
- Modify: `src/elspeth/plugins/transforms/truncate.py:88`
- Modify: `src/elspeth/plugins/transforms/json_explode.py:123`
- Modify: `src/elspeth/plugins/transforms/keyword_filter.py`
- Modify: `src/elspeth/plugins/transforms/batch_stats.py:88`
- Modify: `src/elspeth/plugins/transforms/batch_replicate.py:118`

**Step 1: Update imports in each file**

Replace `PluginContext` import with:
```python
from elspeth.contracts.contexts import TransformContext
```

These files don't have `on_start`/`on_complete` overrides, so no `LifecycleContext` needed.

Note: `batch_stats.py` and `batch_replicate.py` are batch-aware transforms (accept `rows: list[PipelineRow]` not `row: PipelineRow`) but follow the same simple import pattern.

**Step 2: Update method signatures**

For each row-transform file, change:
- `def process(self, row: PipelineRow, ctx: PluginContext)` → `def process(self, row: PipelineRow, ctx: TransformContext)`

For each batch-transform file, change:
- `def process(self, rows: list[PipelineRow], ctx: PluginContext)` → `def process(self, rows: list[PipelineRow], ctx: TransformContext)`

These transforms don't access ctx at all (or minimally), so this is purely a signature change.

**Step 3: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/plugins/transforms/ -v --timeout=60 -k "passthrough or field_mapper or truncate or json_explode or keyword or batch_stats or batch_replicate"`
Expected: All pass

**Step 4: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/transforms/passthrough.py src/elspeth/plugins/transforms/field_mapper.py src/elspeth/plugins/transforms/truncate.py src/elspeth/plugins/transforms/json_explode.py src/elspeth/plugins/transforms/keyword_filter.py src/elspeth/plugins/transforms/batch_stats.py src/elspeth/plugins/transforms/batch_replicate.py`
Expected: Clean

---

## Task 4a: Sub-checkpoint commit (simple transforms)

> **[W3] Review amendment:** Simple transforms (Task 4) are independently committable from the complex
> transforms (Tasks 5-6). Committing here reduces blast radius if the complex transform work stalls.
> Phase 2-3 is the largest single phase (19 plugin files) and has the highest stall risk. **[N10]**

**Step 1: Commit simple transforms checkpoint**

```bash
git add src/elspeth/plugins/transforms/passthrough.py src/elspeth/plugins/transforms/field_mapper.py src/elspeth/plugins/transforms/truncate.py src/elspeth/plugins/transforms/json_explode.py src/elspeth/plugins/transforms/keyword_filter.py src/elspeth/plugins/transforms/batch_stats.py src/elspeth/plugins/transforms/batch_replicate.py
git commit -m "refactor(T17): Phase 2-3 checkpoint — narrow simple transform signatures

Update 7 simple transform plugins to accept TransformContext instead of
PluginContext. Signature-only changes, no logic modifications."
```

**Step 2: Run quality gate**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q && .venv/bin/python -m mypy src/`
Expected: All pass

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

**Step 3a: Audit tests before removing defensive fallbacks**

> **[W1] Review amendment:** Before removing the fallbacks, identify tests that call `process()`/`accept()`
> without first calling `on_start()`. These tests currently pass because the fallback silently sets
> `self._recorder = ctx.landscape`. After removal, they will crash with `AttributeError`.

Run: `grep -rn "_recorder\|on_start" tests/unit/plugins/transforms/azure/ --include='*.py'`

Identify any test that:
1. Creates a `PromptShieldTransform` or `ContentSafetyTransform`
2. Calls `process()`/`accept()` directly
3. Does NOT call `on_start()` first

Update those tests to call `on_start(ctx)` with a properly configured `PluginContext` before calling `process()`/`accept()`.

**Step 3b: Remove defensive fallbacks in prompt_shield.py and content_safety.py**

Both `prompt_shield.py` and `content_safety.py` have defensive fallback patterns in `accept()` / `process()` like:
```python
if self._recorder is None and ctx.landscape is not None:
    self._recorder = ctx.landscape
```
These violate CLAUDE.md's prohibition on defensive programming (system-owned code should crash, not silently recover). Under `TransformContext`, `ctx.landscape` is not available — which makes these fallbacks both prohibited and impossible. **Remove these fallback blocks.** If `on_start()` wasn't called, that's a bug in the engine — let it crash.

**Step 3c: Refactor web_scrape.py infrastructure access**

`web_scrape.py` is unique: its `process()` method reads infrastructure fields (`ctx.landscape`, `ctx.rate_limit_registry`) that are NOT in `TransformContext`. This must be refactored before the signature can be narrowed:

> **[N3] Behavioral change note:** This refactoring moves crash detection from row-processing time to
> run-start time. Previously, a misconfigured transform would crash when the first row arrived.
> After this change, it crashes at `on_start()`. This is strictly better (fail-fast), but verify
> that existing web_scrape integration tests cover the `on_start()` path, not just `process()`.

> **[R6] Pre-existing issue:** Neither `PluginContext` construction at `orchestrator/core.py:1205` nor
> `:2180` passes `payload_store`. The `PluginContext` field defaults to `None`. If `web_scrape`
> requires `payload_store is not None`, the crash will now surface at `on_start()` rather than mid-row.
> Confirm whether `payload_store` should be wired to `PluginContext` before executing this step.

1. Add `on_start()` override to `WebScrapeTransform` that captures infrastructure:
   ```python
   def on_start(self, ctx: LifecycleContext) -> None:
       super().on_start(ctx)
       self._recorder = ctx.landscape
       self._limiter = ctx.rate_limit_registry
       self._telemetry_emit = ctx.telemetry_emit
       self._payload_store = ctx.payload_store
   ```
   The existing code crashes if `ctx.rate_limit_registry is None` or `ctx.landscape is None` (lines 297-300). Replicate these crash-if-None assertions in `on_start()` so bugs surface early, not when the first row arrives.
2. Before removing `ctx.landscape`/`ctx.rate_limit_registry`/`ctx.telemetry_emit`/`ctx.payload_store` from `process()`, audit web_scrape tests:
   ```bash
   grep -rn "on_start\|WebScrape" tests/ --include='*.py' | grep -v '__pycache__'
   ```
   Update any test that calls `process()` without `on_start()` to go through the lifecycle.
3. Update `process()` and internal helpers (`_fetch_url` at line 283, etc.) to use `self._recorder`, `self._limiter`, `self._telemetry_emit`, and `self._payload_store` instead of `ctx.landscape`, `ctx.rate_limit_registry`, `ctx.telemetry_emit`, `ctx.payload_store`. Note: `_fetch_url` also accesses `ctx.state_id`, `ctx.run_id`, and `ctx.token` — these ARE in `TransformContext` and should remain as `ctx.X`.
4. Then narrow `process()` to `ctx: TransformContext`

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
- **`LLMQueryStrategy` protocol** (line 80): `def execute(self, ..., ctx: PluginContext)` → `ctx: TransformContext`
- **`SingleQueryStrategy.execute()`** (line 102): `ctx: TransformContext`
- **`MultiQueryStrategy.execute()`** (line 256): `ctx: TransformContext`

> **[N8] Note:** `LLMQueryStrategy` protocol line numbers (80, 102, 256) were not verified by the Reality
> Checker. Spot-check before executing. Low risk — if wrong, the correct locations are nearby.

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
- `json_sink.py`: Same pattern as csv_sink (`_resolve_display_headers` at ~line 533 accesses `ctx.landscape`)
- `database_sink.py`: `_ensure_table`, `_drop_table` helpers accept ctx
- `blob_sink.py`: `_render_blob_path`, `_get_or_init`, **`_resolve_display_headers_if_needed`** helpers accept ctx
  > **[W2] Review amendment:** `_resolve_display_headers_if_needed` (at ~line 524) accesses `ctx.landscape`
  > and was missing from the original helper list. Must be narrowed to `SinkContext`. mypy will catch this
  > if missed, but naming it explicitly prevents confusion during mechanical execution.

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

- `accept(self, row, ctx: TransformContext, ...)` abstract method (line 103)
- `accept_row(self, row, ctx: TransformContext, ...)` (line 173)
- `Callable[[PipelineRow, PluginContext], TransformResult]` type annotations at lines 177 and 226 → `Callable[[PipelineRow, TransformContext], TransformResult]`
- `_process_and_complete()` and any internal methods that pass ctx: use `TransformContext`

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

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120 -q && .venv/bin/python -m mypy src/ && .venv/bin/python -m ruff check src/ && .venv/bin/python -m scripts.check_contracts && .venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model`
Expected: All pass
