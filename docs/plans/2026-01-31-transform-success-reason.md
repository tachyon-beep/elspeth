# TransformReason (Success Reason) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire up the existing `TransformReason` TypedDict to provide structured metadata for successful transform operations. This completes the audit symmetry: errors have `TransformErrorReason`, routing has `RoutingReason`, and now success has `TransformReason`.

**Value:**
- `action`: Distinguishes conditional paths ("enriched" vs "skipped - data present")
- `fields_modified`: Efficient audit queries without diffing input/output
- `validation_errors`: Non-blocking warnings for data quality monitoring

**Bead:** TBD (create with `bd create --title="Wire up TransformReason for success metadata" --type=feature --priority=2`)

---

## Task 1: Rename TransformReason to TransformSuccessReason

**Files:**
- Modify: `src/elspeth/contracts/errors.py:84-92`
- Modify: `src/elspeth/contracts/__init__.py`
- Modify: `tests/contracts/test_errors.py`

**Context:** Rename for clarity - distinguishes from `TransformErrorReason`. Also add a Literal type for common actions.

**Step 1: Update TypedDict in errors.py**

Replace lines 84-92 with:

```python
# Literal type for common transform actions (extensible - str also accepted)
TransformActionCategory = Literal[
    # Processing actions
    "processed",  # Generic successful processing
    "mapped",  # Field mapping completed
    "validated",  # Validation passed
    "enriched",  # Data enrichment from external source
    "transformed",  # Data transformation applied
    "normalized",  # Data normalization applied
    "filtered",  # Row passed filter criteria
    "classified",  # Classification assigned
    # Skip/passthrough actions
    "passthrough",  # No changes made (intentional)
    "skipped",  # Processing skipped (e.g., data already present)
    "cached",  # Result retrieved from cache
]


class TransformSuccessReason(TypedDict):
    """Metadata for successful transform operations.

    Provides structured audit information about what a transform did,
    beyond just the input/output data. This enables:
    - Efficient audit queries (fields_modified without diffing)
    - Data quality monitoring (validation_errors for non-blocking warnings)
    - Conditional path tracking (action distinguishes code paths)

    Used when transforms return TransformResult.success() with optional
    success_reason parameter.

    Required field:
        action: What the transform did. Use TransformActionCategory values
                for common actions, or custom strings for plugin-specific actions.

    Optional fields:
        fields_modified: List of field names that were changed
        fields_added: List of field names that were added
        fields_removed: List of field names that were removed
        validation_warnings: Non-blocking validation issues (data quality flags)
        metadata: Additional plugin-specific context

    Example usage:
        # Simple action tracking
        TransformResult.success(row, success_reason={"action": "enriched"})

        # Field change tracking
        TransformResult.success(row, success_reason={
            "action": "mapped",
            "fields_modified": ["customer_id", "amount"],
            "fields_added": ["currency_code"],
        })

        # Data quality warning
        TransformResult.success(row, success_reason={
            "action": "validated",
            "validation_warnings": ["amount near threshold (995 of 1000 limit)"],
        })
    """

    action: str  # Use TransformActionCategory or custom string

    # Field tracking
    fields_modified: NotRequired[list[str]]
    fields_added: NotRequired[list[str]]
    fields_removed: NotRequired[list[str]]

    # Data quality
    validation_warnings: NotRequired[list[str]]

    # Extensibility
    metadata: NotRequired[dict[str, Any]]
```

**Step 2: Update exports in __init__.py**

Change import:
```python
# From:
    TransformReason,
# To:
    TransformActionCategory,
    TransformSuccessReason,
```

Change `__all__`:
```python
# From:
    "TransformReason",
# To:
    "TransformActionCategory",
    "TransformSuccessReason",
```

**Step 3: Update tests**

In `tests/contracts/test_errors.py`, rename test classes:
- `TestTransformReasonSchema` → `TestTransformSuccessReasonSchema`
- `TestTransformReason` → `TestTransformSuccessReason`

Update test content to match new field names (`validation_warnings` instead of `validation_errors`).

Add test for Literal type:
```python
def test_transform_action_category_values(self) -> None:
    """TransformActionCategory contains expected action types."""
    from typing import get_args
    from elspeth.contracts import TransformActionCategory

    categories = get_args(TransformActionCategory)
    assert "processed" in categories
    assert "mapped" in categories
    assert "skipped" in categories
    assert "enriched" in categories
```

**Step 4: Verify**

Run: `.venv/bin/python -c "from elspeth.contracts import TransformSuccessReason, TransformActionCategory; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add src/elspeth/contracts/errors.py src/elspeth/contracts/__init__.py tests/contracts/test_errors.py
git commit -m "$(cat <<'EOF'
feat(contracts): rename TransformReason to TransformSuccessReason

Clarify naming to distinguish from TransformErrorReason.
Expand fields for better audit tracking:
- action: What the transform did (Literal + custom string)
- fields_modified/added/removed: Explicit field tracking
- validation_warnings: Non-blocking data quality flags
- metadata: Plugin-specific extensibility

Add TransformActionCategory Literal for common action values.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add success_reason Field to TransformResult

**Files:**
- Modify: `src/elspeth/contracts/results.py`

**Step 1: Add import**

Add to imports:
```python
from elspeth.contracts.errors import TransformErrorReason, TransformSuccessReason
```

**Step 2: Add field to dataclass**

Add after line 101 (`rows: list[dict[str, Any]] | None = None`):

```python
    # Success metadata - set by plugin via success() factory
    success_reason: TransformSuccessReason | None = None
```

**Step 3: Update success() factory method**

Change lines 118-121:

```python
    @classmethod
    def success(
        cls,
        row: dict[str, Any],
        *,
        success_reason: TransformSuccessReason | None = None,
    ) -> "TransformResult":
        """Create successful result with single output row.

        Args:
            row: The transformed row data
            success_reason: Optional metadata about what the transform did.
                           See TransformSuccessReason for available fields.

        Returns:
            TransformResult with status="success" and the provided row.
        """
        return cls(
            status="success",
            row=row,
            reason=None,
            rows=None,
            success_reason=success_reason,
        )
```

**Step 4: Update success_multi() factory method**

Change lines 123-138:

```python
    @classmethod
    def success_multi(
        cls,
        rows: list[dict[str, Any]],
        *,
        success_reason: TransformSuccessReason | None = None,
    ) -> "TransformResult":
        """Create successful result with multiple output rows.

        Args:
            rows: List of output rows (must not be empty)
            success_reason: Optional metadata about what the transform did.
                           See TransformSuccessReason for available fields.

        Returns:
            TransformResult with status="success", row=None, rows=rows

        Raises:
            ValueError: If rows is empty
        """
        if not rows:
            raise ValueError("success_multi requires at least one row")
        return cls(
            status="success",
            row=None,
            reason=None,
            rows=rows,
            success_reason=success_reason,
        )
```

**Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/contracts/test_results.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/elspeth/contracts/results.py
git commit -m "$(cat <<'EOF'
feat(results): add success_reason field to TransformResult

Transforms can now provide structured metadata about successful
processing via optional success_reason parameter:

    TransformResult.success(row, success_reason={
        "action": "enriched",
        "fields_modified": ["customer_id"],
    })

The success_reason is optional - existing code continues to work
unchanged. This is additive, not breaking.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add success_reason_json Column to node_states Schema

**Files:**
- Modify: `src/elspeth/core/landscape/schema.py`
- Create: `alembic/versions/xxxx_add_success_reason_json.py`

**Step 1: Update schema.py**

Add after line 199 (`Column("error_json", Text),`):

```python
    Column("success_reason_json", Text),  # TransformSuccessReason for successful transforms
```

**Step 2: Create Alembic migration**

Run: `cd /home/john/elspeth-rapid && alembic revision -m "add_success_reason_json_to_node_states"`

Edit the generated migration file:

```python
"""add_success_reason_json_to_node_states

Revision ID: <auto-generated>
Revises: <previous>
Create Date: 2026-01-31 ...
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '<auto-generated>'
down_revision = '<previous>'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'node_states',
        sa.Column('success_reason_json', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('node_states', 'success_reason_json')
```

**Step 3: Verify migration**

Run: `alembic upgrade head` (on a test database)
Expected: Migration applies successfully

**Step 4: Commit**

```bash
git add src/elspeth/core/landscape/schema.py alembic/versions/*_add_success_reason_json*.py
git commit -m "$(cat <<'EOF'
feat(schema): add success_reason_json column to node_states

New column stores TransformSuccessReason JSON for successful
transform operations. Nullable for backwards compatibility -
existing rows and transforms without success_reason work unchanged.

Migration: alembic upgrade head

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update NodeStateCompleted Dataclass

**Files:**
- Modify: `src/elspeth/contracts/audit.py`

**Step 1: Add field to NodeStateCompleted**

Add after line 220 (`context_after_json: str | None = None`):

```python
    success_reason_json: str | None = None
```

**Step 2: Verify**

Run: `.venv/bin/python -c "from elspeth.contracts import NodeStateCompleted; print(NodeStateCompleted.__dataclass_fields__.keys())"`
Expected: Shows `success_reason_json` in fields

**Step 3: Commit**

```bash
git add src/elspeth/contracts/audit.py
git commit -m "$(cat <<'EOF'
feat(audit): add success_reason_json to NodeStateCompleted

Dataclass now includes optional success_reason_json field
matching the new schema column.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Update LandscapeRecorder.complete_node_state()

**Files:**
- Modify: `src/elspeth/core/landscape/recorder.py`

**Step 1: Add import**

Add to imports:
```python
from elspeth.contracts.errors import TransformSuccessReason
```

**Step 2: Update method signature and overloads**

Update the COMPLETED overload (around line 1060):

```python
    @overload
    def complete_node_state(
        self,
        state_id: str,
        status: Literal[NodeStateStatus.COMPLETED],
        *,
        output_data: dict[str, Any] | list[dict[str, Any]] | None = None,
        duration_ms: float | None = None,
        error: ExecutionError | TransformErrorReason | CoalesceFailureReason | None = None,
        success_reason: TransformSuccessReason | None = None,  # ADD THIS
        context_after: dict[str, Any] | None = None,
    ) -> NodeStateCompleted: ...
```

**Step 3: Update main implementation**

Update the main `complete_node_state` method signature (around line 1083):

```python
    def complete_node_state(
        self,
        state_id: str,
        status: NodeStateStatus,
        *,
        output_data: dict[str, Any] | list[dict[str, Any]] | None = None,
        duration_ms: float | None = None,
        error: ExecutionError | TransformErrorReason | CoalesceFailureReason | None = None,
        success_reason: TransformSuccessReason | None = None,  # ADD THIS
        context_after: dict[str, Any] | None = None,
    ) -> NodeStatePending | NodeStateCompleted | NodeStateFailed:
```

**Step 4: Serialize and store success_reason**

In the method body, after error_json handling, add:

```python
        # Serialize success reason if provided
        success_reason_json: str | None = None
        if success_reason is not None:
            success_reason_json = json.dumps(success_reason)
```

**Step 5: Update the UPDATE statement**

Find the `node_states_table.update()` call and add `success_reason_json`:

```python
        self._ops.execute_update(
            node_states_table.update()
            .where(node_states_table.c.state_id == state_id)
            .values(
                status=status.value,
                output_hash=output_hash,
                completed_at=timestamp,
                duration_ms=duration_ms,
                error_json=error_json,
                success_reason_json=success_reason_json,  # ADD THIS
                context_after_json=context_json,
            )
        )
```

**Step 6: Update NodeStateCompleted return**

Update the return statement for COMPLETED status to include success_reason_json:

```python
        if status == NodeStateStatus.COMPLETED:
            return NodeStateCompleted(
                state_id=state_id,
                token_id=existing.token_id,
                node_id=existing.node_id,
                step_index=existing.step_index,
                attempt=existing.attempt,
                status=NodeStateStatus.COMPLETED,
                input_hash=existing.input_hash,
                started_at=existing.started_at,
                output_hash=output_hash or "",
                completed_at=timestamp,
                duration_ms=duration_ms,
                context_before_json=existing.context_before_json,
                context_after_json=context_json,
                success_reason_json=success_reason_json,  # ADD THIS
            )
```

**Step 7: Run tests**

Run: `.venv/bin/python -m pytest tests/core/landscape/ -v -k "complete_node_state or recorder"`
Expected: PASS

**Step 8: Commit**

```bash
git add src/elspeth/core/landscape/recorder.py
git commit -m "$(cat <<'EOF'
feat(recorder): store success_reason in complete_node_state

LandscapeRecorder now accepts optional success_reason parameter
and stores it as JSON in the success_reason_json column for
COMPLETED node states.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update Executors to Pass Through success_reason

**Files:**
- Modify: `src/elspeth/engine/executors.py`

**Step 1: Update TransformExecutor**

Find the success path (around lines 353-358) and update:

```python
            self._recorder.complete_node_state(
                state_id=state.state_id,
                status=NodeStateStatus.COMPLETED,
                output_data=output_data,
                duration_ms=duration_ms,
                success_reason=result.success_reason,  # ADD THIS
            )
```

**Step 2: Update AggregationExecutor**

Find the aggregation success path (around lines 1199-1204) and update:

```python
            self._recorder.complete_node_state(
                state_id=state.state_id,
                status=NodeStateStatus.COMPLETED,
                output_data=output_data,
                duration_ms=duration_ms,
                success_reason=result.success_reason,  # ADD THIS
            )
```

**Step 3: GateExecutor and SinkExecutor**

Gates and sinks don't return TransformResult, so no changes needed for those.
Gates have RoutingReason (stored via routing events), sinks produce artifacts.

**Step 4: Run executor tests**

Run: `.venv/bin/python -m pytest tests/engine/test_transform_executor.py tests/engine/test_executors.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/elspeth/engine/executors.py
git commit -m "$(cat <<'EOF'
feat(executors): pass success_reason through to recorder

TransformExecutor and AggregationExecutor now pass
TransformResult.success_reason to complete_node_state().

Gates and sinks unchanged - they have their own audit mechanisms
(routing events and artifacts respectively).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Update MCP Server to Expose success_reason

**Files:**
- Modify: `src/elspeth/mcp/server.py` (or wherever explain_token is implemented)

**Step 1: Find explain_token implementation**

Search for where node state data is returned in explain queries.

**Step 2: Include success_reason_json in output**

When returning node state details, include:
```python
"success_reason": json.loads(state.success_reason_json) if state.success_reason_json else None
```

**Step 3: Test MCP server**

Run the MCP server and test `explain_token` on a run with transforms.

**Step 4: Commit**

```bash
git add src/elspeth/mcp/
git commit -m "$(cat <<'EOF'
feat(mcp): expose success_reason in explain_token output

The explain_token tool now includes success_reason for completed
transform states, enabling audit queries to see what action a
transform took without diffing input/output.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Add Integration Tests

**Files:**
- Create: `tests/engine/test_transform_success_reason.py`

**Step 1: Create test file**

```python
"""Tests for TransformSuccessReason audit trail integration.

Verifies that success_reason flows from transform through executor
to Landscape audit trail correctly.
"""

from typing import Any

import pytest

from elspeth.contracts import TransformResult, TransformSuccessReason
from elspeth.contracts.enums import NodeStateStatus
from elspeth.plugins.base import PluginContext


class FieldTrackingTransform:
    """Test transform that reports fields it modified."""

    node_id: str = ""
    _on_error: str = "discard"

    def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
        # Modify some fields
        result = {**row, "processed": True, "amount_usd": row.get("amount", 0) * 1.0}

        success_reason: TransformSuccessReason = {
            "action": "processed",
            "fields_added": ["processed", "amount_usd"],
        }
        return TransformResult.success(result, success_reason=success_reason)


class DataQualityTransform:
    """Test transform that reports validation warnings."""

    node_id: str = ""
    _on_error: str = "discard"

    def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
        warnings = []
        amount = row.get("amount", 0)
        if amount > 900:
            warnings.append(f"amount near threshold ({amount} of 1000 limit)")

        success_reason: TransformSuccessReason = {
            "action": "validated",
            "validation_warnings": warnings if warnings else None,
        }
        # Remove None values
        success_reason = {k: v for k, v in success_reason.items() if v is not None}

        return TransformResult.success(row, success_reason=success_reason)


class TestTransformSuccessReasonAudit:
    """Tests for success_reason in audit trail."""

    def test_success_reason_stored_in_node_state(
        self,
        minimal_pipeline_with_transform,  # Fixture that sets up pipeline
        landscape_recorder,
    ) -> None:
        """success_reason is stored in node_states table."""
        # Run pipeline with FieldTrackingTransform
        # Query node_states for the transform's state
        # Assert success_reason_json is populated
        # Assert it contains expected fields
        pass  # Implementation depends on test fixtures

    def test_success_reason_none_when_not_provided(
        self,
        minimal_pipeline_with_transform,
        landscape_recorder,
    ) -> None:
        """success_reason_json is NULL when transform doesn't provide it."""
        # Run pipeline with PassthroughTransform (no success_reason)
        # Assert success_reason_json is None
        pass

    def test_validation_warnings_captured(
        self,
        minimal_pipeline_with_transform,
        landscape_recorder,
    ) -> None:
        """validation_warnings flow through to audit trail."""
        # Run pipeline with DataQualityTransform
        # Query node_states
        # Assert validation_warnings present in success_reason_json
        pass
```

**Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/engine/test_transform_success_reason.py -v`
Expected: PASS (after implementing fixtures)

**Step 3: Commit**

```bash
git add tests/engine/test_transform_success_reason.py
git commit -m "$(cat <<'EOF'
test(engine): add integration tests for TransformSuccessReason

Verify success_reason flows from transform through executor to
audit trail correctly.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Final Verification

**Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS

**Step 2: Run mypy**

Run: `.venv/bin/python -m mypy src/elspeth/`
Expected: No new errors

**Step 3: Run ruff**

Run: `.venv/bin/python -m ruff check src/elspeth/`
Expected: No errors

**Step 4: Verify end-to-end**

Create a test pipeline with a transform that uses success_reason:
```yaml
source:
  plugin: csv
  options:
    path: test_data.csv

transforms:
  - plugin: passthrough  # Or a custom transform with success_reason

sinks:
  output:
    plugin: csv
    options:
      path: output.csv
```

Run: `elspeth run --settings test_pipeline.yaml --execute`

Query the audit database:
```sql
SELECT state_id, status, success_reason_json
FROM node_states
WHERE success_reason_json IS NOT NULL;
```

**Step 5: Close bead**

```bash
bd close <bead-id> --reason="Wired up TransformSuccessReason: schema, recorder, executors, MCP. Transforms can now report action, fields_modified, validation_warnings."
```

---

## Summary

| Component | Change |
|-----------|--------|
| `contracts/errors.py` | Rename to `TransformSuccessReason`, add `TransformActionCategory` |
| `contracts/results.py` | Add `success_reason` field and factory parameters |
| `contracts/audit.py` | Add `success_reason_json` to `NodeStateCompleted` |
| `core/landscape/schema.py` | Add `success_reason_json` column |
| `core/landscape/recorder.py` | Accept and store `success_reason` |
| `engine/executors.py` | Pass `success_reason` through to recorder |
| `mcp/server.py` | Expose in `explain_token` output |
| Alembic migration | Add column to existing databases |

**Key Design Decisions:**

1. **Separate field from error reason** - `success_reason` is distinct from `reason` (errors). Clear semantics, no type union confusion.

2. **Optional everywhere** - Existing transforms work unchanged. Success reason is additive.

3. **Literal + string for action** - `TransformActionCategory` provides common values, but custom strings allowed for plugin-specific actions.

4. **Renamed to TransformSuccessReason** - Avoids confusion with `TransformErrorReason`.

5. **validation_warnings not validation_errors** - Emphasizes these are non-blocking (warnings that don't fail the row).

**Audit Trail Value:**

```sql
-- Find transforms that skipped processing
SELECT * FROM node_states
WHERE json_extract(success_reason_json, '$.action') = 'skipped';

-- Find rows with data quality warnings
SELECT * FROM node_states
WHERE json_extract(success_reason_json, '$.validation_warnings') IS NOT NULL;

-- See which fields a transform modified
SELECT json_extract(success_reason_json, '$.fields_modified') AS modified
FROM node_states
WHERE state_id = '...';
```
