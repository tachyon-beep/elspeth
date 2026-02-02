"""Contract builder for first-row inference and locking.

Handles the "infer-and-lock" pattern for OBSERVED and FLEXIBLE modes:
1. First row arrives
2. Types are inferred from values
3. Contract is locked
4. Subsequent rows validate against locked contract
"""

from __future__ import annotations

from typing import Any

from elspeth.contracts.schema_contract import SchemaContract


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
            field_resolution: Mapping of original->normalized names

        Returns:
            Locked SchemaContract with all field types defined

        Raises:
            ValueError: If row contains NaN or Infinity values
        """
        # Already locked - nothing to do
        if self._contract.locked:
            return self._contract

        # Build reverse mapping: normalized -> original
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
