"""Shared contracts for cross-boundary data types.

All dataclasses, enums, TypedDicts, and NamedTuples that cross subsystem
boundaries MUST be defined here. Internal types are whitelisted in
config/cicd/contracts-whitelist.yaml.

Import pattern:
    from elspeth.contracts import NodeType, TransformResult, Run
"""

# isort: skip_file
# Import order is load-bearing: config imports MUST come last to avoid circular
# import through core.checkpoint -> core.landscape -> contracts.

from elspeth.contracts.enums import (
    BackpressureMode,
    BatchStatus,
    CallStatus,
    CallType,
    Determinism,
    ExportStatus,
    NodeStateStatus,
    NodeType,
    RoutingKind,
    RoutingMode,
    RowOutcome,
    RunMode,
    RunStatus,
    TelemetryGranularity,
    TriggerType,
)
from elspeth.contracts.errors import (
    BatchPendingError,
    ExecutionError,
    RoutingReason,
    TransformReason,
)
from elspeth.contracts.audit import (
    Artifact,
    Batch,
    BatchMember,
    BatchOutput,
    BatchStatusUpdate,
    Call,
    Checkpoint,
    Edge,
    ExportStatusUpdate,
    Node,
    NodeState,
    NodeStateCompleted,
    NodeStateFailed,
    NodeStateOpen,
    NodeStatePending,
    NonCanonicalMetadata,
    RoutingEvent,
    Row,
    RowLineage,
    Run,
    Token,
    TokenOutcome,
    TokenParent,
    TransformErrorRecord,
    ValidationErrorRecord,
)
from elspeth.contracts.identity import TokenInfo
from elspeth.contracts.checkpoint import ResumeCheck, ResumePoint
from elspeth.contracts.types import (
    AggregationName,
    BranchName,
    CoalesceName,
    GateName,
    NodeID,
    SinkName,
)
from elspeth.contracts.results import (
    ArtifactDescriptor,
    FailureInfo,
    GateResult,
    RowResult,
    SourceRow,
    TransformResult,
)
from elspeth.contracts.routing import EdgeInfo, RoutingAction, RoutingSpec
from elspeth.contracts.data import (
    CompatibilityResult,
    PluginSchema,
    SchemaValidationError,
    check_compatibility,
    validate_row,
)
from elspeth.contracts.config import (
    CheckpointSettings,
    ConcurrencySettings,
    DatabaseSettings,
    ElspethSettings,
    ExporterConfig,
    ExporterSettings,
    LandscapeExportSettings,
    LandscapeSettings,
    PayloadStoreSettings,
    RateLimitSettings,
    RetrySettings,
    SinkSettings,
    SourceSettings,
    TelemetrySettings,
    TransformSettings,
    # Runtime protocols
    RuntimeCheckpointProtocol,
    RuntimeConcurrencyProtocol,
    RuntimeRateLimitProtocol,
    RuntimeRetryProtocol,
    RuntimeTelemetryConfig,
    RuntimeTelemetryProtocol,
    # Default registries
    INTERNAL_DEFAULTS,
    POLICY_DEFAULTS,
    # Alignment documentation
    EXEMPT_SETTINGS,
    FIELD_MAPPINGS,
    SETTINGS_TO_RUNTIME,
)
from elspeth.contracts.events import (
    PhaseAction,
    PhaseCompleted,
    PhaseError,
    PhaseStarted,
    PipelinePhase,
    RunCompleted,
    RunCompletionStatus,
)
from elspeth.contracts.engine import RetryPolicy
from elspeth.contracts.payload_store import IntegrityError, PayloadStore
from elspeth.contracts.cli import ExecutionResult, ProgressEvent
from elspeth.contracts.url import (
    SENSITIVE_PARAMS,
    SanitizedDatabaseUrl,
    SanitizedWebhookUrl,
)
from elspeth.contracts.sink import OutputValidationResult

__all__ = [  # Grouped by category for readability
    # audit
    "Artifact",
    # errors
    "BatchPendingError",
    "ExecutionError",
    "RoutingReason",
    "TransformReason",
    "Batch",
    "BatchMember",
    "BatchOutput",
    "BatchStatusUpdate",
    "Call",
    "Checkpoint",
    "Edge",
    "ExportStatusUpdate",
    "Node",
    "NodeState",
    "NodeStateCompleted",
    "NodeStateFailed",
    "NodeStateOpen",
    "NodeStatePending",
    "NonCanonicalMetadata",
    "RoutingEvent",
    "Row",
    "RowLineage",
    "Run",
    "Token",
    "TokenOutcome",
    "TokenParent",
    "TransformErrorRecord",
    "ValidationErrorRecord",
    # config - Settings classes
    "CheckpointSettings",
    "ConcurrencySettings",
    "DatabaseSettings",
    "ElspethSettings",
    "ExporterConfig",
    "ExporterSettings",
    "LandscapeExportSettings",
    "LandscapeSettings",
    "PayloadStoreSettings",
    "RateLimitSettings",
    "RetrySettings",
    "SinkSettings",
    "SourceSettings",
    "TelemetrySettings",
    "TransformSettings",
    # config - Runtime protocols
    "RuntimeCheckpointProtocol",
    "RuntimeConcurrencyProtocol",
    "RuntimeRateLimitProtocol",
    "RuntimeRetryProtocol",
    "RuntimeTelemetryConfig",
    "RuntimeTelemetryProtocol",
    # config - Default registries
    "INTERNAL_DEFAULTS",
    "POLICY_DEFAULTS",
    # config - Alignment documentation
    "EXEMPT_SETTINGS",
    "FIELD_MAPPINGS",
    "SETTINGS_TO_RUNTIME",
    # enums
    "BackpressureMode",
    "BatchStatus",
    "CallStatus",
    "CallType",
    "Determinism",
    "ExportStatus",
    "NodeStateStatus",
    "NodeType",
    "RoutingKind",
    "RoutingMode",
    "RowOutcome",
    "RunMode",
    "RunStatus",
    "TelemetryGranularity",
    "TriggerType",
    # identity
    "TokenInfo",
    # checkpoint
    "ResumeCheck",
    "ResumePoint",
    # types
    "AggregationName",
    "BranchName",
    "CoalesceName",
    "GateName",
    "NodeID",
    "SinkName",
    # results (NOTE: AcceptResult deleted in aggregation structural cleanup)
    "ArtifactDescriptor",
    "FailureInfo",
    "GateResult",
    "RowResult",
    "SourceRow",
    "TransformResult",
    # routing
    "EdgeInfo",
    "RoutingAction",
    "RoutingSpec",
    # data
    "CompatibilityResult",
    "PluginSchema",
    "SchemaValidationError",
    "check_compatibility",
    "validate_row",
    # engine
    "RetryPolicy",
    # payload_store
    "IntegrityError",
    "PayloadStore",
    # events
    "PhaseAction",
    "PhaseCompleted",
    "PhaseError",
    "PhaseStarted",
    "PipelinePhase",
    "RunCompleted",
    "RunCompletionStatus",
    # cli
    "ExecutionResult",
    "ProgressEvent",
    # url
    "SENSITIVE_PARAMS",
    "SanitizedDatabaseUrl",
    "SanitizedWebhookUrl",
    # sink
    "OutputValidationResult",
]
