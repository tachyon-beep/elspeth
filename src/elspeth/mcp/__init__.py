# src/elspeth/mcp/__init__.py
"""MCP (Model Context Protocol) server for ELSPETH Landscape analysis.

Provides read-only tools for querying the audit database:
- list_runs: List all pipeline runs
- get_run: Get details of a specific run
- get_run_summary: Statistics for a run
- list_rows: List rows for a run
- explain_token: Complete lineage for a token
- get_errors: Get validation and transform errors
- query: Execute read-only SQL queries
"""

from elspeth.mcp.server import create_server, main

__all__ = ["create_server", "main"]
