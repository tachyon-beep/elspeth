# T19 Phase B4+C: Extract QueryRepository and Finalize Facade

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract the last mixin (QueryMethodsMixin) into QueryRepository and convert LandscapeRecorder into a pure facade that delegates to 4 composed domain repositories.

**Architecture:** QueryMethodsMixin --> QueryRepository (read-only queries). Then LandscapeRecorder becomes a zero-inheritance facade creating 4 repositories in __init__ and delegating ~91 public methods. The public API is 100% unchanged.

**Tech Stack:** Python 3.12, SQLAlchemy Core, pytest, mypy, ruff

**Prerequisites:**
- Phase B3 complete (DataFlowRepository extracted)
- All tests passing before starting

> **⚠ WARNING — This plan requires update before execution.**
>
> This plan was written before Phase A remediation and Phases B1–B3 execution. By the time this phase runs, recorder.py will have been extensively modified:
>
> 1. **recorder.py is now a hybrid facade.** Phases B1–B3 converted 3 of 7 mixins into composed repositories (RunLifecycleRepository, ExecutionRepository, DataFlowRepository). The inheritance chain, `__init__`, import block, and delegation methods have all changed. Line numbers and code snippets in this plan are STALE.
> 2. **~73 delegation methods already exist.** B1 added 15, B2 added 29, B3 added ~29. This plan adds the final ~18 and removes the last mixin. The "total method count" and facade structure described here must be reconciled with reality.
> 3. **OperationLoader and other Phase A changes.** Loader classes were refactored in Phase A remediation. Verify constructor signatures against the actual repository classes, not this plan's descriptions.
> 4. **Module docstring evolved.** Each phase updated the docstring. By B4, it should show 4 composed repositories and 0 mixins.
> 5. **Import accumulation.** Each phase added TYPE_CHECKING imports for delegation signatures. The final facade may have a large import block — verify no duplicates or unused imports remain after the last mixin is removed.
> 6. **Delegation style:** B1 established brief one-liner docstrings on delegation methods (`"""Brief desc. Delegates to XRepository."""`). All subsequent phases followed suit.
>
> 7. **Process note from B3 review (L1):** The B3 commit (0713c2c3) bundled mypy `warn_unused_ignores` config + 15 stale type-ignore removals alongside the DataFlowRepository extraction. Future phases MUST separate config/tooling changes from extraction commits — one commit for config changes, one for the extraction. This improves `git bisect` and reduces reviewer confusion.
>
> **Action:** Read the current state of ALL files referenced in this plan before starting. This plan describes the end-state architecture (pure facade, zero inheritance) but the intermediate state after B1–B3 determines what's actually left to do. A full re-read of recorder.py and `_query_methods.py` is mandatory before Task 1.

---

## QueryMethodsMixin Analysis

**File:** `src/elspeth/core/landscape/_query_methods.py` (499 lines)

**Public methods (18):**

*Single-entity queries:*

| # | Method | Signature Summary |
|---|--------|-------------------|
| 1 | `get_rows` | `(run_id) -> list[Row]` |
| 2 | `get_tokens` | `(row_id) -> list[Token]` |
| 3 | `get_node_states_for_token` | `(token_id) -> list[NodeState]` |
| 4 | `get_row` | `(row_id) -> Row \| None` |
| 5 | `get_row_data` | `(row_id) -> RowDataResult` |
| 6 | `get_token` | `(token_id) -> Token \| None` |
| 7 | `get_token_parents` | `(token_id) -> list[TokenParent]` |
| 8 | `get_routing_events` | `(state_id) -> list[RoutingEvent]` |
| 9 | `get_calls` | `(state_id) -> list[Call]` |

*Batch queries with chunking (N+1 fix):*

| # | Method | Signature Summary |
|---|--------|-------------------|
| 10 | `get_routing_events_for_states` | `(state_ids: list[str]) -> list[RoutingEvent]` -- chunks at 500 |
| 11 | `get_calls_for_states` | `(state_ids: list[str]) -> list[Call]` -- chunks at 500 |

*Full-run batch queries:*

| # | Method | Signature Summary |
|---|--------|-------------------|
| 12 | `get_all_tokens_for_run` | `(run_id) -> list[Token]` |
| 13 | `get_all_node_states_for_run` | `(run_id) -> list[NodeState]` |
| 14 | `get_all_routing_events_for_run` | `(run_id) -> list[RoutingEvent]` |
| 15 | `get_all_calls_for_run` | `(run_id) -> list[Call]` |
| 16 | `get_all_token_parents_for_run` | `(run_id) -> list[TokenParent]` |
| 17 | `get_all_token_outcomes_for_run` | `(run_id) -> list[TokenOutcome]` |

*Lineage:*

| # | Method | Signature Summary |
|---|--------|-------------------|
| 18 | `explain_row` | `(run_id, row_id) -> RowLineage \| None` |

**Module-level constant:** `_QUERY_CHUNK_SIZE = 500` (SQLite IN-clause limit)

**Shared state accessed (all via `self.*`):**
- `_ops: DatabaseOps` -- query execution helper (every method)
- `_payload_store: PayloadStore | None` -- payload retrieval (`get_row_data`, `explain_row`)
- `_row_loader: RowLoader` (was `_row_repo`) -- row DTO mapping
- `_token_loader: TokenLoader` (was `_token_repo`) -- token DTO mapping
- `_token_parent_loader: TokenParentLoader` (was `_token_parent_repo`) -- token parent DTO mapping
- `_node_state_loader: NodeStateLoader` (was `_node_state_repo`) -- node state DTO mapping
- `_routing_event_loader: RoutingEventLoader` (was `_routing_event_repo`) -- routing event DTO mapping
- `_call_loader: CallLoader` (was `_call_repo`) -- call DTO mapping
- `_token_outcome_loader: TokenOutcomeLoader` (was `_token_outcome_repo`) -- token outcome DTO mapping

**Internal calls:**
- `explain_row()` calls `self.get_row()` (same class)
- `get_row_data()` calls `self.get_row()` (same class)

**Cross-mixin calls:** NONE -- fully independent. All internal calls are within QueryMethodsMixin.

**External imports required:**

```python
import json
import logging
from typing import Any

from sqlalchemy import select

from elspeth.contracts import (
    Call,
    NodeState,
    Row,
    RowLineage,
    Token,
    TokenOutcome,
    TokenParent,
)
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.core.landscape.row_data import RowDataResult, RowDataState
from elspeth.core.landscape.schema import (
    calls_table,
    node_states_table,
    routing_events_table,
    rows_table,
    token_outcomes_table,
    token_parents_table,
    tokens_table,
)
```

**TYPE_CHECKING imports that must become runtime imports** (needed as constructor parameter types):

```python
from elspeth.contracts import RoutingEvent
from elspeth.contracts.payload_store import PayloadStore
from elspeth.core.landscape._database_ops import DatabaseOps
from elspeth.core.landscape.model_loaders import (  # renamed from repositories in Phase A
    CallLoader,
    NodeStateLoader,
    RoutingEventLoader,
    RowLoader,
    TokenLoader,
    TokenOutcomeLoader,
    TokenParentLoader,
)
```

Note: `LandscapeDB` is NOT needed by QueryRepository. It only uses `DatabaseOps` for queries. This makes it the lightest-weight repository, suitable for giving read-only access to the MCP server or exporter without exposing the full DB handle.

**Callers:** All external code calls these methods via `LandscapeRecorder`. No file imports `QueryMethodsMixin` directly (only `recorder.py` imports it for inheritance).

---

## Query Method Overlap Note

After Phases B1-B3, domain repositories have their own `get_*` methods for internal use (e.g., `RunLifecycleRepository.get_run()`, `ExecutionRepository.get_batch()`). QueryRepository provides the external read-only API used by the MCP server, exporter, CLI, and TUI. Some methods exist in both a domain repository and QueryRepository -- this is intentional to avoid circular dependencies between repositories. Each repository is independently testable and has no dependency on another repository.

---

## Task 1: Create QueryRepository class

**File to create:** `src/elspeth/core/landscape/query_repository.py`

**Prerequisite reads (mandatory before writing any code):**
1. Read `src/elspeth/core/landscape/_query_methods.py` in full
2. Read `src/elspeth/core/landscape/recorder.py` in full (to confirm current attribute names after B1-B3)
3. Read `src/elspeth/core/landscape/model_loaders.py` (to confirm loader class names after Phase A rename)
4. Read `tests/core/landscape/test_query_methods.py` (to confirm existing test coverage — these tests exercise all 18 methods via `LandscapeRecorder` and will continue to work unchanged after extraction)

**Steps:**

0. Verify Phase B3 complete before proceeding:
   ```bash
   ls src/elspeth/core/landscape/data_flow_repository.py  # must succeed
   grep 'TokenRecordingMixin' src/elspeth/core/landscape/recorder.py  # must return 0 hits
   ```
   If either check fails, STOP -- Phase B3 is not complete.

1. Create the file with this module docstring:
   ```python
   """QueryRepository: read-only queries for audit trail entities.

   Extracted from QueryMethodsMixin as part of T19 (Landscape mixin ->
   composed repository decomposition).

   Provides the external read-only API used by MCP server, exporter, CLI,
   and TUI. Does NOT need LandscapeDB -- only DatabaseOps for queries.
   This makes it the lightest-weight repository.
   """
   ```

2. Write the `__init__` signature. The constructor receives injected dependencies:

   ```python
   class QueryRepository:
       """Read-only query repository for audit trail entities."""

       _QUERY_CHUNK_SIZE = 500

       def __init__(
           self,
           ops: DatabaseOps,
           *,
           row_loader: RowLoader,
           token_loader: TokenLoader,
           token_parent_loader: TokenParentLoader,
           node_state_loader: NodeStateLoader,
           routing_event_loader: RoutingEventLoader,
           call_loader: CallLoader,
           token_outcome_loader: TokenOutcomeLoader,
           payload_store: PayloadStore | None = None,
       ) -> None:
           self._ops = ops
           self._row_loader = row_loader
           self._token_loader = token_loader
           self._token_parent_loader = token_parent_loader
           self._node_state_loader = node_state_loader
           self._routing_event_loader = routing_event_loader
           self._call_loader = call_loader
           self._token_outcome_loader = token_outcome_loader
           self._payload_store = payload_store
   ```

   Note: No `db: LandscapeDB` parameter and no `self._db`. QueryRepository only needs `DatabaseOps` for read-only query execution.

3. Copy ALL 18 public methods from QueryMethodsMixin, preserving their exact signatures, docstrings, and implementations.

4. Update all `self._*_repo` attribute references to `self._*_loader` (Phase A rename convention):
   - `self._row_repo` --> `self._row_loader`
   - `self._token_repo` --> `self._token_loader`
   - `self._token_parent_repo` --> `self._token_parent_loader`
   - `self._node_state_repo` --> `self._node_state_loader`
   - `self._routing_event_repo` --> `self._routing_event_loader`
   - `self._call_repo` --> `self._call_loader`
   - `self._token_outcome_repo` --> `self._token_outcome_loader`

5. Internal calls remain unchanged:
   - `explain_row()` calls `self.get_row()` (same class)
   - `get_row_data()` calls `self.get_row()` (same class)

6. Move `_QUERY_CHUNK_SIZE = 500` from module-level to a class constant. Both the module-level and class-constant forms work; prefer class constant for consistency with the B2 pattern (`_TERMINAL_BATCH_STATUSES`).

   **IMPORTANT:** When moving `_QUERY_CHUNK_SIZE` from module-level to class constant, update ALL references in `get_routing_events_for_states()` and `get_calls_for_states()` to use `self._QUERY_CHUNK_SIZE` or `QueryRepository._QUERY_CHUNK_SIZE`. Bare `_QUERY_CHUNK_SIZE` will produce a NameError at runtime.

7. Merge all imports. Move the TYPE_CHECKING-only imports (`DatabaseOps`, `PayloadStore`, the loader classes) into runtime imports since they are now constructor parameter types. The `RoutingEvent` import must also be a runtime import since it appears in return types.

**Verification:** The new file should have exactly 19 `def` statements: the `__init__` plus 18 public methods.

---

## Task 2: Update recorder.py

**File:** `src/elspeth/core/landscape/recorder.py`

**Prerequisite reads (mandatory before editing):**
1. Read `src/elspeth/core/landscape/recorder.py` in full (re-read; will have changed after B1-B3)
2. Read the newly created `src/elspeth/core/landscape/query_repository.py` to confirm the class name and constructor

**Steps:**

1. **Remove from inheritance list:** Delete `QueryMethodsMixin` from the `class LandscapeRecorder(...)` bases. Since B3 is complete (verified in Task 1 step 0), `QueryMethodsMixin` is the sole remaining parent. After removal the class becomes:

   ```python
   class LandscapeRecorder:
   ```

   If any OTHER mixin parents are still present, STOP — a prior phase was incomplete. Do not proceed until that is resolved.

2. **Remove import:** Delete the mixin import:
   ```python
   from elspeth.core.landscape._query_methods import QueryMethodsMixin
   ```

3. **Add import:**
   ```python
   from elspeth.core.landscape.query_repository import QueryRepository
   ```

4. **In `__init__`:** Construct QueryRepository with loader instances already created in `__init__`:

   ```python
   self._query = QueryRepository(
       self._ops,
       row_loader=self._row_loader,
       token_loader=self._token_loader,
       token_parent_loader=self._token_parent_loader,
       node_state_loader=self._node_state_loader,
       routing_event_loader=self._routing_event_loader,
       call_loader=self._call_loader,
       token_outcome_loader=self._token_outcome_loader,
       payload_store=payload_store,
   )
   ```

   Note: Uses `self._ops` (not `db` or `self._db`) and all the `_*_loader` attribute names from Phase A.

5. **Add 18 delegation methods.** Each method on LandscapeRecorder delegates to `self._query`. Every delegation method must have the EXACT same signature (parameter names, types, defaults, return type) as the QueryRepository method:

   ```python
   def get_rows(self, run_id: str) -> list[Row]:
       return self._query.get_rows(run_id)

   def get_tokens(self, row_id: str) -> list[Token]:
       return self._query.get_tokens(row_id)

   def get_node_states_for_token(self, token_id: str) -> list[NodeState]:
       return self._query.get_node_states_for_token(token_id)

   def get_row(self, row_id: str) -> Row | None:
       return self._query.get_row(row_id)

   def get_row_data(self, row_id: str) -> RowDataResult:
       return self._query.get_row_data(row_id)

   def get_token(self, token_id: str) -> Token | None:
       return self._query.get_token(token_id)

   def get_token_parents(self, token_id: str) -> list[TokenParent]:
       return self._query.get_token_parents(token_id)

   def get_routing_events(self, state_id: str) -> list[RoutingEvent]:
       return self._query.get_routing_events(state_id)

   def get_calls(self, state_id: str) -> list[Call]:
       return self._query.get_calls(state_id)

   def get_routing_events_for_states(self, state_ids: list[str]) -> list[RoutingEvent]:
       return self._query.get_routing_events_for_states(state_ids)

   def get_calls_for_states(self, state_ids: list[str]) -> list[Call]:
       return self._query.get_calls_for_states(state_ids)

   def get_all_tokens_for_run(self, run_id: str) -> list[Token]:
       return self._query.get_all_tokens_for_run(run_id)

   def get_all_node_states_for_run(self, run_id: str) -> list[NodeState]:
       return self._query.get_all_node_states_for_run(run_id)

   def get_all_routing_events_for_run(self, run_id: str) -> list[RoutingEvent]:
       return self._query.get_all_routing_events_for_run(run_id)

   def get_all_calls_for_run(self, run_id: str) -> list[Call]:
       return self._query.get_all_calls_for_run(run_id)

   def get_all_token_parents_for_run(self, run_id: str) -> list[TokenParent]:
       return self._query.get_all_token_parents_for_run(run_id)

   def get_all_token_outcomes_for_run(self, run_id: str) -> list[TokenOutcome]:
       return self._query.get_all_token_outcomes_for_run(run_id)

   def explain_row(self, run_id: str, row_id: str) -> RowLineage | None:
       return self._query.explain_row(run_id, row_id)
   ```

6. **Add necessary imports** to recorder.py for the type annotations used in delegation method signatures. The types needed across the 18 signatures include:
   - From `elspeth.contracts`: `Call`, `NodeState`, `Row`, `RowLineage`, `Token`, `TokenOutcome`, `TokenParent`, `RoutingEvent`
   - From `elspeth.core.landscape.row_data`: `RowDataResult`

   Check what recorder.py already imports (after B1-B3 changes) and only add what is missing. With `from __future__ import annotations` in place, TYPE_CHECKING imports work for signatures.

---

## Task 3: Delete `_query_methods.py`

**File to delete:** `src/elspeth/core/landscape/_query_methods.py`

**Steps:**

1. Delete the file:
   ```bash
   git rm src/elspeth/core/landscape/_query_methods.py
   ```

2. Verify no other files import from this module:
   ```bash
   grep -rn '_query_methods' src/elspeth/
   ```
   Expected: 0 hits. The only importer was `recorder.py` (updated in Task 2).

3. Update `recorder.py` module docstring: remove the line referencing `_query_methods.py` and ensure the docstring reflects the new architecture.

---

## Task 4: Clean up LandscapeRecorder to pure facade

**File:** `src/elspeth/core/landscape/recorder.py`

After Task 3, LandscapeRecorder should be a pure facade. Verify and clean up:

1. **Verify zero inheritance.** The class definition should be:
   ```python
   class LandscapeRecorder:
   ```
   If any mixin parents remain, something went wrong in a prior phase. Do NOT remove them here -- go back and fix the missing extraction first.

2. **Verify `__init__` creates 4 repositories.** The constructor should:
   - Create `DatabaseOps`
   - Instantiate all model loaders
   - Create `self._run_lifecycle = RunLifecycleRepository(...)`
   - Create `self._execution = ExecutionRepository(...)`
   - Create `self._data_flow = DataFlowRepository(...)`
   - Create `self._query = QueryRepository(...)`
   - Nothing else (no thread-safety state, no mixin setup)

3. **Update the module docstring** to reflect the final architecture:

   ```python
   """LandscapeRecorder: pure facade for audit trail recording.

   Delegates to 4 composed domain repositories:
   - RunLifecycleRepository: run lifecycle, graph registration, export
   - ExecutionRepository: node states, external calls, batch management
   - DataFlowRepository: rows, tokens, errors
   - QueryRepository: read-only queries, bulk retrieval, lineage

   The public API is 100% unchanged -- all ~91 methods delegate directly
   to the appropriate repository. No logic in this file.
   """
   ```

4. **Remove any dead imports.** After all mixins are gone, `recorder.py` should not import from any `_*_recording.py` or `_query_methods.py` file. Clean up any leftover imports that were only needed by mixin code.

5. **Verify approximate line count.** The file should be ~250-300 lines total:
   - Module docstring: ~10 lines
   - Imports: ~30 lines
   - Class docstring: ~15 lines
   - `__init__`: ~30 lines
   - ~91 delegation methods at ~2-3 lines each: ~180-270 lines

   If the file is significantly larger than 350 lines, something is wrong (likely residual implementation code that should be in a repository).

---

## Task 5: Update `__init__.py` if needed

**File:** `src/elspeth/core/landscape/__init__.py`

**Steps:**

1. Read `src/elspeth/core/landscape/__init__.py` in full.

2. Verify it does NOT import anything from deleted files. It should import from:
   - `recorder.py` (LandscapeRecorder)
   - `database.py` (LandscapeDB)
   - `exporter.py` (LandscapeExporter)
   - `formatters.py` (formatters)
   - `lineage.py` (explain)
   - `reproducibility.py` (grades)
   - `row_data.py` (RowDataResult)
   - `schema.py` (tables)
   - `elspeth.contracts` (domain models)

   It should NOT import from any `_*_recording.py` or `_query_methods.py` files.

3. If the current `__init__.py` imports from `repositories.py` (the old name before Phase A rename), verify this was updated to `model_loaders.py` in Phase A. If not, update it.

4. **Do NOT add `QueryRepository` to `__init__.py`.** Note: B1–B3 added `RunLifecycleRepository`, `ExecutionRepository`, and `DataFlowRepository` to `__init__.py` exports during their respective phases. Leave those existing exports in place — removing them would be a breaking change to import paths used by tests and other modules. The consistency rule for B4 is: do not add `QueryRepository` to the public API since it is the lightest-weight repository (no `LandscapeDB` dependency) and its primary future use case is direct injection into MCP/exporter consumers, which is a follow-on task.

---

## Task 6: Verify `_helpers.py` and `_database_ops.py` are still needed

**Files:** `src/elspeth/core/landscape/_helpers.py`, `src/elspeth/core/landscape/_database_ops.py`

These two underscore files are NOT mixins -- they are utility modules used by the new repository files.

**Steps:**

1. Verify `_helpers.py` is imported by the repository files:
   ```bash
   grep -rn 'from elspeth.core.landscape._helpers' src/elspeth/core/landscape/
   ```
   Expected: Hits in `run_lifecycle_repository.py`, `execution_repository.py`, `data_flow_repository.py` (all use `generate_id`, `now`). QueryRepository does NOT use `_helpers.py` (it only reads, never generates IDs or timestamps).

2. Verify `_database_ops.py` is imported by the repository files:
   ```bash
   grep -rn 'from elspeth.core.landscape._database_ops\|DatabaseOps' src/elspeth/core/landscape/
   ```
   Expected: Hits in all 4 repository files and `recorder.py`.

3. Both files should remain. Do NOT delete them.

---

## Task 7: Full verification suite

Run all checks in order, stopping on first failure:

1. **Tests:** `.venv/bin/python -m pytest tests/ -x -q` -- ALL tests pass.

2. **Type checking:** `.venv/bin/python -m mypy src/` -- clean (no new errors).

3. **Linting:** `.venv/bin/python -m ruff check src/` -- clean (no new errors).

4. **Verify final file layout.** Confirm these files exist:
   ```bash
   ls -1 src/elspeth/core/landscape/__init__.py \
         src/elspeth/core/landscape/_database_ops.py \
         src/elspeth/core/landscape/_helpers.py \
         src/elspeth/core/landscape/database.py \
         src/elspeth/core/landscape/model_loaders.py \
         src/elspeth/core/landscape/run_lifecycle_repository.py \
         src/elspeth/core/landscape/execution_repository.py \
         src/elspeth/core/landscape/data_flow_repository.py \
         src/elspeth/core/landscape/query_repository.py \
         src/elspeth/core/landscape/recorder.py \
         src/elspeth/core/landscape/exporter.py \
         src/elspeth/core/landscape/formatters.py \
         src/elspeth/core/landscape/journal.py \
         src/elspeth/core/landscape/lineage.py \
         src/elspeth/core/landscape/reproducibility.py \
         src/elspeth/core/landscape/row_data.py \
         src/elspeth/core/landscape/schema.py
   ```

5. **Verify ALL deleted files are gone:**
   ```bash
   # All 8 mixin files must be deleted
   for f in _run_recording.py _graph_recording.py _node_state_recording.py \
            _token_recording.py _call_recording.py _batch_recording.py \
            _error_recording.py _query_methods.py; do
     test ! -f "src/elspeth/core/landscape/$f" || echo "ERROR: $f still exists"
   done

   # Old repositories.py must be deleted (renamed to model_loaders.py in Phase A)
   test ! -f src/elspeth/core/landscape/repositories.py || echo "ERROR: repositories.py still exists"
   ```

6. **Verify NO `Mixin` classes remain in landscape:**
   ```bash
   grep -rn 'class.*Mixin' src/elspeth/core/landscape/
   ```
   Expected: 0 hits.

7. **Verify NO imports from deleted files:**
   ```bash
   grep -rn '_run_recording\|_graph_recording\|_node_state_recording\|_token_recording\|_call_recording\|_batch_recording\|_error_recording\|_query_methods' src/elspeth/
   ```
   Expected: 0 hits.

8. **Verify LandscapeRecorder has no mixin parents:**
   ```bash
   grep -n 'class LandscapeRecorder' src/elspeth/core/landscape/recorder.py
   ```
   Expected: `class LandscapeRecorder:` -- no parenthesized bases.

9. **Verify 4 repository attributes are constructed:**
   ```bash
   grep -n 'self\._run_lifecycle\|self\._execution\|self\._data_flow\|self\._query' src/elspeth/core/landscape/recorder.py | head -8
   ```
   Expected: 4 construction lines in `__init__` plus delegation references.

If any verification step fails, fix the issue before proceeding to Task 8.

---

## Task 8: Commit

```bash
git add -A src/elspeth/core/landscape/
git commit -m "$(cat <<'EOF'
refactor(t19): extract QueryRepository and finalize facade

Phase B4+C: QueryMethodsMixin -> QueryRepository. LandscapeRecorder
is now a pure facade with zero inheritance, delegating ~91 methods
to 4 composed domain repositories.

Final layout: RunLifecycleRepository, ExecutionRepository,
DataFlowRepository, QueryRepository. All 8 mixins eliminated.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Risk Assessment

**Risk: LOW.** This is the safest mixin extraction and the simplest of the four:

1. **Zero cross-mixin calls.** QueryMethodsMixin never calls methods defined in other mixins. All internal calls (`explain_row` -> `get_row`, `get_row_data` -> `get_row`) stay within the same class.

2. **No shared mutable state.** The mixin reads from `self._ops` and the loader instances but never mutates them. No locking, no counters, no caches.

3. **No callers import the mixin directly.** Only `recorder.py` uses it (for inheritance). All external callers go through `LandscapeRecorder`.

4. **Read-only operations only.** QueryRepository does not write to the database. It only uses `execute_fetchone` and `execute_fetchall` -- never `execute_insert` or `execute_update`. This means it cannot corrupt state even if something goes wrong.

5. **No LandscapeDB dependency.** QueryRepository is the only repository that does not need `LandscapeDB` directly -- it only needs `DatabaseOps`. This makes it trivially instantiable for testing or for giving read-only access to external consumers (MCP server, exporter).

6. **Delegation is mechanical.** Each method forwards arguments verbatim with no transformation. All 18 delegations are one-liners.

**Potential gotchas:**

- **`_payload_store` is optional.** Both `get_row_data()` and `explain_row()` check `if self._payload_store is None` before using it. This null-check pattern is correct (payload store is an optional integration, not a bug workaround). Preserve it.

- **Chunking constant scope.** `_QUERY_CHUNK_SIZE` is currently module-level (line 48). Moving it to a class constant (`QueryRepository._QUERY_CHUNK_SIZE = 500`) keeps it encapsulated. The internal references `_QUERY_CHUNK_SIZE` in method bodies must be updated to `self._QUERY_CHUNK_SIZE` or the class-qualified `QueryRepository._QUERY_CHUNK_SIZE`. Alternatively, keep it module-level in the new file -- either approach works; be consistent.

- **Phase C finalization scope.** Task 4 assumes ALL prior phases (B1, B2, B3) are complete. If any mixin still appears in the inheritance list when Task 4 runs, STOP and investigate which phase was incomplete. Do not remove mixin parents that weren't extracted to repositories.

---

## Follow-On Notes

- **MCP server coupling narrowing:** `src/elspeth/mcp/analyzers/queries.py` accepts `recorder: LandscapeRecorder` but only calls read-only methods. A future task could accept `QueryRepository` directly, eliminating unnecessary write-capability exposure. Do not attempt in this plan.

- **`explain_row()` vs `get_row_data()` payload handling inconsistency (pre-existing):** `explain_row()` handles `json.JSONDecodeError` and `OSError` separately while `get_row_data()` only handles `KeyError`. This inconsistency is preserved from the original -- log as separate audit task, do not fix in B4.

---

## Definition of Done

- [ ] `_query_methods.py` deleted
- [ ] `query_repository.py` exists with `QueryRepository` class (18 public methods + `__init__`)
- [ ] `QueryRepository.__init__` takes `(ops, *, row_loader, ..., payload_store=None)` -- no `LandscapeDB`, no inheritance
- [ ] LandscapeRecorder inherits from NOTHING (pure `class LandscapeRecorder:`)
- [ ] All 8 mixin files deleted (`_run_recording.py`, `_graph_recording.py`, `_node_state_recording.py`, `_token_recording.py`, `_call_recording.py`, `_batch_recording.py`, `_error_recording.py`, `_query_methods.py`)
- [ ] Old `repositories.py` confirmed absent (renamed to `model_loaders.py` in Phase A — this is a confirmation check, not a B4 action)
- [ ] 4 domain repository files exist (`run_lifecycle_repository.py`, `execution_repository.py`, `data_flow_repository.py`, `query_repository.py`)
- [ ] `recorder.py` is ~250-300 lines (facade only, no implementation logic)
- [ ] `recorder.py` constructs 4 repositories in `__init__`
- [ ] All ~91 delegation methods forward arguments verbatim (no logic)
- [ ] `_helpers.py` and `_database_ops.py` still exist and are used by repository files
- [ ] `__init__.py` does NOT export `QueryRepository` (B1-B3 repos remain exported — leave as-is)
- [ ] No `class.*Mixin` definitions remain anywhere in `core/landscape/`
- [ ] No imports from deleted mixin files remain anywhere in `src/elspeth/`
- [ ] All tests pass
- [ ] mypy clean
- [ ] ruff clean
