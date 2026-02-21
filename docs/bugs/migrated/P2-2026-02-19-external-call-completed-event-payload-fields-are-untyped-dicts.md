## Summary

`ExternalCallCompleted` in `contracts/events.py` has three dict-typed payload fields — `request_payload`, `response_payload`, and `token_usage` — all typed as `dict[str, Any] | None`. These are deep-copied in `__post_init__()` for immutability but lack semantic structure. They represent a unified concept (external call observation data) that could be a dedicated type.

## Severity

- Severity: moderate
- Priority: P2

## Location

- File: `src/elspeth/contracts/events.py` — Lines 346-348

## Evidence

```python
@dataclass(frozen=True, slots=True)
class ExternalCallCompleted:
    # ... other fields ...
    request_payload: dict[str, Any] | None = None   # Line 346
    response_payload: dict[str, Any] | None = None   # Line 347
    token_usage: dict[str, int] | None = None         # Line 348
```

These three fields are always set together (or all None) at every emission site in `plugins/clients/llm.py` and `plugins/clients/http.py`. The `__post_init__` method deep-copies all three independently.

## Proposed Fix

Consider grouping into a dedicated frozen dataclass:

```python
@dataclass(frozen=True, slots=True)
class ExternalCallPayload:
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    token_usage: dict[str, int] | None = None
```

This simplifies `__post_init__` (one deep-copy instead of three) and makes the "set together or not at all" invariant explicit. However, evaluate whether this adds value vs. the current approach — the current three separate fields are clear and well-named.

## Affected Subsystems

- `contracts/events.py` — definition
- `plugins/clients/llm.py` — emission (2 sites: success + error)
- `plugins/clients/http.py` — emission
- `telemetry/` — consumption
