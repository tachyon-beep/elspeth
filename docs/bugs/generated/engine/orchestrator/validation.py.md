## Summary

`validate_source_quarantine_destination()` treats a missing source `_on_validation_failure` as a user route typo instead of a framework invariant breach, so source injection bugs are misclassified as `RouteValidationError` rather than crashing as `OrchestrationInvariantError`.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: [src/elspeth/engine/orchestrator/validation.py](/home/john/elspeth/src/elspeth/engine/orchestrator/validation.py)
- Line(s): 150-163
- Function/Method: `validate_source_quarantine_destination`

## Evidence

[`validation.py` lines 150-163](/home/john/elspeth/src/elspeth/engine/orchestrator/validation.py#L150) read the source field directly, but never enforce the invariant that it must exist:

```python
# _on_validation_failure is required by SourceProtocol
on_validation_failure = source._on_validation_failure

if on_validation_failure == "discard":
    return

if on_validation_failure not in available_sinks:
    raise RouteValidationError(...)
```

That differs from the sibling validators in the same file, which explicitly crash on missing injected fields:

[`validation.py` lines 111-116](/home/john/elspeth/src/elspeth/engine/orchestrator/validation.py#L111):
```python
on_error = transform.on_error
if on_error is None:
    raise OrchestrationInvariantError(...)
```

[`validation.py` lines 197-202](/home/john/elspeth/src/elspeth/engine/orchestrator/validation.py#L197):
```python
dest = config.on_write_failure
if dest is None:
    raise OrchestrationInvariantError(...)
```

The source contract says `_on_validation_failure` is mandatory, not optional:

[`plugin_protocols.py` lines 68-70](/home/john/elspeth/src/elspeth/contracts/plugin_protocols.py#L68):
```python
# All sources must set this
_on_validation_failure: str
```

And source config requires a non-empty value at construction time:

[`config_base.py` lines 153-164](/home/john/elspeth/src/elspeth/plugins/infrastructure/config_base.py#L153):
```python
on_validation_failure: str = Field(...)

if not v or not v.strip():
    raise ValueError("on_validation_failure must be a sink name or 'discard'")
```

But the tests for this validator only cover valid strings and unknown sink names; there is no regression test for `None` or missing injection:

[`test_validation.py` lines 141-170](/home/john/elspeth/tests/unit/engine/orchestrator/test_validation.py#L141)

What the code does now:
- If `_on_validation_failure` is `None`, it falls through to `if on_validation_failure not in available_sinks` and raises `RouteValidationError("... no sink named 'None' exists ...")`.

What it should do:
- Treat `None` as a framework bug and raise `OrchestrationInvariantError`, matching the transform and sink validators and the project’s “plugin bugs crash immediately” rule.

## Root Cause Hypothesis

This looks like an asymmetry introduced when the transform and sink validators were hardened for post-construction injection failures, but the source validator was left on the older “unknown destination” path. The function assumes the protocol guarantee always holds, yet the surrounding module already acknowledges that injected routing fields can be absent at runtime and must be treated as Tier-1 invariant violations.

## Suggested Fix

Add a `None` guard before the `"discard"` check and cover it with a unit test.

Example fix:

```python
on_validation_failure = source._on_validation_failure
if on_validation_failure is None:
    raise OrchestrationInvariantError(
        f"Source '{source.name}' has _on_validation_failure=None — this should be impossible since SourceDataConfig requires on_validation_failure"
    )
if on_validation_failure == "discard":
    return
```

Also add a test alongside [`tests/unit/engine/orchestrator/test_validation.py`](/home/john/elspeth/tests/unit/engine/orchestrator/test_validation.py) asserting `OrchestrationInvariantError` for `None`.

## Impact

When source injection is skipped or a programmatically constructed source forgets `_on_validation_failure`, the run fails with a misleading configuration error instead of an explicit framework-bug crash. That does not silently corrupt data, but it violates the repo’s crash-on-plugin-bug policy, slows diagnosis, and can send engineers hunting for nonexistent sink typos instead of fixing the real invariant break.
