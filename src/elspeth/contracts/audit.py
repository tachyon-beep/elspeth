"""Audit trail contracts for Landscape tables.

These are strict contracts - all enum fields use proper enum types.
Model loader layer handles string→enum conversion for DB reads.

Per Data Manifesto: The audit database is OUR data. If we read
garbage from it, something catastrophic happened - crash immediately.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal, TypedDict

from elspeth.contracts.freeze import deep_freeze

if TYPE_CHECKING:
    pass  # Placeholder for future type-only imports

from elspeth.contracts.enums import (
    BatchStatus,
    CallStatus,
    CallType,
    Determinism,
    ExportStatus,
    NodeStateStatus,
    NodeType,
    ReproducibilityGrade,
    RoutingMode,
    RowOutcome,
    RunStatus,
    TriggerType,
)


def _validate_enum(value: object, enum_type: type, field_name: str) -> None:
    """Validate that value is an instance of the expected enum type.

    Tier 1 audit data must crash on invalid types - no coercion, no defaults.
    Per Data Manifesto: If we read garbage from our own database,
    something catastrophic happened - crash immediately.
    """
    if value is not None and not isinstance(value, enum_type):
        raise TypeError(f"{field_name} must be {enum_type.__name__}, got {type(value).__name__}: {value!r}")


@dataclass(frozen=True, slots=True)
class Run:
    """A single execution of a pipeline.

    Strict contract - status must be RunStatus enum.
    """

    run_id: str
    started_at: datetime
    config_hash: str
    settings_json: str
    canonical_version: str
    status: RunStatus  # Strict: enum only
    completed_at: datetime | None = None
    reproducibility_grade: ReproducibilityGrade | None = None
    export_status: ExportStatus | None = None  # Strict: enum only
    export_error: str | None = None
    exported_at: datetime | None = None
    export_format: str | None = None
    export_sink: str | None = None

    def __post_init__(self) -> None:
        """Validate enum fields - Tier 1 crash on invalid types."""
        _validate_enum(self.status, RunStatus, "status")
        _validate_enum(self.reproducibility_grade, ReproducibilityGrade, "reproducibility_grade")
        _validate_enum(self.export_status, ExportStatus, "export_status")


@dataclass(frozen=True, slots=True)
class Node:
    """A node (plugin instance) in the execution graph.

    Strict contract - node_type and determinism must be enums.
    """

    node_id: str
    run_id: str
    plugin_name: str
    node_type: NodeType  # Strict: enum only
    plugin_version: str
    determinism: Determinism  # Strict: enum only
    config_hash: str
    config_json: str
    registered_at: datetime
    schema_hash: str | None = None
    sequence_in_pipeline: int | None = None
    # Schema configuration for audit trail (WP-11.99)
    schema_mode: str | None = None  # "observed", "fixed", "flexible", "parse"
    schema_fields: Sequence[Mapping[str, object]] | None = None  # Field definitions if explicit

    def __post_init__(self) -> None:
        """Validate enum fields - Tier 1 crash on invalid types."""
        _validate_enum(self.node_type, NodeType, "node_type")
        _validate_enum(self.determinism, Determinism, "determinism")
        if self.schema_fields is not None:
            frozen = deep_freeze(self.schema_fields)
            if frozen is not self.schema_fields:
                object.__setattr__(self, "schema_fields", frozen)


@dataclass(frozen=True, slots=True)
class Edge:
    """An edge in the execution graph.

    Strict contract - default_mode must be RoutingMode enum.
    """

    edge_id: str
    run_id: str
    from_node_id: str
    to_node_id: str
    label: str
    default_mode: RoutingMode  # Strict: enum only
    created_at: datetime

    def __post_init__(self) -> None:
        """Validate enum fields - Tier 1 crash on invalid types."""
        _validate_enum(self.default_mode, RoutingMode, "default_mode")


@dataclass(frozen=True, slots=True)
class Row:
    """A source row loaded into the system."""

    row_id: str
    run_id: str
    source_node_id: str
    row_index: int
    source_data_hash: str
    created_at: datetime
    source_data_ref: str | None = None


@dataclass(frozen=True, slots=True)
class Token:
    """A row instance flowing through a specific DAG path."""

    token_id: str
    row_id: str
    created_at: datetime
    run_id: str
    fork_group_id: str | None = None
    join_group_id: str | None = None
    expand_group_id: str | None = None  # For deaggregation grouping
    branch_name: str | None = None
    step_in_pipeline: int | None = None  # Step where token was created (fork/coalesce/expand)


@dataclass(frozen=True, slots=True)
class TokenParent:
    """Parent relationship for tokens (supports multi-parent joins)."""

    token_id: str
    parent_token_id: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class NodeStateOpen:
    """A node state currently being processed.

    Invariants:
    - No output_hash (not produced yet)
    - No completed_at (not completed)
    - No duration_ms (not finished timing)
    """

    state_id: str
    token_id: str
    node_id: str
    step_index: int
    attempt: int
    status: Literal[NodeStateStatus.OPEN]
    input_hash: str
    started_at: datetime
    context_before_json: str | None = None


@dataclass(frozen=True, slots=True)
class NodeStatePending:
    """A node state where processing completed but output is pending.

    Used for async operations like batch submission where the operation
    completed successfully but the result won't be available until later.

    Invariants:
    - No output_hash (result not available yet)
    - Has completed_at (operation finished)
    - Has duration_ms (timing complete)
    """

    state_id: str
    token_id: str
    node_id: str
    step_index: int
    attempt: int
    status: Literal[NodeStateStatus.PENDING]
    input_hash: str
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    context_before_json: str | None = None
    context_after_json: str | None = None


@dataclass(frozen=True, slots=True)
class NodeStateCompleted:
    """A node state that completed successfully.

    Invariants:
    - Has output_hash (produced output)
    - Has completed_at (finished)
    - Has duration_ms (timing complete)
    """

    state_id: str
    token_id: str
    node_id: str
    step_index: int
    attempt: int
    status: Literal[NodeStateStatus.COMPLETED]
    input_hash: str
    started_at: datetime
    output_hash: str
    completed_at: datetime
    duration_ms: float
    context_before_json: str | None = None
    context_after_json: str | None = None
    success_reason_json: str | None = None


@dataclass(frozen=True, slots=True)
class NodeStateFailed:
    """A node state that failed during processing.

    Invariants:
    - Has completed_at (finished, with failure)
    - Has duration_ms (timing complete)
    - May have error_json
    """

    state_id: str
    token_id: str
    node_id: str
    step_index: int
    attempt: int
    status: Literal[NodeStateStatus.FAILED]
    input_hash: str
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    error_json: str | None = None
    output_hash: str | None = None
    context_before_json: str | None = None
    context_after_json: str | None = None


# Discriminated union type
NodeState = NodeStateOpen | NodeStatePending | NodeStateCompleted | NodeStateFailed


@dataclass(frozen=True, slots=True)
class Call:
    """An external call made during node processing or operation.

    Strict contract - call_type and status must be enums.

    Calls can be parented by either:
    - node_state (transform processing): state_id is set, operation_id is None
    - operation (source/sink I/O): operation_id is set, state_id is None

    The XOR constraint is enforced at the database level.
    """

    call_id: str
    call_index: int
    call_type: CallType  # Strict: enum only
    status: CallStatus  # Strict: enum only
    request_hash: str
    created_at: datetime
    # Parent context - exactly one must be set (XOR)
    state_id: str | None = None  # For transform calls
    operation_id: str | None = None  # For source/sink calls
    request_ref: str | None = None
    response_hash: str | None = None
    response_ref: str | None = None
    error_json: str | None = None
    latency_ms: float | None = None

    def __post_init__(self) -> None:
        """Validate enum fields and structural invariants — Tier 1 crash on invalid types."""
        _validate_enum(self.call_type, CallType, "call_type")
        _validate_enum(self.status, CallStatus, "status")
        # XOR: exactly one of state_id or operation_id must be set
        has_state = self.state_id is not None
        has_operation = self.operation_id is not None
        if has_state == has_operation:
            raise ValueError(
                f"Call requires exactly one of state_id or operation_id. Got state_id={self.state_id!r}, operation_id={self.operation_id!r}"
            )


@dataclass(frozen=True, slots=True)
class Artifact:
    """An artifact produced by a sink."""

    artifact_id: str
    run_id: str
    produced_by_state_id: str
    sink_node_id: str
    artifact_type: str  # Not enum - user-defined (csv, json, webhook, etc.)
    path_or_uri: str
    content_hash: str
    size_bytes: int
    created_at: datetime
    idempotency_key: str | None = None  # For retry deduplication


@dataclass(frozen=True, slots=True)
class RoutingEvent:
    """A routing decision at a gate node.

    Strict contract - mode must be RoutingMode enum.
    """

    event_id: str
    state_id: str
    edge_id: str
    routing_group_id: str
    ordinal: int
    mode: RoutingMode  # Strict: enum only
    created_at: datetime
    reason_hash: str | None = None
    reason_ref: str | None = None

    def __post_init__(self) -> None:
        """Validate enum fields - Tier 1 crash on invalid types."""
        _validate_enum(self.mode, RoutingMode, "mode")


@dataclass(frozen=True, slots=True)
class Batch:
    """An aggregation batch collecting tokens.

    Strict contract - status and trigger_type must be enums.
    """

    batch_id: str
    run_id: str
    aggregation_node_id: str
    attempt: int
    status: BatchStatus  # Strict: enum only
    created_at: datetime
    aggregation_state_id: str | None = None
    trigger_type: TriggerType | None = None  # Strict: enum only
    trigger_reason: str | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate enum fields - Tier 1 crash on invalid types."""
        _validate_enum(self.status, BatchStatus, "status")
        _validate_enum(self.trigger_type, TriggerType, "trigger_type")


@dataclass(frozen=True, slots=True)
class BatchMember:
    """A token belonging to a batch."""

    batch_id: str
    token_id: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class BatchOutput:
    """An output produced by a batch."""

    batch_id: str
    output_type: str  # token, artifact
    output_id: str


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Checkpoint for crash recovery.

    Captures run progress at row/transform boundaries.

    Format Versions:
        Version 1: Pre-deterministic node IDs (legacy, incompatible)
        Version 2: Deterministic node IDs (2026-01-24+)
        Version 3: Phase 2 traversal refactor checkpoint break
        Version 4: Pending coalesce state persisted in checkpoints (current)
    """

    # Current checkpoint format version (ClassVar excludes from dataclass fields)
    CURRENT_FORMAT_VERSION: ClassVar[int] = 4

    checkpoint_id: str
    run_id: str
    token_id: str
    node_id: str
    sequence_number: int
    created_at: datetime  # Required - schema enforces NOT NULL (Tier 1 audit data)
    # Topology validation fields - REQUIRED for checkpoint compatibility checking
    # Schema enforces NOT NULL - these are audit-critical for resume validation
    upstream_topology_hash: str  # Hash of ALL nodes + edges in DAG (full topology)
    checkpoint_node_config_hash: str  # Hash of checkpoint node config only
    # Optional fields (with defaults) MUST come after required fields in dataclass
    aggregation_state_json: str | None = None
    coalesce_state_json: str | None = None
    # Format version for compatibility checking
    format_version: int | None = None

    def __post_init__(self) -> None:
        """Validate required fields - Tier 1 crash on invalid data.

        Per Data Manifesto: Audit data is OUR data. If we receive None
        for required hash fields, that's a bug in our code - crash immediately.
        """
        if not self.upstream_topology_hash:
            raise ValueError("upstream_topology_hash is required and cannot be empty")
        if not self.checkpoint_node_config_hash:
            raise ValueError("checkpoint_node_config_hash is required and cannot be empty")


@dataclass(frozen=True, slots=True)
class RowLineage:
    """Source row with resolved payload for explain output.

    Combines Row DB record fields with resolved payload data.
    Used by LineageResult.source_row for complete explain output.

    Supports graceful payload degradation - hash always preserved,
    actual data may be unavailable after retention purge.
    """

    # From Row (DB record fields)
    row_id: str
    run_id: str
    source_node_id: str
    row_index: int
    source_data_hash: str  # Consistent naming with Row
    created_at: datetime

    # Resolved payload (from PayloadStore)
    source_data: Mapping[str, object] | None  # None if purged
    payload_available: bool

    def __post_init__(self) -> None:
        if self.source_data is not None:
            frozen = deep_freeze(self.source_data)
            if frozen is not self.source_data:
                object.__setattr__(self, "source_data", frozen)


class ExportStatusUpdate(TypedDict, total=False):
    """Schema for export status updates in recorder.

    Used by recorder methods that update export-related fields on Run records.
    Uses total=False to allow partial updates.
    """

    export_status: ExportStatus
    exported_at: datetime
    export_error: str
    export_format: str
    export_sink: str


class BatchStatusUpdate(TypedDict, total=False):
    """Schema for batch status updates in recorder.

    Used by recorder methods that update batch-related fields.
    Uses total=False to allow partial updates.
    """

    status: BatchStatus
    completed_at: datetime
    trigger_reason: str
    aggregation_state_id: str


@dataclass(frozen=True, slots=True)
class ValidationErrorRecord:
    """A validation error recorded in the audit trail.

    Created when a source row fails schema validation.
    These are operational errors (bad user data), not system bugs.
    """

    error_id: str
    run_id: str
    node_id: str | None
    row_hash: str
    error: str
    schema_mode: str  # "fixed", "flexible", "observed", "parse"
    destination: str
    created_at: datetime
    row_data_json: str | None = None


@dataclass(frozen=True, slots=True)
class NonCanonicalMetadata:
    """Metadata for non-canonical data stored in the audit trail.

    When data cannot be canonically serialized (contains NaN, Infinity,
    non-dict types, etc.), this metadata captures what we saw for forensic
    analysis.

    This is part of the Tier-3 (external data) trust boundary handling.
    Non-canonical data is quarantined and recorded with this metadata
    instead of crashing the pipeline.

    Invariants:
    - repr_value is never empty (captures what we saw)
    - type_name must be a valid Python type name
    - canonical_error explains why canonical serialization failed

    Fields:
        repr_value: Result of repr(data)
        type_name: type(data).__name__
        canonical_error: Why canonicalization failed
    """

    repr_value: str
    type_name: str
    canonical_error: str

    def to_dict(self) -> dict[str, str]:
        """Convert to dict for JSON serialization.

        Returns dict with keys matching current inline dict structure
        for backwards compatibility with existing audit data.

        Returns:
            Dict with __repr__, __type__, __canonical_error__ keys
        """
        return {
            "__repr__": self.repr_value,
            "__type__": self.type_name,
            "__canonical_error__": self.canonical_error,
        }

    @classmethod
    def from_error(cls, data: Any, error: Exception) -> "NonCanonicalMetadata":
        """Create metadata from data that failed canonicalization.

        Factory method for convenient creation from exception context.

        Args:
            data: The non-canonical data
            error: The canonicalization exception (ValueError or TypeError)

        Returns:
            NonCanonicalMetadata instance

        Example:
            >>> try:
            ...     canonical_json({"value": float("nan")})
            ... except ValueError as e:
            ...     meta = NonCanonicalMetadata.from_error({"value": float("nan")}, e)
        """
        return cls(
            repr_value=repr(data),
            type_name=type(data).__name__,
            canonical_error=str(error),
        )


@dataclass(frozen=True, slots=True)
class TransformErrorRecord:
    """A transform processing error recorded in the audit trail.

    Created when a transform returns TransformResult.error().
    These are operational errors (bad data values), not transform bugs.
    """

    error_id: str
    run_id: str
    token_id: str
    transform_id: str
    row_hash: str
    destination: str
    created_at: datetime
    row_data_json: str | None = None
    error_details_json: str | None = None


@dataclass(frozen=True, slots=True)
class TokenOutcome:
    """Recorded terminal state for a token.

    Captures the moment a token reached its terminal (or buffered) state.
    Part of AUD-001 audit integrity - explicit rather than derived.
    """

    outcome_id: str
    run_id: str
    token_id: str
    outcome: RowOutcome  # Direct type, not forward reference
    is_terminal: bool
    recorded_at: datetime

    # Outcome-specific fields (nullable based on outcome type)
    sink_name: str | None = None
    batch_id: str | None = None
    fork_group_id: str | None = None
    join_group_id: str | None = None
    expand_group_id: str | None = None
    error_hash: str | None = None
    context_json: str | None = None
    expected_branches_json: str | None = None  # Branch contract for FORKED/EXPANDED

    def __post_init__(self) -> None:
        """Validate enum and bool fields - Tier 1 crash on invalid types."""
        _validate_enum(self.outcome, RowOutcome, "outcome")
        # is_terminal must be bool, not int or other truthy/falsy value
        if not isinstance(self.is_terminal, bool):
            raise TypeError(f"is_terminal must be bool, got {type(self.is_terminal).__name__}: {self.is_terminal!r}")


@dataclass(frozen=True, slots=True)
class Operation:
    """Represents a source/sink I/O operation in the audit trail.

    Operations are the equivalent of node_states for sources and sinks.
    They provide a parent context for external calls made during
    source.load() or sink.write().

    Unlike node_states (which require a token_id because they process
    existing data flow), operations exist at the run/node level because
    sources CREATE tokens rather than processing them.

    Lifecycle:
        1. begin_operation() creates with status='open'
        2. External calls recorded via record_operation_call()
        3. complete_operation() sets status to 'completed' or 'failed'

    The operation_id follows format "op_{uuid4().hex}" to stay within
    the 64-char column limit while remaining globally unique.
    """

    operation_id: str
    run_id: str
    node_id: str
    operation_type: Literal["source_load", "sink_write"]
    started_at: datetime
    status: Literal["open", "completed", "failed", "pending"]
    completed_at: datetime | None = None
    input_data_ref: str | None = None
    input_data_hash: str | None = None
    output_data_ref: str | None = None
    output_data_hash: str | None = None
    error_message: str | None = None
    duration_ms: float | None = None

    _ALLOWED_OPERATION_TYPES: ClassVar[frozenset[str]] = frozenset({"source_load", "sink_write"})
    _ALLOWED_STATUSES: ClassVar[frozenset[str]] = frozenset({"open", "completed", "failed", "pending"})

    def __post_init__(self) -> None:
        """Validate constrained literal fields and lifecycle invariants for Tier 1 audit integrity.

        Status-dependent invariants:
        - open: completed_at, duration_ms, error_message must all be None
        - completed: completed_at and duration_ms must be present, error_message must be None
        - failed: completed_at and duration_ms must be present, error_message must be present
        - pending: completed_at and duration_ms must be present
        """
        if self.operation_type not in self._ALLOWED_OPERATION_TYPES:
            raise ValueError(f"operation_type must be one of {sorted(self._ALLOWED_OPERATION_TYPES)}, got {self.operation_type!r}")

        if self.status not in self._ALLOWED_STATUSES:
            raise ValueError(f"status must be one of {sorted(self._ALLOWED_STATUSES)}, got {self.status!r}")

        # Lifecycle invariant validation — Tier 1 crash on impossible state combinations
        if self.status == "open":
            if self.completed_at is not None:
                raise ValueError(f"Operation {self.operation_id!r}: status='open' but completed_at is set")
            if self.duration_ms is not None:
                raise ValueError(f"Operation {self.operation_id!r}: status='open' but duration_ms is set")
            if self.error_message is not None:
                raise ValueError(f"Operation {self.operation_id!r}: status='open' but error_message is set")
        elif self.status in {"completed", "failed", "pending"}:
            if self.completed_at is None:
                raise ValueError(f"Operation {self.operation_id!r}: status={self.status!r} but completed_at is None")
            if self.duration_ms is None:
                raise ValueError(f"Operation {self.operation_id!r}: status={self.status!r} but duration_ms is None")
            if self.status == "failed" and self.error_message is None:
                raise ValueError(f"Operation {self.operation_id!r}: status='failed' but error_message is None")
            if self.status == "completed" and self.error_message is not None:
                raise ValueError(f"Operation {self.operation_id!r}: status='completed' but error_message is set")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for database insertion.

        Returns dict with keys matching operations table columns.
        """
        return {
            "operation_id": self.operation_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "operation_type": self.operation_type,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "input_data_ref": self.input_data_ref,
            "input_data_hash": self.input_data_hash,
            "output_data_ref": self.output_data_ref,
            "output_data_hash": self.output_data_hash,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class SecretResolution:
    """Record of a secret loaded from Key Vault for audit trail.

    These records enable auditors to answer: "Which Key Vault and which
    secret was used for this pipeline run?" without exposing actual secret
    values (only HMAC fingerprints are stored).

    Secret resolutions are recorded at run start, before processing begins.
    They capture the provenance of secrets loaded from external vaults.

    Attributes:
        resolution_id: Unique identifier for this resolution event
        run_id: Run that used this secret
        timestamp: When the secret was loaded (epoch seconds, may be before run start)
        env_var_name: Environment variable the secret was injected into
        source: Source type ('keyvault' - env source doesn't record)
        vault_url: Key Vault URL (None if source != keyvault)
        secret_name: Secret name in the vault
        fingerprint: HMAC-SHA256 fingerprint of the secret value (not the value itself)
        resolution_latency_ms: Time to fetch from vault (None if not measured)
    """

    _ALLOWED_SOURCES: ClassVar[frozenset[str]] = frozenset({"keyvault"})

    resolution_id: str
    run_id: str
    timestamp: float  # Epoch seconds - may be before run start
    env_var_name: str
    source: str  # 'keyvault'
    fingerprint: str  # HMAC fingerprint, NOT the secret value
    vault_url: str | None = None
    secret_name: str | None = None
    resolution_latency_ms: float | None = None

    def __post_init__(self) -> None:
        """Validate Tier 1 invariants for secret provenance records.

        Per Data Manifesto: The audit database is OUR data. If we read
        garbage from it, something catastrophic happened - crash immediately.

        Invariants:
        - resolution_id, run_id, env_var_name, source, fingerprint must be non-empty strings
        - source must be a known value ('keyvault')
        - fingerprint must be 64-char lowercase hex (HMAC-SHA256)
        - timestamp must be finite
        - resolution_latency_ms must be non-negative when present
        - keyvault source requires non-empty vault_url and secret_name
        """
        import math

        if not self.resolution_id:
            raise ValueError("SecretResolution: resolution_id is required and cannot be empty")
        if not self.run_id:
            raise ValueError("SecretResolution: run_id is required and cannot be empty")
        if not self.env_var_name:
            raise ValueError("SecretResolution: env_var_name is required and cannot be empty")
        if not self.source:
            raise ValueError("SecretResolution: source is required and cannot be empty")
        if self.source not in self._ALLOWED_SOURCES:
            raise ValueError(f"SecretResolution: source must be one of {sorted(self._ALLOWED_SOURCES)}, got {self.source!r}")
        if not self.fingerprint:
            raise ValueError("SecretResolution: fingerprint is required and cannot be empty")
        if len(self.fingerprint) != 64 or not all(c in "0123456789abcdef" for c in self.fingerprint):
            raise ValueError(
                f"SecretResolution: fingerprint must be 64-char lowercase hex (HMAC-SHA256), "
                f"got {self.fingerprint!r} (length={len(self.fingerprint)})"
            )
        if not isinstance(self.timestamp, (int, float)) or math.isinf(self.timestamp) or math.isnan(self.timestamp):
            raise ValueError(f"SecretResolution: timestamp must be a finite number, got {self.timestamp!r}")
        if self.resolution_latency_ms is not None and self.resolution_latency_ms < 0:
            raise ValueError(f"SecretResolution: resolution_latency_ms must be non-negative, got {self.resolution_latency_ms!r}")
        if self.source == "keyvault":
            if not self.vault_url:
                raise ValueError("SecretResolution: vault_url is required when source='keyvault'")
            if not self.secret_name:
                raise ValueError("SecretResolution: secret_name is required when source='keyvault'")


@dataclass(frozen=True, slots=True)
class SecretResolutionInput:
    """Write-side DTO for secret resolution records.

    Used at the Tier 1 boundary when recording secret resolutions into the
    audit trail. Replaces the previous dict[str, Any] pattern with compile-time
    key validation. The resolution_id and run_id are assigned at record time,
    not at creation time.

    Follows the TokenUsage precedent (commit dffe74a6) for typed audit inputs.
    """

    _ALLOWED_SOURCES: ClassVar[frozenset[str]] = frozenset({"keyvault"})

    env_var_name: str
    source: str
    vault_url: str | None
    secret_name: str | None
    timestamp: float
    resolution_latency_ms: float
    fingerprint: str

    def __post_init__(self) -> None:
        """Validate write-side invariants before audit trail insertion.

        Lightweight checks for security-critical invariants. The full
        set of business rule validations lives on the read-side
        SecretResolution. These checks prevent:
        - Plaintext secrets being written as fingerprints (security)
        - Invalid source values persisting undetected (Tier 1 integrity)
        - Non-negative latency invariant (data quality)
        """
        if not self.env_var_name:
            raise ValueError("SecretResolutionInput: env_var_name is required and cannot be empty")
        if not self.source or self.source not in self._ALLOWED_SOURCES:
            raise ValueError(f"SecretResolutionInput: source must be one of {sorted(self._ALLOWED_SOURCES)}, got {self.source!r}")
        if len(self.fingerprint) != 64 or not all(c in "0123456789abcdef" for c in self.fingerprint):
            raise ValueError(
                f"SecretResolutionInput: fingerprint must be 64-char lowercase hex (HMAC-SHA256), "
                f"got {self.fingerprint!r} (length={len(self.fingerprint)})"
            )
        if self.resolution_latency_ms < 0:
            raise ValueError(f"SecretResolutionInput: resolution_latency_ms must be non-negative, got {self.resolution_latency_ms!r}")
