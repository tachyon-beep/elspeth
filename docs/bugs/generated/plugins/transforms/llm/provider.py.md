## Summary

`parse_finish_reason()` logs per-call finish-reason anomalies to `structlog`, duplicating row-level LLM outcome evidence outside the Landscape audit trail.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/llm/provider.py
- Line(s): 62-90
- Function/Method: `parse_finish_reason`

## Evidence

`parse_finish_reason()` emits a warning whenever a provider returns an unknown finish reason:

```python
except ValueError:
    logger.warning(
        "Unknown LLM finish_reason — will be rejected by transform (fail-closed)",
        finish_reason=raw,
        known_values=[e.value for e in FinishReason],
        action="Add to FinishReason enum if this is a known-good completion reason. "
        "Unrecognized finish reasons are rejected as errors by LLMTransform.",
    )
    return UnrecognizedFinishReason(raw)
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/provider.py:82-90`

That warning is emitted on the hot path for individual LLM calls. The repo’s logging policy explicitly forbids logging row-level decisions and call results because they belong in Landscape, not logs:

- `/home/john/elspeth/.agents/skills/logging-telemetry-policy/SKILL.md`
- Forbidden uses include “Logging row-level decisions” and “Logging call results”.

The transform already records this same fact in the audit trail by converting unknown finish reasons into structured `TransformResult.error(...)` payloads:

- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:164-179`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:307-321`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:593-608`

So the code currently does both:
1. Persist the probative result in Landscape.
2. Also log the per-row/provider outcome.

What it should do instead is record the finish reason only through the existing audit path.

## Root Cause Hypothesis

The helper was written as if unknown finish reasons were primarily an operational warning, but in this subsystem finish reasons are probative per-call data. The transform already fail-closes and persists that outcome, so the extra logger call violates the project’s “audit first, logs last” rule.

## Suggested Fix

Remove the `logger.warning(...)` call from `parse_finish_reason()` and let the returned `UnrecognizedFinishReason` flow into the existing audit/error handling in `transform.py`.

If operational visibility is still needed, emit aggregate telemetry elsewhere, not per-row logs. The helper can simply do:

```python
except ValueError:
    return UnrecognizedFinishReason(raw)
```

Update the tests in `/home/john/elspeth/tests/unit/plugins/llm/test_provider_protocol.py` accordingly, since they currently assert on the warning side effect.

## Impact

This does not corrupt the Landscape record, but it creates an observability policy violation:
- Per-row LLM outcomes leak into logs.
- Logs become a second, partial record of call behavior.
- Operators may rely on ephemeral log lines for evidence that should only live in the audit trail.
---
## Summary

`LLMQueryResult` does not validate its typed fields (`usage` and `finish_reason`), so provider contract violations are accepted at DTO construction time and explode later in the transform with misleading failures.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/llm/provider.py
- Line(s): 93-117
- Function/Method: `LLMQueryResult.__post_init__`

## Evidence

`LLMQueryResult` claims that usage is already normalized and finish reason is already parsed:

```python
@dataclass(frozen=True, slots=True)
class LLMQueryResult:
    ...
    content: str
    usage: TokenUsage
    model: str
    finish_reason: ParsedFinishReason = None

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("LLMQueryResult.content must be non-empty (whitespace-only rejected)")
        if not self.model or not self.model.strip():
            raise ValueError("LLMQueryResult.model must be non-empty")
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/llm/provider.py:93-117`

But it never verifies that:
- `usage` is actually a `TokenUsage`
- `finish_reason` is actually `FinishReason | UnrecognizedFinishReason | None`

Downstream code assumes those contracts are true. For example, single-query success unconditionally calls `result.usage.to_dict()`:

- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:371-375`

And the finish-reason logic assumes the parsed union, with a fallback `str(...)` branch that should be unreachable:

- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:83-101`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:147-179`

Concrete failure modes if a provider constructs an invalid DTO:
- `usage={"prompt_tokens": 1}` passes `LLMQueryResult` construction, then crashes later with `AttributeError: 'dict' object has no attribute 'to_dict'`.
- `finish_reason="stop"` passes construction, then `_finish_reason_error()` treats it as an unexpected finish reason because it is not `FinishReason.STOP`.

Those are contract violations that should be rejected immediately at the provider boundary, not deferred to unrelated transform code.

## Root Cause Hypothesis

`LLMQueryResult` only enforces the easy string invariants and relies on static typing for the rest. In practice this DTO is the runtime boundary between provider implementations and the transform, so it needs runtime validation to fail fast on bad provider outputs.

## Suggested Fix

Harden `LLMQueryResult.__post_init__` to validate all fields at construction time, for example:

```python
def __post_init__(self) -> None:
    if not self.content or not self.content.strip():
        raise ValueError("LLMQueryResult.content must be non-empty (whitespace-only rejected)")
    if not self.model or not self.model.strip():
        raise ValueError("LLMQueryResult.model must be non-empty")
    if not isinstance(self.usage, TokenUsage):
        raise TypeError(f"usage must be TokenUsage, got {type(self.usage).__name__}")
    if self.finish_reason is not None and not isinstance(
        self.finish_reason, (FinishReason, UnrecognizedFinishReason)
    ):
        raise TypeError(
            f"finish_reason must be FinishReason | UnrecognizedFinishReason | None, "
            f"got {type(self.finish_reason).__name__}"
        )
```

Tests should also be added for invalid `usage` and invalid `finish_reason` construction.

## Impact

When a provider violates the contract, the failure currently appears later and in the wrong place:
- transforms crash with opaque attribute/type errors,
- valid completions can be misclassified as failures,
- debugging points at transform code instead of the bad provider output.

That weakens the plugin contract boundary and makes provider regressions harder to diagnose cleanly.
