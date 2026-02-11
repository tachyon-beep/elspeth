# tests/unit/mcp/test_query_validation.py
"""Tests for MCP query() SQL validation — read-only enforcement.

The query() tool claims to be read-only (SELECT only). These tests verify
that the validation guard correctly rejects:
  - Non-SELECT statements
  - Multi-statement payloads (semicolons)
  - Dangerous keywords even inside SELECT subqueries
  - Comment-based bypass attempts
  - Known dangerous SQLite/Postgres commands

And correctly allows:
  - Simple SELECT statements
  - CTEs (WITH ... SELECT)
  - SELECT with legitimate keywords in identifiers/strings

Bug ref: docs/bugs/open/mcp/P1-2026-02-05-query-read-only-guard-allows-non-select-o.md
"""

from __future__ import annotations

import pytest

from elspeth.mcp.analyzers.queries import _validate_readonly_sql


class TestBasicSelectAllowed:
    """Valid read-only queries should pass validation."""

    def test_simple_select(self) -> None:
        _validate_readonly_sql("SELECT * FROM runs")

    def test_select_with_where(self) -> None:
        _validate_readonly_sql("SELECT run_id FROM runs WHERE status = 'completed'")

    def test_select_with_join(self) -> None:
        _validate_readonly_sql("SELECT r.run_id, n.node_id FROM runs r JOIN nodes n ON r.run_id = n.run_id")

    def test_select_with_subquery(self) -> None:
        _validate_readonly_sql("SELECT * FROM runs WHERE run_id IN (SELECT run_id FROM nodes)")

    def test_select_with_aggregation(self) -> None:
        _validate_readonly_sql("SELECT COUNT(*), status FROM runs GROUP BY status HAVING COUNT(*) > 1")

    def test_select_with_order_limit(self) -> None:
        _validate_readonly_sql("SELECT * FROM runs ORDER BY created_at DESC LIMIT 10")

    def test_select_case_insensitive(self) -> None:
        _validate_readonly_sql("select * from runs")

    def test_select_with_leading_whitespace(self) -> None:
        _validate_readonly_sql("   SELECT * FROM runs")

    def test_select_with_leading_newlines(self) -> None:
        _validate_readonly_sql("\n\n  SELECT * FROM runs")


class TestCTEAllowed:
    """WITH ... SELECT (Common Table Expressions) should pass."""

    def test_simple_cte(self) -> None:
        _validate_readonly_sql("WITH recent AS (SELECT * FROM runs WHERE status = 'completed') SELECT * FROM recent")

    def test_multiple_ctes(self) -> None:
        _validate_readonly_sql("WITH a AS (SELECT 1), b AS (SELECT 2) SELECT * FROM a, b")

    def test_recursive_cte(self) -> None:
        _validate_readonly_sql("WITH RECURSIVE cte(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM cte WHERE n < 10) SELECT * FROM cte")

    def test_cte_case_insensitive(self) -> None:
        _validate_readonly_sql("with cte as (select 1) select * from cte")


class TestNonSelectRejected:
    """Non-SELECT statements must be rejected."""

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO runs VALUES ('x', 'y')",
            "UPDATE runs SET status = 'failed'",
            "DELETE FROM runs",
            "DROP TABLE runs",
            "CREATE TABLE evil (id INT)",
            "ALTER TABLE runs ADD COLUMN evil TEXT",
            "TRUNCATE TABLE runs",
            "GRANT ALL ON runs TO public",
            "REVOKE ALL ON runs FROM public",
        ],
        ids=[
            "insert",
            "update",
            "delete",
            "drop",
            "create",
            "alter",
            "truncate",
            "grant",
            "revoke",
        ],
    )
    def test_rejects_dml_ddl(self, sql: str) -> None:
        with pytest.raises(ValueError, match=r"(?i)read-only|forbidden|not allowed|SELECT"):
            _validate_readonly_sql(sql)


class TestDangerousCommandsRejected:
    """Database-specific dangerous commands must be rejected."""

    @pytest.mark.parametrize(
        "sql",
        [
            "COPY runs TO '/tmp/data.csv'",
            "PRAGMA journal_mode=OFF",
            "PRAGMA query_only = OFF",
            "ATTACH DATABASE '/tmp/evil.db' AS evil",
            "DETACH DATABASE evil",
            "VACUUM",
            "SET ROLE admin",
            "SET default_transaction_read_only = off",
            "BEGIN",
            "COMMIT",
            "ROLLBACK",
            "SAVEPOINT sp1",
            "RELEASE sp1",
            "REINDEX runs",
        ],
        ids=[
            "copy",
            "pragma_journal",
            "pragma_query_only",
            "attach",
            "detach",
            "vacuum",
            "set_role",
            "set_readonly",
            "begin",
            "commit",
            "rollback",
            "savepoint",
            "release",
            "reindex",
        ],
    )
    def test_rejects_dangerous_commands(self, sql: str) -> None:
        with pytest.raises(ValueError, match=r"(?i)read-only|forbidden|not allowed|SELECT"):
            _validate_readonly_sql(sql)


class TestMultiStatementRejected:
    """Multi-statement payloads (semicolons) must be rejected."""

    def test_select_then_drop(self) -> None:
        with pytest.raises(ValueError, match=r"(?i)semicolon|multiple|statement"):
            _validate_readonly_sql("SELECT 1; DROP TABLE runs")

    def test_select_then_copy(self) -> None:
        with pytest.raises(ValueError, match=r"(?i)semicolon|multiple|statement"):
            _validate_readonly_sql("SELECT 1; COPY runs TO '/tmp/data.csv'")

    def test_select_then_set(self) -> None:
        with pytest.raises(ValueError, match=r"(?i)semicolon|multiple|statement"):
            _validate_readonly_sql("SELECT 1; SET ROLE admin")

    def test_select_then_pragma(self) -> None:
        with pytest.raises(ValueError, match=r"(?i)semicolon|multiple|statement"):
            _validate_readonly_sql("SELECT 1; PRAGMA journal_mode=OFF")

    def test_trailing_semicolon_is_ok(self) -> None:
        """A single trailing semicolon with no second statement is acceptable."""
        _validate_readonly_sql("SELECT * FROM runs;")

    def test_trailing_semicolon_with_whitespace_is_ok(self) -> None:
        _validate_readonly_sql("SELECT * FROM runs;  \n  ")


class TestCommentBypassPrevented:
    """SQL comment tricks should not bypass validation."""

    def test_line_comment_hiding_payload(self) -> None:
        """Line comment should not hide a dangerous second statement."""
        with pytest.raises(ValueError, match=r"(?i)semicolon|multiple|statement|forbidden"):
            _validate_readonly_sql("SELECT 1; --\nDROP TABLE runs")

    def test_block_comment_wrapping_select(self) -> None:
        """Block comment removing the SELECT prefix."""
        with pytest.raises(ValueError, match=r"(?i)read-only|not allowed|SELECT"):
            _validate_readonly_sql("/* SELECT */ DROP TABLE runs")

    def test_nested_block_comment(self) -> None:
        with pytest.raises(ValueError, match=r"(?i)read-only|not allowed|SELECT|forbidden"):
            _validate_readonly_sql("SELECT 1; /* harmless */ DROP TABLE runs")

    def test_line_comment_marker_inside_string_does_not_hide_payload(self) -> None:
        """'--' inside a quoted string must not suppress trailing statements."""
        with pytest.raises(ValueError, match=r"(?i)semicolon|multiple|statement|forbidden"):
            _validate_readonly_sql("SELECT '--'; UPDATE runs SET status = 'failed'")

    def test_comment_marker_inside_string_remains_valid_for_single_select(self) -> None:
        """Comment-like text inside string literals is valid in read-only SELECT."""
        _validate_readonly_sql("SELECT '--not-a-comment' AS marker")


class TestKeywordInIdentifierAllowed:
    """Keywords appearing as column/table names (word boundaries) should not
    trigger false positives."""

    def test_created_at_column(self) -> None:
        """'created_at' contains 'CREATE' but is not a CREATE statement."""
        _validate_readonly_sql("SELECT created_at FROM runs")

    def test_updated_at_column(self) -> None:
        """'updated_at' contains 'UPDATE' but is not an UPDATE statement."""
        _validate_readonly_sql("SELECT updated_at FROM runs")

    def test_grant_total_column(self) -> None:
        _validate_readonly_sql("SELECT grant_total FROM invoices")

    def test_keyword_in_string_literal(self) -> None:
        _validate_readonly_sql("SELECT * FROM runs WHERE status = 'INSERT'")

    def test_delete_flag_column(self) -> None:
        """'is_deleted' contains 'DELETE' substring but is not a DELETE statement."""
        _validate_readonly_sql("SELECT is_deleted FROM runs")


class TestEmptyAndMalformed:
    """Edge cases for empty/whitespace/garbage input."""

    def test_empty_string(self) -> None:
        with pytest.raises(ValueError):
            _validate_readonly_sql("")

    def test_whitespace_only(self) -> None:
        with pytest.raises(ValueError):
            _validate_readonly_sql("   \n\t  ")

    def test_just_a_semicolon(self) -> None:
        with pytest.raises(ValueError):
            _validate_readonly_sql(";")

    def test_comment_only(self) -> None:
        with pytest.raises(ValueError):
            _validate_readonly_sql("-- just a comment")

    def test_block_comment_only(self) -> None:
        with pytest.raises(ValueError):
            _validate_readonly_sql("/* nothing here */")
