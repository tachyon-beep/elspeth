"""Integration test for BatchReplicate contract provision during token expansion.

Verifies fix for bug where batch_replicate.process() returned TransformResult.success_multi()
without a contract, causing ValueError at processor.py:1826-1830 during token expansion.
"""

from __future__ import annotations

from elspeth.contracts import PipelineRow
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.contracts.plugin_context import PluginContext
from elspeth.plugins.transforms.batch_replicate import BatchReplicate


def test_batch_replicate_returns_contract_with_multi_row_output():
    """BatchReplicate provides contract when returning multi-row output.

    The processor requires multi-row transforms to provide contracts (processor.py:1826-1830).
    Without this, pipelines using batch_replicate with output_mode="transform" would crash
    with: ValueError: Transform batch_replicate produced multi-row output but returned no contract.

    This test verifies the fix at batch_replicate.py:163-178 that creates an OBSERVED
    contract from the first output row.
    """
    # Create transform
    transform = BatchReplicate(
        {
            "schema": {"mode": "observed"},
            "copies_field": "copies",
        }
    )

    # Create input as list (batch-aware mode)
    rows = [
        {"id": 1, "copies": 2},
        {"id": 2, "copies": 3},
    ]

    # Create PipelineRow instances with minimal contract
    pipeline_rows = []
    for row in rows:
        fields = tuple(
            FieldContract(
                normalized_name=key,
                original_name=key,
                python_type=object,
                required=False,
                source="inferred",
            )
            for key in row
        )
        contract = SchemaContract(mode="OBSERVED", fields=fields, locked=True)
        pipeline_rows.append(PipelineRow(data=row, contract=contract))

    # Process batch
    ctx = PluginContext(run_id="test-run", config={})
    result = transform.process(pipeline_rows, ctx)

    # Verify multi-row result
    assert result.is_multi_row, "Should return multi-row result"
    assert result.rows is not None, "Rows should not be None"
    assert len(result.rows) == 5, f"Expected 5 output rows (2+3), got {len(result.rows)}"

    # CRITICAL: Verify contract is provided
    # Without this, processor.py:1826-1830 would raise ValueError
    assert result.contract is not None, (
        "BatchReplicate MUST provide contract for multi-row output. Missing contract causes ValueError during token expansion in processor."
    )

    # Verify contract is OBSERVED mode (correct for inferred fields)
    assert result.contract.mode == "OBSERVED", "Contract should be OBSERVED mode"

    # Verify contract includes all output fields
    # BatchReplicate adds copy_index by default
    expected_fields = {"id", "copies", "copy_index"}
    contract_field_names = {fc.normalized_name for fc in result.contract.fields}
    assert contract_field_names == expected_fields, (
        f"Contract should include all output fields. Expected {expected_fields}, got {contract_field_names}"
    )

    # Verify all fields are marked as inferred (OBSERVED mode pattern)
    for field in result.contract.fields:
        assert field.source == "inferred", f"Field {field.normalized_name} should be inferred"
        assert field.python_type is object, f"Field {field.normalized_name} should have object type"


def test_batch_replicate_contract_empty_output():
    """BatchReplicate returns marker row for empty batch (not multi-row)."""
    transform = BatchReplicate(
        {
            "schema": {"mode": "observed"},
            "copies_field": "copies",
            "default_copies": 1,
        }
    )

    # Empty batch
    ctx = PluginContext(run_id="test-run", config={})
    result = transform.process([], ctx)

    # Empty batches return a marker row (single-row success), not multi-row
    # This is correct behavior per the plugin's empty batch handling
    assert not result.is_multi_row, "Empty batch should return marker row, not multi-row"
    assert result.row is not None, "Should return marker row"
    assert result.row.get("batch_empty") is True, "Marker should indicate empty batch"
