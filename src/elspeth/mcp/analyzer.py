# src/elspeth/mcp/analyzer.py
"""Thin facade for the Landscape audit database analyzer.

LandscapeAnalyzer keeps its public API but delegates every method
to the appropriate submodule in ``mcp.analyzers``. Holds only
``__init__`` (db/recorder setup) and ``close()``.
"""

from __future__ import annotations

from typing import Any

from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.mcp.analyzers import contracts, diagnostics, queries, reports
from elspeth.mcp.types import (
    CallDetail,
    ContractViolationsReport,
    DAGStructureReport,
    DiagnosticReport,
    ErrorAnalysisReport,
    ErrorResult,
    ErrorsReport,
    ExplainTokenResult,
    FailureContextReport,
    FieldExplanation,
    FieldNotFoundError,
    LLMUsageReport,
    NodeDetail,
    NodeStateRecord,
    OperationCallRecord,
    OperationRecord,
    OutcomeAnalysisReport,
    PerformanceReport,
    RecentActivityReport,
    RowRecord,
    RunContractReport,
    RunDetail,
    RunRecord,
    RunSummaryReport,
    SchemaDescription,
    TokenRecord,
)


class LandscapeAnalyzer:
    """Read-only analyzer for the Landscape audit database.

    Thin facade that delegates to domain-specific submodules:
    - queries: Core CRUD (list_runs, list_rows, etc.)
    - reports: Computed analysis (get_run_summary, get_performance_report, etc.)
    - diagnostics: Emergency tools (diagnose, get_failure_context, etc.)
    - contracts: Schema contract tools (get_run_contract, explain_field, etc.)
    """

    def __init__(self, database_url: str, *, passphrase: str | None = None) -> None:
        """Initialize analyzer with database connection.

        Args:
            database_url: SQLAlchemy connection URL (e.g., sqlite:///./state/audit.db)
            passphrase: SQLCipher encryption passphrase (if database is encrypted)
        """
        self._db = LandscapeDB.from_url(database_url, passphrase=passphrase, create_tables=False)
        self._recorder = LandscapeRecorder(self._db)

    def close(self) -> None:
        """Close database connection."""
        self._db.close()

    # === Core Query Tools (queries module) ===

    def list_runs(self, limit: int = 50, status: str | None = None) -> list[RunRecord]:
        return queries.list_runs(self._db, self._recorder, limit=limit, status=status)

    def get_run(self, run_id: str) -> RunDetail | None:
        return queries.get_run(self._db, self._recorder, run_id)

    def list_rows(self, run_id: str, limit: int = 100, offset: int = 0) -> list[RowRecord]:
        return queries.list_rows(self._db, self._recorder, run_id, limit=limit, offset=offset)

    def list_nodes(self, run_id: str) -> list[NodeDetail]:
        return queries.list_nodes(self._db, self._recorder, run_id)

    def list_tokens(self, run_id: str, row_id: str | None = None, limit: int = 100) -> list[TokenRecord]:
        return queries.list_tokens(self._db, self._recorder, run_id, row_id=row_id, limit=limit)

    def list_operations(
        self,
        run_id: str,
        operation_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[OperationRecord]:
        return queries.list_operations(self._db, self._recorder, run_id, operation_type=operation_type, status=status, limit=limit)

    def get_operation_calls(self, operation_id: str) -> list[OperationCallRecord]:
        return queries.get_operation_calls(self._db, self._recorder, operation_id)

    def explain_token(
        self,
        run_id: str,
        token_id: str | None = None,
        row_id: str | None = None,
        sink: str | None = None,
    ) -> ExplainTokenResult | ErrorResult:
        result = queries.explain_token(self._db, self._recorder, run_id, token_id=token_id, row_id=row_id, sink=sink)
        if result is None:
            return {"error": "Token or row not found, or no terminal tokens exist yet"}
        return result  # type: ignore[return-value]

    def get_errors(self, run_id: str, error_type: str = "all", limit: int = 100) -> ErrorsReport:
        return queries.get_errors(self._db, self._recorder, run_id, error_type=error_type, limit=limit)  # type: ignore[return-value]

    def get_node_states(
        self,
        run_id: str,
        node_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[NodeStateRecord]:
        return queries.get_node_states(self._db, self._recorder, run_id, node_id=node_id, status=status, limit=limit)

    def get_calls(self, state_id: str) -> list[CallDetail]:
        return queries.get_calls(self._db, self._recorder, state_id)

    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return queries.query(self._db, self._recorder, sql, params=params)

    # === Computed Analysis Tools (reports module) ===

    def get_run_summary(self, run_id: str) -> RunSummaryReport | ErrorResult:
        return reports.get_run_summary(self._db, self._recorder, run_id)

    def get_dag_structure(self, run_id: str) -> DAGStructureReport | ErrorResult:
        return reports.get_dag_structure(self._db, self._recorder, run_id)

    def get_performance_report(self, run_id: str) -> PerformanceReport | ErrorResult:
        return reports.get_performance_report(self._db, self._recorder, run_id)

    def get_error_analysis(self, run_id: str) -> ErrorAnalysisReport | ErrorResult:
        return reports.get_error_analysis(self._db, self._recorder, run_id)

    def get_llm_usage_report(self, run_id: str) -> LLMUsageReport | ErrorResult:
        return reports.get_llm_usage_report(self._db, self._recorder, run_id)

    def describe_schema(self) -> SchemaDescription:
        return reports.describe_schema(self._db, self._recorder)

    def get_outcome_analysis(self, run_id: str) -> OutcomeAnalysisReport | ErrorResult:
        return reports.get_outcome_analysis(self._db, self._recorder, run_id)

    # === Emergency Diagnostic Tools (diagnostics module) ===

    def diagnose(self) -> DiagnosticReport:
        return diagnostics.diagnose(self._db, self._recorder)

    def get_failure_context(self, run_id: str, limit: int = 10) -> FailureContextReport | ErrorResult:
        return diagnostics.get_failure_context(self._db, self._recorder, run_id, limit=limit)

    def get_recent_activity(self, minutes: int = 60) -> RecentActivityReport:
        return diagnostics.get_recent_activity(self._db, self._recorder, minutes=minutes)

    # === Schema Contract Tools (contracts module) ===

    def get_run_contract(self, run_id: str) -> RunContractReport | ErrorResult:
        return contracts.get_run_contract(self._db, self._recorder, run_id)

    def explain_field(self, run_id: str, field_name: str) -> FieldExplanation | ErrorResult | FieldNotFoundError:
        return contracts.explain_field(self._db, self._recorder, run_id, field_name)

    def list_contract_violations(self, run_id: str, limit: int = 100) -> ContractViolationsReport | ErrorResult:
        return contracts.list_contract_violations(self._db, self._recorder, run_id, limit=limit)
