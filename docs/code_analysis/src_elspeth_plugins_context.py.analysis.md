# Analysis: src/elspeth/plugins/context.py

**Lines:** 511
**Role:** `PluginContext` is the execution context passed to every plugin operation. It carries run metadata, landscape recorder, telemetry callbacks, rate limiters, schema contracts, audited clients, and checkpoint state. It also provides convenience methods for recording external calls, validation errors, and transform errors to the audit trail. This is the plugin-facing API surface for all engine services.
**Key dependencies:** Imports `logging`, `contextlib`, `dataclasses`, `datetime`. TYPE_CHECKING imports for `Tracer`, `Span`, `Call`, `CallStatus`, `CallType`, `TransformErrorReason`, `RuntimeConcurrencyConfig`, `TokenInfo`, `PipelineRow`, `SchemaContract`, `LandscapeRecorder`, `RateLimitRegistry`, `AuditedHTTPClient`, `AuditedLLMClient`. Consumed by every plugin via method signatures, by engine executors (which set fields like `state_id`, `node_id`, `contract`), and by the orchestrator (which constructs the context).
**Analysis depth:** FULL

## Summary

The file is well-structured and the `record_call()` method has robust XOR validation for `state_id`/`operation_id`. The telemetry emission is correctly wrapped to prevent failures from corrupting the audit recording. There are no critical issues. The main concerns are: (1) `route_to_sink()` is a Phase 2 stub that only logs, and the executor calls it redundantly -- the actual row delivery is handled by the orchestrator via `RowResult` outcomes, making this method misleading dead code, (2) `record_validation_error()` does not pass the `contract_violation` parameter through to the recorder, losing structured audit data, (3) the `PluginContext` is a mutable dataclass with many fields set by the executor after construction, creating a wide mutation surface that is hard to reason about.

## Critical Findings

No critical findings.

## Warnings

### [488-511] route_to_sink() is a Phase 2 stub -- misleading dead code

**What:** `route_to_sink()` at line 488 is documented as a "Phase 2 stub" that "Currently logs the routing action." It does `logger.info(...)` and nothing else. The engine executor at `executors.py:504-508` calls this method when a transform returns an error routed to a sink.

**Why it matters:** The actual row delivery for error-routed rows does NOT depend on this method. The processor returns a `RowResult` with `outcome=RowOutcome.ROUTED` and `sink_name=error_sink` (processor.py:1797-1809), and the orchestrator handles it by placing the token into `pending_tokens[result.sink_name]` (orchestrator/core.py:1249-1255), which then gets written by `SinkExecutor.write()`. So the rows ARE delivered correctly.

The problem is that `route_to_sink()` exists as dead code that misleads readers into thinking it's the delivery mechanism. Additionally, a plugin developer reading the `PluginContext` API might try to call `route_to_sink()` directly, expecting it to work. It will silently do nothing except log. This method should either be implemented to actually route (redundant but correct), or removed, or documented clearly as inoperative.

**Evidence:**
```python
# Line 496-511 -- Phase 2 stub, never actually routes:
def route_to_sink(self, sink_name, row, metadata=None) -> None:
    logger.info("route_to_sink: %s -> %s (metadata=%s)", self.node_id, sink_name, metadata)
```

And the executor calls it at executors.py:504-508 but the actual delivery goes through the `RowResult` return path.

### [363-428] record_validation_error() does not forward contract_violation to recorder

**What:** The `record_validation_error()` method on `PluginContext` does not accept or pass through a `contract_violation` parameter. However, the underlying `LandscapeRecorder.record_validation_error()` accepts an optional `contract_violation: ContractViolation | None = None` keyword argument (see recorder.py line 2950). This means plugins calling `ctx.record_validation_error()` cannot provide structured contract violation data, even though the recorder supports it.

**Why it matters:** When a source plugin catches a `ContractViolation` (e.g., type mismatch, missing field), it records it as a plain string error message. The recorder's support for structured violation data (`violation_type`, `normalized_field_name`, `original_field_name`, `expected_type`, `actual_type`) is inaccessible through the context API. This degrades audit trail quality -- structured data is more queryable and analyzable than free-text error strings.

**Evidence:** Compare the signatures:

```python
# Context (line 363-368):
def record_validation_error(
    self, row: Any, error: str, schema_mode: str, destination: str,
) -> ValidationErrorToken:

# Recorder (line 2941-2950):
def record_validation_error(
    self, run_id: str, node_id: str | None, row_data: Any,
    error: str, schema_mode: str, destination: str,
    *, contract_violation: ContractViolation | None = None,
) -> str:
```

The context call at line 421 does not pass `contract_violation`:
```python
error_id = self.landscape.record_validation_error(
    run_id=self.run_id, node_id=self.node_id,
    row_data=row, error=error,
    schema_mode=schema_mode, destination=destination,
)
```

### [83-131] PluginContext has a wide mutation surface -- 15+ optional fields set after construction

**What:** `PluginContext` is a mutable dataclass. The orchestrator constructs it with a few core fields (`run_id`, `config`, `landscape`), then the executor mutates it repeatedly:

- `ctx.state_id = state.state_id` (executors.py:247)
- `ctx.node_id = transform.node_id` (executors.py:248)
- `ctx.contract = token.row_data.contract` (executors.py:254)
- `ctx.llm_client = ...` (set by orchestrator for LLM transforms)
- `ctx.operation_id = ...` (set for source/sink operations)

The same context object is mutated across multiple transform invocations, with fields being overwritten each time.

**Why it matters:** This creates temporal coupling -- the correctness of `record_call()` depends on `state_id` being set correctly by the executor *before* the plugin calls it. If the executor forgets to set a field, or sets it too late, or the plugin stores a reference to the context and uses it asynchronously after the executor has mutated it for a different row, the behavior is undefined. The comment at line 103 ("IMPORTANT: This is derivative state - the executor must keep it synchronized") acknowledges this risk.

For the current synchronous execution model this works, but if the engine ever adds true async processing (where multiple rows are in-flight simultaneously sharing the same context), the mutation pattern will cause race conditions.

**Evidence:**
```python
# Context is constructed at orchestrator/core.py:851:
ctx = PluginContext(run_id=run_id, config=config.config, landscape=recorder, ...)

# Then mutated per-transform at executors.py:247-254:
ctx.state_id = state.state_id
ctx.node_id = transform.node_id
ctx.contract = token.row_data.contract
```

### [391-392] record_validation_error uses row["id"] as row_id if present -- trusts external data for identity

**What:** At line 391-392, when generating a `row_id` for validation errors, the method checks if `row` is a dict with an `"id"` key and uses `str(row["id"])` as the `row_id`. This means external data controls the identity used in the `ValidationErrorToken`.

**Why it matters:** This is Tier 3 (external data). If two different rows have the same `"id"` value, their validation errors would share the same `row_id`, making them indistinguishable in the `ValidationErrorToken` (though the recorder uses its own hashing for the `error_id`, so the audit trail records remain separate). More concerning, the `row_id` in the `ValidationErrorToken` is used for tracking and could confuse downstream logic that relies on row identity uniqueness. The hash-based fallback (lines 396-407) is more robust because it derives identity from content.

**Evidence:**
```python
# Lines 391-392:
if isinstance(row, dict) and "id" in row:
    row_id = str(row["id"])
```

### [319-349] Telemetry emission in record_call() imports modules inside try/except

**What:** The telemetry emission block (lines 319-348) imports `CallType`, `stable_hash`, and `ExternalCallCompleted` inside the try block. If these imports fail (e.g., corrupted installation, circular import), the except clause at line 349 catches it as a telemetry failure and logs a warning.

**Why it matters:** Import errors are framework bugs that should crash per the data manifesto. Catching them as "telemetry failures" hides a potentially serious problem. In practice, these imports should always succeed because they are from the same package, but the broad `except Exception` catch makes it impossible to distinguish an import error from an actual telemetry emission error.

**Evidence:**
```python
# Lines 319-349:
try:
    from elspeth.contracts.enums import CallType as CallTypeEnum
    from elspeth.core.canonical import stable_hash
    from elspeth.telemetry.events import ExternalCallCompleted
    # ... telemetry emission ...
except Exception as tel_err:
    # This catches IMPORT errors too, hiding framework bugs
    logger.warning("telemetry_emit_failed in record_call", ...)
```

## Observations

### [145-189] Checkpoint API is well-designed with clear lifecycle

**What:** The `get_checkpoint()`, `update_checkpoint()`, and `clear_checkpoint()` methods form a clean checkpoint lifecycle. The two-tier lookup (batch checkpoints from previous errors, then local checkpoint) correctly supports crash recovery. The `clear_checkpoint()` method properly clears both tiers.

### [210-221] start_span() correctly returns nullcontext when tracer is None

**What:** The `start_span()` method returns `nullcontext()` when the tracer is not configured, allowing callers to use `with ctx.start_span(...)` unconditionally. This is clean and correct.

### [257-361] record_call() has robust XOR validation

**What:** The `record_call()` method enforces that exactly one of `state_id` or `operation_id` is set, using `FrameworkBugError` for violations. The error messages include the actual values for debugging. The assertions at lines 288 and 304 are redundant (guarded by the if/else logic) but serve as documentation and narrow the type for mypy. This is well-implemented.

### [130] telemetry_emit default lambda is correct

**What:** `telemetry_emit: Callable[[Any], None] = field(default=lambda event: None)` provides a no-op default. This means plugins can always call `self.telemetry_emit(event)` without None checks. The orchestrator replaces this with a real callback when telemetry is configured. Clean pattern.

### [40-63] ValidationErrorToken and TransformErrorToken are simple and correct

**What:** These dataclasses carry the essential information for tracking quarantined and errored rows. The default values (`error_id=None`, `destination="discard"`) are appropriate for the case where landscape is not available.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Either implement `route_to_sink()` properly or remove it and remove the call from the executor -- the current state is misleading dead code. (2) Add `contract_violation` parameter passthrough to `record_validation_error()` to enable structured audit data. (3) Consider splitting the telemetry try/except to separate import errors from emission errors, or move the imports to module level. (4) The mutable context pattern works for the current synchronous model but should be documented as a constraint -- any future async execution model would require per-invocation immutable contexts.
**Confidence:** HIGH -- Full read, cross-referenced with engine executors (which set context fields), orchestrator (which constructs context and handles ROUTED outcomes), recorder (which receives context calls), and concrete plugins (which use the context API). The `route_to_sink()` finding was initially assessed as critical but downgraded after tracing the full delivery path through the orchestrator's `pending_tokens` mechanism.
