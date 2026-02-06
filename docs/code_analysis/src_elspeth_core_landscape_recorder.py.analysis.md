# Analysis: src/elspeth/core/landscape/recorder.py

**Lines:** 3,233
**Role:** The audit trail recorder -- backbone of ELSPETH's accountability system. LandscapeRecorder is the high-level API for recording every pipeline operation (runs, nodes, edges, rows, tokens, node states, routing events, batches, artifacts, calls, operations, errors, and token outcomes) into a SQLAlchemy-backed database. It is the legal record of what the pipeline did.
**Key dependencies:**
- Imports from: `elspeth.contracts` (audit dataclasses, enums, errors, contract_records), `elspeth.core.canonical` (canonical_json, stable_hash, repr_hash), `elspeth.core.landscape._database_ops` (DatabaseOps), `elspeth.core.landscape._helpers` (generate_id, now), `elspeth.core.landscape.database` (LandscapeDB), `elspeth.core.landscape.repositories` (all Repository classes), `elspeth.core.landscape.row_data` (RowDataResult, RowDataState), `elspeth.core.landscape.schema` (all table definitions), `elspeth.core.security.fingerprint` (secret_fingerprint), `sqlalchemy.select`
- Imported by: `elspeth.engine.orchestrator`, `elspeth.engine.processor`, `elspeth.engine.executors`, `elspeth.core.landscape.exporter`, `elspeth.core.landscape.lineage`, `elspeth.plugins.clients.*` (audited clients), `elspeth.tui.*`, CLI commands
**Analysis depth:** FULL

## Summary

LandscapeRecorder is a well-structured, large-but-not-complex class with clear method boundaries and strong Tier 1 data integrity enforcement. The code generally follows the project's Data Manifesto correctly: it crashes on corruption of its own data, validates enum types at load time, uses canonical JSON for hashing, and wraps operations atomically where required (fork_token, expand_token, coalesce_tokens). However, I identified one critical race condition in `complete_operation()`, several warning-level issues around truthiness-based filtering, unbounded memory growth in call index dictionaries, and a silent swallow of `json.JSONDecodeError` in `explain_row()` that could mask Tier 1 data corruption. The overall quality is high for a file of this size.

## Critical Findings

### [2417-2427] TOCTOU race in complete_operation() double-complete guard

**What:** The `complete_operation()` method has a check-then-act pattern that is not atomic. It first reads the current status of an operation in one transaction (line 2418-2419 via `execute_fetchone`, which uses its own `with self._db.connection()` block), then later updates it in a separate transaction (line 2435-2444 via `execute_update`, which opens a new connection). Between the read and the write, another thread or process could complete the same operation, bypassing the double-complete guard.

**Why it matters:** In a concurrent pipeline execution scenario (pooled transforms with thread pools), two threads could both read the operation as "open" and both proceed to complete it. The second completion would overwrite the first with potentially different status, output_data, or error information. This directly corrupts the audit trail -- the legal record would reflect the last writer's data, silently destroying the first completion's evidence. The database-level check constraint on operations does not prevent this because the status column has no unique constraint preventing overwrites.

**Evidence:**
```python
# Line 2418-2419: Read in transaction A
query = select(operations_table.c.status).where(operations_table.c.operation_id == operation_id)
current = self._ops.execute_fetchone(query)  # Opens and closes a connection

# ... arbitrary delay between transactions ...

# Line 2435-2444: Write in transaction B (separate connection)
self._ops.execute_update(
    operations_table.update()
    .where(operations_table.c.operation_id == operation_id)
    .values(status=status, ...)
)
```

Each call to `_ops.execute_fetchone` and `_ops.execute_update` opens its own `with self._db.connection()` block (see `_database_ops.py` lines 27-29 and 53-57), so the read and write happen in different transactions with no locking.

### [2662] Silent swallow of json.JSONDecodeError in explain_row() masks Tier 1 corruption

**What:** The `explain_row()` method catches `json.JSONDecodeError` when loading payload data from the payload store and silently returns `payload_available=False`. However, the payload data was written by THIS SYSTEM (via `create_row()` at line 962, which uses `canonical_json(data).encode("utf-8")`). If the data we wrote is not valid JSON when we read it back, that indicates Tier 1 data corruption -- either the payload store is corrupted, there was a partial write, or tampering has occurred.

**Why it matters:** Per the Data Manifesto: "Bad data in the audit trail = crash immediately" and "If we read garbage from our own database, something catastrophic happened." By silently returning `payload_available=False`, the system treats corruption the same as legitimate payload purging. An investigator running `elspeth explain` would see "payload unavailable" instead of being alerted to corruption. This violates the core auditability principle: "I don't know what happened" is never an acceptable answer.

**Evidence:**
```python
# Line 2662
except (KeyError, json.JSONDecodeError, OSError):
    # Payload has been purged or is corrupted
    # KeyError: raised by PayloadStore when content not found
    # JSONDecodeError: content corrupted  <-- THIS IS TIER 1 CORRUPTION
    # OSError: filesystem issues
    pass
```

`KeyError` (payload purged) is legitimate graceful degradation. `json.JSONDecodeError` (our own data is corrupt) should crash or at minimum log at ERROR level. `OSError` is ambiguous -- transient filesystem issues are different from corruption.

## Warnings

### [1690-1694] Truthiness-based filtering loses legitimate falsy values in update_batch_status()

**What:** Lines 1690-1694 use bare truthiness checks (`if trigger_type:`, `if trigger_reason:`, `if state_id:`) to decide whether to include fields in the update dict. This means legitimate falsy values like empty strings would be silently dropped. While these specific fields are unlikely to be empty strings in practice, the pattern is inconsistent with the Tier 1 strictness principle.

**Why it matters:** If a `TriggerType` enum ever included a falsy string value, or if `trigger_reason` were legitimately an empty string for "no reason needed" triggers, the update would silently skip storing that value. More critically, this pattern creates a precedent that could be copy-pasted to other methods where falsy values ARE meaningful. The `complete_batch()` method at line 1729 correctly uses `trigger_type.value if trigger_type else None`, showing the codebase is inconsistent on this pattern.

**Evidence:**
```python
# Line 1690-1695 (update_batch_status)
if trigger_type:      # Would skip TriggerType with falsy .value
    updates["trigger_type"] = trigger_type.value
if trigger_reason:    # Would skip empty string trigger_reason
    updates["trigger_reason"] = trigger_reason
if state_id:          # Would skip empty string state_id
    updates["aggregation_state_id"] = state_id
```

Compare with `complete_batch()` at line 1729 which uses explicit None check:
```python
trigger_type=trigger_type.value if trigger_type else None,
```

The same pattern appears at lines 1776-1778 (`get_batches`) and 1943 (`get_artifacts`).

### [143-148] Unbounded memory growth in call index dictionaries

**What:** The `_call_indices` and `_operation_call_indices` dictionaries grow monotonically for the lifetime of the LandscapeRecorder instance. Every unique `state_id` and `operation_id` gets an entry that is never removed. For a pipeline processing millions of rows (each generating a state_id per transform step), these dictionaries could grow to hold millions of entries.

**Why it matters:** In a long-running pipeline with 1M rows and 5 transforms, `_call_indices` would accumulate ~5M entries (one per state_id). Each entry is a string key (~32 hex chars = ~80 bytes with Python overhead) plus an int value (~28 bytes), totaling ~540MB of memory. For pipelines that make external calls (LLM, HTTP), this is realistic. The entries are never needed after the state is completed.

**Evidence:**
```python
# Line 143-148: Dictionaries grow without bound
self._call_indices: dict[str, int] = {}  # state_id -> next_index
self._operation_call_indices: dict[str, int] = {}  # operation_id -> next_index

# Line 2246-2251: Entries added but never removed
def allocate_call_index(self, state_id: str) -> int:
    with self._call_index_lock:
        if state_id not in self._call_indices:
            self._call_indices[state_id] = 0
        idx = self._call_indices[state_id]
        self._call_indices[state_id] += 1
        return idx
```

### [2417-2427] complete_operation validates in separate transaction from update

**What:** Beyond the TOCTOU race described in Critical Findings, the `complete_operation()` method performs its validation read and its update write in two separate database transactions. In `_database_ops.py`, each `execute_fetchone` and `execute_update` call opens its own `with self._db.connection()` context. This means the validation (line 2418-2419) and the update (line 2435-2444) are not transactionally atomic.

**Why it matters:** Even in a single-threaded scenario with SQLite, there is a theoretical window where a crash after the validation read but before the update write would leave the operation in an inconsistent state (the validation passed, but the update was never applied). More practically, this pattern could cause issues if the system is ever moved to PostgreSQL where connection isolation levels matter.

### [959] Legacy payload_ref parameter still accepted in create_row

**What:** The `create_row()` method has a `payload_ref` parameter marked as `DEPRECATED` in the docstring (line 938), and line 959 assigns it to `final_payload_ref` as a "Legacy path (will be removed)". However, it is still functional code that accepts and uses the parameter, and the `# Legacy path (will be removed)` comment suggests this is a backwards-compatibility shim that was supposed to be removed.

**Why it matters:** Per the project's "No Legacy Code Policy" in CLAUDE.md: "Legacy code, backwards compatibility, and compatibility shims are strictly forbidden" and "When something is removed or changed, DELETE THE OLD CODE COMPLETELY." The continued existence of this parameter violates the stated policy. If any caller is still passing `payload_ref`, that caller should be updated to not pass it, and the parameter should be removed entirely.

**Evidence:**
```python
# Line 938
payload_ref: DEPRECATED - payload persistence now handled internally

# Line 959
final_payload_ref = payload_ref  # Legacy path (will be removed)
```

### [1110] Outcome ID generation uses truncated UUID

**What:** Throughout the recorder, outcome_ids and error_ids use truncated UUIDs: `f"out_{generate_id()[:12]}"` (lines 1110, 1265, 2845), `f"verr_{generate_id()[:12]}"` (line 2971), `f"terr_{generate_id()[:12]}"` (line 3055). This truncates a 32-character hex UUID to 12 characters, yielding ~48 bits of entropy.

**Why it matters:** With 48 bits of entropy, the birthday paradox gives a 50% collision probability at approximately 2^24 = ~16.7 million records. For a system designed to handle "10,000 rows" (as mentioned in the Data Manifesto example), this is adequate. However, for production systems processing millions of rows across many runs sharing the same database, collision probability becomes non-trivial. The primary key columns for these tables are `String(64)` (sufficient for full UUIDs), so there is no column-width reason for truncation. A collision would cause an IntegrityError that crashes the pipeline, so this is not a silent failure, but it is an unnecessary fragility.

### [2662-2667] OSError catch in explain_row is overly broad

**What:** `explain_row()` catches `OSError` when retrieving payloads. `OSError` is a very broad exception hierarchy that includes `PermissionError`, `FileNotFoundError`, `IsADirectoryError`, `ConnectionRefusedError`, and many others. Some of these (like `PermissionError`) indicate configuration problems or security issues that should not be silently ignored.

**Why it matters:** If the payload store's filesystem permissions are misconfigured, every `explain_row()` call would silently return `payload_available=False` instead of surfacing the permission problem. Operators would see "payload unavailable" across all rows and might assume retention purging, when the real problem is a misconfigured filesystem mount or changed permissions.

## Observations

### [112-170] God class at 3,233 lines

**What:** LandscapeRecorder is the single class in this file and handles ALL audit recording: runs, nodes, edges, rows, tokens, node states, routing events, batches, artifacts, calls, operations, outcomes, validation errors, transform errors, explain, and replay lookups.

**Why it matters:** While each method is individually clean and well-documented, the class has grown to the point where it is difficult to understand the full surface area. The repository pattern is already partially extracted (RowRepository, NodeStateRepository, etc.) but only handles load/read operations. Separating write operations into domain-specific recorders (e.g., `RunRecorder`, `TokenRecorder`, `BatchRecorder`) would improve navigability. This is a design observation, not a functional problem.

### [372] Redundant import of json module

**What:** The `json` module is imported at file level (line 10) and again locally inside `get_source_field_resolution()` (line 372), `explain_row()` (line 2643), and `get_row_data()` (line 2035). The local imports are unnecessary since `json` is already available at module scope.

### [2500-2501] Deterministic call_id generation for operation calls

**What:** Operation call IDs use `f"call_{operation_id}_{call_index}"` (line 2501), which is deterministic given the operation_id and call_index. In contrast, state-parented call IDs use `generate_id()` (line 2289), which is a random UUID. This inconsistency means operation call IDs are predictable/reproducible while state call IDs are not.

**Why it matters:** This is minor, but the inconsistency could cause confusion in debugging or in replay mode if call_id matching is ever needed. The deterministic form for operation calls is arguably better (predictable, testable), but the inconsistency should be intentional.

### [2378] Truthiness check on input_data in begin_operation

**What:** Line 2378 uses `if input_data and self._payload_store is not None:` which would skip storing an empty dict `{}` as input_data. Similarly, line 2430 in `complete_operation()` uses `if output_data and self._payload_store is not None:`.

**Why it matters:** An empty dict is a valid input/output (a sink_write with no additional context). The truthiness check would skip storing it. The correct check is `if input_data is not None`.

### [2845] Outcome ID prefix "out_" may collide with user-defined IDs

**What:** Outcome IDs are prefixed with "out_" and error IDs with "verr_" or "terr_". These are not in a namespace that could collide with user-provided IDs since the primary key columns are type-specific (outcome_id, error_id). This is noted as a well-considered convention, not an issue.

### [1120] expected_branches_json uses json.dumps, not canonical_json

**What:** In `fork_token()` at line 1120, `expected_branches_json=json.dumps(branches)` is used instead of `canonical_json(branches)`. Similarly, `expand_token()` at line 1276 uses `json.dumps({"count": count})`.

**Why it matters:** While these are simple data structures (a list of strings and a dict with one int), the codebase consistently uses `canonical_json` for all audit trail JSON to ensure deterministic serialization. Using `json.dumps` here creates an inconsistency. For a list of strings, the output is likely identical, but this breaks the principle of using canonical_json everywhere in the audit trail.

### [130-169] Repository instances initialized with None session

**What:** All repository instances are created with `None` as the session parameter (lines 155-168). The session is described as "passed per-call" but is never actually set on any repository instance -- the repos are only used for their `load()` method which takes a database row directly without using the session.

**Why it matters:** The `session` parameter on Repository classes is dead code. Every `__init__` accepts a `session: Any` and stores it as `self.session`, but no `load()` method uses it. This is technical debt from an earlier design that can be cleaned up.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:**
1. Fix the TOCTOU race in `complete_operation()` by combining the validation read and status update into a single transaction (use `WHERE status = 'open'` in the UPDATE itself and check rowcount).
2. Differentiate `json.JSONDecodeError` from `KeyError` in `explain_row()` -- the former indicates corruption and should at minimum log at ERROR level, while the latter is expected graceful degradation.
3. Replace truthiness checks (`if trigger_type:`) with explicit None checks (`if trigger_type is not None:`) in `update_batch_status()`, `get_batches()`, and `get_artifacts()`.
4. Remove the deprecated `payload_ref` parameter from `create_row()` per the No Legacy Code policy.
5. Consider adding cleanup of `_call_indices`/`_operation_call_indices` for completed states, or document the expected memory footprint.

**Confidence:** HIGH -- I read every line of the file and all key dependencies. The findings are based on concrete code analysis, not speculation. The TOCTOU race is definitively confirmed by the `_database_ops.py` implementation showing separate connections per call. The memory growth concern is based on straightforward calculation. I am less certain about the practical impact of the truthiness filtering (it depends on whether callers ever pass falsy non-None values), but the inconsistency with other methods in the same file is clear evidence of a pattern problem.
