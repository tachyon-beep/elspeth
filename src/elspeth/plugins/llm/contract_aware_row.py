"""Contract-aware row wrapper for dual-name template access.

Enables Jinja2 templates to reference fields by either original or
normalized names, with O(1) resolution via SchemaContract.

This class is designed to be passed as the 'row' context variable
to Jinja2 templates, providing transparent name resolution.

Example:
    contract = SchemaContract(...)  # Has "'Amount USD'" -> "amount_usd"
    data = {"amount_usd": 100}
    row = ContractAwareRow(data, contract)

    # In template:
    {{ row["'Amount USD'"] }}  # Works - resolves to amount_usd
    {{ row.amount_usd }}       # Works - direct access
    {{ row["amount_usd"] }}    # Works - normalized name
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from elspeth.contracts.schema_contract import SchemaContract


class ContractAwareRow:
    """Row wrapper enabling dual-name access via SchemaContract.

    Intercepts __getitem__ and __getattr__ to resolve original or
    normalized field names to the underlying normalized data.

    Uses __slots__ for memory efficiency (no __dict__ per instance).
    This is important since we create one per row rendered.

    Attributes:
        _data: Underlying row data (normalized keys)
        _contract: Schema contract for name resolution
    """

    __slots__ = ("_contract", "_data")

    def __init__(self, data: dict[str, Any], contract: SchemaContract) -> None:
        """Initialize ContractAwareRow.

        Args:
            data: Row data with normalized field names as keys
            contract: Schema contract for dual-name resolution
        """
        self._data = data
        self._contract = contract

    def __getitem__(self, key: str) -> Any:
        """Access field by original OR normalized name.

        Args:
            key: Field name (either form)

        Returns:
            Field value

        Raises:
            KeyError: If field not found in contract or data
        """
        normalized = self._contract.resolve_name(key)
        return self._data[normalized]

    def __getattr__(self, key: str) -> Any:
        """Dot notation access: row.field_name.

        Only works for normalized names (Python identifiers).
        Original names with special characters must use bracket notation.

        Args:
            key: Normalized field name

        Returns:
            Field value

        Raises:
            AttributeError: If field not found or is private
        """
        # Private attributes should not be delegated
        if key.startswith("_"):
            raise AttributeError(key)

        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __contains__(self, key: str) -> bool:
        """Check if field exists (by either name form).

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

    def __iter__(self) -> Iterator[str]:
        """Iterate over normalized field names.

        Yields:
            Normalized field names (for Jinja2 iteration)
        """
        return iter(self._data)

    def keys(self) -> list[str]:
        """Return normalized field names.

        Returns:
            List of normalized field names
        """
        return list(self._data.keys())

    def get(self, key: str, default: Any = None) -> Any:
        """Get field value with optional default.

        Supports dual-name resolution like __getitem__.

        Args:
            key: Field name (original or normalized)
            default: Value to return if field not found

        Returns:
            Field value or default
        """
        try:
            return self[key]
        except KeyError:
            return default

    @property
    def contract(self) -> SchemaContract:
        """Access the schema contract (for introspection)."""
        return self._contract

    def to_dict(self) -> dict[str, Any]:
        """Export raw data (normalized keys) for hashing.

        Returns:
            Copy of underlying data dict
        """
        return dict(self._data)
