## Summary

`CollectionReadinessResult` forces probes to fabricate `count=0` for “count unknown” outcomes, so missing collections, malformed probe responses, and empty collections collapse into the same contract state.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/contracts/probes.py
- Line(s): 23-33
- Function/Method: `CollectionReadinessResult.__post_init__`

## Evidence

`CollectionReadinessResult` requires `count: int` and rejects only negative values, while also enforcing `reachable=False -> count=0`:

```python
# /home/john/elspeth/src/elspeth/contracts/probes.py:23-33
collection: str
reachable: bool
count: int
message: str

def __post_init__(self) -> None:
    if not self.collection:
        raise ValueError("collection must not be empty")
    require_int(self.count, "count", min_value=0)
    if not self.reachable and self.count != 0:
        raise ValueError(...)
```

That contract leaves providers no honest way to represent “the probe could not determine the count”. The implementations are already forced into fabrication:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py:328-349
if response.status_code == 404:
    return CollectionReadinessResult(..., reachable=True, count=0, message="Index ... not found")

try:
    count = int(response.text.strip())
except ValueError:
    return CollectionReadinessResult(..., reachable=True, count=0, message="... non-integer $count body ...")
```

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/probe_factory.py:76-91
except chromadb.errors.NotFoundError:
    return CollectionReadinessResult(..., reachable=True, count=0, message="Collection ... not found")
except (...):
    return CollectionReadinessResult(..., reachable=False, count=0, message="Collection ... unreachable ...")
```

The tests explicitly codify this collapse:

- `/home/john/elspeth/tests/unit/plugins/infrastructure/clients/retrieval/test_azure_search.py:395-415`
- `/home/john/elspeth/tests/unit/plugins/infrastructure/clients/retrieval/test_azure_search.py:450-460`

Those assert `count == 0` for:
- genuinely empty index
- 404 not found
- malformed non-integer `$count` body

Downstream, commencement gates only receive `reachable` and `count`; the distinguishing `message` is discarded:

```python
# /home/john/elspeth/src/elspeth/engine/bootstrap.py:87-94
for probe in probes:
    result = probe.probe()
    probe_results[result.collection] = {
        "reachable": result.reachable,
        "count": result.count,
    }
```

Real gate configs therefore branch on fabricated data:

```yaml
# /home/john/elspeth/tests/integration/pipeline/test_rag_indexed_smoke.py:104-106
commencement_gates:
- name: corpus_ready
  condition: "collections['smoke-test-facts']['count'] > 0"
```

Per `CLAUDE.md`, absent external data must be recorded as absence, not invented defaults. Here “unknown count” is being recorded as a confident zero.

## Root Cause Hypothesis

The contract modeled readiness as only two dimensions, `reachable` and `count`, with `count` required to be a non-negative integer. That works for “reachable with known count”, but it cannot represent “reachable but collection absent” or “reachable but probe response malformed”. Because the contract forbids `None` or an explicit status field, every caller is pushed toward `count=0`, which silently changes “unknown” into “empty”.

## Suggested Fix

Change the contract so unknown counts are representable without fabrication.

A robust fix in this file would be:
- make `count` nullable: `count: int | None`
- validate `count` with `require_int(..., optional=True, min_value=0)`
- reject contradictory states such as `reachable=False and count is not None`
- add an explicit status/existence field, e.g. `status: Literal["ready", "empty", "missing", "unreachable", "invalid_response"]` or `exists: bool | None`

Example shape:

```python
@dataclass(frozen=True, slots=True)
class CollectionReadinessResult:
    collection: str
    reachable: bool
    count: int | None
    status: Literal["ready", "empty", "missing", "unreachable", "invalid_response"]
    message: str

    def __post_init__(self) -> None:
        if not self.collection:
            raise ValueError("collection must not be empty")
        if not self.message:
            raise ValueError("message must not be empty")
        require_int(self.count, "count", optional=True, min_value=0)
        if not self.reachable and self.count is not None:
            raise ValueError("Unreachable collections must report count=None")
```

Then update probe implementations and gate/bootstrap plumbing to preserve that richer state instead of collapsing everything to `{reachable, count}`.

## Impact

This violates the Tier 3 rule against fabrication at the external boundary. The audit trail can record `count=0` even when the system never learned the count, and commencement gates evaluate against that fabricated zero. In practice:
- a missing collection is indistinguishable from an empty collection in gate context
- a malformed `$count` response is indistinguishable from a genuinely empty index
- audit records overstate certainty about external system state
- operators cannot write accurate gates for “must exist” vs “may exist but be empty” scenarios
