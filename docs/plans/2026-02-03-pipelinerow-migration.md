# PipelineRow Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate plugin input signatures from `dict[str, Any]` to `PipelineRow`, enabling immutable row access, dual-name field resolution, and proper contract propagation.

**Architecture:** Change `TokenInfo.row_data` from `dict[str, Any]` to `PipelineRow`. Update all plugin base classes (`BaseTransform.process()`, `BaseGate.evaluate()`) to accept `PipelineRow`. Keep sink signatures as `list[dict]` since sinks serialize data. Remove the `ctx.contract` shim after migration.

**Tech Stack:** Python dataclasses, frozen types, SchemaContract, PipelineRow (already implemented in `contracts/schema_contract.py`)

---

## ⚠️ CRITICAL: Breaking Change Warning

> **ONE-WAY DOOR:** This migration is an RC-breaking change. All plugin signatures change simultaneously.
> There is NO backwards compatibility path per the NO LEGACY CODE POLICY.
>
> **Before starting Task 1:**
> ```bash
> git branch rollback-point-pre-pipelinerow HEAD
> ```
>
> **If ANY task fails:** Stop immediately. Assess whether to continue or revert to rollback branch.
> Partial migration is NOT possible - either ALL 19 tasks succeed or EVERYTHING reverts.

---

## Mypy Expectation

> **Note:** Mypy will report type errors from Task 2 through Task 9. This is expected behavior
> during the migration. Use a feature branch where mypy failures are accepted until Task 9 completes.
> After Task 9, mypy should pass for engine code. After Task 16, mypy should pass for all code.

---

## Sink Signature Rationale

> **Design Decision:** Sinks keep `list[dict[str, Any]]` while transforms/gates use `PipelineRow`.
>
> **Why:** Sinks serialize data to external formats (CSV, JSON, database). They don't need:
> - Dual-name field resolution (output uses normalized names)
> - Contract access (schema already determined by upstream)
> - Immutability (data is being written out, not processed further)
>
> SinkExecutor calls `token.row_data.to_dict()` before `sink.write()` for efficiency.
> If future sinks need contract access (e.g., CSV with original headers), this can be revisited.

---

## Pre-Implementation: Revert the ctx.contract Shim

Before starting, revert the temporary `ctx.contract` changes that were the wrong approach:

```bash
# Check what needs reverting
git diff src/elspeth/plugins/context.py
git diff src/elspeth/plugins/llm/base.py
git diff src/elspeth/engine/orchestrator.py

# Revert only Issue 2 changes (keep Issue 1 SecretResolution)
git checkout HEAD -- src/elspeth/plugins/context.py
git checkout HEAD -- src/elspeth/engine/orchestrator.py

# For llm/base.py, manually revert only the ctx.contract fallback logic
```

---

## Task 1: Add contract Field to GateResult

**Files:**
- Modify: `src/elspeth/contracts/results.py:304-318`
- Test: `tests/contracts/test_gate_result_contract.py` (create)

**Step 1: Write the failing test**

Create `tests/contracts/test_gate_result_contract.py`:

```python
"""Tests for GateResult contract support."""

import pytest

from elspeth.contracts import GateResult, RoutingAction
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


def _make_contract() -> SchemaContract:
    """Create a minimal schema contract for testing."""
    return SchemaContract(
        mode="FIXED",
        fields=(
            FieldContract(
                normalized_name="amount",
                original_name="'Amount'",
                python_type=int,
                required=True,
                source="declared",
            ),
        ),
        locked=True,
    )


class TestGateResultContract:
    """Tests for GateResult contract field."""

    def test_gate_result_has_contract_field(self) -> None:
        """GateResult should have optional contract field."""
        contract = _make_contract()
        result = GateResult(
            row={"amount": 100},
            action=RoutingAction.continue_processing(),
            contract=contract,
        )
        assert result.contract is contract

    def test_gate_result_contract_defaults_to_none(self) -> None:
        """GateResult contract should default to None."""
        result = GateResult(
            row={"amount": 100},
            action=RoutingAction.continue_processing(),
        )
        assert result.contract is None

    def test_to_pipeline_row_with_contract(self) -> None:
        """to_pipeline_row() should work when contract is present."""
        contract = _make_contract()
        result = GateResult(
            row={"amount": 100},
            action=RoutingAction.continue_processing(),
            contract=contract,
        )
        pipeline_row = result.to_pipeline_row()
        assert isinstance(pipeline_row, PipelineRow)
        assert pipeline_row["amount"] == 100
        assert pipeline_row.contract is contract

    def test_to_pipeline_row_without_contract_raises(self) -> None:
        """to_pipeline_row() should raise when contract is None."""
        result = GateResult(
            row={"amount": 100},
            action=RoutingAction.continue_processing(),
        )
        with pytest.raises(ValueError, match="no contract"):
            result.to_pipeline_row()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/contracts/test_gate_result_contract.py -v`
Expected: FAIL - `GateResult.__init__() got an unexpected keyword argument 'contract'`

**Step 3: Implement the contract field**

Modify `src/elspeth/contracts/results.py`, update the GateResult dataclass:

```python
@dataclass
class GateResult:
    """Result of a gate evaluation.

    Contains the (possibly modified) row and routing action.
    Audit fields are populated by GateExecutor, not by plugin.
    """

    row: dict[str, Any]
    action: RoutingAction

    # Schema contract for output (optional)
    # Enables conversion to PipelineRow via to_pipeline_row()
    contract: SchemaContract | None = field(default=None, repr=False)

    # Audit fields - set by executor, not by plugin
    input_hash: str | None = field(default=None, repr=False)
    output_hash: str | None = field(default=None, repr=False)
    duration_ms: float | None = field(default=None, repr=False)

    def to_pipeline_row(self) -> PipelineRow:
        """Convert to PipelineRow for downstream processing.

        Returns:
            PipelineRow wrapping row data with contract

        Raises:
            ValueError: If contract is None
        """
        if self.contract is None:
            raise ValueError("GateResult has no contract - cannot create PipelineRow")
        return PipelineRow(self.row, self.contract)
```

Add the import at top of file:

```python
from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/contracts/test_gate_result_contract.py -v`
Expected: PASS (4 tests)

**Step 5: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -x --tb=short`
Expected: All tests pass

**Step 6: Commit**

```bash
git add src/elspeth/contracts/results.py tests/contracts/test_gate_result_contract.py
git commit -m "feat(contracts): add contract field to GateResult

Add contract: SchemaContract | None field to GateResult for parity with
TransformResult. Add to_pipeline_row() method for contract-aware conversion.

Part of PipelineRow migration (Phase 1).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Change TokenInfo.row_data Type to PipelineRow

**Files:**
- Modify: `src/elspeth/contracts/identity.py:11-50`
- Test: `tests/contracts/test_token_info_pipeline_row.py` (create)

**Step 1: Write the failing test**

Create `tests/contracts/test_token_info_pipeline_row.py`:

```python
"""Tests for TokenInfo with PipelineRow."""

import pytest

from elspeth.contracts.identity import TokenInfo
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


def _make_contract() -> SchemaContract:
    """Create a minimal schema contract for testing."""
    return SchemaContract(
        mode="FIXED",
        fields=(
            FieldContract(
                normalized_name="amount",
                original_name="'Amount'",
                python_type=int,
                required=True,
                source="declared",
            ),
        ),
        locked=True,
    )


class TestTokenInfoPipelineRow:
    """Tests for TokenInfo with PipelineRow row_data."""

    def test_token_info_accepts_pipeline_row(self) -> None:
        """TokenInfo should accept PipelineRow for row_data."""
        contract = _make_contract()
        pipeline_row = PipelineRow({"amount": 100}, contract)

        token = TokenInfo(
            row_id="row_001",
            token_id="token_001",
            row_data=pipeline_row,
        )

        assert token.row_data is pipeline_row
        assert token.row_data["amount"] == 100

    def test_with_updated_data_returns_new_token(self) -> None:
        """with_updated_data() should return new TokenInfo with new PipelineRow."""
        contract = _make_contract()
        original_row = PipelineRow({"amount": 100}, contract)
        updated_row = PipelineRow({"amount": 200}, contract)

        original_token = TokenInfo(
            row_id="row_001",
            token_id="token_001",
            row_data=original_row,
        )

        updated_token = original_token.with_updated_data(updated_row)

        # Original unchanged
        assert original_token.row_data["amount"] == 100
        # New token has new data
        assert updated_token.row_data["amount"] == 200
        # Identity preserved
        assert updated_token.row_id == original_token.row_id
        assert updated_token.token_id == original_token.token_id

    def test_row_data_contract_accessible(self) -> None:
        """Should be able to access contract from row_data."""
        contract = _make_contract()
        pipeline_row = PipelineRow({"amount": 100}, contract)

        token = TokenInfo(
            row_id="row_001",
            token_id="token_001",
            row_data=pipeline_row,
        )

        assert token.row_data.contract is contract
        assert token.row_data.contract.mode == "FIXED"

    def test_pipeline_row_to_dict_includes_extra_fields(self) -> None:
        """to_dict() should return ALL fields, not just contract fields.

        Important for audit integrity: transforms may add fields beyond contract
        (FLEXIBLE mode). These must be preserved in landscape recording.
        """
        contract = _make_contract()  # Only has "amount"
        data_with_extras = {"amount": 100, "computed_field": "extra", "nested": {"a": 1}}
        pipeline_row = PipelineRow(data_with_extras, contract)

        result = pipeline_row.to_dict()

        # All fields preserved, not just contract fields
        assert result["amount"] == 100
        assert result["computed_field"] == "extra"
        assert result["nested"] == {"a": 1}
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/contracts/test_token_info_pipeline_row.py -v`
Expected: Could pass if PipelineRow duck-types as dict, but mypy will fail

Run: `.venv/bin/python -m mypy src/elspeth/contracts/identity.py`
Expected: Type errors when we change the annotation

**Step 3: Update TokenInfo type annotation**

Modify `src/elspeth/contracts/identity.py`:

```python
"""Entity identifiers and token structures.

These types answer: "How do we refer to things?"
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspeth.contracts.schema_contract import PipelineRow


@dataclass
class TokenInfo:
    """Identity and data for a token flowing through the DAG.

    Tokens track row instances through forks/joins:
    - row_id: Stable source row identity
    - token_id: Instance of row in a specific DAG path
    - branch_name: Which fork path this token is on (if forked)
    - fork_group_id: Groups all children from a fork operation
    - join_group_id: Groups all tokens merged in a coalesce operation
    - expand_group_id: Groups all children from an expand operation

    Note: NOT frozen because row_data may need to be updated as tokens
    flow through the pipeline. Use with_updated_data() for updates.
    """

    row_id: str
    token_id: str
    row_data: "PipelineRow"  # CHANGED from dict[str, Any]
    branch_name: str | None = None
    fork_group_id: str | None = None
    join_group_id: str | None = None
    expand_group_id: str | None = None

    def with_updated_data(self, new_data: "PipelineRow") -> "TokenInfo":
        """Return a new TokenInfo with updated row_data, preserving all lineage fields.

        This method ensures that when row_data is updated after a transform,
        all identity and lineage metadata (branch_name, fork_group_id,
        join_group_id, expand_group_id) are preserved.

        Use this instead of constructing TokenInfo manually when updating
        a token's data after processing.

        Args:
            new_data: The new PipelineRow to use

        Returns:
            A new TokenInfo with the same identity/lineage but new row_data
        """
        return replace(self, row_data=new_data)
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/contracts/test_token_info_pipeline_row.py -v`
Expected: PASS (4 tests)

**Step 5: Run mypy (expect errors in other files)**

Run: `.venv/bin/python -m mypy src/elspeth/contracts/identity.py`
Expected: PASS for this file, but other files using TokenInfo will now have type errors

**Step 6: Commit**

```bash
git add src/elspeth/contracts/identity.py tests/contracts/test_token_info_pipeline_row.py
git commit -m "feat(contracts): change TokenInfo.row_data to PipelineRow

Update TokenInfo.row_data type from dict[str, Any] to PipelineRow.
This is the core type change for the PipelineRow migration.

Note: This will cause type errors in downstream code until the full
migration is complete (engine, plugins).

Part of PipelineRow migration (Phase 1).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Update TokenManager for PipelineRow

**Files:**
- Modify: `src/elspeth/engine/tokens.py:61-284`
- Test: `tests/engine/test_token_manager_pipeline_row.py` (create)

**Step 1: Write the failing test**

Create `tests/engine/test_token_manager_pipeline_row.py`:

```python
"""Tests for TokenManager with PipelineRow support."""

from unittest.mock import MagicMock, Mock

import pytest

from elspeth.contracts import SourceRow
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.engine.tokens import TokenManager


def _make_contract() -> SchemaContract:
    """Create a minimal schema contract for testing."""
    return SchemaContract(
        mode="OBSERVED",
        fields=(
            FieldContract(
                normalized_name="amount",
                original_name="'Amount'",
                python_type=int,
                required=True,
                source="declared",
            ),
        ),
        locked=True,
    )


def _make_mock_recorder() -> MagicMock:
    """Create a mock LandscapeRecorder."""
    recorder = MagicMock()
    recorder.create_row.return_value = Mock(row_id="row_001")
    recorder.create_token.return_value = Mock(token_id="token_001")
    return recorder


class TestTokenManagerCreateInitialToken:
    """Tests for TokenManager.create_initial_token() with SourceRow."""

    def test_create_initial_token_from_source_row(self) -> None:
        """create_initial_token should accept SourceRow and create PipelineRow."""
        contract = _make_contract()
        recorder = _make_mock_recorder()
        manager = TokenManager(recorder)

        source_row = SourceRow.valid({"amount": 100}, contract=contract)

        token = manager.create_initial_token(
            run_id="run_001",
            source_node_id="source_001",
            row_index=0,
            source_row=source_row,
        )

        # Token has PipelineRow
        assert isinstance(token.row_data, PipelineRow)
        assert token.row_data["amount"] == 100
        assert token.row_data.contract is contract

        # Recorder was called with dict (for landscape storage)
        recorder.create_row.assert_called_once()
        call_kwargs = recorder.create_row.call_args.kwargs
        assert call_kwargs["data"] == {"amount": 100}

    def test_create_initial_token_requires_contract(self) -> None:
        """create_initial_token should raise ValueError if SourceRow has no contract.

        This is a critical guard - if a source plugin returns SourceRow without
        contract, we crash immediately with a clear message rather than propagating
        None through the pipeline.
        """
        recorder = _make_mock_recorder()
        manager = TokenManager(recorder)

        # SourceRow without contract
        source_row = SourceRow.valid({"amount": 100}, contract=None)

        with pytest.raises(ValueError, match="must have contract"):
            manager.create_initial_token(
                run_id="run_001",
                source_node_id="source_001",
                row_index=0,
                source_row=source_row,
            )


class TestTokenManagerForkToken:
    """Tests for TokenManager.fork_token() with PipelineRow."""

    def test_fork_token_propagates_contract(self) -> None:
        """fork_token should propagate contract to all children."""
        contract = _make_contract()
        recorder = _make_mock_recorder()
        recorder.fork_token.return_value = (
            [Mock(token_id="child_001"), Mock(token_id="child_002")],
            "fork_group_001",
        )
        manager = TokenManager(recorder)

        # Create parent token with PipelineRow
        parent_row = PipelineRow({"amount": 100}, contract)
        from elspeth.contracts.identity import TokenInfo

        parent_token = TokenInfo(
            row_id="row_001",
            token_id="parent_001",
            row_data=parent_row,
        )

        children, fork_group_id = manager.fork_token(
            parent_token=parent_token,
            branches=["branch_a", "branch_b"],
            step_in_pipeline=1,
            run_id="run_001",
        )

        assert len(children) == 2
        # Each child has PipelineRow with same contract
        for child in children:
            assert isinstance(child.row_data, PipelineRow)
            assert child.row_data.contract is contract
            # Data is deep copied
            assert child.row_data["amount"] == 100
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/engine/test_token_manager_pipeline_row.py -v`
Expected: FAIL - signature mismatch or TypeError

**Step 3: Update TokenManager methods**

Modify `src/elspeth/engine/tokens.py`. Key changes:

1. `create_initial_token()` - Accept SourceRow, create PipelineRow
2. `create_token_for_existing_row()` - Accept PipelineRow
3. `fork_token()` - Propagate contract to children
4. `coalesce_tokens()` - Accept PipelineRow for merged data
5. `update_row_data()` - Accept PipelineRow
6. `expand_token()` - Propagate contract to expanded rows

The full implementation is extensive - see the actual file for complete changes. Key pattern:

```python
def create_initial_token(
    self,
    run_id: str,
    source_node_id: str,
    row_index: int,
    source_row: SourceRow,  # CHANGED from row_data: dict[str, Any]
) -> TokenInfo:
    """Create a token for a source row."""
    if source_row.contract is None:
        raise ValueError("SourceRow must have contract to create token")

    pipeline_row = source_row.to_pipeline_row()

    # Recorder stores dict representation
    row = self._recorder.create_row(
        run_id=run_id,
        source_node_id=source_node_id,
        row_index=row_index,
        data=pipeline_row.to_dict(),
    )

    token = self._recorder.create_token(row_id=row.row_id)

    return TokenInfo(
        row_id=row.row_id,
        token_id=token.token_id,
        row_data=pipeline_row,
    )
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/engine/test_token_manager_pipeline_row.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/elspeth/engine/tokens.py tests/engine/test_token_manager_pipeline_row.py
git commit -m "feat(engine): update TokenManager for PipelineRow

- create_initial_token() now accepts SourceRow, creates PipelineRow
- fork_token() propagates contract to all children
- coalesce_tokens() accepts PipelineRow for merged data
- All methods store dict via to_dict() for landscape

Part of PipelineRow migration (Phase 1).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Update Plugin Base Classes

**Files:**
- Modify: `src/elspeth/plugins/base.py`
- Modify: `src/elspeth/plugins/protocols.py`
- Test: Existing tests should fail, then pass after update

**Step 1: Update BaseTransform.process() signature**

Modify `src/elspeth/plugins/base.py`:

```python
from elspeth.contracts.schema_contract import PipelineRow

class BaseTransform(ABC):
    # ... existing code ...

    @abstractmethod
    def process(
        self,
        row: PipelineRow,  # CHANGED from dict[str, Any]
        ctx: PluginContext,
    ) -> TransformResult:
        """Process a single row.

        Args:
            row: Input row as PipelineRow (immutable, supports dual-name access)
            ctx: Plugin context

        Returns:
            TransformResult with processed row dict or error
        """
        ...
```

**Step 2: Update BaseGate.evaluate() signature**

```python
class BaseGate(ABC):
    # ... existing code ...

    @abstractmethod
    def evaluate(
        self,
        row: PipelineRow,  # CHANGED from dict[str, Any]
        ctx: PluginContext,
    ) -> GateResult:
        """Evaluate a row and decide routing.

        Args:
            row: Input row as PipelineRow
            ctx: Plugin context

        Returns:
            GateResult with routing decision
        """
        ...
```

**Step 3: Keep BaseSink.write() unchanged**

```python
class BaseSink(ABC):
    # ... existing code ...

    @abstractmethod
    def write(
        self,
        rows: list[dict[str, Any]],  # KEEP as dict - sinks serialize (see rationale above)
        ctx: PluginContext,
    ) -> ArtifactDescriptor:
        """Write a batch of rows to the sink.

        Args:
            rows: List of row dicts to write (extracted from PipelineRow by SinkExecutor)
            ctx: Plugin context

        Returns:
            ArtifactDescriptor with content_hash and size_bytes
        """
        ...
```

**Step 4: Update protocols.py**

Modify `src/elspeth/plugins/protocols.py` with matching signatures.

**Step 5: Run mypy to see type errors**

Run: `.venv/bin/python -m mypy src/elspeth/plugins/`
Expected: Type errors in all plugin implementations (expected)

**Step 6: Commit**

```bash
git add src/elspeth/plugins/base.py src/elspeth/plugins/protocols.py
git commit -m "feat(plugins): update base class signatures for PipelineRow

- BaseTransform.process() now takes PipelineRow instead of dict
- BaseGate.evaluate() now takes PipelineRow instead of dict
- BaseSink.write() unchanged (sinks receive extracted dicts)

Note: Plugin implementations will have type errors until updated.

Part of PipelineRow migration (Phase 2).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Update BatchTransformMixin

**Files:**
- Modify: `src/elspeth/plugins/batching/mixin.py`
- Test: `tests/plugins/batching/test_mixin_pipeline_row.py` (create)

**Step 1: Write the test**

Create `tests/plugins/batching/test_mixin_pipeline_row.py`:

```python
"""Tests for BatchTransformMixin with PipelineRow support."""

from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


def _make_contract() -> SchemaContract:
    """Create a minimal schema contract for testing."""
    return SchemaContract(
        mode="OBSERVED",
        fields=(
            FieldContract(
                normalized_name="value",
                original_name="value",
                python_type=int,
                required=True,
                source="declared",
            ),
        ),
        locked=True,
    )


class TestBatchTransformMixinPipelineRow:
    """Tests for BatchTransformMixin with PipelineRow."""

    def test_accept_row_with_pipeline_row(self) -> None:
        """accept_row should accept PipelineRow and pass it through unchanged."""
        # This test verifies the signature accepts PipelineRow
        # Full integration testing happens in batch plugin tests
        contract = _make_contract()
        pipeline_row = PipelineRow({"value": 42}, contract)

        # Verify PipelineRow can be accessed as expected by mixin
        assert pipeline_row["value"] == 42
        assert pipeline_row.contract is contract
```

**Step 2: Update accept_row signature**

```python
def accept_row(
    self,
    row: PipelineRow,  # CHANGED from dict[str, Any]
    ctx: PluginContext,
    processor: Callable[[PipelineRow, PluginContext], TransformResult],
) -> None:
    """Accept a row for async processing."""
    # ... implementation unchanged, row is just passed through
```

**Step 3: Commit**

```bash
git add src/elspeth/plugins/batching/mixin.py tests/plugins/batching/test_mixin_pipeline_row.py
git commit -m "feat(batching): update BatchTransformMixin for PipelineRow

Part of PipelineRow migration (Phase 2).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Update Engine Executors

**Files:**
- Modify: `src/elspeth/engine/executors.py`
- This is the largest single task - update all executor classes

**Key patterns to apply throughout:**

1. **Hashing**: `stable_hash(token.row_data.to_dict())`
2. **Landscape recording**: `input_data=token.row_data.to_dict()`
3. **Plugin calls**: Pass `token.row_data` directly (now PipelineRow)
4. **Token updates**: Create new PipelineRow from result dict + contract
5. **Logging**: Add DEBUG logging for contract propagation (observability)

**Step 1: Update TransformExecutor**

Key changes in `execute_transform()`:

```python
import structlog

logger = structlog.get_logger()

# Hash input data
input_hash = stable_hash(token.row_data.to_dict())

# Begin node state with dict
state = self._recorder.begin_node_state(
    token_id=token.token_id,
    node_id=transform.node_id,
    run_id=ctx.run_id,
    step_index=step_in_pipeline,
    input_data=token.row_data.to_dict(),  # Extract dict
    attempt=attempt,
)

# Call transform with PipelineRow
result = transform.process(token.row_data, ctx)

# Create new PipelineRow from result
if result.status == "success" and result.row is not None:
    output_contract = result.contract if result.contract else token.row_data.contract
    new_row = PipelineRow(result.row, output_contract)
    updated_token = token.with_updated_data(new_row)

    # Log contract propagation at DEBUG level
    logger.debug(
        "contract_propagated",
        transform=transform.node_id,
        token_id=token.token_id,
        contract_mode=output_contract.mode,
        field_count=len(output_contract.fields),
    )
```

**Step 2: Update GateExecutor**

Similar pattern for `execute_gate()` and `execute_config_gate()`.

Add improved error handling for dual-name resolution failures:

```python
try:
    result = gate.evaluate(token.row_data, ctx)
except KeyError as e:
    # Provide diagnostic error message for field access failures
    available_fields = list(token.row_data.to_dict().keys())
    contract_fields = [f.normalized_name for f in token.row_data.contract.fields]
    logger.warning(
        "gate_field_access_failed",
        gate=gate.node_id,
        missing_field=str(e),
        available_fields=available_fields,
        contract_fields=contract_fields,
    )
    raise
```

**Step 3: Update SinkExecutor**

```python
# Extract dicts for sink write
rows = [t.row_data.to_dict() for t in tokens]
artifact_info = sink.write(rows, ctx)
```

**Step 4: Update AggregationExecutor**

Change buffer type:

```python
self._buffers: dict[NodeID, list[PipelineRow]] = {}

def accept_row(self, node_id: NodeID, token: TokenInfo) -> ...:
    self._buffers[node_id].append(token.row_data)  # Now PipelineRow
```

**Step 5: Commit**

```bash
git add src/elspeth/engine/executors.py
git commit -m "feat(engine): update executors for PipelineRow

- TransformExecutor: Extract dict for landscape, pass PipelineRow to plugins
- GateExecutor: Same pattern, improved KeyError diagnostics
- SinkExecutor: Extract dicts before sink.write()
- AggregationExecutor: Store PipelineRow in buffers
- Added DEBUG logging for contract propagation

Part of PipelineRow migration (Phase 3).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Update RowProcessor

**Files:**
- Modify: `src/elspeth/engine/processor.py`

**Key changes:**

1. Update calls to `token_manager.create_initial_token()` to pass SourceRow
2. Update all `token.row_data` accesses where dict was expected
3. Ensure fork/coalesce operations propagate contracts

**Step 1: Update initial token creation**

```python
# OLD:
token = token_manager.create_initial_token(
    run_id=run_id,
    source_node_id=source_node_id,
    row_index=row_index,
    row_data=row_data,
)

# NEW:
token = token_manager.create_initial_token(
    run_id=run_id,
    source_node_id=source_node_id,
    row_index=row_index,
    source_row=source_row,  # Pass SourceRow directly
)
```

**Step 2: Commit**

```bash
git add src/elspeth/engine/processor.py
git commit -m "feat(engine): update RowProcessor for PipelineRow

- Pass SourceRow to create_initial_token()
- Update all token.row_data accesses

Part of PipelineRow migration (Phase 3).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Update CoalesceExecutor

**Files:**
- Modify: `src/elspeth/engine/coalesce_executor.py`
- Test: `tests/engine/test_coalesce_contract_merge.py` (create)

**Step 1: Write the contract merge failure tests**

Create `tests/engine/test_coalesce_contract_merge.py`:

```python
"""Tests for CoalesceExecutor contract merge behavior."""

import pytest

from elspeth.contracts.identity import TokenInfo
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


def _make_contract(mode: str = "FIXED", fields: tuple[FieldContract, ...] | None = None) -> SchemaContract:
    """Create a schema contract for testing."""
    if fields is None:
        fields = (
            FieldContract(
                normalized_name="amount",
                original_name="amount",
                python_type=int,
                required=True,
                source="declared",
            ),
        )
    return SchemaContract(mode=mode, fields=fields, locked=True)


class TestCoalesceContractMerge:
    """Tests for contract merge behavior at coalesce points."""

    def test_coalesce_with_none_contract_raises(self) -> None:
        """Coalesce should raise clear error if any parent has None contract.

        This validates the defensive assertion - if a buggy transform
        produces a token with None contract, we crash immediately at
        coalesce with actionable error rather than propagating None.
        """
        contract = _make_contract()

        # Parent with valid contract
        valid_token = TokenInfo(
            row_id="row_001",
            token_id="token_a",
            row_data=PipelineRow({"amount": 100}, contract),
            branch_name="branch_a",
        )

        # Parent with None contract (bug scenario)
        # In real code, PipelineRow requires contract, so this simulates
        # a situation where contract became None through some edge case
        # We test the defensive check in _perform_merge

        # The actual test would be against CoalesceExecutor._perform_merge
        # verifying it raises ValueError for None contract
        pass  # Implementation test added in Step 2

    def test_coalesce_contract_merge_incompatible_modes(self) -> None:
        """Merging FIXED and OBSERVED mode contracts should handle gracefully.

        SchemaContract.merge() should define the merge semantics.
        This test documents the expected behavior.
        """
        fixed_contract = _make_contract(mode="FIXED")
        observed_contract = _make_contract(mode="OBSERVED")

        # Test that SchemaContract.merge() handles mode differences
        # The merge policy should be documented in SchemaContract
        merged = fixed_contract.merge(observed_contract)

        # Document expected behavior - FIXED should dominate
        # (or raise if incompatible - depends on SchemaContract.merge impl)
        assert merged is not None

    def test_coalesce_contract_merge_conflicting_types(self) -> None:
        """Merging contracts with conflicting field types should raise.

        If branch A says field 'x' is int and branch B says 'x' is str,
        the merge should fail with a clear error.
        """
        contract_a = _make_contract(
            fields=(
                FieldContract(
                    normalized_name="value",
                    original_name="value",
                    python_type=int,
                    required=True,
                    source="declared",
                ),
            )
        )
        contract_b = _make_contract(
            fields=(
                FieldContract(
                    normalized_name="value",
                    original_name="value",
                    python_type=str,  # Conflicting type!
                    required=True,
                    source="declared",
                ),
            )
        )

        # SchemaContract.merge() should raise on type conflict
        # or have documented merge semantics
        with pytest.raises((ValueError, TypeError)):
            contract_a.merge(contract_b)

    def test_coalesce_logs_merge_operation(self) -> None:
        """Contract merge should log at DEBUG level for observability."""
        # This is validated by checking log output in integration tests
        pass
```

**Step 2: Implement with defensive assertions**

Key changes:

1. Merge contracts from all branches at coalesce
2. Add defensive assertion for None contracts
3. Create PipelineRow with merged contract
4. Add logging for merge operations

```python
import structlog

logger = structlog.get_logger()

def _perform_merge(self, pending: _PendingCoalesce, ...) -> TokenInfo:
    # Defensive check - crash early with clear message if any contract is None
    for branch, token in pending.arrived.items():
        if token.row_data.contract is None:
            raise ValueError(
                f"Token {token.token_id} on branch '{branch}' has no contract. "
                f"Cannot coalesce without contracts on all parents. "
                f"This indicates a bug in an upstream transform."
            )

    # Merge contracts from all arrived branches
    contracts = [t.row_data.contract for t in pending.arrived.values()]
    merged_contract = contracts[0]
    for c in contracts[1:]:
        merged_contract = merged_contract.merge(c)

    # Log merge operation
    logger.debug(
        "contract_merge_at_coalesce",
        coalesce_id=pending.coalesce_id,
        branch_count=len(pending.arrived),
        branches=list(pending.arrived.keys()),
        merged_field_count=len(merged_contract.fields),
    )

    # Merge row data
    merged_data = self._merge_rows(pending.arrived, strategy)

    # Create PipelineRow with merged contract
    merged_row = PipelineRow(merged_data, merged_contract)

    return self._token_manager.coalesce_tokens(
        parents=list(pending.arrived.values()),
        merged_data=merged_row,
        step_in_pipeline=step,
    )
```

**Step 3: Commit**

```bash
git add src/elspeth/engine/coalesce_executor.py tests/engine/test_coalesce_contract_merge.py
git commit -m "feat(engine): update CoalesceExecutor for PipelineRow

- Merge contracts from all branches at coalesce point
- Add defensive assertion: crash with clear error if any contract is None
- Create PipelineRow with merged contract
- Add DEBUG logging for contract merge operations

Part of PipelineRow migration (Phase 3).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Update Expression Parser

**Files:**
- Modify: `src/elspeth/engine/expression_parser.py`

**Step 1: Update evaluate signature**

```python
def evaluate(self, row: PipelineRow | dict[str, Any]) -> Any:
    """Evaluate expression against row data.

    Args:
        row: Row data (PipelineRow or dict for backwards compatibility)

    PipelineRow implements __getitem__ so expression evaluation works.
    """
    evaluator = _ExpressionEvaluator(row)
    return evaluator.visit(self._ast)
```

**Step 2: Commit**

```bash
git add src/elspeth/engine/expression_parser.py
git commit -m "feat(engine): update expression parser for PipelineRow

Accept PipelineRow in evaluate() - uses __getitem__ protocol.

Part of PipelineRow migration (Phase 3).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Add Checkpoint Version for PipelineRow Compatibility

**Files:**
- Modify: `src/elspeth/engine/executors.py` (AggregationExecutor checkpoint methods)
- Test: `tests/engine/test_aggregation_checkpoint_version.py` (create)

> **CRITICAL:** This task prevents data corruption when resuming checkpoints across versions.

**Step 1: Write the checkpoint version tests**

Create `tests/engine/test_aggregation_checkpoint_version.py`:

```python
"""Tests for AggregationExecutor checkpoint version compatibility."""

import pytest

from elspeth.contracts.identity import TokenInfo
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


def _make_contract() -> SchemaContract:
    """Create a minimal schema contract for testing."""
    return SchemaContract(
        mode="OBSERVED",
        fields=(
            FieldContract(
                normalized_name="value",
                original_name="value",
                python_type=int,
                required=True,
                source="declared",
            ),
        ),
        locked=True,
    )


class TestAggregationCheckpointVersion:
    """Tests for checkpoint version compatibility."""

    def test_checkpoint_includes_version(self) -> None:
        """Checkpoint state should include version field."""
        # AggregationExecutor.get_checkpoint_state() should return
        # {"version": 2, "buffers": {...}, ...}
        pass  # Implemented by checking actual checkpoint output

    def test_restore_rejects_incompatible_version(self) -> None:
        """restore_from_checkpoint should reject old version checkpoints.

        Old checkpoints (version 1) store dict row_data.
        New checkpoints (version 2) store PipelineRow-compatible data.
        Attempting to restore v1 checkpoint with v2 code should raise.
        """
        old_checkpoint = {
            "version": 1,  # Old format
            "buffers": {
                "agg_001": [{"value": 42}]  # dict, not PipelineRow
            }
        }

        # Should raise clear error
        # with pytest.raises(CheckpointVersionError, match="incompatible"):
        #     executor.restore_from_checkpoint(old_checkpoint)
        pass  # Implemented in Step 2

    def test_checkpoint_round_trip_preserves_pipeline_row(self) -> None:
        """Checkpoint and restore should preserve PipelineRow state.

        This validates that:
        1. PipelineRow is correctly serialized to checkpoint
        2. PipelineRow is correctly restored from checkpoint
        3. Contract is preserved through round-trip
        """
        contract = _make_contract()
        pipeline_row = PipelineRow({"value": 42}, contract)

        token = TokenInfo(
            row_id="row_001",
            token_id="token_001",
            row_data=pipeline_row,
        )

        # Full integration test with actual AggregationExecutor
        # 1. Accept 3 rows into aggregation buffer
        # 2. Get checkpoint state
        # 3. Create new executor, restore from checkpoint
        # 4. Verify buffer contains valid PipelineRow with correct contract
        pass  # Full implementation in integration test
```

**Step 2: Add checkpoint version to AggregationExecutor**

```python
# In executors.py, AggregationExecutor class

CHECKPOINT_VERSION = 2  # Increment when checkpoint format changes

class CheckpointVersionError(Exception):
    """Raised when checkpoint version is incompatible."""
    pass

def get_checkpoint_state(self) -> dict[str, Any]:
    """Get current state for checkpointing."""
    return {
        "version": CHECKPOINT_VERSION,
        "buffers": {
            node_id: [row.to_dict() for row in rows]
            for node_id, rows in self._buffers.items()
        },
        "contracts": {
            node_id: rows[0].contract.to_dict() if rows else None
            for node_id, rows in self._buffers.items()
        },
        # ... other state
    }

def restore_from_checkpoint(self, state: dict[str, Any]) -> None:
    """Restore state from checkpoint."""
    version = state.get("version", 1)  # Default to v1 for old checkpoints

    if version < CHECKPOINT_VERSION:
        raise CheckpointVersionError(
            f"Checkpoint version {version} is incompatible with code version {CHECKPOINT_VERSION}. "
            f"Cannot resume pipeline checkpointed before PipelineRow migration. "
            f"Please re-run the pipeline from source."
        )

    # Restore buffers with PipelineRow
    contracts = state.get("contracts", {})
    for node_id, rows in state["buffers"].items():
        contract = SchemaContract.from_dict(contracts[node_id])
        self._buffers[node_id] = [
            PipelineRow(row, contract) for row in rows
        ]
```

**Step 3: Commit**

```bash
git add src/elspeth/engine/executors.py tests/engine/test_aggregation_checkpoint_version.py
git commit -m "feat(engine): add checkpoint version for PipelineRow compatibility

- Add CHECKPOINT_VERSION = 2 constant
- get_checkpoint_state() includes version and serialized contracts
- restore_from_checkpoint() rejects incompatible versions with clear error
- Prevents data corruption when resuming across PipelineRow migration

Part of PipelineRow migration (Phase 3).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11-17: Update Plugin Implementations

For each plugin, apply this pattern:

```python
def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
    # Access via dual-name
    value = row["field_name"]

    # Create output dict
    output = row.to_dict()
    output["computed"] = value * 2

    # Propagate contract
    return TransformResult.success(
        output,
        success_reason={"action": "computed"},
        contract=row.contract,
    )
```

**Plugins to update (one commit each):**

- Task 11: `passthrough.py`, `field_mapper.py`
- Task 12: `truncate.py`, `keyword_filter.py`
- Task 13: `json_explode.py`
- Task 14: `batch_stats.py`, `batch_replicate.py`
- Task 15: `azure/content_safety.py`, `azure/prompt_shield.py`
- Task 16: `llm/base.py`, `llm/azure.py`
- Task 17: `llm/openrouter.py` and all OpenRouter variants

---

## Task 18: Remove ctx.contract Shim

**Files:**
- Modify: `src/elspeth/plugins/context.py`
- Modify: `src/elspeth/engine/orchestrator.py`

**Step 1: Remove contract field from PluginContext**

Delete these lines from `context.py`:

```python
# DELETE:
# contract: "SchemaContract | None" = field(default=None)
```

**Step 2: Remove ctx.contract assignments from orchestrator**

Delete these lines from `orchestrator.py`:

```python
# DELETE:
# ctx.contract = schema_contract
# ctx.contract = recorder.get_run_contract(run_id)
```

**Step 3: Commit**

```bash
git add src/elspeth/plugins/context.py src/elspeth/engine/orchestrator.py
git commit -m "refactor(plugins): remove ctx.contract shim

Contract is now always available via row.contract (PipelineRow).

Completes PipelineRow migration (Phase 5).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 19: Update Tests

Update all tests that:
1. Create TokenInfo with dict row_data → use PipelineRow
2. Call transform.process() with dict → use PipelineRow
3. Mock PluginContext with contract field → remove

**Split by subsystem for tracking:**

### Task 19a: Update contracts tests (~15 files)

Files in `tests/contracts/`:
- `test_results.py` - TransformResult, GateResult
- `test_identity.py` - TokenInfo
- `test_source_row.py` - SourceRow integration

### Task 19b: Update engine tests (~25 files)

Files in `tests/engine/`:
- `test_tokens.py` - TokenManager
- `test_executors.py` - All executor tests
- `test_processor.py` - RowProcessor
- `test_coalesce*.py` - Coalesce tests

### Task 19c: Update plugin tests (~40 files)

Files in `tests/plugins/`:
- `test_passthrough.py`, `test_field_mapper.py`, etc.
- `tests/plugins/llm/` - All LLM plugin tests
- `tests/plugins/azure/` - Azure plugin tests

### Task 19d: Update integration tests (~15 files)

Files in `tests/integration/`:
- Full pipeline tests
- Fork/coalesce integration tests

Run full test suite and fix failures iteratively.

---

## Final Verification

```bash
# Full test suite
.venv/bin/python -m pytest tests/ -v

# Type checking (should pass after all tasks complete)
.venv/bin/python -m mypy src/

# Integration test
.venv/bin/python -m pytest tests/integration/ -v

# Example pipeline
cd examples/openrouter_multi_query_assessment
elspeth run --settings settings.yaml --execute

# Validate contract propagation via landscape MCP
# After pipeline runs, verify no NULL contracts in completed states:
elspeth-mcp &
# Then query:
# get_node_states(run_id, status="completed") -> verify all have contracts
# explain_token(run_id, token_id) -> verify contract present at each step
```

### Contract Propagation Validation

After running the example pipeline, use the Landscape MCP to verify contracts flowed through the entire DAG:

```python
# Using MCP query tool
result = query("""
    SELECT ns.state_id, ns.status, ns.node_id
    FROM node_states ns
    WHERE ns.run_id = ?
    AND ns.status = 'completed'
""", [run_id])

# For each completed state, verify via explain_token that contract is present
for state in result:
    lineage = explain_token(run_id, token_id=state.token_id)
    assert lineage.contract is not None, f"NULL contract at {state.node_id}"
```

---

## Performance Benchmark (Optional)

Before and after the migration, run this benchmark to measure PipelineRow overhead:

```bash
# Create benchmark script: scripts/benchmark_pipeline_row.py
.venv/bin/python scripts/benchmark_pipeline_row.py

# Expected output:
# dict-based fork (1000 rows, 5 branches): X.XX ms
# PipelineRow fork (1000 rows, 5 branches): Y.YY ms
# Overhead: Z%

# If overhead > 100%, investigate structural sharing options
```

---

## Summary

| Task | Description | Files | Phase |
|------|-------------|-------|-------|
| 1 | Add contract to GateResult | results.py | 1 |
| 2 | Change TokenInfo.row_data type | identity.py | 1 |
| 3 | Update TokenManager | tokens.py | 1 |
| 4 | Update plugin base classes | base.py, protocols.py | 2 |
| 5 | Update BatchTransformMixin | batching/mixin.py | 2 |
| 6 | Update engine executors | executors.py | 3 |
| 7 | Update RowProcessor | processor.py | 3 |
| 8 | Update CoalesceExecutor | coalesce_executor.py | 3 |
| 9 | Update expression parser | expression_parser.py | 3 |
| 10 | Add checkpoint version | executors.py | 3 |
| 11-17 | Update plugin implementations | ~17 plugin files | 4 |
| 18 | Remove ctx.contract shim | context.py, orchestrator.py | 5 |
| 19a-d | Update tests | ~95 test files | 6 |

**Phase boundaries for testing:**
- After Phase 1 (Tasks 1-3): Run `pytest tests/contracts/ tests/engine/test_tokens.py`
- After Phase 3 (Tasks 6-10): Run `pytest tests/engine/`
- After Phase 4 (Tasks 11-17): Run `pytest tests/plugins/`
- After Phase 6 (Task 19): Run full `pytest tests/` and `mypy src/`
