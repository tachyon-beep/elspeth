## Summary

`elspeth.contracts.config` drops `ServiceRateLimitProtocol` from its public re-export surface, so callers using the package façade cannot import the protocol that `RuntimeRateLimitProtocol.get_service_config()` publicly returns.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/contracts/config/__init__.py
- Line(s): 56-62, 89-110
- Function/Method: module import surface / `__all__`

## Evidence

`protocols.py` defines `ServiceRateLimitProtocol` and uses it in the public `RuntimeRateLimitProtocol` contract:

```python
# src/elspeth/contracts/config/protocols.py
class ServiceRateLimitProtocol(Protocol):
    @property
    def requests_per_minute(self) -> int: ...

class RuntimeRateLimitProtocol(Protocol):
    def get_service_config(self, service_name: str) -> ServiceRateLimitProtocol: ...
```

Evidence:
- `/home/john/elspeth/src/elspeth/contracts/config/protocols.py:80-87`
- `/home/john/elspeth/src/elspeth/contracts/config/protocols.py:117-119`

But `__init__.py` re-exports other runtime protocols and omits this one:

```python
from elspeth.contracts.config.protocols import (
    RuntimeCheckpointProtocol,
    RuntimeConcurrencyProtocol,
    RuntimeRateLimitProtocol,
    RuntimeRetryProtocol,
    RuntimeTelemetryProtocol,
)
...
__all__ = [
    ...
    "RuntimeRateLimitProtocol",
    ...
]
```

Evidence:
- `/home/john/elspeth/src/elspeth/contracts/config/__init__.py:56-62`
- `/home/john/elspeth/src/elspeth/contracts/config/__init__.py:89-110`

The omission is observable at runtime:

```python
import elspeth.contracts.config as c
'ServiceRateLimitProtocol' in dir(c)  # False
from elspeth.contracts.config import ServiceRateLimitProtocol
# ImportError: cannot import name 'ServiceRateLimitProtocol'
```

I verified that import failure locally against this repo.

What the code does:
- Presents `elspeth.contracts.config` as the package façade for runtime config contracts.
- Re-exports most protocol/dataclass surface.

What it should do:
- Re-export the complete public protocol surface used by that façade, including `ServiceRateLimitProtocol`, because `RuntimeRateLimitProtocol` exposes it in its method signature.

## Root Cause Hypothesis

`__init__.py` appears to have been treated as a curated convenience export list, but the curation missed the helper protocol nested under rate-limiting. Because tests in `/home/john/elspeth/tests/unit/contracts/test_config.py:42-68` hard-code the expected export set and also omit `ServiceRateLimitProtocol`, the incomplete façade is currently locked in by test coverage rather than detected as a contract gap.

## Suggested Fix

Add `ServiceRateLimitProtocol` to the package re-export list and `__all__` in `/home/john/elspeth/src/elspeth/contracts/config/__init__.py`.

Helpful shape:

```python
from elspeth.contracts.config.protocols import (
    RuntimeCheckpointProtocol,
    RuntimeConcurrencyProtocol,
    RuntimeRateLimitProtocol,
    RuntimeRetryProtocol,
    RuntimeTelemetryProtocol,
    ServiceRateLimitProtocol,
)
...
__all__ = [
    ...
    "RuntimeRateLimitProtocol",
    "RuntimeRetryProtocol",
    "RuntimeTelemetryProtocol",
    "ServiceRateLimitProtocol",
    ...
]
```

A follow-up test update in `/home/john/elspeth/tests/unit/contracts/test_config.py` should assert the new export so the façade stays complete.

## Impact

The bug breaks the public package contract for config protocols: any caller that imports from `elspeth.contracts.config` as the documented façade cannot reference the return type of `RuntimeRateLimitProtocol.get_service_config()` without reaching into the private submodule path. This does not corrupt audit data, but it does create an inconsistent protocol surface and an avoidable integration failure at import time.
