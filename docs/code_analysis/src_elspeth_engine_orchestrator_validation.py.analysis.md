# Analysis: src/elspeth/engine/orchestrator/validation.py

**Lines:** 174
**Role:** Pre-run validation of route configurations. Validates that gate routes, transform error sinks, and source quarantine destinations all reference existing sinks before any rows are processed. This is the last line of defense against misconfigured pipelines.
**Key dependencies:** Imports `GateName` and `RouteValidationError` from contracts/types. Uses `GateProtocol` and `TransformProtocol` from protocols (runtime, for isinstance checks). Called by `orchestrator.core.Orchestrator._validate_routes()` during pipeline initialization.
**Analysis depth:** FULL

## Summary

This is a well-written defensive validation module. It correctly catches configuration errors at pipeline initialization time rather than letting them surface as cryptic runtime failures. The code is clear, the error messages are actionable, and the validation coverage is thorough for the routing paths it covers. There are no critical findings. A few minor observations about completeness and edge cases.

## Warnings

### [66-70] Reverse lookup only considers GateProtocol instances in transforms list

**What:** The `node_id_to_gate_name` reverse lookup is built by iterating `transforms` and checking `isinstance(transform, GateProtocol)`. However, the `route_resolution_map` may contain entries for config gates (passed separately via `config_gate_id_map`). The code handles this at lines 73-77 by also adding config gates to the lookup. But if a `gate_node_id` in `route_resolution_map` is neither in `transforms` (as a GateProtocol) nor in `config_gate_id_map`, the lookup at line 92 will raise a `KeyError`.

**Why it matters:** This would only happen if there is a bug in graph construction (a route exists for a gate that was never registered). Per CLAUDE.md, crashing on system bugs is correct. However, the `KeyError` would produce a confusing error message without context. The `RouteValidationError` at lines 93-97 would never be reached; instead, a bare `KeyError` would propagate.

**Evidence:**
```python
# Line 92 - KeyError if gate_node_id not in lookup
gate_name = node_id_to_gate_name[gate_node_id]
```
This is acceptable behavior (crash on system bug), but the error message would not indicate which gate_node_id was missing or that it represents a graph construction bug.

### [122] Direct access to transform._on_error (underscore-prefixed attribute)

**What:** The validation accesses `transform._on_error` directly. While `_on_error` is defined in `TransformProtocol` as a protocol attribute (line 206 of protocols.py), the single-underscore prefix conventionally signals a "private" or "internal" attribute. Accessing it from outside the class hierarchy is an unusual pattern.

**Why it matters:** This is a stylistic concern, not a bug. The attribute is explicitly part of the protocol contract. However, it could confuse developers who expect underscore-prefixed attributes to be private. The same pattern is used for `source._on_validation_failure` at line 161. Both are protocol-defined attributes that happen to use underscore naming, likely to avoid collision with user-facing config properties.

**Evidence:**
```python
on_error = transform._on_error  # Line 122
on_validation_failure = source._on_validation_failure  # Line 161
```

## Observations

### [38-97] validate_route_destinations is thorough

The function correctly skips "continue" and "fork" destinations (lines 82-87), builds reverse lookups from both transform-based gates and config gates, and produces clear error messages with available sink names. The validation correctly runs at initialization time.

### [100-139] validate_transform_error_sinks correctly filters on TransformProtocol

The function correctly skips non-TransformProtocol instances (GateProtocol uses routing, not error sinks). It also correctly handles the "discard" special value. The validation is straightforward and complete.

### [142-174] validate_source_quarantine_destination covers the P2-2026-01-19 fix

The docstring references the specific bug this validation prevents (P2-2026-01-19-source-quarantine-silent-drop), showing good traceability. The validation is simple and correct.

### Missing validation: batch transform _on_error not covered

The `validate_transform_error_sinks` function checks `TransformProtocol._on_error` but batch-aware transforms (`BatchTransformProtocol`) also have `_on_error`. Since batch transforms are included in the transforms list as `TransformProtocol` instances (they satisfy the protocol), they are covered. However, this relies on the isinstance check at line 118 matching batch transforms, which it does because `TransformProtocol` is a runtime_checkable protocol and batch transforms implement all required attributes.

### Missing validation: aggregation output sinks

There is no validation that aggregation outputs (which route through remaining transforms and potentially to sinks) have valid destinations. This is handled implicitly by the gate route validation and the fact that aggregation tokens use the default sink, but explicit validation could catch edge cases.

## Verdict

**Status:** SOUND
**Recommended action:** No immediate changes required. The module fulfills its purpose well. Consider adding a more descriptive error if `node_id_to_gate_name` lookup fails at line 92 (wrapping the KeyError with context about graph construction), but this is low priority since it would only fire on framework bugs.
**Confidence:** HIGH -- The module is short, focused, and straightforward. All code paths are clear.
