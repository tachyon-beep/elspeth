# T19 Phase B3: Extract DataFlowRepository

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract 3 data-tracking mixins into a composed DataFlowRepository, the highest-risk extraction due to atomic transaction requirements in fork/coalesce/expand.

**Architecture:** TokenRecordingMixin + GraphRecordingMixin + ErrorRecordingMixin -> single DataFlowRepository class. Atomic transactions for fork/coalesce/expand preserved via direct LandscapeDB.connection() usage. Token ownership validation deduplicated between Token and Error recording.

**Tech Stack:** Python 3.12, SQLAlchemy Core, pytest, mypy, ruff

**Prerequisites:**
- Phase B2 complete (ExecutionRepository extracted)
- All tests passing before starting

> **⚠ NOTE — Plan verified against post-B1/B2 codebase (2026-02-28).**
>
> This plan was originally written before Phase A remediation and Phase B1/B2 execution.
> It has since been reviewed against the actual source files and updated to match reality.
> Key verifications performed:
>
> 1. **All 3 mixin files read in full** — method inventories, signatures, imports, and shared state confirmed accurate.
> 2. **recorder.py current state confirmed** — inheritance chain, `__init__` structure, B1/B2 delegation patterns all accounted for.
> 3. **Constructor excludes unused loaders** — `_row_loader` and `_token_loader` are declared in mixin type annotations but never referenced in method bodies. Correctly omitted from `DataFlowRepository.__init__`.
> 4. **CI/CD config updates added** — `enforce_tier_model/core.yaml` and `contracts-whitelist.yaml` entries that reference old mixin files are handled in Task 3a.
> 5. **`__init__.py` update added** — `DataFlowRepository` export added in Task 2.
>
> **Action:** Still read the actual source files before copying — method bodies are the source of truth, not this plan's summaries.

---

## Mixin Analysis

### TokenRecordingMixin (`_token_recording.py`, 809 lines) -- MOST COMPLEX

**Public methods (8):**

| Method | Signature | Notes |
|--------|-----------|-------|
| `create_row` | `(run_id, source_node_id, row_index, data, *, row_id=None, quarantined=False) -> Row` | Handles Tier 3 non-canonical data via `repr_hash` fallback; payload store persistence |
| `create_token` | `(row_id, *, token_id=None, branch_name=None, fork_group_id=None, join_group_id=None) -> Token` | Derives `run_id` from row record (Tier 1 lookup) |
| `fork_token` | `(parent_token_id, row_id, branches, *, run_id, step_in_pipeline=None) -> tuple[list[Token], str]` | **ATOMIC** -- children + parent FORKED outcome in single transaction |
| `coalesce_tokens` | `(parent_token_ids, row_id, *, step_in_pipeline=None) -> Token` | **ATOMIC** -- merged token + parent relationships in single transaction |
| `expand_token` | `(parent_token_id, row_id, count, *, run_id, step_in_pipeline=None, record_parent_outcome=True) -> tuple[list[Token], str]` | **ATOMIC** -- children + optional parent EXPANDED outcome in single transaction |
| `record_token_outcome` | `(run_id, token_id, outcome, *, sink_name=None, batch_id=None, fork_group_id=None, join_group_id=None, expand_group_id=None, error_hash=None, context=None) -> str` | Returns `outcome_id`; validates outcome-specific required fields |
| `get_token_outcome` | `(token_id) -> TokenOutcome | None` | Returns terminal outcome (preferred) or most recent non-terminal |
| `get_token_outcomes_for_row` | `(run_id, row_id) -> list[TokenOutcome]` | JOIN query -- tokens + outcomes; critical for explain() disambiguation |

**Private helpers (5):**

| Method | Signature | Notes |
|--------|-----------|-------|
| `_resolve_run_id_for_row` | `(row_id) -> str` | Tier 1 lookup; crashes on missing row |
| `_resolve_token_ownership` | `(token_id) -> tuple[str, str]` | Returns `(row_id, run_id)`; crashes on missing token |
| `_validate_token_run_ownership` | `(token_id, run_id) -> None` | Crashes on cross-run contamination |
| `_validate_token_row_ownership` | `(token_id, row_id) -> None` | Crashes on cross-row lineage corruption |
| `_validate_outcome_fields` | `(outcome, *, sink_name, batch_id, fork_group_id, join_group_id, expand_group_id, error_hash) -> None` | Contract enforcement for outcome-specific required fields |

**Shared state (declared):** `_db`, `_ops`, `_row_loader`, `_token_loader`, `_token_outcome_loader`, `_payload_store`

**Note:** `_row_loader` and `_token_loader` are declared as type annotations for the mixin pattern but are **never referenced** in any method body. They are correctly excluded from the `DataFlowRepository` constructor.

**CRITICAL:** `fork_token`, `coalesce_tokens`, and `expand_token` use `self._db.connection()` for atomic multi-insert transactions. This pattern MUST be preserved exactly -- it ensures children and parent outcomes are recorded atomically with no crash window.

### GraphRecordingMixin (`_graph_recording.py`, 365 lines)

**Public methods (9):**

| Method | Signature | Notes |
|--------|-----------|-------|
| `register_node` | `(run_id, plugin_name, node_type, plugin_version, config, *, node_id=None, sequence=None, schema_hash=None, determinism=DETERMINISTIC, schema_config, input_contract=None, output_contract=None) -> Node` | Canonicalizes config; stores schema contracts as audit records. Note: `plugin_version` is a positional param between `node_type` and `config`. |
| `register_edge` | `(run_id, from_node_id, to_node_id, label, mode, *, edge_id=None) -> Edge` | Stores `RoutingMode` as string value |
| `get_node` | `(node_id, run_id) -> Node | None` | **COMPOSITE PK** -- requires both `node_id` and `run_id` |
| `get_nodes` | `(run_id) -> list[Node]` | Ordered by `sequence_in_pipeline` (NULL last), then `registered_at`, then `node_id` |
| `get_node_contracts` | `(run_id, node_id) -> tuple[SchemaContract | None, SchemaContract | None]` | Returns `(input_contract, output_contract)` via `ContractAuditRecord` deserialization |
| `get_edges` | `(run_id) -> list[Edge]` | Ordered by `created_at` then `edge_id` for deterministic export |
| `get_edge` | `(edge_id) -> Edge` | Tier 1 -- crashes on missing edge (audit integrity violation) |
| `get_edge_map` | `(run_id) -> dict[tuple[str, str], str]` | Maps `(from_node_id, label) -> edge_id`; used for FK integrity in routing events |
| `update_node_output_contract` | `(run_id, node_id, contract) -> None` | Updates after first-row inference or schema evolution |

**Shared state:** `_ops`, `_node_loader`, `_edge_loader`

### ErrorRecordingMixin (`_error_recording.py`, 298 lines)

**Public methods (6):**

| Method | Signature | Notes |
|--------|-----------|-------|
| `record_validation_error` | `(run_id, node_id, row_data, error, schema_mode, destination, *, contract_violation=None) -> str` | Tier 3 boundary -- `row_data` may be non-canonical; falls back to `repr_hash`/`NonCanonicalMetadata` |
| `record_transform_error` | `(run_id, token_id, transform_id, row_data, error_details, destination) -> str` | Validates token-run ownership; `error_details` may contain non-canonical values |
| `get_validation_errors_for_row` | `(run_id, row_hash) -> list[ValidationErrorRecord]` | Keyed by `row_hash` since quarantined rows never get `row_id` |
| `get_validation_errors_for_run` | `(run_id) -> list[ValidationErrorRecord]` | Ordered by `created_at` |
| `get_transform_errors_for_token` | `(token_id) -> list[TransformErrorRecord]` | |
| `get_transform_errors_for_run` | `(run_id) -> list[TransformErrorRecord]` | Ordered by `created_at` |

**Private helpers (1):**

| Method | Signature | Notes |
|--------|-----------|-------|
| `_validate_token_run_ownership_for_error` | `(token_id, run_id) -> None` | **DUPLICATE** of TokenRecording's `_validate_token_run_ownership` |

**Shared state:** `_ops`, `_validation_error_loader`, `_transform_error_loader`

### Deduplication Target

`ErrorRecordingMixin._validate_token_run_ownership_for_error()` (lines 136-161 of `_error_recording.py`) does the exact same query as `TokenRecordingMixin._validate_token_run_ownership()` (lines 99-118 of `_token_recording.py`):

- Both query `tokens_table` for `run_id` where `token_id` matches
- Both raise `AuditIntegrityError` if token not found
- Both raise `AuditIntegrityError` if `run_id` does not match
- Only the error messages differ slightly ("before recording outcomes" vs "in record_transform_error")

When merged into `DataFlowRepository`, these become one method: `_validate_token_run_ownership(token_id, run_id)`. The implementation from `TokenRecordingMixin` is preferred because it delegates to `_resolve_token_ownership()` (which is also being moved), avoiding a separate query. The error recording version does a direct single-column query which is slightly more efficient but creates code duplication.

**Resolution:** Use the `_resolve_token_ownership` pattern (from TokenRecording). It performs one query returning `(row_id, run_id)` and is reused by `_validate_token_row_ownership` too. `record_transform_error()` calls `self._validate_token_run_ownership()` instead of the deleted `_validate_token_run_ownership_for_error()`.

---

## Combined Dependency Summary

The DataFlowRepository needs these constructor parameters:

| Parameter | Type | Used By |
|-----------|------|---------|
| `db` | `LandscapeDB` | TokenRecording (atomic transactions in fork/coalesce/expand) |
| `ops` | `DatabaseOps` | All 3 mixins (every DB operation) |
| `token_outcome_loader` | `TokenOutcomeLoader` | TokenRecording (`get_token_outcome`, `get_token_outcomes_for_row`) |
| `node_loader` | `NodeLoader` | GraphRecording (`get_node`, `get_nodes`) |
| `edge_loader` | `EdgeLoader` | GraphRecording (`get_edges`, `get_edge`) |
| `validation_error_loader` | `ValidationErrorLoader` | ErrorRecording (all `get_validation_errors_*` methods) |
| `transform_error_loader` | `TransformErrorLoader` | ErrorRecording (all `get_transform_errors_*` methods) |
| `payload_store` | `PayloadStore | None` | TokenRecording (`create_row` payload persistence) |

**Excluded:** `RowLoader` and `TokenLoader` are declared as mixin type annotations but never referenced in any method body — omitted from constructor.

**Note on naming:** Phase A has been applied — all DTO mapper classes are now `*Loader` with `*_loader` attributes. The table above reflects the current naming.

---

## Task 1: Create DataFlowRepository class

**Files:**
- Create: `src/elspeth/core/landscape/data_flow_repository.py`

**Steps:**

0. **Verify Phase B2 complete:**
   ```bash
   ls src/elspeth/core/landscape/execution_repository.py  # Must succeed
   grep 'CallRecordingMixin' src/elspeth/core/landscape/recorder.py  # Must return 0 hits
   ```

1. Read all 3 mixin files fully:
   - `src/elspeth/core/landscape/_token_recording.py` (809 lines)
   - `src/elspeth/core/landscape/_graph_recording.py` (365 lines)
   - `src/elspeth/core/landscape/_error_recording.py` (298 lines)

2. Create `DataFlowRepository` as a plain class (NOT a mixin -- no shared state annotations, explicit `__init__`).

3. Constructor signature:
   ```python
   class DataFlowRepository:
       """Records data flow: tokens, rows, graph structure, and errors.

       Consolidates TokenRecordingMixin + GraphRecordingMixin + ErrorRecordingMixin.
       Atomic transactions in fork/coalesce/expand preserved via direct
       LandscapeDB.connection() usage.

       NOTE: nodes table has composite PK (node_id, run_id). Always filter
       by both columns when querying individual nodes.
       """

       def __init__(
           self,
           db: LandscapeDB,
           ops: DatabaseOps,
           *,
           token_outcome_loader: TokenOutcomeLoader,
           node_loader: NodeLoader,
           edge_loader: EdgeLoader,
           validation_error_loader: ValidationErrorLoader,
           transform_error_loader: TransformErrorLoader,
           payload_store: PayloadStore | None = None,
       ) -> None:
   ```
   Store all as `self._db`, `self._ops`, `self._token_outcome_loader`, etc.

   **Constructor note:** `_db` is used exclusively by the three atomic Token methods (`fork_token`, `coalesce_tokens`, `expand_token`) for `with self._db.connection() as conn:` blocks. Graph and Error methods use `_ops` exclusively.

4. Copy ALL 23 public methods from the 3 mixins, preserving signatures exactly:
   - From TokenRecordingMixin (8): `create_row`, `create_token`, `fork_token`, `coalesce_tokens`, `expand_token`, `record_token_outcome`, `get_token_outcome`, `get_token_outcomes_for_row`
   - From GraphRecordingMixin (9): `register_node`, `register_edge`, `get_node`, `get_nodes`, `get_node_contracts`, `get_edges`, `get_edge`, `get_edge_map`, `update_node_output_contract`
   - From ErrorRecordingMixin (6): `record_validation_error`, `record_transform_error`, `get_validation_errors_for_row`, `get_validation_errors_for_run`, `get_transform_errors_for_token`, `get_transform_errors_for_run`

5. Copy private helpers from TokenRecordingMixin (5): `_resolve_run_id_for_row`, `_resolve_token_ownership`, `_validate_token_run_ownership`, `_validate_token_row_ownership`, `_validate_outcome_fields`

6. **DEDUPLICATE:** Do NOT copy `_validate_token_run_ownership_for_error` from ErrorRecordingMixin. Instead, update `record_transform_error` to call `self._validate_token_run_ownership(token_id, run_id)` (the method from TokenRecordingMixin that delegates to `_resolve_token_ownership`).

7. Build the merged import set from all 3 mixin files. **Read each mixin's actual imports** — the list below is a guide, not the source of truth:

   **Runtime imports:**
   - `from __future__ import annotations`
   - `import json` (TokenRecording, ErrorRecording)
   - `import logging` (ErrorRecording)
   - `from typing import TYPE_CHECKING, Any`
   - `from sqlalchemy import select`
   - From `elspeth.contracts`: `ContractAuditRecord` (Graph), `Determinism` (Graph), `Edge` (Graph), `Node` (Graph), `NodeType` (Graph), `NonCanonicalMetadata` (Error), `Row` (Token), `RoutingMode` (Graph), `RowOutcome` (Token), `Token` (Token), `TokenOutcome` (Token), `TransformErrorReason` (Error), `TransformErrorRecord` (Error), `ValidationErrorRecord` (Error), `ValidationErrorWithContract` (Error)
   - From `elspeth.contracts.errors`: `AuditIntegrityError` (Token, Error)
   - From `elspeth.contracts.hashing`: `repr_hash` (Token, Error)
   - From `elspeth.core.canonical`: `canonical_json`, `stable_hash` (all 3)
   - From `elspeth.core.landscape._helpers`: `generate_id`, `now` (all 3)
   - From `elspeth.core.landscape._database_ops`: `DatabaseOps` (runtime — used in constructor)
   - From `elspeth.core.landscape.database`: `LandscapeDB` (runtime — used in constructor)
   - From `elspeth.core.landscape.model_loaders`: `EdgeLoader`, `NodeLoader`, `TokenOutcomeLoader`, `TransformErrorLoader`, `ValidationErrorLoader` (runtime — used in constructor)
   - From `elspeth.core.landscape.schema`: `edges_table`, `nodes_table` (Graph), `rows_table`, `token_outcomes_table`, `token_parents_table`, `tokens_table` (Token), `transform_errors_table`, `validation_errors_table` (Error)

   **TYPE_CHECKING imports:**
   - From `elspeth.contracts.errors`: `ContractViolation` (Error)
   - From `elspeth.contracts.payload_store`: `PayloadStore` (Token)
   - From `elspeth.contracts.schema_contract`: `PipelineRow` (Error), `SchemaContract` (Graph)
   - From `elspeth.contracts.schema`: `SchemaConfig` (Graph)

**CRITICAL PRESERVATION RULES:**
- `fork_token`, `coalesce_tokens`, `expand_token` use `with self._db.connection() as conn:` for atomic multi-insert. Copy these transaction blocks EXACTLY.
- `get_node` requires composite PK `(node_id, run_id)`. Preserve the dual-column WHERE clause.
- `record_validation_error` handles Tier 3 non-canonical data with `repr_hash`/`NonCanonicalMetadata` fallback. Preserve this pattern.
- `record_transform_error` wraps `error_details` serialization in try/except for non-canonical values. Preserve this pattern.
- `create_row` handles quarantined rows with `repr_hash` fallback for both hashing and payload serialization. Preserve this pattern.

---

## Task 2: Update recorder.py

**File:** `src/elspeth/core/landscape/recorder.py`

**Steps:**

1. Remove `TokenRecordingMixin`, `GraphRecordingMixin`, `ErrorRecordingMixin` from the inheritance list of `LandscapeRecorder`.

2. Remove their imports:
   ```python
   # DELETE these 3 lines:
   from elspeth.core.landscape._error_recording import ErrorRecordingMixin
   from elspeth.core.landscape._graph_recording import GraphRecordingMixin
   from elspeth.core.landscape._token_recording import TokenRecordingMixin
   ```

3. Add import for the new class:
   ```python
   from elspeth.core.landscape.data_flow_repository import DataFlowRepository
   ```

4. In `__init__`, after creating `self._ops` and all repository/loader instances, create the DataFlowRepository:
   ```python
   self._data_flow = DataFlowRepository(
       db,
       self._ops,
       token_outcome_loader=self._token_outcome_loader,
       node_loader=self._node_loader,
       edge_loader=self._edge_loader,
       validation_error_loader=self._validation_error_loader,
       transform_error_loader=self._transform_error_loader,
       payload_store=payload_store,
   )
   ```
   (Phase A naming applied: all attributes use `_*_loader` suffix.)

5. Add delegation methods for all 23 public methods. Each delegation method should:
   - Have the exact same signature as the original mixin method
   - Have a one-line docstring referencing the repository
   - Delegate to `self._data_flow.<method>(...)`
   - Pass through all arguments exactly

   Example delegation pattern:
   ```python
   def create_row(
       self,
       run_id: str,
       source_node_id: str,
       row_index: int,
       data: dict[str, Any],
       *,
       row_id: str | None = None,
       quarantined: bool = False,
   ) -> Row:
       """Create a source row record. Delegates to DataFlowRepository."""
       return self._data_flow.create_row(
           run_id, source_node_id, row_index, data,
           row_id=row_id, quarantined=quarantined,
       )
   ```

6. The 23 delegation methods (grouped by origin):

   **From TokenRecordingMixin (8):**
   - `create_row`
   - `create_token`
   - `fork_token`
   - `coalesce_tokens`
   - `expand_token`
   - `record_token_outcome`
   - `get_token_outcome`
   - `get_token_outcomes_for_row`

   **From GraphRecordingMixin (9):**
   - `register_node`
   - `register_edge`
   - `get_node`
   - `get_nodes`
   - `get_node_contracts`
   - `get_edges`
   - `get_edge`
   - `get_edge_map`
   - `update_node_output_contract`

   **From ErrorRecordingMixin (6):**
   - `record_validation_error`
   - `record_transform_error`
   - `get_validation_errors_for_row`
   - `get_validation_errors_for_run`
   - `get_transform_errors_for_token`
   - `get_transform_errors_for_run`

7. Update the module docstring to reflect that these 3 mixins have been replaced by `DataFlowRepository`. The current docstring (lines 1-18) lists the 3 mixins under "Mixins (inherited behavior)" — replace those 3 entries with a single entry under "Composed repositories":
   ```
   - data_flow_repository.py: Token/row lifecycle, graph structure, validation/transform errors
   ```

8. **Update `src/elspeth/core/landscape/__init__.py`:**
   Add `DataFlowRepository` to both the import block and `__all__`, matching the existing pattern for `ExecutionRepository` and `RunLifecycleRepository`:
   ```python
   from elspeth.core.landscape.data_flow_repository import DataFlowRepository
   ```
   Add `"DataFlowRepository"` to `__all__` in alphabetical position (after `"CSVFormatter"`).

---

## Task 3: Delete the 3 mixin files

**Files to delete:**
- `src/elspeth/core/landscape/_token_recording.py` (809 lines)
- `src/elspeth/core/landscape/_graph_recording.py` (365 lines)
- `src/elspeth/core/landscape/_error_recording.py` (298 lines)

**Steps:**

1. Delete all 3 files.
2. Verify no other files import from these modules:
   ```bash
   grep -rn '_token_recording\|_graph_recording\|_error_recording' src/elspeth/
   ```
   This should return zero hits after Task 2 is complete. If any imports remain, update them to import from `data_flow_repository` or remove them.

---

## Task 3a: Update CI/CD config files

The old mixin file paths and class names appear in two CI/CD config files. With `fail_on_stale: true` (see `config/cicd/enforce_tier_model/_defaults.yaml`), stale entries pointing to deleted files will **fail CI**.

**File 1: `config/cicd/enforce_tier_model/core.yaml`**

Update 4 allowlist entry keys. The file path and class name change; fingerprints are content-based and **may change** since the method bodies are being copied into a new class. The safest approach: delete the 4 old entries, then run the enforcement tool to regenerate with correct keys.

Old entries to delete:
```yaml
- key: core/landscape/_error_recording.py:R6:ErrorRecordingMixin:record_validation_error:fp=456420b45c227638
- key: core/landscape/_error_recording.py:R6:ErrorRecordingMixin:record_transform_error:fp=4f50497797b6f1eb
- key: core/landscape/_token_recording.py:R6:TokenRecordingMixin:create_row:fp=7bb3d062bfbc975d
- key: core/landscape/_token_recording.py:R6:TokenRecordingMixin:create_row:fp=b76283a08da8ae76
```

After deletion, run the enforcement tool to detect new findings in `data_flow_repository.py`:
```bash
.venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model
```

For each new finding, add a replacement entry with the same `owner`, `reason`, `safety`, and `expires` values — only the `key` changes (file path + class name).

**File 2: `config/cicd/contracts-whitelist.yaml`**

Update 4 entries (lines 185-192). Replace old mixin paths with new repository path:

| Old Entry | New Entry |
|-----------|-----------|
| `_token_recording.py:TokenRecordingMixin.create_row:data` | `data_flow_repository.py:DataFlowRepository.create_row:data` |
| `_token_recording.py:TokenRecordingMixin.record_token_outcome:context` | `data_flow_repository.py:DataFlowRepository.record_token_outcome:context` |
| `_graph_recording.py:GraphRecordingMixin.register_node:config` | `data_flow_repository.py:DataFlowRepository.register_node:config` |
| `_error_recording.py:ErrorRecordingMixin.record_transform_error:row_data` | `data_flow_repository.py:DataFlowRepository.record_transform_error:row_data` |

**Verify:** Run both tools after updates to confirm no stale/missing entries remain.

---

## Task 4: Run verification

Run in order, stopping on first failure:

1. **Full test suite:**
   ```bash
   .venv/bin/python -m pytest tests/ -x -q
   ```
   All tests must pass.

2. **Atomic operation tests specifically:**
   ```bash
   .venv/bin/python -m pytest tests/ -k "fork or coalesce or expand" -v
   ```
   These exercise the critical atomic transaction paths.

3. **Type checking:**
   ```bash
   .venv/bin/python -m mypy src/
   ```
   No new type errors.

4. **Linting:**
   ```bash
   .venv/bin/python -m ruff check src/
   ```
   No new lint errors.

5. **Verify deletions:**
   ```bash
   # These 3 files must not exist
   test ! -f src/elspeth/core/landscape/_token_recording.py
   test ! -f src/elspeth/core/landscape/_graph_recording.py
   test ! -f src/elspeth/core/landscape/_error_recording.py
   ```

6. **Verify new file exists:**
   ```bash
   test -f src/elspeth/core/landscape/data_flow_repository.py
   ```

7. **Verify no residual imports:**
   ```bash
   grep -rn 'TokenRecordingMixin\|GraphRecordingMixin\|ErrorRecordingMixin' src/elspeth/
   ```
   Should return zero hits.

8. **Tier model enforcement (CI/CD allowlist):**
   ```bash
   .venv/bin/python scripts/cicd/enforce_tier_model.py check --root src/elspeth --allowlist config/cicd/enforce_tier_model
   ```
   Must pass with no stale entries and no unallowlisted findings.

9. **Verify `DataFlowRepository` is exported:**
   ```bash
   grep 'DataFlowRepository' src/elspeth/core/landscape/__init__.py
   ```
   Must appear in both import and `__all__`.

If any verification step fails, fix the issue before proceeding to Task 5.

---

## Task 5: Commit

```bash
git add -A src/elspeth/core/landscape/ config/cicd/enforce_tier_model/core.yaml config/cicd/contracts-whitelist.yaml
git commit -m "refactor(t19): extract DataFlowRepository from 3 data-tracking mixins

Phase B3: TokenRecording + GraphRecording + ErrorRecording ->
DataFlowRepository. Token ownership validation deduplicated.
Atomic transactions in fork/coalesce/expand preserved.
CI/CD allowlists updated for new file path and class name.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Risk Notes

These are the highest-risk areas in this extraction. The implementer must pay special attention:

1. **Atomic transactions.** `fork_token`, `coalesce_tokens`, and `expand_token` use `with self._db.connection() as conn:` to ensure children and parent outcomes are written atomically. If this pattern is broken (e.g., by accidentally using `self._ops.execute_insert()` instead of `conn.execute()` inside the `with` block), there will be a crash window where children exist but the parent outcome is not recorded. This would corrupt the audit trail.

2. **Composite primary key.** The `nodes` table has a composite PK `(node_id, run_id)`. The `get_node()` method filters on both columns. If the `run_id` filter is accidentally dropped, queries will return ambiguous results when the same `node_id` exists across multiple runs. Document this in the class docstring.

3. **Tier 3 boundaries.** `record_validation_error` and `record_transform_error` handle external data that may contain non-canonical values (NaN, Infinity). The `repr_hash()` and `NonCanonicalMetadata` fallbacks are deliberate Tier 3 boundary handling -- do not simplify or remove them. The unguarded `stable_hash(row_data)` and `canonical_json(row_data)` calls in `record_transform_error` are INTENTIONALLY unguarded -- `row_data` is Tier 2 pipeline data. Do NOT add try/except around these during the merge.

4. **`create_row` quarantine path.** When `quarantined=True`, both hashing and payload serialization use fallback paths (`repr_hash` and `json.dumps({"_repr": repr(data)})` respectively). These paths exist because quarantined rows are Tier 3 external data that may not be canonically serializable. Do not merge the quarantine and normal code paths.

5. **Deduplication correctness.** When replacing `_validate_token_run_ownership_for_error()` with `_validate_token_run_ownership()`, verify that the error messages in `record_transform_error()` remain clear. The original error message says "in record_transform_error" which helps with debugging. The replacement method's message says "caller supplied run_id" which is less specific but still accurate. This is an acceptable trade-off for deduplication. The `record_transform_error` call site will receive the generic ownership error message ('corrupt the audit trail by attributing records to the wrong run') instead of the context-specific message ('attributing errors to the wrong run'). This is a deliberate trade-off for deduplication -- the generic message is still audit-appropriate.

---

## Follow-On Tasks

- **Pre-existing inefficiency in `coalesce_tokens`:** `coalesce_tokens` performs 2N queries before the transaction block (validate + resolve for each parent). Could be consolidated into 1 query per parent. Log as separate follow-on task, do not fix in B3.

---

## Definition of Done

- [ ] 3 mixin files deleted (`_token_recording.py`, `_graph_recording.py`, `_error_recording.py`)
- [ ] `data_flow_repository.py` exists with `DataFlowRepository` class
- [ ] All 23 public methods present in `DataFlowRepository`
- [ ] Token ownership validation deduplicated (1 method `_validate_token_run_ownership`, not 2)
- [ ] `_validate_token_run_ownership_for_error` does NOT exist in new class
- [ ] Atomic transactions preserved in `fork_token`, `coalesce_tokens`, `expand_token` (using `self._db.connection()`)
- [ ] All 23 methods delegated from `LandscapeRecorder` with identical signatures
- [ ] `LandscapeRecorder` no longer inherits from `TokenRecordingMixin`, `GraphRecordingMixin`, or `ErrorRecordingMixin`
- [ ] No imports from deleted mixin files remain anywhere in `src/elspeth/`
- [ ] `DataFlowRepository` exported from `landscape/__init__.py` (import + `__all__`)
- [ ] `config/cicd/enforce_tier_model/core.yaml` updated (4 entries: old mixin paths → new repository path)
- [ ] `config/cicd/contracts-whitelist.yaml` updated (4 entries: old mixin paths → new repository path)
- [ ] Tier model enforcement passes (`enforce_tier_model.py check` — no stale entries)
- [ ] All tests pass
- [ ] mypy clean (no new errors)
- [ ] ruff clean (no new errors)
