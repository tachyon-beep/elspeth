# Analysis: src/elspeth/plugins/protocols.py

**Lines:** 665
**Role:** Defines the Protocol interfaces (contracts) for all plugin types -- Source, Transform, BatchTransform, Gate, Coalesce, and Sink. These are the structural typing contracts that plugins are verified against at type-check time and via `isinstance()` at runtime.
**Key dependencies:** Imports `Determinism` from `elspeth.contracts`; TYPE_CHECKING imports for `PluginSchema`, `PipelineRow`, `SourceRow`, `PluginContext`, `TransformResult`, `GateResult`, `ArtifactDescriptor`, `OutputValidationResult`. Imported by `elspeth.engine.executors`, `elspeth.engine.processor`, `elspeth.engine.orchestrator`, `elspeth.core.dag`, `elspeth.plugins.__init__`, and tests.
**Analysis depth:** FULL

## Summary

The file is structurally sound and well-documented. The protocols faithfully define the plugin contracts that the engine enforces. There are no critical bugs. The main concerns are: (1) `PluginProtocol` is defined but never used anywhere in the codebase, (2) `CoalesceProtocol` is missing a `close()` method that all other plugin protocols declare, (3) `BatchTransformProtocol` is missing the `transforms_adds_fields` attribute that `TransformProtocol` has, and (4) the `_on_validation_failure` and `_on_error` attributes use private naming convention but are part of the public protocol contract, creating a confusing precedent.

## Critical Findings

No critical findings.

## Warnings

### [31-41] PluginProtocol is dead code -- defined but never consumed

**What:** `PluginProtocol` defines a base protocol with `name`, `plugin_version`, and `determinism` attributes. However, it is never imported or used anywhere in the source tree -- not by the engine, not by the plugin manager, not by tests, and not re-exported from `plugins/__init__.py`.

**Why it matters:** Dead protocol definitions create confusion about what constitutes the actual plugin contract. A developer may add attributes to `PluginProtocol` believing it will be enforced, but nothing checks it. The individual protocols (`SourceProtocol`, `TransformProtocol`, etc.) each independently define `name`, `plugin_version`, and `determinism` without referencing `PluginProtocol`. This is not DRY, and the base protocol serves no purpose.

**Evidence:** Grep for `PluginProtocol` across all source files returns only the definition at line 31. It is not imported by `plugins/__init__.py`, not used in `isinstance()` checks, and not referenced in type annotations anywhere.

### [449-518] CoalesceProtocol missing close() lifecycle method

**What:** Every other plugin protocol (`SourceProtocol`, `TransformProtocol`, `BatchTransformProtocol`, `GateProtocol`, `SinkProtocol`) declares a `close()` method for resource cleanup. `CoalesceProtocol` only declares `on_start()` and `on_complete()` but not `close()`.

**Why it matters:** If a coalesce plugin holds resources (connections, file handles, buffers), there is no protocol-level contract guaranteeing the engine will call `close()`. Since there is also no `BaseCoalesce` class (confirmed by grep), the asymmetry could lead to resource leaks when coalesce plugins are added. Currently the codebase has no concrete coalesce implementations besides the engine-internal `CoalesceExecutor`, so this is latent.

**Evidence:**
```python
# CoalesceProtocol (line 510-518) -- no close():
    def on_start(self, ctx: "PluginContext") -> None: ...
    def on_complete(self, ctx: "PluginContext") -> None: ...
    # Missing: def close(self) -> None: ...

# Compare TransformProtocol (line 228-234):
    def close(self) -> None: ...
```

### [248-339] BatchTransformProtocol missing transforms_adds_fields attribute

**What:** `TransformProtocol` declares `transforms_adds_fields: bool` (line 201), which signals to the engine that a transform adds fields during execution and needs evolved contract recording. `BatchTransformProtocol` does not declare this attribute.

**Why it matters:** The engine executor checks `transform.transforms_adds_fields` at line 409 of `executors.py`. If a batch-aware transform sets this flag, the executor will try to access it. The runtime behavior depends on whether the concrete class (which inherits from `BaseTransform` which does define it) has it, but the protocol contract is incomplete. This creates a silent gap: mypy cannot verify that batch transforms satisfy the full contract because the protocol doesn't require it.

**Evidence:**
```python
# TransformProtocol (line 197-201):
    transforms_adds_fields: bool

# BatchTransformProtocol (lines 286-305):
    # ... no transforms_adds_fields declared
```

And in `executors.py` line 409:
```python
if result.row is not None and transform.transforms_adds_fields:
```

### [78, 206] Private naming convention for public protocol attributes

**What:** `_on_validation_failure` on `SourceProtocol` and `_on_error` on `TransformProtocol` / `BatchTransformProtocol` use underscore-prefix naming, which by Python convention indicates private/internal attributes. Yet these are part of the public protocol contract -- the engine accesses them directly.

**Why it matters:** This creates a naming inconsistency. Protocol attributes are by definition part of the public interface. Developers familiar with Python conventions will be confused about whether these should be accessed externally. The engine validation code at `orchestrator/validation.py:161` explicitly accesses `source._on_validation_failure`, and the executor at `executors.py` accesses `transform._on_error`. The underscore convention suggests these should not be touched, but the protocol contract requires them.

**Evidence:**
```python
# Line 78 (SourceProtocol):
_on_validation_failure: str

# Line 206 (TransformProtocol):
_on_error: str | None
```

External access in `orchestrator/validation.py`:
```python
on_validation_failure = source._on_validation_failure  # Line 161
```

## Observations

### [67-68] SourceProtocol output_schema typed as type[PluginSchema] -- inconsistent with practice

**What:** `output_schema` is typed as `type[PluginSchema]`, meaning it expects a class. In practice, sources can use dynamic schemas. The typing is correct for the fixed/flexible use case but the protocol doesn't account for how dynamic schemas work in OBSERVED mode where the schema is inferred at runtime.

### [186-195] is_batch_aware flag creates a protocol bifurcation

**What:** `TransformProtocol.is_batch_aware` must be `False`, and `BatchTransformProtocol.is_batch_aware` must be `True`. But both protocols share almost all the same attributes and methods. The only real difference is the `process()` signature (`PipelineRow` vs `list[PipelineRow]`). This design means the engine must check `is_batch_aware` at runtime and cast to the correct protocol, which `isinstance()` checks handle but which obscures the contract at the type level.

### [431-437] CoalescePolicy enum defined in protocols.py rather than contracts/enums.py

**What:** `CoalescePolicy` is an enum defined inline in `protocols.py` at line 431. All other enums in the system are defined in `contracts/enums.py`. This breaks the established pattern where all boundary-crossing enums live in the contracts package.

### [621-665] Resume-related methods on SinkProtocol are well-designed

**What:** `configure_for_resume()`, `validate_output_target()`, and `set_resume_field_resolution()` are properly documented with clear contracts, default behaviors, and implementation notes. No issues found.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Remove `PluginProtocol` or actually use it to enforce the common attributes across all plugin protocols. (2) Add `close()` to `CoalesceProtocol` for consistency. (3) Add `transforms_adds_fields` to `BatchTransformProtocol` to match the engine's expectations. (4) Consider moving `CoalescePolicy` to `contracts/enums.py` for consistency. The naming convention issue with underscore-prefixed protocol attributes is a design decision that should at minimum be documented.
**Confidence:** HIGH -- Full read of the file, cross-referenced with all consumers (engine executors, processor, orchestrator validation, DAG construction, and plugin base classes).
