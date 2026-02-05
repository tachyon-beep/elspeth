# Analysis: src/elspeth/contracts/enums.py

**Lines:** 271
**Role:** Central enumeration definitions for the entire ELSPETH system. Defines status codes (`RunStatus`, `NodeStateStatus`, `BatchStatus`), type classifiers (`NodeType`, `Determinism`, `CallType`), routing semantics (`RoutingKind`, `RoutingMode`), row lifecycle (`RowOutcome`), execution modes (`RunMode`), telemetry config (`TelemetryGranularity`, `BackpressureMode`), and aggregation output (`OutputMode`). These enums are the vocabulary of the system -- they are used in 107+ source files and are serialized directly to the audit database.
**Key dependencies:** Only `enum` from the standard library. This is a true leaf module with zero internal dependencies. Imported by nearly every subsystem: engine, landscape, telemetry, plugins, contracts, CLI, MCP server.
**Analysis depth:** FULL

## Summary

This is a clean, well-organized enumeration module. All enums correctly use `(str, Enum)` for database serialization compatibility. The `RowOutcome.is_terminal` property is a thoughtful addition. Two substantive concerns: the `CoalesceFailureReason` backward compatibility alias in `errors.py` (which this file's enums feed into) and the `BackpressureMode.SLOW` enum member that is defined but explicitly unimplemented. Overall, the file is sound.

## Critical Findings

None.

## Warnings

### [248-252] BackpressureMode.SLOW is defined but unimplemented

**What:** `BackpressureMode.SLOW = "slow"` is defined as a valid enum member, but `_IMPLEMENTED_BACKPRESSURE_MODES` on line 257 explicitly excludes it. The runtime config (`RuntimeTelemetryConfig.from_settings()`) rejects it at config load time.

**Why it matters:** This means users can write `backpressure_mode: slow` in YAML and Pydantic will accept it (since `BackpressureMode("slow")` succeeds), but the pipeline will fail with an opaque error later during `from_settings()` rather than at validation time. The error path is tested, but the enum-level acceptance creates a misleading API surface. Per the CLAUDE.md "No Legacy Code" policy, if SLOW mode is not implemented, it arguably should not exist in the enum at all -- it is a placeholder for future functionality that creates a false affordance today.

**Evidence:**
```python
class BackpressureMode(str, Enum):
    BLOCK = "block"
    DROP = "drop"
    SLOW = "slow"  # Defined...

_IMPLEMENTED_BACKPRESSURE_MODES = frozenset({BackpressureMode.BLOCK, BackpressureMode.DROP})  # ...but excluded
```

### [140-182] RowOutcome lacks explicit TERMINAL_OUTCOMES set for validation

**What:** The `is_terminal` property uses `self != RowOutcome.BUFFERED` -- a negative check. This means any future enum member added to `RowOutcome` is implicitly terminal by default.

**Why it matters:** If a new non-terminal outcome is added (e.g., `PENDING`, `RETRYING`, `DEFERRED`), the developer must remember to update the `is_terminal` property. A negative-check pattern makes the new member terminal by default, which could cause the engine to incorrectly treat a non-terminal state as final, leading to rows being considered "done" when they are not. An explicit set of terminal outcomes (or non-terminal outcomes) would be safer.

**Evidence:**
```python
@property
def is_terminal(self) -> bool:
    return self != RowOutcome.BUFFERED  # Negative check - all others assumed terminal
```

## Observations

### [11-20] All enums correctly use (str, Enum) for database serialization

Every enum that is stored in the database uses the `(str, Enum)` pattern, which means `.value` produces a clean string for SQL INSERT and SELECT round-tripping. This is consistent and correct throughout.

### [91-113] Determinism enum is well-designed

The `Determinism` enum has clear replay semantics documented for each value. The comment about every plugin MUST declaring one is enforced elsewhere (registration time crash). Good design.

### [127-138] RoutingMode separation is architecturally clean

The MOVE/COPY distinction is clearly documented with a concise comment about when each applies. This enum is correctly consumed by `RoutingAction.__post_init__` which enforces the constraints.

### [185-205] CallType and CallStatus are minimal

`CallType` has four members and `CallStatus` has two (SUCCESS/ERROR). These are intentionally minimal. If more call types are needed (e.g., GRPC, WebSocket), they can be added without disruption since the enum is used in INSERT context, not exhaustive matching.

### [260-271] OutputMode is simple and correct

`PASSTHROUGH` and `TRANSFORM` are the two aggregation output modes. Clean and properly documented.

### General: No `__str__` or `__repr__` overrides

The enums rely on default `str(enum_member)` behavior which produces `"EnumClass.MEMBER"` for display and `.value` for serialization. This is correct for database usage but could produce confusing log output (e.g., `"RunStatus.FAILED"` instead of `"failed"`). Since these are `(str, Enum)`, `str()` actually returns the `.value` string, which is correct.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Remove `BackpressureMode.SLOW` entirely per the No Legacy Code policy -- it is not implemented, and its presence creates a misleading API. If/when adaptive rate limiting is built, the enum member can be re-added. (2) Consider converting `RowOutcome.is_terminal` to use an explicit frozenset of non-terminal outcomes (positive-list pattern) to prevent silent bugs when new outcomes are added. Both are low-risk, high-value changes.
**Confidence:** HIGH -- this is a pure enum definition module. The concerns are about API surface design and future-proofing, not about runtime bugs.
