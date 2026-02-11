# src/elspeth/mcp/analyzers/queries.py
"""Core CRUD query functions for the Landscape audit database.

Functions: list_runs, get_run, list_rows, list_nodes, list_tokens,
list_operations, get_operation_calls, get_node_states, get_calls, query.

All functions accept (db, recorder) as their first two parameters.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.formatters import dataclass_to_dict, serialize_datetime
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.mcp.types import (
    CallDetail,
    NodeDetail,
    NodeStateRecord,
    OperationCallRecord,
    OperationRecord,
    RowRecord,
    RunDetail,
    RunRecord,
    TokenRecord,
)

_serialize_datetime = serialize_datetime
_dataclass_to_dict = dataclass_to_dict


def list_runs(db: LandscapeDB, recorder: LandscapeRecorder, limit: int = 50, status: str | None = None) -> list[RunRecord]:
    """List pipeline runs.

    Args:
        db: Database connection
        recorder: Landscape recorder
        limit: Maximum number of runs to return (default 50)
        status: Filter by status (PENDING, RUNNING, COMPLETED, FAILED)

    Returns:
        List of run records with id, status, timestamps
    """
    from sqlalchemy import select

    from elspeth.contracts import RunStatus
    from elspeth.core.landscape.schema import runs_table

    with db.connection() as conn:
        query = select(runs_table).order_by(runs_table.c.started_at.desc()).limit(limit)

        if status is not None:
            # Validate status
            try:
                RunStatus(status)
            except ValueError:
                valid = [s.value for s in RunStatus]
                raise ValueError(f"Invalid status '{status}'. Valid: {valid}") from None
            query = query.where(runs_table.c.status == status)

        rows = conn.execute(query).fetchall()

    return [
        {
            "run_id": row.run_id,
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "config_hash": row.config_hash,
            "export_status": row.export_status,
        }
        for row in rows
    ]


def get_run(db: LandscapeDB, recorder: LandscapeRecorder, run_id: str) -> RunDetail | None:
    """Get details of a specific run.

    Args:
        db: Database connection
        recorder: Landscape recorder
        run_id: The run ID to retrieve

    Returns:
        Run record or None if not found
    """
    run = recorder.get_run(run_id)
    if run is None:
        return None
    return cast(RunDetail, _dataclass_to_dict(run))


def list_rows(db: LandscapeDB, recorder: LandscapeRecorder, run_id: str, limit: int = 100, offset: int = 0) -> list[RowRecord]:
    """List source rows for a run.

    Args:
        db: Database connection
        recorder: Landscape recorder
        run_id: Run ID to query
        limit: Maximum rows to return (default 100)
        offset: Number of rows to skip (default 0)

    Returns:
        List of row records
    """
    from sqlalchemy import select

    from elspeth.core.landscape.schema import rows_table

    with db.connection() as conn:
        query = select(rows_table).where(rows_table.c.run_id == run_id).order_by(rows_table.c.row_index).limit(limit).offset(offset)
        rows = conn.execute(query).fetchall()

    return [
        {
            "row_id": row.row_id,
            "run_id": row.run_id,
            "source_node_id": row.source_node_id,
            "row_index": row.row_index,
            "source_data_hash": row.source_data_hash,
            "source_data_ref": row.source_data_ref,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def list_nodes(db: LandscapeDB, recorder: LandscapeRecorder, run_id: str) -> list[NodeDetail]:
    """List all nodes (plugin instances) for a run.

    Args:
        db: Database connection
        recorder: Landscape recorder
        run_id: Run ID to query

    Returns:
        List of node records with plugin info
    """
    nodes = recorder.get_nodes(run_id)
    return [_dataclass_to_dict(node) for node in nodes]


def list_tokens(
    db: LandscapeDB,
    recorder: LandscapeRecorder,
    run_id: str,
    row_id: str | None = None,
    limit: int = 100,
) -> list[TokenRecord]:
    """List tokens for a run or specific row.

    Args:
        db: Database connection
        recorder: Landscape recorder
        run_id: Run ID to query
        row_id: Optional row ID to filter by
        limit: Maximum tokens to return

    Returns:
        List of token records
    """
    from sqlalchemy import select

    from elspeth.core.landscape.schema import rows_table, tokens_table

    with db.connection() as conn:
        query = (
            select(tokens_table)
            .join(rows_table, tokens_table.c.row_id == rows_table.c.row_id)
            .where(rows_table.c.run_id == run_id)
            .limit(limit)
        )

        if row_id is not None:
            query = query.where(tokens_table.c.row_id == row_id)

        rows = conn.execute(query).fetchall()

    return [
        {
            "token_id": row.token_id,
            "row_id": row.row_id,
            "branch_name": row.branch_name,
            "fork_group_id": row.fork_group_id,
            "join_group_id": row.join_group_id,
            "step_in_pipeline": row.step_in_pipeline,
            "expand_group_id": row.expand_group_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def list_operations(
    db: LandscapeDB,
    recorder: LandscapeRecorder,
    run_id: str,
    operation_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[OperationRecord]:
    """List source/sink operations for a run.

    Operations are the source/sink equivalent of node_states. They track
    external I/O operations (blob downloads, file writes, database inserts)
    and provide a parent context for external calls made during source.load()
    or sink.write().

    Args:
        db: Database connection
        recorder: Landscape recorder
        run_id: Run ID to query
        operation_type: Filter by type ('source_load' or 'sink_write')
        status: Filter by status ('open', 'completed', 'failed', 'pending')
        limit: Maximum operations to return

    Returns:
        List of operation records with node info
    """
    from sqlalchemy import select

    from elspeth.core.landscape.schema import nodes_table, operations_table

    with db.connection() as conn:
        query = (
            select(
                operations_table.c.operation_id,
                operations_table.c.run_id,
                operations_table.c.node_id,
                operations_table.c.operation_type,
                operations_table.c.started_at,
                operations_table.c.completed_at,
                operations_table.c.status,
                operations_table.c.error_message,
                operations_table.c.duration_ms,
                nodes_table.c.plugin_name,
            )
            .join(
                nodes_table,
                (operations_table.c.node_id == nodes_table.c.node_id) & (operations_table.c.run_id == nodes_table.c.run_id),
            )
            .where(operations_table.c.run_id == run_id)
            .order_by(operations_table.c.started_at.desc())
            .limit(limit)
        )

        if operation_type is not None:
            if operation_type not in ("source_load", "sink_write"):
                raise ValueError(f"Invalid operation_type '{operation_type}'. Valid: source_load, sink_write")
            query = query.where(operations_table.c.operation_type == operation_type)

        if status is not None:
            valid_statuses = ("open", "completed", "failed", "pending")
            if status not in valid_statuses:
                raise ValueError(f"Invalid status '{status}'. Valid: {valid_statuses}")
            query = query.where(operations_table.c.status == status)

        rows = conn.execute(query).fetchall()

    return [
        {
            "operation_id": row.operation_id,
            "run_id": row.run_id,
            "node_id": row.node_id,
            "plugin_name": row.plugin_name,
            "operation_type": row.operation_type,
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "duration_ms": row.duration_ms,
            "error_message": row.error_message,
        }
        for row in rows
    ]


def get_operation_calls(db: LandscapeDB, recorder: LandscapeRecorder, operation_id: str) -> list[OperationCallRecord]:
    """Get external calls for a source/sink operation.

    Unlike get_calls() which takes a state_id for transform calls, this
    method returns calls made during source.load() or sink.write().

    Args:
        db: Database connection
        recorder: Landscape recorder
        operation_id: Operation ID to query

    Returns:
        List of call records (HTTP, SQL, etc.)
    """
    from sqlalchemy import select

    from elspeth.core.landscape.schema import calls_table

    with db.connection() as conn:
        query = select(calls_table).where(calls_table.c.operation_id == operation_id).order_by(calls_table.c.call_index)
        rows = conn.execute(query).fetchall()

    return [
        {
            "call_id": row.call_id,
            "operation_id": row.operation_id,
            "call_index": row.call_index,
            "call_type": row.call_type,
            "status": row.status,
            "latency_ms": row.latency_ms,
            "request_hash": row.request_hash,
            "response_hash": row.response_hash,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def explain_token(
    db: LandscapeDB,
    recorder: LandscapeRecorder,
    run_id: str,
    token_id: str | None = None,
    row_id: str | None = None,
    sink: str | None = None,
) -> dict[str, Any] | None:
    """Get complete lineage for a token or row.

    Args:
        db: Database connection
        recorder: Landscape recorder
        run_id: Run ID to query
        token_id: Token ID for precise lineage (preferred for DAGs with forks)
        row_id: Row ID (requires disambiguation if multiple terminal tokens)
        sink: Sink name to disambiguate when row has multiple terminal tokens

    Returns:
        Complete lineage including source row, node states, calls, errors, outcome,
        or None if not found
    """
    from elspeth.core.landscape.lineage import explain

    result = explain(recorder, run_id, token_id=token_id, row_id=row_id, sink=sink)
    if result is None:
        return None
    result_dict = cast(dict[str, Any], _dataclass_to_dict(result))

    # Annotate routing_events with flow_type convenience field
    for event in result_dict.get("routing_events", []):
        event["flow_type"] = "divert" if event.get("mode") == "divert" else "normal"

    # Build divert_summary from routing events
    divert_events = [e for e in result_dict.get("routing_events", []) if e.get("mode") == "divert"]

    if divert_events:
        divert_event = divert_events[-1]  # Last divert event is the terminal one
        edge = recorder.get_edge(divert_event["edge_id"])
        result_dict["divert_summary"] = {
            "diverted": True,
            "divert_type": "quarantine" if "__quarantine__" in edge.label else "error",
            "from_node": edge.from_node_id,
            "to_sink": edge.to_node_id,
            "edge_label": edge.label,
            "reason_hash": divert_event.get("reason_hash"),
        }
    else:
        result_dict["divert_summary"] = None

    return result_dict


def get_errors(
    db: LandscapeDB,
    recorder: LandscapeRecorder,
    run_id: str,
    error_type: str = "all",
    limit: int = 100,
) -> dict[str, Any]:
    """Get validation and/or transform errors for a run.

    Args:
        db: Database connection
        recorder: Landscape recorder
        run_id: Run ID to query
        error_type: "validation", "transform", or "all" (default)
        limit: Maximum errors to return per type

    Returns:
        Errors grouped by type
    """
    from sqlalchemy import select

    from elspeth.core.landscape.schema import transform_errors_table, validation_errors_table

    result: dict[str, Any] = {"run_id": run_id}

    with db.connection() as conn:
        if error_type in ("all", "validation"):
            query = (
                select(validation_errors_table)
                .where(validation_errors_table.c.run_id == run_id)
                .order_by(validation_errors_table.c.created_at.desc())
                .limit(limit)
            )
            rows = conn.execute(query).fetchall()
            result["validation_errors"] = [
                {
                    "error_id": row.error_id,
                    "node_id": row.node_id,
                    "row_hash": row.row_hash,
                    "row_data": json.loads(row.row_data_json) if row.row_data_json else None,
                    "schema_mode": row.schema_mode,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

        if error_type in ("all", "transform"):
            query = (
                select(transform_errors_table)
                .where(transform_errors_table.c.run_id == run_id)
                .order_by(transform_errors_table.c.created_at.desc())
                .limit(limit)
            )
            rows = conn.execute(query).fetchall()
            result["transform_errors"] = [
                {
                    "error_id": row.error_id,
                    "token_id": row.token_id,
                    "transform_id": row.transform_id,
                    "row_data": json.loads(row.row_data_json) if row.row_data_json else None,
                    "error_details": json.loads(row.error_details_json) if row.error_details_json else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

    return result


def get_node_states(
    db: LandscapeDB,
    recorder: LandscapeRecorder,
    run_id: str,
    node_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[NodeStateRecord]:
    """Get node states (processing records) for a run.

    Args:
        db: Database connection
        recorder: Landscape recorder
        run_id: Run ID to query
        node_id: Optional filter by node ID
        status: Optional filter by status (PENDING, RUNNING, COMPLETED, FAILED)
        limit: Maximum states to return

    Returns:
        List of node state records
    """
    from sqlalchemy import select

    from elspeth.contracts import NodeStateStatus
    from elspeth.core.landscape.schema import node_states_table

    with db.connection() as conn:
        query = select(node_states_table).where(node_states_table.c.run_id == run_id).limit(limit)

        if node_id is not None:
            query = query.where(node_states_table.c.node_id == node_id)

        if status is not None:
            try:
                NodeStateStatus(status)
            except ValueError:
                valid = [s.value for s in NodeStateStatus]
                raise ValueError(f"Invalid status '{status}'. Valid: {valid}") from None
            query = query.where(node_states_table.c.status == status)

        query = query.order_by(node_states_table.c.step_index)
        rows = conn.execute(query).fetchall()

    return [
        {
            "state_id": row.state_id,
            "token_id": row.token_id,
            "node_id": row.node_id,
            "step_index": row.step_index,
            "attempt": row.attempt,
            "status": row.status,
            "input_hash": row.input_hash,
            "output_hash": row.output_hash,
            "duration_ms": row.duration_ms,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }
        for row in rows
    ]


def get_calls(db: LandscapeDB, recorder: LandscapeRecorder, state_id: str) -> list[CallDetail]:
    """Get external calls for a node state.

    Args:
        db: Database connection
        recorder: Landscape recorder
        state_id: Node state ID to query

    Returns:
        List of call records (LLM calls, HTTP requests, etc.)
    """
    calls = recorder.get_calls(state_id)
    return [_dataclass_to_dict(call) for call in calls]


def _strip_sql_comments(sql: str) -> str:
    """Strip SQL comments (block and line) from a query string.

    Removes ``/* ... */`` block comments and ``-- ...`` line comments.
    Does NOT handle comments inside string literals, but the MCP analysis
    server should never receive queries that rely on that distinction.
    """
    # Remove block comments (non-greedy to handle multiple)
    result = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Remove line comments
    result = re.sub(r"--[^\n]*", " ", result)
    return result


# Keyword blocklist: statements that are NOT read-only.
# Uses word-boundary matching to avoid false positives (e.g., created_at vs CREATE).
_FORBIDDEN_KEYWORDS = frozenset(
    {
        # Standard DML/DDL
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "GRANT",
        "REVOKE",
        "MERGE",
        "REPLACE",
        # Transaction control
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT",
        "RELEASE",
        # SQLite-specific
        "PRAGMA",
        "ATTACH",
        "DETACH",
        "VACUUM",
        "REINDEX",
        # PostgreSQL-specific
        "COPY",
        "SET",
        # Procedure execution
        "EXEC",
        "EXECUTE",
        "CALL",
        # Data loading
        "LOAD",
        "IMPORT",
        "EXPORT",
    }
)


def _validate_readonly_sql(sql: str) -> None:
    """Validate that a SQL string is a single read-only SELECT or CTE.

    Raises ValueError if the query is empty, contains multiple statements,
    uses a non-SELECT/WITH prefix, or contains forbidden keywords.

    Note: Semicolons inside string literals will be rejected. This is an
    acceptable limitation for the MCP analysis server, which receives
    machine-generated queries from LLMs.
    """
    # Step 1: Strip comments to prevent bypass via comment tricks
    stripped = _strip_sql_comments(sql)
    normalized = stripped.strip()

    if not normalized:
        raise ValueError("Query is empty")

    # Step 2: Reject multi-statement payloads (semicolons).
    # Allow a single trailing semicolon (common in SQL tools).
    without_trailing = normalized.rstrip("; \t\n\r")
    if ";" in without_trailing:
        raise ValueError("Multiple statements are not allowed (semicolons found)")

    # Step 3: Require SELECT or WITH prefix (case-insensitive)
    upper = normalized.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise ValueError("Only SELECT queries are allowed (must start with SELECT or WITH)")

    # Step 4: Reject forbidden keywords (word-boundary match).
    # Strip string literal contents first so that keywords inside quotes
    # (e.g., WHERE status = 'INSERT') don't trigger false positives.
    upper_stripped = re.sub(r"'[^']*'", "''", upper)
    upper_stripped = re.sub(r'"[^"]*"', '""', upper_stripped)
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper_stripped):
            raise ValueError(f"Query contains forbidden keyword: {keyword}")


def query(db: LandscapeDB, recorder: LandscapeRecorder, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute a read-only SQL query.

    Args:
        db: Database connection
        recorder: Landscape recorder
        sql: SQL query (must be a single SELECT or WITH...SELECT)
        params: Optional query parameters

    Returns:
        Query results as list of dicts

    Raises:
        ValueError: If query fails read-only validation
    """
    _validate_readonly_sql(sql)

    from sqlalchemy import text

    with db.connection() as conn:
        result = conn.execute(text(sql), params or {})
        columns = result.keys()
        rows = result.fetchall()

    return [dict(zip(columns, [_serialize_datetime(v) for v in row], strict=False)) for row in rows]
