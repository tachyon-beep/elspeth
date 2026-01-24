# src/elspeth/plugins/base.py
"""Base classes for plugin implementations.

These provide common functionality and ensure proper interface compliance.
Plugins can subclass these for convenience, or implement protocols directly.

Phase 3 Integration:
- Lifecycle hooks (on_start, on_complete) are called by engine
- PluginContext is provided by engine with landscape/tracer/payload_store
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any

from elspeth.contracts import ArtifactDescriptor, Determinism, PluginSchema, SourceRow
from elspeth.plugins.context import PluginContext
from elspeth.plugins.results import (
    GateResult,
    TransformResult,
)


class BaseTransform(ABC):
    """Base class for stateless row transforms.

    Subclass and implement process() to create a transform.

    For batch-aware transforms (used in aggregation nodes):
    - Set is_batch_aware = True
    - process() will receive list[dict] when used in aggregation

    Example:
        class MyTransform(BaseTransform):
            name = "my_transform"
            input_schema = InputSchema
            output_schema = OutputSchema

            def process(self, row: dict, ctx: PluginContext) -> TransformResult:
                return TransformResult.success({**row, "new_field": "value"})
    """

    name: str
    input_schema: type[PluginSchema]
    output_schema: type[PluginSchema]
    node_id: str | None = None  # Set by orchestrator after registration

    # Metadata for Phase 3 audit/reproducibility
    determinism: Determinism = Determinism.DETERMINISTIC
    plugin_version: str = "0.0.0"

    # Batch support - override to True for batch-aware transforms
    # When True, engine may pass list[dict] instead of single dict to process()
    is_batch_aware: bool = False

    # Token creation flag for deaggregation transforms
    # When True AND process() returns success_multi(), the processor creates
    # new token_ids for each output row with parent linkage to input token.
    # When False AND success_multi() is returned, the processor expects
    # passthrough mode (same number of outputs as inputs, preserve token_ids).
    # Default: False (most transforms don't create new tokens)
    creates_tokens: bool = False

    # Error routing configuration (WP-11.99b)
    # Transforms extending TransformDataConfig override this from config.
    # None means: transform doesn't return errors, OR errors are bugs.
    _on_error: str | None = None

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration.

        Args:
            config: Plugin configuration

        Raises:
            ValueError: If schema configuration is invalid or incompatible
        """
        self.config = config
        self._validation_called = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Enforce that subclasses call _validate_self_consistency() in __init__.

        This hook wraps the subclass __init__ to verify validation was called.
        Prevents plugins from bypassing validation by implementing but not calling.

        Only enforces for classes that define their own __init__ (i.e., production plugins).
        Test helpers that don't override __init__ use the default implementation.
        """
        super().__init_subclass__(**kwargs)

        # Only enforce if the class defines its own __init__
        if "__init__" not in cls.__dict__:
            return  # Using parent's __init__, no validation needed

        original_init = cls.__init__

        def wrapped_init(self: Any, *args: Any, **kwargs: Any) -> None:
            original_init(self, *args, **kwargs)
            # __init_subclass__ hook: Verify validation was called (R2 allowlisted)
            if not getattr(self, "_validation_called", False):
                raise RuntimeError(
                    f"{cls.__name__}.__init__ did not call _validate_self_consistency(). Validation is mandatory for audit integrity."
                )

        cls.__init__ = wrapped_init  # type: ignore[method-assign]

    def _validate_self_consistency(self) -> None:
        """Validate plugin's own schemas are self-consistent (PHASE 1).

        Called by subclass __init__ after setting schemas. This is SELF-validation
        only - checking that the plugin's own configuration makes sense.

        Raises:
            ValueError: If schemas are internally inconsistent

        Note:
            This is NOT about compatibility with OTHER plugins. That happens in
            PHASE 2 during ExecutionGraph.from_plugin_instances().

            Examples of self-consistency checks:
            - PassThrough: input_schema must equal output_schema
            - FieldMapper: output fields must be subset of input fields (if mode=strict)
            - Gate: input_schema must equal output_schema (pass-through)

            Default implementation (for plugins with no self-consistency constraints):
            ```python
            def _validate_self_consistency(self) -> None:
                super()._validate_self_consistency()  # Sets _validation_called = True
                # Add additional validation here if needed
            ```

            Subclasses MUST:
            1. Call this method in __init__ (enforced by __init_subclass__ - RuntimeError if not called)
            2. Call super()._validate_self_consistency() if overriding (sets _validation_called)
            3. Override to add custom validation logic (optional)

            The __init_subclass__ hook verifies validation was called after __init__ completes.
        """
        self._validation_called = True  # Default: no additional validation needed

    @abstractmethod
    def process(
        self,
        row: dict[str, Any],
        ctx: PluginContext,
    ) -> TransformResult:
        """Process a single row.

        Args:
            row: Input row matching input_schema
            ctx: Plugin context

        Returns:
            TransformResult with processed row or error
        """
        ...

    def close(self) -> None:  # noqa: B027 - optional override, not abstract
        """Clean up resources after pipeline completion.

        Called once after all rows have been processed. Override for closing
        connections, flushing buffers, or releasing external resources.
        """
        pass

    # === Lifecycle Hooks (Phase 3) ===
    # These are intentionally empty - optional hooks for subclasses to override

    def on_start(self, ctx: PluginContext) -> None:  # noqa: B027 - optional hook
        """Called at the start of each run.

        Override for per-run initialization.
        """
        pass

    def on_complete(self, ctx: PluginContext) -> None:  # noqa: B027 - optional hook
        """Called at the end of each run.

        Override for cleanup.
        """
        pass


class BaseGate(ABC):
    """Base class for gate transforms (routing decisions).

    Subclass and implement evaluate() to create a gate.

    Example:
        class SafetyGate(BaseGate):
            name = "safety"
            input_schema = RowSchema
            output_schema = RowSchema

            def evaluate(self, row: dict, ctx: PluginContext) -> GateResult:
                if self._is_suspicious(row):
                    return GateResult(
                        row=row,
                        action=RoutingAction.route("suspicious"),  # Resolved via routes config
                    )
                return GateResult(row=row, action=RoutingAction.route("normal"))
    """

    name: str
    input_schema: type[PluginSchema]
    output_schema: type[PluginSchema]
    node_id: str | None = None  # Set by orchestrator after registration

    # Metadata for Phase 3 audit/reproducibility
    determinism: Determinism = Determinism.DETERMINISTIC
    plugin_version: str = "0.0.0"

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration.

        Args:
            config: Plugin configuration

        Raises:
            ValueError: If schema configuration is invalid or incompatible
        """
        self.config = config
        self._validation_called = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Enforce that subclasses call _validate_self_consistency() in __init__.

        This hook wraps the subclass __init__ to verify validation was called.
        Prevents plugins from bypassing validation by implementing but not calling.

        Only enforces for classes that define their own __init__ (i.e., production plugins).
        Test helpers that don't override __init__ use the default implementation.
        """
        super().__init_subclass__(**kwargs)

        # Only enforce if the class defines its own __init__
        if "__init__" not in cls.__dict__:
            return  # Using parent's __init__, no validation needed

        original_init = cls.__init__

        def wrapped_init(self: Any, *args: Any, **kwargs: Any) -> None:
            original_init(self, *args, **kwargs)
            # __init_subclass__ hook: Verify validation was called (R2 allowlisted)
            if not getattr(self, "_validation_called", False):
                raise RuntimeError(
                    f"{cls.__name__}.__init__ did not call _validate_self_consistency(). Validation is mandatory for audit integrity."
                )

        cls.__init__ = wrapped_init  # type: ignore[method-assign]

    def _validate_self_consistency(self) -> None:
        """Validate plugin's own schemas are self-consistent (PHASE 1).

        Called by subclass __init__ after setting schemas. This is SELF-validation
        only - checking that the plugin's own configuration makes sense.

        Raises:
            ValueError: If schemas are internally inconsistent

        Note:
            Gates typically have input_schema == output_schema (pass-through).
            Most gates have no additional self-consistency constraints.

            Default implementation (for gates with no self-consistency constraints):
            ```python
            def _validate_self_consistency(self) -> None:
                super()._validate_self_consistency()  # Sets _validation_called = True
                # Add additional validation here if needed
            ```

            Subclasses MUST:
            1. Call this method in __init__ (enforced by __init_subclass__ - RuntimeError if not called)
            2. Call super()._validate_self_consistency() if overriding (sets _validation_called)
            3. Override to add custom validation logic (optional)
        """
        self._validation_called = True  # Default: no additional validation needed

    @abstractmethod
    def evaluate(
        self,
        row: dict[str, Any],
        ctx: PluginContext,
    ) -> GateResult:
        """Evaluate a row and decide routing.

        Args:
            row: Input row
            ctx: Plugin context

        Returns:
            GateResult with routing decision
        """
        ...

    def close(self) -> None:  # noqa: B027 - optional override, not abstract
        """Clean up resources after pipeline completion.

        Called once after all rows have been processed. Override for closing
        connections, flushing buffers, or releasing external resources.
        """
        pass

    # === Lifecycle Hooks (Phase 3) ===

    def on_start(self, ctx: PluginContext) -> None:  # noqa: B027 - optional hook
        """Called at start of run."""
        pass

    def on_complete(self, ctx: PluginContext) -> None:  # noqa: B027 - optional hook
        """Called at end of run."""
        pass


# NOTE: BaseAggregation was DELETED in aggregation structural cleanup.
# Aggregation is now fully structural:
# - Engine buffers rows internally
# - Engine evaluates triggers (WP-06)
# - Engine calls batch-aware Transform.process(rows: list[dict])
# Use is_batch_aware=True on BaseTransform for batch processing.


class BaseSink(ABC):
    """Base class for sink plugins.

    Subclass and implement write(), flush(), close().

    Example:
        class CSVSink(BaseSink):
            name = "csv"
            input_schema = RowSchema
            idempotent = False

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

            def close(self) -> None:
                self._file.close()
    """

    name: str
    input_schema: type[PluginSchema]
    idempotent: bool = False
    node_id: str | None = None  # Set by orchestrator after registration

    # Metadata for Phase 3 audit/reproducibility
    determinism: Determinism = Determinism.IO_WRITE
    plugin_version: str = "0.0.0"

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration.

        Args:
            config: Plugin configuration

        Raises:
            ValueError: If schema configuration is invalid or incompatible
        """
        self.config = config
        self._validation_called = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Enforce that subclasses call _validate_self_consistency() in __init__.

        This hook wraps the subclass __init__ to verify validation was called.
        Prevents plugins from bypassing validation by implementing but not calling.

        Only enforces for classes that define their own __init__ (i.e., production plugins).
        Test helpers that don't override __init__ use the default implementation.
        """
        super().__init_subclass__(**kwargs)

        # Only enforce if the class defines its own __init__
        if "__init__" not in cls.__dict__:
            return  # Using parent's __init__, no validation needed

        original_init = cls.__init__

        def wrapped_init(self: Any, *args: Any, **kwargs: Any) -> None:
            original_init(self, *args, **kwargs)
            # __init_subclass__ hook: Verify validation was called (R2 allowlisted)
            if not getattr(self, "_validation_called", False):
                raise RuntimeError(
                    f"{cls.__name__}.__init__ did not call _validate_self_consistency(). Validation is mandatory for audit integrity."
                )

        cls.__init__ = wrapped_init  # type: ignore[method-assign]

    def _validate_self_consistency(self) -> None:
        """Validate plugin's own schemas are self-consistent (PHASE 1).

        Called by subclass __init__ after setting schemas. This is SELF-validation
        only - checking that the plugin's own configuration makes sense.

        Raises:
            ValueError: If schemas are internally inconsistent

        Note:
            Sinks typically have only input_schema with no self-consistency constraints.

            Default implementation (for sinks with no self-consistency constraints):
            ```python
            def _validate_self_consistency(self) -> None:
                super()._validate_self_consistency()  # Sets _validation_called = True
                # Add additional validation here if needed
            ```

            Subclasses MUST:
            1. Call this method in __init__ (enforced by __init_subclass__ - RuntimeError if not called)
            2. Call super()._validate_self_consistency() if overriding (sets _validation_called)
            3. Override to add custom validation logic (optional)
        """
        self._validation_called = True  # Default: no additional validation needed

    @abstractmethod
    def write(
        self,
        rows: list[dict[str, Any]],
        ctx: PluginContext,
    ) -> ArtifactDescriptor:
        """Write a batch of rows to the sink.

        Args:
            rows: List of row dicts to write
            ctx: Plugin context

        Returns:
            ArtifactDescriptor with content_hash and size_bytes
        """
        ...

    @abstractmethod
    def flush(self) -> None:
        """Flush buffered data."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close and release resources."""
        ...

    # === Lifecycle Hooks (Phase 3) ===

    def on_start(self, ctx: PluginContext) -> None:  # noqa: B027 - optional hook
        """Called at start of run."""
        pass

    def on_complete(self, ctx: PluginContext) -> None:  # noqa: B027 - optional hook
        """Called at end of run (before close)."""
        pass


class BaseSource(ABC):
    """Base class for source plugins.

    Subclass and implement load() and close().

    Example:
        class CSVSource(BaseSource):
            name = "csv"
            output_schema = RowSchema

            def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
                with open(self.config["path"]) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        yield SourceRow.valid(row)

            def close(self) -> None:
                pass  # File already closed by context manager
    """

    name: str
    output_schema: type[PluginSchema]
    node_id: str | None = None  # Set by orchestrator after registration

    # Metadata for Phase 3 audit/reproducibility
    determinism: Determinism = Determinism.IO_READ
    plugin_version: str = "0.0.0"

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize with configuration.

        Args:
            config: Plugin configuration

        Raises:
            ValueError: If schema configuration is invalid or incompatible
        """
        self.config = config
        self._validation_called = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Enforce that subclasses call _validate_self_consistency() in __init__.

        This hook wraps the subclass __init__ to verify validation was called.
        Prevents plugins from bypassing validation by implementing but not calling.

        Only enforces for classes that define their own __init__ (i.e., production plugins).
        Test helpers that don't override __init__ use the default implementation.
        """
        super().__init_subclass__(**kwargs)

        # Only enforce if the class defines its own __init__
        if "__init__" not in cls.__dict__:
            return  # Using parent's __init__, no validation needed

        original_init = cls.__init__

        def wrapped_init(self: Any, *args: Any, **kwargs: Any) -> None:
            original_init(self, *args, **kwargs)
            # __init_subclass__ hook: Verify validation was called (R2 allowlisted)
            if not getattr(self, "_validation_called", False):
                raise RuntimeError(
                    f"{cls.__name__}.__init__ did not call _validate_self_consistency(). Validation is mandatory for audit integrity."
                )

        cls.__init__ = wrapped_init  # type: ignore[method-assign]

    def _validate_self_consistency(self) -> None:
        """Validate plugin's own schemas are self-consistent (PHASE 1).

        Called by subclass __init__ after setting schemas. This is SELF-validation
        only - checking that the plugin's own configuration makes sense.

        Raises:
            ValueError: If schemas are internally inconsistent

        Note:
            Sources typically have only output_schema with no self-consistency constraints.

            Default implementation (for sources with no self-consistency constraints):
            ```python
            def _validate_self_consistency(self) -> None:
                super()._validate_self_consistency()  # Sets _validation_called = True
                # Add additional validation here if needed
            ```

            Subclasses MUST:
            1. Call this method in __init__ (enforced by __init_subclass__ - RuntimeError if not called)
            2. Call super()._validate_self_consistency() if overriding (sets _validation_called)
            3. Override to add custom validation logic (optional)
        """
        self._validation_called = True  # Default: no additional validation needed

    @abstractmethod
    def load(self, ctx: PluginContext) -> Iterator[SourceRow]:
        """Load and yield rows from the source.

        Args:
            ctx: Plugin context

        Yields:
            SourceRow for each row - either SourceRow.valid() for rows that
            passed validation, or SourceRow.quarantined() for invalid rows.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Clean up resources."""
        ...

    # === Lifecycle Hooks (Phase 3) ===

    def on_start(self, ctx: PluginContext) -> None:  # noqa: B027 - optional hook
        """Called before load()."""
        pass

    def on_complete(self, ctx: PluginContext) -> None:  # noqa: B027 - optional hook
        """Called after load() completes (before close)."""
        pass
