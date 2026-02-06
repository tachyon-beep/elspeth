# Analysis: src/elspeth/plugins/llm/openrouter_batch.py

**Lines:** 783
**Role:** OpenRouter batch LLM transform. Collects rows into batches (via aggregation engine) and sends them to OpenRouter's batch API in parallel via ThreadPoolExecutor. Handles per-row template rendering, HTTP calls, JSON response parsing, and Langfuse tracing.
**Key dependencies:** Imports from `httpx`, `concurrent.futures`, `elspeth.plugins.llm.base.LLMConfig`, `elspeth.plugins.llm.templates`, `elspeth.plugins.llm.tracing`, `elspeth.plugins.pooling`, `elspeth.contracts`, `elspeth.plugins.base.BaseTransform`, `elspeth.plugins.context.PluginContext`. Consumed by the plugin manager; no other modules import from it directly.
**Analysis depth:** FULL

## Summary
The file is well-structured with clear adherence to the Three-Tier Trust Model. Error handling at the external boundary (OpenRouter API) is thorough. However, there are several issues: a thread-safety problem with `ctx.record_call()` being invoked from worker threads; the `_record_langfuse_trace` method has a Langfuse context manager threading concern; the contract inference from the first output row is fragile; and the `_on_error` field from config is stored but never referenced by this class. The code is production-viable but needs attention on the concurrency concerns.

## Critical Findings

### [540-555] ctx.record_call() invoked from worker threads without thread-safety guarantee

**What:** `_process_single_row` is called within a `ThreadPoolExecutor` (line 442), and it calls `ctx.record_call()` (lines 540, 593, 651, 671, 693, 707, 727). `PluginContext.record_call()` delegates to `self.landscape.allocate_call_index(self.state_id)` which uses an internal counter. If the `PluginContext` instance is shared across worker threads (a single `ctx` is captured in the closure on line 442), all workers share the same `state_id`, and the call_index allocator may produce duplicate indices or corrupt state depending on whether `LandscapeRecorder.allocate_call_index()` is thread-safe.

**Why it matters:** If call_index allocation is not thread-safe, the `UNIQUE(state_id, call_index)` constraint in the audit database will be violated, causing `IntegrityError` exceptions that crash individual row processing. In the best case, rows fail silently. In the worst case, audit records are corrupted or lost.

**Evidence:** Line 442 submits work with a shared `ctx`:
```python
futures = {executor.submit(self._process_single_row, idx, row.to_dict(), ctx, client): idx for idx, row in enumerate(rows)}
```
All threads share the same `ctx` and therefore the same `state_id`. Inside `_process_single_row`, line 540 calls `ctx.record_call()`. The `PluginContext.record_call()` method (context.py line 289) calls `self.landscape.allocate_call_index(self.state_id)` -- unless this allocator is thread-safe (uses a lock), this is a race condition.

### [486-511] Contract inferred from first output row only -- inconsistent with error rows

**What:** The output contract is built by iterating the keys of `output_rows[0]` (line 493-503). When the first row is an error row (has `_error` key, no `_usage`/`_model`/etc.), the contract will be missing the success-specific fields. Conversely, when the first row succeeds but later rows have errors, the contract includes fields those rows lack.

**Why it matters:** Downstream consumers relying on the output contract to know which fields exist will get an inconsistent view. The OBSERVED contract advertises fields that may not exist on every row in the batch, potentially causing downstream `KeyError` exceptions.

**Evidence:** Lines 464-484 show that error rows get `response_field` set to `None` and `response_field_error` set, while success rows (line 748-758) get `_usage`, `_template_hash`, `_model`, etc. The contract (line 492-503) is built from whichever row happens to be first.

## Warnings

### [264-337] Langfuse tracing context managers in worker threads

**What:** `_record_langfuse_trace()` uses Langfuse's `start_as_current_observation()` context managers. These use OpenTelemetry context propagation which is thread-local. When called from ThreadPoolExecutor worker threads, the OTEL context is isolated per-thread but the Langfuse client is shared. Nested context managers (`span` wrapping `generation`) may not establish correct parent-child relationships across threads since the parent span is created and destroyed within the same thread scope.

**Why it matters:** Langfuse traces may show disconnected spans rather than proper hierarchies. While this does not cause data loss, it degrades observability, making it harder to correlate traces with specific batch executions. The tracing was specifically noted as a benefit of this plugin over azure_batch ("we CAN trace each call").

**Evidence:** Lines 292-308 create nested `start_as_current_observation` calls. Each worker thread creates its own span tree. There is no parent trace or batch-level span linking these per-row traces together.

### [153] _on_error stored but never used within this class

**What:** `self._on_error = cfg.on_error` is set on line 153 but is never referenced anywhere else in `OpenRouterBatchLLMTransform`. The base class `BaseTransform` has `_on_error` as a class attribute, and the engine presumably reads it externally for error routing. However, the assignment on line 153 overwrites the class attribute without being used in the plugin itself.

**Why it matters:** This is benign but confusing. The store-but-never-use pattern makes it unclear whether error routing is actually functional for this transform. If the engine reads `transform._on_error` directly, this works. But it creates a code smell where someone might think it is dead code and remove it, breaking error routing.

**Evidence:** `grep -n "_on_error" openrouter_batch.py` returns only line 153.

### [442] row.to_dict() called in main thread, potential memory amplification

**What:** Line 442 calls `row.to_dict()` for every row in the batch, creating a full dict copy in the main thread before submitting to the executor. For large batches with large rows, this creates 2x memory usage (PipelineRow + dict copy) for all rows simultaneously.

**Why it matters:** For batches of thousands of rows with rich data, this could cause memory pressure. The conversion could be deferred to the worker threads.

**Evidence:**
```python
futures = {executor.submit(self._process_single_row, idx, row.to_dict(), ctx, client): idx for idx, row in enumerate(rows)}
```

### [574-577] state_id None check returns error dict instead of crashing

**What:** Lines 575-577 check `if state_id is None: return {"error": {"reason": "missing_state_id"}}`. Per CLAUDE.md, `state_id` being `None` in a batch transform context is a framework bug (our code), not user data. The code should crash rather than return an error dict.

**Why it matters:** This violates the "crash on our bugs" principle from CLAUDE.md. A missing `state_id` means the engine failed to set up the execution context properly. Silently returning an error dict means this row gets marked as a row-level failure instead of surfacing the actual framework bug.

**Evidence:** The state_id is set by the engine's executor. If it is None, that is a bug in orchestrator/executor setup, not a data issue. Compare with `azure.py` line 438 which raises `RuntimeError` for the same condition.

## Observations

### [80-112] Comprehensive docstring and configuration example

**What:** The class docstring is thorough, explaining the architecture, configuration, and differences from azure_batch_llm.

### [430-439] httpx.Client properly shared across threads

**What:** The httpx.Client is created once and shared across all ThreadPoolExecutor workers. httpx.Client is documented as thread-safe. This is correct and avoids per-row connection overhead.

### [486-503] python_type=object for all fields in inferred contract

**What:** All inferred fields use `python_type=object`, which provides no type safety. This is noted as an "architectural gap" in the comments. While acceptable for OBSERVED mode, it means downstream schema validation is effectively disabled for batch transform outputs.

### [762-782] Proper resource cleanup in close()

**What:** The `close()` method properly flushes Langfuse tracing and cleans up the client reference. However, it does not shut down any ThreadPoolExecutor since those are created/destroyed per `_process_batch` call using context managers. This is correct.

### Duplication with azure.py

**What:** Significant code duplication between this file and `azure.py` (tracing setup, Langfuse trace recording, schema construction, output field building). The tracing setup code (~100 lines) is nearly identical. This creates a maintenance burden where tracing changes must be replicated across all LLM transform files.

## Verdict
**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Verify thread-safety of `ctx.record_call()` and `landscape.allocate_call_index()` when called from ThreadPoolExecutor workers with a shared context. If not thread-safe, either clone the context per-worker or add locking. (2) Fix the `state_id is None` check to raise RuntimeError instead of returning an error dict. (3) Consider building the output contract from the union of all rows rather than just the first. (4) Extract duplicated tracing setup into a shared mixin or helper.
**Confidence:** HIGH -- all findings are based on direct code reading with full context of the threading model and CLAUDE.md principles.
