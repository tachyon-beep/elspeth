## Summary

Aggregation checkpointing is lossy for mixed-contract batches: `AggregationExecutor` flushes live batches using each token’s own `SchemaContract`, but checkpoint save/restore collapses the whole batch to the first token’s contract, so resume can crash with `AuditIntegrityError` on otherwise valid buffered rows.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/executors/aggregation.py
- Line(s): 307-319, 634-665, 728-747
- Function/Method: `execute_flush`, `get_checkpoint_state`, `restore_from_checkpoint`

## Evidence

Live execution already treats contracts as per-token, not per-batch:

```python
# src/elspeth/engine/executors/aggregation.py:312-319
for row_dict, token in zip(buffered_rows, buffered_tokens, strict=True):
    contract = token.row_data.contract
    ...
    pipeline_rows.append(PipelineRow(row_dict, contract))
```

That means a buffered aggregation batch can legitimately contain tokens with different contracts.

Checkpoint save then throws that information away:

```python
# src/elspeth/engine/executors/aggregation.py:642-665
first_token_contract = node.tokens[0].row_data.contract
token_checkpoints = tuple(
    AggregationTokenCheckpoint(
        ...
        contract_version=t.row_data.contract.version_hash(),
    )
    for t in node.tokens
)

nodes[node_id] = AggregationNodeCheckpoint(
    ...
    contract=first_token_contract.to_checkpoint_format(),
)
```

Only the first token’s full contract is stored. Every token stores only a version hash.

Checkpoint restore reconstructs every buffered token with that single restored contract and hard-fails if any token had a different version:

```python
# src/elspeth/engine/executors/aggregation.py:728-747
restored_contract = SchemaContract.from_checkpoint(dict(node_checkpoint.contract))

for t in node_checkpoint.tokens:
    if t.contract_version != restored_contract.version_hash():
        raise AuditIntegrityError(...)
    row_data = PipelineRow(deep_thaw(t.row_data), restored_contract)
```

So a batch that is valid in-memory becomes un-restorable after checkpointing if contracts differ across buffered tokens.

Repository context supports that mixed contracts are a supported concept, not an impossible state. For example, sink batching explicitly merges contracts across tokens instead of assuming uniformity:

```python
# src/elspeth/engine/executors/sink.py:178-180
batch_contract = tokens[0].row_data.contract
for token in tokens[1:]:
    batch_contract = batch_contract.merge(token.row_data.contract)
```

Test coverage around aggregation checkpoints only exercises the single-contract case, so this regression path is currently unguarded: [tests/unit/engine/test_executors.py](/home/john/elspeth/tests/unit/engine/test_executors.py#L2469) to [tests/unit/engine/test_executors.py](/home/john/elspeth/tests/unit/engine/test_executors.py#L2548).

## Root Cause Hypothesis

`AggregationExecutor` assumes “all tokens in buffer share same contract” when serializing checkpoint state, but that invariant is neither enforced in `buffer_row()` nor used during live flush execution. The restore path therefore treats legitimate per-token contract diversity as checkpoint corruption.

## Suggested Fix

Change aggregation checkpoint persistence to preserve contract identity per buffered token instead of once per node.

Practical options:

```python
# Example direction
AggregationNodeCheckpoint(
    ...
    contracts_by_version={
        contract.version_hash(): contract.to_checkpoint_format()
        for contract in unique_contracts
    },
)

AggregationTokenCheckpoint(
    ...
    contract_version=t.row_data.contract.version_hash(),
)
```

Then restore each token with the contract selected by its own `contract_version`.

Also add a regression test that buffers two tokens with different contracts, runs `get_checkpoint_state() -> restore_from_checkpoint()`, and verifies `execute_flush()` still succeeds after resume.

## Impact

Crash recovery for aggregation is broken when a buffered batch contains heterogeneous contracts, which is plausible with observed/flexible schemas or upstream contract evolution. On resume, ELSPETH can reject its own checkpoint as “corrupted,” leaving buffered batch state unrecoverable and breaking the checkpoint/recovery guarantee for that run.
