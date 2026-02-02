"""Schema contracts for preserving type and name information through the pipeline.

This module implements the Unified Schema Contracts design:
- FieldContract: Immutable field metadata (normalized name, original name, type)
- SchemaContract: Per-node schema with O(1) name resolution
- PipelineRow: Row wrapper enabling dual-name access

Design doc: docs/plans/2026-02-02-unified-schema-contracts-design.md
"""

from __future__ import annotations

import hashlib
import types
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from elspeth.contracts.errors import (
    ContractMergeError,
    ContractViolation,
    ExtraFieldViolation,
    MissingFieldViolation,
    TypeMismatchViolation,
)
from elspeth.contracts.type_normalization import normalize_type_for_contract

# Types that can be serialized in checkpoint and restored in from_checkpoint()
# Must match type_map in SchemaContract.from_checkpoint()
VALID_FIELD_TYPES: frozenset[type] = frozenset(
    {
        int,
        str,
        float,
        bool,
        type(None),
        datetime,
        object,  # 'any' type for fields that accept any value
    }
)


@dataclass(frozen=True, slots=True)
class FieldContract:
    """A field in the schema contract.

    Immutable after creation - type locking means no mutation.
    Uses frozen dataclass pattern for checkpoint safety.

    Attributes:
        normalized_name: Dict key / Python identifier (e.g., "important_data")
        original_name: Display name from source (e.g., "'Important - Data !!'")
        python_type: Python primitive type (int, str, float, bool, datetime, type(None), object)
        required: Whether field must be present in row
        source: "declared" (from config) or "inferred" (from first row observation)
    """

    normalized_name: str
    original_name: str
    python_type: type
    required: bool
    source: Literal["declared", "inferred"]

    def __post_init__(self) -> None:
        """Validate python_type is checkpoint-serializable.

        Raises:
            TypeError: If python_type is not in VALID_FIELD_TYPES
        """
        if self.python_type not in VALID_FIELD_TYPES:
            raise TypeError(
                f"Invalid python_type '{self.python_type.__name__}' for FieldContract. "
                f"Valid types: {', '.join(sorted(t.__name__ for t in VALID_FIELD_TYPES))}."
            )


@dataclass(frozen=True, slots=True)
class SchemaContract:
    """Immutable schema contract for a node.

    Uses frozen dataclass pattern - all "mutations" return new instances.

    Attributes:
        mode: Schema enforcement mode
            - FIXED: Exact fields only, extras rejected
            - FLEXIBLE: Declared minimum + inferred extras allowed
            - OBSERVED: All fields observed/inferred from data
        fields: Immutable tuple of FieldContract instances
        locked: True after first row processed (types frozen)
    """

    mode: Literal["FIXED", "FLEXIBLE", "OBSERVED"]
    fields: tuple[FieldContract, ...]
    locked: bool = False

    # Computed indices - populated in __post_init__
    _by_normalized: dict[str, FieldContract] = field(default_factory=dict, repr=False, compare=False, hash=False)
    _by_original: dict[str, str] = field(default_factory=dict, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        """Build O(1) lookup indices after initialization.

        Raises:
            ValueError: If duplicate normalized_name found in fields
        """
        # Defense-in-depth: validate uniqueness before building indices
        # (with_field() also checks, but direct construction must be safe)
        normalized_names = [fc.normalized_name for fc in self.fields]
        if len(normalized_names) != len(set(normalized_names)):
            duplicates = [n for n in normalized_names if normalized_names.count(n) > 1]
            raise ValueError(f"Duplicate normalized_name in fields: {set(duplicates)}")

        by_norm = {fc.normalized_name: fc for fc in self.fields}
        by_orig = {fc.original_name: fc.normalized_name for fc in self.fields}
        object.__setattr__(self, "_by_normalized", by_norm)
        object.__setattr__(self, "_by_original", by_orig)

    def resolve_name(self, key: str) -> str:
        """Resolve original or normalized name to normalized name.

        O(1) lookup via precomputed indices.

        Args:
            key: Either an original_name or normalized_name

        Returns:
            The normalized_name for the field

        Raises:
            KeyError: If the key is not found in the schema
        """
        if key in self._by_normalized:
            return key  # Already normalized
        if key in self._by_original:
            return self._by_original[key]
        raise KeyError(f"'{key}' not found in schema contract")

    def get_field(self, normalized_name: str) -> FieldContract | None:
        """Get FieldContract by normalized name.

        Args:
            normalized_name: The normalized field name to look up

        Returns:
            The FieldContract if found, None otherwise
        """
        return self._by_normalized.get(normalized_name)

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
            TypeError: If field already exists (duplicate prevention)
            ValueError: If value is NaN or Infinity
        """
        # Always check for duplicates - prevents broken O(1) lookup invariant
        # Per CLAUDE.md: Adding duplicate is a bug in caller code
        if normalized in self._by_normalized:
            raise TypeError(f"Field '{original}' ({normalized}) already exists in contract")

        new_field = FieldContract(
            normalized_name=normalized,
            original_name=original,
            python_type=normalize_type_for_contract(value),
            required=False,  # Inferred fields are never required
            source="inferred",
        )
        return SchemaContract(
            mode=self.mode,
            fields=(*self.fields, new_field),
            locked=self.locked,
        )

    def validate(self, row: dict[str, Any]) -> list[ContractViolation]:
        """Validate row data against contract.

        Checks:
        1. Required fields are present
        2. Field types match (with numpy/pandas normalization)
        3. FIXED mode: No extra fields allowed

        Note: Fields with python_type=object ('any' type) skip type validation
        since they accept any value type by design.

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
                # Skip type check for 'any' fields (python_type is object)
                # 'any' type accepts any value - existence check above is sufficient
                if fc.python_type is object:
                    continue

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

    def version_hash(self) -> str:
        """Deterministic hash of contract for checkpoint references.

        Uses canonical JSON of field definitions for reproducibility.
        The hash is truncated to 16 hex characters (64 bits).

        Returns:
            16-character hex hash string
        """
        from elspeth.core.canonical import canonical_json

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
            "object": object,  # For 'any' type fields that accept any value
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
        # Per CLAUDE.md: "Bad data in the audit trail = crash immediately"
        # to_checkpoint_format() ALWAYS writes version_hash, so missing = corruption
        expected_hash = data["version_hash"]  # KeyError if missing = correct!
        actual_hash = contract.version_hash()
        if actual_hash != expected_hash:
            raise ValueError(
                f"Contract integrity violation: hash mismatch. "
                f"Expected {expected_hash}, got {actual_hash}. "
                f"Checkpoint may be corrupted or from different version."
            )

        return contract

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
        # Mode precedence: FIXED > FLEXIBLE > OBSERVED
        mode_order: dict[str, int] = {"FIXED": 0, "FLEXIBLE": 1, "OBSERVED": 2}
        merged_mode = min(
            self.mode,
            other.mode,
            key=lambda m: mode_order[m],
        )

        # Build merged field set
        merged_fields: dict[str, FieldContract] = {}

        all_names = {fc.normalized_name for fc in self.fields} | {fc.normalized_name for fc in other.fields}

        for name in all_names:
            in_self = name in self._by_normalized
            in_other = name in other._by_normalized

            if in_self and in_other:
                self_fc = self._by_normalized[name]
                other_fc = other._by_normalized[name]
                # Both have field - types must match
                if self_fc.python_type != other_fc.python_type:
                    raise ContractMergeError(
                        field=name,
                        type_a=self_fc.python_type.__name__,
                        type_b=other_fc.python_type.__name__,
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
            elif in_self:
                # Only in self - include but mark non-required
                fc = self._by_normalized[name]
                merged_fields[name] = FieldContract(
                    normalized_name=fc.normalized_name,
                    original_name=fc.original_name,
                    python_type=fc.python_type,
                    required=False,  # Can't require field from only one path
                    source=fc.source,
                )
            else:
                # Only in other (in_other must be True since name came from union)
                fc = other._by_normalized[name]
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


class PipelineRow:
    """Row wrapper that enables dual-name access and type tracking.

    Wraps row data with a SchemaContract reference, enabling:
    - Access by normalized name: row["amount_usd"] or row.amount_usd
    - Access by original name: row["'Amount USD'"]
    - Type tracking via contract reference
    - Checkpoint serialization

    Uses __slots__ for memory efficiency (no __dict__ per instance).
    """

    __slots__ = ("_contract", "_data")

    def __init__(self, data: dict[str, Any], contract: SchemaContract) -> None:
        """Initialize PipelineRow.

        Args:
            data: Row data with normalized field names as keys
            contract: Schema contract for name resolution and validation
        """
        # Store as immutable view to prevent mutation after audit recording
        # Per CLAUDE.md Tier 1: audit data must not be modified
        self._data = types.MappingProxyType(dict(data))
        self._contract = contract

    def __setitem__(self, key: str, value: Any) -> None:
        """Raise TypeError - PipelineRow is immutable.

        Args:
            key: Field name
            value: Value to set

        Raises:
            TypeError: Always - PipelineRow is immutable for audit integrity
        """
        raise TypeError("PipelineRow is immutable - cannot modify audit data")

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
            "data": dict(self._data),  # Convert MappingProxyType to dict for serialization
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
