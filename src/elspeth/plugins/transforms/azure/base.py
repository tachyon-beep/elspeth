"""Base class for Azure safety transforms.

Provides shared infrastructure for Azure Content Safety and Azure Prompt Shield:
- Batch processing lifecycle (connect_output, accept, process, close)
- Audited HTTP client management with per-state_id caching
- Rate limiting integration
- Recorder/telemetry capture from LifecycleContext
- Field scanning loop with shared error handling

Subclasses implement _analyze_field() for their specific Azure API.
"""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import Field, field_validator

from elspeth.contracts import Determinism
from elspeth.contracts.contexts import LifecycleContext, TransformContext
from elspeth.contracts.schema_contract import PipelineRow
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.batching import BatchTransformMixin, OutputPort
from elspeth.plugins.config_base import TransformDataConfig
from elspeth.plugins.pooling import CapacityError, is_capacity_error
from elspeth.plugins.results import TransformResult
from elspeth.plugins.schema_factory import create_schema_from_config
from elspeth.plugins.transforms.azure.errors import MalformedResponseError
from elspeth.plugins.transforms.safety_utils import (
    get_fields_to_scan,
)
from elspeth.plugins.transforms.safety_utils import (
    validate_fields_not_empty as _validate_fields,
)

if TYPE_CHECKING:
    from elspeth.core.landscape.recorder import LandscapeRecorder


class BaseAzureSafetyConfig(TransformDataConfig):
    """Shared configuration fields for Azure safety transforms.

    Subclass to add transform-specific fields (thresholds, analysis_type, etc.).
    """

    endpoint: str = Field(..., description="Azure Content Safety endpoint URL")
    api_key: str = Field(..., description="Azure Content Safety API key")
    fields: str | list[str] = Field(
        ...,
        description="Field name(s) to analyze, or 'all' for all string fields",
    )
    max_capacity_retry_seconds: int = Field(3600, gt=0, description="Max seconds to retry capacity errors")

    @field_validator("fields")
    @classmethod
    def validate_fields_not_empty(cls, v: str | list[str]) -> str | list[str]:
        """Reject empty fields — security transform must scan at least one field."""
        return _validate_fields(v)


class BaseAzureSafetyTransform(BaseTransform, BatchTransformMixin):
    """Base class for Azure safety transforms with shared batch infrastructure.

    Handles:
    - Batch processing lifecycle (connect_output, accept, flush, close)
    - Per-state_id AuditedHTTPClient caching for audit trail integrity
    - Rate limiting, recorder, and telemetry capture
    - Field scanning loop with shared error handling

    Subclasses must:
    - Set class attribute ``name`` (used for rate limiter lookup and plugin registration)
    - Override ``__init__`` to parse their config and call ``super().__init__``
    - Implement ``_analyze_field()`` for API-specific analysis and result checking
    """

    determinism = Determinism.EXTERNAL_CALL
    plugin_version = "1.0.0"
    creates_tokens = False

    API_VERSION = "2024-09-01"

    def __init__(
        self,
        config: dict[str, Any],
        cfg: BaseAzureSafetyConfig,
        schema_name: str,
    ) -> None:
        super().__init__(config)

        self._endpoint = cfg.endpoint.rstrip("/")
        self._api_key = cfg.api_key
        self._fields = cfg.fields
        self._max_capacity_retry_seconds = cfg.max_capacity_retry_seconds

        schema = create_schema_from_config(cfg.schema_config, schema_name, allow_coercion=False)
        self.input_schema = schema
        self.output_schema = schema

        self._recorder: LandscapeRecorder | None = None
        self._run_id: str = ""
        self._telemetry_emit: Callable[[Any], None] = lambda event: None
        self._limiter: Any = None  # RateLimiter | NoOpLimiter | None

        self._http_clients: dict[str, Any] = {}  # state_id -> AuditedHTTPClient
        self._http_clients_lock = Lock()

        self._batch_initialized = False

    def on_start(self, ctx: LifecycleContext) -> None:
        """Capture recorder, telemetry, and rate limit context for pooled execution."""
        super().on_start(ctx)
        self._recorder = ctx.landscape
        self._run_id = ctx.run_id
        self._telemetry_emit = ctx.telemetry_emit
        self._limiter = ctx.rate_limit_registry.get_limiter(self.name) if ctx.rate_limit_registry is not None else None

    def connect_output(
        self,
        output: OutputPort,
        max_pending: int = 30,
    ) -> None:
        """Connect output port and initialize batch processing.

        Call this after __init__ but before accept(). The output port
        receives results in FIFO order (submission order, not completion order).

        Args:
            output: Output port to emit results to (sink adapter or next transform)
            max_pending: Maximum rows in flight before accept() blocks (backpressure)

        Raises:
            RuntimeError: If called more than once
        """
        if self._batch_initialized:
            raise RuntimeError("connect_output() already called")

        self.init_batch_processing(
            max_pending=max_pending,
            output=output,
            name=self.name,
            max_workers=max_pending,  # Match workers to max_pending
            batch_wait_timeout=float(self._max_capacity_retry_seconds),
        )
        self._batch_initialized = True

    def accept(self, row: PipelineRow, ctx: TransformContext) -> None:
        """Accept a row for processing.

        Submits the row to the batch processing pipeline. Returns quickly
        unless backpressure is applied (buffer full). Results flow through
        the output port in FIFO order.

        Args:
            row: Input row with fields to analyze
            ctx: Plugin context with token and landscape

        Raises:
            RuntimeError: If connect_output() was not called
        """
        if not self._batch_initialized:
            raise RuntimeError("connect_output() must be called before accept(). This wires up the output port for result emission.")
        self.accept_row(row, ctx, self._process_row)

    def process(
        self,
        row: PipelineRow,
        ctx: TransformContext,
    ) -> TransformResult:
        """Not supported - use accept() for row-level pipelining.

        This transform uses BatchTransformMixin for concurrent row processing
        with FIFO output ordering. Call accept() instead of process().

        Raises:
            NotImplementedError: Always, directing callers to use accept()
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} uses row-level pipelining. Use accept() instead of process(). See class docstring for usage."
        )

    def _process_row(
        self,
        row: PipelineRow,
        ctx: TransformContext,
    ) -> TransformResult:
        """Process a single row. Called by worker threads.

        This is the processor function passed to accept_row(). It runs in
        the BatchTransformMixin's worker pool.
        """
        # Capture state_id at entry — ctx is mutable and shared across retry
        # attempts, so ctx.state_id can change between try and finally if a
        # timeout triggers a retry with a new state_id.
        state_id = ctx.state_id
        if state_id is None:
            raise RuntimeError("state_id is required for batch processing. Ensure transform is executed through the engine.")
        token_id = ctx.token.token_id if ctx.token is not None else None

        try:
            return self._process_single_with_state(row, state_id, token_id=token_id)
        finally:
            # Clean up cached HTTP client for this state_id
            with self._http_clients_lock:
                client = self._http_clients.pop(state_id, None)
            if client is not None:
                client.close()

    def _process_single_with_state(
        self,
        row: PipelineRow,
        state_id: str,
        *,
        token_id: str | None = None,
    ) -> TransformResult:
        """Process a single row with explicit state_id.

        Iterates over configured fields, validates presence and type,
        then delegates to _analyze_field() for API-specific analysis.
        Handles shared exception types (httpx errors, MalformedResponseError).

        Raises:
            CapacityError: On rate limit errors (for worker pool retry)
        """
        fields_to_scan = self._get_fields_to_scan(row)
        all_mode = self._fields == "all"

        for field_name in fields_to_scan:
            if field_name not in row:
                if all_mode:
                    continue  # "all" mode scans only present string fields
                # Explicitly-configured field is missing — fail CLOSED.
                # Security transform must not report "validated" when configured
                # fields were never analyzed.
                return TransformResult.error(
                    {"reason": "missing_field", "field": field_name},
                    retryable=False,
                )

            value = row[field_name]
            if not isinstance(value, str):
                # Explicitly-configured field is non-string — fail CLOSED.
                # ("all" mode pre-filters to string fields in _get_fields_to_scan,
                # so this branch only fires for explicitly-configured fields.)
                return TransformResult.error(
                    {
                        "reason": "non_string_field",
                        "field": field_name,
                        "actual_type": type(value).__name__,
                    },
                    retryable=False,
                )

            # Call subclass-specific analysis
            try:
                violation = self._analyze_field(value, field_name, state_id, token_id=token_id)
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if is_capacity_error(status_code):
                    # Convert to CapacityError for pooled executor retry (429/503/529)
                    raise CapacityError(status_code, str(e)) from e
                return TransformResult.error(
                    {
                        "reason": "api_error",
                        "error_type": "http_error",
                        "status_code": status_code,
                        "message": str(e),
                    },
                    retryable=False,
                )
            except httpx.RequestError as e:
                return TransformResult.error(
                    {
                        "reason": "api_error",
                        "error_type": "network_error",
                        "message": str(e),
                    },
                    retryable=True,
                )
            except MalformedResponseError as e:
                # Malformed API response — fail CLOSED, non-retryable
                # (response structure won't improve on retry)
                return TransformResult.error(
                    {
                        "reason": "api_error",
                        "error_type": "malformed_response",
                        "message": str(e),
                    },
                    retryable=False,
                )

            if violation is not None:
                return violation

        return TransformResult.success(row, success_reason={"action": "validated"})

    def _analyze_field(
        self,
        value: str,
        field_name: str,
        state_id: str,
        *,
        token_id: str | None = None,
    ) -> TransformResult | None:
        """Analyze a single field value. Subclasses must implement.

        Returns TransformResult.error if the field fails analysis, or None
        if it passes. May raise httpx.HTTPStatusError, httpx.RequestError,
        or MalformedResponseError — these are handled by the base class's
        _process_single_with_state().
        """
        raise NotImplementedError

    def _get_fields_to_scan(self, row: PipelineRow) -> list[str]:
        """Determine which fields to scan based on config."""
        return get_fields_to_scan(self._fields, row)

    def _get_http_client(self, state_id: str, *, token_id: str | None = None) -> Any:
        """Get or create audited HTTP client for a state_id.

        Clients are cached to preserve call_index across retries.
        This ensures uniqueness of (state_id, call_index) even when
        the worker pool retries after CapacityError.

        Thread-safe: multiple workers can call this concurrently.
        """
        from elspeth.plugins.clients.http import AuditedHTTPClient

        with self._http_clients_lock:
            if state_id not in self._http_clients:
                if self._recorder is None:
                    raise RuntimeError(f"{self.name}: recorder not initialized — call on_start() before processing")
                self._http_clients[state_id] = AuditedHTTPClient(
                    recorder=self._recorder,
                    state_id=state_id,
                    run_id=self._run_id,
                    telemetry_emit=self._telemetry_emit,
                    timeout=30.0,
                    headers={
                        "Ocp-Apim-Subscription-Key": self._api_key,
                        "Content-Type": "application/json",
                    },
                    limiter=self._limiter,
                    token_id=token_id,
                )
            return self._http_clients[state_id]

    def close(self) -> None:
        """Release resources."""
        # Shutdown batch processing infrastructure first
        if self._batch_initialized:
            self.shutdown_batch_processing()

        # Close all cached HTTP clients
        with self._http_clients_lock:
            for client in self._http_clients.values():
                client.close()
            self._http_clients.clear()

        self._recorder = None
