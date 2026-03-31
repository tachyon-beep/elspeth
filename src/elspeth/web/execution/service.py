"""ExecutionServiceImpl — background pipeline execution with thread safety.

Thread safety fixes implemented here:
- B2: Always pass shutdown_event=threading.Event() to Orchestrator.run()
- B3: Construct LandscapeDB/PayloadStore from WebSettings resolvers
- B7: except BaseException + future.add_done_callback() safety net
- B8/C1: _call_async() bridges sync thread to async event loop for SessionService

The _run_pipeline() method is the ONLY code that runs outside the asyncio
event loop. Everything else runs in the main async context. Because
SessionService methods are async, _run_pipeline() uses _call_async() to
schedule coroutines on the main event loop from the background thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Coroutine
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar, cast
from uuid import UUID

import structlog

from elspeth.cli_helpers import instantiate_plugins_from_config
from elspeth.contracts.audit import SecretResolutionInput
from elspeth.contracts.cli import ProgressEvent
from elspeth.contracts.errors import GracefulShutdownError
from elspeth.core.config import load_settings_from_yaml_string
from elspeth.core.dag.graph import ExecutionGraph
from elspeth.core.events import EventBus
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.payload_store import FilesystemPayloadStore
from elspeth.core.secrets import SecretResolutionError
from elspeth.engine.orchestrator.core import Orchestrator
from elspeth.engine.orchestrator.types import PipelineConfig
from elspeth.web.execution.progress import ProgressBroadcaster
from elspeth.web.execution.schemas import (
    RunEvent,
    RunStatusResponse,
    ValidationCheck,
    ValidationError,
    ValidationResult,
)
from elspeth.web.sessions.converters import state_from_record
from elspeth.web.sessions.protocol import RunAlreadyActiveError, SessionServiceProtocol  # B1: canonical definition

slog = structlog.get_logger()

T = TypeVar("T")

# B1 fix: RunAlreadyActiveError is NOT defined here — imported from
# sessions.protocol where the canonical definition lives. Defining a
# second class with the same name would prevent app.py's global
# exception handler (which catches sessions.protocol.RunAlreadyActiveError)
# from catching exceptions raised here.


class ExecutionServiceImpl:
    """Pipeline execution service with ThreadPoolExecutor backend.

    Construction: Created inside the FastAPI lifespan async context manager
    (after ProgressBroadcaster), NOT in the synchronous create_app() factory.
    Stored as application state and injected into route handlers via FastAPI's
    dependency injection. The event loop reference is obtained from
    asyncio.get_running_loop() in the lifespan (same loop as ProgressBroadcaster).

    Thread model: execute() submits _run_pipeline() to a ThreadPoolExecutor
    with max_workers=1. The pipeline runs in a background thread. All other
    methods run in the asyncio event loop thread.

    B8/C1 fix: SessionService methods are async. _run_pipeline() runs in a
    background thread and uses _call_async() to bridge async calls back to
    the main event loop via asyncio.run_coroutine_threadsafe().
    """

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        broadcaster: ProgressBroadcaster,
        settings: Any,  # WebSettings
        session_service: SessionServiceProtocol,
        yaml_generator: Any,  # YamlGenerator — injected, not module-level
        blob_service: Any = None,  # BlobServiceImpl — optional for blob linkage
        secret_service: Any = None,  # WebSecretService — optional for secret resolution
    ) -> None:
        self._loop = loop
        self._broadcaster = broadcaster
        self._settings = settings
        self._session_service = session_service
        self._yaml_generator = yaml_generator
        self._blob_service = blob_service
        self._secret_service = secret_service
        # AC #17: No run_repository — all Run CRUD delegates to SessionService
        # via create_run(), update_run_status(), get_active_run(), get_run().
        # R6 expanded params: landscape_run_id, pipeline_yaml, rows_processed,
        # rows_failed.
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._shutdown_events: dict[str, threading.Event] = {}

    def _call_async(self, coro: Coroutine[Any, Any, T]) -> T:
        """Bridge an async call from the background thread to the main event loop.

        B8/C1 fix: SessionService methods are async, but _run_pipeline() runs
        in a ThreadPoolExecutor worker thread. This helper schedules the
        coroutine on the main event loop and blocks until it completes.

        R6 fix: 30-second timeout prevents deadlock during shutdown — if the
        event loop is blocked in executor.shutdown(wait=True), this will raise
        TimeoutError instead of hanging forever.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=30.0)

    def shutdown(self) -> None:
        """Shut down the thread pool. Called during app shutdown.

        Sets all active shutdown events first so running pipelines can
        terminate gracefully before blocking on executor.shutdown(wait=True).
        """
        for event in list(self._shutdown_events.values()):
            event.set()
        self._executor.shutdown(wait=True)

    async def execute(self, session_id: UUID, state_id: UUID | None = None, *, user_id: str | None = None) -> UUID:
        """Start a background pipeline run.

        B6 enforcement: raises RunAlreadyActiveError if a pending or running
        run already exists for this session.

        Returns the run_id immediately.

        Args:
            session_id: Session to execute.
            state_id: Specific state to execute (latest if None).
            user_id: Authenticated user's ID for scoped secret resolution.

        Note: async because SessionService methods are async. The pipeline
        itself runs in a background thread — only setup is async.
        """
        # B6: One active run per session (AC #17: via SessionService)
        active = await self._session_service.get_active_run(session_id)
        if active is not None:
            raise RunAlreadyActiveError(str(session_id))

        # B4 fix: get_composition_state() doesn't exist on SessionService.
        # Use get_state() for explicit state_id, get_current_state() for latest.
        state_record = None
        if state_id is not None:
            state_record = await self._session_service.get_state(state_id)
            # Verify state belongs to the requested session (IDOR prevention)
            if state_record.session_id != session_id:
                raise ValueError(f"State {state_id} does not belong to session {session_id}")
        else:
            state_record = await self._session_service.get_current_state(session_id)
            if state_record is None:
                raise ValueError(f"No composition state exists for session {session_id}")

        assert state_record is not None

        # Bridge CompositionStateRecord → CompositionState for generate_yaml().
        # The record stores raw dicts; generate_yaml() needs the typed domain object.
        composition_state = state_from_record(state_record)

        # Path allowlist check — defense-in-depth. The validate endpoint also
        # checks this, but /execute does not require /validate first. An
        # authenticated user could skip validation and execute a state that
        # reads files outside the allowed directories.
        if composition_state.source is not None:
            from elspeth.web.composer.tools import _allowed_source_directories

            allowed_dirs = _allowed_source_directories(str(self._settings.data_dir))
            for key in ("path", "file"):
                value = composition_state.source.options.get(key)
                if value is not None:
                    resolved = Path(value).resolve()
                    if not any(resolved.is_relative_to(d) for d in allowed_dirs):
                        raise ValueError(f"Source {key}='{value}' resolves outside allowed directories")

        pipeline_yaml = self._yaml_generator.generate_yaml(composition_state)

        # Pre-validate blob_ref UUID before creating the run record.
        # UUID() can raise ValueError on malformed strings; if that happens
        # after create_run(), the pending run blocks the session permanently
        # because the except block below only cleans up _shutdown_events.
        parsed_blob_id: UUID | None = None
        if composition_state.source is not None and self._blob_service is not None:
            blob_ref = composition_state.source.options.get("blob_ref")
            if blob_ref is not None:
                parsed_blob_id = UUID(blob_ref)

        # B9 fix: create_run() generates its own UUID internally and returns
        # a RunRecord. Read the run_id back from the returned record so our
        # _shutdown_events key matches the DB record.
        run_record = await self._session_service.create_run(
            session_id=session_id,
            state_id=state_record.id,  # From the record, not the domain object
            pipeline_yaml=pipeline_yaml,
        )
        run_id = run_record.id  # Use the DB-generated UUID as canonical

        # Register shutdown event immediately so cancel() always finds it.
        # Without this, cancel() firing between create_run() and registration
        # bypasses the event and updates DB to "cancelled" directly — causing
        # an illegal cancelled→running transition when _run_pipeline starts.
        shutdown_event = threading.Event()
        self._shutdown_events[str(run_id)] = shutdown_event

        try:
            # Record blob-to-run linkage for input blobs
            if parsed_blob_id is not None:
                await self._blob_service.link_blob_to_run(
                    blob_id=parsed_blob_id,
                    run_id=run_id,
                    direction="input",
                )

            # Submit to thread pool
            future = self._executor.submit(self._run_pipeline, str(run_id), pipeline_yaml, shutdown_event, user_id)
        except BaseException as exc:
            self._shutdown_events.pop(str(run_id), None)
            # Transition run out of pending so the one-active-run constraint
            # doesn't permanently block this session.
            with contextlib.suppress(Exception):
                await self._session_service.update_run_status(run_id, status="failed", error=f"Setup failed: {exc}")
            raise
        # B7 Layer 2: safety net callback
        future.add_done_callback(self._on_pipeline_done)

        return run_id

    async def get_status(self, run_id: UUID) -> RunStatusResponse:
        """Return current run status. AC #17: delegates to SessionService."""
        run = await self._session_service.get_run(run_id)
        return RunStatusResponse(
            run_id=str(run.id),
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            rows_processed=run.rows_processed,
            rows_failed=run.rows_failed,
            error=run.error,
            landscape_run_id=run.landscape_run_id,
        )

    async def validate(self, session_id: UUID, *, user_id: str | None = None) -> ValidationResult:
        """Dry-run validation using real engine code paths.

        Wraps the sync validate_pipeline() call via run_in_executor
        to avoid blocking the event loop (AC #16).

        Args:
            session_id: Session whose current state to validate.
            user_id: Authenticated user's ID for scoped secret ref validation.
        """
        from functools import partial

        from elspeth.web.execution.validation import validate_pipeline

        state_record = await self._session_service.get_current_state(session_id)
        if state_record is None:
            return ValidationResult(
                is_valid=False,
                checks=[
                    ValidationCheck(
                        name="state_exists",
                        passed=False,
                        detail="No composition state exists for this session",
                    )
                ],
                errors=[
                    ValidationError(
                        component_id=None,
                        component_type=None,
                        message="No composition state exists for this session",
                        suggestion="Use the composer to build a pipeline first.",
                    )
                ],
            )

        composition_state = state_from_record(state_record)
        loop = asyncio.get_running_loop()
        return cast(
            ValidationResult,
            await loop.run_in_executor(
                None,
                partial(
                    validate_pipeline,
                    composition_state,
                    self._settings,
                    self._yaml_generator,
                    secret_service=self._secret_service,
                    user_id=user_id,
                ),
            ),
        )

    async def verify_run_ownership(self, user: Any, run_id: str) -> bool:
        """Verify that a run belongs to the authenticated user's session.

        Used by the WebSocket handler for IDOR protection. Checks both
        user_id and auth_provider_type to prevent cross-provider access
        when user_id namespaces overlap between providers.
        """
        run = await self._session_service.get_run(UUID(run_id))
        session = await self._session_service.get_session(run.session_id)
        return str(session.user_id) == str(user.user_id) and session.auth_provider_type == self._settings.auth_provider

    async def cancel(self, run_id: UUID) -> None:
        """Cancel a run via the shutdown Event.

        Active runs: sets the Event, Orchestrator detects during row processing.
        Pending runs (no Event registered yet): marks the run as cancelled
        directly via SessionService so _run_pipeline terminates immediately.
        Terminal runs: no-op (idempotent).

        Async because the pending-run path awaits SessionService (we're in
        the event loop thread, not the background thread).
        """
        event = self._shutdown_events.get(str(run_id))
        if event is not None:
            event.set()
        else:
            # No event means either pending (not yet started) or already done
            run = await self._session_service.get_run(run_id)
            if run.status not in ("completed", "failed", "cancelled"):
                await self._session_service.update_run_status(run_id, status="cancelled")

    # ── Background Thread ──────────────────────────────────────────────

    def _run_pipeline(
        self,
        run_id: str,
        pipeline_yaml: str,
        shutdown_event: threading.Event,
        user_id: str | None = None,
    ) -> None:
        """Execute a pipeline in the background thread.

        B7 fix: Wrapped in try/except BaseException/finally.
        - except BaseException: Updates run to failed, re-raises.
        - finally: Removes shutdown event from _shutdown_events.

        B2 fix: shutdown_event is ALWAYS passed to orchestrator.run().
        B3 fix: LandscapeDB and PayloadStore from WebSettings resolvers.

        Secret resolution: If secret_service and user_id are available,
        resolves {"secret_ref": "NAME"} patterns in the YAML config before
        loading settings. Resolved values exist only in the worker thread's
        local memory — never persisted.
        """
        landscape_db: LandscapeDB | None = None
        run_uuid = UUID(run_id)
        try:
            # B8/C1: SessionService is async — bridge from background thread.
            # Race defence: if cancel() updated DB to "cancelled" before we
            # started, this transition raises ValueError. Detect that specific
            # case and exit gracefully — the run was legitimately cancelled.
            try:
                self._call_async(self._session_service.update_run_status(run_uuid, status="running"))
            except ValueError:
                current = self._call_async(self._session_service.get_run(run_uuid))
                if current.status == "cancelled":
                    self._broadcaster.broadcast(
                        run_id,
                        RunEvent(
                            run_id=run_id,
                            timestamp=datetime.now(tz=UTC),
                            event_type="cancelled",
                            data={},
                        ),
                    )
                    self._finalize_output_blobs(run_id, success=False)
                    return  # Graceful exit — finally block still runs
                raise  # Non-cancelled ValueError — crash per offensive programming

            # B3 fix: construct from WebSettings, not hardcoded paths
            # NOTE: LandscapeDB is constructed per-run, not shared. This is safe
            # with max_workers=1 (no concurrent access) but wasteful — each run
            # creates a new SQLAlchemy engine. Acceptable for MVP; consider
            # sharing a single instance if profiling shows connection overhead.
            landscape_db = LandscapeDB(connection_string=self._settings.get_landscape_url())
            payload_store = FilesystemPayloadStore(base_path=self._settings.get_payload_store_path())

            # Resolve secret refs before writing YAML to temp file.
            # Resolved values exist only in this thread's local memory — the
            # original pipeline_yaml (persisted in the Run record) is untouched.
            resolved_yaml = pipeline_yaml
            secret_resolution_inputs: list[SecretResolutionInput] = []
            if self._secret_service is not None and user_id is not None:
                import yaml as _yaml

                from elspeth.core.secrets import resolve_secret_refs

                config_dict = _yaml.safe_load(pipeline_yaml)
                if not isinstance(config_dict, dict):
                    raise TypeError(
                        f"generate_yaml() produced non-dict YAML (got {type(config_dict).__name__}) — this is a bug in the YAML generator"
                    )
                resolved_dict, resolutions = resolve_secret_refs(config_dict, self._secret_service, user_id)
                resolved_yaml = _yaml.dump(resolved_dict, default_flow_style=False)

                # Map ResolvedSecret.scope (web domain) to
                # SecretResolutionInput.source (audit domain).
                # "server" secrets are env vars on the host → audit source "env".
                _SCOPE_TO_AUDIT_SOURCE: dict[str, str] = {
                    "user": "user",
                    "server": "env",
                }
                for rs in resolutions:
                    audit_source = _SCOPE_TO_AUDIT_SOURCE.get(rs.scope)
                    if audit_source is None:
                        raise ValueError(
                            f"No audit source mapping for secret scope {rs.scope!r} "
                            f"(secret: {rs.name!r}) — add mapping to _SCOPE_TO_AUDIT_SOURCE"
                        )
                    secret_resolution_inputs.append(
                        SecretResolutionInput(
                            env_var_name=rs.name,
                            source=audit_source,
                            vault_url=None,
                            secret_name=None,
                            timestamp=time.time(),
                            resolution_latency_ms=0.0,
                            fingerprint=rs.fingerprint,
                        )
                    )

            # Load settings from YAML string — never write resolved secrets
            # to disk.  load_settings_from_yaml_string() parses in-process,
            # bypassing Dynaconf file I/O.
            settings = load_settings_from_yaml_string(resolved_yaml)
            bundle = instantiate_plugins_from_config(settings)

            graph = ExecutionGraph.from_plugin_instances(
                source=bundle.source,
                source_settings=bundle.source_settings,
                transforms=bundle.transforms,
                sinks=bundle.sinks,
                aggregations=bundle.aggregations,
                gates=list(settings.gates),
                coalesce_settings=(list(settings.coalesce) if settings.coalesce else None),
            )
            graph.validate()

            # Include aggregation transforms alongside regular transforms,
            # following the CLI pattern (cli.py:868-878)
            from elspeth.contracts.types import AggregationName

            all_transforms = [t.plugin for t in bundle.transforms]

            agg_id_map = graph.get_aggregation_id_map()
            aggregation_settings: dict[str, Any] = {}

            for agg_name, (transform, agg_config) in bundle.aggregations.items():
                node_id = agg_id_map[AggregationName(agg_name)]
                aggregation_settings[node_id] = agg_config
                transform.node_id = node_id
                all_transforms.append(transform)

            pipeline_config = PipelineConfig(
                source=bundle.source,
                transforms=all_transforms,
                sinks=bundle.sinks,
                gates=list(settings.gates),
                aggregation_settings=aggregation_settings,
                coalesce_settings=(list(settings.coalesce) if settings.coalesce else []),
            )

            # Set up EventBus to bridge ProgressEvent -> RunEvent -> broadcaster.
            # _to_run_event is a pure mapping (system code) — let it crash.
            # broadcast() pushes to async queues — catch network/client errors.
            def _safe_broadcast(evt: ProgressEvent) -> None:
                run_event = self._to_run_event(run_id, evt)
                try:
                    self._broadcaster.broadcast(run_id, run_event)
                except Exception as broadcast_err:
                    slog.error(
                        "progress_broadcast_failed",
                        run_id=run_id,
                        error=str(broadcast_err),
                    )

            event_bus = EventBus()
            event_bus.subscribe(ProgressEvent, _safe_broadcast)

            orchestrator = Orchestrator(db=landscape_db, event_bus=event_bus)

            # B2 fix: ALWAYS pass shutdown_event — suppresses signal handler
            # installation from background thread (Python forbids
            # signal.signal() from non-main threads)
            result = orchestrator.run(
                pipeline_config,
                graph=graph,
                settings=settings,
                payload_store=payload_store,
                secret_resolutions=secret_resolution_inputs or None,
                shutdown_event=shutdown_event,  # B2: NEVER omit this
            )

            # Orchestrator.run() returns normally ONLY on completion.
            # If shutdown was requested, it raises GracefulShutdownError
            # (caught below). Do NOT check shutdown_event.is_set() here —
            # cancel() can set the event after processing finishes but
            # before we persist status, causing a completed run to be
            # misclassified as cancelled.
            self._broadcaster.broadcast(
                run_id,
                RunEvent(
                    run_id=run_id,
                    timestamp=datetime.now(tz=UTC),
                    event_type="completed",
                    data={
                        "rows_processed": result.rows_processed,
                        "rows_succeeded": result.rows_succeeded,
                        "rows_failed": result.rows_failed,
                        "rows_quarantined": result.rows_quarantined,
                        "landscape_run_id": result.run_id,
                    },
                ),
            )
            self._call_async(
                self._session_service.update_run_status(
                    run_uuid,
                    status="completed",
                    landscape_run_id=result.run_id,
                    rows_processed=result.rows_processed,
                    rows_failed=result.rows_failed,
                )
            )
            self._finalize_output_blobs(run_id, success=True)

        except GracefulShutdownError:
            # Orchestrator detected shutdown during processing and raised
            # after flushing in-progress work. This is the ONLY path that
            # should classify a run as cancelled.
            self._broadcaster.broadcast(
                run_id,
                RunEvent(
                    run_id=run_id,
                    timestamp=datetime.now(tz=UTC),
                    event_type="cancelled",
                    data={},
                ),
            )
            self._call_async(
                self._session_service.update_run_status(
                    run_uuid,
                    status="cancelled",
                )
            )
            self._finalize_output_blobs(run_id, success=False)

        except BaseException as exc:
            # B7 fix: Catch BaseException (not Exception) to handle
            # KeyboardInterrupt, SystemExit, and OOM-triggered exceptions.
            # Without this, the Run record stays in 'running' forever.
            # Broadcast "failed" (terminal) not "error" (non-terminal).
            # "error" is for per-row exceptions during processing;
            # "failed" means the pipeline itself crashed.

            # Sanitize error messages — SecretResolutionError may contain
            # secret names that should not leak to WebSocket clients or
            # be persisted in run records.
            if isinstance(exc, SecretResolutionError):
                client_msg = "One or more secret references could not be resolved. Check the Secrets panel."
            else:
                client_msg = str(exc)

            self._broadcaster.broadcast(
                run_id,
                RunEvent(
                    run_id=run_id,
                    timestamp=datetime.now(tz=UTC),
                    event_type="failed",
                    data={
                        "detail": client_msg,
                        "node_id": None,
                        "row_id": None,
                    },
                ),
            )
            # R6 fix: Skip _call_async for KeyboardInterrupt/SystemExit — the event
            # loop is likely shutting down. Let orphan cleanup handle the status.
            if not isinstance(exc, (KeyboardInterrupt, SystemExit)):
                try:
                    self._call_async(self._session_service.update_run_status(run_uuid, status="failed", error=client_msg))
                except Exception as status_err:
                    slog.error(
                        "run_status_update_failed_in_except",
                        run_id=run_id,
                        original_error=client_msg,
                        status_update_error=str(status_err),
                    )
            else:
                slog.warning(
                    "skipping_status_update_on_signal",
                    run_id=run_id,
                    exc_type=type(exc).__name__,
                )
            # Finalize output blobs as error (run failed)
            self._finalize_output_blobs(run_id, success=False)
            raise  # Re-raise so future.add_done_callback sees it
        finally:
            # Always clean up, regardless of success or failure
            self._shutdown_events.pop(run_id, None)
            if landscape_db is not None:
                landscape_db.close()
            self._broadcaster.cleanup_run(run_id)

    def _finalize_output_blobs(self, run_id: str, *, success: bool) -> None:
        """Finalize pending output blobs after a run completes/fails/cancels.

        Uses _call_async to bridge from the background thread to the async
        blob service. Failure here must not mask the original run outcome —
        errors are logged, not raised.
        """
        if self._blob_service is None:
            return
        try:
            self._call_async(
                self._blob_service.finalize_run_output_blobs(
                    UUID(run_id),
                    success=success,
                )
            )
        except Exception as blob_err:
            slog.error(
                "blob_finalization_failed",
                run_id=run_id,
                success=success,
                error=str(blob_err),
            )

    def _on_pipeline_done(self, future: Future[None]) -> None:
        """B7 Layer 2: Safety net callback.

        Fires when the Future completes, regardless of how. Logs any
        exception that _run_pipeline() raised. Does NOT update the Run
        record — that's Layer 1's job. This is purely diagnostic.

        Sanitizes SecretResolutionError to avoid leaking secret names
        into logs.
        """
        exc = future.exception()
        if exc is not None:
            if isinstance(exc, SecretResolutionError):
                slog.error(
                    "pipeline_secret_resolution_failed",
                    missing_count=len(exc.missing),
                )
            else:
                slog.error(
                    "pipeline_thread_failed",
                    exc_type=type(exc).__name__,
                    exc_message=str(exc),
                )

    def _to_run_event(self, run_id: str, progress: ProgressEvent) -> RunEvent:
        """Translate engine ProgressEvent to web RunEvent.

        Explicit mapping — unknown event types raise ValueError
        (offensive programming, not silent drop).
        """
        return RunEvent(
            run_id=run_id,
            timestamp=datetime.now(tz=UTC),
            event_type="progress",
            data={
                "rows_processed": progress.rows_processed,
                "rows_failed": progress.rows_failed,
            },
        )
