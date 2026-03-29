## Summary

Routing contract dataclasses in `routing.py` silently accept raw `str` values for enum fields (`kind`/`mode`), so invalidly typed routing objects pass as valid and can survive into executor/validation logic.

## Severity

- Severity: major
- Priority: P2

## Location

- File: [src/elspeth/contracts/routing.py](/home/john/elspeth/src/elspeth/contracts/routing.py)
- Line(s): 46-71, 154-171, 201-204, 220-227
- Function/Method: `RoutingAction.__post_init__`, `RouteDestination.__post_init__`, `RoutingSpec.__post_init__`, `EdgeInfo.__post_init__`

## Evidence

[routing.py](/home/john/elspeth/src/elspeth/contracts/routing.py#L46) validates `RoutingAction.mode` but never validates `RoutingAction.kind`:

```python
if not isinstance(self.mode, RoutingMode):
    raise TypeError(...)
if self.kind == RoutingKind.CONTINUE and self.destinations:
    ...
```

[routing.py](/home/john/elspeth/src/elspeth/contracts/routing.py#L154) similarly branches on `RouteDestination.kind` without validating its type, and [routing.py](/home/john/elspeth/src/elspeth/contracts/routing.py#L201) / [routing.py](/home/john/elspeth/src/elspeth/contracts/routing.py#L220) never validate `RoutingSpec.mode` or `EdgeInfo.mode` at all.

That is dangerous here because these enums are `StrEnum`s ([enums.py](/home/john/elspeth/src/elspeth/contracts/enums.py#L117), [enums.py](/home/john/elspeth/src/elspeth/contracts/enums.py#L128)), so raw strings compare equal to enum members. Downstream code therefore treats mistyped contract objects as valid:

- [gate.py](/home/john/elspeth/src/elspeth/engine/executors/gate.py#L139) dispatches on `destination.kind == RouteDestinationKind.CONTINUE`
- [validation.py](/home/john/elspeth/src/elspeth/engine/orchestrator/validation.py#L74) accepts `destination.kind in (...)`
- [graph.py](/home/john/elspeth/src/elspeth/core/dag/graph.py#L935) branches on `edge.mode == RoutingMode.DIVERT`

I verified the runtime behavior directly:

```python
RoutingAction(kind='continue', destinations=(), mode=RoutingMode.MOVE)
RouteDestination(kind='continue')
RoutingSpec(edge_id='e1', mode='move')
EdgeInfo(from_node='a', to_node='b', label='continue', mode='divert')
```

All four constructions succeeded, and each stored field remained a plain `str` while still comparing equal to the enum.

I also verified that integration code accepts the bad object: `validate_route_destinations(...)` completed successfully with `RouteDestination(kind='continue')`, so the mistyped contract survives past construction and validation.

This is inconsistent with the project’s own strict-contract pattern in [audit.py](/home/john/elspeth/src/elspeth/contracts/audit.py#L36), where enum fields are explicitly rejected unless they are actual enum instances.

## Root Cause Hypothesis

The file assumes type hints plus factory methods are sufficient, but these contracts are public dataclasses and are also used as boundary objects. Because `StrEnum` is a `str` subclass, equality-based invariant checks accidentally accept raw strings, masking missing conversions and violating ELSPETH’s “strict contract, crash on anomaly” rule.

## Suggested Fix

Add explicit enum-instance validation for every enum field in these contracts, matching the strict pattern already used in `contracts/audit.py`.

For example:

```python
if not isinstance(self.kind, RoutingKind):
    raise TypeError(...)
if not isinstance(self.mode, RoutingMode):
    raise TypeError(...)
if not isinstance(self.kind, RouteDestinationKind):
    raise TypeError(...)
```

Also add unit tests that direct construction with `"continue"`, `"move"`, and `"divert"` raises `TypeError` for these classes.

## Impact

This creates silent contract corruption at the routing boundary. A caller that forgets to convert DB/config strings into enums will not fail fast in `routing.py`; the bad objects can flow into gate dispatch, DAG validation, and graph analysis as if they were well-typed. That hides root-cause bugs, breaks Tier-1 “crash on anomaly” expectations, and makes routing/audit code less trustworthy because malformed state is treated as valid until some later, less-local failure point, or not rejected at all.
