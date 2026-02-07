# src/elspeth/mcp/types.py
"""TypedDict definitions for MCP server return types.

These TypedDicts give static structure to the dicts returned by
LandscapeAnalyzer methods. At runtime they are plain dicts and
serialize identically via json.dumps() -- the MCP wire format is
unchanged. mypy uses them to verify that return structures match.

Follows the naming convention from tui/types.py:
  - {Noun}Record   -- items in a list (SQL row projections)
  - {Noun}Detail   -- dataclass_to_dict conversions (audit entities)
  - {Noun}Report   -- aggregate / analysis single-dict returns

Design decisions:
  - ``total=False`` + ``Required[]`` when some keys are conditionally present
  - ``dict[str, Any]`` for genuinely dynamic sub-structures
    (outcome distributions, per-plugin stats, dataclass-converted nested objects)
  - Functional TypedDict form for ``DAGEdge`` (``"from"`` is a Python keyword)
"""

from typing import Any, Required, TypedDict

# ══════════════════════════════════════════════════════════════════════════════
# Group A -- Simple Record Types (for list-returning methods)
# ══════════════════════════════════════════════════════════════════════════════


class RunRecord(TypedDict):
    """A run record as returned by ``list_runs``."""

    run_id: str
    status: str
    started_at: str | None
    completed_at: str | None
    config_hash: str
    export_status: str | None


class RowRecord(TypedDict):
    """A source row record as returned by ``list_rows``."""

    row_id: str
    run_id: str
    source_node_id: str
    row_index: int
    source_data_hash: str
    source_data_ref: str | None
    created_at: str | None


class TokenRecord(TypedDict):
    """A token record as returned by ``list_tokens``."""

    token_id: str
    row_id: str
    branch_name: str | None
    fork_group_id: str | None
    join_group_id: str | None
    step_in_pipeline: int | None
    expand_group_id: str | None
    created_at: str | None


class OperationRecord(TypedDict):
    """A source/sink operation record as returned by ``list_operations``."""

    operation_id: str
    run_id: str
    node_id: str
    plugin_name: str
    operation_type: str
    status: str
    started_at: str | None
    completed_at: str | None
    duration_ms: float | None
    error_message: str | None


class OperationCallRecord(TypedDict):
    """A call made during a source/sink operation (``get_operation_calls``)."""

    call_id: str
    operation_id: str
    call_index: int
    call_type: str
    status: str
    latency_ms: float | None
    request_hash: str
    response_hash: str | None
    created_at: str | None


class NodeStateRecord(TypedDict):
    """A node state record as returned by ``get_node_states``."""

    state_id: str
    token_id: str
    node_id: str
    step_index: int
    attempt: int
    status: str
    input_hash: str
    output_hash: str | None
    duration_ms: float | None
    started_at: str | None
    completed_at: str | None


# ══════════════════════════════════════════════════════════════════════════════
# Group B -- Dataclass Mirror Types (for dataclass_to_dict conversions)
# ══════════════════════════════════════════════════════════════════════════════
# These mirror the audit dataclasses in contracts/audit.py after
# dataclass_to_dict conversion (datetime -> str, enum -> str).
# We use dict[str, Any] as the type since dataclass_to_dict produces
# fully dynamic dicts whose exact shape depends on the dataclass variant.


RunDetail = dict[str, Any]
"""Run detail dict from ``dataclass_to_dict(Run)``."""

NodeDetail = dict[str, Any]
"""Node detail dict from ``dataclass_to_dict(Node)``."""

CallDetail = dict[str, Any]
"""Call detail dict from ``dataclass_to_dict(Call)``."""


# ══════════════════════════════════════════════════════════════════════════════
# Group C -- Complex Report Types (nested structures)
# ══════════════════════════════════════════════════════════════════════════════


# --- RunSummaryReport ---


class RunSummaryCounts(TypedDict):
    """Count sub-dict inside ``RunSummaryReport``."""

    rows: int
    tokens: int
    nodes: int
    node_states: int
    operations: int
    source_loads: int
    sink_writes: int


class RunSummaryErrors(TypedDict):
    """Error count sub-dict inside ``RunSummaryReport``."""

    validation: int
    transform: int
    total: int


class RunSummaryReport(TypedDict):
    """Return type for ``get_run_summary``."""

    run_id: str
    status: str
    started_at: str | None
    completed_at: str | None
    run_duration_seconds: float | None
    counts: RunSummaryCounts
    errors: RunSummaryErrors
    outcome_distribution: dict[str, int]  # dynamic outcome names
    avg_state_duration_ms: float | None


# --- DAGStructureReport ---


class DAGNode(TypedDict):
    """A node in the DAG structure."""

    node_id: str
    plugin_name: str
    node_type: str
    sequence: int | None


# Functional form because "from" is a Python keyword
DAGEdge = TypedDict(
    "DAGEdge",
    {
        "from": str,
        "to": str,
        "label": str,
        "mode": str,
        "flow_type": str,
    },
)


class DAGStructureReport(TypedDict):
    """Return type for ``get_dag_structure``."""

    run_id: str
    nodes: list[DAGNode]
    edges: list[DAGEdge]
    node_count: int
    edge_count: int
    mermaid: str


# --- PerformanceReport ---


class NodePerformance(TypedDict):
    """Per-node performance statistics."""

    node_id: str
    plugin: str
    type: str
    executions: int
    avg_ms: float | None
    min_ms: float | None
    max_ms: float | None
    total_ms: float | None
    pct_of_total: float
    failures: int


class PerformanceReport(TypedDict):
    """Return type for ``get_performance_report``."""

    run_id: str
    total_processing_time_ms: float
    node_count: int
    bottlenecks: list[NodePerformance]
    high_variance_nodes: list[NodePerformance]
    node_performance: list[NodePerformance]


# --- ErrorAnalysisReport ---


class ValidationErrorGroup(TypedDict):
    """Validation error group by source plugin."""

    source_plugin: str
    schema_mode: str
    count: int


class TransformErrorGroup(TypedDict):
    """Transform error group by transform plugin."""

    transform_plugin: str
    count: int


class ValidationErrorSummary(TypedDict):
    """Validation errors sub-dict in ``ErrorAnalysisReport``."""

    total: int
    by_source: list[ValidationErrorGroup]
    sample_data: list[dict[str, Any] | None]


class TransformErrorSummary(TypedDict):
    """Transform errors sub-dict in ``ErrorAnalysisReport``."""

    total: int
    by_transform: list[TransformErrorGroup]
    sample_details: list[dict[str, Any] | None]


class ErrorAnalysisReport(TypedDict):
    """Return type for ``get_error_analysis``."""

    run_id: str
    validation_errors: ValidationErrorSummary
    transform_errors: TransformErrorSummary


# --- LLMUsageReport ---


class LLMSummary(TypedDict):
    """LLM call summary totals."""

    total_calls: int
    total_latency_ms: float
    avg_latency_ms: float | None


class LLMPluginStats(TypedDict):
    """Per-plugin LLM statistics."""

    total_calls: int
    successful: int
    failed: int
    avg_latency_ms: float
    total_latency_ms: float


class LLMUsageReport(TypedDict, total=False):
    """Return type for ``get_llm_usage_report``.

    Uses ``total=False`` because the empty-case returns ``message``
    instead of ``llm_summary`` / ``by_plugin``.
    """

    run_id: Required[str]
    # Present when there are LLM calls
    call_types: dict[str, int]  # dynamic call type names
    llm_summary: LLMSummary
    by_plugin: dict[str, LLMPluginStats]  # dynamic plugin names
    # Present when there are NO LLM calls
    message: str


# --- OutcomeAnalysisReport ---


class OutcomeSummary(TypedDict):
    """Outcome summary counts."""

    terminal_tokens: int
    non_terminal_tokens: int
    fork_operations: int
    join_operations: int


class OutcomeDistributionEntry(TypedDict):
    """Single entry in outcome distribution."""

    outcome: str
    is_terminal: bool
    count: int


class OutcomeAnalysisReport(TypedDict):
    """Return type for ``get_outcome_analysis``."""

    run_id: str
    summary: OutcomeSummary
    outcome_distribution: list[OutcomeDistributionEntry]
    sink_distribution: dict[str, int]  # dynamic sink names


# --- SchemaDescription ---


class ColumnInfo(TypedDict):
    """Column metadata from SQLAlchemy inspector."""

    name: str
    type: str
    nullable: bool


class ForeignKeyInfo(TypedDict):
    """Foreign key metadata."""

    columns: list[str]
    references: str


class TableInfo(TypedDict):
    """Table metadata from SQLAlchemy inspector."""

    columns: list[ColumnInfo]
    primary_key: list[str]
    foreign_keys: list[ForeignKeyInfo]


class SchemaDescription(TypedDict):
    """Return type for ``describe_schema``."""

    tables: dict[str, TableInfo]  # dynamic table names
    table_count: int
    hint: str


# --- ErrorsReport ---


class ValidationErrorDetail(TypedDict):
    """A single validation error in ``get_errors``."""

    error_id: str
    node_id: str | None
    row_hash: str
    row_data: dict[str, Any] | None
    schema_mode: str
    created_at: str | None


class TransformErrorDetail(TypedDict):
    """A single transform error in ``get_errors``."""

    error_id: str
    token_id: str
    transform_id: str
    row_data: dict[str, Any] | None
    error_details: dict[str, Any] | None
    created_at: str | None


class ErrorsReport(TypedDict, total=False):
    """Return type for ``get_errors``.

    Uses ``total=False`` because validation_errors and transform_errors
    are conditionally present depending on the ``error_type`` parameter.
    """

    run_id: Required[str]
    validation_errors: list[ValidationErrorDetail]
    transform_errors: list[TransformErrorDetail]


# --- DiagnosticReport ---


class DiagnosticProblem(TypedDict, total=False):
    """A single problem in ``diagnose``.

    Uses ``total=False`` because different problem types include
    different fields (``run_ids``, ``runs``, ``operations``, ``count``).
    """

    severity: Required[str]
    type: Required[str]
    message: Required[str]
    count: int
    run_ids: list[str]
    runs: list[dict[str, Any]]
    operations: list[dict[str, Any]]


class RecentRunSummary(TypedDict):
    """A recent run in the diagnose summary."""

    run_id: str
    status: str
    started: str | None


class DiagnosticReport(TypedDict):
    """Return type for ``diagnose``."""

    status: str
    problems: list[DiagnosticProblem]
    recent_runs: list[RecentRunSummary]
    recommendations: list[str]
    next_steps: list[str]


# --- FailureContextReport ---


class FailedNodeState(TypedDict):
    """A failed node state in failure context."""

    state_id: str
    token_id: str
    plugin: str
    type: str
    step: int
    attempt: int
    started: str | None


class FailureTransformError(TypedDict):
    """A transform error in failure context."""

    token_id: str
    plugin: str
    details: dict[str, Any] | None


class FailureValidationError(TypedDict):
    """A validation error in failure context."""

    plugin: str
    row_hash: str | None
    sample_data: dict[str, Any] | None


class FailurePatterns(TypedDict):
    """Patterns identified in failure analysis."""

    plugins_failing: list[str]
    has_retries: bool
    failure_count: int
    transform_error_count: int
    validation_error_count: int


class FailureContextReport(TypedDict):
    """Return type for ``get_failure_context``."""

    run_id: str
    run_status: str
    failed_node_states: list[FailedNodeState]
    transform_errors: list[FailureTransformError]
    validation_errors: list[FailureValidationError]
    patterns: FailurePatterns
    next_steps: list[str]


# --- RecentActivityReport ---


class RecentRunDetail(TypedDict):
    """A run in the recent activity timeline."""

    run_id: str
    full_run_id: str
    status: str
    started: str | None
    duration_seconds: float | None
    rows_processed: int
    node_executions: int


class RecentActivityReport(TypedDict):
    """Return type for ``get_recent_activity``."""

    time_window_minutes: int
    total_runs: int
    status_summary: dict[str, int]  # dynamic status names
    runs: list[RecentRunDetail]


# --- RunContractReport ---


class ContractField(TypedDict):
    """A field in the schema contract."""

    normalized_name: str
    original_name: str
    python_type: str
    required: bool
    source: str


class RunContractReport(TypedDict):
    """Return type for ``get_run_contract``."""

    run_id: str
    mode: str
    locked: bool
    fields: list[ContractField]
    field_count: int
    version_hash: str


# --- FieldExplanation ---


class FieldExplanation(TypedDict):
    """Return type for ``explain_field``."""

    run_id: str
    normalized_name: str
    original_name: str
    python_type: str
    required: bool
    source: str
    contract_mode: str


# --- ContractViolationsReport ---


class ContractViolationRecord(TypedDict):
    """A single contract violation."""

    error_id: str
    violation_type: str
    normalized_field_name: str | None
    original_field_name: str | None
    expected_type: str | None
    actual_type: str | None
    error: str
    schema_mode: str
    destination: str
    created_at: str | None


class ContractViolationsReport(TypedDict):
    """Return type for ``list_contract_violations``."""

    run_id: str
    total_violations: int
    violations: list[ContractViolationRecord]
    limit: int


# --- ExplainTokenResult ---


class DivertSummary(TypedDict):
    """Summary of a divert (quarantine/error routing)."""

    diverted: bool
    divert_type: str
    from_node: str
    to_sink: str
    edge_label: str
    reason_hash: str | None


class ExplainTokenResult(TypedDict):
    """Return type for ``explain_token``.

    Top-level keys are typed but deeply nested sub-structures
    (routing_events items, node_states items) use ``dict[str, Any]``
    because they come from ``dataclass_to_dict()`` on complex nested
    dataclasses -- typing them fully would duplicate the entire audit
    dataclass hierarchy.
    """

    token: dict[str, Any]
    source_row: dict[str, Any]
    node_states: list[dict[str, Any]]
    routing_events: list[dict[str, Any]]
    calls: list[dict[str, Any]]
    parent_tokens: list[dict[str, Any]]
    validation_errors: list[dict[str, Any]]
    transform_errors: list[dict[str, Any]]
    outcome: dict[str, Any] | None
    divert_summary: DivertSummary | None


# ══════════════════════════════════════════════════════════════════════════════
# Group D -- Shared utility type
# ══════════════════════════════════════════════════════════════════════════════


class ErrorResult(TypedDict):
    """Returned for early-exit ``{"error": "..."}`` paths."""

    error: str


# --- ErrorResult variant with available_fields (explain_field not-found) ---


class FieldNotFoundError(TypedDict):
    """Returned when a field is not found in ``explain_field``."""

    error: str
    available_fields: list[str]
