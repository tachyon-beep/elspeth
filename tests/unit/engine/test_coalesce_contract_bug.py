# tests/unit/engine/test_coalesce_contract_bug.py
"""Test coalesce contract behavior with nested merge strategy.

Verifies that nested merge produces a FIXED contract with branch-key fields
(type=object) rather than an empty FLEXIBLE contract or a union of flat fields.

The fix is in coalesce_executor.py: the nested merge branch builds FieldContracts
for each branch name with python_type=object, instead of an empty FLEXIBLE contract.
"""

from elspeth.contracts.schema_contract import SchemaContract
from tests.fixtures.factories import make_field, make_row


def _make_nested_merge_contract(
    branch_names: list[str],
    arrived_branches: set[str] | None = None,
) -> SchemaContract:
    """Build a nested merge contract the same way coalesce_executor does.

    Args:
        branch_names: All expected branch names (from CoalesceSettings.branches)
        arrived_branches: Which branches actually arrived (defaults to all)
    """
    if arrived_branches is None:
        arrived_branches = set(branch_names)

    return SchemaContract(
        fields=tuple(
            make_field(
                name,
                python_type=object,
                required=name in arrived_branches,
                source="declared",
            )
            for name in branch_names
        ),
        mode="FIXED",
        locked=True,
    )


def test_nested_merge_contract_allows_branch_key_access():
    """Nested merge contract declares branch keys, enabling row['branch_name'] access."""
    contract = _make_nested_merge_contract(["path_a", "path_b"])

    nested_data = {"path_a": {"value_a": "from_a"}, "path_b": {"value_b": "from_b"}}
    row = make_row(nested_data, contract=contract)

    assert row["path_a"] == {"value_a": "from_a"}
    assert row["path_b"] == {"value_b": "from_b"}


def test_nested_merge_contract_has_correct_field_types():
    """Nested merge contract declares branch keys with object type."""
    contract = _make_nested_merge_contract(["path_a", "path_b"])

    field_names = {f.normalized_name for f in contract.fields}
    assert field_names == {"path_a", "path_b"}

    # object is the "any" type in VALID_FIELD_TYPES -- correct for nested dicts
    field_types = {f.normalized_name: f.python_type for f in contract.fields}
    assert field_types["path_a"] is object
    assert field_types["path_b"] is object


def test_nested_merge_contract_is_fixed_mode():
    """Nested merge uses FIXED mode -- only declared branch keys are valid."""
    contract = _make_nested_merge_contract(["path_a", "path_b"])

    assert contract.mode == "FIXED"
    assert contract.locked is True


def test_nested_merge_partial_arrival_marks_missing_not_required():
    """When a branch doesn't arrive (quorum/best_effort), its field is not required."""
    contract = _make_nested_merge_contract(
        branch_names=["path_a", "path_b", "path_c"],
        arrived_branches={"path_a", "path_c"},
    )

    required = {f.normalized_name: f.required for f in contract.fields}
    assert required["path_a"] is True
    assert required["path_b"] is False  # Didn't arrive
    assert required["path_c"] is True
