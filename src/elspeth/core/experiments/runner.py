"""Simplified experiment runner ported from legacy implementation."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Type

import pandas as pd

from elspeth.core.base.protocols import LLMClientProtocol, LLMMiddleware, LLMRequest, ResultSink
from elspeth.core.base.schema import DataFrameSchema, SchemaViolation
from elspeth.core.base.types import DeterminismLevel, SecurityLevel
from elspeth.core.controls import CostTracker, RateLimiter
from elspeth.core.experiments.plugin_registry import create_early_stop_plugin
from elspeth.core.experiments.validation import validate_plugin_schemas
from elspeth.core.pipeline.artifact_pipeline import ArtifactPipeline, SinkBinding
from elspeth.core.pipeline.processing import prepare_prompt_context
from elspeth.core.prompts import PromptEngine, PromptRenderingError, PromptTemplate, PromptValidationError
from elspeth.core.security import ensure_security_level, resolve_determinism_level, resolve_security_level
from elspeth.core.utils.path_guard import check_and_prepare_dir, ensure_destination_is_not_symlink, resolve_under_base
from elspeth.plugins.orchestrators.experiment.protocols import (
    AggregationExperimentPlugin,
    EarlyStopPlugin,
    RowExperimentPlugin,
    ValidationPlugin,
)

logger = logging.getLogger(__name__)


@dataclass
class CheckpointManager:
    r"""Manages checkpoint loading, tracking, and persistence with path traversal protection.

    Provides atomic checkpoint operations with exactly-once semantics for
    row processing tracking. Thread-safe for parallel execution. Protects
    against path traversal attacks by constraining checkpoint files to an
    allowed base directory.

    File Format:
        Plain text, one row ID per line with newline terminator.
        Example: "row1\\nrow2\\nrow3\\n"

    Args:
        path: Path to checkpoint file (plain text, one ID per line)
        id_field: Name of DataFrame column containing unique row identifiers
        allowed_base_path: Directory path to constrain checkpoint file location.
            If set, enables path validation to prevent traversal attacks.
            If None, requires _bypass_validation_for_trusted_internal_paths=True
        _bypass_validation_for_trusted_internal_paths: DANGEROUS bypass for internal code.
            Set to True ONLY for hardcoded, trusted paths (tests, internal code).
            NEVER use for user-provided configurations.
            If False (default), allowed_base_path is required (defense in depth).

    Security (Defense in Depth):
        - Layer 1: _init_checkpoint() provides safe defaults for user configs
        - Layer 2: CheckpointManager enforces validation requirements
        - Path traversal protection via resolve_under_base()
        - Symlink attack prevention via path_guard utilities
        - Thread-safe file operations with lock
        - FAIL-CLOSED: allowed_base_path required unless explicit bypass
        - Explicit bypass parameter prevents accidental security bypasses

    Examples:
        Secure usage (user-controlled configuration - REQUIRED):
        >>> # Configuration from untrusted sources (user input, external APIs, YAML files)
        >>> # MUST provide allowed_base_path to prevent path traversal attacks
        >>> checkpoint_mgr = CheckpointManager(
        ...     path=Path("checkpoints/experiment_001.txt"),
        ...     id_field="row_id",
        ...     allowed_base_path=Path("/safe/checkpoints/directory"),
        ... )
        >>> # Path traversal attempts will raise ValueError:
        >>> # path=Path("../../../etc/passwd") -> ValueError

        Trusted usage (internal hardcoded paths - ONLY for tests/internal code):
        >>> # ONLY for hardcoded, trusted paths (pytest fixtures, internal code)
        >>> # Requires EXPLICIT bypass parameter to prevent accidents
        >>> checkpoint_mgr = CheckpointManager(
        ...     path=Path("internal_checkpoints/run.txt"),
        ...     id_field="id",
        ...     allowed_base_path=None,
        ...     _bypass_validation_for_trusted_internal_paths=True,  # EXPLICIT bypass
        ... )
        >>> # WARNING: Bypass disables ALL path validation. Use ONLY for hardcoded paths.
        >>> # NEVER use bypass for user-provided paths or configurations!

    Raises:
        ValueError: If path escapes allowed_base_path or contains symlinks
        ValueError: If allowed_base_path cannot be resolved
        ValueError: If allowed_base_path is None without explicit bypass (DEFENSE IN DEPTH)
    """

    path: Path
    id_field: str
    allowed_base_path: Path | None = None
    _bypass_validation_for_trusted_internal_paths: bool = False
    _processed_ids: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _safe_path: Path = field(init=False)  # Cached validated path

    def __post_init__(self) -> None:
        """Validate checkpoint path and load existing checkpoint file.

        Security Model (DEFENSE IN DEPTH):
            - Layer 1: _init_checkpoint() provides safe defaults for user configs
            - Layer 2: THIS METHOD enforces validation requirements for ALL callers
            - If allowed_base_path is set: Validates path against base, caches validated path
            - If allowed_base_path is None: Requires explicit bypass parameter

        Raises:
            ValueError: If allowed_base_path is None without explicit bypass
            ValueError: If allowed_base_path is set and path escapes base or contains symlinks
            ValueError: If allowed_base_path cannot be resolved
        """
        # DEFENSE IN DEPTH: Enforce validation unless explicitly bypassed
        if self.allowed_base_path is None and not self._bypass_validation_for_trusted_internal_paths:
            raise ValueError(
                "CheckpointManager requires allowed_base_path for security (DEFENSE IN DEPTH). "
                "Path validation protects against traversal attacks. "
                "If this is a hardcoded, trusted internal path (tests/fixtures), "
                "set _bypass_validation_for_trusted_internal_paths=True. "
                "NEVER bypass validation for user-provided configurations."
            )

        if self.allowed_base_path is not None:
            # Untrusted path: Validate against allowed base directory
            try:
                resolved_base = self.allowed_base_path.resolve()
            except (OSError, ValueError) as e:
                raise ValueError(f"Invalid allowed_base_path: {e}") from e

            # Validate path doesn't escape base and cache validated result
            try:
                self._safe_path = resolve_under_base(self.path, resolved_base)
                ensure_destination_is_not_symlink(self._safe_path)
            except ValueError as e:
                raise ValueError(f"Checkpoint path validation failed: {e}") from e
        else:
            # Trusted path: Use directly without validation
            # WARNING: This disables ALL path validation - only for trusted sources!
            logger.warning(
                "CheckpointManager initialized WITHOUT path validation (allowed_base_path=None). "
                "Path: %s. This should ONLY occur for hardcoded trusted paths, never user config!",
                self.path
            )
            self._safe_path = self.path

        # Prepare checkpoint directory once during initialization (fail-fast)
        # This prevents lock contention during concurrent checkpoint writes
        check_and_prepare_dir(self._safe_path)

        # Load existing checkpoint if file exists
        if self._safe_path.exists():
            self._load_checkpoint()

    def _load_checkpoint(self) -> None:
        """Load processed row IDs from checkpoint file (plain text format).

        Uses cached validated path from __post_init__. No repeated security checks needed.
        """
        try:
            with self._safe_path.open("r", encoding="utf-8") as f:
                for line in f:
                    row_id = line.strip()
                    if row_id:
                        self._processed_ids.add(row_id)
        except OSError as e:
            logger.warning(f"Failed to load checkpoint from {self._safe_path}: {e}")

    def is_processed(self, row_id: str) -> bool:
        """Check if a row has already been processed."""
        return row_id in self._processed_ids

    def mark_processed(self, row_id: str) -> None:
        """Mark a row as processed and persist to checkpoint file."""
        if row_id not in self._processed_ids:
            self._processed_ids.add(row_id)
            self._append_checkpoint(row_id)

    def _append_checkpoint(self, row_id: str) -> None:
        """Append a single checkpoint entry to file (plain text format).

        Thread-safe: Uses lock to serialize appends during parallel execution.
        Uses cached validated path from __post_init__. Directory already prepared during init.

        Raises:
            OSError: If file write fails
        """
        with self._lock:
            try:
                # Append checkpoint entry to validated path
                with self._safe_path.open("a", encoding="utf-8") as f:
                    f.write(f"{row_id}\n")
            except OSError as e:
                logger.error(f"Failed to write checkpoint to {self._safe_path}: {e}")
                raise


@dataclass
class ExperimentContext:
    """Compiled experiment configuration ready for execution."""

    engine: PromptEngine
    system_template: PromptTemplate
    user_template: PromptTemplate
    criteria_templates: dict[str, PromptTemplate]
    checkpoint_manager: CheckpointManager | None
    row_plugins: list[RowExperimentPlugin]


@dataclass
class RowBatch:
    """Collection of rows prepared for processing."""

    rows: list[tuple[int, pd.Series, dict[str, Any], str | None]]

    @property
    def count(self) -> int:
        """Number of rows in batch."""
        return len(self.rows)


@dataclass
class ProcessingResult:
    """Results from row processing execution."""

    records: list[dict[str, Any]]
    failures: list[dict[str, Any]]


@dataclass
class ResultHandlers:
    """Callback handlers for row processing results."""

    on_success: Callable[[int, dict[str, Any], str | None], None]
    on_failure: Callable[[dict[str, Any]], None]


@dataclass
class ExecutionMetadata:
    """Metadata about experiment execution.

    Row Counts:
        processed_rows: Number of rows successfully processed in this run (len(results))
        total_rows: Total rows in input DataFrame (len(df))

    With checkpointing, processed_rows < total_rows indicates previously completed rows were skipped.
    With early stop, processed_rows < total_rows indicates remaining rows were not attempted.
    """

    processed_rows: int
    total_rows: int
    retry_summary: dict[str, int] | None = None
    cost_summary: dict[str, Any] | None = None
    failures: list[dict[str, Any]] | None = None
    aggregates: dict[str, Any] | None = None
    security_level: SecurityLevel | None = None
    determinism_level: DeterminismLevel | None = None
    early_stop: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        from dataclasses import asdict

        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ExperimentRunner:
    """Run an experiment over a DataFrame and dispatch to sinks."""

    llm_client: LLMClientProtocol
    sinks: list[ResultSink]
    prompt_system: str
    prompt_template: str
    prompt_fields: list[str] | None = None
    criteria: list[dict[str, Any]] | None = None
    row_plugins: list[RowExperimentPlugin] | None = None
    aggregator_plugins: list[AggregationExperimentPlugin] | None = None
    validation_plugins: list[ValidationPlugin] | None = None
    rate_limiter: RateLimiter | None = None
    cost_tracker: CostTracker | None = None
    experiment_name: str | None = None
    retry_config: dict[str, Any] | None = None
    checkpoint_config: dict[str, Any] | None = None
    _checkpoint_ids: set[str] | None = None
    prompt_defaults: dict[str, Any] | None = None
    prompt_engine: PromptEngine | None = None
    _compiled_system_prompt: PromptTemplate | None = None
    _compiled_user_prompt: PromptTemplate | None = None
    _compiled_criteria_prompts: dict[str, PromptTemplate] | None = None
    llm_middlewares: list[LLMMiddleware] | None = None
    concurrency_config: dict[str, Any] | None = None
    security_level: SecurityLevel | None = None
    _active_security_level: SecurityLevel | None = None
    determinism_level: DeterminismLevel | None = None
    _active_determinism_level: DeterminismLevel | None = None
    early_stop_plugins: list[EarlyStopPlugin] | None = None
    early_stop_config: dict[str, Any] | None = None
    _active_early_stop_plugins: list[EarlyStopPlugin] | None = None
    _early_stop_event: threading.Event | None = None
    _early_stop_lock: threading.Lock | None = None
    _early_stop_reason: dict[str, Any] | None = None
    on_schema_violation: str = "abort"  # "abort" | "route" | "skip"
    malformed_data_sink: ResultSink | None = None
    _malformed_rows: list[SchemaViolation] | None = None

    # ============================================================================
    # Result Processing & Metadata Helpers
    # ============================================================================

    def _calculate_retry_summary(self, results: ProcessingResult) -> dict[str, int] | None:
        """Calculate retry statistics from processing results.

        Returns retry summary dict if any retries occurred, None otherwise.
        """
        retry_summary: dict[str, int] = {
            "total_requests": len(results.records) + len(results.failures),
            "total_retries": 0,
            "exhausted": len(results.failures),
        }

        retry_present = False

        # Count retries in successful results
        for record in results.records:
            info = record.get("retry")
            if info:
                retry_present = True
                attempts = int(info.get("attempts", 1))
                retry_summary["total_retries"] += max(attempts - 1, 0)

        # Count retries in failures
        for failure in results.failures:
            info = failure.get("retry")
            if info:
                retry_present = True
                attempts = int(info.get("attempts", 0))
                retry_summary["total_retries"] += max(attempts - 1, 0)

        return retry_summary if retry_present else None

    def _resolve_security_level(self, df: pd.DataFrame) -> SecurityLevel:
        """Resolve final security level from DataFrame and configuration."""
        df_security_level = getattr(df, "attrs", {}).get("security_level") if hasattr(df, "attrs") else None
        self._active_security_level = resolve_security_level(self.security_level, df_security_level)
        return self._active_security_level

    def _resolve_determinism_level(self, df: pd.DataFrame) -> DeterminismLevel:
        """Resolve final determinism level from DataFrame and configuration."""
        df_determinism_level = getattr(df, "attrs", {}).get("determinism_level") if hasattr(df, "attrs") else None
        self._active_determinism_level = resolve_determinism_level(self.determinism_level, df_determinism_level)
        return self._active_determinism_level

    # ============================================================================
    # Prompt Compilation Helpers
    # ============================================================================

    def _compile_system_prompt(self, engine: PromptEngine) -> PromptTemplate:
        """Compile system prompt template."""
        return engine.compile(
            self.prompt_system or "",
            name=f"{self.experiment_name or 'experiment'}:system",
            defaults=self.prompt_defaults or {},
        )

    def _compile_user_prompt(self, engine: PromptEngine) -> PromptTemplate:
        """Compile user prompt template."""
        return engine.compile(
            self.prompt_template or "",
            name=f"{self.experiment_name or 'experiment'}:user",
            defaults=self.prompt_defaults or {},
        )

    def _compile_criteria_prompts(self, engine: PromptEngine) -> dict[str, PromptTemplate]:
        """Compile criteria prompt templates."""
        criteria_templates: dict[str, PromptTemplate] = {}

        if not self.criteria:
            return criteria_templates

        for crit in self.criteria:
            template_text = crit.get("template", self.prompt_template or "")
            crit_name = crit.get("name") or template_text
            defaults = dict(self.prompt_defaults or {})
            defaults.update(crit.get("defaults", {}))
            criteria_templates[crit_name] = engine.compile(
                template_text,
                name=f"{self.experiment_name or 'experiment'}:criteria:{crit_name}",
                defaults=defaults,
            )

        return criteria_templates

    def _run_aggregation(self, results: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Execute aggregator plugins and collect results.

        Returns aggregates dictionary if any aggregator produced output, None otherwise.
        """
        aggregates: dict[str, Any] = {}
        for plugin in self.aggregator_plugins or []:
            derived = plugin.finalize(results)
            if derived:
                # Standardize aggregator payloads: always include failures (possibly empty)
                if isinstance(derived, dict) and "failures" not in derived:
                    derived["failures"] = []
                aggregates[plugin.name] = derived

        return aggregates if aggregates else None

    def _assemble_metadata(
        self,
        results: list[dict[str, Any]],
        failures: list[dict[str, Any]],
        aggregates: dict[str, Any] | None,
        df: pd.DataFrame,
    ) -> ExecutionMetadata:
        """Assemble execution metadata from results and configuration.

        Returns ExecutionMetadata dataclass with all metadata fields populated.
        """
        metadata = ExecutionMetadata(
            processed_rows=len(results),
            total_rows=len(df),
        )

        # Calculate retry summary
        retry_summary = self._calculate_retry_summary(ProcessingResult(records=results, failures=failures))
        if retry_summary:
            metadata.retry_summary = retry_summary

        # Add aggregates if present
        if aggregates:
            metadata.aggregates = aggregates

        # Add cost summary if available
        if self.cost_tracker:
            summary = self.cost_tracker.summary()
            if summary:
                metadata.cost_summary = summary

        # Add failures if present
        if failures:
            metadata.failures = failures

        # Resolve security and determinism levels
        metadata.security_level = self._resolve_security_level(df)
        metadata.determinism_level = self._resolve_determinism_level(df)

        # Add early stop reason if present
        if self._early_stop_reason:
            metadata.early_stop = dict(self._early_stop_reason)

        return metadata

    def _dispatch_to_sinks(self, payload: dict[str, Any], metadata: dict[str, Any]) -> None:
        """Dispatch payload to configured sinks via artifact pipeline."""
        pipeline = ArtifactPipeline(self._build_sink_bindings())
        pipeline.execute(payload, metadata)

    # ============================================================================
    # Row Processing Orchestration
    # ============================================================================

    def _prepare_rows_to_process(
        self,
        df: pd.DataFrame,
        checkpoint_manager: CheckpointManager | None,
    ) -> list[tuple[int, pd.Series, dict[str, Any], str | None]]:
        """Prepare list of rows to process, filtering checkpointed and early-stopped rows.

        Args:
            df: Input DataFrame with rows to process
            checkpoint_manager: Optional CheckpointManager for resumption tracking

        Returns:
            List of (index, row, context, row_id) tuples ready for processing

        Example:
            >>> df = pd.DataFrame({"id": ["A", "B", "C"], "text": ["x", "y", "z"]})
            >>> checkpoint_mgr = CheckpointManager(path=Path("checkpoint.txt"), id_field="id")
            >>> checkpoint_mgr.mark_processed("A")  # "A" already processed
            >>> rows = runner._prepare_rows_to_process(df, checkpoint_mgr)
            >>> len(rows)  # Only B and C remain
            2
            >>> rows[0][0]  # First row index
            1
            >>> rows[0][3]  # First row ID
            'B'
        """
        rows_to_process: list[tuple[int, pd.Series, dict[str, Any], str | None]] = []
        for idx, (_, row) in enumerate(df.iterrows()):
            context = prepare_prompt_context(row, include_fields=self.prompt_fields)

            # Skip checkpoint-filtered rows (guard clause pattern)
            if checkpoint_manager is not None:
                row_id = context.get(checkpoint_manager.id_field)
                if row_id is not None and checkpoint_manager.is_processed(row_id):
                    continue
            else:
                row_id = None

            if self._early_stop_event and self._early_stop_event.is_set():
                break
            rows_to_process.append((idx, row, context, row_id))

        return rows_to_process

    # ============================================================================
    # Initialization Helpers
    # ============================================================================

    def _init_checkpoint(self) -> CheckpointManager | None:
        """Initialize checkpoint configuration with fail-closed path validation.

        Security Model (FAIL-CLOSED):
            User-provided checkpoint paths are UNTRUSTED and MUST be validated.
            If allowed_base_path is not specified in configuration, we provide
            a safe default (current working directory) rather than disabling
            validation entirely. This prevents path traversal attacks.

        Returns:
            CheckpointManager instance with validated path, or None if checkpointing disabled

        Raises:
            ValueError: If checkpoint path escapes allowed base or contains symlinks

        Security Rationale:
            NEVER allow user configurations to bypass path validation by omitting
            allowed_base_path. This prevents attacks like:
                checkpoint_config:
                  path: "../../../etc/passwd"  # Path traversal
                  # Omitted allowed_base_path to bypass validation
        """
        if not self.checkpoint_config:
            return None

        checkpoint_path = Path(self.checkpoint_config.get("path", "checkpoint.txt"))
        checkpoint_field = self.checkpoint_config.get("field", "APPID")

        # SECURITY: Fail-closed path validation
        # User configs MUST NOT bypass validation by omitting allowed_base_path
        allowed_base = self.checkpoint_config.get("allowed_base_path")
        if allowed_base:
            allowed_base_path = Path(allowed_base)
        else:
            # FAIL-CLOSED: Default to CWD for strict validation
            # This ensures user-provided paths cannot escape to system directories
            allowed_base_path = Path.cwd()
            logger.info(
                "Checkpoint allowed_base_path not specified in config. "
                "FAIL-CLOSED: Defaulting to current working directory for security: %s. "
                "Checkpoint path will be validated against this directory.",
                allowed_base_path
            )

        return CheckpointManager(
            path=checkpoint_path,
            id_field=checkpoint_field,
            allowed_base_path=allowed_base_path,  # Always set (never None)
        )

    def _init_prompts(self) -> tuple[PromptEngine, PromptTemplate, PromptTemplate, dict[str, PromptTemplate]]:
        """Initialize and compile all prompt templates.

        Returns tuple of (engine, system_template, user_template, criteria_templates).
        Also caches compiled templates in instance variables.
        """
        engine = self.prompt_engine or PromptEngine()
        system_template = self._compile_system_prompt(engine)
        user_template = self._compile_user_prompt(engine)
        criteria_templates = self._compile_criteria_prompts(engine)

        # Cache compiled templates
        self._compiled_system_prompt = system_template
        self._compiled_user_prompt = user_template
        self._compiled_criteria_prompts = criteria_templates

        return engine, system_template, user_template, criteria_templates

    def _init_validation(self, df: pd.DataFrame) -> None:
        """Initialize schema validation and malformed data tracking."""
        datasource_schema = df.attrs.get("schema") if hasattr(df, "attrs") else None
        if datasource_schema:
            self._validate_plugin_schemas(datasource_schema)

        self._malformed_rows = []

    def _create_result_handlers(
        self,
        records_with_index: list[tuple[int, dict[str, Any]]],
        failures: list[dict[str, Any]],
        checkpoint_manager: CheckpointManager | None,
    ) -> ResultHandlers:
        """Create success/failure handlers with checkpoint integration.

        Creates callback handlers that manage result accumulation, checkpoint persistence,
        and early stop triggering for row processing operations.

        Args:
            records_with_index: List to accumulate successful (index, record) tuples
            failures: List to accumulate failure dictionaries
            checkpoint_manager: Optional manager for checkpoint persistence

        Returns:
            ResultHandlers with on_success and on_failure callbacks
        """

        def handle_success(idx: int, record: dict[str, Any], row_id: str | None) -> None:
            records_with_index.append((idx, record))
            if checkpoint_manager is not None and row_id is not None:
                checkpoint_manager.mark_processed(row_id)
            self._maybe_trigger_early_stop(record, row_index=idx)

        def handle_failure(failure: dict[str, Any]) -> None:
            failures.append(failure)

        return ResultHandlers(on_success=handle_success, on_failure=handle_failure)

    def _process_rows_sequentially(
        self,
        rows_to_process: list[tuple[int, pd.Series, dict[str, Any], str | None]],
        engine: PromptEngine,
        system_template: PromptTemplate,
        user_template: PromptTemplate,
        criteria_templates: dict[str, PromptTemplate],
        row_plugins: list[RowExperimentPlugin],
        handlers: ResultHandlers,
    ) -> None:
        """Process rows sequentially with early stop support.

        Processes each row one at a time in order, checking for early stop between rows.
        Uses provided handlers to manage successful and failed processing results.

        Args:
            rows_to_process: List of (index, row, context, row_id) tuples
            engine: Prompt engine for template rendering
            system_template: Compiled system prompt template
            user_template: Compiled user prompt template
            criteria_templates: Dict of compiled criteria templates by name
            row_plugins: List of row-level experiment plugins
            handlers: ResultHandlers with success/failure callbacks
        """
        for idx, row, context, row_id in rows_to_process:
            if self._early_stop_event and self._early_stop_event.is_set():
                break

            record, failure = self._process_single_row(
                engine,
                system_template,
                user_template,
                criteria_templates,
                row_plugins,
                context,
                row,
                row_id,
            )

            if record:
                handlers.on_success(idx, record, row_id)
            if failure:
                handlers.on_failure(failure)

    def _sort_and_extract_records(
        self, records_with_index: list[tuple[int, dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        """Sort records by original row index and extract record dictionaries.

        Maintains DataFrame row order by sorting records according to their original
        index, then extracts just the record dictionaries.

        Args:
            records_with_index: List of (index, record) tuples from processing

        Returns:
            Sorted list of record dictionaries
        """
        records_with_index.sort(key=lambda item: item[0])
        return [record for _, record in records_with_index]

    def _execute_row_processing(
        self,
        rows_to_process: list[tuple[int, pd.Series, dict[str, Any], str | None]],
        engine: PromptEngine,
        system_template: PromptTemplate,
        user_template: PromptTemplate,
        criteria_templates: dict[str, PromptTemplate],
        row_plugins: list[RowExperimentPlugin],
        checkpoint_manager: CheckpointManager | None,
    ) -> ProcessingResult:
        """Execute row processing using parallel or sequential execution based on configuration.

        This method orchestrates the core experiment execution loop. It processes each row
        through the LLM, applies row plugins, and manages checkpointing. Execution mode
        (parallel vs sequential) is determined by concurrency_config.

        Args:
            rows_to_process: List of (index, row, context, row_id) tuples prepared by _prepare_rows_to_process()
            engine: Compiled prompt engine for rendering templates
            system_template: Compiled system prompt template
            user_template: Compiled user prompt template
            criteria_templates: Dict of compiled criteria prompt templates by name
            row_plugins: List of row-level experiment plugins to apply
            checkpoint_manager: Optional CheckpointManager for tracking completion

        Returns:
            ProcessingResult containing records list and failures list

        Example:
            >>> # Prepare inputs
            >>> rows = [(0, row_series, {"text": "hello"}, "row_1")]
            >>> engine = PromptEngine()
            >>> sys_tmpl = engine.compile("You are helpful")
            >>> user_tmpl = engine.compile("Process: {{text}}")
            >>> checkpoint_mgr = CheckpointManager(Path("checkpoint.txt"), id_field="id")
            >>>
            >>> # Execute processing
            >>> result = runner._execute_row_processing(
            ...     rows, engine, sys_tmpl, user_tmpl, {}, [], checkpoint_mgr
            ... )
            >>> result.records  # List of successful processing records
            [{"row": {"text": "hello"}, "response": {...}, ...}]
            >>> result.failures  # List of failed row processing attempts
            []
        """
        records_with_index: list[tuple[int, dict[str, Any]]] = []
        failures: list[dict[str, Any]] = []

        # Create handlers with checkpoint integration
        handlers = self._create_result_handlers(records_with_index, failures, checkpoint_manager)

        # Execute parallel or sequential based on configuration
        concurrency_cfg = self.concurrency_config or {}
        if rows_to_process and self._should_run_parallel(concurrency_cfg, len(rows_to_process)):
            self._run_parallel(
                rows_to_process,
                engine,
                system_template,
                user_template,
                criteria_templates,
                row_plugins,
                handlers.on_success,
                handlers.on_failure,
                concurrency_cfg,
            )
        else:
            self._process_rows_sequentially(
                rows_to_process,
                engine,
                system_template,
                user_template,
                criteria_templates,
                row_plugins,
                handlers,
            )

        # Sort and extract results maintaining row order
        results = self._sort_and_extract_records(records_with_index)
        return ProcessingResult(records=results, failures=failures)

    def run(self, df: pd.DataFrame) -> dict[str, Any]:
        """Execute the run, returning a structured payload for sinks and reports."""
        self._init_early_stop()
        checkpoint_manager = self._init_checkpoint()

        row_plugins = self.row_plugins or []

        # Initialize and compile prompt templates
        engine, system_template, user_template, criteria_templates = self._init_prompts()

        # Initialize schema validation and malformed data tracking
        self._init_validation(df)

        # Prepare rows to process (filtering checkpointed and early-stopped rows)
        rows_to_process = self._prepare_rows_to_process(df, checkpoint_manager)

        # Execute row processing (parallel or sequential based on configuration)
        processing_result = self._execute_row_processing(
            rows_to_process,
            engine,
            system_template,
            user_template,
            criteria_templates,
            row_plugins,
            checkpoint_manager,
        )
        results = processing_result.records
        failures = processing_result.failures

        payload: dict[str, Any] = {"results": results, "failures": failures}
        aggregates = self._run_aggregation(results)
        if aggregates:
            payload["aggregates"] = aggregates

        # Assemble metadata using helper method
        metadata_obj = self._assemble_metadata(results, failures, aggregates, df)
        metadata = metadata_obj.to_dict()

        # Add metadata-derived fields to payload
        if metadata_obj.cost_summary:
            payload["cost_summary"] = metadata_obj.cost_summary
        if metadata_obj.early_stop:
            payload["early_stop"] = metadata_obj.early_stop

        payload["metadata"] = metadata

        # Dispatch to sinks via artifact pipeline
        self._dispatch_to_sinks(payload, metadata)
        self._active_security_level = None
        return payload

    def _init_early_stop(self) -> None:
        self._early_stop_reason = None
        plugins: list[EarlyStopPlugin] = []
        parent_context = getattr(self, "plugin_context", None)

        if self.early_stop_plugins:
            plugins = list(self.early_stop_plugins)
        elif self.early_stop_config:
            definition = {"name": "threshold", "options": dict(self.early_stop_config)}
            plugin = create_early_stop_plugin(definition, parent_context=parent_context)
            plugins = [plugin]

        if plugins:
            for plugin in plugins:
                try:
                    plugin.reset()
                except AttributeError:
                    pass
            self._active_early_stop_plugins = plugins
            self._early_stop_event = threading.Event()
            self._early_stop_lock = threading.Lock()
        else:
            self._active_early_stop_plugins = []
            self._early_stop_event = None
            self._early_stop_lock = None

    def _maybe_trigger_early_stop(self, record: dict[str, Any], *, row_index: int | None = None) -> None:
        event = self._early_stop_event
        if not event or event.is_set():
            return
        plugins = self._active_early_stop_plugins or []
        if not plugins or self._early_stop_reason:
            return

        metadata: dict[str, Any] | None = None
        if row_index is not None:
            metadata = {"row_index": row_index}

        def _evaluate() -> None:
            if event.is_set() or self._early_stop_reason:
                return
            for plugin in plugins:
                try:
                    reason = plugin.check(record, metadata=metadata)
                except Exception:  # pragma: no cover - defensive guard
                    logger.exception(
                        "Early-stop plugin '%s' raised an unexpected error; continuing",
                        getattr(plugin, "name", "unknown"),
                    )
                    continue
                if not reason:
                    continue
                reason = dict(reason)
                reason.setdefault("plugin", getattr(plugin, "name", "unknown"))
                if metadata:
                    for key, value in metadata.items():
                        reason.setdefault(key, value)
                self._early_stop_reason = reason
                event.set()
                logger.info(
                    "Early stop triggered by plugin '%s' (reason: %s)",
                    reason.get("plugin", getattr(plugin, "name", "unknown")),
                    {k: v for k, v in reason.items() if k != "plugin"},
                )
                break

        if self._early_stop_lock:
            with self._early_stop_lock:
                _evaluate()
        else:
            _evaluate()

    def _process_single_row(
        self,
        engine: PromptEngine,
        system_template: PromptTemplate,
        user_template: PromptTemplate,
        criteria_templates: dict[str, PromptTemplate],
        row_plugins: list[RowExperimentPlugin],
        context: dict[str, Any],
        row: pd.Series,
        row_id: str | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if self._early_stop_event and self._early_stop_event.is_set():
            return None, None
        try:
            rendered_system_prompt, base_user_prompt = self._render_prompts(engine, system_template, user_template, context)
            record, primary_response = self._collect_responses(
                rendered_system_prompt,
                base_user_prompt,
                criteria_templates,
                context,
                row,
                row_id,
            )
            self._populate_prompt_metadata(
                record,
                system_template,
                user_template,
                rendered_system_prompt,
                base_user_prompt,
            )
            self._attach_retry_metadata(record, primary_response)
            self._apply_row_plugins(record, row_plugins)
            self._apply_security_level(record)
            return record, None
        except (PromptRenderingError, PromptValidationError) as exc:
            return None, {
                "row": context,
                "error": str(exc),
                "timestamp": time.time(),
            }
        except Exception as exc:  # pylint: disable=broad-except
            failure = {
                "row": context,
                "error": str(exc),
                "timestamp": time.time(),
            }
            history = getattr(exc, "_elspeth_retry_history", None)
            if history:
                failure["retry"] = {
                    "attempts": getattr(exc, "_elspeth_retry_attempts", len(history)),
                    "max_attempts": getattr(exc, "_elspeth_retry_max_attempts", len(history)),
                    "history": history,
                }
            return None, failure

    def _render_prompts(
        self,
        engine: PromptEngine,
        system_template: PromptTemplate,
        user_template: PromptTemplate,
        context: dict[str, Any],
    ) -> tuple[str, str]:
        rendered_system_prompt = engine.render(system_template, context)
        base_user_prompt = engine.render(user_template, context)
        return rendered_system_prompt, base_user_prompt

    def _collect_responses(
        self,
        rendered_system_prompt: str,
        base_user_prompt: str,
        criteria_templates: dict[str, PromptTemplate],
        context: dict[str, Any],
        row: pd.Series,
        row_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if self.criteria:
            return self._collect_criteria_responses(
                rendered_system_prompt,
                criteria_templates,
                context,
                row,
            )
        response = self._execute_llm(
            base_user_prompt,
            {"row_id": row.get("APPID", row_id)},
            system_prompt=rendered_system_prompt,
            row_context=context,
        )
        record: dict[str, Any] = {"row": context, "response": response}
        self._merge_response_metrics(record, [response])
        return record, response

    def _collect_criteria_responses(
        self,
        rendered_system_prompt: str,
        criteria_templates: dict[str, PromptTemplate],
        context: dict[str, Any],
        row: pd.Series,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        responses: dict[str, dict[str, Any]] = {}
        for crit in self.criteria or []:
            crit_name = crit.get("name") or crit.get("template", "criteria")
            prompt_template = criteria_templates[crit_name]
            user_prompt = prompt_template.render(context, extra={"criteria": crit_name})
            response = self._execute_llm(
                user_prompt,
                {"row_id": row.get("APPID"), "criteria": crit_name},
                system_prompt=rendered_system_prompt,
                row_context=context,
            )
            responses[crit_name] = response
        primary_response = next(iter(responses.values())) if responses else {}
        record: dict[str, Any] = {"row": context, "response": primary_response, "responses": responses}
        self._merge_response_metrics(record, responses.values())
        return record, primary_response

    @staticmethod
    def _merge_response_metrics(record: dict[str, Any], responses: Iterable[Mapping[str, Any]]) -> None:
        for resp in responses:
            metrics = resp.get("metrics") if isinstance(resp, Mapping) else None
            if metrics:
                record.setdefault("metrics", {}).update(metrics)

    @staticmethod
    def _populate_prompt_metadata(
        record: dict[str, Any],
        system_template: PromptTemplate,
        user_template: PromptTemplate,
        rendered_system_prompt: str,
        base_user_prompt: str,
    ) -> None:
        metadata = record.setdefault("metadata", {})
        metadata.setdefault("prompt_system", rendered_system_prompt)
        metadata.setdefault("prompt_user", base_user_prompt)
        metadata.setdefault("prompt_system_template", system_template.raw)
        metadata.setdefault("prompt_user_template", user_template.raw)
        required = getattr(user_template, "required_fields", None)
        if required:
            metadata.setdefault("prompt_user_fields", list(required))

    @staticmethod
    def _attach_retry_metadata(record: dict[str, Any], response: Mapping[str, Any]) -> None:
        retry_meta = response.get("retry") if isinstance(response, Mapping) else None
        if retry_meta:
            record["retry"] = retry_meta

    def _apply_row_plugins(self, record: dict[str, Any], row_plugins: list[RowExperimentPlugin]) -> None:
        responses = record.get("responses") or {"default": record.get("response")}
        for plugin in row_plugins:
            derived = plugin.process_row(record["row"], responses)
            if derived:
                record.setdefault("metrics", {}).update(derived)

    def _apply_security_level(self, record: dict[str, Any]) -> None:
        if self._active_security_level:
            record["security_level"] = self._active_security_level

    def _should_run_parallel(self, config: dict[str, Any], backlog_size: int) -> bool:
        if not config or not config.get("enabled"):
            return False
        max_workers = max(int(config.get("max_workers", 1)), 1)
        if max_workers <= 1:
            return False
        threshold = int(config.get("backlog_threshold", 50))
        return backlog_size >= threshold

    def _run_parallel(
        self,
        rows_to_process: list[tuple[int, pd.Series, dict[str, Any], str | None]],
        engine: PromptEngine,
        system_template: PromptTemplate,
        user_template: PromptTemplate,
        criteria_templates: dict[str, PromptTemplate],
        row_plugins: list[RowExperimentPlugin],
        handle_success: Callable[[int, dict[str, Any], str | None], None],
        handle_failure: Callable[[dict[str, Any]], None],
        config: dict[str, Any],
    ) -> None:
        max_workers = max(int(config.get("max_workers", 4)), 1)
        pause_threshold = float(config.get("utilization_pause", 0.8))
        pause_interval = float(config.get("pause_interval", 0.5))

        lock = threading.Lock()

        def worker(data: tuple[int, pd.Series, dict[str, Any], str | None]) -> None:
            if self._early_stop_event and self._early_stop_event.is_set():
                return
            idx, row, context, row_id = data
            record, failure = self._process_single_row(
                engine,
                system_template,
                user_template,
                criteria_templates,
                row_plugins,
                context,
                row,
                row_id,
            )
            with lock:
                if record:
                    handle_success(idx, record, row_id)
                if failure:
                    handle_failure(failure)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for data in rows_to_process:
                if self.rate_limiter and pause_threshold > 0:
                    while True:
                        utilization = self.rate_limiter.utilization()
                        if utilization < pause_threshold:
                            break
                        time.sleep(pause_interval)
                if self._early_stop_event and self._early_stop_event.is_set():
                    break
                executor.submit(worker, data)

    def _build_sink_bindings(self) -> list[SinkBinding]:
        bindings: list[SinkBinding] = []
        for index, sink in enumerate(self.sinks):
            artifact_config = getattr(sink, "_elspeth_artifact_config", {}) or {}
            plugin = getattr(sink, "_elspeth_plugin_name", sink.__class__.__name__)
            base_id = getattr(sink, "_elspeth_sink_name", plugin)
            sink_id = f"{base_id}:{index}"
            security_level = getattr(sink, "_elspeth_security_level", None)
            if security_level is not None and not isinstance(security_level, SecurityLevel):
                security_level = ensure_security_level(security_level)
            bindings.append(
                SinkBinding(
                    id=sink_id,
                    plugin=plugin,
                    sink=sink,
                    artifact_config=artifact_config,
                    original_index=index,
                    security_level=security_level,
                )
            )
        return bindings

    def _execute_llm(
        self,
        user_prompt: str,
        metadata: dict[str, Any],
        *,
        system_prompt: str | None = None,
        row_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        delay = 0.0
        max_attempts = 1
        backoff = 0.0
        if self.retry_config:
            max_attempts = int(self.retry_config.get("max_attempts", 1))
            delay = float(self.retry_config.get("initial_delay", 0.0))
            backoff = float(self.retry_config.get("backoff_multiplier", 1.0))

        attempt = 0
        last_error: Exception | None = None
        attempt_history: list[dict[str, Any]] = []
        last_request: LLMRequest | None = None
        while attempt < max_attempts:
            attempt += 1
            attempt_start = time.time()
            try:
                request = LLMRequest(
                    system_prompt=system_prompt or self.prompt_system or "",
                    user_prompt=user_prompt,
                    metadata={**metadata, "attempt": attempt},
                )
                last_request = request
                for middleware in self.llm_middlewares or []:
                    request = middleware.before_request(request)

                if self.rate_limiter:
                    acquire_context = self.rate_limiter.acquire({"experiment": self.experiment_name, **request.metadata})
                else:
                    acquire_context = None

                if acquire_context:
                    with acquire_context:
                        response = self.llm_client.generate(
                            system_prompt=request.system_prompt,
                            user_prompt=request.user_prompt,
                            metadata=request.metadata,
                        )
                else:
                    response = self.llm_client.generate(
                        system_prompt=request.system_prompt,
                        user_prompt=request.user_prompt,
                        metadata=request.metadata,
                    )

                for middleware in reversed(self.llm_middlewares or []):
                    response = middleware.after_response(request, response)
                if self.cost_tracker:
                    cost_metrics = self.cost_tracker.record(response, {"experiment": self.experiment_name, **request.metadata})
                    if cost_metrics:
                        response.setdefault("metrics", {}).update(cost_metrics)

                self._run_validations(response, request, row_context=row_context)

                attempt_record = {
                    "attempt": attempt,
                    "status": "success",
                    "duration": max(time.time() - attempt_start, 0.0),
                }
                attempt_history.append(attempt_record)
                response.setdefault("metrics", {})["attempts_used"] = attempt
                response.setdefault(
                    "retry",
                    {
                        "attempts": attempt,
                        "max_attempts": max_attempts,
                        "history": attempt_history,
                    },
                )
                if self.rate_limiter:
                    self.rate_limiter.update_usage(response, request.metadata)
                return response
            except Exception as exc:  # pylint: disable=broad-except
                last_error = exc
                attempt_record = {
                    "attempt": attempt,
                    "status": "error",
                    "duration": max(time.time() - attempt_start, 0.0),
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                }
                if attempt >= max_attempts:
                    attempt_history.append(attempt_record)
                    break
                sleep_for = delay if delay > 0 else 0
                attempt_record["next_delay"] = sleep_for
                attempt_history.append(attempt_record)
                if sleep_for > 0:
                    time.sleep(sleep_for)
                if backoff and backoff > 0:
                    delay = delay * backoff if delay else backoff

        if last_error is None:
            raise RuntimeError("Retry loop terminated without capturing an error")
        if last_request is not None:
            setattr(last_error, "_elspeth_retry_history", attempt_history)
            setattr(last_error, "_elspeth_retry_attempts", attempt)
            setattr(last_error, "_elspeth_retry_max_attempts", max_attempts)
            try:
                self._notify_retry_exhausted(last_request, last_error, attempt_history)
            except Exception:  # pragma: no cover - defensive logging
                logger.debug("Retry exhausted hook raised", exc_info=True)
        raise last_error

    def _notify_retry_exhausted(self, request: LLMRequest, error: Exception, history: list[dict[str, Any]]) -> None:
        metadata = {
            "experiment": self.experiment_name,
            "attempts": getattr(error, "_elspeth_retry_attempts", len(history)),
            "max_attempts": getattr(error, "_elspeth_retry_max_attempts", len(history)),
            "error": str(error),
            "error_type": error.__class__.__name__,
            "history": history,
        }
        logger.warning(
            "LLM request exhausted retries for experiment '%s' after %s attempts: %s",
            self.experiment_name,
            metadata["attempts"],
            metadata["error"],
        )
        for middleware in self.llm_middlewares or []:
            hook = getattr(middleware, "on_retry_exhausted", None)
            if callable(hook):
                try:
                    hook(request, metadata, error)
                except Exception:  # pragma: no cover - middleware isolation
                    logger.debug("Middleware %s retry hook failed", getattr(middleware, "name", middleware), exc_info=True)

    def _run_validations(
        self,
        response: dict[str, Any],
        request: LLMRequest,
        *,
        row_context: dict[str, Any] | None = None,
    ) -> None:
        plugins = self.validation_plugins or []
        if not plugins:
            return
        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        context = row_context
        for plugin in plugins:
            plugin.validate(response, context=context, metadata=metadata)

    def _validate_plugin_schemas(self, datasource_schema: Type[DataFrameSchema]) -> None:
        """Validate plugin compatibility with public helper.

        This is config-time validation - runs once before row processing.
        """
        validate_plugin_schemas(
            datasource_schema,
            row_plugins=self.row_plugins or [],
            aggregator_plugins=self.aggregator_plugins or [],
            validation_plugins=self.validation_plugins or [],
        )

    def _write_malformed_data(self) -> None:
        """Write malformed rows to dedicated sink."""
        if not self._malformed_rows or not self.malformed_data_sink:
            return

        malformed_payload = {
            "malformed_data": [v.to_dict() for v in self._malformed_rows],
            "count": len(self._malformed_rows),
            "schema_name": self._malformed_rows[0].schema_name if self._malformed_rows else None,
        }

        try:
            self.malformed_data_sink.write(
                malformed_payload,
                metadata={"type": "schema_violations"},
            )
            logger.info(
                "Wrote %d malformed rows to dedicated sink",
                len(self._malformed_rows),
            )
        except Exception as exc:
            logger.error(
                "Failed to write malformed data to sink: %s",
                exc,
                exc_info=True,
            )
