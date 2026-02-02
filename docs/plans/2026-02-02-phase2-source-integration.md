# Phase 2: Source Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate schema contracts with source plugins so sources emit `PipelineRow` with inferred contracts, merging `FieldResolution` into `SchemaContract` and implementing infer-and-lock semantics for OBSERVED mode.

**Architecture:** Sources will create a `SchemaContract` from their `SchemaConfig` at initialization, then update it with inferred fields on the first row (for OBSERVED/FLEXIBLE modes). The contract locks after the first row, and all subsequent rows are validated against it. `FieldResolution` data is incorporated into `FieldContract` instances (original_name field).

**Tech Stack:** Python 3.11+, existing `SchemaConfig`, `FieldResolution`, `SchemaContract` from Phase 1, Pydantic for validation.

**Design Doc:** `docs/plans/2026-02-02-unified-schema-contracts-design.md`

**Depends On:** Phase 1 (Core Contracts) - `FieldContract`, `SchemaContract`, `PipelineRow` must be implemented.

**Pre-Requisite Fixes Applied:** The following fixes were made to Phase 1 code before Phase 2 implementation:

1. **`any` type validation** (`schema_contract.py`): `SchemaContract.validate()` now skips type checks for fields with `python_type=object` since `any` type accepts any value. Without this fix, `any` fields would spuriously fail validation because `int != object`, `str != object`, etc.

2. **`object` in checkpoint type map** (`schema_contract.py`): `SchemaContract.from_checkpoint()` type map now includes `"object": object` to support checkpoint restoration of `any` type fields.

3. **Tests for `any` type** (`test_schema_contract.py`): Added `TestSchemaContractAnyType` test class with 9 tests covering validation and checkpoint round-trip.

---

## Overview

Phase 2 creates the bridge between configuration-time schema definitions and runtime contracts:

```
SchemaConfig (YAML)     →  SchemaContract (runtime)  →  PipelineRow (per-row)
├── mode: strict        →  mode: FIXED               →  row["field"] / row.field
├── mode: free          →  mode: FLEXIBLE
└── fields: dynamic     →  mode: OBSERVED
```

Key changes:
1. **Contract Factory**: Create `SchemaContract` from `SchemaConfig` + `FieldResolution`
2. **Source Base**: Update `BaseSource` to track contract state
3. **CSVSource**: Emit `PipelineRow` instead of `dict[str, Any]`
4. **First-Row Locking**: OBSERVED/FLEXIBLE modes lock types on first row

---

## Task 1: Schema Mode Mapping

**Files:**
- Create: `src/elspeth/contracts/schema_contract_factory.py`
- Test: `tests/contracts/test_schema_contract_factory.py` (create new)

**Step 1.1: Write failing tests for mode mapping**

```python
# tests/contracts/test_schema_contract_factory.py
"""Tests for SchemaContract factory from SchemaConfig."""

import pytest

from elspeth.contracts.schema import FieldDefinition, SchemaConfig
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.contracts.schema_contract_factory import (
    create_contract_from_config,
    map_schema_mode,
)


class TestMapSchemaMode:
    """Test mapping SchemaConfig modes to SchemaContract modes."""

    def test_strict_maps_to_fixed(self) -> None:
        """strict mode maps to FIXED."""
        assert map_schema_mode("strict") == "FIXED"

    def test_free_maps_to_flexible(self) -> None:
        """free mode maps to FLEXIBLE."""
        assert map_schema_mode("free") == "FLEXIBLE"

    def test_none_maps_to_observed(self) -> None:
        """None (dynamic) maps to OBSERVED."""
        assert map_schema_mode(None) == "OBSERVED"


class TestCreateContractFromConfig:
    """Test creating SchemaContract from SchemaConfig."""

    def test_dynamic_schema_creates_observed_contract(self) -> None:
        """Dynamic schema creates unlocked OBSERVED contract."""
        config = SchemaConfig.from_dict({"fields": "dynamic"})
        contract = create_contract_from_config(config)

        assert contract.mode == "OBSERVED"
        assert contract.locked is False
        assert len(contract.fields) == 0

    def test_strict_schema_creates_fixed_contract(self) -> None:
        """Strict schema creates FIXED contract with declared fields."""
        config = SchemaConfig.from_dict({
            "mode": "strict",
            "fields": ["id: int", "name: str"],
        })
        contract = create_contract_from_config(config)

        assert contract.mode == "FIXED"
        assert len(contract.fields) == 2
        # Fields are declared and required
        id_field = next(f for f in contract.fields if f.normalized_name == "id")
        assert id_field.python_type is int
        assert id_field.required is True
        assert id_field.source == "declared"

    def test_free_schema_creates_flexible_contract(self) -> None:
        """Free schema creates FLEXIBLE contract."""
        config = SchemaConfig.from_dict({
            "mode": "free",
            "fields": ["id: int"],
        })
        contract = create_contract_from_config(config)

        assert contract.mode == "FLEXIBLE"

    def test_optional_field_not_required(self) -> None:
        """Optional field (?) has required=False."""
        config = SchemaConfig.from_dict({
            "mode": "strict",
            "fields": ["id: int", "note: str?"],
        })
        contract = create_contract_from_config(config)

        note_field = next(f for f in contract.fields if f.normalized_name == "note")
        assert note_field.required is False

    def test_field_type_mapping(self) -> None:
        """Field types map correctly to Python types."""
        config = SchemaConfig.from_dict({
            "mode": "strict",
            "fields": [
                "a: int",
                "b: str",
                "c: float",
                "d: bool",
                "e: any",
            ],
        })
        contract = create_contract_from_config(config)

        type_map = {f.normalized_name: f.python_type for f in contract.fields}
        assert type_map["a"] is int
        assert type_map["b"] is str
        assert type_map["c"] is float
        assert type_map["d"] is bool
        # 'any' type maps to object (base type)
        assert type_map["e"] is object

    def test_explicit_contract_is_locked(self) -> None:
        """Explicit schemas (strict/free) start locked."""
        config = SchemaConfig.from_dict({
            "mode": "strict",
            "fields": ["id: int"],
        })
        contract = create_contract_from_config(config)

        # Explicit schemas have complete type info - locked immediately
        assert contract.locked is True

    def test_dynamic_contract_is_unlocked(self) -> None:
        """Dynamic schemas start unlocked (types inferred from first row)."""
        config = SchemaConfig.from_dict({"fields": "dynamic"})
        contract = create_contract_from_config(config)

        assert contract.locked is False
```

**Step 1.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract_factory.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'elspeth.contracts.schema_contract_factory'`

**Step 1.3: Implement schema contract factory**

```python
# src/elspeth/contracts/schema_contract_factory.py
"""Factory for creating SchemaContract from configuration.

Bridges the gap between user-facing SchemaConfig (YAML) and runtime
SchemaContract used for validation and dual-name access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from elspeth.contracts.schema_contract import FieldContract, SchemaContract

if TYPE_CHECKING:
    from elspeth.contracts.schema import SchemaConfig


# Type mapping from SchemaConfig field types to Python types
_FIELD_TYPE_MAP: dict[str, type] = {
    "int": int,
    "str": str,
    "float": float,
    "bool": bool,
    "any": object,  # 'any' accepts anything - use object as base type
}


def map_schema_mode(
    mode: Literal["strict", "free"] | None,
) -> Literal["FIXED", "FLEXIBLE", "OBSERVED"]:
    """Map SchemaConfig mode to SchemaContract mode.

    Args:
        mode: SchemaConfig mode ('strict', 'free', or None for dynamic)

    Returns:
        SchemaContract mode literal
    """
    if mode == "strict":
        return "FIXED"
    elif mode == "free":
        return "FLEXIBLE"
    else:
        return "OBSERVED"


def create_contract_from_config(
    config: "SchemaConfig",
    field_resolution: dict[str, str] | None = None,
) -> SchemaContract:
    """Create SchemaContract from SchemaConfig.

    For explicit schemas (strict/free), creates a locked contract with
    declared fields. For dynamic schemas, creates an unlocked contract
    that will infer types from the first row.

    Args:
        config: Schema configuration from YAML
        field_resolution: Optional mapping of original→normalized names.
            If provided, original_name on FieldContract will use the
            original header; otherwise, original_name = normalized_name.

    Returns:
        SchemaContract ready for validation
    """
    mode = map_schema_mode(config.mode)

    # Build reverse mapping for looking up original names
    # field_resolution is original→normalized, we need normalized→original
    normalized_to_original: dict[str, str] = {}
    if field_resolution:
        normalized_to_original = {v: k for k, v in field_resolution.items()}

    # For explicit schemas, create FieldContracts from FieldDefinitions
    fields: tuple[FieldContract, ...] = ()

    if config.fields is not None:
        field_contracts: list[FieldContract] = []
        for fd in config.fields:
            # Look up original name if resolution provided
            original = normalized_to_original.get(fd.name, fd.name)

            fc = FieldContract(
                normalized_name=fd.name,
                original_name=original,
                python_type=_FIELD_TYPE_MAP[fd.field_type],
                required=fd.required,
                source="declared",
            )
            field_contracts.append(fc)
        fields = tuple(field_contracts)

    # Explicit schemas start locked (types are known)
    # Dynamic schemas start unlocked (types inferred from first row)
    locked = not config.is_dynamic

    return SchemaContract(
        mode=mode,
        fields=fields,
        locked=locked,
    )
```

**Step 1.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract_factory.py -v
```

Expected: All tests PASS

**Step 1.5: Commit**

```bash
git add src/elspeth/contracts/schema_contract_factory.py tests/contracts/test_schema_contract_factory.py
git commit -m "feat(contracts): add schema contract factory

Create SchemaContract from SchemaConfig:
- strict -> FIXED (locked, exact fields)
- free -> FLEXIBLE (locked, at least these fields)
- dynamic -> OBSERVED (unlocked, infer from first row)

Maps field types: int, str, float, bool, any.
Supports field_resolution for original name tracking.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Contract Factory with Field Resolution

**Files:**
- Modify: `src/elspeth/contracts/schema_contract_factory.py`
- Test: `tests/contracts/test_schema_contract_factory.py` (extend)

**Step 2.1: Write failing tests for field resolution integration**

Add to `tests/contracts/test_schema_contract_factory.py`:

```python
class TestContractWithFieldResolution:
    """Test creating contracts with field resolution (original names)."""

    def test_field_resolution_sets_original_names(self) -> None:
        """Field resolution mapping populates original_name."""
        config = SchemaConfig.from_dict({
            "mode": "strict",
            "fields": ["amount_usd: int", "customer_id: str"],
        })
        resolution = {
            "'Amount USD'": "amount_usd",
            "Customer ID": "customer_id",
        }
        contract = create_contract_from_config(config, field_resolution=resolution)

        amount_field = next(f for f in contract.fields if f.normalized_name == "amount_usd")
        assert amount_field.original_name == "'Amount USD'"

        customer_field = next(f for f in contract.fields if f.normalized_name == "customer_id")
        assert customer_field.original_name == "Customer ID"

    def test_no_resolution_uses_normalized_as_original(self) -> None:
        """Without resolution, original_name equals normalized_name."""
        config = SchemaConfig.from_dict({
            "mode": "strict",
            "fields": ["id: int"],
        })
        contract = create_contract_from_config(config)  # No resolution

        id_field = contract.fields[0]
        assert id_field.original_name == id_field.normalized_name == "id"

    def test_partial_resolution(self) -> None:
        """Resolution mapping can be partial (not all fields mapped)."""
        config = SchemaConfig.from_dict({
            "mode": "strict",
            "fields": ["mapped_field: int", "unmapped_field: str"],
        })
        resolution = {"Original Header": "mapped_field"}  # Only one field
        contract = create_contract_from_config(config, field_resolution=resolution)

        mapped = next(f for f in contract.fields if f.normalized_name == "mapped_field")
        unmapped = next(f for f in contract.fields if f.normalized_name == "unmapped_field")

        assert mapped.original_name == "Original Header"
        assert unmapped.original_name == "unmapped_field"  # Falls back to normalized
```

**Step 2.2: Run tests to verify they pass**

These tests should pass with the existing implementation from Step 1.3.

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract_factory.py::TestContractWithFieldResolution -v
```

Expected: All tests PASS

**Step 2.3: Commit**

```bash
git add tests/contracts/test_schema_contract_factory.py
git commit -m "test(contracts): add field resolution tests for contract factory

Verify original_name population from field_resolution mapping.
Partial resolution falls back to normalized name.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: First-Row Type Inference

**Files:**
- Create: `src/elspeth/contracts/contract_builder.py`
- Test: `tests/contracts/test_contract_builder.py` (create new)

**Step 3.1: Write failing tests for first-row inference**

```python
# tests/contracts/test_contract_builder.py
"""Tests for ContractBuilder - handles first-row inference and locking."""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.contracts.contract_builder import ContractBuilder
from elspeth.contracts.errors import TypeMismatchViolation


class TestContractBuilderInference:
    """Test type inference from first row."""

    def test_infer_types_from_first_row(self) -> None:
        """OBSERVED mode infers types from first row."""
        contract = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        builder = ContractBuilder(contract)

        first_row = {"id": 1, "name": "Alice", "score": 3.14}
        field_resolution = {"id": "id", "name": "name", "score": "score"}

        updated = builder.process_first_row(first_row, field_resolution)

        assert updated.locked is True
        assert len(updated.fields) == 3

        types = {f.normalized_name: f.python_type for f in updated.fields}
        assert types["id"] is int
        assert types["name"] is str
        assert types["score"] is float

    def test_infer_preserves_original_names(self) -> None:
        """Inferred fields get correct original names from resolution."""
        contract = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        builder = ContractBuilder(contract)

        first_row = {"amount_usd": 100}
        field_resolution = {"'Amount USD'": "amount_usd"}

        updated = builder.process_first_row(first_row, field_resolution)

        field = updated.fields[0]
        assert field.normalized_name == "amount_usd"
        assert field.original_name == "'Amount USD'"

    def test_flexible_adds_extra_fields(self) -> None:
        """FLEXIBLE mode adds extra fields to declared ones."""
        declared = FieldContract("id", "id", int, True, "declared")
        contract = SchemaContract(mode="FLEXIBLE", fields=(declared,), locked=False)
        builder = ContractBuilder(contract)

        first_row = {"id": 1, "extra": "value"}
        field_resolution = {"id": "id", "extra": "extra"}

        updated = builder.process_first_row(first_row, field_resolution)

        assert len(updated.fields) == 2
        extra_field = next(f for f in updated.fields if f.normalized_name == "extra")
        assert extra_field.python_type is str
        assert extra_field.source == "inferred"
        assert extra_field.required is False  # Inferred fields are optional

    def test_fixed_ignores_first_row(self) -> None:
        """FIXED mode doesn't infer - already locked."""
        declared = FieldContract("id", "id", int, True, "declared")
        contract = SchemaContract(mode="FIXED", fields=(declared,), locked=True)
        builder = ContractBuilder(contract)

        first_row = {"id": 1}
        field_resolution = {"id": "id"}

        # Should return same contract (already locked)
        updated = builder.process_first_row(first_row, field_resolution)
        assert updated is contract

    def test_infer_numpy_types(self) -> None:
        """numpy types normalize to Python primitives."""
        contract = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        builder = ContractBuilder(contract)

        first_row = {
            "np_int": np.int64(42),
            "np_float": np.float64(3.14),
            "np_bool": np.bool_(True),
        }
        field_resolution = {k: k for k in first_row}

        updated = builder.process_first_row(first_row, field_resolution)

        types = {f.normalized_name: f.python_type for f in updated.fields}
        assert types["np_int"] is int
        assert types["np_float"] is float
        assert types["np_bool"] is bool

    def test_infer_pandas_timestamp(self) -> None:
        """pandas.Timestamp normalizes to datetime."""
        contract = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        builder = ContractBuilder(contract)

        first_row = {"ts": pd.Timestamp("2024-01-01")}
        field_resolution = {"ts": "ts"}

        updated = builder.process_first_row(first_row, field_resolution)

        ts_field = updated.fields[0]
        assert ts_field.python_type is datetime

    def test_infer_none_type(self) -> None:
        """None values infer as type(None)."""
        contract = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        builder = ContractBuilder(contract)

        first_row = {"nullable": None}
        field_resolution = {"nullable": "nullable"}

        updated = builder.process_first_row(first_row, field_resolution)

        field = updated.fields[0]
        assert field.python_type is type(None)


class TestContractBuilderValidation:
    """Test validation after locking."""

    def test_validate_subsequent_row(self) -> None:
        """Subsequent rows validate against locked contract."""
        contract = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        builder = ContractBuilder(contract)

        first_row = {"id": 1, "name": "Alice"}
        field_resolution = {"id": "id", "name": "name"}
        locked_contract = builder.process_first_row(first_row, field_resolution)

        # Valid row
        violations = locked_contract.validate({"id": 2, "name": "Bob"})
        assert violations == []

    def test_type_mismatch_after_lock(self) -> None:
        """Type mismatch on subsequent row returns violation."""
        contract = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        builder = ContractBuilder(contract)

        first_row = {"amount": 100}  # int
        field_resolution = {"amount": "amount"}
        locked_contract = builder.process_first_row(first_row, field_resolution)

        # Wrong type
        violations = locked_contract.validate({"amount": "not_an_int"})

        assert len(violations) == 1
        assert isinstance(violations[0], TypeMismatchViolation)
        assert violations[0].expected_type is int
        assert violations[0].actual_type is str

    def test_any_type_field_accepts_different_types(self) -> None:
        """Fields declared as 'any' (python_type=object) accept any type."""
        # Pre-declare a field with 'any' type (object)
        any_field = FieldContract("data", "Data", object, True, "declared")
        contract = SchemaContract(mode="FLEXIBLE", fields=(any_field,), locked=True)

        # Should accept int
        violations = contract.validate({"data": 42})
        assert violations == []

        # Should accept str
        violations = contract.validate({"data": "hello"})
        assert violations == []

        # Should accept list
        violations = contract.validate({"data": [1, 2, 3]})
        assert violations == []

        # Should accept None
        violations = contract.validate({"data": None})
        assert violations == []
```

**Step 3.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_contract_builder.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'elspeth.contracts.contract_builder'`

**Step 3.3: Implement ContractBuilder**

```python
# src/elspeth/contracts/contract_builder.py
"""Contract builder for first-row inference and locking.

Handles the "infer-and-lock" pattern for OBSERVED and FLEXIBLE modes:
1. First row arrives
2. Types are inferred from values
3. Contract is locked
4. Subsequent rows validate against locked contract
"""

from __future__ import annotations

from typing import Any

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.contracts.type_normalization import normalize_type_for_contract


class ContractBuilder:
    """Manages contract state through first-row inference.

    For OBSERVED/FLEXIBLE modes, the first row determines field types.
    After processing the first row, the contract is locked and cannot
    be modified.

    Usage:
        builder = ContractBuilder(initial_contract)
        locked_contract = builder.process_first_row(first_row, resolution)
        # Use locked_contract.validate() for subsequent rows

    Attributes:
        contract: Current contract state (may be locked or unlocked)
    """

    def __init__(self, contract: SchemaContract) -> None:
        """Initialize with starting contract.

        Args:
            contract: Initial contract from config (may be locked or unlocked)
        """
        self._contract = contract

    @property
    def contract(self) -> SchemaContract:
        """Current contract state."""
        return self._contract

    def process_first_row(
        self,
        row: dict[str, Any],
        field_resolution: dict[str, str],
    ) -> SchemaContract:
        """Process first row to infer types and lock contract.

        For unlocked contracts (OBSERVED/FLEXIBLE):
        - Infers types from row values
        - Adds any extra fields (FLEXIBLE/OBSERVED only)
        - Locks the contract

        For locked contracts (FIXED with declared fields):
        - Returns the contract unchanged

        Args:
            row: First row data (normalized field names as keys)
            field_resolution: Mapping of original→normalized names

        Returns:
            Locked SchemaContract with all field types defined

        Raises:
            ValueError: If row contains NaN or Infinity values
        """
        # Already locked - nothing to do
        if self._contract.locked:
            return self._contract

        # Build reverse mapping: normalized → original
        normalized_to_original = {v: k for k, v in field_resolution.items()}

        # Start from current contract
        updated = self._contract

        # Get set of already-declared field names
        declared_names = {f.normalized_name for f in updated.fields}

        # Process each field in the row
        for normalized_name, value in row.items():
            if normalized_name in declared_names:
                # Field already declared - skip (type from config takes precedence)
                continue

            # New field - infer type
            original_name = normalized_to_original.get(normalized_name, normalized_name)
            updated = updated.with_field(normalized_name, original_name, value)

        # Lock the contract
        updated = updated.with_locked()
        self._contract = updated

        return updated
```

**Step 3.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_contract_builder.py -v
```

Expected: All tests PASS

**Step 3.5: Commit**

```bash
git add src/elspeth/contracts/contract_builder.py tests/contracts/test_contract_builder.py
git commit -m "feat(contracts): add ContractBuilder for first-row inference

Implements infer-and-lock pattern for OBSERVED/FLEXIBLE modes:
- First row determines field types
- Types normalized (numpy/pandas -> primitives)
- Contract locks after first row
- Subsequent rows validate against locked contract

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: SourceRow with Contract

**Files:**
- Modify: `src/elspeth/contracts/results.py`
- Test: `tests/contracts/test_source_row_contract.py` (create new)

**Step 4.1: Write failing tests for SourceRow with contract**

```python
# tests/contracts/test_source_row_contract.py
"""Tests for SourceRow with SchemaContract integration."""

import pytest

from elspeth.contracts.results import SourceRow
from elspeth.contracts.schema_contract import (
    FieldContract,
    PipelineRow,
    SchemaContract,
)


class TestSourceRowWithContract:
    """Test SourceRow carrying contract reference."""

    @pytest.fixture
    def sample_contract(self) -> SchemaContract:
        """Sample locked contract."""
        return SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract("id", "ID", int, True, "declared"),
                FieldContract("name", "Name", str, True, "declared"),
            ),
            locked=True,
        )

    def test_valid_with_contract(self, sample_contract: SchemaContract) -> None:
        """SourceRow.valid() can include contract."""
        row_data = {"id": 1, "name": "Alice"}
        source_row = SourceRow.valid(row_data, contract=sample_contract)

        assert source_row.is_quarantined is False
        assert source_row.contract is sample_contract

    def test_valid_without_contract(self) -> None:
        """SourceRow.valid() works without contract (backwards compatible)."""
        row_data = {"id": 1}
        source_row = SourceRow.valid(row_data)

        assert source_row.contract is None

    def test_quarantined_no_contract(self) -> None:
        """Quarantined rows don't carry contracts."""
        source_row = SourceRow.quarantined(
            row={"bad": "data"},
            error="validation failed",
            destination="quarantine",
        )

        assert source_row.contract is None

    def test_to_pipeline_row(self, sample_contract: SchemaContract) -> None:
        """SourceRow can convert to PipelineRow."""
        row_data = {"id": 1, "name": "Alice"}
        source_row = SourceRow.valid(row_data, contract=sample_contract)

        pipeline_row = source_row.to_pipeline_row()

        assert isinstance(pipeline_row, PipelineRow)
        assert pipeline_row["id"] == 1
        assert pipeline_row["name"] == "Alice"

    def test_to_pipeline_row_raises_without_contract(self) -> None:
        """to_pipeline_row() raises if no contract attached."""
        source_row = SourceRow.valid({"id": 1})

        with pytest.raises(ValueError, match="no contract"):
            source_row.to_pipeline_row()

    def test_to_pipeline_row_raises_if_quarantined(self, sample_contract: SchemaContract) -> None:
        """to_pipeline_row() raises for quarantined rows."""
        source_row = SourceRow.quarantined(
            row={"bad": "data"},
            error="failed",
            destination="quarantine",
        )

        with pytest.raises(ValueError, match="quarantined"):
            source_row.to_pipeline_row()
```

**Step 4.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_source_row_contract.py -v
```

Expected: FAIL (SourceRow doesn't have contract parameter)

**Step 4.3: Modify SourceRow to support contracts**

In `src/elspeth/contracts/results.py`, find the `SourceRow` class and update it:

First, add import at top of file:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
```

Then modify the `SourceRow` dataclass (around line 389):

```python
@dataclass
class SourceRow:
    """Result of loading a row from a source.

    Either a valid row ready for processing, or a quarantined row
    with error information for routing to quarantine sink.

    Attributes:
        row: The row data (dict for valid, may be partial for quarantined)
        is_quarantined: True if row failed validation
        quarantine_error: Error message if quarantined
        quarantine_destination: Sink name for quarantined rows
        contract: SchemaContract for valid rows (optional, for Phase 2+)
    """

    row: Any
    is_quarantined: bool
    quarantine_error: str | None = None
    quarantine_destination: str | None = None
    contract: "SchemaContract | None" = None

    @classmethod
    def valid(
        cls,
        row: dict[str, Any],
        contract: "SchemaContract | None" = None,
    ) -> "SourceRow":
        """Create a valid source row.

        Args:
            row: Validated row data
            contract: Optional schema contract for the row

        Returns:
            SourceRow with is_quarantined=False
        """
        return cls(row=row, is_quarantined=False, contract=contract)

    @classmethod
    def quarantined(
        cls,
        row: Any,
        error: str,
        destination: str,
    ) -> "SourceRow":
        """Create a quarantined source row.

        Args:
            row: Row data (may be partial or malformed)
            error: Description of validation failure
            destination: Sink name for quarantine routing

        Returns:
            SourceRow with is_quarantined=True
        """
        return cls(
            row=row,
            is_quarantined=True,
            quarantine_error=error,
            quarantine_destination=destination,
            contract=None,  # Quarantined rows don't have contracts
        )

    def to_pipeline_row(self) -> "PipelineRow":
        """Convert to PipelineRow for processing.

        Returns:
            PipelineRow wrapping row data with contract

        Raises:
            ValueError: If row is quarantined or has no contract
        """
        from elspeth.contracts.schema_contract import PipelineRow

        if self.is_quarantined:
            raise ValueError("Cannot convert quarantined row to PipelineRow")
        if self.contract is None:
            raise ValueError("SourceRow has no contract - cannot create PipelineRow")

        return PipelineRow(self.row, self.contract)
```

**Step 4.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_source_row_contract.py -v
```

Expected: All tests PASS

**Step 4.5: Commit**

```bash
git add src/elspeth/contracts/results.py tests/contracts/test_source_row_contract.py
git commit -m "feat(contracts): add contract support to SourceRow

SourceRow.valid() now accepts optional contract parameter.
Add to_pipeline_row() method for converting to PipelineRow.

Quarantined rows cannot have contracts or convert to PipelineRow.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: BaseSource Contract Tracking

**Files:**
- Modify: `src/elspeth/plugins/base.py`
- Test: `tests/plugins/test_base_source_contract.py` (create new)

**Step 5.1: Write failing tests for BaseSource contract methods**

```python
# tests/plugins/test_base_source_contract.py
"""Tests for BaseSource schema contract tracking."""

from collections.abc import Iterator
from typing import Any

import pytest

from elspeth.contracts import SourceRow
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.plugins.base import BaseSource
from elspeth.plugins.context import PluginContext


class TestSource(BaseSource):
    """Test source implementation."""

    name = "test"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._on_validation_failure = "quarantine"
        # Manually set output_schema for protocol compliance
        from elspeth.contracts.data import PluginSchema
        self.output_schema = PluginSchema

    def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
        yield SourceRow.valid({"id": 1})

    def close(self) -> None:
        pass


class TestBaseSourceContract:
    """Test contract tracking on BaseSource."""

    def test_get_schema_contract_returns_none_before_load(self) -> None:
        """get_schema_contract() returns None before load()."""
        source = TestSource({})
        assert source.get_schema_contract() is None

    def test_set_schema_contract(self) -> None:
        """set_schema_contract() stores contract for retrieval."""
        source = TestSource({})
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "id", int, True, "declared"),),
            locked=True,
        )

        source.set_schema_contract(contract)

        assert source.get_schema_contract() is contract

    def test_update_schema_contract(self) -> None:
        """Contract can be updated (for first-row locking)."""
        source = TestSource({})

        # Initial unlocked contract
        initial = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        source.set_schema_contract(initial)

        # Lock it
        locked = initial.with_field("id", "id", 1).with_locked()
        source.set_schema_contract(locked)

        assert source.get_schema_contract() is locked
        assert source.get_schema_contract().locked is True
```

**Step 5.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/plugins/test_base_source_contract.py -v
```

Expected: FAIL (BaseSource doesn't have get/set_schema_contract methods)

**Step 5.3: Add contract tracking to BaseSource**

In `src/elspeth/plugins/base.py`, update the `BaseSource` class (around line 356):

First, add import at top of file (in TYPE_CHECKING block):

```python
if TYPE_CHECKING:
    from elspeth.contracts.schema_contract import SchemaContract
    from elspeth.contracts.sink import OutputValidationResult
```

Then update `BaseSource` class:

```python
class BaseSource(ABC):
    """Base class for source plugins.

    Subclass and implement load() and close().

    Schema Contract Support (Phase 2):
        Sources can track schema contracts for row validation and dual-name access.
        Use set_schema_contract() during initialization or first-row processing,
        then get_schema_contract() to retrieve for SourceRow creation.

    Example:
        class CSVSource(BaseSource):
            name = "csv"
            output_schema = RowSchema

            def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
                with open(self.config["path"]) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        yield SourceRow.valid(row, contract=self.get_schema_contract())

            def close(self) -> None:
                pass
    """

    name: str
    output_schema: type[PluginSchema]
    node_id: str | None = None  # Set by orchestrator after registration

    # Metadata for Phase 3 audit/reproducibility
    determinism: Determinism = Determinism.IO_READ
    plugin_version: str = "0.0.0"

    # Sink name for quarantined rows, or "discard" to drop invalid rows
    # All sources must set this - config-based sources get it from SourceDataConfig
    _on_validation_failure: str

    # Schema contract for row validation (Phase 2)
    _schema_contract: "SchemaContract | None" = None

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration.

        Args:
            config: Plugin configuration
        """
        self.config = config
        self._schema_contract = None

    @abstractmethod
    def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
        """Load and yield rows from the source.

        Args:
            ctx: Plugin context

        Yields:
            SourceRow for each row - either SourceRow.valid() for rows that
            passed validation, or SourceRow.quarantined() for invalid rows.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Clean up resources."""
        ...

    # === Schema Contract Support (Phase 2) ===

    def get_schema_contract(self) -> "SchemaContract | None":
        """Get the current schema contract.

        Returns:
            SchemaContract if set, None otherwise
        """
        return self._schema_contract

    def set_schema_contract(self, contract: "SchemaContract") -> None:
        """Set or update the schema contract.

        Called during initialization for explicit schemas (FIXED/FLEXIBLE),
        or after first-row inference for OBSERVED mode.

        Args:
            contract: The schema contract to use for validation
        """
        self._schema_contract = contract

    # === Lifecycle Hooks (Phase 3) ===
    # ... (keep existing hooks)
```

**Step 5.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/plugins/test_base_source_contract.py -v
```

Expected: All tests PASS

**Step 5.5: Commit**

```bash
git add src/elspeth/plugins/base.py tests/plugins/test_base_source_contract.py
git commit -m "feat(plugins): add contract tracking to BaseSource

Add get_schema_contract() and set_schema_contract() methods.
Sources can track contracts for SourceRow creation.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: CSVSource Contract Integration

**Files:**
- Modify: `src/elspeth/plugins/sources/csv_source.py`
- Test: `tests/plugins/sources/test_csv_source_contract.py` (create new)

**Step 6.1: Write failing tests for CSVSource with contracts**

```python
# tests/plugins/sources/test_csv_source_contract.py
"""Tests for CSVSource schema contract integration."""

from pathlib import Path
from textwrap import dedent

import pytest

from elspeth.contracts.schema_contract import PipelineRow, SchemaContract
from elspeth.plugins.sources.csv_source import CSVSource
from elspeth.plugins.context import PluginContext


@pytest.fixture
def temp_csv(tmp_path: Path) -> Path:
    """Create a temporary CSV file."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(dedent("""\
        id,name,score
        1,Alice,95.5
        2,Bob,87.0
    """))
    return csv_file


@pytest.fixture
def mock_context() -> PluginContext:
    """Create a mock plugin context."""
    # Minimal context for testing - real context has more fields
    class MockContext:
        def record_validation_error(self, **kwargs: object) -> None:
            pass

    return MockContext()  # type: ignore[return-value]


class TestCSVSourceContract:
    """Test CSVSource schema contract integration."""

    def test_dynamic_schema_creates_observed_contract(
        self, temp_csv: Path, mock_context: PluginContext
    ) -> None:
        """Dynamic schema creates OBSERVED mode contract."""
        source = CSVSource({
            "path": str(temp_csv),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
        })

        rows = list(source.load(mock_context))

        # Contract should be created and locked after first row
        contract = source.get_schema_contract()
        assert contract is not None
        assert contract.mode == "OBSERVED"
        assert contract.locked is True

    def test_strict_schema_creates_fixed_contract(
        self, temp_csv: Path, mock_context: PluginContext
    ) -> None:
        """Strict schema creates FIXED mode contract."""
        source = CSVSource({
            "path": str(temp_csv),
            "schema": {
                "mode": "strict",
                "fields": ["id: int", "name: str", "score: float"],
            },
            "on_validation_failure": "quarantine",
        })

        rows = list(source.load(mock_context))

        contract = source.get_schema_contract()
        assert contract is not None
        assert contract.mode == "FIXED"

    def test_source_row_has_contract(
        self, temp_csv: Path, mock_context: PluginContext
    ) -> None:
        """Valid SourceRows include contract reference."""
        source = CSVSource({
            "path": str(temp_csv),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
        })

        rows = list(source.load(mock_context))

        for row in rows:
            if not row.is_quarantined:
                assert row.contract is not None
                assert row.contract.locked is True

    def test_source_row_converts_to_pipeline_row(
        self, temp_csv: Path, mock_context: PluginContext
    ) -> None:
        """SourceRow can convert to PipelineRow."""
        source = CSVSource({
            "path": str(temp_csv),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
        })

        rows = list(source.load(mock_context))
        source_row = rows[0]

        pipeline_row = source_row.to_pipeline_row()

        assert isinstance(pipeline_row, PipelineRow)
        assert pipeline_row["id"] == 1
        assert pipeline_row["name"] == "Alice"

    def test_contract_includes_field_resolution(
        self, tmp_path: Path, mock_context: PluginContext
    ) -> None:
        """Contract original_name populated from field resolution."""
        csv_file = tmp_path / "messy.csv"
        csv_file.write_text(dedent("""\
            'Amount USD',Customer ID
            100,C001
        """))

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
            "normalize_fields": True,
        })

        rows = list(source.load(mock_context))
        contract = source.get_schema_contract()

        # Find the amount field
        amount_field = next(
            f for f in contract.fields if f.normalized_name == "amount_usd"
        )
        assert amount_field.original_name == "'Amount USD'"

    def test_inferred_types_from_first_row(
        self, temp_csv: Path, mock_context: PluginContext
    ) -> None:
        """OBSERVED mode infers types from first row values."""
        source = CSVSource({
            "path": str(temp_csv),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "quarantine",
        })

        rows = list(source.load(mock_context))
        contract = source.get_schema_contract()

        # CSV values come through Pydantic with coercion
        # So types depend on what Pydantic coerced them to
        type_map = {f.normalized_name: f.python_type for f in contract.fields}

        # With dynamic schema, all CSV values start as strings
        # unless Pydantic schema coerces them
        assert "id" in type_map
        assert "name" in type_map
        assert "score" in type_map

    def test_empty_source_locks_contract(
        self, tmp_path: Path, mock_context: PluginContext
    ) -> None:
        """Contract is locked even if all rows are quarantined."""
        csv_file = tmp_path / "all_bad.csv"
        csv_file.write_text(dedent("""\
            id,amount
            not_int,100
            also_not_int,200
        """))

        source = CSVSource({
            "path": str(csv_file),
            "schema": {
                "mode": "strict",
                "fields": ["id: int", "amount: int"],
            },
            "on_validation_failure": "quarantine",
        })

        rows = list(source.load(mock_context))

        # All rows should be quarantined (id field not coercible to int)
        assert all(r.is_quarantined for r in rows)

        # Contract should still be locked (not left in unlocked state)
        contract = source.get_schema_contract()
        assert contract is not None
        assert contract.locked is True
```

**Step 6.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/plugins/sources/test_csv_source_contract.py -v
```

Expected: FAIL (CSVSource doesn't create contracts yet)

**Step 6.3: Update CSVSource to create and track contracts**

Update `src/elspeth/plugins/sources/csv_source.py`:

First, add imports at top:

```python
from elspeth.contracts.contract_builder import ContractBuilder
from elspeth.contracts.schema_contract_factory import create_contract_from_config
```

Then update the `__init__` method to create the initial contract:

```python
def __init__(self, config: dict[str, Any]) -> None:
    super().__init__(config)
    cfg = CSVSourceConfig.from_dict(config)

    self._path = cfg.resolved_path()
    self._delimiter = cfg.delimiter
    self._encoding = cfg.encoding
    self._skip_rows = cfg.skip_rows

    # Store normalization config for use in load()
    self._columns = cfg.columns
    self._normalize_fields = cfg.normalize_fields
    self._field_mapping = cfg.field_mapping

    # Field resolution computed at load() time - includes version for audit
    self._field_resolution: FieldResolution | None = None

    # Store schema config for audit trail (required by DataPluginConfig)
    self._schema_config = cfg.schema_config

    # Store quarantine routing destination
    self._on_validation_failure = cfg.on_validation_failure

    # CRITICAL: allow_coercion=True for sources (external data boundary)
    # Sources are the ONLY place where type coercion is allowed
    self._schema_class: type[PluginSchema] = create_schema_from_config(
        self._schema_config,
        "CSVRowSchema",
        allow_coercion=True,
    )

    # Set output_schema for protocol compliance
    self.output_schema = self._schema_class

    # Create initial schema contract (may be updated after first row)
    # Contract creation deferred until load() when field_resolution is known
    self._contract_builder: ContractBuilder | None = None
```

Then update the `load` method to create and lock the contract:

```python
def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
    """Load rows from CSV file with optional field normalization.

    ... (keep existing docstring) ...
    """
    if not self._path.exists():
        raise FileNotFoundError(f"CSV file not found: {self._path}")

    # CRITICAL: newline='' required for proper embedded newline handling
    with open(self._path, encoding=self._encoding, newline="") as f:
        # Skip header rows as configured
        for _ in range(self._skip_rows):
            next(f, None)

        reader = csv.reader(f, delimiter=self._delimiter)

        # Determine headers based on config
        if self._columns is not None:
            raw_headers = None
        else:
            try:
                raw_headers = next(reader)
            except StopIteration:
                return

        # Resolve field names (normalization + mapping)
        self._field_resolution = resolve_field_names(
            raw_headers=raw_headers,
            normalize_fields=self._normalize_fields,
            field_mapping=self._field_mapping,
            columns=self._columns,
        )
        headers = self._field_resolution.final_headers
        expected_count = len(headers)

        # Create initial contract with field resolution
        initial_contract = create_contract_from_config(
            self._schema_config,
            field_resolution=self._field_resolution.resolution_mapping,
        )
        self._contract_builder = ContractBuilder(initial_contract)

        # Track whether first valid row has been processed (for type inference)
        first_valid_row_processed = False

        # Process data rows
        row_num = 0
        while True:
            try:
                values = next(reader)
            except StopIteration:
                break
            except csv.Error as e:
                # ... (keep existing CSV error handling)
                row_num += 1
                physical_line = reader.line_num + self._skip_rows
                raw_row = {
                    "__raw_line__": "(unparseable due to csv.Error)",
                    "__line_number__": physical_line,
                    "__row_number__": row_num,
                }
                error_msg = f"CSV parse error at line {physical_line}: {e}"

                ctx.record_validation_error(
                    row=raw_row,
                    error=error_msg,
                    schema_mode="parse",
                    destination=self._on_validation_failure,
                )

                if self._on_validation_failure != "discard":
                    yield SourceRow.quarantined(
                        row=raw_row,
                        error=error_msg,
                        destination=self._on_validation_failure,
                    )
                continue

            # Skip empty rows
            if not values:
                continue

            row_num += 1
            physical_line = reader.line_num + self._skip_rows

            # Column count validation
            if len(values) != expected_count:
                # ... (keep existing column count error handling)
                raw_row = {
                    "__raw_line__": self._delimiter.join(values),
                    "__line_number__": physical_line,
                    "__row_number__": row_num,
                }
                error_msg = f"CSV parse error at line {physical_line}: expected {expected_count} fields, got {len(values)}"

                ctx.record_validation_error(
                    row=raw_row,
                    error=error_msg,
                    schema_mode="parse",
                    destination=self._on_validation_failure,
                )

                if self._on_validation_failure != "discard":
                    yield SourceRow.quarantined(
                        row=raw_row,
                        error=error_msg,
                        destination=self._on_validation_failure,
                    )
                continue

            # Build row dict
            row = dict(zip(headers, values, strict=False))

            # Validate row against Pydantic schema
            try:
                validated = self._schema_class.model_validate(row)
                validated_row = validated.to_row()

                # Process first valid row for type inference
                if not first_valid_row_processed:
                    self._contract_builder.process_first_row(
                        validated_row,
                        self._field_resolution.resolution_mapping,
                    )
                    self.set_schema_contract(self._contract_builder.contract)
                    first_valid_row_processed = True

                yield SourceRow.valid(
                    validated_row,
                    contract=self.get_schema_contract(),
                )

            except ValidationError as e:
                ctx.record_validation_error(
                    row=row,
                    error=str(e),
                    schema_mode=self._schema_config.mode or "dynamic",
                    destination=self._on_validation_failure,
                )

                if self._on_validation_failure != "discard":
                    yield SourceRow.quarantined(
                        row=row,
                        error=str(e),
                        destination=self._on_validation_failure,
                    )

        # CRITICAL: Handle empty source case (all rows quarantined or no rows)
        # If no valid rows were processed, the contract is still unlocked.
        # Lock it now so downstream consumers have a consistent contract state.
        if not first_valid_row_processed and self._contract_builder is not None:
            self.set_schema_contract(self._contract_builder.contract.with_locked())
```

**Step 6.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/plugins/sources/test_csv_source_contract.py -v
```

Expected: All tests PASS

**Step 6.5: Run existing CSVSource tests to ensure no regressions**

```bash
.venv/bin/python -m pytest tests/plugins/sources/test_csv_source.py -v
```

Expected: All tests PASS

**Step 6.6: Commit**

```bash
git add src/elspeth/plugins/sources/csv_source.py tests/plugins/sources/test_csv_source_contract.py
git commit -m "feat(csv): integrate schema contracts with CSVSource

CSVSource now:
- Creates SchemaContract from SchemaConfig at load time
- Uses ContractBuilder for first-row type inference
- Attaches contract to SourceRow.valid() calls
- Populates original_name from field resolution

OBSERVED mode locks types after first valid row.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Module Exports

**Files:**
- Modify: `src/elspeth/contracts/__init__.py`
- Test: Run all tests

**Step 7.1: Update module exports**

Add to `src/elspeth/contracts/__init__.py`:

```python
# Schema contract factory (Phase 2)
from elspeth.contracts.contract_builder import ContractBuilder
from elspeth.contracts.schema_contract_factory import (
    create_contract_from_config,
    map_schema_mode,
)
```

Update `__all__` list:

```python
__all__ = [
    # ... existing exports ...

    # Schema contract factory (Phase 2)
    "ContractBuilder",
    "create_contract_from_config",
    "map_schema_mode",
]
```

**Step 7.2: Run all contract tests**

```bash
.venv/bin/python -m pytest tests/contracts/ -v --tb=short
```

Expected: All tests PASS

**Step 7.3: Run type checker**

```bash
.venv/bin/python -m mypy src/elspeth/contracts/
```

Expected: No errors

**Step 7.4: Run linter**

```bash
.venv/bin/python -m ruff check src/elspeth/contracts/
```

Expected: No errors

**Step 7.5: Final commit**

```bash
git add src/elspeth/contracts/__init__.py
git commit -m "feat(contracts): export Phase 2 schema contract factory

Add to contracts module exports:
- ContractBuilder
- create_contract_from_config
- map_schema_mode

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Integration Test - Full Pipeline

**Files:**
- Test: `tests/integration/test_source_contract_integration.py` (create new)

**Step 8.1: Write integration test**

```python
# tests/integration/test_source_contract_integration.py
"""Integration tests for source → contract → pipeline flow."""

from pathlib import Path
from textwrap import dedent

import pytest

from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.sources.csv_source import CSVSource


class MockContext:
    """Minimal context for integration testing."""

    def __init__(self) -> None:
        self.validation_errors: list[dict] = []

    def record_validation_error(self, **kwargs: object) -> None:
        self.validation_errors.append(dict(kwargs))


class TestSourceContractIntegration:
    """End-to-end tests for source contract integration."""

    def test_dynamic_schema_infer_and_lock(self, tmp_path: Path) -> None:
        """Dynamic schema infers types from first row and locks."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(dedent("""\
            id,amount,status
            1,100,active
            2,200,inactive
            3,300,active
        """))

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "discard",
        })
        ctx = MockContext()

        rows = list(source.load(ctx))

        # All rows valid
        assert len(rows) == 3
        assert all(not r.is_quarantined for r in rows)

        # Contract locked after first row
        contract = source.get_schema_contract()
        assert contract.locked is True
        assert contract.mode == "OBSERVED"

        # All rows have same contract
        for row in rows:
            assert row.contract is contract

    def test_dual_name_access(self, tmp_path: Path) -> None:
        """PipelineRow supports dual-name access."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(dedent("""\
            'Amount USD',Customer ID
            100,C001
        """))

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "discard",
            "normalize_fields": True,
        })
        ctx = MockContext()

        rows = list(source.load(ctx))
        pipeline_row = rows[0].to_pipeline_row()

        # Access by normalized name
        assert pipeline_row["amount_usd"] == "100"
        assert pipeline_row.amount_usd == "100"

        # Access by original name
        assert pipeline_row["'Amount USD'"] == "100"

    def test_strict_schema_validation(self, tmp_path: Path) -> None:
        """Strict schema validates and quarantines bad rows."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(dedent("""\
            id,amount
            1,100
            two,200
            3,300
        """))

        source = CSVSource({
            "path": str(csv_file),
            "schema": {
                "mode": "strict",
                "fields": ["id: int", "amount: int"],
            },
            "on_validation_failure": "quarantine",
        })
        ctx = MockContext()

        rows = list(source.load(ctx))

        # Row 2 quarantined (id "two" not int)
        valid_rows = [r for r in rows if not r.is_quarantined]
        quarantined_rows = [r for r in rows if r.is_quarantined]

        assert len(valid_rows) == 2
        assert len(quarantined_rows) == 1

        # Quarantined row has no contract
        assert quarantined_rows[0].contract is None

    def test_contract_survives_checkpoint_round_trip(self, tmp_path: Path) -> None:
        """Contract can serialize for checkpoints."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(dedent("""\
            id,name
            1,Alice
        """))

        source = CSVSource({
            "path": str(csv_file),
            "schema": {"fields": "dynamic"},
            "on_validation_failure": "discard",
        })
        ctx = MockContext()

        rows = list(source.load(ctx))
        contract = source.get_schema_contract()

        # Serialize and restore
        from elspeth.contracts.schema_contract import SchemaContract

        checkpoint_data = contract.to_checkpoint_format()
        restored = SchemaContract.from_checkpoint(checkpoint_data)

        # Verify integrity
        assert restored.mode == contract.mode
        assert restored.locked == contract.locked
        assert len(restored.fields) == len(contract.fields)
```

**Step 8.2: Run integration tests**

```bash
.venv/bin/python -m pytest tests/integration/test_source_contract_integration.py -v
```

Expected: All tests PASS

**Step 8.3: Commit**

```bash
git add tests/integration/test_source_contract_integration.py
git commit -m "test(integration): add source contract integration tests

End-to-end tests for:
- Dynamic schema infer-and-lock
- Dual-name access via PipelineRow
- Strict schema validation
- Contract checkpoint serialization

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Update Beads and Sync

**Step 9.1: Update beads issue**

```bash
bd update elspeth-rapid-0ax --status=completed
bd sync
```

---

## Summary

Phase 2 implementation integrates schema contracts with source plugins:

| Component | Purpose |
|-----------|---------|
| `schema_contract_factory.py` | Create `SchemaContract` from `SchemaConfig` |
| `contract_builder.py` | First-row type inference and locking |
| `SourceRow.contract` | Attach contract to valid rows |
| `BaseSource.get/set_schema_contract()` | Contract tracking on sources |
| `CSVSource` integration | Full contract support |

**Key patterns:**
- Schema mode mapping: strict→FIXED, free→FLEXIBLE, dynamic→OBSERVED
- First-row locking for OBSERVED/FLEXIBLE modes
- Field resolution populates `original_name` on `FieldContract`
- `SourceRow.to_pipeline_row()` converts to `PipelineRow`

**Next:** Phase 3 integrates contracts with transforms and sinks.
