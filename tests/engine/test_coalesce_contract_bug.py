"""Test case demonstrating coalesce contract mismatch for nested/select merge strategies.

This test reproduces the P2 bug identified in code review:
- Coalesce with merge="nested" creates data like {branch_a: {...}, branch_b: {...}}
- But the contract is a union of all branch fields, not the nested structure
- Downstream transforms fail with KeyError when accessing row['branch_a']
"""

import pytest

from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract

# Integration tests are commented out pending decision on test fixtures
# These demonstrate the bug but require more complex setup

# def test_coalesce_nested_with_downstream_transform_fails(tmp_path, mock_clock):
#     """Reproduce P2: nested merge creates data with branch keys, but contract has original fields."""
#     pass

# def test_coalesce_select_with_downstream_transform_fails(tmp_path, mock_clock):
#     """Reproduce P2: select merge returns selected branch data, but contract has all branch fields."""
#     pass


def test_pipeline_row_nested_access_demonstrates_bug():
    """Unit test demonstrating the contract/data mismatch for nested merge.

    This test PASSES to demonstrate the bug exists:
    - Contract describes pre-merge structure (value_a, value_b)
    - Data has post-merge structure (path_a, path_b)
    - Both forms of access fail - the data is unusable!

    Expected behavior after fix:
    - This test should FAIL because the contract should match the actual data shape
    - For nested merge, contract should have path_a and path_b keys
    """

    # Create contracts for two branches
    contract_a = SchemaContract(
        fields=[
            FieldContract(
                original_name="value_a",
                normalized_name="value_a",
                python_type=str,
                required=True,
                source="inferred",
            )
        ],
        mode="FIXED",
    )
    contract_b = SchemaContract(
        fields=[
            FieldContract(
                original_name="value_b",
                normalized_name="value_b",
                python_type=str,
                required=True,
                source="inferred",
            )
        ],
        mode="FIXED",
    )

    # Merge contracts (what coalesce does now - WRONG for nested merge)
    merged_contract = contract_a.merge(contract_b)
    # merged_contract has fields: value_a, value_b (WRONG - should be path_a, path_b)

    # Nested merge creates this data shape:
    nested_data = {"path_a": {"value_a": "from_a"}, "path_b": {"value_b": "from_b"}}

    # Create PipelineRow with mismatched contract
    row = PipelineRow(nested_data, merged_contract)

    # BUG: Both accesses fail because contract doesn't match data!
    # Try to access branch keys - fails because contract doesn't have path_a
    with pytest.raises(KeyError, match="path_a"):
        _ = row["path_a"]

    # Try to access original fields - fails because data doesn't have value_a at top level
    with pytest.raises(KeyError, match="value_a"):
        _ = row["value_a"]

    # The data is completely inaccessible - this is the bug!
