# tests/mcp/test_contract_tools.py
"""Tests for MCP server contract analysis tools.

Phase 5 Unified Schema Contracts: Task 5 - MCP Server Contract Tools
for debugging validation failures and tracing field provenance.
"""

from __future__ import annotations

from elspeth.contracts import (
    FieldContract,
    MissingFieldViolation,
    NodeType,
    SchemaContract,
    TypeMismatchViolation,
)
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.mcp.server import LandscapeAnalyzer

# Dynamic schema for tests that don't care about specific fields
DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


class TestGetRunContract:
    """Tests for get_run_contract() MCP tool."""

    def test_returns_contract_for_run_with_contract(self) -> None:
        """get_run_contract() returns contract details when stored."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        # Create contract
        contract = SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract(
                    normalized_name="customer_id",
                    original_name="Customer ID",
                    python_type=str,
                    required=True,
                    source="declared",
                ),
                FieldContract(
                    normalized_name="amount",
                    original_name="Amount USD",
                    python_type=int,
                    required=True,
                    source="declared",
                ),
            ),
            locked=True,
        )

        run = analyzer._recorder.begin_run(
            config={},
            canonical_version="v1",
            schema_contract=contract,
        )

        result = analyzer.get_run_contract(run.run_id)

        assert "error" not in result
        assert result["mode"] == "FIXED"
        assert result["locked"] is True
        assert len(result["fields"]) == 2

        # Check field details
        fields_by_name = {f["normalized_name"]: f for f in result["fields"]}
        assert "customer_id" in fields_by_name
        assert fields_by_name["customer_id"]["original_name"] == "Customer ID"
        assert fields_by_name["customer_id"]["python_type"] == "str"
        assert fields_by_name["customer_id"]["required"] is True
        assert fields_by_name["customer_id"]["source"] == "declared"

    def test_returns_error_for_run_without_contract(self) -> None:
        """get_run_contract() returns error when no contract stored."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        run = analyzer._recorder.begin_run(
            config={},
            canonical_version="v1",
        )

        result = analyzer.get_run_contract(run.run_id)

        assert "error" in result
        assert "no contract" in result["error"].lower()

    def test_returns_error_for_nonexistent_run(self) -> None:
        """get_run_contract() returns error for nonexistent run."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        result = analyzer.get_run_contract("nonexistent_run_id")

        assert "error" in result
        assert "not found" in result["error"].lower()


class TestExplainField:
    """Tests for explain_field() MCP tool."""

    def test_explains_field_by_normalized_name(self) -> None:
        """explain_field() returns provenance for normalized name."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        contract = SchemaContract(
            mode="OBSERVED",
            fields=(
                FieldContract(
                    normalized_name="amount_usd",
                    original_name="Amount USD",
                    python_type=float,
                    required=True,
                    source="inferred",
                ),
            ),
            locked=True,
        )

        run = analyzer._recorder.begin_run(
            config={},
            canonical_version="v1",
            schema_contract=contract,
        )

        result = analyzer.explain_field(run.run_id, "amount_usd")

        assert "error" not in result
        assert result["normalized_name"] == "amount_usd"
        assert result["original_name"] == "Amount USD"
        assert result["python_type"] == "float"
        assert result["source"] == "inferred"

    def test_explains_field_by_original_name(self) -> None:
        """explain_field() returns provenance for original name."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        contract = SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract(
                    normalized_name="customer_id",
                    original_name="Customer-ID",
                    python_type=str,
                    required=True,
                    source="declared",
                ),
            ),
            locked=True,
        )

        run = analyzer._recorder.begin_run(
            config={},
            canonical_version="v1",
            schema_contract=contract,
        )

        # Access by original name
        result = analyzer.explain_field(run.run_id, "Customer-ID")

        assert "error" not in result
        assert result["normalized_name"] == "customer_id"
        assert result["original_name"] == "Customer-ID"

    def test_returns_error_for_nonexistent_field(self) -> None:
        """explain_field() returns error for field not in contract."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        contract = SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract(
                    normalized_name="existing_field",
                    original_name="Existing Field",
                    python_type=str,
                    required=True,
                    source="declared",
                ),
            ),
            locked=True,
        )

        run = analyzer._recorder.begin_run(
            config={},
            canonical_version="v1",
            schema_contract=contract,
        )

        result = analyzer.explain_field(run.run_id, "nonexistent_field")

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_returns_error_for_run_without_contract(self) -> None:
        """explain_field() returns error when run has no contract."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        run = analyzer._recorder.begin_run(
            config={},
            canonical_version="v1",
        )

        result = analyzer.explain_field(run.run_id, "any_field")

        assert "error" in result
        assert "no contract" in result["error"].lower()


class TestListContractViolations:
    """Tests for list_contract_violations() MCP tool."""

    def test_lists_type_mismatch_violations(self) -> None:
        """list_contract_violations() returns type mismatch details."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        run = analyzer._recorder.begin_run(config={}, canonical_version="v1")

        # Register source node for FK constraint
        analyzer._recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
            node_id="source_1",
            sequence=0,
        )

        # Record a type mismatch violation
        violation = TypeMismatchViolation(
            normalized_name="amount",
            original_name="Amount",
            expected_type=int,
            actual_type=str,
            actual_value="not_a_number",
        )

        analyzer._recorder.record_validation_error(
            run_id=run.run_id,
            node_id="source_1",
            row_data={"amount": "not_a_number"},
            error="Type mismatch",
            schema_mode="fixed",
            destination="quarantine",
            contract_violation=violation,
        )

        result = analyzer.list_contract_violations(run.run_id)

        assert "error" not in result
        assert result["total_violations"] == 1
        assert len(result["violations"]) == 1

        v = result["violations"][0]
        assert v["violation_type"] == "type_mismatch"
        assert v["normalized_field_name"] == "amount"
        assert v["original_field_name"] == "Amount"
        assert v["expected_type"] == "int"
        assert v["actual_type"] == "str"

    def test_lists_missing_field_violations(self) -> None:
        """list_contract_violations() returns missing field details."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        run = analyzer._recorder.begin_run(config={}, canonical_version="v1")

        analyzer._recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
            node_id="source_1",
            sequence=0,
        )

        violation = MissingFieldViolation(
            normalized_name="customer_id",
            original_name="Customer ID",
        )

        analyzer._recorder.record_validation_error(
            run_id=run.run_id,
            node_id="source_1",
            row_data={},
            error="Missing required field",
            schema_mode="fixed",
            destination="discard",
            contract_violation=violation,
        )

        result = analyzer.list_contract_violations(run.run_id)

        assert result["total_violations"] == 1
        v = result["violations"][0]
        assert v["violation_type"] == "missing_field"
        assert v["normalized_field_name"] == "customer_id"
        assert v["original_field_name"] == "Customer ID"

    def test_returns_empty_list_for_run_without_violations(self) -> None:
        """list_contract_violations() returns empty list when no violations."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        run = analyzer._recorder.begin_run(config={}, canonical_version="v1")

        result = analyzer.list_contract_violations(run.run_id)

        assert "error" not in result
        assert result["total_violations"] == 0
        assert result["violations"] == []

    def test_respects_limit_parameter(self) -> None:
        """list_contract_violations() respects the limit parameter."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        run = analyzer._recorder.begin_run(config={}, canonical_version="v1")

        analyzer._recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
            node_id="source_1",
            sequence=0,
        )

        # Record multiple violations
        for i in range(5):
            violation = TypeMismatchViolation(
                normalized_name=f"field_{i}",
                original_name=f"Field {i}",
                expected_type=int,
                actual_type=str,
                actual_value="bad",
            )
            analyzer._recorder.record_validation_error(
                run_id=run.run_id,
                node_id="source_1",
                row_data={f"field_{i}": "bad"},
                error="Type mismatch",
                schema_mode="fixed",
                destination="quarantine",
                contract_violation=violation,
            )

        result = analyzer.list_contract_violations(run.run_id, limit=3)

        assert result["total_violations"] == 5  # Total count
        assert len(result["violations"]) == 3  # Limited results

    def test_returns_error_for_nonexistent_run(self) -> None:
        """list_contract_violations() returns error for nonexistent run."""
        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        result = analyzer.list_contract_violations("nonexistent_run")

        assert "error" in result
        assert "not found" in result["error"].lower()


class TestMCPToolIntegration:
    """Tests for MCP tool integration via the analyzer methods."""

    def test_get_run_contract_method_exists(self) -> None:
        """get_run_contract method exists on LandscapeAnalyzer."""
        # Verify the method exists and is callable
        assert hasattr(LandscapeAnalyzer, "get_run_contract")
        assert callable(LandscapeAnalyzer.get_run_contract)

    def test_explain_field_method_exists(self) -> None:
        """explain_field method exists on LandscapeAnalyzer."""
        assert hasattr(LandscapeAnalyzer, "explain_field")
        assert callable(LandscapeAnalyzer.explain_field)

    def test_list_contract_violations_method_exists(self) -> None:
        """list_contract_violations method exists on LandscapeAnalyzer."""
        assert hasattr(LandscapeAnalyzer, "list_contract_violations")
        assert callable(LandscapeAnalyzer.list_contract_violations)

    def test_contract_tools_return_json_serializable_results(self) -> None:
        """Contract tools return JSON-serializable results."""
        import json

        db = LandscapeDB.in_memory()
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._recorder = LandscapeRecorder(db)

        contract = SchemaContract(
            mode="FIXED",
            fields=(
                FieldContract(
                    normalized_name="test_field",
                    original_name="Test Field",
                    python_type=str,
                    required=True,
                    source="declared",
                ),
            ),
            locked=True,
        )

        run = analyzer._recorder.begin_run(
            config={},
            canonical_version="v1",
            schema_contract=contract,
        )

        # All results should be JSON-serializable
        contract_result = analyzer.get_run_contract(run.run_id)
        json.dumps(contract_result)  # Should not raise

        field_result = analyzer.explain_field(run.run_id, "test_field")
        json.dumps(field_result)  # Should not raise

        violations_result = analyzer.list_contract_violations(run.run_id)
        json.dumps(violations_result)  # Should not raise
