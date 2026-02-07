# PipelineRow Migration Implementation Plan (Revised)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the migration of plugin input signatures from `dict[str, Any]` to `PipelineRow`, enabling immutable row access, dual-name field resolution, and proper contract propagation throughout the pipeline.

**Current State (as of 2026-02-03):**
- `PipelineRow` class: ✅ Complete with immutable design via `MappingProxyType`
- `SchemaContract`: ✅ Complete with field resolution, merging, validation, checkpoint support
- `TransformResult.contract`: ✅ Already has contract field
- `GateResult.contract`: ❌ Missing - needs adding (Task 1)
- `TokenInfo.row_data`: ❌ Still `dict[str, Any]` - **this is the critical blocker**
- Plugin base signatures: ❌ Still expect `dict[str, Any]`
- LLM plugins: ⚠️ Already accept union `dict[str, Any] | PipelineRow` (transitional)
- `ctx.contract`: ✅ Working production mechanism - **do NOT remove**
- Contract propagation utilities: ✅ Ready to use in `contracts/contract_propagation.py`

**Architecture Decision: Keep ctx.contract**

The original plan incorrectly called `ctx.contract` a "shim to be removed." It is the **production mechanism** for contract propagation when plugins receive plain dicts. After this migration:
- Transforms receiving `PipelineRow` use `row.contract` directly
- `ctx.contract` remains as backup for edge cases and compatibility
- Both access patterns are valid and should work

**Tech Stack:** Python dataclasses, frozen types, SchemaContract, PipelineRow (in `contracts/schema_contract.py`)

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
> Partial migration is NOT possible - either ALL tasks succeed or EVERYTHING reverts.

---

## Mypy Expectation

> **Note:** Mypy will report type errors from Task 2 through Task 7. This is expected behavior
> during the migration. Use a feature branch where mypy failures are accepted until Task 7 completes.
> After Task 7, mypy should pass for engine code. After Task 10, mypy should pass for all code.

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

---

## Task 1: Add contract Field to GateResult

**Files:**
- Modify: `src/elspeth/contracts/results.py:303-318`
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

Modify `src/elspeth/contracts/results.py`, update the GateResult dataclass (around line 303):

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

Add the import at top of file (if not present):

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
- Modify: `src/elspeth/contracts/identity.py:10-51`
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

**Step 2: Run test to verify current state**

Run: `.venv/bin/python -m pytest tests/contracts/test_token_info_pipeline_row.py -v`
Expected: Tests may partially pass due to duck-typing, but mypy will fail after type change

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
- Modify: `src/elspeth/engine/tokens.py`
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

Key changes to `src/elspeth/engine/tokens.py`:

1. `create_initial_token()` - Accept SourceRow, create PipelineRow
2. `fork_token()` - Propagate contract to children
3. `coalesce_tokens()` - Accept PipelineRow for merged data
4. `expand_token()` - Propagate contract to expanded rows

The critical pattern:

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
        rows: list[dict[str, Any]],  # KEEP as dict - sinks serialize
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

**Step 4: Update protocols.py with matching signatures**

**Step 5: Commit**

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

## Task 5: Update Engine Executors

**Files:**
- Modify: `src/elspeth/engine/executors.py`

**Key patterns to apply throughout:**

1. **Hashing**: `stable_hash(token.row_data.to_dict())`
2. **Landscape recording**: `input_data=token.row_data.to_dict()`
3. **Plugin calls**: Pass `token.row_data` directly (now PipelineRow)
4. **Token updates**: Create new PipelineRow from result dict + contract
5. **ctx.contract**: Set `ctx.contract = token.row_data.contract` for fallback access

**Key changes in TransformExecutor.execute_transform():**

```python
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

# Set ctx.contract for plugins that use it
ctx.contract = token.row_data.contract

# Call transform with PipelineRow
result = transform.process(token.row_data, ctx)

# Create new PipelineRow from result
if result.status == "success" and result.row is not None:
    output_contract = result.contract if result.contract else token.row_data.contract
    new_row = PipelineRow(result.row, output_contract)
    updated_token = token.with_updated_data(new_row)
```

**Similar pattern for GateExecutor and SinkExecutor:**

```python
# SinkExecutor - extract dicts for sink write
rows = [t.row_data.to_dict() for t in tokens]
artifact_info = sink.write(rows, ctx)
```

**Step: Commit**

```bash
git add src/elspeth/engine/executors.py
git commit -m "feat(engine): update executors for PipelineRow

- TransformExecutor: Extract dict for landscape, pass PipelineRow to plugins
- GateExecutor: Same pattern
- SinkExecutor: Extract dicts before sink.write()
- Set ctx.contract from token.row_data.contract for fallback access

Part of PipelineRow migration (Phase 3).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Update RowProcessor and CoalesceExecutor

**Files:**
- Modify: `src/elspeth/engine/processor.py`
- Modify: `src/elspeth/engine/coalesce_executor.py`

**RowProcessor changes:**
- Update calls to `token_manager.create_initial_token()` to pass SourceRow
- Update all `token.row_data` accesses

**CoalesceExecutor changes:**
- Merge contracts from all branches at coalesce point
- Add defensive assertion: crash if any contract is None
- Create PipelineRow with merged contract

```python
def _perform_merge(self, pending: _PendingCoalesce, ...) -> TokenInfo:
    # Defensive check - crash early if any contract is None
    for branch, token in pending.arrived.items():
        if token.row_data.contract is None:
            raise ValueError(
                f"Token {token.token_id} on branch '{branch}' has no contract. "
                f"Cannot coalesce without contracts on all parents."
            )

    # Merge contracts from all arrived branches
    contracts = [t.row_data.contract for t in pending.arrived.values()]
    merged_contract = contracts[0]
    for c in contracts[1:]:
        merged_contract = merged_contract.merge(c)

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

**Step: Commit**

```bash
git add src/elspeth/engine/processor.py src/elspeth/engine/coalesce_executor.py
git commit -m "feat(engine): update RowProcessor and CoalesceExecutor for PipelineRow

- RowProcessor: Pass SourceRow to create_initial_token()
- CoalesceExecutor: Merge contracts at coalesce, create PipelineRow

Part of PipelineRow migration (Phase 3).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Update Core Plugin Implementations

**Files to update (one commit for all):**
- `src/elspeth/plugins/transforms/passthrough.py`
- `src/elspeth/plugins/transforms/field_mapper.py`
- `src/elspeth/plugins/transforms/truncate.py`
- `src/elspeth/plugins/transforms/keyword_filter.py`
- `src/elspeth/plugins/transforms/json_explode.py`
- `src/elspeth/plugins/transforms/batch_stats.py`
- `src/elspeth/plugins/transforms/batch_replicate.py`
- `src/elspeth/plugins/gates/` (all gate implementations)

**Pattern for each plugin:**

```python
def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
    # Access via dual-name (PipelineRow supports __getitem__)
    value = row["field_name"]

    # Create output dict (transforms output dict, not PipelineRow)
    output = row.to_dict()
    output["computed"] = value * 2

    # Propagate contract through result
    return TransformResult.success(
        output,
        success_reason={"action": "computed"},
        contract=row.contract,
    )
```

**Step: Commit**

```bash
git add src/elspeth/plugins/transforms/ src/elspeth/plugins/gates/
git commit -m "feat(plugins): update core transforms and gates for PipelineRow

Update process() and evaluate() signatures to accept PipelineRow.
Propagate contract through TransformResult/GateResult.

Part of PipelineRow migration (Phase 4).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Update LLM Plugin Signatures

**Files:**
- `src/elspeth/plugins/llm/base.py` (already accepts union - simplify to PipelineRow only)
- `src/elspeth/plugins/llm/azure.py`
- `src/elspeth/plugins/llm/azure_batch.py`
- `src/elspeth/plugins/llm/azure_multi_query.py`
- `src/elspeth/plugins/llm/openrouter.py`
- `src/elspeth/plugins/llm/openrouter_batch.py`
- `src/elspeth/plugins/llm/openrouter_multi_query.py`

**Note:** The LLM base class already accepts `dict[str, Any] | PipelineRow`. Simplify to `PipelineRow` only:

```python
def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
    """Process a row through the LLM.

    Args:
        row: Input row as PipelineRow
        ctx: Plugin context
    """
    # Contract always available from row
    input_contract = row.contract
    row_data = row.to_dict()

    # ... rest of processing
```

**Step: Commit**

```bash
git add src/elspeth/plugins/llm/
git commit -m "feat(llm): update LLM plugins for PipelineRow

Simplify process() signature from union type to PipelineRow only.
Remove fallback to ctx.contract since row.contract always available.

Part of PipelineRow migration (Phase 4).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Update Azure Content Safety Plugins

**Files:**
- `src/elspeth/plugins/azure/content_safety.py`
- `src/elspeth/plugins/azure/prompt_shield.py`

Same pattern as Task 7.

**Step: Commit**

```bash
git add src/elspeth/plugins/azure/
git commit -m "feat(azure): update Azure plugins for PipelineRow

Part of PipelineRow migration (Phase 4).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Update Tests

Update all tests that:
1. Create TokenInfo with dict row_data → use PipelineRow
2. Call transform.process() with dict → use PipelineRow
3. Check ctx.contract → verify it's still set (NOT removed)

**Split by subsystem:**

### Task 10a: Update contracts tests (~15 files)
- `tests/contracts/test_results.py`
- `tests/contracts/test_identity.py`

### Task 10b: Update engine tests (~25 files)
- `tests/engine/test_tokens.py`
- `tests/engine/test_executors.py`
- `tests/engine/test_processor.py`
- `tests/engine/test_coalesce*.py`

### Task 10c: Update plugin tests (~40 files)
- `tests/plugins/test_*.py`
- `tests/plugins/llm/`
- `tests/plugins/azure/`

### Task 10d: Update integration tests (~15 files)
- `tests/integration/`

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
elspeth-mcp &
# Then query to verify contracts flow through:
# explain_token(run_id, token_id) -> verify contract present at each step
```

---

## Summary

| Task | Description | Files | Phase |
|------|-------------|-------|-------|
| 1 | Add contract to GateResult | results.py | 1 |
| 2 | Change TokenInfo.row_data type | identity.py | 1 |
| 3 | Update TokenManager | tokens.py | 1 |
| 4 | Update plugin base classes | base.py, protocols.py | 2 |
| 5 | Update engine executors | executors.py | 3 |
| 6 | Update RowProcessor + Coalesce | processor.py, coalesce_executor.py | 3 |
| 7 | Update core plugins | ~15 transform/gate files | 4 |
| 8 | Update LLM plugins | ~7 LLM files | 4 |
| 9 | Update Azure plugins | ~2 Azure files | 4 |
| 10a-d | Update tests | ~95 test files | 5 |

**Phase boundaries for testing:**
- After Phase 1 (Tasks 1-3): Run `pytest tests/contracts/ tests/engine/test_tokens.py`
- After Phase 3 (Tasks 5-6): Run `pytest tests/engine/`
- After Phase 4 (Tasks 7-9): Run `pytest tests/plugins/`
- After Phase 5 (Task 10): Run full `pytest tests/` and `mypy src/`

---

## Changelog from Original Plan

**Removed:**
- "Pre-Implementation: Revert the ctx.contract Shim" section - ctx.contract is production infrastructure
- Task 18 "Remove ctx.contract shim" - WRONG, ctx.contract stays as fallback
- Tasks 5 (BatchTransformMixin), 9 (expression parser), 10 (checkpoint version) - merged into other tasks or no longer needed
- Tasks 11-17 individual plugin tasks - consolidated into Tasks 7-9

**Updated:**
- Architecture description now correctly describes ctx.contract as production mechanism
- LLM plugin section updated to reflect existing `dict | PipelineRow` union type
- Task count reduced from 19 to 10 (plus test subtasks)
- Line numbers updated to current codebase state
- Removed obsolete rollback instructions for ctx.contract changes

**Key insight:** The original plan assumed ctx.contract was temporary. It's actually the correct pattern - executors set it from `token.row_data.contract` before calling plugins, enabling both access patterns.
