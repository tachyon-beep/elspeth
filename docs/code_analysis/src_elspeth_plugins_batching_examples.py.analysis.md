# Analysis: src/elspeth/plugins/batching/examples.py

**Lines:** 212
**Role:** Documentation-as-code file providing examples of how to use the batching infrastructure. Contains one runnable class (`OutputPortSinkAdapter`) and extensive docstring-based examples showing transform conversion, orchestrator integration, transform chaining, and throughput improvement visualization.
**Key dependencies:** TYPE_CHECKING imports only (`TransformResult`, `TokenInfo`). No runtime imports beyond `__future__`. `OutputPortSinkAdapter` is a self-contained class. Not imported by any production or test code.
**Analysis depth:** FULL

## Summary

This file is primarily documentation. The single concrete class (`OutputPortSinkAdapter`) has a data-loss bug in `_flush()` where it unpacks tokens from the buffer but discards the actual results and never calls the sink. The docstring examples contain a stale API signature that does not match the current `OutputPort.emit()` protocol. These issues are contained to an example file and do not affect production code, but if someone copies this code into production, they would encounter silent data loss and type errors.

## Warnings

### [51-61] OutputPortSinkAdapter._flush() discards results and never writes to sink

**What:** The `_flush()` method extracts tokens from the buffer at line 57 but does not extract results or pass them to the sink. The sink write call is commented out (line 59). If this adapter is used as-is, all data buffered via `emit()` is silently discarded on flush.

**Why it matters:** If a developer copies this "example" into production without noticing the commented-out sink write, they would have a transform that appears to work (no errors) but silently drops all output. This contradicts ELSPETH's "no silent drops" principle. Since this is an example file, the impact is limited to developers who might use it as a template.

**Evidence:**
```python
def _flush(self) -> None:
    if not self._buffer:
        return
    _tokens = [token for token, _, _ in self._buffer]  # Results are discarded
    # Your sink.write() call here
    # self._sink.write(tokens=_tokens, ...)  # COMMENTED OUT
    self._buffer.clear()  # Buffer cleared without writing anything
```

### [177] TransformOutputAdapter example has wrong emit() signature

**What:** In Example 4 (line 177), the `TransformOutputAdapter.emit()` method has the signature `emit(self, token: TokenInfo, result: TransformResult) -> None`, which is missing the `state_id: str | None` parameter required by the `OutputPort` protocol (ports.py line 40).

**Why it matters:** If a developer copies this example, it would fail at runtime when the BatchTransformMixin's release loop calls `emit(token, result, state_id)` with three arguments. This would manifest as a `TypeError: emit() takes 3 positional arguments but 4 were given`.

**Evidence:**
```python
# Example 4, line 177:
class TransformOutputAdapter:
    def emit(self, token: TokenInfo, result: TransformResult) -> None:
        # Missing state_id parameter!

# Actual OutputPort protocol (ports.py):
class OutputPort(Protocol):
    def emit(self, token: TokenInfo, result: TransformResult | ExceptionResult, state_id: str | None) -> None:
```

### [25-66] OutputPortSinkAdapter does not implement thread safety

**What:** `OutputPortSinkAdapter.emit()` appends to `self._buffer` (a list) and calls `_flush()` when the batch size threshold is reached. Since `emit()` is called from the BatchTransformMixin's release thread and `close()` might be called from the orchestrator thread, there is a potential race condition on the buffer list.

**Why it matters:** In practice, only one release thread calls `emit()`, and `close()` would be called after shutdown, so there is no actual concurrent access. However, the class does not document this threading assumption, and as an "example" that developers might copy, the lack of thread safety is a trap.

## Observations

### [1-8] File is mostly docstrings in triple-quoted strings

**What:** Examples 2-5 (lines 72-212) are enclosed in triple-quoted strings rather than actual code. They are effectively documentation that happens to live in a `.py` file rather than a `.md` file. This means they are never syntax-checked, never type-checked, and never tested.

**Why it matters:** The stale API signature in Example 4 (noted above) is a direct consequence of this pattern. If these examples were actual code with type annotations, mypy would have caught the missing `state_id` parameter. As docstrings, they rot silently.

### [25] OutputPortSinkAdapter not imported or used anywhere

**What:** A grep for `OutputPortSinkAdapter` across the codebase confirms it is only defined in this file and not imported or referenced by any other file.

**Why it matters:** This is expected for an examples file, but it means this code has zero test coverage and no production validation.

### [96-110] Example 2 shows dict-based accept() rather than PipelineRow

**What:** The "After" example in Example 2 shows `accept(self, row: dict, ctx: PluginContext)` and `_do_processing(self, row: dict, ctx: PluginContext)` using `dict` as the row type. The actual production transforms use `PipelineRow` (the codebase is mid-migration per `2026-02-05-pipeline-row-everywhere-refactor.md`).

**Why it matters:** Minor staleness. The examples use the pre-migration types.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Fix the `TransformOutputAdapter.emit()` signature in Example 4 to include `state_id: str | None`. (2) Either complete the `OutputPortSinkAdapter._flush()` implementation or add a prominent comment that it is intentionally incomplete. (3) Consider converting docstring-based examples to actual tested code or moving them to proper documentation. These are all low-severity issues since this file does not affect production behavior.
**Confidence:** HIGH -- The file is short and self-contained. All findings are straightforward to verify.
