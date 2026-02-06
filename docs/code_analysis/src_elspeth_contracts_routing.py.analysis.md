# Analysis: src/elspeth/contracts/routing.py

**Lines:** 172
**Role:** Flow control and edge definitions for the DAG execution model. Defines `RoutingAction` (the routing decision from gates), `RoutingSpec` (audit trail edge record), and `EdgeInfo` (execution graph edge metadata). The `RoutingAction` class is the primary output of gate evaluation -- it determines whether a token continues, routes to a sink, or forks to parallel paths.
**Key dependencies:** `copy` (standard library), `elspeth.contracts.enums` (RoutingKind, RoutingMode), `elspeth.contracts.errors` (RoutingReason). Imported by `results.py`, `engine/executors.py`, `engine/processor.py`, integration tests, and plugin protocols.
**Analysis depth:** FULL

## Summary

This is a well-designed module with strong invariant enforcement. The `RoutingAction` frozen dataclass with factory methods and `__post_init__` validation is a textbook implementation of a constrained value type. The `deep_copy` defensive copying on `reason` is appropriate given that reasons are mutable dicts. One concern: the `route()` factory method accepts a `mode` parameter that defaults to `MOVE` but will raise `ValueError` if `COPY` is passed -- the method signature allows a value that is always rejected.

## Critical Findings

None.

## Warnings

### [96-122] `route()` factory method accepts `mode=COPY` but always rejects it

**What:** The `route()` classmethod has parameter `mode: RoutingMode = RoutingMode.MOVE` which accepts any `RoutingMode` value. However, `__post_init__` (line 77-83) unconditionally rejects `ROUTE + COPY` combination. This means `RoutingAction.route("sink_a", mode=RoutingMode.COPY)` will be accepted by the function signature but immediately raise `ValueError` from `__post_init__`.

**Why it matters:** The method docstring says "COPY mode not supported - use fork_to_paths() instead" and the `__post_init__` error message is helpful. However, the type signature is misleading -- it implies COPY is a valid option for routing. A caller reading the function signature (not the docstring) would reasonably expect both modes to work. This is an API design issue, not a bug, since the error is deterministic and immediate. In production, callers use `RoutingMode.MOVE` exclusively (confirmed by grep of the codebase showing all `RoutingAction.route()` calls pass `mode=RoutingMode.MOVE`).

**Evidence:**
```python
@classmethod
def route(
    cls,
    label: str,
    *,
    mode: RoutingMode = RoutingMode.MOVE,  # Accepts COPY...
    reason: RoutingReason | None = None,
) -> "RoutingAction":
    # ...
    return cls(
        kind=RoutingKind.ROUTE,
        destinations=(label,),
        mode=mode,
        reason=_copy_reason(reason),
    )
# But __post_init__ rejects ROUTE + COPY:
# if self.kind == RoutingKind.ROUTE and self.mode == RoutingMode.COPY:
#     raise ValueError(...)
```

### [136-140] `fork_to_paths()` duplicate detection is O(n^2)

**What:** The duplicate path detection uses `paths.count(p) > 1` inside a list comprehension, which is O(n * m) where n is the number of duplicates and m is the total paths.

**Why it matters:** For typical fork operations (2-5 paths), this is negligible. However, if a malformed configuration somehow creates a fork with many paths, this becomes quadratic. Given that forks are typically small (DAG branches), this is a theoretical concern only.

**Evidence:**
```python
if len(paths) != len(set(paths)):
    duplicates = [p for p in paths if paths.count(p) > 1]
```

## Observations

### [12-29] `_copy_reason()` defensive deep copy is appropriate

The `copy.deepcopy()` on the mutable `RoutingReason` dict prevents the frozen dataclass from being circumvented through reference mutation. Since `RoutingReason` is a `TypedDict` (which is a regular dict at runtime), this deep copy is necessary to maintain true immutability. Good pattern.

### [63-83] `__post_init__` validation is thorough and covers all invalid combinations

The five validation checks in `__post_init__` exhaustively cover the constraint space:
1. CONTINUE + non-empty destinations
2. CONTINUE + COPY mode
3. FORK_TO_PATHS + non-COPY mode
4. ROUTE + not exactly one destination
5. ROUTE + COPY mode

This is a complete enforcement of the routing invariants described in the docstring.

### [85-93] `continue_()` uses trailing underscore to avoid keyword conflict

The `continue_()` method name correctly avoids the Python keyword `continue`. This is a standard Python naming convention and is documented implicitly.

### [149-172] RoutingSpec and EdgeInfo are simple, correct value types

Both are frozen dataclasses with no logic. `RoutingSpec` captures edge routing for audit, `EdgeInfo` captures graph edge metadata. Both enforce that `mode` is `RoutingMode` enum, not string, with the comment "Conversion from DB strings happens in repository layer." This is correct per the trust tier model.

### [59] `destinations` is `tuple[str, ...]` not `list`

Good choice -- tuples are immutable and hashable, consistent with the frozen dataclass pattern. The `fork_to_paths()` factory converts the `list[str]` parameter to `tuple()` on line 143.

## Verdict

**Status:** SOUND
**Recommended action:** Consider narrowing the `route()` method's `mode` parameter to accept only `RoutingMode.MOVE` (via a `Literal[RoutingMode.MOVE]` type annotation or by removing the parameter entirely since MOVE is always the correct mode for ROUTE). This would make the invalid state unrepresentable at the API level rather than relying on runtime validation. Low priority -- the current code works correctly and the error message is clear.
**Confidence:** HIGH -- this is a small, focused module with strong invariant enforcement, no I/O, no concurrency, and comprehensive validation. The routing logic is well-tested (12+ test files reference it).
