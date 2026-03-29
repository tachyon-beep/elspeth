## Summary

`elspeth.plugins.infrastructure.clients` advertises package-level replay imports, but it does not re-export `ReplayPayloadMissingError`, so callers cannot catch the replay mode failure that `CallReplayer` actually raises.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/__init__.py`
- Line(s): 55-79
- Function/Method: Module export surface (`__all__`)

## Evidence

[`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/__init__.py:55`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/__init__.py#L55) imports only `CallReplayer`, `ReplayedCall`, and `ReplayMissError` from `replayer.py`, and [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/__init__.py:66`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/__init__.py#L66) omits `ReplayPayloadMissingError` from `__all__`.

But [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/replayer.py:86`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/replayer.py#L86) defines `ReplayPayloadMissingError`, and [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/replayer.py:242`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/replayer.py#L242) and [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/replayer.py:249`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/replayer.py#L249) raise it for missing/purged payloads.

Confirmed directly from the package boundary:

```python
from elspeth.plugins.infrastructure.clients import ReplayPayloadMissingError
```

raises:

```text
ImportError: cannot import name 'ReplayPayloadMissingError'
```

So the package-level API exposes the success path (`CallReplayer`) but not one of its documented runtime failure types.

## Root Cause Hypothesis

`__init__.py` was treated as a convenience barrel file, but its re-exports were not kept aligned with the replay client's actual exception contract. The module exports `ReplayMissError` but forgot the second replay-specific exception added later.

## Suggested Fix

Re-export `ReplayPayloadMissingError` from the package root and include it in `__all__`.

Helpful shape:

```python
from elspeth.plugins.infrastructure.clients.replayer import (
    CallReplayer,
    ReplayedCall,
    ReplayMissError,
    ReplayPayloadMissingError,
)
```

and add `"ReplayPayloadMissingError"` to `__all__`.

## Impact

Replay-mode callers following the package’s flat import pattern cannot catch the “payload was recorded metadata-only / later purged” failure path. That turns a typed operational condition into an import-time contract break, making replay integrations harder to write correctly and violating the package’s public API consistency.
---
## Summary

`elspeth.plugins.infrastructure.clients` does not re-export the typed LLM exceptions (`ContentPolicyError`, `ContextLengthError`, `NetworkError`, `ServerError`) even though the package already presents itself as the top-level client API and already re-exports only a partial subset of LLM errors.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/__init__.py`
- Line(s): 49-79
- Function/Method: Module export surface (`__all__`)

## Evidence

[`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/__init__.py:49`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/__init__.py#L49) re-exports `AuditedLLMClient`, `LLMClientError`, `LLMResponse`, and `RateLimitError`, but not the other typed LLM exceptions defined in [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py:91`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py#L91), [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py:102`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py#L102), [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py:120`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py#L120), and [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py:131`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py#L131).

The LLM provider contract explicitly relies on those exception types at [`/home/john/elspeth/src/elspeth/plugins/transforms/llm/provider.py:123`](/home/john/elspeth/src/elspeth/plugins/transforms/llm/provider.py#L123).

Confirmed directly:

```python
from elspeth.plugins.infrastructure.clients import ContentPolicyError
```

raises:

```text
ImportError: cannot import name 'ContentPolicyError'
```

This is not just “not in `__all__`”; the symbols are absent from the package namespace entirely.

## Root Cause Hypothesis

The barrel file was frozen around the earliest exported LLM types and never updated when additional typed exceptions were added to `llm.py`. That leaves the package root with a partial, misleading exception surface.

## Suggested Fix

Import and export the full typed LLM exception set from `llm.py`:

```python
from elspeth.plugins.infrastructure.clients.llm import (
    AuditedLLMClient,
    ContentPolicyError,
    ContextLengthError,
    LLMClientError,
    LLMResponse,
    NetworkError,
    RateLimitError,
    ServerError,
)
```

and add those names to `__all__`.

## Impact

Any consumer standardizing on package-root imports can catch `RateLimitError` but not the other documented LLM failure modes that drive retry vs. terminal handling. That creates an inconsistent API boundary and makes correct error handling depend on knowing internal submodule paths instead of the advertised package surface.
