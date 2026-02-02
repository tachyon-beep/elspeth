# Phase 3: Transform/Sink Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate schema contracts with transforms and sinks so that contracts propagate through the pipeline, transforms validate input/output against contracts, sinks support header mode configuration, and contract violations route to quarantine.

**Architecture:** Transforms receive `PipelineRow` (with contract), validate input, process, validate output, and emit new `PipelineRow` with updated contract. Sinks validate input against contract and support three header modes: `original`, `normalized`, or custom mapping. Contract violations are treated as transform errors and route via `_on_error`.

**Tech Stack:** Python 3.11+, existing `SchemaContract`, `PipelineRow`, `TransformResult`, `TransformExecutor`, `SinkExecutor`.

**Design Doc:** `docs/plans/2026-02-02-unified-schema-contracts-design.md`

**Depends On:** Phase 1 (Core Contracts), Phase 2 (Source Integration)

---

## Overview

Phase 3 completes the contract flow through the pipeline:

```
Source                Transform               Transform              Sink
┌──────────────┐     ┌──────────────┐        ┌──────────────┐      ┌──────────────┐
│ PipelineRow  │────►│ Validate IN  │───────►│ Validate IN  │─────►│ Validate IN  │
│ + Contract   │     │ Process      │        │ Process      │      │ Write        │
│              │     │ Validate OUT │        │ Validate OUT │      │ Headers mode │
└──────────────┘     │ PipelineRow  │        │ PipelineRow  │      └──────────────┘
                     └──────────────┘        └──────────────┘
```

Key changes:
1. **Contract-aware processing**: Transforms/gates receive and emit `PipelineRow`
2. **Output validation**: Transform output validated against `output_schema` contract
3. **Sink header modes**: `original`, `normalized`, or custom mapping
4. **Violation routing**: Contract violations → `_on_error` sink (existing infrastructure)

---

## Task 1: Transform Contract Protocol

**Files:**
- Create: `src/elspeth/contracts/transform_contract.py`
- Test: `tests/contracts/test_transform_contract.py` (create new)

**Step 1.1: Write failing tests for output contract creation**

```python
# tests/contracts/test_transform_contract.py
"""Tests for transform contract creation and validation."""

import pytest

from elspeth.contracts.data import PluginSchema
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.contracts.transform_contract import (
    create_output_contract_from_schema,
    validate_output_against_contract,
)
from elspeth.contracts.errors import TypeMismatchViolation


class OutputSchema(PluginSchema):
    """Test output schema."""

    id: int
    result: str
    score: float


class TestCreateOutputContract:
    """Test creating output contracts from PluginSchema."""

    def test_creates_fixed_contract_from_schema(self) -> None:
        """PluginSchema creates FIXED contract with declared fields."""
        contract = create_output_contract_from_schema(OutputSchema)

        assert contract.mode == "FIXED"
        assert contract.locked is True
        assert len(contract.fields) == 3

    def test_field_types_from_annotations(self) -> None:
        """Field types extracted from schema annotations."""
        contract = create_output_contract_from_schema(OutputSchema)

        type_map = {f.normalized_name: f.python_type for f in contract.fields}
        assert type_map["id"] is int
        assert type_map["result"] is str
        assert type_map["score"] is float

    def test_fields_are_declared(self) -> None:
        """All fields marked as declared (from schema)."""
        contract = create_output_contract_from_schema(OutputSchema)

        for field in contract.fields:
            assert field.source == "declared"

    def test_original_equals_normalized(self) -> None:
        """Without resolution, original_name equals normalized_name."""
        contract = create_output_contract_from_schema(OutputSchema)

        for field in contract.fields:
            assert field.original_name == field.normalized_name


class DynamicSchema(PluginSchema):
    """Dynamic schema that accepts any fields."""

    model_config = {"extra": "allow"}


class TestDynamicOutputContract:
    """Test dynamic schemas create FLEXIBLE contracts."""

    def test_extra_allow_creates_flexible(self) -> None:
        """Schema with extra='allow' creates FLEXIBLE contract."""
        contract = create_output_contract_from_schema(DynamicSchema)

        assert contract.mode == "FLEXIBLE"


class TestValidateOutputAgainstContract:
    """Test output validation against contracts."""

    @pytest.fixture
    def output_contract(self) -> SchemaContract:
        """Fixed contract for output validation."""
        return SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract("id", "id", int, True, "declared"),
                FieldContract("result", "result", str, True, "declared"),
            ),
            locked=True,
        )

    def test_valid_output_returns_empty(self, output_contract: SchemaContract) -> None:
        """Valid output returns no violations."""
        output = {"id": 1, "result": "success"}
        violations = validate_output_against_contract(output, output_contract)

        assert violations == []

    def test_type_mismatch_returns_violation(self, output_contract: SchemaContract) -> None:
        """Wrong type returns TypeMismatchViolation."""
        output = {"id": "not_an_int", "result": "success"}
        violations = validate_output_against_contract(output, output_contract)

        assert len(violations) == 1
        assert isinstance(violations[0], TypeMismatchViolation)
        assert violations[0].normalized_name == "id"

    def test_missing_field_returns_violation(self, output_contract: SchemaContract) -> None:
        """Missing required field returns violation."""
        output = {"id": 1}  # Missing "result"
        violations = validate_output_against_contract(output, output_contract)

        assert len(violations) == 1
        assert violations[0].normalized_name == "result"

    def test_extra_field_in_fixed_returns_violation(self, output_contract: SchemaContract) -> None:
        """Extra field in FIXED mode returns violation."""
        output = {"id": 1, "result": "ok", "extra": "field"}
        violations = validate_output_against_contract(output, output_contract)

        assert len(violations) == 1
        assert violations[0].normalized_name == "extra"
```

**Step 1.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_transform_contract.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'elspeth.contracts.transform_contract'`

**Step 1.3: Implement transform contract utilities**

```python
# src/elspeth/contracts/transform_contract.py
"""Contract utilities for transform input/output validation.

Transforms have explicit schemas (PluginSchema subclasses) that define
their input and output contracts. This module bridges PluginSchema
(Pydantic) with SchemaContract (frozen dataclass).
"""

from __future__ import annotations

from typing import Any, get_type_hints

from elspeth.contracts.data import PluginSchema
from elspeth.contracts.errors import ContractViolation
from elspeth.contracts.schema_contract import FieldContract, SchemaContract


# Map Python types to contract types
_TYPE_MAP: dict[type, type] = {
    int: int,
    str: str,
    float: float,
    bool: bool,
    type(None): type(None),
}


def _get_python_type(annotation: Any) -> type:
    """Extract Python type from type annotation.

    Handles Optional, Union, etc. by taking the first non-None type.

    Args:
        annotation: Type annotation from schema

    Returns:
        Python primitive type
    """
    # Handle Optional[X] which is Union[X, None]
    origin = getattr(annotation, "__origin__", None)

    if origin is not None:
        # Union type - get first non-None arg
        args = getattr(annotation, "__args__", ())
        for arg in args:
            if arg is not type(None):
                return _TYPE_MAP.get(arg, object)
        return type(None)

    # Simple type
    return _TYPE_MAP.get(annotation, object)


def create_output_contract_from_schema(
    schema_class: type[PluginSchema],
) -> SchemaContract:
    """Create SchemaContract from PluginSchema class.

    Extracts field types from schema annotations. The contract is
    always locked since transform schemas are static.

    Args:
        schema_class: PluginSchema subclass

    Returns:
        Locked SchemaContract with declared fields
    """
    # Check if schema allows extra fields
    model_config = getattr(schema_class, "model_config", {})
    extra = model_config.get("extra", "ignore")

    if extra == "allow":
        mode = "FLEXIBLE"
    elif extra == "forbid":
        mode = "FIXED"
    else:
        mode = "FIXED"  # Default: transforms have fixed output

    # Get field annotations
    hints = get_type_hints(schema_class)

    # Filter out inherited PluginSchema fields (if any)
    # and build FieldContracts
    fields: list[FieldContract] = []

    for name, annotation in hints.items():
        if name.startswith("_"):
            continue  # Skip private fields

        python_type = _get_python_type(annotation)

        # Check if field is optional (has default or is Optional type)
        model_fields = getattr(schema_class, "model_fields", {})
        field_info = model_fields.get(name)

        # Field is required if no default and not Optional
        required = True
        if field_info is not None:
            required = field_info.is_required()

        fields.append(
            FieldContract(
                normalized_name=name,
                original_name=name,  # No resolution for transform outputs
                python_type=python_type,
                required=required,
                source="declared",
            )
        )

    return SchemaContract(
        mode=mode,  # type: ignore[arg-type]
        fields=tuple(fields),
        locked=True,  # Transform schemas are static
    )


def validate_output_against_contract(
    output: dict[str, Any],
    contract: SchemaContract,
) -> list[ContractViolation]:
    """Validate transform output against output contract.

    Args:
        output: Transform output row
        contract: Output schema contract

    Returns:
        List of violations (empty if valid)
    """
    return contract.validate(output)
```

**Step 1.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_transform_contract.py -v
```

Expected: All tests PASS

**Step 1.5: Commit**

```bash
git add src/elspeth/contracts/transform_contract.py tests/contracts/test_transform_contract.py
git commit -m "feat(contracts): add transform contract utilities

Create SchemaContract from PluginSchema for output validation:
- Extract field types from annotations
- Handle Optional types
- Detect extra='allow' for FLEXIBLE mode
- validate_output_against_contract() for validation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Contract Propagation Wrapper

**Files:**
- Create: `src/elspeth/contracts/contract_propagation.py`
- Test: `tests/contracts/test_contract_propagation.py` (create new)

**Step 2.1: Write failing tests for contract propagation**

```python
# tests/contracts/test_contract_propagation.py
"""Tests for contract propagation through transforms."""

import pytest

from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.contracts.contract_propagation import (
    propagate_contract,
    merge_contract_with_output,
)


class TestPropagateContract:
    """Test contract propagation through transform output."""

    @pytest.fixture
    def input_contract(self) -> SchemaContract:
        """Input contract with source fields."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("id", "ID", int, True, "declared"),
                FieldContract("name", "Name", str, True, "declared"),
            ),
            locked=True,
        )

    def test_passthrough_preserves_contract(self, input_contract: SchemaContract) -> None:
        """Passthrough transform preserves input contract."""
        input_row = {"id": 1, "name": "Alice"}
        output_row = {"id": 1, "name": "Alice"}  # Same data

        output_contract = propagate_contract(
            input_contract=input_contract,
            output_row=output_row,
            transform_adds_fields=False,
        )

        assert output_contract.mode == input_contract.mode
        assert len(output_contract.fields) == len(input_contract.fields)

    def test_transform_adds_field(self, input_contract: SchemaContract) -> None:
        """Transform adding field creates new contract with added field."""
        output_row = {"id": 1, "name": "Alice", "score": 95.5}

        output_contract = propagate_contract(
            input_contract=input_contract,
            output_row=output_row,
            transform_adds_fields=True,
        )

        assert len(output_contract.fields) == 3
        score_field = next(f for f in output_contract.fields if f.normalized_name == "score")
        assert score_field.python_type is float
        assert score_field.source == "inferred"

    def test_preserves_original_names(self, input_contract: SchemaContract) -> None:
        """Original names preserved through propagation."""
        output_row = {"id": 1, "name": "Alice"}

        output_contract = propagate_contract(
            input_contract=input_contract,
            output_row=output_row,
            transform_adds_fields=False,
        )

        id_field = next(f for f in output_contract.fields if f.normalized_name == "id")
        assert id_field.original_name == "ID"


class TestMergeContractWithOutput:
    """Test merging output schema with propagated contract."""

    def test_output_schema_adds_guaranteed_fields(self) -> None:
        """Output schema fields become guaranteed in merged contract."""
        input_contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("id", "id", int, True, "declared"),),
            locked=True,
        )

        output_schema_contract = SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract("id", "id", int, True, "declared"),
                FieldContract("result", "result", str, True, "declared"),
            ),
            locked=True,
        )

        merged = merge_contract_with_output(
            input_contract=input_contract,
            output_schema_contract=output_schema_contract,
        )

        # Output schema guarantees 'result' field
        result_field = next(f for f in merged.fields if f.normalized_name == "result")
        assert result_field is not None
        assert result_field.required is True

    def test_preserves_original_names_from_input(self) -> None:
        """Original names from input contract preserved in merge."""
        input_contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("amount_usd", "'Amount USD'", int, True, "declared"),),
            locked=True,
        )

        output_schema_contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("amount_usd", "amount_usd", int, True, "declared"),),
            locked=True,
        )

        merged = merge_contract_with_output(
            input_contract=input_contract,
            output_schema_contract=output_schema_contract,
        )

        # Original name from input should be preserved
        amount_field = next(f for f in merged.fields if f.normalized_name == "amount_usd")
        assert amount_field.original_name == "'Amount USD'"
```

**Step 2.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_contract_propagation.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 2.3: Implement contract propagation**

```python
# src/elspeth/contracts/contract_propagation.py
"""Contract propagation through transform pipeline.

Contracts flow through the pipeline, carrying field metadata (types,
original names) from source to sink. Transforms may add fields, which
get inferred types, or remove fields (narrowing the contract).
"""

from __future__ import annotations

from typing import Any

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.contracts.type_normalization import normalize_type_for_contract


def propagate_contract(
    input_contract: SchemaContract,
    output_row: dict[str, Any],
    *,
    transform_adds_fields: bool = True,
) -> SchemaContract:
    """Propagate contract through transform, inferring new field types.

    For passthrough transforms: returns input contract unchanged.
    For transforms adding fields: infers types from output values.

    Args:
        input_contract: Contract from input row
        output_row: Transform output data
        transform_adds_fields: If True, infer types for new fields

    Returns:
        Contract for output row
    """
    if not transform_adds_fields:
        # Passthrough - same contract (or could narrow based on output keys)
        return input_contract

    # Check for new fields in output
    existing_names = {f.normalized_name for f in input_contract.fields}
    new_fields: list[FieldContract] = []

    for name, value in output_row.items():
        if name not in existing_names:
            # New field - infer type
            new_fields.append(
                FieldContract(
                    normalized_name=name,
                    original_name=name,  # No original for transform-created fields
                    python_type=normalize_type_for_contract(value),
                    required=False,  # Inferred fields are optional
                    source="inferred",
                )
            )

    if not new_fields:
        return input_contract

    # Create new contract with additional fields
    return SchemaContract(
        mode=input_contract.mode,
        fields=input_contract.fields + tuple(new_fields),
        locked=True,
    )


def merge_contract_with_output(
    input_contract: SchemaContract,
    output_schema_contract: SchemaContract,
) -> SchemaContract:
    """Merge input contract with transform's output schema.

    The output schema contract defines what the transform guarantees.
    We merge this with input contract to preserve original names
    while adding any new guaranteed fields.

    Args:
        input_contract: Contract from input (has original names)
        output_schema_contract: Contract from transform.output_schema

    Returns:
        Merged contract with original names and output guarantees
    """
    # Build lookup for input contract original names
    input_originals = {f.normalized_name: f.original_name for f in input_contract.fields}

    # Build merged fields
    merged_fields: list[FieldContract] = []

    for output_field in output_schema_contract.fields:
        # Preserve original name from input if available
        original = input_originals.get(
            output_field.normalized_name,
            output_field.original_name,
        )

        merged_fields.append(
            FieldContract(
                normalized_name=output_field.normalized_name,
                original_name=original,
                python_type=output_field.python_type,
                required=output_field.required,
                source=output_field.source,
            )
        )

    # Use most restrictive mode
    mode_order = {"FIXED": 0, "FLEXIBLE": 1, "OBSERVED": 2}
    merged_mode = min(
        input_contract.mode,
        output_schema_contract.mode,
        key=lambda m: mode_order[m],
    )

    return SchemaContract(
        mode=merged_mode,
        fields=tuple(merged_fields),
        locked=True,
    )
```

**Step 2.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_contract_propagation.py -v
```

Expected: All tests PASS

**Step 2.5: Commit**

```bash
git add src/elspeth/contracts/contract_propagation.py tests/contracts/test_contract_propagation.py
git commit -m "feat(contracts): add contract propagation utilities

propagate_contract(): Infer types for new fields from output
merge_contract_with_output(): Merge input originals with output schema

Preserves original names through transform chain.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: TransformResult with Contract

**Files:**
- Modify: `src/elspeth/contracts/results.py`
- Test: `tests/contracts/test_transform_result_contract.py` (create new)

**Step 3.1: Write failing tests for TransformResult with contract**

```python
# tests/contracts/test_transform_result_contract.py
"""Tests for TransformResult with SchemaContract."""

import pytest

from elspeth.contracts.results import TransformResult
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


class TestTransformResultWithContract:
    """Test TransformResult carrying contract reference."""

    @pytest.fixture
    def sample_contract(self) -> SchemaContract:
        """Sample output contract."""
        return SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract("id", "id", int, True, "declared"),
                FieldContract("result", "result", str, True, "declared"),
            ),
            locked=True,
        )

    def test_success_with_contract(self, sample_contract: SchemaContract) -> None:
        """TransformResult.success() can include contract."""
        result = TransformResult.success(
            row={"id": 1, "result": "ok"},
            success_reason={"action": "processed"},
            contract=sample_contract,
        )

        assert result.contract is sample_contract

    def test_success_without_contract(self) -> None:
        """TransformResult.success() works without contract (backwards compatible)."""
        result = TransformResult.success(
            row={"id": 1},
            success_reason={"action": "processed"},
        )

        assert result.contract is None

    def test_error_has_no_contract(self) -> None:
        """Error results don't carry contracts."""
        result = TransformResult.error(
            reason={"error": "failed"},
            retryable=False,
        )

        assert result.contract is None

    def test_success_multi_with_contract(self, sample_contract: SchemaContract) -> None:
        """success_multi() can include contract."""
        result = TransformResult.success_multi(
            rows=[{"id": 1, "result": "a"}, {"id": 2, "result": "b"}],
            success_reason={"action": "split"},
            contract=sample_contract,
        )

        assert result.contract is sample_contract

    def test_to_pipeline_row(self, sample_contract: SchemaContract) -> None:
        """TransformResult can convert to PipelineRow."""
        result = TransformResult.success(
            row={"id": 1, "result": "ok"},
            success_reason={"action": "processed"},
            contract=sample_contract,
        )

        pipeline_row = result.to_pipeline_row()

        assert isinstance(pipeline_row, PipelineRow)
        assert pipeline_row["id"] == 1

    def test_to_pipeline_row_raises_on_error(self) -> None:
        """to_pipeline_row() raises for error results."""
        result = TransformResult.error(
            reason={"error": "failed"},
            retryable=False,
        )

        with pytest.raises(ValueError, match="error"):
            result.to_pipeline_row()

    def test_to_pipeline_row_raises_without_contract(self) -> None:
        """to_pipeline_row() raises if no contract."""
        result = TransformResult.success(
            row={"id": 1},
            success_reason={"action": "processed"},
        )

        with pytest.raises(ValueError, match="no contract"):
            result.to_pipeline_row()

    def test_to_pipeline_rows_multi(self, sample_contract: SchemaContract) -> None:
        """to_pipeline_rows() returns list for multi-row results."""
        result = TransformResult.success_multi(
            rows=[{"id": 1, "result": "a"}, {"id": 2, "result": "b"}],
            success_reason={"action": "split"},
            contract=sample_contract,
        )

        pipeline_rows = result.to_pipeline_rows()

        assert len(pipeline_rows) == 2
        assert all(isinstance(r, PipelineRow) for r in pipeline_rows)
```

**Step 3.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_transform_result_contract.py -v
```

Expected: FAIL (TransformResult doesn't have contract parameter)

**Step 3.3: Update TransformResult to support contracts**

In `src/elspeth/contracts/results.py`, update the `TransformResult` dataclass:

First, update the TYPE_CHECKING import block:

```python
if TYPE_CHECKING:
    from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
```

Then update the `TransformResult` class (around line 85):

```python
@dataclass
class TransformResult:
    """Result of a transform operation.

    Encapsulates success/error state, output data, and metadata.
    For Phase 3+, can carry schema contract for output validation.

    Attributes:
        status: "success" or "error"
        row: Single row output (for success)
        rows: Multiple row output (for success_multi)
        reason: Error details (for error)
        success_reason: Success metadata (REQUIRED for success)
        retryable: Whether error is retryable
        input_hash: Set by executor
        output_hash: Set by executor
        duration_ms: Set by executor
        context_after: Pool metadata
        contract: Schema contract for output (Phase 3+)
    """

    status: Literal["success", "error"]
    row: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None
    reason: TransformErrorReason | None = None
    success_reason: TransformSuccessReason | None = None
    retryable: bool = False
    input_hash: str | None = None
    output_hash: str | None = None
    duration_ms: float | None = None
    context_after: dict[str, Any] | None = None
    contract: "SchemaContract | None" = None

    def __post_init__(self) -> None:
        if self.status == "success" and self.success_reason is None:
            raise ValueError(
                "TransformResult with status='success' MUST provide success_reason"
            )

    @property
    def is_success(self) -> bool:
        """Check if result is success."""
        return self.status == "success"

    @property
    def is_error(self) -> bool:
        """Check if result is error."""
        return self.status == "error"

    @property
    def is_multi_row(self) -> bool:
        """Check if result has multiple output rows."""
        return self.rows is not None

    @classmethod
    def success(
        cls,
        row: dict[str, Any],
        *,
        success_reason: TransformSuccessReason,
        contract: "SchemaContract | None" = None,
    ) -> "TransformResult":
        """Create success result with single output row.

        Args:
            row: Output row data
            success_reason: Metadata about what was done
            contract: Optional output schema contract

        Returns:
            TransformResult with status='success'
        """
        return cls(
            status="success",
            row=row,
            success_reason=success_reason,
            contract=contract,
        )

    @classmethod
    def success_multi(
        cls,
        rows: list[dict[str, Any]],
        *,
        success_reason: TransformSuccessReason,
        contract: "SchemaContract | None" = None,
    ) -> "TransformResult":
        """Create success result with multiple output rows.

        Args:
            rows: List of output rows
            success_reason: Metadata about what was done
            contract: Optional output schema contract

        Returns:
            TransformResult with status='success' and is_multi_row=True
        """
        return cls(
            status="success",
            rows=rows,
            success_reason=success_reason,
            contract=contract,
        )

    @classmethod
    def error(
        cls,
        reason: TransformErrorReason,
        *,
        retryable: bool = False,
    ) -> "TransformResult":
        """Create error result.

        Args:
            reason: Structured error details
            retryable: Whether operation can be retried

        Returns:
            TransformResult with status='error'
        """
        return cls(
            status="error",
            reason=reason,
            retryable=retryable,
            contract=None,  # Errors don't have contracts
        )

    def to_pipeline_row(self) -> "PipelineRow":
        """Convert single-row result to PipelineRow.

        Returns:
            PipelineRow wrapping output data with contract

        Raises:
            ValueError: If result is error, multi-row, or has no contract
        """
        from elspeth.contracts.schema_contract import PipelineRow

        if self.is_error:
            raise ValueError("Cannot convert error result to PipelineRow")
        if self.is_multi_row:
            raise ValueError("Cannot convert multi-row result to single PipelineRow - use to_pipeline_rows()")
        if self.contract is None:
            raise ValueError("TransformResult has no contract - cannot create PipelineRow")
        if self.row is None:
            raise ValueError("TransformResult has no row data")

        return PipelineRow(self.row, self.contract)

    def to_pipeline_rows(self) -> list["PipelineRow"]:
        """Convert multi-row result to list of PipelineRows.

        Returns:
            List of PipelineRow instances

        Raises:
            ValueError: If result is error, single-row, or has no contract
        """
        from elspeth.contracts.schema_contract import PipelineRow

        if self.is_error:
            raise ValueError("Cannot convert error result to PipelineRows")
        if not self.is_multi_row:
            raise ValueError("Cannot convert single-row result to list - use to_pipeline_row()")
        if self.contract is None:
            raise ValueError("TransformResult has no contract - cannot create PipelineRows")
        if self.rows is None:
            raise ValueError("TransformResult has no rows data")

        return [PipelineRow(row, self.contract) for row in self.rows]
```

**Step 3.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_transform_result_contract.py -v
```

Expected: All tests PASS

**Step 3.5: Run existing TransformResult tests to ensure no regressions**

```bash
.venv/bin/python -m pytest tests/contracts/test_results.py -v -k "TransformResult"
```

Expected: All tests PASS

**Step 3.6: Commit**

```bash
git add src/elspeth/contracts/results.py tests/contracts/test_transform_result_contract.py
git commit -m "feat(contracts): add contract support to TransformResult

TransformResult.success/success_multi now accept optional contract.
Add to_pipeline_row() and to_pipeline_rows() methods.

Error results cannot have contracts.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Sink Header Modes

**Files:**
- Create: `src/elspeth/contracts/header_modes.py`
- Test: `tests/contracts/test_header_modes.py` (create new)

**Step 4.1: Write failing tests for header mode resolution**

```python
# tests/contracts/test_header_modes.py
"""Tests for sink header mode resolution."""

import pytest

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.contracts.header_modes import (
    HeaderMode,
    resolve_headers,
    parse_header_mode,
)


class TestParseHeaderMode:
    """Test parsing header mode from config."""

    def test_parse_normalized(self) -> None:
        """String 'normalized' parses to NORMALIZED mode."""
        mode = parse_header_mode("normalized")
        assert mode == HeaderMode.NORMALIZED

    def test_parse_original(self) -> None:
        """String 'original' parses to ORIGINAL mode."""
        mode = parse_header_mode("original")
        assert mode == HeaderMode.ORIGINAL

    def test_parse_dict_is_custom(self) -> None:
        """Dict config is CUSTOM mode."""
        mode = parse_header_mode({"amount_usd": "AMOUNT_USD"})
        assert mode == HeaderMode.CUSTOM

    def test_parse_none_defaults_to_normalized(self) -> None:
        """None defaults to NORMALIZED."""
        mode = parse_header_mode(None)
        assert mode == HeaderMode.NORMALIZED


class TestResolveHeaders:
    """Test header resolution for different modes."""

    @pytest.fixture
    def contract(self) -> SchemaContract:
        """Contract with original name mappings."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount_usd", "'Amount USD'", int, True, "declared"),
                FieldContract("customer_id", "Customer ID", str, True, "declared"),
            ),
            locked=True,
        )

    def test_normalized_mode(self, contract: SchemaContract) -> None:
        """NORMALIZED mode uses normalized names."""
        headers = resolve_headers(
            contract=contract,
            mode=HeaderMode.NORMALIZED,
            custom_mapping=None,
        )

        assert headers == {"amount_usd": "amount_usd", "customer_id": "customer_id"}

    def test_original_mode(self, contract: SchemaContract) -> None:
        """ORIGINAL mode uses original names from contract."""
        headers = resolve_headers(
            contract=contract,
            mode=HeaderMode.ORIGINAL,
            custom_mapping=None,
        )

        assert headers == {"amount_usd": "'Amount USD'", "customer_id": "Customer ID"}

    def test_custom_mode(self, contract: SchemaContract) -> None:
        """CUSTOM mode uses provided mapping."""
        custom = {"amount_usd": "AMOUNT", "customer_id": "CUSTOMER"}

        headers = resolve_headers(
            contract=contract,
            mode=HeaderMode.CUSTOM,
            custom_mapping=custom,
        )

        assert headers == {"amount_usd": "AMOUNT", "customer_id": "CUSTOMER"}

    def test_custom_partial_mapping(self, contract: SchemaContract) -> None:
        """CUSTOM mode with partial mapping falls back to normalized."""
        custom = {"amount_usd": "AMOUNT"}  # customer_id not mapped

        headers = resolve_headers(
            contract=contract,
            mode=HeaderMode.CUSTOM,
            custom_mapping=custom,
        )

        assert headers["amount_usd"] == "AMOUNT"
        assert headers["customer_id"] == "customer_id"  # Fallback

    def test_no_contract_returns_identity(self) -> None:
        """Without contract, returns identity mapping for known fields."""
        headers = resolve_headers(
            contract=None,
            mode=HeaderMode.ORIGINAL,
            custom_mapping=None,
            field_names=["a", "b"],
        )

        assert headers == {"a": "a", "b": "b"}
```

**Step 4.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_header_modes.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 4.3: Implement header modes**

```python
# src/elspeth/contracts/header_modes.py
"""Sink header mode resolution.

Sinks can output headers in three modes:
- NORMALIZED: Use Python identifier names (default)
- ORIGINAL: Restore original source header names
- CUSTOM: Use explicit mapping for external system handover

This module bridges SchemaContract (which stores original names)
with sink output configuration.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any

from elspeth.contracts.schema_contract import SchemaContract


class HeaderMode(Enum):
    """Header output mode for sinks."""

    NORMALIZED = auto()  # Python identifiers: "amount_usd"
    ORIGINAL = auto()    # Source headers: "'Amount USD'"
    CUSTOM = auto()      # Explicit mapping: "AMOUNT_USD"


def parse_header_mode(
    config: str | dict[str, str] | None,
) -> HeaderMode:
    """Parse header mode from sink config.

    Args:
        config: One of:
            - None: Default to NORMALIZED
            - "normalized": Use normalized names
            - "original": Restore original names
            - dict: Custom mapping

    Returns:
        HeaderMode enum value
    """
    if config is None:
        return HeaderMode.NORMALIZED

    if isinstance(config, dict):
        return HeaderMode.CUSTOM

    if config == "normalized":
        return HeaderMode.NORMALIZED

    if config == "original":
        return HeaderMode.ORIGINAL

    raise ValueError(
        f"Invalid header mode '{config}'. "
        f"Expected 'normalized', 'original', or mapping dict."
    )


def resolve_headers(
    *,
    contract: SchemaContract | None,
    mode: HeaderMode,
    custom_mapping: dict[str, str] | None,
    field_names: list[str] | None = None,
) -> dict[str, str]:
    """Resolve output headers based on mode and contract.

    Args:
        contract: Schema contract with original name metadata
        mode: Header mode (NORMALIZED, ORIGINAL, CUSTOM)
        custom_mapping: Custom mapping for CUSTOM mode
        field_names: Field names if contract is None

    Returns:
        Dict mapping normalized_name -> output_header
    """
    # Determine field names to process
    if contract is not None:
        names = [f.normalized_name for f in contract.fields]
    elif field_names is not None:
        names = field_names
    else:
        return {}

    result: dict[str, str] = {}

    for name in names:
        if mode == HeaderMode.NORMALIZED:
            result[name] = name

        elif mode == HeaderMode.ORIGINAL:
            if contract is not None:
                field = contract.get_field(name)
                result[name] = field.original_name if field else name
            else:
                result[name] = name

        elif mode == HeaderMode.CUSTOM:
            if custom_mapping and name in custom_mapping:
                result[name] = custom_mapping[name]
            else:
                result[name] = name  # Fallback to normalized

    return result
```

**Step 4.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_header_modes.py -v
```

Expected: All tests PASS

**Step 4.5: Commit**

```bash
git add src/elspeth/contracts/header_modes.py tests/contracts/test_header_modes.py
git commit -m "feat(contracts): add sink header mode resolution

Three header modes for sink output:
- NORMALIZED: Python identifiers (default)
- ORIGINAL: Restore source headers from contract
- CUSTOM: Explicit mapping for external systems

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Sink Config Header Mode

**Files:**
- Modify: `src/elspeth/plugins/config_base.py`
- Test: `tests/plugins/test_sink_header_config.py` (create new)

**Step 5.1: Write failing tests for sink header config**

```python
# tests/plugins/test_sink_header_config.py
"""Tests for sink header mode configuration."""

import pytest

from elspeth.plugins.config_base import SinkPathConfig
from elspeth.contracts.header_modes import HeaderMode


class TestSinkHeaderConfig:
    """Test sink header mode parsing from config."""

    def test_default_is_normalized(self) -> None:
        """Default headers mode is normalized."""
        config = SinkPathConfig.from_dict({
            "path": "output.csv",
            "schema": {"fields": "dynamic"},
        })

        assert config.headers_mode == HeaderMode.NORMALIZED

    def test_headers_normalized(self) -> None:
        """headers: normalized parses correctly."""
        config = SinkPathConfig.from_dict({
            "path": "output.csv",
            "schema": {"fields": "dynamic"},
            "headers": "normalized",
        })

        assert config.headers_mode == HeaderMode.NORMALIZED

    def test_headers_original(self) -> None:
        """headers: original parses correctly."""
        config = SinkPathConfig.from_dict({
            "path": "output.csv",
            "schema": {"fields": "dynamic"},
            "headers": "original",
        })

        assert config.headers_mode == HeaderMode.ORIGINAL

    def test_headers_custom_dict(self) -> None:
        """headers: {mapping} parses as CUSTOM."""
        config = SinkPathConfig.from_dict({
            "path": "output.csv",
            "schema": {"fields": "dynamic"},
            "headers": {"amount_usd": "AMOUNT_USD"},
        })

        assert config.headers_mode == HeaderMode.CUSTOM
        assert config.headers_mapping == {"amount_usd": "AMOUNT_USD"}

    def test_restore_source_headers_sets_original(self) -> None:
        """restore_source_headers=True sets ORIGINAL mode."""
        config = SinkPathConfig.from_dict({
            "path": "output.csv",
            "schema": {"fields": "dynamic"},
            "restore_source_headers": True,
        })

        assert config.headers_mode == HeaderMode.ORIGINAL

    def test_headers_takes_precedence(self) -> None:
        """headers setting takes precedence over restore_source_headers."""
        config = SinkPathConfig.from_dict({
            "path": "output.csv",
            "schema": {"fields": "dynamic"},
            "headers": "normalized",
            "restore_source_headers": True,  # Ignored
        })

        assert config.headers_mode == HeaderMode.NORMALIZED
```

**Step 5.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/plugins/test_sink_header_config.py -v
```

Expected: FAIL (SinkPathConfig doesn't have headers_mode property)

**Step 5.3: Update SinkPathConfig with headers mode**

In `src/elspeth/plugins/config_base.py`, update `SinkPathConfig`:

First, add import:

```python
from elspeth.contracts.header_modes import HeaderMode, parse_header_mode
```

Then update the class (around line 200):

```python
class SinkPathConfig(PathConfig):
    """Configuration for path-based sinks (CSV, JSON).

    Attributes:
        display_headers: Explicit header mapping (deprecated, use 'headers')
        restore_source_headers: Restore original headers (deprecated, use 'headers: original')
        headers: Header output mode - 'normalized', 'original', or {mapping}
    """

    display_headers: dict[str, str] | None = None
    restore_source_headers: bool = False
    headers: str | dict[str, str] | None = None

    @property
    def headers_mode(self) -> HeaderMode:
        """Get resolved header mode.

        Priority:
        1. 'headers' setting (if specified)
        2. 'restore_source_headers' (legacy, maps to ORIGINAL)
        3. Default: NORMALIZED
        """
        if self.headers is not None:
            return parse_header_mode(self.headers)

        if self.restore_source_headers:
            return HeaderMode.ORIGINAL

        if self.display_headers is not None:
            return HeaderMode.CUSTOM

        return HeaderMode.NORMALIZED

    @property
    def headers_mapping(self) -> dict[str, str] | None:
        """Get custom header mapping if CUSTOM mode."""
        if isinstance(self.headers, dict):
            return self.headers

        if self.display_headers is not None:
            return self.display_headers

        return None
```

**Step 5.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/plugins/test_sink_header_config.py -v
```

Expected: All tests PASS

**Step 5.5: Commit**

```bash
git add src/elspeth/plugins/config_base.py tests/plugins/test_sink_header_config.py
git commit -m "feat(plugins): add headers mode to sink config

New 'headers' option: 'normalized', 'original', or {mapping}
Deprecates restore_source_headers and display_headers.
headers_mode property provides unified access.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: CSVSink Header Mode Integration

**Files:**
- Modify: `src/elspeth/plugins/sinks/csv_sink.py`
- Test: `tests/plugins/sinks/test_csv_sink_headers.py` (create new)

**Step 6.1: Write failing tests for CSVSink header modes**

```python
# tests/plugins/sinks/test_csv_sink_headers.py
"""Tests for CSVSink header mode integration."""

from pathlib import Path

import pytest

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.plugins.sinks.csv_sink import CSVSink


class MockContext:
    """Minimal context for testing."""

    def __init__(self) -> None:
        self.run_id = "test-run"
        self.landscape = None


class TestCSVSinkHeaderModes:
    """Test CSVSink header output modes."""

    @pytest.fixture
    def output_path(self, tmp_path: Path) -> Path:
        """Output file path."""
        return tmp_path / "output.csv"

    @pytest.fixture
    def sample_contract(self) -> SchemaContract:
        """Contract with original name mappings."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount_usd", "'Amount USD'", int, True, "declared"),
                FieldContract("customer_id", "Customer ID", str, True, "declared"),
            ),
            locked=True,
        )

    def test_normalized_headers(self, output_path: Path) -> None:
        """headers: normalized uses Python identifiers."""
        sink = CSVSink({
            "path": str(output_path),
            "schema": {"fields": "dynamic"},
            "headers": "normalized",
        })
        ctx = MockContext()

        sink.write([{"amount_usd": 100, "customer_id": "C001"}], ctx)
        sink.close()

        content = output_path.read_text()
        assert "amount_usd" in content
        assert "customer_id" in content

    def test_original_headers_from_contract(
        self, output_path: Path, sample_contract: SchemaContract
    ) -> None:
        """headers: original restores source headers from contract."""
        sink = CSVSink({
            "path": str(output_path),
            "schema": {"fields": "dynamic"},
            "headers": "original",
        })
        ctx = MockContext()

        # Provide contract to sink
        sink.set_output_contract(sample_contract)

        sink.write([{"amount_usd": 100, "customer_id": "C001"}], ctx)
        sink.close()

        content = output_path.read_text()
        assert "'Amount USD'" in content
        assert "Customer ID" in content

    def test_custom_headers(self, output_path: Path) -> None:
        """headers: {mapping} uses custom header names."""
        sink = CSVSink({
            "path": str(output_path),
            "schema": {"fields": "dynamic"},
            "headers": {
                "amount_usd": "AMOUNT",
                "customer_id": "CUST_ID",
            },
        })
        ctx = MockContext()

        sink.write([{"amount_usd": 100, "customer_id": "C001"}], ctx)
        sink.close()

        content = output_path.read_text()
        assert "AMOUNT" in content
        assert "CUST_ID" in content
```

**Step 6.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/plugins/sinks/test_csv_sink_headers.py -v
```

Expected: FAIL (CSVSink doesn't have set_output_contract method)

**Step 6.3: Update CSVSink to use header modes and contracts**

In `src/elspeth/plugins/sinks/csv_sink.py`, add contract support:

First, add imports:

```python
from elspeth.contracts.header_modes import HeaderMode, resolve_headers
from elspeth.contracts.schema_contract import SchemaContract
```

Then update the class to add contract tracking and header resolution:

```python
class CSVSink(BaseSink):
    """CSV file sink with header mode support."""

    name = "csv"
    # ... existing attributes ...

    # Contract for header resolution (Phase 3)
    _output_contract: SchemaContract | None = None

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        cfg = CSVSinkConfig.from_dict(config)

        self._path = cfg.resolved_path()
        # ... existing init code ...

        # Header mode configuration
        self._headers_mode = cfg.headers_mode
        self._headers_mapping = cfg.headers_mapping

        # Resolved headers (computed lazily on first write)
        self._resolved_headers: dict[str, str] | None = None

    def set_output_contract(self, contract: SchemaContract) -> None:
        """Set output contract for header resolution.

        Called by engine before first write to provide contract
        with original name metadata.

        Args:
            contract: Output schema contract
        """
        self._output_contract = contract
        # Reset resolved headers to recompute with contract
        self._resolved_headers = None

    def _resolve_headers_if_needed(self, row_keys: list[str]) -> dict[str, str]:
        """Resolve headers on first write.

        Args:
            row_keys: Field names from first row

        Returns:
            Mapping of normalized_name -> output_header
        """
        if self._resolved_headers is not None:
            return self._resolved_headers

        self._resolved_headers = resolve_headers(
            contract=self._output_contract,
            mode=self._headers_mode,
            custom_mapping=self._headers_mapping,
            field_names=row_keys,
        )

        return self._resolved_headers

    def write(
        self,
        rows: list[dict[str, Any]],
        ctx: PluginContext,
    ) -> ArtifactDescriptor:
        """Write rows to CSV with configured header mode."""
        if not rows:
            return ArtifactDescriptor.empty()

        # Resolve headers on first write
        first_row_keys = list(rows[0].keys())
        header_map = self._resolve_headers_if_needed(first_row_keys)

        # Write header row if file is new
        if not self._header_written:
            output_headers = [header_map.get(k, k) for k in first_row_keys]
            self._writer.writerow(output_headers)
            self._header_written = True

        # Write data rows (keys unchanged, only headers mapped)
        for row in rows:
            self._writer.writerow([row[k] for k in first_row_keys])

        # ... rest of existing write logic ...
```

**Step 6.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/plugins/sinks/test_csv_sink_headers.py -v
```

Expected: All tests PASS

**Step 6.5: Run existing CSVSink tests to ensure no regressions**

```bash
.venv/bin/python -m pytest tests/plugins/sinks/test_csv_sink.py -v
```

Expected: All tests PASS

**Step 6.6: Commit**

```bash
git add src/elspeth/plugins/sinks/csv_sink.py tests/plugins/sinks/test_csv_sink_headers.py
git commit -m "feat(csv-sink): integrate header modes with contracts

CSVSink now supports:
- set_output_contract() for original name resolution
- headers: normalized/original/{mapping}
- Lazy header resolution on first write

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: BaseSink Contract Support

**Files:**
- Modify: `src/elspeth/plugins/base.py`
- Test: `tests/plugins/test_base_sink_contract.py` (create new)

**Step 7.1: Write failing tests for BaseSink contract methods**

```python
# tests/plugins/test_base_sink_contract.py
"""Tests for BaseSink schema contract tracking."""

from typing import Any

import pytest

from elspeth.contracts import ArtifactDescriptor
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.plugins.base import BaseSink
from elspeth.plugins.context import PluginContext


class TestSink(BaseSink):
    """Test sink implementation."""

    name = "test"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        from elspeth.contracts.data import PluginSchema
        self.input_schema = PluginSchema

    def write(self, rows: list[dict[str, Any]], ctx: PluginContext) -> ArtifactDescriptor:
        return ArtifactDescriptor.empty()

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class TestBaseSinkContract:
    """Test contract tracking on BaseSink."""

    def test_get_output_contract_returns_none_before_set(self) -> None:
        """get_output_contract() returns None before set."""
        sink = TestSink({})
        assert sink.get_output_contract() is None

    def test_set_output_contract(self) -> None:
        """set_output_contract() stores contract for retrieval."""
        sink = TestSink({})
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )

        sink.set_output_contract(contract)

        assert sink.get_output_contract() is contract
```

**Step 7.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/plugins/test_base_sink_contract.py -v
```

Expected: FAIL (BaseSink doesn't have get/set_output_contract methods)

**Step 7.3: Add contract tracking to BaseSink**

In `src/elspeth/plugins/base.py`, update the `BaseSink` class:

```python
class BaseSink(ABC):
    """Base class for sink plugins.

    Schema Contract Support (Phase 3):
        Sinks can receive output contracts for header resolution.
        Use set_output_contract() to provide contract before write,
        then use get_output_contract() for header mode resolution.
    """

    name: str
    input_schema: type[PluginSchema]
    idempotent: bool = False
    node_id: str | None = None

    # ... existing attributes ...

    # Output contract for header resolution (Phase 3)
    _output_contract: "SchemaContract | None" = None

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration."""
        self.config = config
        self._output_contract = None

    # === Schema Contract Support (Phase 3) ===

    def get_output_contract(self) -> "SchemaContract | None":
        """Get the output contract for header resolution.

        Returns:
            SchemaContract if set, None otherwise
        """
        return self._output_contract

    def set_output_contract(self, contract: "SchemaContract") -> None:
        """Set output contract for header resolution.

        Called by engine before first write to provide contract
        with original name metadata for header modes.

        Args:
            contract: Output schema contract
        """
        self._output_contract = contract

    # ... rest of existing methods ...
```

**Step 7.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/plugins/test_base_sink_contract.py -v
```

Expected: All tests PASS

**Step 7.5: Commit**

```bash
git add src/elspeth/plugins/base.py tests/plugins/test_base_sink_contract.py
git commit -m "feat(plugins): add contract tracking to BaseSink

Add get_output_contract() and set_output_contract() methods.
Sinks can receive contracts for header mode resolution.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Contract Violation Error Type

**Files:**
- Modify: `src/elspeth/contracts/errors.py`
- Test: `tests/contracts/test_contract_violation_error.py` (create new)

**Step 8.1: Write failing tests for contract violation as transform error**

```python
# tests/contracts/test_contract_violation_error.py
"""Tests for contract violation error integration."""

import pytest

from elspeth.contracts.errors import (
    ContractViolation,
    MissingFieldViolation,
    TypeMismatchViolation,
    TransformErrorReason,
)
from elspeth.contracts.results import TransformResult


class TestContractViolationAsError:
    """Test converting contract violations to transform errors."""

    def test_violation_to_error_reason(self) -> None:
        """Contract violation converts to TransformErrorReason."""
        violation = TypeMismatchViolation(
            normalized_name="amount",
            original_name="'Amount'",
            expected_type=int,
            actual_type=str,
            actual_value="not_a_number",
        )

        reason = violation.to_error_reason()

        assert isinstance(reason, dict)
        assert reason["error"] == "contract_violation"
        assert reason["field"] == "amount"
        assert reason["violation_type"] == "type_mismatch"

    def test_transform_error_from_violation(self) -> None:
        """TransformResult.error can be created from violation."""
        violation = MissingFieldViolation(
            normalized_name="required_field",
            original_name="Required Field",
        )

        result = TransformResult.error(
            reason=violation.to_error_reason(),
            retryable=False,
        )

        assert result.is_error
        assert result.reason["error"] == "contract_violation"

    def test_multiple_violations_to_error(self) -> None:
        """Multiple violations combine into single error reason."""
        violations = [
            MissingFieldViolation("a", "A"),
            TypeMismatchViolation("b", "B", int, str, "x"),
        ]

        from elspeth.contracts.errors import violations_to_error_reason

        reason = violations_to_error_reason(violations)

        assert reason["error"] == "contract_violations"
        assert len(reason["violations"]) == 2
```

**Step 8.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_contract_violation_error.py -v
```

Expected: FAIL (to_error_reason method doesn't exist)

**Step 8.3: Add error conversion to ContractViolation**

In `src/elspeth/contracts/errors.py`, update the violation classes:

```python
class ContractViolation(Exception):
    """Base class for schema contract violations."""

    def __init__(self, normalized_name: str, original_name: str) -> None:
        self.normalized_name = normalized_name
        self.original_name = original_name
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        return f"Contract violation on field '{self.original_name}' ({self.normalized_name})"

    def to_error_reason(self) -> dict[str, Any]:
        """Convert to TransformErrorReason dict.

        Returns:
            Dict suitable for TransformResult.error()
        """
        return {
            "error": "contract_violation",
            "field": self.normalized_name,
            "original_field": self.original_name,
            "violation_type": self.__class__.__name__.replace("Violation", "").lower(),
            "message": str(self),
        }


class TypeMismatchViolation(ContractViolation):
    """Raised when a field value has wrong type."""

    def __init__(
        self,
        normalized_name: str,
        original_name: str,
        expected_type: type,
        actual_type: type,
        actual_value: Any,
    ) -> None:
        self.expected_type = expected_type
        self.actual_type = actual_type
        self.actual_value = actual_value
        super().__init__(normalized_name, original_name)

    def _format_message(self) -> str:
        return (
            f"Field '{self.original_name}' ({self.normalized_name}) "
            f"expected {self.expected_type.__name__}, got {self.actual_type.__name__}"
        )

    def to_error_reason(self) -> dict[str, Any]:
        """Convert to TransformErrorReason with type details."""
        reason = super().to_error_reason()
        reason["violation_type"] = "type_mismatch"
        reason["expected_type"] = self.expected_type.__name__
        reason["actual_type"] = self.actual_type.__name__
        return reason


# Add helper function at module level:

def violations_to_error_reason(
    violations: list[ContractViolation],
) -> dict[str, Any]:
    """Convert multiple violations to single error reason.

    Args:
        violations: List of contract violations

    Returns:
        Combined error reason dict
    """
    if len(violations) == 1:
        return violations[0].to_error_reason()

    return {
        "error": "contract_violations",
        "count": len(violations),
        "violations": [v.to_error_reason() for v in violations],
        "message": f"{len(violations)} contract violations",
    }
```

**Step 8.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_contract_violation_error.py -v
```

Expected: All tests PASS

**Step 8.5: Commit**

```bash
git add src/elspeth/contracts/errors.py tests/contracts/test_contract_violation_error.py
git commit -m "feat(contracts): add error conversion for violations

ContractViolation.to_error_reason() for TransformResult.error()
violations_to_error_reason() combines multiple violations.

Enables contract violations to route via _on_error.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Module Exports

**Files:**
- Modify: `src/elspeth/contracts/__init__.py`
- Test: Run all tests

**Step 9.1: Update module exports**

Add to `src/elspeth/contracts/__init__.py`:

```python
# Transform/Sink contracts (Phase 3)
from elspeth.contracts.contract_propagation import (
    merge_contract_with_output,
    propagate_contract,
)
from elspeth.contracts.header_modes import (
    HeaderMode,
    parse_header_mode,
    resolve_headers,
)
from elspeth.contracts.transform_contract import (
    create_output_contract_from_schema,
    validate_output_against_contract,
)
from elspeth.contracts.errors import violations_to_error_reason
```

Update `__all__` list:

```python
__all__ = [
    # ... existing exports ...

    # Transform/Sink contracts (Phase 3)
    "HeaderMode",
    "create_output_contract_from_schema",
    "merge_contract_with_output",
    "parse_header_mode",
    "propagate_contract",
    "resolve_headers",
    "validate_output_against_contract",
    "violations_to_error_reason",
]
```

**Step 9.2: Run all contract tests**

```bash
.venv/bin/python -m pytest tests/contracts/ -v --tb=short
```

Expected: All tests PASS

**Step 9.3: Run type checker**

```bash
.venv/bin/python -m mypy src/elspeth/contracts/
```

Expected: No errors

**Step 9.4: Run linter**

```bash
.venv/bin/python -m ruff check src/elspeth/contracts/
```

Expected: No errors

**Step 9.5: Commit**

```bash
git add src/elspeth/contracts/__init__.py
git commit -m "feat(contracts): export Phase 3 transform/sink utilities

Add to contracts module exports:
- HeaderMode, parse_header_mode, resolve_headers
- create_output_contract_from_schema, validate_output_against_contract
- propagate_contract, merge_contract_with_output
- violations_to_error_reason

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Integration Test - Transform Chain

**Files:**
- Test: `tests/integration/test_transform_contract_integration.py` (create new)

**Step 10.1: Write integration test**

```python
# tests/integration/test_transform_contract_integration.py
"""Integration tests for transform → contract → sink flow."""

from pathlib import Path
from textwrap import dedent

import pytest

from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.contracts.header_modes import HeaderMode
from elspeth.plugins.sources.csv_source import CSVSource
from elspeth.plugins.sinks.csv_sink import CSVSink


class MockContext:
    """Minimal context for integration testing."""

    def __init__(self) -> None:
        self.run_id = "test-run"
        self.landscape = None
        self.validation_errors: list[dict] = []

    def record_validation_error(self, **kwargs: object) -> None:
        self.validation_errors.append(dict(kwargs))


class TestTransformContractIntegration:
    """End-to-end tests for contract propagation."""

    def test_source_to_sink_contract_flow(self, tmp_path: Path) -> None:
        """Contract flows from source through to sink."""
        # Create source CSV
        input_file = tmp_path / "input.csv"
        input_file.write_text(dedent("""\
            'Amount USD',Customer ID
            100,C001
            200,C002
        """))

        output_file = tmp_path / "output.csv"

        # Source with normalization
        source = CSVSource({
            "path": str(input_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "discard",
            "normalize_fields": True,
        })

        # Sink with original header mode
        sink = CSVSink({
            "path": str(output_file),
            "schema": {"fields": "dynamic"},
            "headers": "original",
        })

        ctx = MockContext()

        # Load rows from source
        source_rows = list(source.load(ctx))

        # Get contract from source
        contract = source.get_schema_contract()
        assert contract is not None

        # Pass contract to sink
        sink.set_output_contract(contract)

        # Write rows to sink
        rows_to_write = [sr.row for sr in source_rows if not sr.is_quarantined]
        sink.write(rows_to_write, ctx)
        sink.close()

        # Verify output has original headers
        output_content = output_file.read_text()
        assert "'Amount USD'" in output_content
        assert "Customer ID" in output_content

    def test_contract_preserved_through_transform(self, tmp_path: Path) -> None:
        """Original names preserved when transform adds fields."""
        input_file = tmp_path / "input.csv"
        input_file.write_text(dedent("""\
            Original Header
            value1
        """))

        source = CSVSource({
            "path": str(input_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "discard",
            "normalize_fields": True,
        })

        ctx = MockContext()
        source_rows = list(source.load(ctx))

        # Simulate transform adding a field
        contract = source.get_schema_contract()
        pipeline_row = source_rows[0].to_pipeline_row()

        # Access by original name still works
        assert pipeline_row["Original Header"] == "value1"
        assert pipeline_row.original_header == "value1"

    def test_pipeline_row_dual_access(self, tmp_path: Path) -> None:
        """PipelineRow supports both original and normalized access."""
        input_file = tmp_path / "input.csv"
        input_file.write_text(dedent("""\
            'Messy Header!!',Simple
            A,B
        """))

        source = CSVSource({
            "path": str(input_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "discard",
            "normalize_fields": True,
        })

        ctx = MockContext()
        source_rows = list(source.load(ctx))
        row = source_rows[0].to_pipeline_row()

        # Normalized access
        assert row["messy_header"] == "A"
        assert row.messy_header == "A"

        # Original access
        assert row["'Messy Header!!'"] == "A"

        # Containment checks
        assert "messy_header" in row
        assert "'Messy Header!!'" in row
        assert "nonexistent" not in row
```

**Step 10.2: Run integration tests**

```bash
.venv/bin/python -m pytest tests/integration/test_transform_contract_integration.py -v
```

Expected: All tests PASS

**Step 10.3: Commit**

```bash
git add tests/integration/test_transform_contract_integration.py
git commit -m "test(integration): add transform/sink contract integration tests

End-to-end tests for:
- Source → Sink contract flow
- Original header restoration
- PipelineRow dual-name access

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Update Beads and Sync

**Step 11.1: Update beads issue**

```bash
bd close elspeth-rapid-XXX  # Replace with actual issue ID
bd sync
```

---

## Summary

Phase 3 implementation integrates schema contracts with transforms and sinks:

| Component | Purpose |
|-----------|---------|
| `transform_contract.py` | Create contracts from PluginSchema |
| `contract_propagation.py` | Propagate/merge contracts through pipeline |
| `header_modes.py` | Resolve sink headers (original/normalized/custom) |
| `TransformResult.contract` | Attach contract to transform output |
| `BaseSink.set_output_contract()` | Receive contract for header resolution |
| `violations_to_error_reason()` | Convert violations to error routing |

**Key patterns:**
- Contracts propagate through transform chain
- Original names preserved from source to sink
- Three header modes: normalized, original, custom
- Contract violations → `_on_error` routing (existing infrastructure)

**Next:** Phase 4 implements template resolver with dual-name support.
