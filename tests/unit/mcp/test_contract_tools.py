# tests/unit/mcp/test_contract_tools.py
"""Tests for MCP server contract analysis tools -- method existence.

Migrated from tests/mcp/test_contract_tools.py.
Tests that require LandscapeDB (actual contract queries, SQL blocklist tests)
are deferred to integration tier.
"""

from elspeth.mcp.analyzer import LandscapeAnalyzer


class TestMCPToolIntegration:
    """Tests for MCP tool integration -- method existence checks."""

    def test_get_run_contract_method_exists(self) -> None:
        """get_run_contract method exists on LandscapeAnalyzer."""
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
