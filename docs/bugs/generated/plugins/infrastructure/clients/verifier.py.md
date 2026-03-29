## Summary

Hash-based verification after payload loss ignores the verifier’s configured comparison rules (`ignore_paths` and `ignore_order`), so runs with purged or hash-only baselines can report false drift that full-payload verification would correctly treat as a match.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [verifier.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/verifier.py)
- Line(s): 330-355, 399-404
- Function/Method: `CallVerifier.verify`

## Evidence

[verifier.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/verifier.py#L330) takes the hash-only path for `PURGED`, `STORE_NOT_CONFIGURED`, and `HASH_ONLY` states:

```python
if call.response_hash is not None:
    live_hash = stable_hash(live_response)
    is_match = live_hash == call.response_hash
```

That path never applies either of the comparison options configured on the verifier.

By contrast, the full-payload path at [verifier.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/verifier.py#L399) does honor both settings:

```python
diff = DeepDiff(
    recorded_response,
    live_response,
    ignore_order=self._ignore_order,
    exclude_paths=self._ignore_paths,
)
```

The baseline `response_hash` is recorded over the entire response payload, with no exclusions or order normalization, in [execution_repository.py](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L534):

```python
response_dict = response_data.to_dict() if response_data is not None else None
response_hash = stable_hash(response_dict) if response_dict is not None else None
```

And `stable_hash()` is order-sensitive for lists because it hashes canonical JSON directly, not a DeepDiff-normalized structure, as shown in [canonical.py](/home/john/elspeth/src/elspeth/core/canonical.py#L181).

This creates an observable inconsistency with the verifier’s documented/tested behavior:

- [test_verifier.py](/home/john/elspeth/tests/unit/plugins/clients/test_verifier.py#L283) verifies that `ignore_paths=["root['latency']"]` makes two otherwise-equal responses match when the payload is available.
- [test_verifier.py](/home/john/elspeth/tests/unit/plugins/clients/test_verifier.py#L744) and [test_verifier.py](/home/john/elspeth/tests/unit/plugins/clients/test_verifier.py#L910) verify that list order is ignored by default and can be made strict via `ignore_order=False`.
- [test_verifier.py](/home/john/elspeth/tests/unit/plugins/clients/test_verifier.py#L570) only covers hash-based verification with exact payload equality; there is no coverage for ignored fields or ignored ordering once the verifier falls back to hashes.

What the code does:
- Full payload present: compare with `DeepDiff`, respecting ignore settings.
- Payload missing: compare full-response hashes, ignoring the ignore settings.

What it should do:
- A response difference that the caller explicitly configured to ignore should not become a mismatch solely because the baseline payload was purged or stored hash-only.

## Root Cause Hypothesis

The verifier treats “payload unavailable but hash survives” as if exact hash equality were interchangeable with the normal DeepDiff-based semantic comparison. It is not interchangeable once `ignore_paths` or `ignore_order` are in play, because those settings define a looser equivalence relation than raw canonical hashing.

## Suggested Fix

In [verifier.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/verifier.py), do not classify a hash mismatch as real drift when semantic comparison settings cannot be honored.

A safe fix in this file is:

- If `call.response_hash is not None` and both `self._ignore_paths` is empty and `self._ignore_order` is `False`-equivalent to exact comparison, keep the current hash-based match/mismatch logic.
- Otherwise, return a non-match/non-difference “cannot semantically verify from hash only” result, or add an explicit result flag for “verification inconclusive due to missing payload under non-exact comparison settings”.

At minimum, add tests covering:
- `ignore_paths` with `CallDataState.PURGED` or `HASH_ONLY`
- `ignore_order=True` with `CallDataState.PURGED` or `HASH_ONLY`

## Impact

Verify mode can raise false drift alerts in exactly the retention scenarios it is supposed to support: purged payloads, attributable-only runs, or environments without payload-store access. That undermines trust in verification reports, inflates mismatch counts, and breaks the contract that payload deletion should preserve meaningful verifiability rather than silently tightening comparison semantics.
