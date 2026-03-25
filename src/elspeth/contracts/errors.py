"""Error and reason schema contracts.

Frozen dataclasses and TypedDict schemas for structured error payloads
in the audit trail.  These provide consistent shapes for executor error
recording.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict

if TYPE_CHECKING:
    from elspeth.contracts.batch_checkpoint import BatchCheckpointState


@dataclass(frozen=True, slots=True)
class ExecutionError:
    """Frozen dataclass for execution error payloads.

    Used by executors when recording node state failures.
    Immutable and validated at construction time, consistent with
    other audit DTOs (TokenUsage, LLMCallRequest, etc.).

    The ``exception_type`` field is renamed from ``type`` to avoid
    shadowing the Python builtin.  ``to_dict()`` serializes it back
    as ``"type"`` for hash stability with existing audit records.
    """

    exception: str  # String representation of the exception
    exception_type: str  # Exception class name (e.g., "ValueError")
    traceback: str | None = None  # Optional full traceback
    phase: str | None = None  # Optional phase indicator (e.g., "flush" for sink flush errors)

    def __post_init__(self) -> None:
        """Validate that required error fields are non-empty.

        These fields are recorded in the audit trail. Empty strings would
        produce valid-looking but uninformative error records.
        """
        if not self.exception:
            raise ValueError("ExecutionError.exception must not be empty")
        if not self.exception_type:
            raise ValueError("ExecutionError.exception_type must not be empty")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to audit-trail dict.

        Uses ``"type"`` as the key name (not ``exception_type``) to
        maintain hash stability with existing audit records.
        Omits None-valued optional fields.
        """
        d: dict[str, Any] = {
            "exception": self.exception,
            "type": self.exception_type,
        }
        if self.traceback is not None:
            d["traceback"] = self.traceback
        if self.phase is not None:
            d["phase"] = self.phase
        return d


@dataclass(frozen=True, slots=True)
class CoalesceFailureReason:
    """Frozen DTO for coalesce/barrier failure payloads.

    Used by CoalesceExecutor when recording fork-join barrier failures.
    These are internal engine errors, not transform or plugin errors.
    """

    failure_reason: str  # Why coalesce failed (e.g., "quorum_not_met")
    expected_branches: tuple[str, ...]  # Branches expected to arrive
    branches_arrived: tuple[str, ...]  # Branches that actually arrived
    merge_policy: str  # Merge policy in effect
    timeout_ms: int | None = None  # Timeout that triggered failure (if applicable)
    select_branch: str | None = None  # Target branch for select policy (if applicable)

    def __post_init__(self) -> None:
        """Validate coalesce failure record invariants."""
        if not self.failure_reason:
            raise ValueError("CoalesceFailureReason.failure_reason must not be empty")
        if not self.merge_policy:
            raise ValueError("CoalesceFailureReason.merge_policy must not be empty")
        if not self.expected_branches:
            raise ValueError("CoalesceFailureReason.expected_branches must not be empty")
        if self.timeout_ms is not None and self.timeout_ms < 0:
            raise ValueError(f"CoalesceFailureReason.timeout_ms must be non-negative, got {self.timeout_ms}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to audit-trail dict.

        Omits None-valued optional fields for compact JSON.
        """
        d: dict[str, Any] = {
            "failure_reason": self.failure_reason,
            "expected_branches": list(self.expected_branches),
            "branches_arrived": list(self.branches_arrived),
            "merge_policy": self.merge_policy,
        }
        if self.timeout_ms is not None:
            d["timeout_ms"] = self.timeout_ms
        if self.select_branch is not None:
            d["select_branch"] = self.select_branch
        return d


class ConfigGateReason(TypedDict):
    """Reason from config-driven gate (expression evaluation).

    Used by gates defined via GateSettings with condition expressions.
    Constructed by GateExecutor.execute_config_gate().

    Fields:
        condition: The expression that was evaluated (e.g., "row['score'] > 100")
        result: The route label that matched (e.g., "true", "false")
    """

    condition: str
    result: str


# RoutingReason union is defined after TransformErrorReason (see RoutingReason below)


# Literal type for common transform actions (extensible - str also accepted)
TransformActionCategory = Literal[
    # Processing actions
    "processed",  # Generic successful processing
    "mapped",  # Field mapping completed
    "validated",  # Validation passed
    "enriched",  # Data enrichment from external source
    "transformed",  # Data transformation applied
    "normalized",  # Data normalization applied
    "filtered",  # Row passed filter criteria
    "classified",  # Classification assigned
    # Skip/passthrough actions
    "passthrough",  # No changes made (intentional)
    "skipped",  # Processing skipped (e.g., data already present)
    "cached",  # Result retrieved from cache
    # Plugin-specific actions
    "query_completed",  # LLM single-query completion
    "multi_query_enriched",  # LLM multi-query execution completed
    "rag_retrieval",  # RAG retrieval pipeline completed
]


class TransformSuccessReason(TypedDict):
    """Metadata for successful transform operations.

    Provides structured audit information about what a transform did,
    beyond just the input/output data. This enables:
    - Efficient audit queries (fields_modified without diffing)
    - Data quality monitoring (validation_warnings for non-blocking warnings)
    - Conditional path tracking (action distinguishes code paths)

    Used when transforms return TransformResult.success() with optional
    success_reason parameter.

    Required field:
        action: What the transform did. Use TransformActionCategory values
                for common actions, or custom strings for plugin-specific actions.

    Optional fields:
        fields_modified: List of field names that were changed
        fields_added: List of field names that were added
        fields_removed: List of field names that were removed
        validation_warnings: Non-blocking validation issues (data quality flags)
        metadata: Additional plugin-specific context

    Example usage:
        # Simple action tracking
        TransformResult.success(row, success_reason={"action": "enriched"})

        # Field change tracking
        TransformResult.success(row, success_reason={
            "action": "mapped",
            "fields_modified": ["customer_id", "amount"],
            "fields_added": ["currency_code"],
        })

        # Data quality warning
        TransformResult.success(row, success_reason={
            "action": "validated",
            "validation_warnings": ["amount near threshold (995 of 1000 limit)"],
        })
    """

    action: str  # Use TransformActionCategory or custom string

    # Multi-query success context
    queries_completed: NotRequired[int]  # Number of queries completed in multi-query

    # Field tracking
    fields_modified: NotRequired[list[str]]
    fields_added: NotRequired[list[str]]
    fields_removed: NotRequired[list[str]]

    # Data quality
    validation_warnings: NotRequired[list[str]]

    # Extensibility
    metadata: NotRequired[dict[str, Any]]


# =============================================================================
# Transform Error Reason Types
# =============================================================================


class TemplateErrorEntry(TypedDict):
    """Entry in template_errors list for batch processing failures."""

    row_index: int
    error: str


class RowErrorEntry(TypedDict):
    """Entry in row_errors list for batch processing failures.

    The ``error`` field accepts both simple strings and structured dicts.
    Batch plugins (e.g., azure_batch) may store structured error bodies
    from external APIs, which are persisted as-is in the audit trail.
    """

    row_index: int
    reason: str
    error: NotRequired[str | dict[str, Any]]


class UsageStats(TypedDict, total=False):
    """LLM token usage statistics.

    Values are ``int | None`` because providers may omit individual fields.
    ``None`` means "provider did not report this value" — distinct from ``0``.
    """

    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


class QueryFailureDetail(TypedDict):
    """Detailed information about a failed query in multi-query transforms.

    Used when transforms need to report more than just the query name.
    """

    query: str
    error: NotRequired[str]
    error_type: NotRequired[str]
    status_code: NotRequired[int]


class ErrorDetail(TypedDict):
    """Detailed information about an error in batch processing.

    Used when more context is needed than a simple error message string.
    """

    message: str
    error_type: NotRequired[str]
    row_index: NotRequired[int]
    details: NotRequired[str]


# Literal type for compile-time validation of error categories
TransformErrorCategory = Literal[
    # API/Network errors
    "api_error",
    "api_call_failed",
    "llm_call_failed",
    "network_error",
    "permanent_error",
    "retry_timeout",
    "transient_error_no_retry",  # Transient error (connection/timeout) but retry disabled
    # Field/validation errors
    "missing_field",
    "type_mismatch",
    "validation_failed",
    "invalid_input",
    # Template errors
    "template_rendering_failed",
    "template_context_failed",  # Multi-query template context build failed (missing field)
    "all_templates_failed",
    # JSON/response parsing errors
    "json_parse_failed",
    "invalid_json",  # Generic JSON parse failure
    "invalid_json_response",
    "invalid_json_type",
    "empty_choices",
    "malformed_response",
    "missing_output_field",
    "response_truncated",
    # Batch processing errors
    "batch_error",
    "batch_create_failed",
    "batch_failed",
    "batch_cancelled",
    "batch_expired",
    "batch_timeout",
    "batch_retrieve_failed",
    "file_upload_failed",
    "file_download_failed",
    "all_output_lines_malformed",
    "all_rows_failed",
    "result_not_found",
    "query_failed",
    "multi_query_failed",  # Non-retryable LLM error in multi-query (atomic failure)
    "context_length_exceeded",  # LLM context too long (not retryable — shorten prompt)
    "rate_limited",
    # Content extraction errors (Tier 3 boundary - external HTML/text parsing)
    "content_extraction_failed",
    # Retrieval errors (RAG retrieval transform)
    "retrieval_failed",
    "no_results",
    "no_regex_match",
    # Content filtering
    "blocked_content",
    "content_filtered",
    "content_safety_violation",
    "prompt_injection_detected",
    "unknown_category",  # Unknown category from external API (fail-closed)
    "non_string_field",  # Explicitly-configured field is non-string (security fail-closed)
    # Field type validation (Tier 3 - LLM output value type mismatch)
    "field_type_mismatch",
    # Field collision (output would overwrite input fields)
    "field_collision",
    # Contract violations (schema validation)
    "contract_violation",
    "multiple_contract_violations",
    # Numeric/computation errors
    "float_overflow",  # Arithmetic overflow producing inf (e.g., sum of large floats)
    "non_finite_usage",  # LLM API returned NaN/Infinity in usage metadata
    # Executor lifecycle
    "shutdown_requested",  # Worker stopped mid-retry due to executor shutdown
    "unexpected_pool_error",  # Worker future raised unexpected exception — buffer slot recovered
    # Generic (for tests and edge cases)
    "test_error",
    "property_test_error",
    "simulated_failure",
    "deliberate_failure",
    "intentional_failure",
    # Batch processing
    "empty_batch",
    "all_non_finite",  # All values in batch were NaN/Inf — no real data to aggregate
    # Transport/network (batch processing)
    "transport_exception",  # HTTP transport error during batch retrieval
    # Replication errors
    "invalid_copies",  # Invalid copies value in batch_replicate transform
]


class TransformErrorReason(TypedDict):
    """Reason for transform processing error.

    Used when transforms return TransformResult.error().
    The reason field describes what category of error occurred.
    Additional fields provide context specific to the error type.

    Recorded in the audit trail (Tier 1 - full trust) for legal traceability.
    Every transform error must be attributable to its cause.

    Required field:
        reason: Error category from TransformErrorCategory literal type.
                Compile-time validated to prevent typos.

    Common context fields:
        error: Exception message or detailed error description
        field: Field name for field-related errors
        error_type: Sub-category (e.g., "http_error", "network_error")
        message: Human-readable error message (alternative to error)

    Multi-query/template context:
        query: Which query in multi-query failed
        template_hash: Template version for debugging
        template_errors: List of per-row template failures (batch processing)

    LLM response context:
        max_tokens: Configured max tokens limit
        completion_tokens: Actual tokens used in response
        prompt_tokens: Tokens used in prompt
        raw_response: Truncated raw LLM response content
        raw_response_preview: Alternative name for truncated preview
        content_after_fence_strip: Content after markdown fence removal
        usage: Token usage stats from LLM response
        response: Full response object for debugging
        response_keys: Keys present in response dict
        body_preview: HTTP body preview for errors
        content_type: Content-Type header value

    Type validation context:
        expected: Expected type or value
        actual: Actual type or value received
        actual_type: Actual Python type name for type checks
        value: The actual value (truncated for audit)

    Contract violation context:
        violation_type: Specific ContractViolation subclass name
        original_field: Original field name before normalization
        count: Number of violations (multiple_contract_violations only)
        violations: Per-violation reason entries (multiple_contract_violations only)

    RAG retrieval context:
        provider: Retrieval provider name (e.g., "azure_search", "chroma")
        cause: Sub-cause within an error category (e.g., "null_value", "empty_query")
        pattern: Regex pattern string (for no_regex_match errors)

    Rate limiting/timeout context:
        elapsed_seconds: Time elapsed before timeout
        max_seconds: Maximum allowed time
        status_code: HTTP status code

    Content filtering context:
        matched_pattern: Regex pattern that matched
        match_context: Context around the match
        categories: Content safety violation categories

    Batch processing context:
        batch_id: Azure/OpenRouter batch job ID
        queries_completed: Number of queries completed before failure
        row_errors: List of per-row error entries

    Example usage:
        # API error with exception details
        TransformResult.error({
            "reason": "api_error",
            "error": str(e),
            "error_type": "http_error",
        })

        # Field-related error
        TransformResult.error({
            "reason": "missing_field",
            "field": "customer_id",
        })

        # LLM response truncation
        TransformResult.error({
            "reason": "response_truncated",
            "error": "Response was truncated at 1000 tokens",
            "query": "sentiment",
            "max_tokens": 1000,
            "completion_tokens": 1000,
        })
    """

    # REQUIRED - error category (Literal-typed for compile-time validation)
    reason: TransformErrorCategory

    # Common context
    error: NotRequired[str]
    field: NotRequired[str]
    error_type: NotRequired[str]
    message: NotRequired[str]
    url: NotRequired[str]

    # Field collision context
    collisions: NotRequired[list[str]]  # Field names that would be overwritten

    # Multi-query/template context
    query: NotRequired[str]
    query_name: NotRequired[str]  # Named query identifier in multi-query
    query_index: NotRequired[int]  # Position of query in multi-query sequence
    failed_query_name: NotRequired[str]  # Name of query that caused atomic failure
    failed_query_index: NotRequired[int]  # Index of query that caused atomic failure
    discarded_successful_queries: NotRequired[int]  # Successful queries discarded (atomic failure)
    template_hash: NotRequired[str]
    template_file_path: NotRequired[str]  # Path to template file; absent = inline template
    template_errors: NotRequired[list[TemplateErrorEntry]]
    failed_queries: NotRequired[list[str | QueryFailureDetail]]  # Query names or detailed failures
    succeeded_count: NotRequired[int]  # Number of successful queries
    total_count: NotRequired[int]  # Total number of queries attempted

    # LLM response context
    available_fields: NotRequired[list[str]]  # Fields present in LLM JSON response (for missing_output_field)
    content_length: NotRequired[int]  # Length of LLM response content
    max_tokens: NotRequired[int]
    completion_tokens: NotRequired[int | None]
    prompt_tokens: NotRequired[int | None]
    finish_reason: NotRequired[str | None]  # LLM finish reason (e.g., "stop", "length")
    raw_response: NotRequired[str]  # LLM response text; absent = empty/unavailable
    raw_response_preview: NotRequired[str]  # Truncated preview; absent = empty/unavailable
    content_after_fence_strip: NotRequired[str]
    usage: NotRequired[UsageStats | dict[str, int]]
    response: NotRequired[dict[str, Any]]
    response_keys: NotRequired[list[str] | None]
    body_preview: NotRequired[str]  # HTTP body preview; absent = empty/unavailable
    content_type: NotRequired[str]

    # Type validation context
    expected: NotRequired[str]
    actual: NotRequired[str]
    actual_type: NotRequired[str]
    value: NotRequired[str]

    # Contract violation context
    violation_type: NotRequired[str]
    original_field: NotRequired[str]
    count: NotRequired[int]
    violations: NotRequired[list[dict[str, Any]]]

    # Rate limiting/timeout context
    elapsed_seconds: NotRequired[float]
    max_seconds: NotRequired[float]
    elapsed_hours: NotRequired[float]  # Batch timeout (hours scale)
    max_wait_hours: NotRequired[float]  # Batch max wait time (hours)
    status_code: NotRequired[int]

    # RAG retrieval context
    provider: NotRequired[str]  # Retrieval provider name (e.g., "azure_search", "chroma")
    cause: NotRequired[str]  # Sub-cause within error category (e.g., "null_value", "empty_query")
    pattern: NotRequired[str]  # Regex pattern string (for no_regex_match errors)

    # Content filtering context
    matched_pattern: NotRequired[str]
    match_context: NotRequired[str]
    match_position: NotRequired[int]  # Start offset of match in field value
    match_length: NotRequired[int]  # Length of matched substring
    field_length: NotRequired[int]  # Total length of scanned field value
    categories: NotRequired[list[str] | dict[str, dict[str, Any]]]  # List of names OR detailed severity/threshold map
    attacks: NotRequired[dict[str, bool]]  # Prompt shield attack flags (user_prompt_attack, document_attack)

    # Batch processing context
    batch_id: NotRequired[str]
    batch_size: NotRequired[int]  # Total rows in batch
    valid_count: NotRequired[int]  # Rows that passed validation within batch
    queries_completed: NotRequired[int]
    row_errors: NotRequired[list[RowErrorEntry]]
    output_file_id: NotRequired[str]  # Batch output file reference
    malformed_count: NotRequired[int]  # Count of malformed batch lines
    errors: NotRequired[list[str | ErrorDetail]]  # Error messages or structured errors
    skipped_non_finite: NotRequired[int]  # Count of NaN/Inf values skipped
    skipped_non_finite_indices: NotRequired[list[int]]  # Row indices with non-finite values


class SourceQuarantineReason(TypedDict):
    """Reason for source quarantine routing.

    Used when source validation fails and the row is routed to a quarantine sink
    via a DIVERT edge. The quarantine_error field distinguishes this variant from
    gate and transform reasons.

    Required field:
        quarantine_error: Description of the validation failure that caused quarantine
    """

    quarantine_error: str


# Discriminated union - field presence distinguishes variants:
# - ConfigGateReason has "condition" and "result"
# - TransformErrorReason has "reason" (error category string)
# - SourceQuarantineReason has "quarantine_error"
RoutingReason = ConfigGateReason | TransformErrorReason | SourceQuarantineReason


# =============================================================================
# Control Flow Exceptions
# =============================================================================


class MaxRetriesExceeded(Exception):
    """Raised when max retry attempts are exceeded.

    This is a control-flow exception used by RetryManager to signal that
    all retry attempts have been exhausted. FailureInfo uses this to
    construct structured error records for the audit trail.

    Attributes:
        attempts: Number of attempts made before giving up
        last_error: The exception from the final attempt
    """

    def __init__(self, attempts: int, last_error: BaseException) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Max retries ({attempts}) exceeded: {last_error}")


class BatchPendingError(Exception):
    """Raised when batch is submitted but not yet complete.

    This is NOT an error condition - it's a control flow signal
    telling the engine to schedule a retry check later.

    The exception carries the checkpoint state so the caller can persist
    it and restore it when scheduling a retry. This enables crash recovery
    and correct resume behavior.

    Attributes:
        batch_id: Azure batch job ID
        status: Current batch status (e.g., "submitted", "in_progress")
        check_after_seconds: When to check again (default 300s = 5 min)
        checkpoint: Typed checkpoint state for retry (BatchCheckpointState)
        node_id: Transform node ID that raised this (for checkpoint keying)

    Example:
        # Phase 1: Submit batch
        batch_id = client.batches.create(...)
        state = BatchCheckpointState(batch_id=batch_id, ...)
        ctx.set_checkpoint(state)
        raise BatchPendingError(
            batch_id, "submitted",
            check_after_seconds=300,
            checkpoint=state,
            node_id=self.node_id,
        )

        # Caller catches, persists checkpoint.to_dict(), schedules retry

        # Phase 2: Resume and check (caller passes checkpoint back via orchestrator)
        checkpoint = ctx.get_checkpoint()
        if checkpoint is not None:
            status = client.batches.retrieve(checkpoint.batch_id).status
            if status == "in_progress":
                raise BatchPendingError(checkpoint.batch_id, "in_progress", checkpoint=checkpoint)
            elif status == "completed":
                # Download results and return
    """

    def __init__(
        self,
        batch_id: str,
        status: str,
        *,
        check_after_seconds: int = 300,
        checkpoint: "BatchCheckpointState | None" = None,
        node_id: str | None = None,
    ) -> None:
        """Initialize BatchPendingError.

        Args:
            batch_id: Azure batch job ID
            status: Current batch status
            check_after_seconds: Seconds until next check (default 300)
            checkpoint: Typed checkpoint state for retry (BatchCheckpointState)
            node_id: Transform node ID (for checkpoint keying)
        """
        self.batch_id = batch_id
        self.status = status
        self.check_after_seconds = check_after_seconds
        self.checkpoint = checkpoint
        self.node_id = node_id
        super().__init__(f"Batch {batch_id} is {status}, check after {check_after_seconds}s")


class GracefulShutdownError(Exception):
    """Raised when a pipeline run is interrupted by a shutdown signal.

    This is a CONTROL-FLOW SIGNAL, like BatchPendingError. It indicates the
    orchestrator stopped processing new rows due to SIGINT/SIGTERM but
    completed all in-flight work (aggregation flush, sink writes, checkpoints).

    The run is marked INTERRUPTED and is resumable via ``elspeth resume``.
    """

    def __init__(
        self,
        rows_processed: int,
        run_id: str,
        *,
        rows_succeeded: int = 0,
        rows_failed: int = 0,
        rows_quarantined: int = 0,
        rows_routed: int = 0,
        routed_destinations: dict[str, int] | None = None,
    ) -> None:
        self.rows_processed = rows_processed
        self.run_id = run_id
        self.rows_succeeded = rows_succeeded
        self.rows_failed = rows_failed
        self.rows_quarantined = rows_quarantined
        self.rows_routed = rows_routed
        self.routed_destinations: Mapping[str, int] = (
            MappingProxyType(dict(routed_destinations)) if routed_destinations is not None else MappingProxyType({})
        )
        super().__init__(
            f"Pipeline interrupted after {rows_processed} rows (run_id={run_id}). Resume with: elspeth resume {run_id} --execute"
        )


class AuditIntegrityError(Exception):
    """Raised when audit database operations fail unexpectedly.

    This indicates catastrophic failure: database corruption, transaction
    failure, or bug in Landscape recording code. Per Tier 1 trust model,
    ELSPETH cannot continue with compromised audit integrity.

    Examples of conditions that trigger this:
    - Run record not found after INSERT/UPDATE
    - NodeState not found after completion update
    - Batch record not found after update
    - State marked terminal but still shows OPEN status

    Recovery: These errors are NOT recoverable. The pipeline must stop
    and the database must be investigated for corruption or tampering.
    """

    pass


class OrchestrationInvariantError(Exception):
    """Raised when orchestration invariants are violated.

    This indicates a bug in the engine: node_id not set before execution,
    routing to non-existent edges, etc. These are programming errors
    that must crash immediately.

    Examples of conditions that trigger this:
    - Transform/Gate/Sink executed without node_id assigned
    - Edge resolution fails due to missing node_id
    - Last transform in pipeline has no node_id

    Recovery: These errors indicate bugs in orchestration code that must
    be fixed. They should never occur in correct operation.
    """

    pass


class PluginRetryableError(Exception):
    """Base for plugin exceptions eligible for engine retry.

    All plugin error types that may be retried by the engine's RetryManager
    must inherit from this class. The processor catches PluginRetryableError
    and dispatches to retry logic based on the retryable attribute.

    Attributes:
        retryable: Whether the error is transient and should be retried.
        status_code: HTTP status code if applicable (for audit context).
    """

    def __init__(self, message: str, *, retryable: bool, status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class FrameworkBugError(Exception):
    """Raised when the framework encounters an internal inconsistency.

    This indicates a bug in ELSPETH itself, not user error or external failure.
    Unlike OrchestrationInvariantError (specific to orchestration flow), this
    is a general-purpose exception for any framework-level bug.

    Examples of conditions that trigger this:
    - Double-completing an operation (already completed, trying to complete again)
    - Missing required context (record_call with neither state_id nor operation_id)
    - Completing a non-existent operation

    Recovery: These errors indicate bugs in framework code that must be fixed.
    They should never occur in correct operation.
    """

    pass


class PluginContractViolation(RuntimeError):
    """Raised when a plugin violates its contract with the framework.

    This indicates a bug in a plugin (Source, Transform, Gate, Sink) that must
    be fixed. Unlike user data errors (which are quarantined), plugin bugs
    MUST crash the pipeline per CLAUDE.md's "plugin bugs must crash" rule.

    Examples of conditions that trigger this:
    - Transform emits non-canonical data (NaN, Infinity, non-serializable types)
    - Plugin returns wrong type from method
    - Plugin violates interface contract

    Recovery: Fix the plugin. These errors indicate bugs in plugin code.
    """

    pass


# =============================================================================
# Schema Contract Violation Types (Tier 3 - External Data)
# =============================================================================
# These exceptions represent validation failures on external/user data.
# They result in row quarantine, NOT crashes. Per CLAUDE.md Three-Tier Trust Model,
# Tier 3 data (external) can be "literal trash" and must be handled gracefully.
#
# Error messages follow "'original' (normalized)" format for debuggability:
#   "Required field 'Customer ID' (customer_id) is missing"
# This shows both what the user sees (original) and what code uses (normalized).
# =============================================================================


class ContractViolation(Exception):
    """Base exception for schema contract violations.

    All schema contract violations track both the normalized field name
    (used internally by code) and the original field name (from user's
    perspective, e.g., CSV column headers).

    Attributes:
        normalized_name: Internal field name used by code (e.g., "customer_id")
        original_name: Original field name from external data (e.g., "Customer ID")
    """

    def __init__(self, *, normalized_name: str, original_name: str) -> None:
        """Initialize ContractViolation.

        Args:
            normalized_name: Internal field name used by code
            original_name: Original field name from external data
        """
        self.normalized_name = normalized_name
        self.original_name = original_name
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the error message. Override in subclasses for specific messages."""
        return f"Contract violation on field '{self.original_name}' ({self.normalized_name})"

    def to_error_reason(self) -> dict[str, Any]:
        """Convert violation to TransformErrorReason dict.

        Returns:
            Dict with 'reason' key suitable for TransformResult.error().
            The violation_type is derived from the class name.
        """
        return {
            "reason": "contract_violation",
            "violation_type": self.__class__.__name__,
            "field": self.normalized_name,
            "original_field": self.original_name,
        }


class MissingFieldViolation(ContractViolation):
    """Raised when a required field is missing from the data.

    This is a Tier 3 data violation - the external data is missing a field
    that the schema declares as required. Results in row quarantine.

    Example:
        >>> raise MissingFieldViolation(normalized_name="customer_id", original_name="Customer ID")
        MissingFieldViolation: Required field 'Customer ID' (customer_id) is missing
    """

    def _format_message(self) -> str:
        """Format message showing required field is missing."""
        return f"Required field '{self.original_name}' ({self.normalized_name}) is missing"


class TypeMismatchViolation(ContractViolation):
    """Raised when a field value has the wrong type.

    This is a Tier 3 data violation - the external data has a value that
    doesn't match the expected type. Results in row quarantine.

    Attributes:
        expected_type: The type that was expected (e.g., int, str)
        actual_type: The type that was received (e.g., str, float)
        actual_value: The actual value received (for debugging)

    Note:
        The `actual_value` attribute is accessible programmatically for debugging
        purposes, but is intentionally excluded from the error message (str/repr).
        This prevents potentially sensitive user data from being exposed in logs,
        audit trails, or error reports. Callers needing the value for investigation
        should access the attribute directly.

    Example:
        >>> raise TypeMismatchViolation(
        ...     normalized_name="amount",
        ...     original_name="Amount",
        ...     expected_type=int,
        ...     actual_type=str,
        ...     actual_value="not_a_number"
        ... )
        TypeMismatchViolation: Field 'Amount' (amount) expected type 'int', got 'str'
    """

    def __init__(
        self,
        *,
        normalized_name: str,
        original_name: str,
        expected_type: type,
        actual_type: type,
        actual_value: Any,
    ) -> None:
        """Initialize TypeMismatchViolation.

        Args:
            normalized_name: Internal field name used by code
            original_name: Original field name from external data
            expected_type: The type that was expected
            actual_type: The type that was received
            actual_value: The actual value received
        """
        self.expected_type = expected_type
        self.actual_type = actual_type
        self.actual_value = actual_value
        super().__init__(normalized_name=normalized_name, original_name=original_name)

    def _format_message(self) -> str:
        """Format message showing type mismatch."""
        return f"Field '{self.original_name}' ({self.normalized_name}) expected type '{self.expected_type.__name__}', got '{self.actual_type.__name__}'"

    def to_error_reason(self) -> dict[str, Any]:
        """Convert violation to TransformErrorReason dict with type details.

        Returns:
            Dict with 'reason' key and type-specific fields suitable for
            TransformResult.error(). Includes expected and actual type names
            only. Raw values are intentionally excluded to prevent sensitive
            or unbounded data from reaching the audit trail.
        """
        base = super().to_error_reason()
        base.update(
            {
                "expected": self.expected_type.__name__,
                "actual": self.actual_type.__name__,
            }
        )
        return base


class ExtraFieldViolation(ContractViolation):
    """Raised when an unexpected field is present in FIXED schema mode.

    This is a Tier 3 data violation - the external data contains a field
    that is not declared in the schema, and the schema is in FIXED mode
    (no extra fields allowed). Results in row quarantine.

    Example:
        >>> raise ExtraFieldViolation(normalized_name="unknown_col", original_name="Unknown Col")
        ExtraFieldViolation: Extra field 'Unknown Col' (unknown_col) not allowed in FIXED mode
    """

    def _format_message(self) -> str:
        """Format message showing extra field not allowed."""
        return f"Extra field '{self.original_name}' ({self.normalized_name}) not allowed in FIXED mode"


class ContractMergeError(ValueError):
    """Raised when schema contracts cannot be merged due to type conflicts.

    This occurs during fork/join (coalesce) operations when parallel paths
    produce incompatible types for the same field. This is a configuration
    error (pipeline design issue), not a data error.

    Inherits from ValueError because it represents an invalid combination
    of schema contracts, not an external data issue.

    Attributes:
        field: The field name with conflicting types
        type_a: The type from one path
        type_b: The type from another path

    Example:
        >>> raise ContractMergeError(field="amount", type_a="int", type_b="str")
        ContractMergeError: Cannot merge contracts: field 'amount' has conflicting types 'int' and 'str'
    """

    def __init__(self, *, field: str, type_a: str, type_b: str) -> None:
        """Initialize ContractMergeError.

        Args:
            field: The field name with conflicting types
            type_a: The type from one path
            type_b: The type from another path
        """
        self.field = field
        self.type_a = type_a
        self.type_b = type_b
        super().__init__(f"Cannot merge contracts: field '{field}' has conflicting types '{type_a}' and '{type_b}'")


# =============================================================================
# Contract Violation to Error Conversion Helpers
# =============================================================================


def violations_to_error_reason(violations: list[ContractViolation]) -> dict[str, Any]:
    """Convert list of violations to TransformErrorReason.

    Provides a convenient way to convert one or more contract violations
    into a dict suitable for TransformResult.error().

    Args:
        violations: List of ContractViolation instances

    Returns:
        Single violation: its to_error_reason() directly
        Multiple violations: wrapped dict with count and list

    Raises:
        ValueError: If violations list is empty

    Example:
        >>> violations = [
        ...     MissingFieldViolation(normalized_name="id", original_name="ID"),
        ...     TypeMismatchViolation(
        ...         normalized_name="amount",
        ...         original_name="Amount",
        ...         expected_type=int,
        ...         actual_type=str,
        ...         actual_value="bad"
        ...     ),
        ... ]
        >>> reason = violations_to_error_reason(violations)
        >>> reason["reason"]
        'multiple_contract_violations'
        >>> reason["count"]
        2
    """
    if not violations:
        raise ValueError("violations list cannot be empty")

    if len(violations) == 1:
        return violations[0].to_error_reason()

    return {
        "reason": "multiple_contract_violations",
        "count": len(violations),
        "violations": [v.to_error_reason() for v in violations],
    }


# =============================================================================
# RAG Ingestion Pipeline Errors
# =============================================================================


class DependencyFailedError(Exception):
    """A pipeline dependency failed to complete successfully."""

    def __init__(self, *, dependency_name: str, run_id: str, reason: str) -> None:
        self.dependency_name = dependency_name
        self.run_id = run_id
        self.reason = reason
        super().__init__(f"Dependency '{dependency_name}' failed (run_id={run_id}): {reason}")


class CommencementGateFailedError(Exception):
    """A commencement gate evaluated to falsy or raised an error."""

    def __init__(
        self,
        *,
        gate_name: str,
        condition: str,
        reason: str,
        context_snapshot: Mapping[str, Any],
    ) -> None:
        from elspeth.contracts.freeze import deep_freeze

        self.gate_name = gate_name
        self.condition = condition
        self.reason = reason
        self.context_snapshot: Mapping[str, Any] = deep_freeze(context_snapshot)
        super().__init__(f"Commencement gate '{gate_name}' failed: {reason} (condition: {condition})")


class RetrievalNotReadyError(Exception):
    """A retrieval provider's collection is empty or unreachable."""

    def __init__(self, *, collection: str, reason: str) -> None:
        self.collection = collection
        self.reason = reason
        super().__init__(f"Collection {collection!r} not ready: {reason}")


class DuplicateDocumentError(Exception):
    """Sink rejected a write because document IDs already exist in the collection.

    Raised when on_duplicate='error' and pre-existing IDs are detected.
    """

    def __init__(self, *, collection: str, duplicate_ids: list[str]) -> None:
        if not duplicate_ids:
            raise ValueError("duplicate_ids must not be empty — DuplicateDocumentError requires at least one duplicate")
        self.collection = collection
        self.duplicate_ids = tuple(duplicate_ids)
        super().__init__(f"Duplicate document IDs in collection {collection!r}: {list(self.duplicate_ids)}")
