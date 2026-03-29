## Summary

`deep_freeze()` treats any incoming `MappingProxyType` as safely frozen and may return it unchanged, so caller-owned mutable dict state can continue to mutate supposedly immutable contract objects.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/contracts/freeze.py
- Line(s): 52-56, 98-102
- Function/Method: `deep_freeze`, `freeze_fields`

## Evidence

`deep_freeze()` has a special-case fast path for `MappingProxyType`:

```python
# /home/john/elspeth/src/elspeth/contracts/freeze.py:52-56
if isinstance(value, MappingProxyType):
    frozen_map = {k: deep_freeze(v) for k, v in value.items()}
    if all(frozen_map[k] is value[k] for k in frozen_map):
        return value
    return MappingProxyType(frozen_map)
```

That logic assumes an incoming `MappingProxyType` is already a detached immutable snapshot. But `MappingProxyType` is only a read-only view; it can still point at a caller-owned mutable dict. When the values are scalars, `frozen_map[k] is value[k]` is true, so the function returns the original proxy unchanged.

`freeze_fields()` inherits the same bug because it skips reassignment when `deep_freeze()` returns the same object:

```python
# /home/john/elspeth/src/elspeth/contracts/freeze.py:98-102
for name in field_names:
    value = getattr(instance, name)
    frozen = deep_freeze(value)
    if frozen is not value:
        object.__setattr__(instance, name, frozen)
```

I verified the target-file behavior directly in this repo:

```python
from types import MappingProxyType
from elspeth.contracts.freeze import deep_freeze

src = {"k": "v"}
proxy = MappingProxyType(src)
frozen = deep_freeze(proxy)
assert frozen is proxy

src["k"] = "mutated"
src["new"] = "added"
assert dict(frozen) == {"k": "mutated", "new": "added"}
```

Observed output:

```text
deep_freeze_identity True
deep_freeze_contents {'k': 'mutated', 'new': 'added'}
```

The repo’s own contract says this is forbidden. `CLAUDE.md` explicitly calls out `MappingProxyType(self.x)` as wrong because it is a “view, not copy” and also warns that `MappingProxyType` is not evidence of deep freezing ([/home/john/elspeth/CLAUDE.md#L357](/home/john/elspeth/CLAUDE.md#L357)).

The current tests enshrine the unsafe behavior instead of catching it:

```python
# /home/john/elspeth/tests/unit/contracts/test_freeze.py:102-105
already = MappingProxyType({"k": "v"})
result = deep_freeze(already)
assert result is already
```

This is not just theoretical. A downstream contract object can drift after construction when it receives a shallow proxy; for example `CoalesceMetadata` changes after mutating the original dict behind a `MappingProxyType` ([/home/john/elspeth/src/elspeth/contracts/coalesce_metadata.py#L62](/home/john/elspeth/src/elspeth/contracts/coalesce_metadata.py#L62)).

## Root Cause Hypothesis

The implementation conflates “read-only wrapper” with “deeply frozen detached snapshot.” `MappingProxyType` preserves read-only access but does not encode whether it wraps a fresh copied dict or a caller-owned mutable one. Because `deep_freeze()` uses identity-preserving idempotency for proxies, it cannot distinguish safe proxies created by ELSPETH from unsafe shallow proxies created elsewhere, so it preserves aliasing that the deep-freeze contract is supposed to eliminate.

## Suggested Fix

Remove identity preservation for `MappingProxyType` inputs and always detach them into a fresh frozen mapping. For example:

```python
if isinstance(value, MappingProxyType):
    return MappingProxyType({k: deep_freeze(v) for k, v in value.items()})
```

Then add regression tests proving:

```python
src = {"k": "v"}
proxy = MappingProxyType(src)
frozen = deep_freeze(proxy)
assert frozen is not proxy
src["k"] = "mutated"
assert dict(frozen) == {"k": "v"}
```

Also update the existing tests in [/home/john/elspeth/tests/unit/contracts/test_freeze.py](/home/john/elspeth/tests/unit/contracts/test_freeze.py) and [/home/john/elspeth/tests/unit/contracts/test_freeze_regression.py](/home/john/elspeth/tests/unit/contracts/test_freeze_regression.py) so they no longer assert identity preservation for `MappingProxyType`.

## Impact

Any frozen dataclass that relies on `freeze_fields()` can silently retain aliases to caller-owned mappings if the caller passes a `MappingProxyType`. That breaks the repo’s frozen-dataclass immutability guarantee and can let audit-relevant contract data change after construction, undermining confidence that serialized metadata reflects the state at record time rather than later incidental mutations.
