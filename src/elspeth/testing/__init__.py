# src/elspeth/testing/__init__.py
"""Test infrastructure for ELSPETH pipelines.

This package contains tools for testing ELSPETH pipelines at scale:

- chaosllm: Fake LLM server for load testing and fault injection
- chaosllm_mcp: MCP server for analyzing ChaosLLM test results
- make_pipeline_row: Shared helper for creating PipelineRow test data
"""

from __future__ import annotations

from typing import Any

from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


def make_pipeline_row(data: dict[str, Any]) -> PipelineRow:
    """Create a PipelineRow with an OBSERVED schema contract for testing.

    Builds a contract where every key in ``data`` becomes an inferred,
    optional field typed as ``object``.  This is the standard test helper
    used across the entire test suite.

    Args:
        data: Row data as a plain dict.

    Returns:
        PipelineRow wrapping *data* with a locked OBSERVED contract.
    """
    fields = tuple(
        FieldContract(
            normalized_name=k,
            original_name=k,
            python_type=object,
            required=False,
            source="inferred",
        )
        for k in data
    )
    contract = SchemaContract(mode="OBSERVED", fields=fields, locked=True)
    return PipelineRow(data=data, contract=contract)
