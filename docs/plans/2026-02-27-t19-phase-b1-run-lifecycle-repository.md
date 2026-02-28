# T19 Phase B1: Extract RunLifecycleRepository

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract RunRecordingMixin into a composed RunLifecycleRepository class, removing the first mixin from LandscapeRecorder's inheritance chain.

**Architecture:** RunRecordingMixin becomes a standalone class that receives its dependencies (LandscapeDB, DatabaseOps, RunLoader) via constructor injection. LandscapeRecorder creates this repository in __init__ and delegates all run lifecycle methods to it.

**Tech Stack:** Python 3.12, SQLAlchemy Core, pytest, mypy, ruff

**Prerequisites:**
- Phase A complete (repositories.py renamed to model_loaders.py, RunRepository renamed to RunLoader, all `self._run_repo` renamed to `self._run_loader`)
- All tests passing before starting

---

## RunRecordingMixin Analysis

**File:** `src/elspeth/core/landscape/_run_recording.py` (544 lines)

**Public methods (15):**

| # | Method | Signature |
|---|--------|-----------|
| 1 | `begin_run` | `(self, config: dict[str, Any], canonical_version: str, *, run_id: str \| None = None, reproducibility_grade: str \| None = None, status: RunStatus = RunStatus.RUNNING, source_schema_json: str \| None = None, schema_contract: SchemaContract \| None = None) -> Run` |
| 2 | `complete_run` | `(self, run_id: str, status: RunStatus, *, reproducibility_grade: str \| None = None) -> Run` |
| 3 | `get_run` | `(self, run_id: str) -> Run \| None` |
| 4 | `get_source_schema` | `(self, run_id: str) -> str` |
| 5 | `record_source_field_resolution` | `(self, run_id: str, resolution_mapping: dict[str, str], normalization_version: str \| None) -> None` |
| 6 | `get_source_field_resolution` | `(self, run_id: str) -> dict[str, str] \| None` |
| 7 | `update_run_status` | `(self, run_id: str, status: RunStatus) -> None` |
| 8 | `update_run_contract` | `(self, run_id: str, contract: SchemaContract) -> None` |
| 9 | `get_run_contract` | `(self, run_id: str) -> SchemaContract \| None` |
| 10 | `record_secret_resolutions` | `(self, run_id: str, resolutions: list[dict[str, Any]]) -> None` |
| 11 | `get_secret_resolutions_for_run` | `(self, run_id: str) -> list[SecretResolution]` |
| 12 | `list_runs` | `(self, *, status: RunStatus \| None = None) -> list[Run]` |
| 13 | `set_export_status` | `(self, run_id: str, status: ExportStatus, *, error: str \| None = None, export_format: str \| None = None, export_sink: str \| None = None) -> None` |
| 14 | `finalize_run` | `(self, run_id: str, status: RunStatus) -> Run` |
| 15 | `compute_reproducibility_grade` | `(self, run_id: str) -> ReproducibilityGrade` |

**Shared state accessed (all via self):**
- `self._db: LandscapeDB` -- direct DB connection (**only** used by `compute_reproducibility_grade` via `compute_grade(self._db, run_id)`; all other methods use `_ops`)
- `self._ops: DatabaseOps` -- insert/update/fetch helper (used by most methods)
- `self._run_loader: RunLoader` -- SA Row to Run conversion (used by `get_run`, `list_runs`; renamed from `_run_repo` in Phase A)

Note: the mixin also declares `self._payload_store: PayloadStore | None` in its type annotations, but **no method in the mixin actually uses it**. Do NOT pass payload_store to RunLifecycleRepository.

**Cross-mixin calls:** NONE -- fully independent. Internal calls only:
- `finalize_run()` calls `self.compute_reproducibility_grade()` and `self.complete_run()`
- `complete_run()` calls `self.get_run()` to verify run exists

**Module-level constant:** `_TERMINAL_RUN_STATUSES` -- move into the new file.

**Imports used:**

```python
import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from elspeth.contracts import (
    ContractAuditRecord,
    ExportStatus,
    Run,
    RunStatus,
    SecretResolution,
)
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.core.canonical import canonical_json, stable_hash
from elspeth.core.landscape._helpers import generate_id, now
from elspeth.core.landscape.schema import runs_table, secret_resolutions_table

# TYPE_CHECKING only:
from elspeth.contracts.schema_contract import SchemaContract
from elspeth.core.landscape._database_ops import DatabaseOps
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.model_loaders import RunLoader  # renamed from RunRepository in Phase A
from elspeth.core.landscape.reproducibility import ReproducibilityGrade
```

**Callers:** All 18 runtime files and 68 test files call these methods via `LandscapeRecorder`. No file imports `RunRecordingMixin` directly (only `recorder.py` imports it for inheritance).

---

## Task 1: Create RunLifecycleRepository class

**Prerequisite verification (do this FIRST, before any work):**

```bash
# Verify Phase A complete:
ls src/elspeth/core/landscape/model_loaders.py   # must succeed
grep '_run_loader' src/elspeth/core/landscape/recorder.py  # must return hits
```

If either check fails, STOP and complete Phase A first.

**Copy-safety note:** Copy method bodies only after Phase A renames are applied. The plan's code snippets reflect post-Phase-A naming (`RunLoader`, `self._run_loader`). If the current file still uses `RunRepository`/`self._run_repo`, Phase A has not been applied.

**Files:**
- Create: `src/elspeth/core/landscape/run_lifecycle_repository.py`

Read `_run_recording.py` fully. Create `RunLifecycleRepository` as a plain class (no inheritance) with:

1. `__init__(self, db: LandscapeDB, ops: DatabaseOps, run_loader: RunLoader)` -- store as `self._db`, `self._ops`, `self._run_loader`
2. Copy ALL 15 public methods from RunRecordingMixin, preserving their exact signatures, docstrings, and implementations
3. Copy the module-level constant `_TERMINAL_RUN_STATUSES` into the new file
4. Copy all imports from `_run_recording.py`, adjusting as needed:
   - Remove `PayloadStore` (not used by any method)
   - Change `RunRepository` to `RunLoader` and import from `model_loaders` (Phase A rename)
   - Move `DatabaseOps`, `LandscapeDB`, `RunLoader`, and `ReproducibilityGrade` from TYPE_CHECKING into runtime imports since they are now constructor parameters or return types
5. All internal `self.method()` calls continue to work -- they now refer to methods on the same class
6. The `compute_reproducibility_grade` method uses a lazy import (`from elspeth.core.landscape.reproducibility import compute_grade`); preserve this as-is

**Verification:** The new file should have exactly 15 `def` statements (the `__init__` plus 15 public methods = 16 total).

---

## Task 2: Update recorder.py

**File:** `src/elspeth/core/landscape/recorder.py`

1. Remove `RunRecordingMixin` from the `LandscapeRecorder` class inheritance list (line 56)
2. Remove the import of `RunRecordingMixin` from `_run_recording` (line 33)
3. Add import: `from elspeth.core.landscape.run_lifecycle_repository import RunLifecycleRepository`
4. In `__init__`, after `self._run_loader = RunLoader()` (Phase A name), create the repository:
   ```python
   self._run_lifecycle = RunLifecycleRepository(db, self._ops, self._run_loader)
   ```
5. Add 15 delegation methods to `LandscapeRecorder`. Each must have the IDENTICAL signature (parameters, defaults, return type) as the original mixin method. Use thin delegation -- no logic, just forward the call:

   ```python
   def begin_run(
       self,
       config: dict[str, Any],
       canonical_version: str,
       *,
       run_id: str | None = None,
       reproducibility_grade: str | None = None,
       status: RunStatus = RunStatus.RUNNING,
       source_schema_json: str | None = None,
       schema_contract: SchemaContract | None = None,
   ) -> Run:
       """Begin a new pipeline run. Delegates to RunLifecycleRepository."""
       return self._run_lifecycle.begin_run(
           config,
           canonical_version,
           run_id=run_id,
           reproducibility_grade=reproducibility_grade,
           status=status,
           source_schema_json=source_schema_json,
           schema_contract=schema_contract,
       )

   def complete_run(
       self,
       run_id: str,
       status: RunStatus,
       *,
       reproducibility_grade: str | None = None,
   ) -> Run:
       """Complete a pipeline run. Delegates to RunLifecycleRepository."""
       return self._run_lifecycle.complete_run(
           run_id, status, reproducibility_grade=reproducibility_grade,
       )

   def get_run(self, run_id: str) -> Run | None:
       """Get a run by ID. Delegates to RunLifecycleRepository."""
       return self._run_lifecycle.get_run(run_id)

   def get_source_schema(self, run_id: str) -> str:
       """Get source schema JSON for a run. Delegates to RunLifecycleRepository."""
       return self._run_lifecycle.get_source_schema(run_id)

   def record_source_field_resolution(
       self,
       run_id: str,
       resolution_mapping: dict[str, str],
       normalization_version: str | None,
   ) -> None:
       """Record field resolution mapping. Delegates to RunLifecycleRepository."""
       self._run_lifecycle.record_source_field_resolution(
           run_id, resolution_mapping, normalization_version,
       )

   def get_source_field_resolution(self, run_id: str) -> dict[str, str] | None:
       """Get source field resolution mapping. Delegates to RunLifecycleRepository."""
       return self._run_lifecycle.get_source_field_resolution(run_id)

   def update_run_status(self, run_id: str, status: RunStatus) -> None:
       """Update run status. Delegates to RunLifecycleRepository."""
       self._run_lifecycle.update_run_status(run_id, status)

   def update_run_contract(self, run_id: str, contract: SchemaContract) -> None:
       """Update run with schema contract. Delegates to RunLifecycleRepository."""
       self._run_lifecycle.update_run_contract(run_id, contract)

   def get_run_contract(self, run_id: str) -> SchemaContract | None:
       """Get schema contract for a run. Delegates to RunLifecycleRepository."""
       return self._run_lifecycle.get_run_contract(run_id)

   def record_secret_resolutions(
       self,
       run_id: str,
       resolutions: list[dict[str, Any]],
   ) -> None:
       """Record secret resolution events. Delegates to RunLifecycleRepository."""
       self._run_lifecycle.record_secret_resolutions(run_id, resolutions)

   def get_secret_resolutions_for_run(self, run_id: str) -> list[SecretResolution]:
       """Get secret resolutions for a run. Delegates to RunLifecycleRepository."""
       return self._run_lifecycle.get_secret_resolutions_for_run(run_id)

   def list_runs(self, *, status: RunStatus | None = None) -> list[Run]:
       """List all runs. Delegates to RunLifecycleRepository."""
       return self._run_lifecycle.list_runs(status=status)

   def set_export_status(
       self,
       run_id: str,
       status: ExportStatus,
       *,
       error: str | None = None,
       export_format: str | None = None,
       export_sink: str | None = None,
   ) -> None:
       """Set export status for a run. Delegates to RunLifecycleRepository."""
       self._run_lifecycle.set_export_status(
           run_id, status, error=error,
           export_format=export_format, export_sink=export_sink,
       )

   def finalize_run(self, run_id: str, status: RunStatus) -> Run:
       """Finalize a run. Delegates to RunLifecycleRepository."""
       return self._run_lifecycle.finalize_run(run_id, status)

   def compute_reproducibility_grade(self, run_id: str) -> ReproducibilityGrade:
       """Compute reproducibility grade. Delegates to RunLifecycleRepository."""
       return self._run_lifecycle.compute_reproducibility_grade(run_id)
   ```

**Import additions needed in recorder.py** for the delegation signatures:

```python
from typing import Any  # if not already imported

# These are needed for method signatures (may need to be added or moved from TYPE_CHECKING):
from elspeth.contracts import (
    ContractAuditRecord,  # only if used in signatures
    ExportStatus,
    Run,
    RunStatus,
    SecretResolution,
)
from elspeth.contracts.errors import AuditIntegrityError  # only if used
```

**Note on `ContractAuditRecord`:** Do NOT import `ContractAuditRecord` into recorder.py -- it is only used inside the repository implementation (within `update_run_contract`), not in any delegation signature.

Check which of these are already imported via TYPE_CHECKING or transitively. The delegation methods reference `RunStatus`, `Run`, `ExportStatus`, `SecretResolution`, `SchemaContract`, `ReproducibilityGrade`, and `Any` in their signatures -- all must be importable at runtime (not just under TYPE_CHECKING). Use `from __future__ import annotations` to defer evaluation if needed, which recorder.py already has.

**CRITICAL:** The public method signatures on LandscapeRecorder must be IDENTICAL to before. Same parameters, same defaults, same return types. Callers must not see any change.

---

## Task 3: Update the module docstring in recorder.py

**File:** `src/elspeth/core/landscape/recorder.py`

Update the module docstring to reflect that `_run_recording.py` is no longer a mixin. Change:

```
- _run_recording.py: Run lifecycle (begin, complete, finalize, secrets, contracts)
```

to:

```
- run_lifecycle_repository.py: Run lifecycle (begin, complete, finalize, secrets, contracts) [composed repository]
```

---

## Task 4: Delete the mixin file

**File:** `src/elspeth/core/landscape/_run_recording.py`

Delete this file entirely. After Phase A, it will have been updated to use `RunLoader` / `model_loaders` naming, but with this phase it is fully replaced by `run_lifecycle_repository.py`.

Verify deletion: `ls src/elspeth/core/landscape/_run_recording.py` should fail.

---

## Task 5: Run verification

Run in order, stopping on first failure:

1. **Tests:** `.venv/bin/python -m pytest tests/ -x -q` -- all tests must pass
2. **Type checking:** `.venv/bin/python -m mypy src/` -- no new type errors
3. **Linting:** `.venv/bin/python -m ruff check src/` -- no new lint errors
4. **Structural checks:**
   - Verify `_run_recording.py` is deleted: `ls src/elspeth/core/landscape/_run_recording.py` should fail
   - Verify `RunRecordingMixin` no longer exists anywhere: `grep -rn 'RunRecordingMixin' src/elspeth/` should return 0 hits
   - Verify `LandscapeRecorder` no longer inherits from `RunRecordingMixin`: check the class definition in `recorder.py`
   - Verify `RunLifecycleRepository` exists: `grep -n 'class RunLifecycleRepository' src/elspeth/core/landscape/run_lifecycle_repository.py`
   - Verify delegation attribute exists: `grep -n '_run_lifecycle' src/elspeth/core/landscape/recorder.py`
   - Verify all 15 methods are delegated: `grep -c 'self._run_lifecycle\.' src/elspeth/core/landscape/recorder.py` should return 15

If any verification step fails, fix the issue before proceeding to Task 6.

---

## Task 6: Commit

```bash
git add src/elspeth/core/landscape/
git commit -m "refactor(t19): extract RunLifecycleRepository from RunRecordingMixin

Phase B1: first mixin extraction. RunRecordingMixin -> standalone
RunLifecycleRepository with explicit constructor injection (LandscapeDB,
DatabaseOps, RunLoader). LandscapeRecorder delegates all 15 run lifecycle
methods. No caller-visible changes.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Risk Assessment

**Risk: LOW.** This is the safest mixin extraction because:

1. **Zero cross-mixin calls.** RunRecordingMixin never calls methods defined in other mixins. All internal calls (`finalize_run` -> `compute_reproducibility_grade` -> `complete_run` -> `get_run`) stay within the same class.
2. **No shared mutable state.** The mixin reads from `self._db`, `self._ops`, and `self._run_loader` but never mutates them. No locking, no counters, no caches.
3. **No callers import the mixin directly.** Only `recorder.py` uses it (for inheritance). All external callers go through `LandscapeRecorder`.
4. **Delegation is mechanical.** Each method forwards arguments verbatim with no transformation.

**Potential gotcha:** The `_payload_store` annotation on the mixin. It is declared as shared state (`_payload_store: PayloadStore | None`) but never used by any method. Do NOT propagate it to `RunLifecycleRepository`. If a future method needs it, it can be added then.

---

## Definition of Done

- [ ] `_run_recording.py` deleted
- [ ] `run_lifecycle_repository.py` exists with `RunLifecycleRepository` class (15 public methods + `__init__`)
- [ ] `RunLifecycleRepository.__init__` takes `(db, ops, run_loader)` -- no inheritance
- [ ] `LandscapeRecorder` no longer inherits from `RunRecordingMixin`
- [ ] `LandscapeRecorder.__init__` creates `self._run_lifecycle = RunLifecycleRepository(...)`
- [ ] `LandscapeRecorder` delegates all 15 run methods to `self._run_lifecycle`
- [ ] All delegation method signatures are identical to the original mixin methods
- [ ] No references to `RunRecordingMixin` remain anywhere in `src/`
- [ ] All tests pass
- [ ] mypy clean
- [ ] ruff clean
