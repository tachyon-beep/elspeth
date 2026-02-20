# Coalesce Pending State Consolidation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace four parallel dicts in `_PendingCoalesce` with a single typed dict of `_BranchEntry` dataclass instances, eliminating the parallel-arrays anti-pattern.

**Architecture:** `_PendingCoalesce` currently tracks per-branch state across 3 parallel dicts (`arrived`, `arrival_times`, `pending_state_ids`) that must always stay in sync. We consolidate into `branches: dict[str, _BranchEntry]` where `_BranchEntry` is a frozen dataclass holding `(token, arrival_time, state_id)`. `lost_branches` stays separate (complementary semantics — tracks branches that never arrived). `first_arrival` stays as a scalar.

**Tech Stack:** Python dataclasses, no new dependencies.

**Bug:** `elspeth-rapid-b5eefe` — "Coalesce pending state uses four parallel dicts instead of one typed dict"

---

## Risk Assessment

- **Scope:** Single file (`coalesce_executor.py`) + 1 test file + 0 contract changes
- **Blast radius:** ~35 access sites, all within `coalesce_executor.py`
- **Behavioral change:** None — pure structural refactor, identical runtime behavior
- **Test coverage:** 120+ unit tests + 30+ property tests exercise all code paths

---

## Task 1: Add `_BranchEntry` dataclass and refactor `_PendingCoalesce`

**Files:**
- Modify: `src/elspeth/engine/coalesce_executor.py:56-64`

**Step 1: Add `_BranchEntry` and update `_PendingCoalesce`**

Replace the existing `_PendingCoalesce` with:

```python
@dataclass(frozen=True, slots=True)
class _BranchEntry:
    """Per-branch state within a pending coalesce.

    Groups token, arrival time, and audit state_id that were previously
    scattered across three parallel dicts.  Frozen to prevent mutation
    after construction — a new entry is created per branch arrival.
    """

    token: TokenInfo
    arrival_time: float  # Monotonic timestamp of arrival
    state_id: str  # Landscape node_state ID for pending hold


@dataclass
class _PendingCoalesce:
    """Tracks pending tokens for a single row_id at a coalesce point."""

    branches: dict[str, _BranchEntry]  # branch_name -> entry
    first_arrival: float  # For timeout calculation
    lost_branches: dict[str, str] = field(default_factory=dict)  # branch_name -> loss reason
```

**Step 2: Run tests to confirm they fail (old field names removed)**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_coalesce_executor.py -x --tb=short -q 2>&1 | tail -5`
Expected: FAIL (tests reference old field names)

---

## Task 2: Update `accept()` method

**Files:**
- Modify: `src/elspeth/engine/coalesce_executor.py` — `accept()` method (~L192-321)

**Access site mapping:**

| Old | New |
|-----|-----|
| `pending.arrived[branch]` (read token) | `pending.branches[branch].token` |
| `pending.arrived[branch] = token` (store) | `pending.branches[branch] = _BranchEntry(...)` |
| `branch in pending.arrived` | `branch in pending.branches` |
| `pending.arrived[branch]` (dup check) | `pending.branches[branch].token` |
| `pending.arrival_times[branch] = now` | absorbed into `_BranchEntry` construction |
| `pending.pending_state_ids[branch] = state.state_id` | absorbed into `_BranchEntry` construction |

Key behavioral improvement: Previously, token and arrival_time were stored BEFORE state_id (lines 295-307), creating a brief window where `arrived` had the branch but `pending_state_ids` didn't. Now all three are stored atomically via a single `_BranchEntry` construction after `begin_node_state()` returns.

**Step 1: Rewrite `accept()` to use `_BranchEntry`**

The `_PendingCoalesce` construction (L274-280) becomes:
```python
self._pending[key] = _PendingCoalesce(
    branches={},
    first_arrival=now,
)
```

The duplicate check (L286-292) changes from `pending.arrived` to `pending.branches`:
```python
if token.branch_name in pending.branches:
    existing = pending.branches[token.branch_name]
    raise ValueError(
        f"Duplicate arrival for branch '{token.branch_name}' at coalesce '{coalesce_name}'. "
        f"Existing token: {existing.token.token_id}, new token: {token.token_id}. "
        ...
    )
```

The recording + storage (L295-307) consolidates into atomic entry creation:
```python
# Record pending node state FIRST, then store entry atomically
state = self._recorder.begin_node_state(
    token_id=token.token_id,
    node_id=node_id,
    run_id=self._run_id,
    step_index=step,
    input_data=token.row_data.to_dict(),
)
pending.branches[token.branch_name] = _BranchEntry(
    token=token,
    arrival_time=now,
    state_id=state.state_id,
)
```

---

## Task 3: Update `_should_merge()` and `_fail_pending()`

**Files:**
- Modify: `src/elspeth/engine/coalesce_executor.py` — `_should_merge()` and `_fail_pending()`

**`_should_merge` changes:**
- `len(pending.arrived)` → `len(pending.branches)`

**`_fail_pending` changes:**
- `list(pending.arrived.values())` → `[e.token for e in pending.branches.values()]`
- `for branch_name, token in pending.arrived.items()` → `for branch_name, entry in pending.branches.items()` with `entry.token`, `entry.state_id`, `entry.arrival_time`

---

## Task 4: Update `_execute_merge()`

**Files:**
- Modify: `src/elspeth/engine/coalesce_executor.py` — `_execute_merge()` (~L413-653)

Largest concentration of changes. Key mappings:

| Old | New |
|-----|-----|
| `pending.arrived.items()` (contract check) | `pending.branches.items()` → `entry.token` |
| `settings.select_branch not in pending.arrived` | `settings.select_branch not in pending.branches` |
| `pending.arrived[branch].row_data.contract` | `pending.branches[branch].token.row_data.contract` |
| `pending.arrived.keys()` | `pending.branches.keys()` |
| `pending.arrived.values()` (consumed tokens) | `[e.token for e in pending.branches.values()]` |
| `pending.arrival_times[branch]` | `pending.branches[branch].arrival_time` |
| `pending.pending_state_ids[branch]` | `pending.branches[branch].state_id` |
| `self._merge_data(settings, pending.arrived)` | `self._merge_data(settings, pending.branches)` |

Also update the `_merge_data` signature and body — it accesses `.row_data.to_dict()` on tokens.

---

## Task 5: Update `_merge_data()`

**Files:**
- Modify: `src/elspeth/engine/coalesce_executor.py` — `_merge_data()` (~L655-712)

Change signature from `arrived: dict[str, TokenInfo]` to `branches: dict[str, _BranchEntry]`.

Update all token accesses:
- `arrived[branch_name].row_data.to_dict()` → `branches[branch_name].token.row_data.to_dict()`
- `arrived[branch_name]` → `branches[branch_name]` (where checking presence)

---

## Task 6: Update `check_timeouts()`, `flush_pending()`, `notify_branch_lost()`

**Files:**
- Modify: `src/elspeth/engine/coalesce_executor.py` — remaining public methods

**`check_timeouts`:** Only calls `_execute_merge` and `_fail_pending` which are already updated. No direct access to `arrived`/`arrival_times`/`pending_state_ids`.

**`flush_pending`:** Same — delegates to `_execute_merge`/`_fail_pending`. One change:
- `list(pending.arrived.keys())` → `list(pending.branches.keys())` (line ~913 error msg)
- `len(pending.arrived)` → `len(pending.branches)` (line ~850, 876)

**`notify_branch_lost`:**
- `lost_branch in pending.arrived` → `lost_branch in pending.branches`
- `_evaluate_after_loss` — `len(pending.arrived)` → `len(pending.branches)`

---

## Task 7: Update `_evaluate_after_loss()`

**Files:**
- Modify: `src/elspeth/engine/coalesce_executor.py` — `_evaluate_after_loss()` (~L1004-1078)

- `len(pending.arrived)` → `len(pending.branches)`
- No other changes needed (delegates to `_execute_merge`/`_fail_pending`)

---

## Task 8: Update test file

**Files:**
- Modify: `tests/unit/engine/test_coalesce_executor.py:24,837-842`

**Step 1: Update import**
```python
from elspeth.engine.coalesce_executor import CoalesceExecutor, CoalesceOutcome, _BranchEntry, _PendingCoalesce
```

**Step 2: Update direct `_PendingCoalesce` construction (line 837-842)**
```python
token = _make_token(branch_name="a")
executor._pending[key] = _PendingCoalesce(
    branches={"a": _BranchEntry(token=token, arrival_time=100.0, state_id="state_fake")},
    first_arrival=100.0,
)
```

**Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_coalesce_executor.py tests/property/engine/test_coalesce_properties.py -v --tb=short -q`
Expected: ALL PASS

---

## Task 9: Run full verification

**Step 1: mypy**
Run: `.venv/bin/python -m mypy src/elspeth/engine/coalesce_executor.py`
Expected: Success

**Step 2: ruff**
Run: `.venv/bin/python -m ruff check src/elspeth/engine/coalesce_executor.py`
Expected: Clean

**Step 3: Full coalesce-related test suite**
Run: `.venv/bin/python -m pytest tests/unit/engine/test_coalesce_executor.py tests/unit/engine/test_coalesce_contract_bug.py tests/unit/engine/test_coalesce_pipeline_row.py tests/property/engine/test_coalesce_properties.py tests/property/engine/test_processor_coalesce_equivalence_properties.py -v --tb=short -q`
Expected: ALL PASS

**Step 4: Broader integration/e2e (coalesce paths)**
Run: `.venv/bin/python -m pytest tests/ -k coalesce --tb=short -q`
Expected: ALL PASS

---

## Task 10: Commit

```bash
git add src/elspeth/engine/coalesce_executor.py tests/unit/engine/test_coalesce_executor.py
git commit -m "fix: consolidate parallel dicts in _PendingCoalesce into typed _BranchEntry

Replaces three parallel dicts (arrived, arrival_times, pending_state_ids)
with a single dict[str, _BranchEntry] where _BranchEntry is a frozen
dataclass holding (token, arrival_time, state_id). This eliminates the
parallel-arrays anti-pattern where all three dicts had to stay in sync
by branch_name key.

Bonus: branch entries are now stored atomically after begin_node_state()
returns, eliminating the brief window where arrived had the branch but
pending_state_ids didn't.

Fixes: elspeth-rapid-b5eefe

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```
