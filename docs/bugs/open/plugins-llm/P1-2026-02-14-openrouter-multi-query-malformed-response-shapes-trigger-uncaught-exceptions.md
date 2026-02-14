## Summary

Malformed OpenRouter response shapes (`message.content` not `str`, `usage` not `dict`, or non-numeric `completion_tokens`) trigger uncaught exceptions in `_process_single_query` instead of returning `TransformResult.error`.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter_multi_query.py`
- Line(s): 303-321, 339
- Function/Method: `_process_single_query`

## Evidence

`_process_single_query` only checks `content is None`, then unconditionally does `content.strip()`:

```python
content = choices[0]["message"]["content"]
if content is None: ...
content_str = content.strip()
```

(`src/elspeth/plugins/llm/openrouter_multi_query.py:290-304,339`)

It also assumes `usage` is a dict:

```python
usage = data.get("usage") or {}
completion_tokens = usage.get("completion_tokens", 0)
if effective_max_tokens is not None and completion_tokens >= effective_max_tokens:
```

(`src/elspeth/plugins/llm/openrouter_multi_query.py:316-321`)

Repro (executed locally with mocked HTTP responses):
- `content` as dict -> `AttributeError: 'dict' object has no attribute 'strip'`
- `usage` as list -> `AttributeError: 'list' object has no attribute 'get'`
- `completion_tokens` as string with `max_tokens` set -> `TypeError: '>=' not supported between instances of 'str' and 'int'`

Uncaught exceptions are treated as plugin bugs and re-raised by engine:
- Wrapped in `ExceptionResult` (`src/elspeth/plugins/batching/mixin.py:250-264`)
- Re-raised in waiter (`src/elspeth/engine/batch_adapter.py:121-122`)
- Node state marked `FAILED` (`src/elspeth/engine/executors/transform.py:255-267`)

Coverage gap: tests cover `content=None` but not non-string `content` / malformed `usage` (`tests/unit/plugins/llm/test_openrouter_multi_query.py:996-1052`).

## Root Cause Hypothesis

Boundary validation is incomplete: the code validates presence of keys but not runtime types of external fields before string/dict operations.

## Suggested Fix

In `_process_single_query`, validate/coerce external fields immediately after extraction:
- Require `content` to be `str` (else `TransformResult.error(reason="malformed_response", ...)`)
- Require `usage` to be `dict` (or coerce `None` to `{}` only)
- Parse/validate token counts before comparison (e.g., `int(...)` with error handling, or hard-fail with structured error if invalid)

## Impact

A single malformed provider response can crash transform execution path instead of producing auditable row-level errors (`query_failed`). This breaks expected external-boundary resilience and turns data-quality problems into pipeline failures.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/openrouter_multi_query.py.md`
- Finding index in source report: 1
- Beads: pending
