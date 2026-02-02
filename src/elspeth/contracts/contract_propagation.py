"""Contract propagation through transform pipeline.

Contracts flow through the pipeline, carrying field metadata (types,
original names) from source to sink. Transforms may add fields, which
get inferred types, or remove fields (narrowing the contract).
"""

from __future__ import annotations

from typing import Any, Literal

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
        # Passthrough - same contract
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
                    required=False,  # Inferred fields are never required
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
    mode_order: dict[Literal["FIXED", "FLEXIBLE", "OBSERVED"], int] = {
        "FIXED": 0,
        "FLEXIBLE": 1,
        "OBSERVED": 2,
    }
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
