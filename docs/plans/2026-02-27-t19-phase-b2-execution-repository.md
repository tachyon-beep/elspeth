# T19 Phase B2: Extract ExecutionRepository

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract 3 processing-related mixins into a composed ExecutionRepository, consolidating node state recording, external call tracking, and batch management.

**Architecture:** NodeStateRecordingMixin + CallRecordingMixin + BatchRecordingMixin --> single ExecutionRepository class. Thread-safe call index allocation (Lock + dicts) is owned by the repository. LandscapeRecorder delegates all execution-related methods.

**Tech Stack:** Python 3.12, SQLAlchemy Core, threading.Lock, pytest, mypy, ruff

**Prerequisites:**
- Phase A complete (DTO repositories renamed to model loaders: `*Repository` --> `*Loader`, `_*_repo` --> `_*_loader`, `repositories.py` --> `model_loaders.py`)
- Phase A remediation complete (`c31e25f2`, `affcd98c`) — added `OperationLoader` to `_call_recording.py` and `recorder.py`
- Phase B1 complete (RunLifecycleRepository extracted, `_run_recording.py` deleted)
- All tests passing before starting

---

## Mixin Inventory

### NodeStateRecordingMixin (`_node_state_recording.py`, 375 lines)

**Public methods (5):**

| # | Method | Signature Summary |
|---|--------|-------------------|
| 1 | `begin_node_state` | `(token_id, node_id, run_id, step_index, input_data, *, state_id=None, attempt=0, quarantined=False) -> NodeStateOpen` |
| 2 | `complete_node_state` | `(state_id, status, *, output_data=None, duration_ms=None, error=None, success_reason=None, context_after=None) -> NodeStatePending \| NodeStateCompleted \| NodeStateFailed` -- 3 `@overload` variants |
| 3 | `get_node_state` | `(state_id) -> NodeState \| None` |
| 4 | `record_routing_event` | `(state_id, edge_id, mode, reason=None, *, event_id=None, routing_group_id=None, ordinal=0, reason_ref=None) -> RoutingEvent` |
| 5 | `record_routing_events` | `(state_id, routes: list[RoutingSpec], reason=None) -> list[RoutingEvent]` |

**Shared state accessed:** `_db`, `_ops`, `_node_state_loader`, `_routing_event_loader`, `_payload_store`

**Internal calls:** `complete_node_state()` calls `self.get_node_state()` to verify the update.

**External imports required:**
```python
from sqlalchemy import select
from elspeth.contracts import (
    CoalesceFailureReason, NodeState, NodeStateCompleted, NodeStateFailed,
    NodeStateOpen, NodeStatePending, NodeStateStatus, RoutingEvent, RoutingMode,
    RoutingReason, RoutingSpec,
)
from elspeth.contracts.errors import AuditIntegrityError, ExecutionError, TransformErrorReason
from elspeth.contracts.hashing import repr_hash
from elspeth.core.canonical import canonical_json, stable_hash
from elspeth.core.landscape._helpers import generate_id, now
from elspeth.core.landscape.schema import node_states_table, routing_events_table
```

**TYPE_CHECKING-only imports:**
```python
from elspeth.contracts.errors import TransformSuccessReason
from elspeth.contracts.node_state_context import NodeStateContext
```

### CallRecordingMixin (`_call_recording.py`, 582 lines)

**Public methods (12):**

| # | Method | Signature Summary |
|---|--------|-------------------|
| 1 | `allocate_call_index` | `(state_id) -> int` -- THREAD-SAFE, uses Lock |
| 2 | `record_call` | `(state_id, call_index, call_type, status, request_data, response_data=None, error=None, latency_ms=None, *, request_ref=None, response_ref=None) -> Call` |
| 3 | `begin_operation` | `(run_id, node_id, operation_type, *, input_data=None) -> Operation` |
| 4 | `complete_operation` | `(operation_id, status, *, output_data=None, error=None, duration_ms=None) -> None` |
| 5 | `allocate_operation_call_index` | `(operation_id) -> int` -- THREAD-SAFE, reuses same Lock |
| 6 | `record_operation_call` | `(operation_id, call_type, status, request_data, response_data=None, error=None, latency_ms=None, *, request_ref=None, response_ref=None, provider=None) -> Call` |
| 7 | `get_operation` | `(operation_id) -> Operation \| None` |
| 8 | `get_operation_calls` | `(operation_id) -> list[Call]` |
| 9 | `get_operations_for_run` | `(run_id) -> list[Operation]` |
| 10 | `get_all_operation_calls_for_run` | `(run_id) -> list[Call]` |
| 11 | `find_call_by_request_hash` | `(run_id, call_type, request_hash, *, sequence_index=0) -> Call \| None` |
| 12 | `get_call_response_data` | `(call_id) -> dict[str, Any] \| None` |

**Shared state accessed:** `_db` (via `_ops._db` in `complete_operation`), `_ops`, `_call_loader`, `_operation_loader`, `_payload_store`, `_call_indices` (dict), `_call_index_lock` (Lock), `_operation_call_indices` (dict)

> **Phase A remediation change:** `_operation_loader: OperationLoader` was added as a shared state annotation. Methods `get_operation()` and `get_operations_for_run()` now use `self._operation_loader.load(row)` instead of inline `Operation(...)` construction. This loader MUST be included in ExecutionRepository's constructor.

**CRITICAL:** Thread-safe call index allocation. The Lock and both dicts MUST move together as internal state of ExecutionRepository. `allocate_call_index` and `allocate_operation_call_index` both share the same `_call_index_lock`.

**Internal calls:** `record_operation_call()` calls `self.allocate_operation_call_index()`.

**External imports required:**
```python
import json
from threading import Lock
from typing import Any, Literal
from uuid import uuid4
from sqlalchemy import func, select
from elspeth.contracts import Call, CallStatus, CallType, FrameworkBugError, Operation
from elspeth.contracts.call_data import CallPayload
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.core.canonical import canonical_json, stable_hash
from elspeth.core.landscape._helpers import generate_id, now
from elspeth.core.landscape.schema import calls_table, node_states_table, operations_table
from elspeth.core.landscape.model_loaders import CallLoader, OperationLoader  # Phase A: OperationLoader added
```

### BatchRecordingMixin (`_batch_recording.py`, 469 lines)

**Public methods (12) + 1 private:**

| # | Method | Signature Summary |
|---|--------|-------------------|
| 1 | `create_batch` | `(run_id, aggregation_node_id, *, batch_id=None, attempt=0) -> Batch` |
| 2 | `add_batch_member` | `(batch_id, token_id, ordinal) -> BatchMember` |
| 3 | `update_batch_status` | `(batch_id, status, *, trigger_type=None, trigger_reason=None, state_id=None) -> None` |
| 4 | `complete_batch` | `(batch_id, status, *, trigger_type=None, trigger_reason=None, state_id=None) -> Batch` |
| 5 | `get_batch` | `(batch_id) -> Batch \| None` |
| 6 | `get_batches` | `(run_id, *, status=None, node_id=None) -> list[Batch]` |
| 7 | `get_incomplete_batches` | `(run_id) -> list[Batch]` |
| 8 | `get_batch_members` | `(batch_id) -> list[BatchMember]` |
| 9 | `get_all_batch_members_for_run` | `(run_id) -> list[BatchMember]` |
| 10 | `retry_batch` | `(batch_id) -> Batch` |
| 11 | `register_artifact` | `(run_id, state_id, sink_node_id, artifact_type, path, content_hash, size_bytes, *, artifact_id=None, idempotency_key=None) -> Artifact` |
| 12 | `get_artifacts` | `(run_id, *, sink_node_id=None) -> list[Artifact]` |
| P | `_find_batch_by_attempt` | `(run_id, aggregation_node_id, attempt) -> Batch \| None` -- private helper |

**Shared state accessed:** `_ops`, `_batch_loader`, `_batch_member_loader`, `_artifact_loader`

**Internal calls:** `complete_batch()` calls `self.get_batch()`. `retry_batch()` calls `self.get_batch()`, `self._find_batch_by_attempt()`, `self.create_batch()`, `self.get_batch_members()`, `self.add_batch_member()`.

**External imports required:**
```python
from typing import Any
from sqlalchemy import select
from elspeth.contracts import Artifact, Batch, BatchMember, BatchStatus, TriggerType
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.core.landscape._helpers import generate_id, now
from elspeth.core.landscape.schema import artifacts_table, batch_members_table, batches_table
```

---

## Method Count Summary

| Mixin | Public | Private | Total |
|-------|--------|---------|-------|
| NodeStateRecordingMixin | 5 | 0 | 5 |
| CallRecordingMixin | 12 | 0 | 12 |
| BatchRecordingMixin | 12 | 1 | 13 |
| **Total** | **29** | **1** | **30** |

LandscapeRecorder will delegate all **29 public methods** to `self._execution`.

---

## Current State of recorder.py (post-Phase A + B1)

Before making any changes, understand what recorder.py looks like right now:

**Inheritance chain (line 65-73):**
```python
class LandscapeRecorder(
    GraphRecordingMixin,         # stays (Phase B3)
    NodeStateRecordingMixin,     # ← REMOVE in this phase
    TokenRecordingMixin,         # stays (Phase B3)
    CallRecordingMixin,          # ← REMOVE in this phase
    BatchRecordingMixin,         # ← REMOVE in this phase
    ErrorRecordingMixin,         # stays (Phase B3/B4)
    QueryMethodsMixin,           # stays (Phase B4)
):
```

**`__init__` state (lines 92-133):** Already has:
- `self._db`, `self._payload_store`, `self._ops = DatabaseOps(db)` (lines 99-112)
- Thread-safety state: `self._call_indices`, `self._call_index_lock`, `self._operation_call_indices` (lines 102-109) — these MOVE to ExecutionRepository
- All 15 loader instances including `self._operation_loader = OperationLoader()` (added by Phase A remediation, line 122)
- `self._run_lifecycle = RunLifecycleRepository(...)` (line 133, added by Phase B1)

**Existing delegation block (lines 135-250):** 15 run lifecycle delegation methods from Phase B1. B2 delegation methods go AFTER this block.

**Imports already present:**
- Runtime: `Lock` (from threading), `Any` (from typing), `RunStatus` (from contracts)
- TYPE_CHECKING: `ExportStatus`, `Run`, `SecretResolution`, `PayloadStore`, `SchemaContract`, `ReproducibilityGrade`
- Model loaders: All 15 loaders including `OperationLoader` (Phase A)
- Repositories: `RunLifecycleRepository` (Phase B1)

---

## Task 1: Create ExecutionRepository class

**File to create:** `src/elspeth/core/landscape/execution_repository.py`

**Verify Phase B1 complete (before doing anything else):**
- `ls src/elspeth/core/landscape/run_lifecycle_repository.py` must succeed
- `grep 'RunRecordingMixin' src/elspeth/core/landscape/recorder.py` must return 0 hits

**Prerequisite reads (mandatory before writing any code):**
1. Read `src/elspeth/core/landscape/_node_state_recording.py` in full
2. Read `src/elspeth/core/landscape/_call_recording.py` in full
3. Read `src/elspeth/core/landscape/_batch_recording.py` in full
4. Read `src/elspeth/core/landscape/recorder.py` in full (to see current `__init__` attribute names)

**Steps:**

1. Create the file with this module docstring:
   ```python
   """ExecutionRepository: node state recording, call tracking, and batch management.

   Extracted from NodeStateRecordingMixin + CallRecordingMixin + BatchRecordingMixin
   as part of T19 (Landscape mixin -> composed repository decomposition).

   Owns thread-safe call index allocation (Lock + per-state and per-operation dicts).
   """
   ```

2. Write the `__init__` signature. The constructor receives injected dependencies (not self-created):

   ```python
   class ExecutionRepository:
       def __init__(
           self,
           db: LandscapeDB,
           ops: DatabaseOps,
           *,
           node_state_loader: NodeStateLoader,
           routing_event_loader: RoutingEventLoader,
           call_loader: CallLoader,
           operation_loader: OperationLoader,
           batch_loader: BatchLoader,
           batch_member_loader: BatchMemberLoader,
           artifact_loader: ArtifactLoader,
           payload_store: PayloadStore | None = None,
       ) -> None:
   ```

   Store all injected dependencies as private attributes (`self._db`, `self._ops`, `self._node_state_loader`, `self._routing_event_loader`, `self._call_loader`, `self._operation_loader`, `self._batch_loader`, `self._batch_member_loader`, `self._artifact_loader`, `self._payload_store`).

3. Create the Lock and index dicts as INTERNAL state in `__init__`:
   ```python
   self._call_indices: dict[str, int] = {}
   self._call_index_lock = Lock()
   self._operation_call_indices: dict[str, int] = {}
   ```
   These are NOT passed from outside. They are internal thread-safety state owned by ExecutionRepository.

4. Copy ALL 30 methods (29 public + 1 private) from the 3 mixin files. All `self.*` references naturally resolve because all shared state is now on ExecutionRepository itself. No method bodies need editing beyond the `complete_operation` fix in step 8.

5. Preserve the `@overload` declarations on `complete_node_state` exactly as they appear in the mixin.

6. Preserve the module-level constant `_TERMINAL_BATCH_STATUSES` from `_batch_recording.py`.

   **Implementation note:** Place `_TERMINAL_BATCH_STATUSES` at module level after imports and before the class definition. Methods that reference this constant will get a NameError if it's placed after them.

7. Merge all imports from the 3 mixin files into the new file's import block. Deduplicate. Use `from __future__ import annotations`. The complete merged import block:

   ```python
   from __future__ import annotations

   import json
   from threading import Lock
   from typing import TYPE_CHECKING, Any, Literal, overload

   from sqlalchemy import func, select

   from elspeth.contracts import (
       Artifact,
       Batch,
       BatchMember,
       BatchStatus,
       Call,
       CallStatus,
       CallType,
       CoalesceFailureReason,
       FrameworkBugError,
       NodeState,
       NodeStateCompleted,
       NodeStateFailed,
       NodeStateOpen,
       NodeStatePending,
       NodeStateStatus,
       Operation,
       RoutingEvent,
       RoutingMode,
       RoutingReason,
       RoutingSpec,
       TriggerType,
   )
   from elspeth.contracts.call_data import CallPayload
   from elspeth.contracts.errors import AuditIntegrityError, ExecutionError, TransformErrorReason
   from elspeth.contracts.hashing import repr_hash
   from elspeth.core.canonical import canonical_json, stable_hash
   from elspeth.core.landscape._database_ops import DatabaseOps
   from elspeth.core.landscape._helpers import generate_id, now
   from elspeth.core.landscape.database import LandscapeDB
   from elspeth.core.landscape.model_loaders import (
       ArtifactLoader,
       BatchLoader,
       BatchMemberLoader,
       CallLoader,
       NodeStateLoader,
       OperationLoader,
       RoutingEventLoader,
   )
   from elspeth.core.landscape.schema import (
       artifacts_table,
       batch_members_table,
       batches_table,
       calls_table,
       node_states_table,
       operations_table,
       routing_events_table,
   )

   if TYPE_CHECKING:
       from elspeth.contracts.errors import TransformSuccessReason
       from elspeth.contracts.node_state_context import NodeStateContext
       from elspeth.contracts.payload_store import PayloadStore
   ```

   **Note:** `PayloadStore` stays under TYPE_CHECKING — it appears in the constructor signature but with `from __future__ import annotations` that's fine. `DatabaseOps`, `LandscapeDB`, and all `*Loader` classes move to runtime imports since they're constructor parameters used for isinstance checks (if any) and direct instantiation by the caller.

8. **REQUIRED EDIT — `complete_operation()` fix:** Replace `self._ops._db.connection()` with `self._db.connection()`. Accessing `_db` through `_ops` couples ExecutionRepository to DatabaseOps internals. This is the ONLY method body edit needed. Search for `self._ops._db` in the extracted code and replace all occurrences with `self._db`.

**DESIGN DECISION:** The Lock and index dicts are OWNED by ExecutionRepository, not injected. They are internal concurrency-control state, not dependencies.

**CRITICAL DETAIL:** `record_routing_events()` uses `self._db.connection()` directly for the batch insert within a single transaction. This works because `ExecutionRepository` receives `_db` as a constructor parameter.

**Verification:** The new file should have exactly 31 `def` statements (the `__init__` plus 29 public methods + 1 private = 31 total).

---

## Task 2: Update recorder.py

**File:** `src/elspeth/core/landscape/recorder.py`

**Prerequisite reads (mandatory before editing):**
1. Read `src/elspeth/core/landscape/recorder.py` in full (re-read; it has changed significantly since Phase A/B1)
2. Read the newly created `src/elspeth/core/landscape/execution_repository.py` to confirm the class name and constructor

**Steps:**

1. **Remove from inheritance list (line 65-73):** Delete `NodeStateRecordingMixin`, `CallRecordingMixin`, `BatchRecordingMixin` from the `class LandscapeRecorder(...)` bases. The remaining bases become:
   ```python
   class LandscapeRecorder(
       GraphRecordingMixin,
       TokenRecordingMixin,
       ErrorRecordingMixin,
       QueryMethodsMixin,
   ):
   ```

2. **Remove imports (lines 35-36, 37):** Delete the 3 mixin import lines:
   ```python
   from elspeth.core.landscape._batch_recording import BatchRecordingMixin
   from elspeth.core.landscape._call_recording import CallRecordingMixin
   from elspeth.core.landscape._node_state_recording import NodeStateRecordingMixin
   ```

3. **Add import** (near line 62, next to RunLifecycleRepository):
   ```python
   from elspeth.core.landscape.execution_repository import ExecutionRepository
   ```

4. **Remove `Lock` import (line 24):** Delete `from threading import Lock`. The Lock now lives inside ExecutionRepository. Verify no other code in recorder.py uses `Lock` before removing.

5. **In `__init__` (lines 92-133):**
   - REMOVE the 3 lines for thread-safety state (lines 102-109):
     ```python
     # DELETE these lines:
     self._call_indices: dict[str, int] = {}
     self._call_index_lock: Lock = Lock()
     self._operation_call_indices: dict[str, int] = {}
     ```
   - ADD construction of ExecutionRepository AFTER the loader instances and AFTER `self._run_lifecycle`:
     ```python
     # Composed repository for execution recording (extracted from 3 mixins in T19)
     self._execution = ExecutionRepository(
         db,
         self._ops,
         node_state_loader=self._node_state_loader,
         routing_event_loader=self._routing_event_loader,
         call_loader=self._call_loader,
         operation_loader=self._operation_loader,
         batch_loader=self._batch_loader,
         batch_member_loader=self._batch_member_loader,
         artifact_loader=self._artifact_loader,
         payload_store=payload_store,
     )
     ```

6. **Add 29 delegation methods** AFTER the existing B1 run lifecycle delegation block (after line 250). Add a section comment:
   ```python
   # ── Execution delegation (ExecutionRepository) ─────────────────────
   ```

   Each delegation method must:
   - Have the EXACT same signature (parameter names, types, defaults, return type) as the ExecutionRepository method
   - Forward all arguments positionally or by keyword matching the target
   - Return the target's return value directly
   - Have a brief one-line docstring matching B1 style: `"""Brief description. Delegates to ExecutionRepository."""`
   - Preserve `@overload` declarations on `complete_node_state` for type narrowing

   **Implementation note:** The `complete_node_state` method requires `@overload` declarations on BOTH ExecutionRepository and the LandscapeRecorder delegation wrapper. Without overloads on the recorder, callers lose mypy type narrowing.

   **Complete list of 29 methods to delegate:**

   From NodeStateRecordingMixin:
   1. `begin_node_state`
   2. `complete_node_state` (with 3 `@overload` variants)
   3. `get_node_state`
   4. `record_routing_event`
   5. `record_routing_events`

   From CallRecordingMixin:
   6. `allocate_call_index`
   7. `record_call`
   8. `begin_operation`
   9. `complete_operation`
   10. `allocate_operation_call_index`
   11. `record_operation_call`
   12. `get_operation`
   13. `get_operation_calls`
   14. `get_operations_for_run`
   15. `get_all_operation_calls_for_run`
   16. `find_call_by_request_hash`
   17. `get_call_response_data`

   From BatchRecordingMixin:
   18. `create_batch`
   19. `add_batch_member`
   20. `update_batch_status`
   21. `complete_batch`
   22. `get_batch`
   23. `get_batches`
   24. `get_incomplete_batches`
   25. `get_batch_members`
   26. `get_all_batch_members_for_run`
   27. `retry_batch`
   28. `register_artifact`
   29. `get_artifacts`

   Note: `_find_batch_by_attempt` is private and NOT delegated. It is only called internally by `retry_batch()` within ExecutionRepository.

7. **Add necessary TYPE_CHECKING imports** to recorder.py for the type annotations used in delegation method signatures. Since recorder.py uses `from __future__ import annotations`, all type annotations are deferred and can be under TYPE_CHECKING.

   **Already imported** (no action needed):
   - `Any` (runtime, line 25)
   - `RunStatus` (runtime, line 27)
   - `ExportStatus`, `Run`, `SecretResolution` (TYPE_CHECKING, line 30)
   - `PayloadStore` (TYPE_CHECKING, line 31)
   - `SchemaContract` (TYPE_CHECKING, line 32)
   - `ReproducibilityGrade` (TYPE_CHECKING, line 33)

   **Must add under TYPE_CHECKING:**
   ```python
   from typing import Literal

   from elspeth.contracts import (
       Artifact,
       Batch,
       BatchMember,
       BatchStatus,
       Call,
       CallStatus,
       CallType,
       CoalesceFailureReason,
       NodeState,
       NodeStateCompleted,
       NodeStateFailed,
       NodeStateOpen,
       NodeStatePending,
       NodeStateStatus,
       Operation,
       RoutingEvent,
       RoutingMode,
       RoutingReason,
       RoutingSpec,
       TriggerType,
   )
   from elspeth.contracts.call_data import CallPayload
   from elspeth.contracts.errors import ExecutionError, TransformErrorReason
   from elspeth.contracts.errors import TransformSuccessReason
   from elspeth.contracts.node_state_context import NodeStateContext
   ```

   **Note:** `Literal` from typing needs to be a **runtime** import (not TYPE_CHECKING) because the `@overload` decorator evaluations happen at import time when `from __future__ import annotations` is active. Move `Literal` to the runtime import: `from typing import TYPE_CHECKING, Any, Literal, overload`.

   Also add `overload` to the runtime typing import — needed for the `@overload` decorators on `complete_node_state` delegation.

   **Must add to runtime imports:**
   ```python
   from typing import TYPE_CHECKING, Any, Literal, overload  # add Literal, overload
   ```

---

## Task 3: Delete the 3 mixin files and update docstring

**Files to delete:**
- `src/elspeth/core/landscape/_node_state_recording.py`
- `src/elspeth/core/landscape/_call_recording.py`
- `src/elspeth/core/landscape/_batch_recording.py`

**Steps:**

1. Delete all 3 files using `git rm` (not plain `rm`):
   ```bash
   git rm src/elspeth/core/landscape/_node_state_recording.py
   git rm src/elspeth/core/landscape/_call_recording.py
   git rm src/elspeth/core/landscape/_batch_recording.py
   ```

2. Verify no other files import from these modules. The only importer was `recorder.py` (updated in Task 2). Confirm with:
   ```bash
   grep -rn '_node_state_recording\|_call_recording\|_batch_recording' src/elspeth/
   ```
   Expected: 0 hits. If any remain, update those files before proceeding.

3. **Update `recorder.py` module docstring** (lines 1-20). The current docstring (post-B1) lists:

   ```
   Composed repository (owned instance, injected via __init__):
   - run_lifecycle_repository.py: Run lifecycle (begin, complete, finalize, secrets, contracts)

   Mixins (inherited behavior):
   - _graph_recording.py: Node and edge registration/queries
   - _node_state_recording.py: Node state recording and routing events
   - _token_recording.py: Row/token creation, fork/coalesce/expand, outcomes
   - _call_recording.py: External call recording, operations, replay lookup
   - _batch_recording.py: Batch management and artifact registration
   - _error_recording.py: Validation and transform error recording
   - _query_methods.py: Read-only entity queries, bulk retrieval, explain
   ```

   Update to:

   ```
   Composed repositories (owned instances, injected via __init__):
   - run_lifecycle_repository.py: Run lifecycle (begin, complete, finalize, secrets, contracts)
   - execution_repository.py: Node states, external calls, operations, batches, artifacts

   Mixins (inherited behavior):
   - _graph_recording.py: Node and edge registration/queries
   - _token_recording.py: Row/token creation, fork/coalesce/expand, outcomes
   - _error_recording.py: Validation and transform error recording
   - _query_methods.py: Read-only entity queries, bulk retrieval, explain
   ```

---

## Task 4: Run verification

Run in order, stopping on first failure:

1. **Tests:** `.venv/bin/python -m pytest tests/ -x -q` -- all tests must pass.

2. **Type checking:** `.venv/bin/python -m mypy src/` -- no new type errors. Pay special attention to:
   - `complete_node_state` overloads must be correctly typed on both `ExecutionRepository` and the recorder delegation
   - All `Literal` type annotations in `begin_operation` and `complete_operation` must be preserved

3. **Linting:** `.venv/bin/python -m ruff check src/` -- no new lint errors. Pay special attention to:
   - `Lock` import removed from recorder.py (unused import error if left)
   - No unused imports in execution_repository.py

4. **Deleted files confirmed:**
   ```bash
   test ! -f src/elspeth/core/landscape/_node_state_recording.py
   test ! -f src/elspeth/core/landscape/_call_recording.py
   test ! -f src/elspeth/core/landscape/_batch_recording.py
   ```

5. **Thread-safety verification:** Confirm the concurrency stress test still passes:
   ```bash
   .venv/bin/python -m pytest tests/performance/stress/test_call_index_concurrency.py -v
   ```

6. **No residual mixin references:**
   ```bash
   grep -rn 'NodeStateRecordingMixin\|CallRecordingMixin\|BatchRecordingMixin' src/elspeth/
   ```
   Expected: 0 hits.

7. **No stale imports from deleted modules:**
   ```bash
   grep -rn '_node_state_recording\|_call_recording\|_batch_recording' src/elspeth/
   ```
   Expected: 0 hits.

8. **OperationLoader propagation check:** Verify the operation loader dependency chain is intact:
   ```bash
   grep -n 'operation_loader' src/elspeth/core/landscape/execution_repository.py
   grep -n '_operation_loader' src/elspeth/core/landscape/recorder.py
   ```
   Expected: execution_repository.py has constructor param + `self._operation_loader` storage + usage in `get_operation()` and `get_operations_for_run()`. recorder.py has `self._operation_loader = OperationLoader()` creation and passes it to ExecutionRepository.

If any verification step fails, fix the issue before proceeding to Task 5.

---

## Task 5: Commit

```bash
git add src/elspeth/core/landscape/execution_repository.py src/elspeth/core/landscape/recorder.py
git add -u src/elspeth/core/landscape/
git commit -m "refactor(t19): extract ExecutionRepository from 3 processing mixins

Phase B2: NodeStateRecording + CallRecording + BatchRecording -->
ExecutionRepository. Thread-safe call index allocation (Lock + dicts)
moves inside repository as internal state. LandscapeRecorder delegates
all 29 public methods. OperationLoader propagated (Phase A remediation).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Definition of Done

- [ ] 3 mixin files deleted (`_node_state_recording.py`, `_call_recording.py`, `_batch_recording.py`)
- [ ] `execution_repository.py` exists with `ExecutionRepository` class containing all 30 methods (29 public + 1 private)
- [ ] `ExecutionRepository.__init__` takes `operation_loader: OperationLoader` (Phase A remediation dependency)
- [ ] LandscapeRecorder no longer inherits from `NodeStateRecordingMixin`, `CallRecordingMixin`, or `BatchRecordingMixin`
- [ ] LandscapeRecorder constructs `self._execution = ExecutionRepository(...)` in `__init__` with all 8 keyword args including `operation_loader`
- [ ] Thread-safe Lock + both index dicts (`_call_indices`, `_operation_call_indices`) owned by ExecutionRepository, not LandscapeRecorder
- [ ] `Lock` import removed from recorder.py (no longer used there)
- [ ] All 29 public methods delegated from LandscapeRecorder to ExecutionRepository with identical signatures
- [ ] Delegation methods have brief one-line docstrings matching B1 style
- [ ] `@overload` declarations on `complete_node_state` preserved on both ExecutionRepository and recorder delegation
- [ ] `Literal` and `overload` added to recorder.py runtime typing import
- [ ] Module-level `_TERMINAL_BATCH_STATUSES` constant lives in `execution_repository.py`
- [ ] `complete_operation()` uses `self._db.connection()` not `self._ops._db.connection()`
- [ ] Module docstring updated: 3 mixin lines removed, `execution_repository.py` line added
- [ ] All tests pass (especially `tests/performance/stress/test_call_index_concurrency.py`)
- [ ] mypy clean (no new errors)
- [ ] ruff clean (no new errors)
- [ ] No residual references to the 3 deleted mixin classes or modules in `src/elspeth/`

## Risk Notes

1. **`complete_operation` raw connection access:** This method uses `self._ops._db.connection()` to do an atomic check-and-update with payload storage in the same transaction. After extraction, use `self._db.connection()` since ExecutionRepository holds `_db` directly. This is the only method body edit beyond mechanical copy.

2. **`record_routing_events` transaction scope:** Uses `self._db.connection()` for a multi-insert transaction. This works naturally since `ExecutionRepository` holds `_db`.

3. **Import type annotations for overloads:** The `@overload` decorator and `Literal` usage on `complete_node_state` require careful handling. The recorder's delegation overloads need the same `Literal[NodeStateStatus.PENDING]` etc. type annotations to preserve mypy narrowing. Both `Literal` and `overload` must be runtime imports in recorder.py.

4. **Delegation method count:** 29, not 30. The private `_find_batch_by_attempt` is NOT delegated -- it is only used internally by `retry_batch()` within ExecutionRepository.

5. **OperationLoader dependency (Phase A remediation):** The original plan predated the Phase A remediation that introduced `OperationLoader` into `_call_recording.py`. If `operation_loader` is omitted from the ExecutionRepository constructor, `get_operation()` and `get_operations_for_run()` will crash with `AttributeError` at runtime. This is the most dangerous delta from the original plan.

6. **Lock import cleanup:** Removing the `Lock` import from recorder.py is required — ruff will flag it as unused (F401). The Lock now lives inside ExecutionRepository.

## Changelog (vs. original plan)

| # | Section | Change | Reason |
|---|---------|--------|--------|
| 1 | Prerequisites | Added Phase A remediation as explicit prereq | Phase A remediation changed `_call_recording.py` |
| 2 | CallRecordingMixin shared state | Added `_operation_loader: OperationLoader` | Phase A remediation added this dependency |
| 3 | CallRecordingMixin imports | Added `OperationLoader` import line | Phase A remediation |
| 4 | CallRecordingMixin line count | 612 → 582 lines | Phase A remediation removed inline `Operation(...)` construction |
| 5 | Task 1 constructor | Added `operation_loader: OperationLoader` parameter | Phase A remediation dependency |
| 6 | Task 1 step 7 | Full merged import block provided | Reduces ambiguity during execution |
| 7 | Task 1 step 8 | Explicit `complete_operation` edit step | Was a note, now a numbered step |
| 8 | New section | "Current State of recorder.py" reference section | Prevents stale line-number references |
| 9 | Task 2 step 4 | Added: remove `Lock` import from recorder.py | Lock moves to ExecutionRepository; ruff F401 |
| 10 | Task 2 step 5 | Construction includes `operation_loader=self._operation_loader` | Phase A remediation dependency |
| 11 | Task 2 step 6 | Delegation docstrings: match B1 style (brief one-liner) | Consistency with existing B1 delegation block |
| 12 | Task 2 step 7 | Complete import delta with already-imported vs must-add | Reduces guesswork during execution |
| 13 | Task 2 step 7 | `Literal` + `overload` must be runtime imports | Required for `@overload` decorator evaluation |
| 14 | Task 3 step 3 | Full before/after docstring content | Accounts for B1's docstring changes |
| 15 | Task 4 step 8 | New: OperationLoader propagation check | Catches the most dangerous regression |
| 16 | Definition of Done | 5 new checklist items | Covers all deltas |
| 17 | Risk Notes | Added risks 5 (OperationLoader) and 6 (Lock cleanup) | New risks from Phase A changes |
