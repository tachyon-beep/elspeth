# Verification Report: P0 Source Row Payloads Never Persisted

## Status: VERIFIED

This is a **real bug** that violates ELSPETH's non-negotiable auditability requirements.

---

## Bug Summary

Source row payloads are never persisted during normal pipeline runs. The `rows.source_data_ref` column remains NULL, and `get_row_data()` returns `NEVER_STORED`. This directly violates the "Data storage points" requirement in CLAUDE.md:

> **Source entry** - Raw data stored before any processing

---

## Code Evidence

### Root Cause: TokenManager Never Passes payload_ref

**File:** `/home/john/elspeth-rapid/src/elspeth/engine/tokens.py`
**Lines:** 73-78

```python
def create_initial_token(
    self,
    run_id: str,
    source_node_id: str,
    row_index: int,
    row_data: dict[str, Any],
) -> TokenInfo:
    # Create row record
    row = self._recorder.create_row(
        run_id=run_id,
        source_node_id=source_node_id,
        row_index=row_index,
        data=row_data,
        # NOTE: payload_ref is NOT passed here!
    )
```

The `create_row()` method accepts an optional `payload_ref` parameter, but `TokenManager.create_initial_token()` never stores the payload to a `PayloadStore` and never passes the reference.

### The Unlinked create_row Signature

**File:** `/home/john/elspeth-rapid/src/elspeth/core/landscape/recorder.py`
**Lines:** 694-727

```python
def create_row(
    self,
    run_id: str,
    source_node_id: str,
    row_index: int,
    data: dict[str, Any],
    *,
    row_id: str | None = None,
    payload_ref: str | None = None,  # Optional, defaults to None
) -> Row:
    ...
    row = Row(
        ...
        source_data_ref=payload_ref,  # Always None in normal runs
        ...
    )
```

### get_row_data Returns NEVER_STORED

**File:** `/home/john/elspeth-rapid/src/elspeth/core/landscape/recorder.py`
**Lines:** 1821-1826

```python
def get_row_data(self, row_id: str) -> RowDataResult:
    row = self.get_row(row_id)
    if row is None:
        return RowDataResult(state=RowDataState.ROW_NOT_FOUND, data=None)

    if row.source_data_ref is None:
        return RowDataResult(state=RowDataState.NEVER_STORED, data=None)
```

Since `source_data_ref` is always NULL, this always returns `NEVER_STORED`.

### Call Chain from Orchestrator to TokenManager

**File:** `/home/john/elspeth-rapid/src/elspeth/engine/orchestrator.py`
**Lines:** 788-802 (in _execute_run)**

The orchestrator iterates through source rows and calls `processor.process_row()`, which eventually calls `TokenManager.create_initial_token()`. At no point in this chain is:

1. A `PayloadStore` instance passed to `TokenManager`
2. The row payload serialized and stored
3. A `payload_ref` generated and passed to `create_row()`

### PayloadStore Exists But Is Unused During Run

**File:** `/home/john/elspeth-rapid/src/elspeth/core/payload_store.py`

The `PayloadStore` protocol and `FilesystemPayloadStore` implementation exist and work correctly. However:

- `Orchestrator.__init__()` does not accept a `PayloadStore`
- `Orchestrator.run()` does not accept a `PayloadStore`
- The CLI's `run` command does not instantiate or wire a `PayloadStore`

The only place `PayloadStore` is used is:
- `resume` command (for recovery, reads stored payloads)
- `purge` command (for retention, deletes old payloads)

---

## Impact Analysis

### Severity: P0 (Critical)

1. **Audit Trail Incomplete**: Every row in the system is missing its raw source data. The hash (`source_data_hash`) exists but the actual data does not. This violates CLAUDE.md's explicit requirement:
   > "Source entry - Raw data stored before any processing"

2. **Resume/Recovery Fails**: `RecoveryManager.get_unprocessed_row_data()` depends on retrieving payloads via `source_data_ref`. Since it's always NULL, resume operations fail.

3. **explain() Cannot Show Raw Input**: The `explain()` feature cannot show what the source row actually contained - only its hash. This undermines the core promise:
   > "For any output, the system must prove complete lineage"

4. **Evidence Tampering Risk**: Without raw data storage, auditors cannot verify that the hash corresponds to actual input. The audit trail is cryptographically signed but semantically incomplete.

---

## Comparison with Transform and Call Data

Interestingly, **transform outputs and external call payloads ARE stored**:

- `record_call()` in recorder.py stores request/response payloads
- Node state outputs are hashed and stored

This inconsistency means:
- You can see what an LLM returned for a classification
- You CANNOT see what source row triggered that classification

---

## Confirmation: This Is Truly P0

From CLAUDE.md's "Auditability Standard":

> Every decision must be traceable to source data, configuration, and code version

Without raw source data persistence:
- Traceability to source data is **impossible** after payload retention expires (or never, since payloads are never stored)
- The audit answer "I don't know what happened" becomes inevitable for any source-level question

The bug catalog correctly identifies this as P0.

---

## Fix Approach (For Reference)

The fix requires:

1. **Orchestrator** must accept and use a `PayloadStore`
2. **TokenManager** (or `create_row`) must serialize row data to `PayloadStore` and pass the `payload_ref`
3. **CLI run command** must instantiate `FilesystemPayloadStore` from settings and pass it through

Example conceptual fix in `TokenManager.create_initial_token()`:

```python
def create_initial_token(
    self,
    run_id: str,
    source_node_id: str,
    row_index: int,
    row_data: dict[str, Any],
    payload_store: PayloadStore | None = None,  # NEW
) -> TokenInfo:
    # Store payload if store configured
    payload_ref = None
    if payload_store is not None:
        payload_bytes = json.dumps(row_data).encode("utf-8")
        payload_ref = payload_store.store(payload_bytes)

    row = self._recorder.create_row(
        run_id=run_id,
        source_node_id=source_node_id,
        row_index=row_index,
        data=row_data,
        payload_ref=payload_ref,  # NOW PASSED
    )
    ...
```

---

## Conclusion

**VERIFIED**: The P0 bug "Source Row Payloads Never Persisted" is real. The code paths exist for payload storage, but they are never invoked during normal pipeline execution. This directly contradicts ELSPETH's documented audit requirements and should be fixed before any production use of the system.
