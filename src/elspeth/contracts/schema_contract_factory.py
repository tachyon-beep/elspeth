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
    config: SchemaConfig,
    field_resolution: dict[str, str] | None = None,
) -> SchemaContract:
    """Create SchemaContract from SchemaConfig.

    For explicit schemas (strict/free), creates a locked contract with
    declared fields. For dynamic schemas, creates an unlocked contract
    that will infer types from the first row.

    Args:
        config: Schema configuration from YAML
        field_resolution: Optional mapping of original->normalized names.
            If provided, original_name on FieldContract will use the
            original header; otherwise, original_name = normalized_name.

    Returns:
        SchemaContract ready for validation
    """
    mode = map_schema_mode(config.mode)

    # Build reverse mapping for looking up original names
    # field_resolution is original->normalized, we need normalized->original
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
