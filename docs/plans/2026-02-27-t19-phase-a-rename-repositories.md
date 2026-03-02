# T19 Phase A: Rename DTO Repositories to Model Loaders

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename existing DTO mapper classes from `*Repository` to `*Loader` to free the "Repository" name for domain repositories in later phases.

**Architecture:** Pure mechanical rename. File `repositories.py` becomes `model_loaders.py`. All 15 `*Repository` classes become `*Loader`. All import sites updated. No behavior changes.

**Tech Stack:** Python 3.12, SQLAlchemy Core, pytest, mypy, ruff

**Prerequisites:**
- On branch `RC3.3-architectural-remediation`
- All tests passing before starting

---

## The 15 Classes to Rename

| Before | After |
|--------|-------|
| `RunRepository` | `RunLoader` |
| `NodeRepository` | `NodeLoader` |
| `EdgeRepository` | `EdgeLoader` |
| `RowRepository` | `RowLoader` |
| `TokenRepository` | `TokenLoader` |
| `TokenParentRepository` | `TokenParentLoader` |
| `CallRepository` | `CallLoader` |
| `RoutingEventRepository` | `RoutingEventLoader` |
| `BatchRepository` | `BatchLoader` |
| `NodeStateRepository` | `NodeStateLoader` |
| `ValidationErrorRepository` | `ValidationErrorLoader` |
| `TransformErrorRepository` | `TransformErrorLoader` |
| `TokenOutcomeRepository` | `TokenOutcomeLoader` |
| `ArtifactRepository` | `ArtifactLoader` |
| `BatchMemberRepository` | `BatchMemberLoader` |

## Files That Import From repositories.py

These are the ONLY importers (verified by grep):

**Runtime imports (not in TYPE_CHECKING):**
- `src/elspeth/core/landscape/recorder.py:36` -- imports all 15, creates instances as `self._*_repo`
- `tests/unit/core/landscape/test_repositories.py:49` -- imports all 15, instantiates in tests

**TYPE_CHECKING imports (used for type hints only):**
- `src/elspeth/core/landscape/_batch_recording.py:28`
- `src/elspeth/core/landscape/_query_methods.py:38`
- `src/elspeth/core/landscape/_run_recording.py:31`
- `src/elspeth/core/landscape/_error_recording.py:34`
- `src/elspeth/core/landscape/_node_state_recording.py:38`
- `src/elspeth/core/landscape/_token_recording.py:32`
- `src/elspeth/core/landscape/_graph_recording.py:30`
- `src/elspeth/core/landscape/_call_recording.py:33`

---

## Task 1: Rename the file and all class names

**Files:**
- Rename: `src/elspeth/core/landscape/repositories.py` -> `src/elspeth/core/landscape/model_loaders.py`

**Steps:**

1. `git mv src/elspeth/core/landscape/repositories.py src/elspeth/core/landscape/model_loaders.py`

2. Inside `model_loaders.py`:

   a. Update the module docstring: `"""Repository layer for Landscape audit models."""` -> `"""Model loaders for Landscape audit records."""`

   b. Rename all 15 classes from `*Repository` to `*Loader`, including their class-specific docstrings (e.g. `"""Repository for Run records."""` -> `"""Loader for Run records."""`). Do NOT rename "Repository" in comments that discuss the repository pattern conceptually.

   The replacements in class definitions:
   - `class RunRepository` -> `class RunLoader`
   - `class NodeRepository` -> `class NodeLoader`
   - `class EdgeRepository` -> `class EdgeLoader`
   - `class RowRepository` -> `class RowLoader`
   - `class TokenRepository` -> `class TokenLoader`
   - `class TokenParentRepository` -> `class TokenParentLoader`
   - `class CallRepository` -> `class CallLoader`
   - `class RoutingEventRepository` -> `class RoutingEventLoader`
   - `class BatchRepository` -> `class BatchLoader`
   - `class NodeStateRepository` -> `class NodeStateLoader`
   - `class ValidationErrorRepository` -> `class ValidationErrorLoader`
   - `class TransformErrorRepository` -> `class TransformErrorLoader`
   - `class TokenOutcomeRepository` -> `class TokenOutcomeLoader`
   - `class ArtifactRepository` -> `class ArtifactLoader`
   - `class BatchMemberRepository` -> `class BatchMemberLoader`

3. **Verify:** `grep -c 'class.*Loader' src/elspeth/core/landscape/model_loaders.py` should return `15`.

---

## Task 2: Update recorder.py imports and attribute names

**File:** `src/elspeth/core/landscape/recorder.py`

**Steps:**

1. Update the import path:
   - `from elspeth.core.landscape.repositories import ...` -> `from elspeth.core.landscape.model_loaders import ...`

2. Update all 15 class names in the import list:
   - `RunRepository` -> `RunLoader`
   - `NodeRepository` -> `NodeLoader`
   - `EdgeRepository` -> `EdgeLoader`
   - `RowRepository` -> `RowLoader`
   - `TokenRepository` -> `TokenLoader`
   - `TokenParentRepository` -> `TokenParentLoader`
   - `CallRepository` -> `CallLoader`
   - `RoutingEventRepository` -> `RoutingEventLoader`
   - `BatchRepository` -> `BatchLoader`
   - `NodeStateRepository` -> `NodeStateLoader`
   - `ValidationErrorRepository` -> `ValidationErrorLoader`
   - `TransformErrorRepository` -> `TransformErrorLoader`
   - `TokenOutcomeRepository` -> `TokenOutcomeLoader`
   - `ArtifactRepository` -> `ArtifactLoader`
   - `BatchMemberRepository` -> `BatchMemberLoader`

3. In `__init__` (and any other methods), rename all `self._*_repo` attribute assignments and references to `self._*_loader`:
   - `self._run_repo` -> `self._run_loader`
   - `self._node_repo` -> `self._node_loader`
   - `self._edge_repo` -> `self._edge_loader`
   - `self._row_repo` -> `self._row_loader`
   - `self._token_repo` -> `self._token_loader`
   - `self._token_parent_repo` -> `self._token_parent_loader`
   - `self._call_repo` -> `self._call_loader`
   - `self._routing_event_repo` -> `self._routing_event_loader`
   - `self._batch_repo` -> `self._batch_loader`
   - `self._node_state_repo` -> `self._node_state_loader`
   - `self._validation_error_repo` -> `self._validation_error_loader`
   - `self._transform_error_repo` -> `self._transform_error_loader`
   - `self._token_outcome_repo` -> `self._token_outcome_loader`
   - `self._artifact_repo` -> `self._artifact_loader`
   - `self._batch_member_repo` -> `self._batch_member_loader`

   **Important:** Also update the right-hand side of assignments where the old class name is used as a constructor call, e.g. `self._run_repo = RunRepository(...)` -> `self._run_loader = RunLoader(...)`.

4. Update the comment on line 105: `# Repository instances for row-to-object conversions` -> `# Loader instances for row-to-object conversions`.

---

## Task 3: Update all 8 mixin TYPE_CHECKING imports

**Files:** All 8 `_*.py` mixin files listed below.

For each file, apply two changes:

### 3a. Update the import statement

Change the import path and class names:
- `from elspeth.core.landscape.repositories import ...` -> `from elspeth.core.landscape.model_loaders import ...`
- Rename each imported class from `*Repository` to `*Loader`

### 3b. Rename `self._*_repo` references to `self._*_loader`

The mixin files access recorder attributes via `self` because they are mixed into `LandscapeRecorder`. Search each file for `self._*_repo` and rename to `self._*_loader`.

**File-by-file checklist:**

1. **`src/elspeth/core/landscape/_batch_recording.py`**
   - Update import path and class names
   - Rename `self._*_repo` -> `self._*_loader` throughout

2. **`src/elspeth/core/landscape/_query_methods.py`**
   - Update import path and class names
   - Rename `self._*_repo` -> `self._*_loader` throughout

3. **`src/elspeth/core/landscape/_run_recording.py`**
   - Update import path and class names
   - Rename `self._*_repo` -> `self._*_loader` throughout

4. **`src/elspeth/core/landscape/_error_recording.py`**
   - Update import path and class names
   - Rename `self._*_repo` -> `self._*_loader` throughout

5. **`src/elspeth/core/landscape/_node_state_recording.py`**
   - Update import path and class names
   - Rename `self._*_repo` -> `self._*_loader` throughout

6. **`src/elspeth/core/landscape/_token_recording.py`**
   - Update import path and class names
   - Rename `self._*_repo` -> `self._*_loader` throughout

7. **`src/elspeth/core/landscape/_graph_recording.py`**
   - Update import path and class names
   - Rename `self._*_repo` -> `self._*_loader` throughout

8. **`src/elspeth/core/landscape/_call_recording.py`**
   - Update import path and class names
   - Rename `self._*_repo` -> `self._*_loader` throughout

---

## Task 3c: Update the test file

**File:** `tests/unit/core/landscape/test_repositories.py`

**Steps:**

1. Update the import path:
   - `from elspeth.core.landscape.repositories import ...` -> `from elspeth.core.landscape.model_loaders import ...`

2. Rename all 15 imported class names in the import list from `*Repository` to `*Loader` (same mapping as Task 1).

3. Rename all instantiation sites throughout the file:
   - Variable names: `repo = RunRepository(...)` -> `loader = RunLoader(...)`, etc.
   - Any other references to `*Repository` class names in test code.

4. Rename test classes and their docstrings to reflect the new names:
   - `class TestRunRepository:` -> `class TestRunLoader:`
   - `"""Tests for RunRepository.load()."""` -> `"""Tests for RunLoader.load()."""`
   - Apply the same pattern for all 15 test classes.

5. Rename the test file:
   - `git mv tests/unit/core/landscape/test_repositories.py tests/unit/core/landscape/test_model_loaders.py`

---

## Task 4: Update __init__.py if it re-exports anything from repositories.py

**File:** `src/elspeth/core/landscape/__init__.py`

**Steps:**

1. Check whether the file re-exports any `*Repository` classes from `repositories.py`.
2. If it does: update the import path to `model_loaders` and rename the classes to `*Loader`.
3. If it does NOT re-export any Repository classes (expected based on prior analysis): no changes needed. Move on.

---

## Task 5: Run verification

Run in order, stopping on first failure:

1. **Tests:** `.venv/bin/python -m pytest tests/ -x -q` -- all tests must pass.
2. **Type checking:** `.venv/bin/python -m mypy src/` -- no new type errors.
3. **Linting:** `.venv/bin/python -m ruff check src/` -- no new lint errors.
4. **Residual references check (source):**
   - `grep -rn 'repositories' src/elspeth/core/landscape/` -- should return 0 hits (the old module name should not appear anywhere).
   - `grep -rn '_repo\b' src/elspeth/core/landscape/` -- should return 0 hits (no `_repo` attribute references should remain; note `\b` is a word boundary so `_reporter` or similar will not match).
   - `grep -rn 'Repository' src/elspeth/core/landscape/model_loaders.py` -- should return 0 hits (all class definitions and their docstrings must say `Loader`).
5. **Residual references check (tests):**
   - `grep -rn 'repositories' tests/unit/core/landscape/` -- should return 0 hits (old module name must not appear in test imports or file names).
   - `grep -rn '_repo\b' tests/unit/core/landscape/` -- should return 0 hits (no `_repo` variable names should remain in tests).

If any verification step fails, fix the issue before proceeding to Task 6.

---

## Task 6: Commit

```bash
git add src/elspeth/core/landscape/ tests/unit/core/landscape/
git commit -m "refactor(t19): rename DTO repositories to model loaders

Phase A of T19: mechanical rename to free 'Repository' name for
domain repositories. repositories.py -> model_loaders.py, all 15
*Repository classes -> *Loader, all self._*_repo -> self._*_loader.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Definition of Done

- [ ] `repositories.py` no longer exists
- [ ] `model_loaders.py` contains 15 `*Loader` classes
- [ ] All imports updated across 10 files (recorder.py + 8 mixins + test file)
- [ ] All `self._*_repo` renamed to `self._*_loader` across recorder + 8 mixins
- [ ] Test file updated and renamed (`test_repositories.py` -> `test_model_loaders.py`)
- [ ] Module docstring and all 15 class docstrings updated from "Repository" to "Loader"
- [ ] Comment in `recorder.py` updated from "Repository instances" to "Loader instances"
- [ ] All tests pass
- [ ] mypy clean (no new errors)
- [ ] ruff clean (no new errors)
- [ ] No residual references to `repositories` or `_repo` in `src/elspeth/core/landscape/` or `tests/unit/core/landscape/`
