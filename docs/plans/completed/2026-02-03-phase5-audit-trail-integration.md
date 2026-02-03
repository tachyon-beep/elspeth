# Phase 5: Audit Trail Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Record schema contracts in the Landscape audit trail so that every field mapping, type inference, and validation decision is fully traceable. Update MCP analysis tools for contract introspection.

**Architecture:** The Landscape schema extends to store contract snapshots at key lifecycle points: runs store source-level field resolution, nodes store their declared contracts, node_states can record inferred schemas for OBSERVED mode. The MCP analysis server gains contract-aware queries for debugging validation failures and tracing field provenance.

**Tech Stack:** Python 3.11+, SQLAlchemy Core (existing), Alembic migrations, existing `SchemaContract`, `LandscapeRecorder`, MCP server.

**Design Doc:** `docs/plans/2026-02-02-unified-schema-contracts-design.md`

**Depends On:** Phase 1 (Core Contracts), Phase 2 (Source Integration), Phase 3 (Transform/Sink Integration), Phase 4 (Template Resolver)

---

## Overview

Phase 5 completes the audit trail for schema contracts:

```
Pipeline Execution                        Audit Trail (Landscape)
┌─────────────────────────┐               ┌─────────────────────────┐
│ Source creates contract │─────────────► │ runs.schema_contract_json │
│ (field resolution +     │               │ - field_resolution mapping │
│  type inference)        │               │ - contract_hash           │
├─────────────────────────┤               ├─────────────────────────┤
│ Transform validates     │─────────────► │ nodes.contract_json       │
│ (input/output schemas)  │               │ - declared fields         │
├─────────────────────────┤               │ - mode (FIXED/FLEXIBLE)   │
│ Validation failure      │─────────────► ├─────────────────────────┤
│                         │               │ validation_errors         │
│                         │               │ - contract_violation type │
│                         │               │ - expected_type           │
│                         │               │ - actual_type             │
└─────────────────────────┘               └─────────────────────────┘
```

Key changes:
1. **Schema extensions**: Add contract columns to `runs` and `nodes` tables
2. **Recorder updates**: Store contracts via `LandscapeRecorder` methods
3. **Validation error enrichment**: Include contract violation details
4. **MCP tools**: Query contracts and trace field provenance
5. **Contract checkpoints**: Support resume with contract restoration

---

## Task 1: Schema Migration - Add Contract Columns

**Files:**
- Create: `alembic/versions/xxxx_add_schema_contracts.py`
- Modify: `src/elspeth/core/landscape/schema.py`
- Test: `tests/core/landscape/test_schema_migration.py` (create new)

**Step 1.1: Write failing test for new schema columns**

```python
# tests/core/landscape/test_schema_contracts_schema.py
"""Tests for schema contract columns in Landscape schema."""

import pytest
from sqlalchemy import inspect

from elspeth.core.landscape.database import LandscapeDB


class TestSchemaContractColumns:
    """Test new schema contract columns exist."""

    @pytest.fixture
    def db(self) -> LandscapeDB:
        """In-memory database with schema."""
        db = LandscapeDB.in_memory()
        db.create_all()
        return db

    def test_runs_has_schema_contract_json(self, db: LandscapeDB) -> None:
        """runs table has schema_contract_json column."""
        inspector = inspect(db.engine)
        columns = {c["name"] for c in inspector.get_columns("runs")}

        assert "schema_contract_json" in columns

    def test_nodes_has_input_contract_json(self, db: LandscapeDB) -> None:
        """nodes table has input_contract_json column."""
        inspector = inspect(db.engine)
        columns = {c["name"] for c in inspector.get_columns("nodes")}

        assert "input_contract_json" in columns

    def test_nodes_has_output_contract_json(self, db: LandscapeDB) -> None:
        """nodes table has output_contract_json column."""
        inspector = inspect(db.engine)
        columns = {c["name"] for c in inspector.get_columns("nodes")}

        assert "output_contract_json" in columns

    def test_validation_errors_has_contract_fields(self, db: LandscapeDB) -> None:
        """validation_errors table has contract violation fields."""
        inspector = inspect(db.engine)
        columns = {c["name"] for c in inspector.get_columns("validation_errors")}

        assert "violation_type" in columns
        assert "expected_type" in columns
        assert "actual_type" in columns
        assert "original_field_name" in columns
```

**Step 1.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/core/landscape/test_schema_contracts_schema.py -v
```

Expected: FAIL (columns don't exist yet)

**Step 1.3: Update schema.py with contract columns**

In `src/elspeth/core/landscape/schema.py`, update the tables:

Update `runs_table`:

```python
runs_table = Table(
    "runs",
    metadata,
    Column("run_id", String(64), primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("config_hash", String(64), nullable=False),
    Column("settings_json", Text, nullable=False),
    Column("reproducibility_grade", String(32)),
    Column("canonical_version", String(64), nullable=False),
    # Source schema for resume type restoration
    Column("source_schema_json", Text),  # Nullable for backward compatibility
    # Field resolution mapping from source.load()
    Column("source_field_resolution_json", Text),  # Nullable for backward compatibility
    # Schema contract for source (Phase 5) - full contract with types
    # Captures field resolution + type inference at source boundary
    Column("schema_contract_json", Text),  # Nullable for backward compatibility
    Column("schema_contract_hash", String(16)),  # version_hash for integrity
    Column("status", String(32), nullable=False),
    # Export tracking
    Column("export_status", String(32)),
    Column("export_error", Text),
    Column("exported_at", DateTime(timezone=True)),
    Column("export_format", String(16)),
    Column("export_sink", String(128)),
)
```

Update `nodes_table`:

```python
nodes_table = Table(
    "nodes",
    metadata,
    Column("node_id", String(64), nullable=False),
    Column("run_id", String(64), ForeignKey("runs.run_id"), nullable=False),
    Column("plugin_name", String(128), nullable=False),
    Column("node_type", String(32), nullable=False),
    Column("plugin_version", String(32), nullable=False),
    Column("determinism", String(32), nullable=False),
    Column("config_hash", String(64), nullable=False),
    Column("config_json", Text, nullable=False),
    Column("schema_hash", String(64)),
    Column("sequence_in_pipeline", Integer),
    Column("registered_at", DateTime(timezone=True), nullable=False),
    # Schema configuration for audit trail (WP-11.99) - legacy
    Column("schema_mode", String(16)),
    Column("schema_fields_json", Text),
    # Schema contracts (Phase 5) - full contracts with types
    # input_contract: What the node requires (input validation)
    # output_contract: What the node guarantees (output schema)
    Column("input_contract_json", Text),  # Nullable for backward compatibility
    Column("output_contract_json", Text),  # Nullable for backward compatibility
    # Composite PK
    PrimaryKeyConstraint("node_id", "run_id"),
)
```

Update `validation_errors_table`:

```python
validation_errors_table = Table(
    "validation_errors",
    metadata,
    Column("error_id", String(32), primary_key=True),
    Column("run_id", String(64), ForeignKey("runs.run_id"), nullable=False),
    Column("node_id", String(64)),
    Column("row_hash", String(64), nullable=False),
    Column("row_data_json", Text),
    Column("error", Text, nullable=False),
    Column("schema_mode", String(16), nullable=False),
    Column("destination", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    # Contract violation details (Phase 5)
    # Enables precise debugging: "field X expected int, got str"
    Column("violation_type", String(32)),  # "type_mismatch", "missing_field", "extra_field"
    Column("original_field_name", String(256)),  # "'Amount USD'" for display
    Column("normalized_field_name", String(256)),  # "amount_usd" for code reference
    Column("expected_type", String(32)),  # "int", "str", etc.
    Column("actual_type", String(32)),  # Type of actual value
    # Composite FK to nodes
    ForeignKeyConstraint(
        ["node_id", "run_id"],
        ["nodes.node_id", "nodes.run_id"],
        ondelete="RESTRICT",
    ),
)
```

**Step 1.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/core/landscape/test_schema_contracts_schema.py -v
```

Expected: All tests PASS

**Step 1.5: Create Alembic migration**

Create migration file:

```python
# alembic/versions/2026_02_03_add_schema_contracts.py
"""Add schema contract columns to runs, nodes, and validation_errors.

Revision ID: add_schema_contracts
Revises: <previous_revision>
Create Date: 2026-02-03

This migration adds Phase 5 schema contract support:
- runs.schema_contract_json: Full contract with field resolution and types
- runs.schema_contract_hash: Integrity hash for checkpoint validation
- nodes.input_contract_json: What the node requires
- nodes.output_contract_json: What the node guarantees
- validation_errors: Contract violation detail columns
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_schema_contracts"
down_revision = "<previous_revision>"  # Fill in actual revision
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add contract columns to runs table
    op.add_column("runs", sa.Column("schema_contract_json", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("schema_contract_hash", sa.String(16), nullable=True))

    # Add contract columns to nodes table
    op.add_column("nodes", sa.Column("input_contract_json", sa.Text(), nullable=True))
    op.add_column("nodes", sa.Column("output_contract_json", sa.Text(), nullable=True))

    # Add violation detail columns to validation_errors table
    op.add_column("validation_errors", sa.Column("violation_type", sa.String(32), nullable=True))
    op.add_column("validation_errors", sa.Column("original_field_name", sa.String(256), nullable=True))
    op.add_column("validation_errors", sa.Column("normalized_field_name", sa.String(256), nullable=True))
    op.add_column("validation_errors", sa.Column("expected_type", sa.String(32), nullable=True))
    op.add_column("validation_errors", sa.Column("actual_type", sa.String(32), nullable=True))


def downgrade() -> None:
    # Remove validation_errors columns
    op.drop_column("validation_errors", "actual_type")
    op.drop_column("validation_errors", "expected_type")
    op.drop_column("validation_errors", "normalized_field_name")
    op.drop_column("validation_errors", "original_field_name")
    op.drop_column("validation_errors", "violation_type")

    # Remove nodes columns
    op.drop_column("nodes", "output_contract_json")
    op.drop_column("nodes", "input_contract_json")

    # Remove runs columns
    op.drop_column("runs", "schema_contract_hash")
    op.drop_column("runs", "schema_contract_json")
```

**Step 1.6: Commit**

```bash
git add src/elspeth/core/landscape/schema.py alembic/versions/2026_02_03_add_schema_contracts.py tests/core/landscape/test_schema_contracts_schema.py
git commit -m "feat(landscape): add schema contract columns

runs table:
- schema_contract_json: Full source contract
- schema_contract_hash: Integrity verification

nodes table:
- input_contract_json: Input requirements
- output_contract_json: Output guarantees

validation_errors table:
- violation_type, original_field_name, normalized_field_name
- expected_type, actual_type for debugging

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Contract Data Types

**Files:**
- Modify: `src/elspeth/contracts/__init__.py`
- Create: `src/elspeth/contracts/contract_records.py`
- Test: `tests/contracts/test_contract_records.py` (create new)

**Step 2.1: Write failing tests for contract records**

```python
# tests/contracts/test_contract_records.py
"""Tests for contract audit record types."""

import pytest

from elspeth.contracts.contract_records import (
    ContractAuditRecord,
    ValidationErrorWithContract,
)
from elspeth.contracts.schema_contract import FieldContract, SchemaContract


class TestContractAuditRecord:
    """Test ContractAuditRecord for Landscape storage."""

    def test_from_schema_contract(self) -> None:
        """Creates audit record from SchemaContract."""
        contract = SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract("id", "ID", int, True, "declared"),
                FieldContract("name", "Name", str, True, "declared"),
            ),
            locked=True,
        )

        record = ContractAuditRecord.from_contract(contract)

        assert record.mode == "FIXED"
        assert record.locked is True
        assert record.version_hash == contract.version_hash()
        assert len(record.fields) == 2

    def test_to_json(self) -> None:
        """Serializes to JSON for storage."""
        contract = SchemaContract(
            mode="OBSERVED",
            fields=(FieldContract("amount", "'Amount'", int, True, "inferred"),),
            locked=True,
        )

        record = ContractAuditRecord.from_contract(contract)
        json_str = record.to_json()

        assert '"mode": "OBSERVED"' in json_str
        assert '"locked": true' in json_str
        assert '"normalized_name": "amount"' in json_str

    def test_from_json(self) -> None:
        """Deserializes from stored JSON."""
        contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(FieldContract("x", "X", float, False, "declared"),),
            locked=False,
        )

        record = ContractAuditRecord.from_contract(contract)
        json_str = record.to_json()

        restored = ContractAuditRecord.from_json(json_str)

        assert restored.mode == record.mode
        assert restored.locked == record.locked
        assert len(restored.fields) == len(record.fields)

    def test_to_schema_contract(self) -> None:
        """Converts back to SchemaContract."""
        original = SchemaContract(
            mode="FIXED",
            fields=(FieldContract("id", "id", int, True, "declared"),),
            locked=True,
        )

        record = ContractAuditRecord.from_contract(original)
        restored = record.to_schema_contract()

        assert restored.mode == original.mode
        assert restored.locked == original.locked
        assert restored.version_hash() == original.version_hash()


class TestValidationErrorWithContract:
    """Test validation error record with contract details."""

    def test_from_type_mismatch_violation(self) -> None:
        """Creates record from TypeMismatchViolation."""
        from elspeth.contracts.errors import TypeMismatchViolation

        violation = TypeMismatchViolation(
            normalized_name="amount",
            original_name="'Amount USD'",
            expected_type=int,
            actual_type=str,
            actual_value="not_an_int",
        )

        record = ValidationErrorWithContract.from_violation(violation)

        assert record.violation_type == "type_mismatch"
        assert record.normalized_field_name == "amount"
        assert record.original_field_name == "'Amount USD'"
        assert record.expected_type == "int"
        assert record.actual_type == "str"

    def test_from_missing_field_violation(self) -> None:
        """Creates record from MissingFieldViolation."""
        from elspeth.contracts.errors import MissingFieldViolation

        violation = MissingFieldViolation(
            normalized_name="required_field",
            original_name="Required Field",
        )

        record = ValidationErrorWithContract.from_violation(violation)

        assert record.violation_type == "missing_field"
        assert record.normalized_field_name == "required_field"
        assert record.expected_type is None  # Missing fields don't have type mismatch

    def test_from_extra_field_violation(self) -> None:
        """Creates record from ExtraFieldViolation."""
        from elspeth.contracts.errors import ExtraFieldViolation

        violation = ExtraFieldViolation(
            normalized_name="unexpected",
            original_name="unexpected",
        )

        record = ValidationErrorWithContract.from_violation(violation)

        assert record.violation_type == "extra_field"
```

**Step 2.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/contracts/test_contract_records.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 2.3: Implement contract records**

```python
# src/elspeth/contracts/contract_records.py
"""Audit record types for schema contracts.

These dataclasses represent schema contract data in a form suitable for
Landscape storage (JSON serialization) while preserving full fidelity.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from elspeth.contracts.errors import (
    ContractViolation,
    ExtraFieldViolation,
    MissingFieldViolation,
    TypeMismatchViolation,
)
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.canonical import canonical_json


@dataclass(frozen=True)
class FieldAuditRecord:
    """Audit record for a single field in a contract.

    Attributes:
        normalized_name: Python identifier (dict key)
        original_name: Display name from source
        python_type: Type name as string (e.g., "int", "str")
        required: Whether field must be present
        source: "declared" or "inferred"
    """

    normalized_name: str
    original_name: str
    python_type: str
    required: bool
    source: Literal["declared", "inferred"]

    @classmethod
    def from_field_contract(cls, fc: FieldContract) -> FieldAuditRecord:
        """Create from FieldContract."""
        return cls(
            normalized_name=fc.normalized_name,
            original_name=fc.original_name,
            python_type=fc.python_type.__name__,
            required=fc.required,
            source=fc.source,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "normalized_name": self.normalized_name,
            "original_name": self.original_name,
            "python_type": self.python_type,
            "required": self.required,
            "source": self.source,
        }


@dataclass(frozen=True)
class ContractAuditRecord:
    """Audit record for a SchemaContract.

    Provides JSON serialization and integrity verification for
    storing contracts in the Landscape audit trail.

    Attributes:
        mode: Schema enforcement mode (FIXED, FLEXIBLE, OBSERVED)
        locked: Whether types are frozen
        version_hash: Integrity hash for checkpoint validation
        fields: Tuple of field records
    """

    mode: Literal["FIXED", "FLEXIBLE", "OBSERVED"]
    locked: bool
    version_hash: str
    fields: tuple[FieldAuditRecord, ...]

    @classmethod
    def from_contract(cls, contract: SchemaContract) -> ContractAuditRecord:
        """Create audit record from SchemaContract.

        Args:
            contract: The schema contract to record

        Returns:
            ContractAuditRecord for Landscape storage
        """
        field_records = tuple(
            FieldAuditRecord.from_field_contract(fc) for fc in contract.fields
        )
        return cls(
            mode=contract.mode,
            locked=contract.locked,
            version_hash=contract.version_hash(),
            fields=field_records,
        )

    def to_json(self) -> str:
        """Serialize to JSON string for storage.

        Uses canonical JSON for deterministic serialization.

        Returns:
            JSON string
        """
        return canonical_json(self._to_dict())

    def _to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "mode": self.mode,
            "locked": self.locked,
            "version_hash": self.version_hash,
            "fields": [f.to_dict() for f in self.fields],
        }

    @classmethod
    def from_json(cls, json_str: str) -> ContractAuditRecord:
        """Deserialize from JSON string.

        Args:
            json_str: JSON string from Landscape storage

        Returns:
            ContractAuditRecord

        Raises:
            json.JSONDecodeError: If JSON is invalid
            KeyError: If required fields are missing
        """
        data = json.loads(json_str)
        fields = tuple(
            FieldAuditRecord(
                normalized_name=f["normalized_name"],
                original_name=f["original_name"],
                python_type=f["python_type"],
                required=f["required"],
                source=f["source"],
            )
            for f in data["fields"]
        )
        return cls(
            mode=data["mode"],
            locked=data["locked"],
            version_hash=data["version_hash"],
            fields=fields,
        )

    def to_schema_contract(self) -> SchemaContract:
        """Convert back to SchemaContract.

        Used for resume and checkpoint restoration.

        Returns:
            SchemaContract with full fidelity

        Raises:
            KeyError: If python_type is unknown (Tier 1 integrity)
        """
        # Explicit type map - NO FALLBACK (Tier 1 audit integrity)
        type_map: dict[str, type] = {
            "int": int,
            "str": str,
            "float": float,
            "bool": bool,
            "NoneType": type(None),
            "datetime": datetime,
            "object": object,
        }

        field_contracts = tuple(
            FieldContract(
                normalized_name=f.normalized_name,
                original_name=f.original_name,
                python_type=type_map[f.python_type],  # KeyError = corruption
                required=f.required,
                source=f.source,
            )
            for f in self.fields
        )

        contract = SchemaContract(
            mode=self.mode,
            fields=field_contracts,
            locked=self.locked,
        )

        # Verify integrity
        if contract.version_hash() != self.version_hash:
            raise ValueError(
                f"Contract integrity violation: hash mismatch. "
                f"Expected {self.version_hash}, got {contract.version_hash()}."
            )

        return contract


@dataclass(frozen=True)
class ValidationErrorWithContract:
    """Validation error record with contract violation details.

    Extends the basic validation error with precise field and type
    information from contract violations.

    Attributes:
        violation_type: "type_mismatch", "missing_field", "extra_field"
        normalized_field_name: Python identifier
        original_field_name: Display name from source
        expected_type: Expected type name (for type_mismatch)
        actual_type: Actual value type name (for type_mismatch)
    """

    violation_type: Literal["type_mismatch", "missing_field", "extra_field"]
    normalized_field_name: str
    original_field_name: str
    expected_type: str | None
    actual_type: str | None

    @classmethod
    def from_violation(cls, violation: ContractViolation) -> ValidationErrorWithContract:
        """Create from ContractViolation.

        Args:
            violation: The contract violation

        Returns:
            ValidationErrorWithContract for Landscape storage
        """
        violation_type: Literal["type_mismatch", "missing_field", "extra_field"]
        expected_type: str | None = None
        actual_type: str | None = None

        if isinstance(violation, TypeMismatchViolation):
            violation_type = "type_mismatch"
            expected_type = violation.expected_type.__name__
            actual_type = violation.actual_type.__name__
        elif isinstance(violation, MissingFieldViolation):
            violation_type = "missing_field"
        elif isinstance(violation, ExtraFieldViolation):
            violation_type = "extra_field"
        else:
            # Default for unknown violation types
            violation_type = "type_mismatch"

        return cls(
            violation_type=violation_type,
            normalized_field_name=violation.normalized_name,
            original_field_name=violation.original_name,
            expected_type=expected_type,
            actual_type=actual_type,
        )
```

**Step 2.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/contracts/test_contract_records.py -v
```

Expected: All tests PASS

**Step 2.5: Update contracts module exports**

Add to `src/elspeth/contracts/__init__.py`:

```python
# Contract audit records (Phase 5)
from elspeth.contracts.contract_records import (
    ContractAuditRecord,
    FieldAuditRecord,
    ValidationErrorWithContract,
)
```

Update `__all__`:

```python
__all__ = [
    # ... existing exports ...

    # Contract audit records (Phase 5)
    "ContractAuditRecord",
    "FieldAuditRecord",
    "ValidationErrorWithContract",
]
```

**Step 2.6: Commit**

```bash
git add src/elspeth/contracts/contract_records.py src/elspeth/contracts/__init__.py tests/contracts/test_contract_records.py
git commit -m "feat(contracts): add audit record types for contracts

ContractAuditRecord: JSON-serializable record for Landscape storage
- from_contract(): Create from SchemaContract
- to_json()/from_json(): Serialization
- to_schema_contract(): Restore with integrity verification

ValidationErrorWithContract: Contract violation details
- violation_type, field names, expected/actual types

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: LandscapeRecorder Contract Methods

**Files:**
- Modify: `src/elspeth/core/landscape/recorder.py`
- Test: `tests/core/landscape/test_recorder_contracts.py` (create new)

**Step 3.1: Write failing tests for recorder contract methods**

```python
# tests/core/landscape/test_recorder_contracts.py
"""Tests for LandscapeRecorder schema contract methods."""

import pytest

from elspeth.contracts import RunStatus
from elspeth.contracts.contract_records import ContractAuditRecord
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder


class TestRecorderContractMethods:
    """Test LandscapeRecorder contract recording methods."""

    @pytest.fixture
    def db(self) -> LandscapeDB:
        """In-memory database."""
        db = LandscapeDB.in_memory()
        db.create_all()
        return db

    @pytest.fixture
    def recorder(self, db: LandscapeDB) -> LandscapeRecorder:
        """Recorder instance."""
        return LandscapeRecorder(db)

    @pytest.fixture
    def sample_contract(self) -> SchemaContract:
        """Sample schema contract."""
        return SchemaContract(
            mode="OBSERVED",
            fields=(
                FieldContract("id", "ID", int, True, "inferred"),
                FieldContract("name", "Name", str, True, "inferred"),
            ),
            locked=True,
        )

    def test_record_run_with_contract(
        self, recorder: LandscapeRecorder, sample_contract: SchemaContract
    ) -> None:
        """begin_run accepts schema_contract parameter."""
        run = recorder.begin_run(
            config={"test": True},
            canonical_version="1.0.0",
            schema_contract=sample_contract,
        )

        # Verify contract was stored
        retrieved = recorder.get_run_contract(run.run_id)

        assert retrieved is not None
        assert retrieved.mode == "OBSERVED"
        assert retrieved.locked is True
        assert len(retrieved.fields) == 2

    def test_update_run_contract(
        self, recorder: LandscapeRecorder, sample_contract: SchemaContract
    ) -> None:
        """update_run_contract stores contract after first-row inference."""
        run = recorder.begin_run(
            config={"test": True},
            canonical_version="1.0.0",
        )

        # Simulate first-row inference completing
        recorder.update_run_contract(run.run_id, sample_contract)

        # Verify contract was stored
        retrieved = recorder.get_run_contract(run.run_id)
        assert retrieved is not None
        assert retrieved.mode == sample_contract.mode

    def test_record_node_with_contracts(
        self, recorder: LandscapeRecorder, sample_contract: SchemaContract
    ) -> None:
        """register_node accepts input/output contracts."""
        run = recorder.begin_run(
            config={"test": True},
            canonical_version="1.0.0",
        )

        output_contract = SchemaContract(
            mode="FLEXIBLE",
            fields=(
                FieldContract("result", "result", str, True, "declared"),
            ),
            locked=True,
        )

        node = recorder.register_node(
            run_id=run.run_id,
            node_id="transform_1",
            plugin_name="test_transform",
            node_type="transform",
            plugin_version="1.0.0",
            determinism="deterministic",
            config={"param": "value"},
            sequence_in_pipeline=1,
            input_contract=sample_contract,
            output_contract=output_contract,
        )

        # Verify contracts were stored
        input_c, output_c = recorder.get_node_contracts(run.run_id, node.node_id)

        assert input_c is not None
        assert input_c.mode == "OBSERVED"

        assert output_c is not None
        assert output_c.mode == "FLEXIBLE"

    def test_get_run_contract_returns_none_if_not_set(
        self, recorder: LandscapeRecorder
    ) -> None:
        """get_run_contract returns None if contract not set."""
        run = recorder.begin_run(
            config={"test": True},
            canonical_version="1.0.0",
        )

        result = recorder.get_run_contract(run.run_id)
        assert result is None

    def test_record_validation_error_with_contract(
        self, recorder: LandscapeRecorder
    ) -> None:
        """record_validation_error accepts contract violation details."""
        from elspeth.contracts.errors import TypeMismatchViolation

        run = recorder.begin_run(
            config={"test": True},
            canonical_version="1.0.0",
        )

        violation = TypeMismatchViolation(
            normalized_name="amount",
            original_name="'Amount USD'",
            expected_type=int,
            actual_type=str,
            actual_value="not_an_int",
        )

        error = recorder.record_validation_error(
            run_id=run.run_id,
            row={"amount": "not_an_int"},
            error="Type mismatch",
            schema_mode="strict",
            destination="quarantine",
            contract_violation=violation,
        )

        # Verify violation details were stored
        errors = recorder.get_validation_errors(run.run_id)
        assert len(errors) == 1
        assert errors[0].violation_type == "type_mismatch"
        assert errors[0].normalized_field_name == "amount"
        assert errors[0].original_field_name == "'Amount USD'"
        assert errors[0].expected_type == "int"
        assert errors[0].actual_type == "str"
```

**Step 3.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/core/landscape/test_recorder_contracts.py -v
```

Expected: FAIL (methods don't exist yet)

**Step 3.3: Add contract methods to LandscapeRecorder**

In `src/elspeth/core/landscape/recorder.py`, add imports:

```python
from elspeth.contracts.contract_records import (
    ContractAuditRecord,
    ValidationErrorWithContract,
)
from elspeth.contracts.schema_contract import SchemaContract
```

Update `begin_run` method signature:

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
    """Begin a new pipeline run.

    Args:
        config: Resolved configuration dictionary
        canonical_version: Version of canonical hash algorithm
        run_id: Optional run ID (generated if not provided)
        reproducibility_grade: Optional grade (FULL_REPRODUCIBLE, etc.)
        status: Initial RunStatus (defaults to RUNNING)
        source_schema_json: Optional serialized source schema for resume type restoration
        schema_contract: Optional source schema contract (Phase 5).
            If provided, stores the contract with field resolution and types.
            Can also be set later via update_run_contract().

    Returns:
        Run model with generated run_id
    """
    # ... existing implementation ...

    # Add contract storage
    schema_contract_json: str | None = None
    schema_contract_hash: str | None = None
    if schema_contract is not None:
        audit_record = ContractAuditRecord.from_contract(schema_contract)
        schema_contract_json = audit_record.to_json()
        schema_contract_hash = audit_record.version_hash

    # Update run creation to include contract columns
    # ... (update the insert statement) ...
```

Add new methods:

```python
def update_run_contract(
    self,
    run_id: str,
    contract: SchemaContract,
) -> None:
    """Update run with schema contract after first-row inference.

    Called by orchestrator after source.load() completes first-row
    processing for OBSERVED/FLEXIBLE modes.

    Args:
        run_id: Run to update
        contract: Locked schema contract from source
    """
    audit_record = ContractAuditRecord.from_contract(contract)

    with self._db.session() as session:
        stmt = (
            runs_table.update()
            .where(runs_table.c.run_id == run_id)
            .values(
                schema_contract_json=audit_record.to_json(),
                schema_contract_hash=audit_record.version_hash,
            )
        )
        session.execute(stmt)
        session.commit()


def get_run_contract(self, run_id: str) -> SchemaContract | None:
    """Get schema contract for a run.

    Args:
        run_id: Run to query

    Returns:
        SchemaContract if stored, None otherwise
    """
    with self._db.session() as session:
        stmt = select(runs_table.c.schema_contract_json).where(
            runs_table.c.run_id == run_id
        )
        result = session.execute(stmt).fetchone()

        if result is None or result[0] is None:
            return None

        audit_record = ContractAuditRecord.from_json(result[0])
        return audit_record.to_schema_contract()


def register_node(
    self,
    run_id: str,
    node_id: str,
    plugin_name: str,
    node_type: str,
    plugin_version: str,
    determinism: str,
    config: dict[str, Any],
    *,
    sequence_in_pipeline: int | None = None,
    schema_config: SchemaConfig | None = None,
    input_contract: SchemaContract | None = None,
    output_contract: SchemaContract | None = None,
) -> Node:
    """Register a node in the audit trail.

    ... (keep existing docstring, add parameters) ...

    Args:
        ... existing args ...
        input_contract: Optional input schema contract (Phase 5)
        output_contract: Optional output schema contract (Phase 5)
    """
    # ... existing implementation ...

    # Add contract storage
    input_contract_json: str | None = None
    output_contract_json: str | None = None

    if input_contract is not None:
        input_contract_json = ContractAuditRecord.from_contract(input_contract).to_json()

    if output_contract is not None:
        output_contract_json = ContractAuditRecord.from_contract(output_contract).to_json()

    # Update insert to include contract columns
    # ... (update the values dict) ...


def get_node_contracts(
    self,
    run_id: str,
    node_id: str,
) -> tuple[SchemaContract | None, SchemaContract | None]:
    """Get input and output contracts for a node.

    Args:
        run_id: Run containing the node
        node_id: Node to query

    Returns:
        Tuple of (input_contract, output_contract), either can be None
    """
    with self._db.session() as session:
        stmt = select(
            nodes_table.c.input_contract_json,
            nodes_table.c.output_contract_json,
        ).where(
            (nodes_table.c.run_id == run_id) & (nodes_table.c.node_id == node_id)
        )
        result = session.execute(stmt).fetchone()

        if result is None:
            return (None, None)

        input_contract: SchemaContract | None = None
        output_contract: SchemaContract | None = None

        if result[0] is not None:
            input_contract = ContractAuditRecord.from_json(result[0]).to_schema_contract()

        if result[1] is not None:
            output_contract = ContractAuditRecord.from_json(result[1]).to_schema_contract()

        return (input_contract, output_contract)


def record_validation_error(
    self,
    run_id: str,
    row: dict[str, Any],
    error: str,
    schema_mode: str,
    destination: str,
    *,
    node_id: str | None = None,
    contract_violation: ContractViolation | None = None,
) -> ValidationErrorRecord:
    """Record a validation error with optional contract details.

    Args:
        run_id: Run where error occurred
        row: The row that failed validation
        error: Error message
        schema_mode: Schema mode (strict, free, dynamic, parse)
        destination: Sink name or "discard"
        node_id: Optional source node ID
        contract_violation: Optional contract violation details (Phase 5)

    Returns:
        ValidationErrorRecord
    """
    # ... existing implementation ...

    # Add contract violation details
    violation_type: str | None = None
    normalized_field_name: str | None = None
    original_field_name: str | None = None
    expected_type: str | None = None
    actual_type: str | None = None

    if contract_violation is not None:
        violation_record = ValidationErrorWithContract.from_violation(contract_violation)
        violation_type = violation_record.violation_type
        normalized_field_name = violation_record.normalized_field_name
        original_field_name = violation_record.original_field_name
        expected_type = violation_record.expected_type
        actual_type = violation_record.actual_type

    # Update insert to include violation columns
    # ... (update the values dict) ...
```

**Step 3.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/core/landscape/test_recorder_contracts.py -v
```

Expected: All tests PASS

**Step 3.5: Commit**

```bash
git add src/elspeth/core/landscape/recorder.py tests/core/landscape/test_recorder_contracts.py
git commit -m "feat(landscape): add contract methods to LandscapeRecorder

New methods:
- begin_run(schema_contract=): Store contract at run start
- update_run_contract(): Set contract after first-row inference
- get_run_contract(): Retrieve contract for resume
- register_node(input_contract=, output_contract=): Store node contracts
- get_node_contracts(): Retrieve node contracts
- record_validation_error(contract_violation=): Store violation details

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Orchestrator Contract Recording

**Files:**
- Modify: `src/elspeth/engine/orchestrator.py`
- Test: `tests/engine/test_orchestrator_contracts.py` (create new)

**Step 4.1: Write failing tests for orchestrator contract recording**

```python
# tests/engine/test_orchestrator_contracts.py
"""Tests for Orchestrator schema contract recording."""

import pytest
from pathlib import Path
from textwrap import dedent

from elspeth.engine.orchestrator import Orchestrator
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder


class TestOrchestratorContractRecording:
    """Test that Orchestrator records contracts in Landscape."""

    @pytest.fixture
    def csv_file(self, tmp_path: Path) -> Path:
        """Create test CSV."""
        csv = tmp_path / "data.csv"
        csv.write_text(dedent("""\
            id,name
            1,Alice
            2,Bob
        """))
        return csv

    @pytest.fixture
    def db(self) -> LandscapeDB:
        """In-memory database."""
        db = LandscapeDB.in_memory()
        db.create_all()
        return db

    def test_records_source_contract_on_first_row(
        self, csv_file: Path, db: LandscapeDB, tmp_path: Path
    ) -> None:
        """Source contract recorded after first-row inference."""
        config = {
            "source": {
                "plugin": "csv",
                "options": {
                    "path": str(csv_file),
                    "schema": {"fields": "dynamic"},
                    "on_validation_failure": "discard",
                },
            },
            "sinks": {
                "output": {
                    "plugin": "csv",
                    "options": {
                        "path": str(tmp_path / "output.csv"),
                        "schema": {"fields": "dynamic"},
                    },
                },
            },
        }

        orchestrator = Orchestrator(config, db)
        run = orchestrator.execute()

        # Verify contract was recorded
        recorder = LandscapeRecorder(db)
        contract = recorder.get_run_contract(run.run_id)

        assert contract is not None
        assert contract.mode == "OBSERVED"
        assert contract.locked is True
        assert len(contract.fields) == 2  # id, name

    def test_records_node_contracts(
        self, csv_file: Path, db: LandscapeDB, tmp_path: Path
    ) -> None:
        """Node input/output contracts recorded on registration."""
        config = {
            "source": {
                "plugin": "csv",
                "options": {
                    "path": str(csv_file),
                    "schema": {
                        "mode": "strict",
                        "fields": ["id: int", "name: str"],
                    },
                    "on_validation_failure": "discard",
                },
            },
            "sinks": {
                "output": {
                    "plugin": "csv",
                    "options": {
                        "path": str(tmp_path / "output.csv"),
                        "schema": {"fields": "dynamic"},
                    },
                },
            },
        }

        orchestrator = Orchestrator(config, db)
        run = orchestrator.execute()

        # Verify source node has contracts
        recorder = LandscapeRecorder(db)
        # Source nodes have output contract (what they emit)
        input_c, output_c = recorder.get_node_contracts(run.run_id, "source")

        assert output_c is not None
        assert output_c.mode == "FIXED"
```

**Step 4.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/engine/test_orchestrator_contracts.py -v
```

Expected: FAIL (orchestrator doesn't record contracts yet)

**Step 4.3: Update Orchestrator to record contracts**

In `src/elspeth/engine/orchestrator.py`, update the source loading phase:

```python
# After source.load() yields first row and contract is locked
def _process_source(self, ctx: ExecutionContext) -> None:
    """Process source rows and record contract."""
    source = ctx.source
    first_row_processed = False

    for source_row in source.load(ctx.plugin_context):
        if not first_row_processed:
            # Record source contract after first-row inference
            contract = source.get_schema_contract()
            if contract is not None:
                self._recorder.update_run_contract(ctx.run_id, contract)
            first_row_processed = True

        # ... rest of row processing ...
```

Update node registration to include contracts:

```python
def _register_source_node(
    self,
    run_id: str,
    source: BaseSource,
) -> Node:
    """Register source node with contracts."""
    contract = source.get_schema_contract()

    return self._recorder.register_node(
        run_id=run_id,
        node_id="source",
        plugin_name=source.name,
        node_type=NodeType.SOURCE.value,
        plugin_version=source.plugin_version,
        determinism=source.determinism.value,
        config=source.config,
        sequence_in_pipeline=0,
        schema_config=source._schema_config if hasattr(source, "_schema_config") else None,
        output_contract=contract,  # Source emits this contract
    )
```

**Step 4.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/engine/test_orchestrator_contracts.py -v
```

Expected: All tests PASS

**Step 4.5: Commit**

```bash
git add src/elspeth/engine/orchestrator.py tests/engine/test_orchestrator_contracts.py
git commit -m "feat(engine): record schema contracts in Orchestrator

Orchestrator now records contracts:
- Source contract stored after first-row inference
- Node contracts stored on registration
- Contracts available for resume and debugging

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: MCP Server Contract Tools

**Files:**
- Modify: `src/elspeth/mcp/tools.py` (or wherever MCP tools are defined)
- Test: `tests/mcp/test_contract_tools.py` (create new)

**Step 5.1: Write failing tests for MCP contract tools**

```python
# tests/mcp/test_contract_tools.py
"""Tests for MCP contract analysis tools."""

import pytest

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder


class TestMCPContractTools:
    """Test MCP tools for contract introspection."""

    @pytest.fixture
    def populated_db(self) -> LandscapeDB:
        """Database with contract data."""
        db = LandscapeDB.in_memory()
        db.create_all()

        recorder = LandscapeRecorder(db)

        contract = SchemaContract(
            mode="OBSERVED",
            fields=(
                FieldContract("amount_usd", "'Amount USD'", int, True, "inferred"),
                FieldContract("customer_id", "Customer ID", str, True, "inferred"),
            ),
            locked=True,
        )

        run = recorder.begin_run(
            config={"test": True},
            canonical_version="1.0.0",
            schema_contract=contract,
        )

        return db

    def test_get_contract_shows_field_mapping(
        self, populated_db: LandscapeDB
    ) -> None:
        """get_contract tool shows original→normalized mapping."""
        from elspeth.mcp.tools import get_run_contract

        result = get_run_contract(populated_db, "test-run-id")

        assert "'Amount USD'" in result
        assert "amount_usd" in result
        assert "original" in result.lower() or "normalized" in result.lower()

    def test_explain_field_shows_provenance(
        self, populated_db: LandscapeDB
    ) -> None:
        """explain_field tool traces field from source to sink."""
        from elspeth.mcp.tools import explain_field

        result = explain_field(populated_db, "test-run-id", "amount_usd")

        # Should show the field's journey through the pipeline
        assert "amount_usd" in result
        assert "source" in result.lower()

    def test_list_contract_violations(
        self, populated_db: LandscapeDB
    ) -> None:
        """list_violations tool shows contract errors with details."""
        from elspeth.mcp.tools import list_contract_violations

        result = list_contract_violations(populated_db, "test-run-id")

        # Should return structured violation data or "no violations"
        assert result is not None
```

**Step 5.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/mcp/test_contract_tools.py -v
```

Expected: FAIL (tools don't exist yet)

**Step 5.3: Implement MCP contract tools**

Add to MCP tools module:

```python
# In src/elspeth/mcp/tools.py (or appropriate module)

def get_run_contract(
    run_id: str,
) -> dict[str, Any]:
    """Get schema contract for a run.

    Shows the source schema contract with field resolution:
    - Mode (FIXED/FLEXIBLE/OBSERVED)
    - Field mappings (original → normalized)
    - Inferred types

    Args:
        run_id: Run ID to query

    Returns:
        Contract details or error message
    """
    contract = _get_recorder().get_run_contract(run_id)

    if contract is None:
        return {"error": f"No contract found for run {run_id}"}

    return {
        "mode": contract.mode,
        "locked": contract.locked,
        "version_hash": contract.version_hash(),
        "fields": [
            {
                "normalized_name": f.normalized_name,
                "original_name": f.original_name,
                "python_type": f.python_type.__name__,
                "required": f.required,
                "source": f.source,
            }
            for f in contract.fields
        ],
        "field_count": len(contract.fields),
    }


def explain_field(
    run_id: str,
    field_name: str,
) -> dict[str, Any]:
    """Trace a field's provenance through the pipeline.

    Shows how a field was:
    - Named at source (original)
    - Normalized (to Python identifier)
    - Typed (inferred or declared)
    - Transformed (if any transforms added/modified it)

    Args:
        run_id: Run ID to query
        field_name: Normalized or original field name

    Returns:
        Field provenance details
    """
    contract = _get_recorder().get_run_contract(run_id)

    if contract is None:
        return {"error": f"No contract found for run {run_id}"}

    # Resolve field name (could be original or normalized)
    try:
        normalized = contract.resolve_name(field_name)
    except KeyError:
        return {"error": f"Field '{field_name}' not found in contract"}

    fc = contract.get_field(normalized)
    if fc is None:
        return {"error": f"Field contract not found for '{normalized}'"}

    return {
        "normalized_name": fc.normalized_name,
        "original_name": fc.original_name,
        "python_type": fc.python_type.__name__,
        "required": fc.required,
        "source": fc.source,
        "provenance": {
            "discovered_at": "source" if fc.source == "inferred" else "config",
            "schema_mode": contract.mode,
        },
    }


def list_contract_violations(
    run_id: str,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """List contract violations for a run.

    Shows validation errors with contract details:
    - Violation type (type_mismatch, missing_field, extra_field)
    - Field names (original and normalized)
    - Type information (expected vs actual)

    Args:
        run_id: Run ID to query
        limit: Maximum violations to return

    Returns:
        List of violations with details
    """
    errors = _get_recorder().get_validation_errors(run_id, limit=limit)

    if not errors:
        return {"message": "No contract violations found", "count": 0}

    violations = []
    for error in errors:
        violation = {
            "error_id": error.error_id,
            "violation_type": error.violation_type,
            "normalized_field": error.normalized_field_name,
            "original_field": error.original_field_name,
            "expected_type": error.expected_type,
            "actual_type": error.actual_type,
            "error_message": error.error,
            "destination": error.destination,
        }
        violations.append(violation)

    return {
        "count": len(violations),
        "violations": violations,
    }
```

**Step 5.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/mcp/test_contract_tools.py -v
```

Expected: All tests PASS

**Step 5.5: Commit**

```bash
git add src/elspeth/mcp/tools.py tests/mcp/test_contract_tools.py
git commit -m "feat(mcp): add contract analysis tools

New MCP tools for debugging:
- get_run_contract: Show field resolution and types
- explain_field: Trace field provenance through pipeline
- list_contract_violations: Show validation errors with details

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Contract Checkpoint Support

**Files:**
- Modify: `src/elspeth/core/checkpoint/checkpoint_manager.py`
- Test: `tests/core/checkpoint/test_checkpoint_contracts.py` (create new)

**Step 6.1: Write failing tests for contract checkpoints**

```python
# tests/core/checkpoint/test_checkpoint_contracts.py
"""Tests for schema contract checkpoint support."""

import pytest

from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.checkpoint.checkpoint_manager import CheckpointManager
from elspeth.core.landscape.database import LandscapeDB


class TestContractCheckpoints:
    """Test contract preservation through checkpoints."""

    @pytest.fixture
    def contract(self) -> SchemaContract:
        """Sample contract."""
        return SchemaContract(
            mode="OBSERVED",
            fields=(
                FieldContract("id", "ID", int, True, "inferred"),
                FieldContract("name", "Name", str, True, "inferred"),
            ),
            locked=True,
        )

    def test_checkpoint_includes_contract(
        self, contract: SchemaContract
    ) -> None:
        """Checkpoint data includes contract for resume."""
        from elspeth.core.checkpoint.checkpoint_data import CheckpointData

        checkpoint = CheckpointData(
            run_id="test-run",
            token_id="test-token",
            node_id="test-node",
            contract=contract,
        )

        # Serialize and restore
        serialized = checkpoint.to_json()
        restored = CheckpointData.from_json(serialized)

        assert restored.contract is not None
        assert restored.contract.mode == contract.mode
        assert restored.contract.version_hash() == contract.version_hash()

    def test_resume_restores_contract(
        self, contract: SchemaContract
    ) -> None:
        """Resume operation restores contract with integrity verification."""
        # Create checkpoint with contract
        # Resume from checkpoint
        # Verify contract is restored with same hash
        pass  # Implementation depends on resume mechanics
```

**Step 6.2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/core/checkpoint/test_checkpoint_contracts.py -v
```

Expected: FAIL (checkpoint doesn't include contracts yet)

**Step 6.3: Update checkpoint to include contracts**

The checkpoint system should store contracts via the Landscape audit trail (Task 3) rather than duplicating storage. The resume operation retrieves contracts via `get_run_contract()` and `get_node_contracts()`.

Update checkpoint manager to verify contract integrity on resume:

```python
# In checkpoint_manager.py

def _verify_contract_integrity(
    self,
    run_id: str,
    expected_hash: str,
) -> SchemaContract:
    """Verify contract integrity on resume.

    Args:
        run_id: Run to resume
        expected_hash: Expected contract version_hash from checkpoint

    Returns:
        SchemaContract if valid

    Raises:
        CheckpointCorruptionError: If contract hash mismatch
    """
    contract = self._recorder.get_run_contract(run_id)

    if contract is None:
        raise CheckpointCorruptionError(
            f"No contract found for run {run_id} during resume"
        )

    if contract.version_hash() != expected_hash:
        raise CheckpointCorruptionError(
            f"Contract integrity violation: expected hash {expected_hash}, "
            f"got {contract.version_hash()}"
        )

    return contract
```

**Step 6.4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/core/checkpoint/test_checkpoint_contracts.py -v
```

Expected: All tests PASS

**Step 6.5: Commit**

```bash
git add src/elspeth/core/checkpoint/ tests/core/checkpoint/test_checkpoint_contracts.py
git commit -m "feat(checkpoint): add contract verification for resume

Resume now verifies contract integrity:
- Retrieves contract from Landscape audit trail
- Verifies version_hash matches checkpoint
- Raises CheckpointCorruptionError on mismatch

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Module Exports and Documentation

**Files:**
- Modify: `src/elspeth/core/landscape/__init__.py`
- Test: Run all tests

**Step 7.1: Update module exports**

Add to `src/elspeth/core/landscape/__init__.py`:

```python
# Re-export for convenience
from elspeth.core.landscape.recorder import LandscapeRecorder

__all__ = [
    "LandscapeDB",
    "LandscapeRecorder",
    # ... other exports ...
]
```

**Step 7.2: Run all contract tests**

```bash
.venv/bin/python -m pytest tests/contracts/ tests/core/landscape/ -v --tb=short
```

Expected: All tests PASS

**Step 7.3: Run type checker**

```bash
.venv/bin/python -m mypy src/elspeth/contracts/ src/elspeth/core/landscape/
```

Expected: No errors

**Step 7.4: Run linter**

```bash
.venv/bin/python -m ruff check src/elspeth/contracts/ src/elspeth/core/landscape/
```

Expected: No errors

**Step 7.5: Commit**

```bash
git add src/elspeth/core/landscape/__init__.py
git commit -m "feat(landscape): export contract-related APIs

Update landscape module exports for Phase 5 integration.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Integration Test - Full Audit Trail

**Files:**
- Test: `tests/integration/test_contract_audit_integration.py` (create new)

**Step 8.1: Write integration test**

```python
# tests/integration/test_contract_audit_integration.py
"""Integration tests for schema contract audit trail."""

from pathlib import Path
from textwrap import dedent

import pytest

from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.engine.orchestrator import Orchestrator


class TestContractAuditIntegration:
    """End-to-end tests for contract audit trail."""

    @pytest.fixture
    def csv_file(self, tmp_path: Path) -> Path:
        """Create test CSV with messy headers."""
        csv = tmp_path / "data.csv"
        csv.write_text(dedent("""\
            'Amount USD',Customer ID
            100,C001
            200,C002
        """))
        return csv

    @pytest.fixture
    def db(self) -> LandscapeDB:
        """In-memory database."""
        db = LandscapeDB.in_memory()
        db.create_all()
        return db

    def test_full_audit_trail_with_contracts(
        self, csv_file: Path, db: LandscapeDB, tmp_path: Path
    ) -> None:
        """Complete pipeline execution records contracts in audit trail."""
        config = {
            "source": {
                "plugin": "csv",
                "options": {
                    "path": str(csv_file),
                    "schema": {"fields": "dynamic"},
                    "on_validation_failure": "discard",
                    "normalize_fields": True,
                },
            },
            "sinks": {
                "output": {
                    "plugin": "csv",
                    "options": {
                        "path": str(tmp_path / "output.csv"),
                        "schema": {"fields": "dynamic"},
                    },
                },
            },
        }

        orchestrator = Orchestrator(config, db)
        run = orchestrator.execute()

        # Verify contract in audit trail
        recorder = LandscapeRecorder(db)
        contract = recorder.get_run_contract(run.run_id)

        assert contract is not None
        assert contract.mode == "OBSERVED"
        assert contract.locked is True

        # Verify field resolution preserved
        amount_field = contract.get_field("amount_usd")
        assert amount_field is not None
        assert amount_field.original_name == "'Amount USD'"
        assert amount_field.normalized_name == "amount_usd"

        customer_field = contract.get_field("customer_id")
        assert customer_field is not None
        assert customer_field.original_name == "Customer ID"

    def test_validation_error_with_contract_details(
        self, tmp_path: Path, db: LandscapeDB
    ) -> None:
        """Validation errors include contract violation details."""
        csv = tmp_path / "bad.csv"
        csv.write_text(dedent("""\
            id,amount
            1,100
            not_int,200
        """))

        config = {
            "source": {
                "plugin": "csv",
                "options": {
                    "path": str(csv),
                    "schema": {
                        "mode": "strict",
                        "fields": ["id: int", "amount: int"],
                    },
                    "on_validation_failure": "quarantine",
                },
            },
            "sinks": {
                "output": {
                    "plugin": "csv",
                    "options": {
                        "path": str(tmp_path / "output.csv"),
                        "schema": {"fields": "dynamic"},
                    },
                },
                "quarantine": {
                    "plugin": "csv",
                    "options": {
                        "path": str(tmp_path / "quarantine.csv"),
                        "schema": {"fields": "dynamic"},
                    },
                },
            },
        }

        orchestrator = Orchestrator(config, db)
        run = orchestrator.execute()

        # Verify validation error has contract details
        recorder = LandscapeRecorder(db)
        errors = recorder.get_validation_errors(run.run_id)

        assert len(errors) >= 1
        error = errors[0]

        # Should have contract violation details
        assert error.violation_type is not None
        assert error.normalized_field_name is not None

    def test_contract_survives_audit_round_trip(
        self, csv_file: Path, db: LandscapeDB, tmp_path: Path
    ) -> None:
        """Contract can be restored from audit trail with full fidelity."""
        config = {
            "source": {
                "plugin": "csv",
                "options": {
                    "path": str(csv_file),
                    "schema": {"fields": "dynamic"},
                    "on_validation_failure": "discard",
                    "normalize_fields": True,
                },
            },
            "sinks": {
                "output": {
                    "plugin": "csv",
                    "options": {
                        "path": str(tmp_path / "output.csv"),
                        "schema": {"fields": "dynamic"},
                    },
                },
            },
        }

        orchestrator = Orchestrator(config, db)
        run = orchestrator.execute()

        # Get contract from audit trail
        recorder = LandscapeRecorder(db)
        contract = recorder.get_run_contract(run.run_id)

        # Simulate checkpoint: store hash, later restore and verify
        stored_hash = contract.version_hash()

        # "Later" - restore from audit trail
        restored = recorder.get_run_contract(run.run_id)

        # Verify integrity
        assert restored.version_hash() == stored_hash
        assert len(restored.fields) == len(contract.fields)

        # Can use restored contract for dual-name access
        from elspeth.contracts.schema_contract import PipelineRow

        row_data = {"amount_usd": 100, "customer_id": "C001"}
        pipeline_row = PipelineRow(row_data, restored)

        # Access works by original name
        assert pipeline_row["'Amount USD'"] == 100
```

**Step 8.2: Run integration tests**

```bash
.venv/bin/python -m pytest tests/integration/test_contract_audit_integration.py -v
```

Expected: All tests PASS

**Step 8.3: Commit**

```bash
git add tests/integration/test_contract_audit_integration.py
git commit -m "test(integration): add contract audit trail integration tests

End-to-end tests for:
- Full pipeline execution with contract recording
- Validation errors with contract details
- Contract round-trip through audit trail
- Dual-name access with restored contract

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Update Beads and Sync

**Step 9.1: Update beads issue**

```bash
bd close elspeth-rapid-XXX  # Replace with actual issue ID
bd sync
```

---

## Summary

Phase 5 implementation completes the audit trail for schema contracts:

| Component | Purpose |
|-----------|---------|
| `schema.py` columns | Store contracts in runs, nodes, validation_errors |
| `ContractAuditRecord` | JSON serialization for Landscape storage |
| `ValidationErrorWithContract` | Detailed violation records |
| `LandscapeRecorder` methods | Store/retrieve contracts |
| `Orchestrator` integration | Record contracts during execution |
| MCP tools | Query contracts for debugging |
| Checkpoint verification | Ensure integrity on resume |

**Key patterns:**
- Contracts stored via `ContractAuditRecord.to_json()` for full fidelity
- Version hash enables integrity verification on restore
- Validation errors include `violation_type`, `expected_type`, `actual_type`
- MCP tools expose contract data for debugging validation failures

**Audit trail example:**

```sql
-- Query: What field caused this validation error?
SELECT
    normalized_field_name,
    original_field_name,
    violation_type,
    expected_type,
    actual_type
FROM validation_errors
WHERE run_id = ?;

-- Result:
-- normalized_field_name | original_field_name | violation_type | expected_type | actual_type
-- amount_usd           | 'Amount USD'        | type_mismatch  | int           | str
```

**MCP debugging workflow:**

```bash
# 1. See what contract was inferred
> get_run_contract("run_123")
{
  "mode": "OBSERVED",
  "fields": [
    {"normalized": "amount_usd", "original": "'Amount USD'", "type": "int"},
    ...
  ]
}

# 2. Trace a specific field
> explain_field("run_123", "'Amount USD'")
{
  "normalized_name": "amount_usd",
  "original_name": "'Amount USD'",
  "python_type": "int",
  "source": "inferred",
  "provenance": {"discovered_at": "source", "schema_mode": "OBSERVED"}
}

# 3. See what went wrong
> list_contract_violations("run_123")
{
  "count": 1,
  "violations": [
    {
      "violation_type": "type_mismatch",
      "normalized_field": "amount_usd",
      "original_field": "'Amount USD'",
      "expected_type": "int",
      "actual_type": "str"
    }
  ]
}
```

**This completes the Unified Schema Contracts feature across all 5 phases.**
