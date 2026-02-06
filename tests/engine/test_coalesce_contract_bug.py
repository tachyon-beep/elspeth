"""Test case for coalesce contract behavior with nested/select merge strategies.

P2 Bug (documented in code review):
- Coalesce with merge="nested" creates data like {branch_a: {...}, branch_b: {...}}
- But the contract is a union of all branch fields, not the nested structure
- Downstream transforms fail with KeyError when accessing row['branch_a']

These tests use @pytest.mark.xfail(strict=True) to document expected behavior.
When the bug is fixed, the tests will pass and strict=True will cause pytest to
fail - alerting the fixer to remove the xfail marker.
"""

import pytest

from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


def _make_branch_contracts() -> tuple[SchemaContract, SchemaContract]:
    """Create sample contracts for two branches."""
    contract_a = SchemaContract(
        fields=(
            FieldContract(
                original_name="value_a",
                normalized_name="value_a",
                python_type=str,
                required=True,
                source="inferred",
            ),
        ),
        mode="FIXED",
    )
    contract_b = SchemaContract(
        fields=(
            FieldContract(
                original_name="value_b",
                normalized_name="value_b",
                python_type=str,
                required=True,
                source="inferred",
            ),
        ),
        mode="FIXED",
    )
    return contract_a, contract_b


@pytest.mark.xfail(
    strict=True,
    reason="P2 bug: nested merge contract should have branch keys (path_a, path_b), not original fields",
)
def test_nested_merge_contract_allows_branch_key_access():
    """For nested merge, contract should allow access to branch keys.

    Expected correct behavior:
    - Nested merge creates data: {"path_a": {...}, "path_b": {...}}
    - Contract should declare path_a and path_b as valid keys
    - row["path_a"] should return the nested dict for that branch

    Current broken behavior:
    - Contract has original fields (value_a, value_b) instead of branch keys
    - row["path_a"] raises KeyError
    """
    contract_a, contract_b = _make_branch_contracts()

    # Current behavior: merge() unions the field names
    # BUG: For nested merge, contract should have path_a/path_b keys instead
    merged_contract = contract_a.merge(contract_b)

    # Nested merge creates this data shape
    nested_data = {"path_a": {"value_a": "from_a"}, "path_b": {"value_b": "from_b"}}

    # Create PipelineRow with the (currently wrong) merged contract
    row = PipelineRow(nested_data, merged_contract)

    # EXPECTED: This should work - path_a is a valid key in nested merge output
    # ACTUAL: Raises KeyError because contract doesn't have path_a
    branch_a_data = row["path_a"]
    assert branch_a_data == {"value_a": "from_a"}

    branch_b_data = row["path_b"]
    assert branch_b_data == {"value_b": "from_b"}


@pytest.mark.xfail(
    strict=True,
    reason="P2 bug: nested merge contract should declare nested dict types for branch keys",
)
def test_nested_merge_contract_has_correct_field_types():
    """For nested merge, contract field types should reflect the nested structure.

    Expected correct behavior:
    - Contract for nested merge should have fields like:
      - path_a: dict (containing value_a)
      - path_b: dict (containing value_b)

    Current broken behavior:
    - Contract has flat fields (value_a: str, value_b: str)
    - No representation of the nested structure
    """
    contract_a, contract_b = _make_branch_contracts()
    merged_contract = contract_a.merge(contract_b)

    # EXPECTED: Contract should have path_a and path_b fields
    field_names = {f.normalized_name for f in merged_contract.fields}

    # These assertions describe the CORRECT behavior we want
    assert "path_a" in field_names, "Nested merge contract should have path_a field"
    assert "path_b" in field_names, "Nested merge contract should have path_b field"
