# Phase 1: Core Contracts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the foundational `FieldContract`, `SchemaContract`, and `PipelineRow` classes that preserve type information and enable dual-name field access through the pipeline.

**Architecture:** Frozen dataclass pattern for immutability (matches existing `RuntimeRetryConfig` and `FieldDefinition`). All "mutations" return new instances. O(1) name resolution via precomputed indices. Type normalization follows `canonical.py` patterns with `isinstance()` checks.

**Tech Stack:** Python 3.11+, dataclasses (frozen), hashlib for version hashes, existing `canonical_json()` for deterministic serialization.

**Design Doc:** `docs/plans/2026-02-02-unified-schema-contracts-design.md`

**Beads Issue:** `elspeth-rapid-0ax`

---

## Task 1: Contract Violation Types

**Files:**
- Modify: `src/elspeth/contracts/errors.py` (add new exception types at end)
- Test: `tests/contracts/test_contract_violations.py` (create new)

**Step 1.1: Write failing tests for violation types**

```python
# tests/contracts/test_contract_violations.py
"""Tests for schema contract violation types."""

import pytest

from elspeth.contracts.errors import (
    ContractMergeError,
    ContractViolation,
    ExtraFieldViolation,
    MissingFieldViolation,
    TypeMismatchViolation,
)


class TestContractViolation:
    """Test base ContractViolation class."""

    def test_contract_violation_is_exception(self) -> None:
        """ContractViolation is an Exception subclass."""
        assert issubclass(ContractViolation, Exception)

    def test_contract_violation_has_field_name(self) -> None:
        """ContractViolation stores field information."""
        violation = MissingFieldViolation(
            normalized_name="amount",
            original_name="'Amount USD'",
        )
        assert violation.normalized_name == "amount"
        assert violation.original_name == "'Amount USD'"


class TestMissingFieldViolation:
    """Test MissingFieldViolation."""

    def test_message_format(self) -> None:
        """Error message shows both names: 'original' (normalized)."""
        violation = MissingFieldViolation(
            normalized_name="amount_usd",
            original_name="'Amount USD'",
        )
        msg = str(violation)
        assert "'Amount USD'" in msg
        assert "amount_usd" in msg
        assert "missing" in msg.lower() or "required" in msg.lower()


class TestTypeMismatchViolation:
    """Test TypeMismatchViolation."""

    def test_stores_type_info(self) -> None:
        """TypeMismatchViolation stores expected and actual types."""
        violation = TypeMismatchViolation(
            normalized_name="amount",
            original_name="'Amount'",
            expected_type=int,
            actual_type=str,
            actual_value="not_a_number",
        )
        assert violation.expected_type is int
        assert violation.actual_type is str
        assert violation.actual_value == "not_a_number"

    def test_message_format(self) -> None:
        """Error message includes type information."""
        violation = TypeMismatchViolation(
            normalized_name="amount",
            original_name="'Amount'",
            expected_type=int,
            actual_type=str,
            actual_value="hello",
        )
        msg = str(violation)
        assert "int" in msg
        assert "str" in msg
        assert "'Amount'" in msg


class TestExtraFieldViolation:
    """Test ExtraFieldViolation for FIXED mode."""

    def test_message_mentions_fixed_mode(self) -> None:
        """Error message indicates FIXED mode rejects extras."""
        violation = ExtraFieldViolation(
            normalized_name="unexpected_field",
            original_name="Unexpected Field",
        )
        msg = str(violation)
        assert "unexpected_field" in msg or "Unexpected Field" in msg


class TestContractMergeError:
    """Test ContractMergeError for fork/join failures."""

    def test_is_value_error(self) -> None:
        """ContractMergeError is ValueError subclass."""
        assert issubclass(ContractMergeError, ValueError)

    def test_message_includes_field_and_types(self) -> None:
        """Error message shows conflicting types."""
        error = ContractMergeError(
            normalized_name="score",
            original_name="'Score'",
            type_a=int,
            type_b=str,
        )
        msg = str(error)
        assert "score" in msg or "Score" in msg
        assert "int" in msg
        assert "str" in msg
```

**Step 1.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_contract_violations.py -v
```

Expected: FAIL with `ImportError: cannot import name 'ContractViolation'`

**Step 1.3: Implement violation types**

Add to `src/elspeth/contracts/errors.py` (at end of file):

```python
# =============================================================================
# Schema Contract Violations
# =============================================================================


class ContractViolation(Exception):
    """Base class for schema contract violations.

    Contract violations occur when row data doesn't match the schema contract.
    These are data issues (Tier 3 external data) that result in quarantine,
    not system errors.

    Attributes:
        normalized_name: The internal field name (Python identifier)
        original_name: The display name (what user sees in source data)
    """

    def __init__(self, normalized_name: str, original_name: str) -> None:
        self.normalized_name = normalized_name
        self.original_name = original_name
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format error message with both names."""
        return f"Contract violation on field '{self.original_name}' ({self.normalized_name})"


class MissingFieldViolation(ContractViolation):
    """Raised when a required field is missing from row data.

    This is a data quality issue, not a system error. The row will be
    quarantined with this violation recorded.
    """

    def _format_message(self) -> str:
        return f"Required field '{self.original_name}' ({self.normalized_name}) is missing"


class TypeMismatchViolation(ContractViolation):
    """Raised when a field value has wrong type.

    This occurs when:
    - FIXED/FLEXIBLE: Value doesn't match declared type
    - OBSERVED: Value doesn't match type inferred from first row

    Attributes:
        expected_type: The type declared or inferred in the contract
        actual_type: The actual type of the value
        actual_value: The problematic value (for debugging)
    """

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


class ExtraFieldViolation(ContractViolation):
    """Raised when FIXED mode schema receives unexpected field.

    FIXED mode rejects any fields not declared in the schema.
    Use FLEXIBLE mode if you want to allow extra fields.
    """

    def _format_message(self) -> str:
        return (
            f"Extra field '{self.original_name}' ({self.normalized_name}) "
            f"not allowed in FIXED mode schema"
        )


class ContractMergeError(ValueError):
    """Raised when contracts cannot be merged at coalesce point.

    This occurs when parallel DAG paths produce incompatible schemas
    that cannot be safely merged. This is a pipeline design error,
    not a data quality issue.

    Attributes:
        normalized_name: Field with conflicting types
        original_name: Display name for the field
        type_a: Type from first path
        type_b: Type from second path
    """

    def __init__(
        self,
        normalized_name: str,
        original_name: str,
        type_a: type,
        type_b: type,
    ) -> None:
        self.normalized_name = normalized_name
        self.original_name = original_name
        self.type_a = type_a
        self.type_b = type_b
        super().__init__(
            f"Type mismatch at coalesce: '{original_name}' ({normalized_name}) "
            f"has type {type_a.__name__} in one path, {type_b.__name__} in another"
        )
```

Also add `Any` to the imports at top of file:

```python
from typing import Any, Literal, NotRequired, TypedDict
```

**Step 1.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_contract_violations.py -v
```

Expected: All tests PASS

**Step 1.5: Commit**

```bash
git add src/elspeth/contracts/errors.py tests/contracts/test_contract_violations.py
git commit -m "feat(contracts): add schema contract violation types

Add ContractViolation base class and specific violation types:
- MissingFieldViolation: required field not present
- TypeMismatchViolation: value has wrong type
- ExtraFieldViolation: FIXED mode rejects unexpected field
- ContractMergeError: fork/join paths have incompatible types

Error messages follow 'original' (normalized) format for debuggability.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Type Normalization Utility

**Files:**
- Create: `src/elspeth/contracts/type_normalization.py`
- Test: `tests/contracts/test_type_normalization.py` (create new)

**Step 2.1: Write failing tests for type normalization**

```python
# tests/contracts/test_type_normalization.py
"""Tests for type normalization (numpy/pandas -> Python primitives)."""

import math
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from elspeth.contracts.type_normalization import normalize_type_for_contract


class TestNormalizeTypeForContract:
    """Test _normalize_type_for_contract function."""

    # === Python primitives pass through ===

    def test_none_returns_nonetype(self) -> None:
        """None normalizes to type(None)."""
        assert normalize_type_for_contract(None) is type(None)

    def test_int_returns_int(self) -> None:
        """Python int returns int."""
        assert normalize_type_for_contract(42) is int

    def test_str_returns_str(self) -> None:
        """Python str returns str."""
        assert normalize_type_for_contract("hello") is str

    def test_float_returns_float(self) -> None:
        """Python float returns float."""
        assert normalize_type_for_contract(3.14) is float

    def test_bool_returns_bool(self) -> None:
        """Python bool returns bool."""
        assert normalize_type_for_contract(True) is bool

    # === NumPy types normalize to primitives ===

    def test_numpy_int64_returns_int(self) -> None:
        """numpy.int64 normalizes to int."""
        assert normalize_type_for_contract(np.int64(42)) is int

    def test_numpy_int32_returns_int(self) -> None:
        """numpy.int32 normalizes to int."""
        assert normalize_type_for_contract(np.int32(42)) is int

    def test_numpy_float64_returns_float(self) -> None:
        """numpy.float64 normalizes to float."""
        assert normalize_type_for_contract(np.float64(3.14)) is float

    def test_numpy_float32_returns_float(self) -> None:
        """numpy.float32 normalizes to float."""
        assert normalize_type_for_contract(np.float32(3.14)) is float

    def test_numpy_bool_returns_bool(self) -> None:
        """numpy.bool_ normalizes to bool."""
        assert normalize_type_for_contract(np.bool_(True)) is bool

    # === Pandas types normalize to primitives ===

    def test_pandas_timestamp_returns_datetime(self) -> None:
        """pandas.Timestamp normalizes to datetime."""
        assert normalize_type_for_contract(pd.Timestamp("2024-01-01")) is datetime

    def test_numpy_datetime64_returns_datetime(self) -> None:
        """numpy.datetime64 normalizes to datetime."""
        assert normalize_type_for_contract(np.datetime64("2024-01-01")) is datetime

    # === NaN/Infinity rejection ===

    def test_float_nan_raises_valueerror(self) -> None:
        """Python float NaN is rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(float("nan"))

    def test_float_infinity_raises_valueerror(self) -> None:
        """Python float infinity is rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(float("inf"))

    def test_numpy_nan_raises_valueerror(self) -> None:
        """numpy.nan is rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(np.nan)

    def test_numpy_inf_raises_valueerror(self) -> None:
        """numpy.inf is rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(np.inf)

    def test_negative_infinity_raises_valueerror(self) -> None:
        """Negative infinity is also rejected."""
        with pytest.raises(ValueError, match="non-finite"):
            normalize_type_for_contract(float("-inf"))

    # === Unknown types pass through ===

    def test_list_returns_list(self) -> None:
        """List type passes through (for complex fields)."""
        assert normalize_type_for_contract([1, 2, 3]) is list

    def test_dict_returns_dict(self) -> None:
        """Dict type passes through."""
        assert normalize_type_for_contract({"a": 1}) is dict
```

**Step 2.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_type_normalization.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'elspeth.contracts.type_normalization'`

**Step 2.3: Implement type normalization**

```python
# src/elspeth/contracts/type_normalization.py
"""Type normalization for schema contracts.

Converts numpy/pandas types to Python primitives for consistent
contract storage and validation. This ensures type comparisons
work correctly regardless of whether data came from pandas DataFrames,
numpy arrays, or native Python objects.

Per CLAUDE.md: Uses isinstance() checks (not string matching on __name__),
which is the Pythonic pattern established in canonical.py.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


def normalize_type_for_contract(value: Any) -> type:
    """Convert value's type to Python primitive for contract storage.

    This is critical because `type(numpy.int64(42))` returns `numpy.int64`,
    not `int`. Contracts must store primitive types for consistent validation.

    Args:
        value: Any Python value

    Returns:
        Python primitive type (int, str, float, bool, datetime, type(None))
        or the original type for unknown types

    Raises:
        ValueError: If value is NaN or Infinity (invalid for audit trail)

    Example:
        >>> normalize_type_for_contract(np.int64(42))
        <class 'int'>
        >>> normalize_type_for_contract(pd.Timestamp("2024-01-01"))
        <class 'datetime.datetime'>
    """
    if value is None:
        return type(None)  # NoneType

    # CRITICAL: Reject NaN/Infinity before type inference (Tier 1 audit integrity)
    # Per CLAUDE.md: "NaN and Infinity are strictly rejected, not silently converted"
    if isinstance(value, (float, np.floating)):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(
                f"Cannot infer type from non-finite float: {value}. "
                f"NaN/Infinity are invalid in audit trail. Use None for missing values."
            )

    # Use isinstance() checks - Pythonic pattern per canonical.py
    # String matching on __name__ is fragile and bug-hiding
    if isinstance(value, np.integer):
        return int
    if isinstance(value, np.floating):
        return float
    if isinstance(value, np.bool_):
        return bool
    if isinstance(value, pd.Timestamp):
        return datetime
    if isinstance(value, np.datetime64):
        return datetime
    if isinstance(value, (np.str_, np.bytes_)):
        return str

    # Already a primitive or unknown type - return as-is
    return type(value)
```

**Step 2.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_type_normalization.py -v
```

Expected: All tests PASS

**Step 2.5: Commit**

```bash
git add src/elspeth/contracts/type_normalization.py tests/contracts/test_type_normalization.py
git commit -m "feat(contracts): add type normalization for schema contracts

Converts numpy/pandas types to Python primitives for consistent
contract storage. Uses isinstance() checks per canonical.py pattern.

Rejects NaN/Infinity per Tier 1 audit integrity requirements.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: FieldContract Dataclass

**Files:**
- Create: `src/elspeth/contracts/schema_contract.py`
- Test: `tests/contracts/test_field_contract.py` (create new)

**Step 3.1: Write failing tests for FieldContract**

```python
# tests/contracts/test_field_contract.py
"""Tests for FieldContract dataclass."""

from typing import Literal

import pytest

from elspeth.contracts.schema_contract import FieldContract


class TestFieldContract:
    """Test FieldContract frozen dataclass."""

    def test_create_declared_field(self) -> None:
        """Create a declared (config-time) field contract."""
        fc = FieldContract(
            normalized_name="amount_usd",
            original_name="'Amount USD'",
            python_type=int,
            required=True,
            source="declared",
        )
        assert fc.normalized_name == "amount_usd"
        assert fc.original_name == "'Amount USD'"
        assert fc.python_type is int
        assert fc.required is True
        assert fc.source == "declared"

    def test_create_inferred_field(self) -> None:
        """Create an inferred (runtime) field contract."""
        fc = FieldContract(
            normalized_name="extra_field",
            original_name="Extra Field",
            python_type=str,
            required=False,
            source="inferred",
        )
        assert fc.source == "inferred"
        assert fc.required is False

    def test_frozen_immutable(self) -> None:
        """FieldContract is frozen (immutable)."""
        fc = FieldContract(
            normalized_name="x",
            original_name="x",
            python_type=int,
            required=True,
            source="declared",
        )
        with pytest.raises(AttributeError):
            fc.normalized_name = "y"  # type: ignore[misc]

    def test_slots_enabled(self) -> None:
        """FieldContract uses __slots__ for memory efficiency."""
        fc = FieldContract(
            normalized_name="x",
            original_name="x",
            python_type=int,
            required=True,
            source="declared",
        )
        # slots=True means no __dict__
        assert not hasattr(fc, "__dict__")

    def test_equality(self) -> None:
        """Two FieldContracts with same values are equal."""
        fc1 = FieldContract("a", "A", int, True, "declared")
        fc2 = FieldContract("a", "A", int, True, "declared")
        assert fc1 == fc2

    def test_hashable(self) -> None:
        """FieldContract is hashable (can be used in sets/dict keys)."""
        fc = FieldContract("a", "A", int, True, "declared")
        # Should not raise
        hash(fc)
        {fc}  # Can be added to set

    def test_source_literal_type(self) -> None:
        """Source must be 'declared' or 'inferred'."""
        # This is a type check - at runtime both work
        fc1 = FieldContract("a", "A", int, True, "declared")
        fc2 = FieldContract("b", "B", str, False, "inferred")
        assert fc1.source in ("declared", "inferred")
        assert fc2.source in ("declared", "inferred")
```

**Step 3.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_field_contract.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'elspeth.contracts.schema_contract'`

**Step 3.3: Implement FieldContract**

```python
# src/elspeth/contracts/schema_contract.py
"""Schema contracts for preserving type and name information through the pipeline.

This module implements the Unified Schema Contracts design:
- FieldContract: Immutable field metadata (normalized name, original name, type)
- SchemaContract: Per-node schema with O(1) name resolution
- PipelineRow: Row wrapper enabling dual-name access

Design doc: docs/plans/2026-02-02-unified-schema-contracts-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    pass  # Forward references if needed


@dataclass(frozen=True, slots=True)
class FieldContract:
    """A field in the schema contract.

    Immutable after creation - type locking means no mutation.
    Uses frozen dataclass pattern for checkpoint safety.

    Attributes:
        normalized_name: Dict key / Python identifier (e.g., "important_data")
        original_name: Display name from source (e.g., "'Important - Data !!'")
        python_type: Python primitive type (int, str, float, bool, datetime, type(None))
        required: Whether field must be present in row
        source: "declared" (from config) or "inferred" (from first row observation)

    Example:
        >>> fc = FieldContract(
        ...     normalized_name="amount_usd",
        ...     original_name="'Amount USD'",
        ...     python_type=int,
        ...     required=True,
        ...     source="declared",
        ... )
    """

    normalized_name: str
    original_name: str
    python_type: type
    required: bool
    source: Literal["declared", "inferred"]
```

**Step 3.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_field_contract.py -v
```

Expected: All tests PASS

**Step 3.5: Commit**

```bash
git add src/elspeth/contracts/schema_contract.py tests/contracts/test_field_contract.py
git commit -m "feat(contracts): add FieldContract frozen dataclass

Immutable field metadata for schema contracts. Stores:
- normalized_name: Python identifier for dict access
- original_name: Display name from source data
- python_type: Primitive type for validation
- required: Whether field must be present
- source: 'declared' or 'inferred'

Uses frozen=True, slots=True for immutability and efficiency.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: SchemaContract - Core Structure

**Files:**
- Modify: `src/elspeth/contracts/schema_contract.py`
- Test: `tests/contracts/test_schema_contract.py` (create new)

**Step 4.1: Write failing tests for SchemaContract creation and name resolution**

```python
# tests/contracts/test_schema_contract.py
"""Tests for SchemaContract dataclass."""

import pytest

from elspeth.contracts.schema_contract import FieldContract, SchemaContract


class TestSchemaContractCreation:
    """Test SchemaContract creation and basic properties."""

    def test_create_fixed_mode(self) -> None:
        """Create FIXED mode contract."""
        fc = FieldContract("id", "id", int, True, "declared")
        contract = SchemaContract(
            mode="FIXED",
            fields=(fc,),
            locked=True,
        )
        assert contract.mode == "FIXED"
        assert len(contract.fields) == 1
        assert contract.locked is True

    def test_create_flexible_mode(self) -> None:
        """Create FLEXIBLE mode contract."""
        contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(),
            locked=False,
        )
        assert contract.mode == "FLEXIBLE"
        assert contract.locked is False

    def test_create_observed_mode(self) -> None:
        """Create OBSERVED mode contract."""
        contract = SchemaContract(
            mode="OBSERVED",
            fields=(),
            locked=False,
        )
        assert contract.mode == "OBSERVED"

    def test_frozen_immutable(self) -> None:
        """SchemaContract is frozen (core fields immutable)."""
        contract = SchemaContract(mode="FIXED", fields=(), locked=True)
        with pytest.raises(AttributeError):
            contract.mode = "FLEXIBLE"  # type: ignore[misc]

    def test_default_locked_false(self) -> None:
        """locked defaults to False."""
        contract = SchemaContract(mode="OBSERVED", fields=())
        assert contract.locked is False


class TestSchemaContractNameResolution:
    """Test O(1) name resolution for dual-name access."""

    @pytest.fixture
    def contract_with_fields(self) -> SchemaContract:
        """Contract with test fields."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount_usd", "'Amount USD'", int, True, "declared"),
                FieldContract("customer_id", "Customer ID", str, True, "declared"),
            ),
            locked=True,
        )

    def test_resolve_normalized_name(self, contract_with_fields: SchemaContract) -> None:
        """Resolving normalized name returns itself."""
        result = contract_with_fields.resolve_name("amount_usd")
        assert result == "amount_usd"

    def test_resolve_original_name(self, contract_with_fields: SchemaContract) -> None:
        """Resolving original name returns normalized name."""
        result = contract_with_fields.resolve_name("'Amount USD'")
        assert result == "amount_usd"

    def test_resolve_unknown_raises_keyerror(self, contract_with_fields: SchemaContract) -> None:
        """Unknown name raises KeyError."""
        with pytest.raises(KeyError, match="nonexistent"):
            contract_with_fields.resolve_name("nonexistent")

    def test_resolution_is_o1(self, contract_with_fields: SchemaContract) -> None:
        """Name resolution uses dict lookup (O(1)), not iteration."""
        # Verify indices are populated (implementation detail check)
        assert "amount_usd" in contract_with_fields._by_normalized
        assert "'Amount USD'" in contract_with_fields._by_original

    def test_get_field_by_normalized(self, contract_with_fields: SchemaContract) -> None:
        """Can retrieve FieldContract by normalized name."""
        fc = contract_with_fields.get_field("amount_usd")
        assert fc is not None
        assert fc.normalized_name == "amount_usd"
        assert fc.original_name == "'Amount USD'"

    def test_get_field_unknown_returns_none(self, contract_with_fields: SchemaContract) -> None:
        """get_field returns None for unknown fields."""
        assert contract_with_fields.get_field("nonexistent") is None
```

**Step 4.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract.py -v
```

Expected: FAIL with `ImportError: cannot import name 'SchemaContract'`

**Step 4.3: Implement SchemaContract core structure**

Add to `src/elspeth/contracts/schema_contract.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SchemaContract:
    """Immutable schema contract for a node.

    Uses frozen dataclass pattern - all "mutations" return new instances.
    This ensures contracts are safe to share across checkpoint boundaries.

    Attributes:
        mode: Schema enforcement mode
            - FIXED: Exact fields only, extras rejected
            - FLEXIBLE: Declared minimum + inferred extras allowed
            - OBSERVED: All fields observed/inferred from data
        fields: Immutable tuple of FieldContract instances
        locked: True after first row processed (types frozen)

    Name Resolution:
        The contract maintains O(1) lookup indices for dual-name access.
        Both original names (from source) and normalized names work.

    Example:
        >>> contract = SchemaContract(
        ...     mode="FLEXIBLE",
        ...     fields=(FieldContract("id", "ID", int, True, "declared"),),
        ...     locked=False,
        ... )
        >>> contract.resolve_name("ID")  # Original name
        'id'
        >>> contract.resolve_name("id")  # Normalized name
        'id'
    """

    mode: Literal["FIXED", "FLEXIBLE", "OBSERVED"]
    fields: tuple[FieldContract, ...]
    locked: bool = False

    # Computed indices - populated in __post_init__
    # Using field() with default_factory for frozen dataclass compatibility
    _by_normalized: dict[str, FieldContract] = field(
        default_factory=dict, repr=False, compare=False, hash=False
    )
    _by_original: dict[str, str] = field(
        default_factory=dict, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        """Build O(1) lookup indices after initialization.

        Uses object.__setattr__ to bypass frozen restriction for
        computed fields. This is the standard pattern for frozen
        dataclasses with computed attributes.
        """
        by_norm = {fc.normalized_name: fc for fc in self.fields}
        by_orig = {fc.original_name: fc.normalized_name for fc in self.fields}
        object.__setattr__(self, "_by_normalized", by_norm)
        object.__setattr__(self, "_by_original", by_orig)

    def resolve_name(self, key: str) -> str:
        """Resolve original or normalized name to normalized name.

        O(1) lookup via precomputed indices.
        Enables dual-name access: both original and normalized names work.

        Args:
            key: Field name (either original or normalized)

        Returns:
            Normalized field name

        Raises:
            KeyError: If name not found in contract
        """
        if key in self._by_normalized:
            return key  # Already normalized
        if key in self._by_original:
            return self._by_original[key]
        raise KeyError(f"'{key}' not found in schema contract")

    def get_field(self, normalized_name: str) -> FieldContract | None:
        """Get FieldContract by normalized name.

        Args:
            normalized_name: The normalized field name

        Returns:
            FieldContract if found, None otherwise
        """
        return self._by_normalized.get(normalized_name)
```

Update imports at top:

```python
from dataclasses import dataclass, field
```

**Step 4.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract.py -v
```

Expected: All tests PASS

**Step 4.5: Commit**

```bash
git add src/elspeth/contracts/schema_contract.py tests/contracts/test_schema_contract.py
git commit -m "feat(contracts): add SchemaContract with O(1) name resolution

SchemaContract stores per-node schema with three modes:
- FIXED: Exact fields only
- FLEXIBLE: Declared minimum + extras
- OBSERVED: All fields inferred

Includes O(1) dual-name resolution via precomputed indices.
resolve_name() accepts both original and normalized names.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: SchemaContract - Mutation Methods

**Files:**
- Modify: `src/elspeth/contracts/schema_contract.py`
- Test: `tests/contracts/test_schema_contract.py` (extend)

**Step 5.1: Write failing tests for with_field and with_locked**

Add to `tests/contracts/test_schema_contract.py`:

```python
import numpy as np
from datetime import datetime


class TestSchemaContractMutation:
    """Test immutable 'mutation' methods that return new instances."""

    def test_with_locked_returns_new_instance(self) -> None:
        """with_locked() returns new contract with locked=True."""
        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        locked = original.with_locked()

        assert locked.locked is True
        assert original.locked is False  # Original unchanged
        assert locked is not original

    def test_with_locked_preserves_fields(self) -> None:
        """with_locked() preserves all fields."""
        fc = FieldContract("x", "X", int, True, "declared")
        original = SchemaContract(mode="FLEXIBLE", fields=(fc,), locked=False)
        locked = original.with_locked()

        assert locked.fields == original.fields
        assert locked.mode == original.mode

    def test_with_field_adds_inferred_field(self) -> None:
        """with_field() adds new inferred field to contract."""
        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        updated = original.with_field("amount", "'Amount'", 100)

        assert len(updated.fields) == 1
        assert updated.fields[0].normalized_name == "amount"
        assert updated.fields[0].original_name == "'Amount'"
        assert updated.fields[0].python_type is int
        assert updated.fields[0].source == "inferred"
        assert updated.fields[0].required is False

    def test_with_field_normalizes_numpy_type(self) -> None:
        """with_field() normalizes numpy.int64 to int."""
        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        updated = original.with_field("count", "Count", np.int64(42))

        assert updated.fields[0].python_type is int  # Not numpy.int64

    def test_with_field_normalizes_pandas_timestamp(self) -> None:
        """with_field() normalizes pandas.Timestamp to datetime."""
        import pandas as pd

        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        updated = original.with_field("ts", "Timestamp", pd.Timestamp("2024-01-01"))

        assert updated.fields[0].python_type is datetime

    def test_with_field_rejects_nan(self) -> None:
        """with_field() rejects NaN values."""
        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)

        with pytest.raises(ValueError, match="non-finite"):
            original.with_field("bad", "Bad", float("nan"))

    def test_with_field_locked_rejects_existing(self) -> None:
        """with_field() raises if field already exists and contract is locked."""
        fc = FieldContract("amount", "'Amount'", int, True, "declared")
        locked = SchemaContract(mode="FLEXIBLE", fields=(fc,), locked=True)

        with pytest.raises(TypeError, match="already locked"):
            locked.with_field("amount", "'Amount'", 200)

    def test_with_field_unlocked_allows_update(self) -> None:
        """with_field() allows adding fields when not locked."""
        fc = FieldContract("a", "A", int, True, "declared")
        unlocked = SchemaContract(mode="FLEXIBLE", fields=(fc,), locked=False)

        # Can add new field
        updated = unlocked.with_field("b", "B", "hello")
        assert len(updated.fields) == 2

    def test_with_field_updates_indices(self) -> None:
        """with_field() updates name resolution indices."""
        original = SchemaContract(mode="OBSERVED", fields=(), locked=False)
        updated = original.with_field("amount", "'Amount USD'", 100)

        # Both names should resolve
        assert updated.resolve_name("amount") == "amount"
        assert updated.resolve_name("'Amount USD'") == "amount"
```

**Step 5.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract.py::TestSchemaContractMutation -v
```

Expected: FAIL with `AttributeError: 'SchemaContract' object has no attribute 'with_locked'`

**Step 5.3: Implement mutation methods**

Add to `SchemaContract` class in `src/elspeth/contracts/schema_contract.py`:

```python
from elspeth.contracts.type_normalization import normalize_type_for_contract

# In SchemaContract class:

    def with_locked(self) -> SchemaContract:
        """Return new contract with locked=True.

        Once locked, types are frozen and cannot be changed.
        This is called after the first row is processed.

        Returns:
            New SchemaContract instance with locked=True
        """
        return SchemaContract(
            mode=self.mode,
            fields=self.fields,
            locked=True,
        )

    def with_field(
        self,
        normalized: str,
        original: str,
        value: Any,
    ) -> SchemaContract:
        """Return new contract with inferred field added.

        Called for OBSERVED/FLEXIBLE extras on first row.
        Returns new instance (frozen pattern).

        Args:
            normalized: Normalized field name (Python identifier)
            original: Original field name (from source)
            value: Sample value for type inference

        Returns:
            New SchemaContract with field added

        Raises:
            TypeError: If field exists and contract is locked
            ValueError: If value is NaN or Infinity
        """
        if self.locked and normalized in self._by_normalized:
            raise TypeError(f"Field '{original}' ({normalized}) already locked")

        new_field = FieldContract(
            normalized_name=normalized,
            original_name=original,
            python_type=normalize_type_for_contract(value),
            required=False,  # Inferred fields are never required
            source="inferred",
        )
        return SchemaContract(
            mode=self.mode,
            fields=self.fields + (new_field,),
            locked=self.locked,
        )
```

Add import at top:

```python
from elspeth.contracts.type_normalization import normalize_type_for_contract
```

**Step 5.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract.py::TestSchemaContractMutation -v
```

Expected: All tests PASS

**Step 5.5: Commit**

```bash
git add src/elspeth/contracts/schema_contract.py tests/contracts/test_schema_contract.py
git commit -m "feat(contracts): add SchemaContract mutation methods

Add with_locked() and with_field() that return new instances:
- with_locked(): Freezes types after first row
- with_field(): Adds inferred field with normalized type

Type normalization converts numpy/pandas to primitives.
Rejects NaN/Infinity per audit integrity requirements.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: SchemaContract - Validation

**Files:**
- Modify: `src/elspeth/contracts/schema_contract.py`
- Test: `tests/contracts/test_schema_contract.py` (extend)

**Step 6.1: Write failing tests for validate method**

Add to `tests/contracts/test_schema_contract.py`:

```python
from elspeth.contracts.errors import (
    MissingFieldViolation,
    TypeMismatchViolation,
    ExtraFieldViolation,
)


class TestSchemaContractValidation:
    """Test contract validation."""

    def test_validate_valid_row_returns_empty(self) -> None:
        """Valid row returns empty violations list."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({"id": 42})
        assert violations == []

    def test_validate_missing_required_field(self) -> None:
        """Missing required field returns MissingFieldViolation."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({})

        assert len(violations) == 1
        assert isinstance(violations[0], MissingFieldViolation)
        assert violations[0].normalized_name == "id"

    def test_validate_optional_field_can_be_missing(self) -> None:
        """Optional field (required=False) can be missing."""
        contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("note", "Note", str, False, "declared"),),
            locked=True,
        )
        violations = contract.validate({})
        assert violations == []

    def test_validate_type_mismatch(self) -> None:
        """Wrong type returns TypeMismatchViolation."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({"id": "not_an_int"})

        assert len(violations) == 1
        assert isinstance(violations[0], TypeMismatchViolation)
        assert violations[0].expected_type is int
        assert violations[0].actual_type is str

    def test_validate_numpy_type_matches_primitive(self) -> None:
        """numpy.int64 value matches int contract type."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("count", "Count", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({"count": np.int64(42)})
        assert violations == []  # np.int64 normalizes to int

    def test_validate_none_matches_nonetype(self) -> None:
        """None value matches type(None) contract."""
        contract = SchemaContract(
            mode="OBSERVED",
            fields=(FieldContract("x", "X", type(None), False, "inferred"),),
            locked=True,
        )
        violations = contract.validate({"x": None})
        assert violations == []

    def test_validate_fixed_rejects_extras(self) -> None:
        """FIXED mode rejects extra fields."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({"id": 1, "extra": "field"})

        assert len(violations) == 1
        assert isinstance(violations[0], ExtraFieldViolation)
        assert violations[0].normalized_name == "extra"

    def test_validate_flexible_allows_extras(self) -> None:
        """FLEXIBLE mode allows extra fields (returns no violation)."""
        contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        violations = contract.validate({"id": 1, "extra": "field"})
        assert violations == []

    def test_validate_observed_allows_extras(self) -> None:
        """OBSERVED mode allows extra fields."""
        contract = SchemaContract(
            mode="OBSERVED",
            fields=(),
            locked=True,
        )
        violations = contract.validate({"anything": "goes"})
        assert violations == []

    def test_validate_multiple_violations(self) -> None:
        """Multiple problems return multiple violations."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract("a", "A", int, True, "declared"),
                FieldContract("b", "B", str, True, "declared"),
            ),
            locked=True,
        )
        violations = contract.validate({"a": "wrong_type"})  # Missing b, wrong type a

        assert len(violations) == 2
        types = {type(v) for v in violations}
        assert MissingFieldViolation in types
        assert TypeMismatchViolation in types
```

**Step 6.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract.py::TestSchemaContractValidation -v
```

Expected: FAIL with `AttributeError: 'SchemaContract' object has no attribute 'validate'`

**Step 6.3: Implement validate method**

Add to `SchemaContract` class:

```python
from elspeth.contracts.errors import (
    ContractViolation,
    ExtraFieldViolation,
    MissingFieldViolation,
    TypeMismatchViolation,
)

# In SchemaContract class:

    def validate(self, row: dict[str, Any]) -> list[ContractViolation]:
        """Validate row data against contract.

        Checks:
        1. Required fields are present
        2. Field types match (with numpy/pandas normalization)
        3. FIXED mode: No extra fields allowed

        Args:
            row: Row data with normalized field names as keys

        Returns:
            List of ContractViolation instances (empty if valid)
        """
        violations: list[ContractViolation] = []

        # Check declared fields
        for fc in self.fields:
            if fc.required and fc.normalized_name not in row:
                violations.append(
                    MissingFieldViolation(
                        normalized_name=fc.normalized_name,
                        original_name=fc.original_name,
                    )
                )
            elif fc.normalized_name in row:
                value = row[fc.normalized_name]
                # Normalize runtime type for comparison
                # (handles numpy.int64 matching int, etc.)
                actual_type = normalize_type_for_contract(value)
                # type(None) matches None values
                if actual_type != fc.python_type:
                    violations.append(
                        TypeMismatchViolation(
                            normalized_name=fc.normalized_name,
                            original_name=fc.original_name,
                            expected_type=fc.python_type,
                            actual_type=actual_type,
                            actual_value=value,
                        )
                    )

        # FIXED mode: reject extra fields
        if self.mode == "FIXED":
            declared_names = {fc.normalized_name for fc in self.fields}
            for key in row:
                if key not in declared_names:
                    violations.append(
                        ExtraFieldViolation(
                            normalized_name=key,
                            original_name=key,  # We don't know original for extras
                        )
                    )

        return violations
```

Add imports at top of file.

**Step 6.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract.py::TestSchemaContractValidation -v
```

Expected: All tests PASS

**Step 6.5: Commit**

```bash
git add src/elspeth/contracts/schema_contract.py tests/contracts/test_schema_contract.py
git commit -m "feat(contracts): add SchemaContract.validate() method

Validates row data against contract:
- Required fields must be present
- Types must match (with numpy/pandas normalization)
- FIXED mode rejects extra fields
- FLEXIBLE/OBSERVED allow extras

Returns list of ContractViolation instances.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: SchemaContract - Checkpoint Serialization

**Files:**
- Modify: `src/elspeth/contracts/schema_contract.py`
- Test: `tests/contracts/test_schema_contract.py` (extend)

**Step 7.1: Write failing tests for checkpoint serialization**

Add to `tests/contracts/test_schema_contract.py`:

```python
class TestSchemaContractCheckpoint:
    """Test checkpoint serialization/deserialization."""

    @pytest.fixture
    def sample_contract(self) -> SchemaContract:
        """Sample contract for testing."""
        return SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount", "'Amount USD'", int, True, "declared"),
                FieldContract("note", "Note", str, False, "inferred"),
            ),
            locked=True,
        )

    def test_version_hash_deterministic(self, sample_contract: SchemaContract) -> None:
        """version_hash() returns same value for same contract."""
        hash1 = sample_contract.version_hash()
        hash2 = sample_contract.version_hash()
        assert hash1 == hash2
        assert len(hash1) == 16  # Truncated SHA-256

    def test_version_hash_changes_on_field_change(self) -> None:
        """Different fields produce different hashes."""
        c1 = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("a", "A", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("b", "B", int, True, "declared"),),
            locked=True,
        )
        assert c1.version_hash() != c2.version_hash()

    def test_version_hash_changes_on_type_change(self) -> None:
        """Different type produces different hash."""
        c1 = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("a", "A", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("a", "A", str, True, "declared"),),
            locked=True,
        )
        assert c1.version_hash() != c2.version_hash()

    def test_to_checkpoint_format(self, sample_contract: SchemaContract) -> None:
        """to_checkpoint_format() returns serializable dict."""
        data = sample_contract.to_checkpoint_format()

        assert data["mode"] == "FLEXIBLE"
        assert data["locked"] is True
        assert "version_hash" in data
        assert len(data["fields"]) == 2
        assert data["fields"][0]["normalized_name"] == "amount"
        assert data["fields"][0]["python_type"] == "int"

    def test_from_checkpoint_round_trip(self, sample_contract: SchemaContract) -> None:
        """Contract survives checkpoint round-trip."""
        data = sample_contract.to_checkpoint_format()
        restored = SchemaContract.from_checkpoint(data)

        assert restored.mode == sample_contract.mode
        assert restored.locked == sample_contract.locked
        assert len(restored.fields) == len(sample_contract.fields)
        assert restored.fields[0].normalized_name == "amount"
        assert restored.fields[0].python_type is int

    def test_from_checkpoint_validates_hash(self, sample_contract: SchemaContract) -> None:
        """from_checkpoint() validates hash integrity."""
        data = sample_contract.to_checkpoint_format()
        data["version_hash"] = "corrupted_hash"

        with pytest.raises(ValueError, match="integrity"):
            SchemaContract.from_checkpoint(data)

    def test_from_checkpoint_unknown_type_crashes(self) -> None:
        """from_checkpoint() crashes on unknown type (Tier 1 integrity)."""
        data = {
            "mode": "FIXED",
            "locked": True,
            "fields": [
                {
                    "normalized_name": "x",
                    "original_name": "X",
                    "python_type": "UnknownType",
                    "required": True,
                    "source": "declared",
                }
            ],
        }
        with pytest.raises(KeyError):
            SchemaContract.from_checkpoint(data)

    def test_from_checkpoint_nonetype_round_trip(self) -> None:
        """type(None) survives checkpoint round-trip."""
        contract = SchemaContract(
            mode="OBSERVED",
            fields=(FieldContract("x", "X", type(None), False, "inferred"),),
            locked=True,
        )
        data = contract.to_checkpoint_format()
        restored = SchemaContract.from_checkpoint(data)

        assert restored.fields[0].python_type is type(None)
```

**Step 7.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract.py::TestSchemaContractCheckpoint -v
```

Expected: FAIL

**Step 7.3: Implement checkpoint methods**

Add to `SchemaContract` class:

```python
import hashlib
from datetime import datetime
from elspeth.core.canonical import canonical_json

# In SchemaContract class:

    def version_hash(self) -> str:
        """Deterministic hash of contract for checkpoint references.

        Uses canonical JSON of field definitions for reproducibility.
        The hash is truncated to 16 hex characters (64 bits).

        Returns:
            16-character hex hash string
        """
        field_defs = [
            {
                "n": fc.normalized_name,
                "o": fc.original_name,
                "t": fc.python_type.__name__,
                "r": fc.required,
            }
            for fc in sorted(self.fields, key=lambda f: f.normalized_name)
        ]
        content = canonical_json({"mode": self.mode, "fields": field_defs})
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_checkpoint_format(self) -> dict[str, Any]:
        """Full contract serialization for checkpoint storage.

        Includes version_hash for integrity verification on restore.

        Returns:
            Dict suitable for JSON serialization
        """
        return {
            "mode": self.mode,
            "locked": self.locked,
            "version_hash": self.version_hash(),
            "fields": [
                {
                    "normalized_name": fc.normalized_name,
                    "original_name": fc.original_name,
                    "python_type": fc.python_type.__name__,
                    "required": fc.required,
                    "source": fc.source,
                }
                for fc in self.fields
            ],
        }

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any]) -> SchemaContract:
        """Restore contract from checkpoint format.

        Validates hash integrity per Tier 1 audit requirements.

        Args:
            data: Dict from to_checkpoint_format()

        Returns:
            Restored SchemaContract

        Raises:
            KeyError: If checkpoint has unknown python_type
            ValueError: If restored hash doesn't match stored hash
        """
        # Explicit type map - NO FALLBACK (Tier 1: crash on corruption)
        # Per CLAUDE.md: "Bad data in the audit trail = crash immediately"
        type_map: dict[str, type] = {
            "int": int,
            "str": str,
            "float": float,
            "bool": bool,
            "NoneType": type(None),
            "datetime": datetime,
        }

        fields = tuple(
            FieldContract(
                normalized_name=f["normalized_name"],
                original_name=f["original_name"],
                python_type=type_map[f["python_type"]],  # KeyError on unknown = correct!
                required=f["required"],
                source=f["source"],
            )
            for f in data["fields"]
        )

        contract = cls(
            mode=data["mode"],
            fields=fields,
            locked=data["locked"],
        )

        # Verify integrity (Tier 1 audit requirement)
        if "version_hash" in data:
            expected_hash = data["version_hash"]
            actual_hash = contract.version_hash()
            if actual_hash != expected_hash:
                raise ValueError(
                    f"Contract integrity violation: hash mismatch. "
                    f"Expected {expected_hash}, got {actual_hash}. "
                    f"Checkpoint may be corrupted or from different version."
                )

        return contract
```

Add imports:

```python
import hashlib
from datetime import datetime
from elspeth.core.canonical import canonical_json
```

**Step 7.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract.py::TestSchemaContractCheckpoint -v
```

Expected: All tests PASS

**Step 7.5: Commit**

```bash
git add src/elspeth/contracts/schema_contract.py tests/contracts/test_schema_contract.py
git commit -m "feat(contracts): add SchemaContract checkpoint serialization

Add version_hash(), to_checkpoint_format(), from_checkpoint():
- Deterministic hash via canonical_json for checkpoint references
- Full serialization preserves all fields and metadata
- Hash validation on restore for Tier 1 audit integrity
- NO fallback for unknown types - crash on corruption

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: SchemaContract - Merge for Coalesce

**Files:**
- Modify: `src/elspeth/contracts/schema_contract.py`
- Test: `tests/contracts/test_schema_contract.py` (extend)

**Step 8.1: Write failing tests for merge**

Add to `tests/contracts/test_schema_contract.py`:

```python
from elspeth.contracts.errors import ContractMergeError


class TestSchemaContractMerge:
    """Test contract merging for fork/join coalesce."""

    def test_merge_same_field_same_type(self) -> None:
        """Same field, same type merges successfully."""
        c1 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        merged = c1.merge(c2)

        assert len(merged.fields) == 1
        assert merged.fields[0].python_type is int

    def test_merge_different_types_raises(self) -> None:
        """Different types raise ContractMergeError."""
        c1 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", str, True, "declared"),),
            locked=True,
        )
        with pytest.raises(ContractMergeError, match="Type mismatch"):
            c1.merge(c2)

    def test_merge_field_only_in_one_path_becomes_optional(self) -> None:
        """Field in only one path becomes optional (required=False)."""
        c1 = SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("x", "X", int, True, "declared"),
                FieldContract("y", "Y", str, True, "declared"),
            ),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        merged = c1.merge(c2)

        # y is only in c1, so becomes optional in merged
        y_field = next(f for f in merged.fields if f.normalized_name == "y")
        assert y_field.required is False

    def test_merge_mode_precedence(self) -> None:
        """Most restrictive mode wins: FIXED > FLEXIBLE > OBSERVED."""
        fixed = SchemaContract(mode="FIXED", fields=(), locked=True)
        flexible = SchemaContract(mode="FLEXIBLE", fields=(), locked=True)
        observed = SchemaContract(mode="OBSERVED", fields=(), locked=True)

        assert fixed.merge(observed).mode == "FIXED"
        assert observed.merge(fixed).mode == "FIXED"
        assert flexible.merge(observed).mode == "FLEXIBLE"

    def test_merge_locked_if_either_locked(self) -> None:
        """Merged contract is locked if either input is locked."""
        locked = SchemaContract(mode="OBSERVED", fields=(), locked=True)
        unlocked = SchemaContract(mode="OBSERVED", fields=(), locked=False)

        assert locked.merge(unlocked).locked is True
        assert unlocked.merge(locked).locked is True

    def test_merge_required_if_either_required(self) -> None:
        """Field is required if required in either path."""
        c1 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, False, "inferred"),),
            locked=True,
        )
        merged = c1.merge(c2)

        assert merged.fields[0].required is True

    def test_merge_source_declared_wins(self) -> None:
        """Field source is 'declared' if either is declared."""
        c1 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "declared"),),
            locked=True,
        )
        c2 = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", int, True, "inferred"),),
            locked=True,
        )
        merged = c1.merge(c2)

        assert merged.fields[0].source == "declared"

    def test_merge_empty_contracts(self) -> None:
        """Merging empty contracts works."""
        c1 = SchemaContract(mode="OBSERVED", fields=(), locked=True)
        c2 = SchemaContract(mode="OBSERVED", fields=(), locked=True)
        merged = c1.merge(c2)

        assert len(merged.fields) == 0
```

**Step 8.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract.py::TestSchemaContractMerge -v
```

Expected: FAIL

**Step 8.3: Implement merge method**

Add to `SchemaContract` class:

```python
from elspeth.contracts.errors import ContractMergeError

# In SchemaContract class:

    def merge(self, other: SchemaContract) -> SchemaContract:
        """Merge two contracts at a coalesce point.

        Rules:
        1. Mode: Most restrictive wins (FIXED > FLEXIBLE > OBSERVED)
        2. Fields present in both: Types must match (error if not)
        3. Fields in only one: Included but marked non-required
        4. Locked: True if either is locked

        Args:
            other: Contract to merge with

        Returns:
            New merged SchemaContract

        Raises:
            ContractMergeError: If field types conflict
        """
        # Mode precedence
        mode_order: dict[str, int] = {"FIXED": 0, "FLEXIBLE": 1, "OBSERVED": 2}
        merged_mode = min(
            self.mode, other.mode,
            key=lambda m: mode_order[m]
        )

        # Build merged field set
        merged_fields: dict[str, FieldContract] = {}

        all_names = (
            {fc.normalized_name for fc in self.fields} |
            {fc.normalized_name for fc in other.fields}
        )

        for name in all_names:
            self_fc = self._by_normalized.get(name)
            other_fc = other._by_normalized.get(name)

            if self_fc and other_fc:
                # Both have field - types must match
                if self_fc.python_type != other_fc.python_type:
                    raise ContractMergeError(
                        normalized_name=name,
                        original_name=self_fc.original_name,
                        type_a=self_fc.python_type,
                        type_b=other_fc.python_type,
                    )
                # Use the one that's required if either is
                # Use declared source if either is declared
                merged_fields[name] = FieldContract(
                    normalized_name=name,
                    original_name=self_fc.original_name,
                    python_type=self_fc.python_type,
                    required=self_fc.required or other_fc.required,
                    source="declared" if self_fc.source == "declared" or other_fc.source == "declared" else "inferred",
                )
            else:
                # Only in one path - include but mark non-required
                fc = self_fc or other_fc
                assert fc is not None  # One must exist since name came from union
                merged_fields[name] = FieldContract(
                    normalized_name=fc.normalized_name,
                    original_name=fc.original_name,
                    python_type=fc.python_type,
                    required=False,  # Can't require field from only one path
                    source=fc.source,
                )

        return SchemaContract(
            mode=merged_mode,
            fields=tuple(merged_fields.values()),
            locked=self.locked or other.locked,
        )
```

**Step 8.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_schema_contract.py::TestSchemaContractMerge -v
```

Expected: All tests PASS

**Step 8.5: Commit**

```bash
git add src/elspeth/contracts/schema_contract.py tests/contracts/test_schema_contract.py
git commit -m "feat(contracts): add SchemaContract.merge() for coalesce

Merge contracts when fork/join paths converge:
- Mode precedence: FIXED > FLEXIBLE > OBSERVED
- Type mismatch raises ContractMergeError
- Field in one path becomes optional in merged
- Required if either path requires it
- Declared source wins over inferred

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: PipelineRow Wrapper

**Files:**
- Modify: `src/elspeth/contracts/schema_contract.py`
- Test: `tests/contracts/test_pipeline_row.py` (create new)

**Step 9.1: Write failing tests for PipelineRow**

```python
# tests/contracts/test_pipeline_row.py
"""Tests for PipelineRow wrapper class."""

import pytest

from elspeth.contracts.schema_contract import (
    FieldContract,
    PipelineRow,
    SchemaContract,
)


class TestPipelineRowAccess:
    """Test PipelineRow data access patterns."""

    @pytest.fixture
    def sample_row(self) -> PipelineRow:
        """Sample row with dual-name access."""
        contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("amount_usd", "'Amount USD'", int, True, "declared"),
                FieldContract("customer_id", "Customer ID", str, True, "declared"),
            ),
            locked=True,
        )
        data = {"amount_usd": 100, "customer_id": "C123"}
        return PipelineRow(data, contract)

    def test_getitem_normalized_name(self, sample_row: PipelineRow) -> None:
        """Access by normalized name via bracket notation."""
        assert sample_row["amount_usd"] == 100

    def test_getitem_original_name(self, sample_row: PipelineRow) -> None:
        """Access by original name via bracket notation."""
        assert sample_row["'Amount USD'"] == 100

    def test_getattr_normalized_name(self, sample_row: PipelineRow) -> None:
        """Access by normalized name via dot notation."""
        assert sample_row.amount_usd == 100

    def test_getattr_unknown_raises(self, sample_row: PipelineRow) -> None:
        """Unknown attribute raises AttributeError."""
        with pytest.raises(AttributeError):
            _ = sample_row.nonexistent

    def test_getitem_unknown_raises(self, sample_row: PipelineRow) -> None:
        """Unknown key raises KeyError."""
        with pytest.raises(KeyError):
            _ = sample_row["nonexistent"]

    def test_contains_normalized(self, sample_row: PipelineRow) -> None:
        """'in' operator works with normalized name."""
        assert "amount_usd" in sample_row

    def test_contains_original(self, sample_row: PipelineRow) -> None:
        """'in' operator works with original name."""
        assert "'Amount USD'" in sample_row

    def test_contains_unknown_false(self, sample_row: PipelineRow) -> None:
        """'in' returns False for unknown fields."""
        assert "nonexistent" not in sample_row

    def test_to_dict_returns_raw_data(self, sample_row: PipelineRow) -> None:
        """to_dict() returns raw data with normalized keys."""
        d = sample_row.to_dict()
        assert d == {"amount_usd": 100, "customer_id": "C123"}
        assert isinstance(d, dict)

    def test_contract_property(self, sample_row: PipelineRow) -> None:
        """contract property provides access to schema."""
        assert sample_row.contract.mode == "FLEXIBLE"
        assert len(sample_row.contract.fields) == 2


class TestPipelineRowCheckpoint:
    """Test PipelineRow checkpoint serialization."""

    def test_to_checkpoint_format(self) -> None:
        """to_checkpoint_format() returns dict with data and contract ref."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        row = PipelineRow({"id": 42}, contract)
        checkpoint = row.to_checkpoint_format()

        assert checkpoint["data"] == {"id": 42}
        assert "contract_version" in checkpoint
        assert checkpoint["contract_version"] == contract.version_hash()

    def test_from_checkpoint_round_trip(self) -> None:
        """PipelineRow survives checkpoint round-trip."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "ID", int, True, "declared"),),
            locked=True,
        )
        original = PipelineRow({"id": 42}, contract)

        # Serialize
        checkpoint = original.to_checkpoint_format()

        # Build registry (in real use, this comes from node checkpoints)
        registry = {contract.version_hash(): contract}

        # Restore
        restored = PipelineRow.from_checkpoint(checkpoint, registry)

        assert restored["id"] == 42
        assert restored.contract.version_hash() == contract.version_hash()

    def test_from_checkpoint_unknown_contract_raises(self) -> None:
        """from_checkpoint() raises if contract not in registry."""
        checkpoint = {
            "data": {"x": 1},
            "contract_version": "unknown_hash_123",
        }
        registry: dict[str, SchemaContract] = {}

        with pytest.raises(KeyError):
            PipelineRow.from_checkpoint(checkpoint, registry)


class TestPipelineRowSlots:
    """Test PipelineRow memory efficiency."""

    def test_uses_slots(self) -> None:
        """PipelineRow uses __slots__ for memory efficiency."""
        contract = SchemaContract(mode="OBSERVED", fields=(), locked=True)
        row = PipelineRow({}, contract)

        # __slots__ means no __dict__
        assert not hasattr(row, "__dict__")
        assert hasattr(row, "__slots__")

    def test_cannot_add_attributes(self) -> None:
        """Cannot add arbitrary attributes (slots restriction)."""
        contract = SchemaContract(mode="OBSERVED", fields=(), locked=True)
        row = PipelineRow({}, contract)

        with pytest.raises(AttributeError):
            row.new_attr = "value"  # type: ignore[attr-defined]
```

**Step 9.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_pipeline_row.py -v
```

Expected: FAIL

**Step 9.3: Implement PipelineRow**

Add to `src/elspeth/contracts/schema_contract.py`:

```python
class PipelineRow:
    """Row wrapper that enables dual-name access and type tracking.

    Wraps row data with a SchemaContract reference, enabling:
    - Access by normalized name: row["amount_usd"] or row.amount_usd
    - Access by original name: row["'Amount USD'"]
    - Type tracking via contract reference
    - Checkpoint serialization

    Uses __slots__ for memory efficiency (no __dict__ per instance).

    Example:
        >>> contract = SchemaContract(...)
        >>> row = PipelineRow({"amount_usd": 100}, contract)
        >>> row.amount_usd
        100
        >>> row["'Amount USD'"]  # Original name also works
        100
    """

    __slots__ = ("_data", "_contract")

    def __init__(self, data: dict[str, Any], contract: SchemaContract) -> None:
        """Initialize PipelineRow.

        Args:
            data: Row data with normalized field names as keys
            contract: Schema contract for name resolution and validation
        """
        self._data = data
        self._contract = contract

    def __getitem__(self, key: str) -> Any:
        """Access field by original OR normalized name.

        Args:
            key: Field name (either original or normalized)

        Returns:
            Field value

        Raises:
            KeyError: If field not found in contract or data
        """
        normalized = self._contract.resolve_name(key)
        return self._data[normalized]

    def __getattr__(self, key: str) -> Any:
        """Dot notation access: row.field_name.

        Args:
            key: Attribute name (must be normalized field name)

        Returns:
            Field value

        Raises:
            AttributeError: If field not found
        """
        # Prevent infinite recursion for private attributes
        if key.startswith("_"):
            raise AttributeError(key)
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __contains__(self, key: str) -> bool:
        """Support 'if field in row' checks.

        Args:
            key: Field name (original or normalized)

        Returns:
            True if field exists in contract
        """
        try:
            self._contract.resolve_name(key)
            return True
        except KeyError:
            return False

    def to_dict(self) -> dict[str, Any]:
        """Export raw data (normalized keys) for serialization.

        Returns:
            Copy of internal data dict
        """
        return dict(self._data)

    @property
    def contract(self) -> SchemaContract:
        """Access the schema contract (for introspection/debugging).

        Returns:
            The SchemaContract associated with this row
        """
        return self._contract

    def to_checkpoint_format(self) -> dict[str, Any]:
        """Serialize for checkpoint storage.

        Returns dict with data and contract reference (not full contract).
        Contract is stored once per node, not per row.

        Returns:
            Checkpoint-serializable dict
        """
        return {
            "data": self._data,
            "contract_version": self._contract.version_hash(),
        }

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_data: dict[str, Any],
        contract_registry: dict[str, SchemaContract],
    ) -> PipelineRow:
        """Restore from checkpoint.

        Args:
            checkpoint_data: Output from to_checkpoint_format()
            contract_registry: Node contracts indexed by version_hash

        Returns:
            Restored PipelineRow

        Raises:
            KeyError: If contract version not in registry
        """
        contract = contract_registry[checkpoint_data["contract_version"]]
        return cls(data=checkpoint_data["data"], contract=contract)
```

**Step 9.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_pipeline_row.py -v
```

Expected: All tests PASS

**Step 9.5: Commit**

```bash
git add src/elspeth/contracts/schema_contract.py tests/contracts/test_pipeline_row.py
git commit -m "feat(contracts): add PipelineRow wrapper class

Enables dual-name field access via contract reference:
- Bracket notation: row['normalized'] or row['original']
- Dot notation: row.normalized_name
- 'in' operator for containment checks
- to_dict() for serialization

Checkpoint support:
- to_checkpoint_format() stores data + contract hash
- from_checkpoint() restores via contract registry

Uses __slots__ for memory efficiency.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Module Exports and Final Integration

**Files:**
- Modify: `src/elspeth/contracts/__init__.py`
- Test: Run all tests

**Step 10.1: Update module exports**

Add to `src/elspeth/contracts/__init__.py`:

```python
# Schema contracts (new)
from elspeth.contracts.schema_contract import (
    FieldContract,
    PipelineRow,
    SchemaContract,
)
from elspeth.contracts.type_normalization import normalize_type_for_contract

# In __all__ list, add:
__all__ = [
    # ... existing exports ...
    "FieldContract",
    "PipelineRow",
    "SchemaContract",
    "normalize_type_for_contract",
]
```

**Step 10.2: Run all contract tests**

```bash
.venv/bin/python -m pytest tests/contracts/ -v --tb=short
```

Expected: All tests PASS

**Step 10.3: Run type checker**

```bash
.venv/bin/python -m mypy src/elspeth/contracts/schema_contract.py src/elspeth/contracts/type_normalization.py
```

Expected: No errors

**Step 10.4: Run linter**

```bash
.venv/bin/python -m ruff check src/elspeth/contracts/schema_contract.py src/elspeth/contracts/type_normalization.py
```

Expected: No errors (or fix any issues)

**Step 10.5: Final commit**

```bash
git add src/elspeth/contracts/__init__.py
git commit -m "feat(contracts): export schema contract types from module

Add to contracts module exports:
- FieldContract
- SchemaContract
- PipelineRow
- normalize_type_for_contract

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

**Step 10.6: Update beads issue**

```bash
bd update elspeth-rapid-0ax --status=completed
bd sync
```

---

## Summary

Phase 1 implementation creates the core schema contracts foundation:

| Component | Purpose |
|-----------|---------|
| `ContractViolation` types | Structured errors for validation failures |
| `normalize_type_for_contract()` | numpy/pandas → Python primitives |
| `FieldContract` | Immutable field metadata (name, type, required) |
| `SchemaContract` | Per-node schema with O(1) name resolution |
| `PipelineRow` | Row wrapper enabling dual-name access |

**Key patterns:**
- Frozen dataclasses for immutability
- O(1) name resolution via precomputed indices
- Type normalization with NaN/Infinity rejection
- Hash-based checkpoint integrity validation
- Contract merge for fork/join coalesce

**Next:** Phase 2 integrates these contracts with source plugins.
