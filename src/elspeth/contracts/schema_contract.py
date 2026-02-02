"""Schema contracts for preserving type and name information through the pipeline.

This module implements the Unified Schema Contracts design:
- FieldContract: Immutable field metadata (normalized name, original name, type)
- SchemaContract: Per-node schema with O(1) name resolution
- PipelineRow: Row wrapper enabling dual-name access

Design doc: docs/plans/2026-02-02-unified-schema-contracts-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


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
    """

    normalized_name: str
    original_name: str
    python_type: type
    required: bool
    source: Literal["declared", "inferred"]


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
        """Build O(1) lookup indices after initialization."""
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
