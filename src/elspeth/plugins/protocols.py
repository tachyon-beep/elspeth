# src/elspeth/plugins/protocols.py
"""Plugin protocols defining the contracts for each plugin type.

These protocols define what methods plugins must implement.
They're used for type checking, not runtime enforcement (that's pluggy's job).

Plugin Types:
- Source: Loads data into the system (one per run)
- Transform: Processes rows (stateless)
- Gate: Routes rows to destinations (stateless)
- Aggregation: Accumulates rows, flushes batches (stateful)
- Coalesce: Merges parallel paths (stateful)
- Sink: Outputs data (one or more per run)
"""

from collections.abc import Iterator
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from elspeth.contracts import Determinism

if TYPE_CHECKING:
    from elspeth.contracts import ArtifactDescriptor, PluginSchema, SourceRow
    from elspeth.contracts.plugin_context import PluginContext
    from elspeth.contracts.schema_contract import PipelineRow
    from elspeth.contracts.sink import OutputValidationResult
    from elspeth.plugins.results import GateResult, TransformResult


@runtime_checkable
class PluginProtocol(Protocol):
    """Base protocol for all plugins.

    Defines the common metadata attributes that all plugins must have.
    Used by PluginManager.from_plugin() for type-safe metadata extraction.
    """

    name: str
    plugin_version: str
    determinism: Determinism


@runtime_checkable
class SourceProtocol(Protocol):
    """Protocol for source plugins.

    Sources load data into the system. There is exactly one source per run.

    Lifecycle:
    1. __init__(config) - Plugin instantiation
    2. on_start(ctx) - Called before loading (optional)
    3. load(ctx) - Yields rows
    4. close() - Cleanup

    Example:
        class CSVSource:
            name = "csv"
            output_schema = RowSchema

            def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
                with open(self.path) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        yield SourceRow.valid(row)
    """

    name: str
    output_schema: type["PluginSchema"]
    node_id: str | None  # Set by orchestrator after registration
    config: dict[str, Any]  # Configuration dict stored by all plugins

    # Metadata for Phase 3 audit/reproducibility
    determinism: Determinism
    plugin_version: str

    # Sink name for quarantined rows, or "discard" to drop invalid rows
    # All sources must set this - config-based sources get it from SourceDataConfig
    _on_validation_failure: str

    # Success routing: sink name for rows that pass source validation
    # All sources must set this - config-based sources get it from SourceDataConfig
    on_success: str

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration."""
        ...

    def load(self, ctx: "PluginContext") -> Iterator["SourceRow"]:
        """Load and yield rows from the source.

        Args:
            ctx: Plugin context with run metadata

        Yields:
            SourceRow for each row - either SourceRow.valid() for valid rows
            or SourceRow.quarantined() for invalid rows.
        """
        ...

    def close(self) -> None:
        """Clean up resources.

        Called after all rows are loaded or on error.
        """
        ...

    # === Optional Lifecycle Hooks ===

    def on_start(self, ctx: "PluginContext") -> None:
        """Called before load(). Override for setup."""
        ...

    def on_complete(self, ctx: "PluginContext") -> None:
        """Called after load() completes. Override for cleanup before close()."""
        ...

    # === Audit Trail Metadata ===

    def get_field_resolution(self) -> tuple[dict[str, str], str | None] | None:
        """Return field resolution mapping computed during load().

        Sources that perform field normalization should override this to return
        the mapping from original header names to final field names.

        Returns:
            Tuple of (resolution_mapping, normalization_version) or None if no
            normalization occurred.
        """
        ...

    # === Schema Contract Support ===

    def get_schema_contract(self) -> Any:
        """Return schema contract for this source.

        Sources with schema validation should override this to return their
        SchemaContract. For OBSERVED/FLEXIBLE modes, the contract is typically
        locked after the first row is processed (type inference happens).

        Returns:
            SchemaContract if available, None otherwise. Using Any return type
            to avoid circular import with contracts module in Protocol definition.
        """
        ...


@runtime_checkable
class TransformProtocol(Protocol):
    """Protocol for stateless single-row transforms.

    Transforms process individual rows and emit results.

    For batch-aware transforms (is_batch_aware=True), use BatchTransformProtocol instead.
    The engine uses is_batch_aware to decide whether to buffer rows and call the batch protocol.

    Lifecycle:
        - __init__(config): Called once at pipeline construction
        - process(row, ctx): Called for each row
        - close(): Called at pipeline completion for cleanup

    Error Routing (WP-11.99b):
        Transforms that can return TransformResult.error() must set _on_error
        to specify where errored rows go. If _on_error is None and the transform
        returns an error, the executor raises RuntimeError.

    Example:
        class EnrichTransform:
            name = "enrich"
            input_schema = InputSchema
            output_schema = OutputSchema
            is_batch_aware = False

            def process(self, row: PipelineRow, ctx: PluginContext) -> TransformResult:
                enriched = {**row.to_dict(), "timestamp": datetime.now().isoformat()}
                return TransformResult.success(
                    enriched,
                    success_reason={"action": "enriched", "fields_added": ["timestamp"]},
                )
    """

    name: str
    input_schema: type["PluginSchema"]
    output_schema: type["PluginSchema"]
    node_id: str | None  # Set by orchestrator after registration
    config: dict[str, Any]  # Configuration dict stored by all plugins

    # Metadata for Phase 3 audit/reproducibility
    determinism: Determinism
    plugin_version: str

    # Batch support flag (must be False for TransformProtocol)
    # When True, transform must implement BatchTransformProtocol instead
    is_batch_aware: bool

    # Token creation flag for deaggregation
    # When True, process() may return TransformResult.success_multi(rows)
    # and new tokens will be created for each output row.
    # When False, success_multi() is only valid in passthrough aggregation mode.
    creates_tokens: bool

    # Schema evolution flag (P1-2026-02-05)
    # When True, transform adds fields during execution and evolved contract
    # should be recorded to audit trail (input fields + added fields).
    # When False (default), transform does not add fields to schema.
    transforms_adds_fields: bool

    # Error routing configuration (WP-11.99b)
    # Transforms extending TransformDataConfig set this from config.
    # None means: transform doesn't return errors, OR errors are bugs.
    @property
    def on_error(self) -> str | None: ...

    # Success routing configuration
    # Terminal transforms (last in chain) set this to the output sink name.
    # None means: non-terminal (more transforms follow in the pipeline).
    @property
    def on_success(self) -> str | None: ...

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration."""
        ...

    def process(
        self,
        row: "PipelineRow",
        ctx: "PluginContext",
    ) -> "TransformResult":
        """Process a single row.

        Args:
            row: Input row as PipelineRow (immutable, supports dual-name access)
            ctx: Plugin context

        Returns:
            TransformResult with processed row dict or error
        """
        ...

    def close(self) -> None:
        """Clean up resources after pipeline completion.

        Called once after all rows have been processed. Use for closing
        connections, flushing buffers, or releasing external resources.
        """
        ...

    # === Optional Lifecycle Hooks ===

    def on_start(self, ctx: "PluginContext") -> None:
        """Called at start of run."""
        ...

    def on_complete(self, ctx: "PluginContext") -> None:
        """Called at end of run."""
        ...


@runtime_checkable
class BatchTransformProtocol(Protocol):
    """Protocol for batch-aware transforms.

    Batch transforms receive lists of rows and emit results. Used in aggregation
    nodes where the engine buffers rows until trigger fires.

    The engine passes list[PipelineRow] - each row is guaranteed to be a PipelineRow
    instance with its schema contract. Transforms should use row.to_dict() to get
    mutable dicts when constructing output.

    Lifecycle:
        - __init__(config): Called once at pipeline construction
        - process(rows, ctx): Called when trigger fires with buffered rows
        - close(): Called at pipeline completion for cleanup

    Error Routing (WP-11.99b):
        Batch transforms that can return TransformResult.error() must set _on_error
        to specify where errored batches go.

    Example:
        class BatchStats:
            name = "batch_stats"
            input_schema = InputSchema
            output_schema = OutputSchema
            is_batch_aware = True

            def process(
                self,
                rows: list[PipelineRow],
                ctx: PluginContext,
            ) -> TransformResult:
                total = sum(row["amount"] for row in rows)
                return TransformResult.success(
                    {"count": len(rows), "total": total},
                    success_reason={"action": "aggregated"},
                )
    """

    name: str
    input_schema: type["PluginSchema"]
    output_schema: type["PluginSchema"]
    node_id: str | None  # Set by orchestrator after registration
    config: dict[str, Any]  # Configuration dict stored by all plugins

    # Metadata for Phase 3 audit/reproducibility
    determinism: Determinism
    plugin_version: str

    # Batch support flag (must be True for BatchTransformProtocol)
    is_batch_aware: bool

    # Token creation flag for deaggregation
    # When True, process() may return TransformResult.success_multi(rows)
    # and new tokens will be created for each output row.
    creates_tokens: bool

    # Error routing configuration (WP-11.99b)
    @property
    def on_error(self) -> str | None: ...

    # Success routing configuration
    @property
    def on_success(self) -> str | None: ...

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration."""
        ...

    def process(
        self,
        rows: list["PipelineRow"],
        ctx: "PluginContext",
    ) -> "TransformResult":
        """Process a batch of rows.

        Args:
            rows: List of input rows as PipelineRow instances
            ctx: Plugin context

        Returns:
            TransformResult with aggregated result or multiple output rows
        """
        ...

    def close(self) -> None:
        """Clean up resources after pipeline completion."""
        ...

    # === Optional Lifecycle Hooks ===

    def on_start(self, ctx: "PluginContext") -> None:
        """Called at start of run."""
        ...

    def on_complete(self, ctx: "PluginContext") -> None:
        """Called at end of run."""
        ...


@runtime_checkable
class GateProtocol(Protocol):
    """Protocol for gate transforms (routing decisions).

    Gates evaluate rows and decide routing. They can:
    - Continue to next transform
    - Route to a named sink
    - Fork to multiple parallel paths

    Lifecycle:
        - __init__(config): Called once at pipeline construction
        - evaluate(row, ctx): Called for each row
        - close(): Called at pipeline completion for cleanup

    Example:
        class SafetyGate:
            name = "safety"
            input_schema = InputSchema
            output_schema = OutputSchema

            def __init__(self, config: dict) -> None:
                # Routes come from GateSettings - required for any gate that routes
                self.routes = config["routes"]  # Crash if missing - config error
                self.fork_to = config.get("fork_to")  # None is valid (most gates don't fork)
                self.node_id = None

            def evaluate(self, row: PipelineRow, ctx: PluginContext) -> GateResult:
                # Direct field access - schema guarantees field exists
                if row["suspicious"]:
                    return GateResult(
                        row=row.to_dict(),
                        action=RoutingAction.route("review"),  # Resolved via routes config
                    )
                return GateResult(row=row.to_dict(), action=RoutingAction.route("normal"))
    """

    name: str
    input_schema: type["PluginSchema"]
    output_schema: type["PluginSchema"]
    node_id: str | None  # Set by orchestrator after registration
    config: dict[str, Any]  # Configuration dict stored by all plugins

    # Routing configuration (set from GateSettings during instantiation)
    routes: dict[str, str]  # Maps route names to destinations
    fork_to: list[str] | None  # Branch names for fork operations

    # Metadata for Phase 3 audit/reproducibility
    determinism: Determinism
    plugin_version: str

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration."""
        ...

    def evaluate(
        self,
        row: "PipelineRow",
        ctx: "PluginContext",
    ) -> "GateResult":
        """Evaluate a row and decide routing.

        Args:
            row: Input row as PipelineRow (immutable, supports dual-name access)
            ctx: Plugin context

        Returns:
            GateResult with (possibly modified) row dict and routing action
        """
        ...

    def close(self) -> None:
        """Clean up resources after pipeline completion.

        Called once after all rows have been processed. Use for closing
        connections, flushing buffers, or releasing external resources.
        """
        ...

    # === Optional Lifecycle Hooks ===

    def on_start(self, ctx: "PluginContext") -> None:
        """Called at start of run."""
        ...

    def on_complete(self, ctx: "PluginContext") -> None:
        """Called at end of run."""
        ...


class CoalescePolicy(Enum):
    """How coalesce handles partial arrivals."""

    REQUIRE_ALL = "require_all"  # Wait for all branches; any failure fails
    QUORUM = "quorum"  # Merge if >= n branches succeed
    BEST_EFFORT = "best_effort"  # Merge whatever arrives by timeout
    FIRST = "first"  # Take first arrival, don't wait for others


# NOTE: AggregationProtocol was DELETED in aggregation structural cleanup.
# Aggregation is now fully structural:
# - Engine buffers rows internally
# - Engine evaluates triggers (WP-06)
# - Engine calls batch-aware Transform.process(rows: list[dict])
# Use is_batch_aware=True on BaseTransform for batch processing.


@runtime_checkable
class CoalesceProtocol(Protocol):
    """Protocol for coalesce transforms (merge parallel paths).

    Coalesce merges results from parallel branches back into a single path.

    Configuration:
    - policy: How to handle partial arrivals
    - quorum_threshold: Minimum branches for QUORUM policy (None otherwise)
    - inputs: Which branches to expect
    - key: How to correlate branch outputs (Phase 3 engine concern)

    Example:
        class SimpleCoalesce:
            name = "merge"
            policy = CoalescePolicy.REQUIRE_ALL
            quorum_threshold = None  # Only used for QUORUM policy

            def merge(self, branch_outputs, ctx) -> dict:
                merged = {}
                for branch_name, output in branch_outputs.items():
                    merged.update(output)
                return merged

        class QuorumCoalesce:
            name = "quorum_merge"
            policy = CoalescePolicy.QUORUM
            quorum_threshold = 2  # Proceed if >= 2 branches arrive
    """

    name: str
    policy: CoalescePolicy
    quorum_threshold: int | None  # Required if policy == QUORUM
    expected_branches: list[str]
    output_schema: type["PluginSchema"]
    node_id: str | None  # Set by orchestrator after registration
    config: dict[str, Any]  # Configuration dict stored by all plugins

    # Metadata for Phase 3 audit/reproducibility
    determinism: Determinism
    plugin_version: str

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration."""
        ...

    def merge(
        self,
        branch_outputs: dict[str, dict[str, Any]],
        ctx: "PluginContext",
    ) -> dict[str, Any]:
        """Merge outputs from multiple branches.

        Args:
            branch_outputs: Map of branch_name -> output_row
            ctx: Plugin context

        Returns:
            Merged output row
        """
        ...

    # === Optional Lifecycle Hooks ===

    def on_start(self, ctx: "PluginContext") -> None:
        """Called at start of run."""
        ...

    def on_complete(self, ctx: "PluginContext") -> None:
        """Called at end of run."""
        ...


@runtime_checkable
class SinkProtocol(Protocol):
    """Protocol for sink plugins.

    Sinks output data to external destinations.
    There can be multiple sinks per run.

    Idempotency:
    - Sinks receive idempotency keys: {run_id}:{row_id}:{sink_name}
    - Sinks that cannot guarantee idempotency should set idempotent=False

    Example:
        class CSVSink:
            name = "csv"
            input_schema = RowSchema
            idempotent = False  # Appends are not idempotent

            def write(self, rows: list[dict], ctx: PluginContext) -> ArtifactDescriptor:
                for row in rows:
                    self._writer.writerow(row)
                return ArtifactDescriptor.for_file(
                    path=self._path,
                    content_hash=self._compute_hash(),
                    size_bytes=self._file.tell(),
                )

            def flush(self) -> None:
                self._file.flush()
    """

    name: str
    input_schema: type["PluginSchema"]
    idempotent: bool  # Can this sink handle retries safely?
    node_id: str | None  # Set by orchestrator after registration
    config: dict[str, Any]  # Configuration dict stored by all plugins

    # Metadata for Phase 3 audit/reproducibility
    determinism: Determinism
    plugin_version: str

    # Resume capability (Phase 5 - Checkpoint/Resume)
    supports_resume: bool  # Can this sink append to existing output on resume?

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration."""
        ...

    def write(
        self,
        rows: list[dict[str, Any]],
        ctx: "PluginContext",
    ) -> "ArtifactDescriptor":
        """Write a batch of rows to the sink.

        Args:
            rows: List of row dicts to write
            ctx: Plugin context

        Returns:
            ArtifactDescriptor with content_hash and size_bytes (REQUIRED for audit)
        """
        ...

    def flush(self) -> None:
        """Ensure all buffered writes are durable.

        MUST guarantee that when this method returns:
        - All data passed to write() is persisted
        - Data survives process crash
        - Data survives power loss (for file/block storage)

        This method MUST block until durability is guaranteed.

        For file-based sinks: Call file.flush() + os.fsync(file.fileno())
        For database sinks: Call connection.commit()
        For async sinks: Await flush completion

        This is called by the orchestrator BEFORE creating checkpoints.
        If this method returns successfully, the checkpoint system assumes
        all data is durable and will NOT replay these writes on resume.
        """
        ...

    def close(self) -> None:
        """Close the sink and release resources.

        Called at end of run or on error.
        """
        ...

    # === Optional Lifecycle Hooks ===

    def on_start(self, ctx: "PluginContext") -> None:
        """Called at start of run."""
        ...

    def on_complete(self, ctx: "PluginContext") -> None:
        """Called at end of run (before close)."""
        ...

    def configure_for_resume(self) -> None:
        """Configure sink for resume mode (append instead of truncate).

        Called by engine when resuming a run. Sinks that support resume
        (supports_resume=True) MUST implement this to switch to append mode.

        Sinks that don't support resume (supports_resume=False) will never
        have this called - the CLI will reject resume before execution.

        Raises:
            NotImplementedError: If sink cannot be resumed despite claiming support.
        """
        ...

    def validate_output_target(self) -> "OutputValidationResult":
        """Validate existing output target matches configured schema.

        Called by engine/CLI before write operations in append/resume mode.
        Returns valid=True by default (dynamic schema or no validation needed).

        Sinks that support resume SHOULD override to validate that existing
        output target (file/table) schema matches configured schema.

        Returns:
            OutputValidationResult indicating compatibility.
        """
        ...

    def set_resume_field_resolution(self, resolution_mapping: dict[str, str]) -> None:
        """Set field resolution mapping for resume validation.

        Called by CLI during `elspeth resume` to provide the source field resolution
        mapping BEFORE calling validate_output_target(). This allows sinks using
        restore_source_headers=True to correctly compare expected display names
        against existing file headers.

        Args:
            resolution_mapping: Dict mapping original header name -> normalized field name.
                This is the same format returned by Landscape.get_source_field_resolution().

        Note:
            Default is a no-op. Only sinks that support restore_source_headers need
            to override this (CSVSink, JSONSink).
        """
        ...
