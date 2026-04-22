"""REST endpoints and WebSocket for pipeline execution.

POST /api/sessions/{session_id}/validate — dry-run validation
POST /api/sessions/{session_id}/execute — start background run
GET  /api/runs/{run_id}                 — run status
POST /api/runs/{run_id}/cancel          — cancel run
GET  /api/runs/{run_id}/results         — run results (terminal only)
WS   /ws/runs/{run_id}                  — live progress stream

All endpoints require authentication. Session-scoped endpoints verify
session ownership. Run-scoped endpoints verify run ownership via the
run's parent session.
"""

from __future__ import annotations

import asyncio
from typing import Literal, cast
from uuid import UUID

import pydantic
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import AuthenticationError, UserIdentity
from elspeth.web.auth.protocol import AuthProvider
from elspeth.web.blobs.protocol import BlobNotFoundError
from elspeth.web.config import WebSettings
from elspeth.web.execution.progress import ProgressBroadcaster
from elspeth.web.execution.protocol import ExecutionService, StateAccessError
from elspeth.web.execution.schemas import (
    RUN_STATUS_NON_TERMINAL_VALUES,
    CancelledData,
    CompletedData,
    FailedData,
    RunEvent,
    RunResultsResponse,
    RunStatusResponse,
    ValidationResult,
)
from elspeth.web.sessions.protocol import SessionServiceProtocol

slog = structlog.get_logger()


# ── Dependency providers (using app.state, matching existing pattern) ──


def _get_execution_service(request: Request) -> ExecutionService:
    return cast(ExecutionService, request.app.state.execution_service)


def _get_session_service(request: Request) -> SessionServiceProtocol:
    return cast(SessionServiceProtocol, request.app.state.session_service)


# ── Ownership verification helpers ────────────────────────────────────


async def _verify_session_ownership(session_id: UUID, user: UserIdentity, request: Request) -> None:
    """Verify the session exists and belongs to the current user.

    Returns 404 (not 403) to avoid leaking session existence (IDOR).
    Matches the pattern in sessions/routes.py.
    """
    session_service: SessionServiceProtocol = request.app.state.session_service
    settings: WebSettings = request.app.state.settings
    try:
        session = await session_service.get_session(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found") from None

    if session.user_id != user.user_id or session.auth_provider_type != settings.auth_provider:
        raise HTTPException(status_code=404, detail="Session not found")


async def _verify_run_ownership(run_id: UUID, user: UserIdentity, request: Request) -> None:
    """Verify the run exists and belongs to the current user's session.

    Looks up the run's parent session and checks ownership.
    Returns 404 (not 403) to avoid leaking run existence (IDOR).
    """
    session_service: SessionServiceProtocol = request.app.state.session_service
    settings: WebSettings = request.app.state.settings
    try:
        run = await session_service.get_run(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found") from None

    try:
        session = await session_service.get_session(run.session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found") from None

    if session.user_id != user.user_id or session.auth_provider_type != settings.auth_provider:
        raise HTTPException(status_code=404, detail="Run not found")


def _run_not_found_http() -> HTTPException:
    """Canonical IDOR-safe not-found response for run-scoped routes."""
    return HTTPException(status_code=404, detail="Run not found")


def _build_terminal_run_event(current: RunStatusResponse) -> RunEvent:
    """Synthesize a terminal RunEvent from authoritative run status.

    ``current`` comes from our session database and is therefore Tier 1.
    Impossible terminal states must raise rather than degrade into
    partial client-visible payloads.
    """
    if current.status == "completed":
        if current.landscape_run_id is None:
            raise RuntimeError(f"Completed run {current.run_id} has no landscape_run_id — Tier 1 anomaly (audit trail incomplete)")
        try:
            payload: CompletedData | FailedData | CancelledData = CompletedData(
                rows_processed=current.rows_processed,
                rows_succeeded=current.rows_succeeded,
                rows_failed=current.rows_failed,
                rows_routed=current.rows_routed,
                rows_quarantined=current.rows_quarantined,
                landscape_run_id=current.landscape_run_id,
            )
        except pydantic.ValidationError as exc:
            raise RuntimeError(
                f"Completed run {current.run_id} failed CompletedData validation — Tier 1 anomaly (audit trail inconsistent): {exc}"
            ) from exc
    elif current.status == "failed":
        if current.error is None:
            raise RuntimeError(f"Failed run {current.run_id} has no error message — Tier 1 anomaly (error column NULL on terminal failure)")
        payload = FailedData(
            detail=current.error,
            node_id=None,
        )
    elif current.status == "cancelled":
        payload = CancelledData(
            rows_processed=current.rows_processed,
            rows_failed=current.rows_failed,
            rows_routed=current.rows_routed,
        )
    else:
        raise RuntimeError(f"_build_terminal_run_event called for non-terminal status {current.status!r}")

    timestamp = current.finished_at or current.started_at
    if timestamp is None:
        raise RuntimeError(f"Terminal run {current.run_id} has no timestamps — Tier 1 anomaly (both finished_at and started_at are NULL)")
    event_type = cast(
        Literal["progress", "error", "completed", "cancelled", "failed"],
        current.status,
    )
    return RunEvent(
        run_id=current.run_id,
        timestamp=timestamp,
        event_type=event_type,
        data=payload,
    )


# ── Router ─────────────────────────────────────────────────────────────


def create_execution_router() -> APIRouter:
    """Create the execution router with REST + WebSocket endpoints."""
    router = APIRouter(tags=["execution"])

    # ── Session-scoped endpoints (validate, execute) ──────────────────

    @router.post(
        "/api/sessions/{session_id}/validate",
        response_model=ValidationResult,
    )
    async def validate_session_pipeline(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        service: ExecutionService = Depends(_get_execution_service),  # noqa: B008
    ) -> ValidationResult:
        """Dry-run validation using real engine code paths."""
        await _verify_session_ownership(session_id, user, request)
        result = await service.validate(session_id, user_id=user.user_id)
        return result

    @router.post(
        "/api/sessions/{session_id}/execute",
        status_code=202,
    )
    async def execute_pipeline(
        session_id: UUID,
        request: Request,
        state_id: UUID | None = None,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        service: ExecutionService = Depends(_get_execution_service),  # noqa: B008
    ) -> dict[str, str]:
        """Start a background pipeline run. Returns run_id immediately.

        RunAlreadyActiveError propagates to the app-level exception handler
        (Seam Contract D) which returns the canonical 409 envelope:
        {"detail": str(exc), "error_type": "run_already_active"}.
        """
        await _verify_session_ownership(session_id, user, request)
        try:
            run_id = await service.execute(session_id, state_id, user_id=user.user_id)
        except StateAccessError:
            # IDOR contract: the "state does not exist" and
            # "state belongs to another session" branches in the
            # service MUST surface here as byte-identical 404
            # responses.  Distinguishable ``detail`` strings would
            # let an authenticated attacker probe arbitrary UUIDs
            # against their own /execute and learn which ones exist
            # in OTHER users' sessions — the same oracle commit
            # e73a921a closed on ``send_message``.  If a future
            # refactor needs diagnostic precision, route it through
            # server-side audit/telemetry, never through the HTTP
            # response body.
            raise HTTPException(status_code=404, detail="State not found") from None
        except BlobNotFoundError:
            # IDOR contract (mirrors StateAccessError above): the
            # nonexistent-blob and cross-session-blob branches MUST
            # surface here as byte-identical 404 responses.  Before
            # this handler existed, nonexistent-blob propagated as a
            # 500 while cross-session-blob returned a 404 — the HTTP
            # status itself was a side channel.
            raise HTTPException(status_code=404, detail="Blob not found") from None
        except ValueError as exc:
            # Remaining ValueError sources are non-IDOR: the user's
            # OWN session having no composition state (when state_id
            # is None), source/sink path-allowlist rejections that
            # echo the caller's own input, and UUID parse errors on
            # malformed blob_ref strings.  These are not cross-user
            # oracles, so the diagnostic body is kept.
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return {"run_id": str(run_id)}

    # ── Run-scoped endpoints (status, cancel, results) ────────────────

    @router.get(
        "/api/runs/{run_id}",
        response_model=RunStatusResponse,
    )
    async def get_run_status(
        run_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        service: ExecutionService = Depends(_get_execution_service),  # noqa: B008
    ) -> RunStatusResponse:
        """Return current run status."""
        await _verify_run_ownership(run_id, user, request)
        try:
            return await service.get_status(run_id)
        except ValueError:
            raise _run_not_found_http() from None

    @router.post("/api/runs/{run_id}/cancel")
    async def cancel_run(
        run_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        service: ExecutionService = Depends(_get_execution_service),  # noqa: B008
    ) -> dict[str, str]:
        """Cancel a run. Idempotent on terminal runs."""
        await _verify_run_ownership(run_id, user, request)
        try:
            await service.cancel(run_id)
            status = await service.get_status(run_id)
        except ValueError:
            raise _run_not_found_http() from None
        return {"status": status.status}

    @router.get(
        "/api/runs/{run_id}/results",
        response_model=RunResultsResponse,
    )
    async def get_run_results(
        run_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        service: ExecutionService = Depends(_get_execution_service),  # noqa: B008
    ) -> RunResultsResponse:
        """Return final run results. 409 if run is not terminal."""
        await _verify_run_ownership(run_id, user, request)
        try:
            status = await service.get_status(run_id)
        except ValueError:
            raise _run_not_found_http() from None
        if status.status in RUN_STATUS_NON_TERMINAL_VALUES:
            raise HTTPException(
                status_code=409,
                detail=f"Run is still {status.status}",
            )
        # mypy can't narrow a Literal through frozenset membership — the
        # cast is safe because RUN_STATUS_NON_TERMINAL_VALUES is the exact
        # complement of RunResultsResponse's Literal values, enforced by a
        # module-load assertion in schemas.py.
        terminal_status = cast(Literal["completed", "failed", "cancelled"], status.status)
        return RunResultsResponse(
            run_id=status.run_id,
            status=terminal_status,
            rows_processed=status.rows_processed,
            rows_succeeded=status.rows_succeeded,
            rows_failed=status.rows_failed,
            rows_routed=status.rows_routed,
            rows_quarantined=status.rows_quarantined,
            landscape_run_id=status.landscape_run_id,
            error=status.error,
        )

    # ── WebSocket Endpoint ─────────────────────────────────────────────

    @router.websocket("/ws/runs/{run_id}")
    async def websocket_run_progress(
        websocket: WebSocket,
        run_id: str,
        token: str | None = None,
    ) -> None:
        """Stream RunEvent JSON payloads for a specific run.

        AC #12: Authentication via ?token=<jwt> query parameter.
        Close code 4001 on auth failure — client MUST NOT auto-reconnect
        on 4001 (token must be refreshed or user must re-authenticate).
        """
        broadcaster: ProgressBroadcaster = websocket.app.state.broadcaster
        auth_provider: AuthProvider = websocket.app.state.auth_provider
        service: ExecutionService = websocket.app.state.execution_service

        # Auth: validate JWT from query parameter
        if token is None:
            await websocket.close(code=4001, reason="Missing authentication token")
            return
        try:
            user = await auth_provider.authenticate(token)
        except AuthenticationError:
            await websocket.close(code=4001, reason="Invalid authentication token")
            return

        await websocket.accept()

        # IDOR protection: verify authenticated user owns this run's session
        try:
            run_ownership = await service.verify_run_ownership(user, run_id)
            if not run_ownership:
                await websocket.close(code=4004, reason="Run not found")
                return
        except ValueError:
            await websocket.close(code=4004, reason="Run not found")
            return

        # Subscribe BEFORE checking terminal status to close the race
        # window where a run finishes between get_status() and subscribe().
        # If subscribed first, any terminal event broadcast during the check
        # lands in the queue and won't be lost.
        queue = broadcaster.subscribe(run_id)
        try:
            # Seed: if the run already reached a terminal state before the
            # client connected (short runs, page refresh), send the terminal
            # status immediately and close.
            try:
                current = await service.get_status(UUID(run_id))
            except ValueError:
                await websocket.close(code=4004, reason="Run not found")
                return
            if current.status in ("completed", "failed", "cancelled"):
                event = _build_terminal_run_event(current)
                await websocket.send_json(event.model_dump(mode="json"))
                await websocket.close(code=1000)
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=60.0)
                except TimeoutError:
                    # Idle timeout — a terminal broadcast may have been missed.
                    # Re-check authoritative run status instead of sending an
                    # ad-hoc payload outside the RunEvent contract.
                    try:
                        current = await service.get_status(UUID(run_id))
                    except ValueError:
                        await websocket.close(code=4004, reason="Run not found")
                        break
                    if current.status in ("completed", "failed", "cancelled"):
                        terminal_event = _build_terminal_run_event(current)
                        await websocket.send_json(terminal_event.model_dump(mode="json"))
                        await websocket.close(code=1000)
                        break
                    continue
                await websocket.send_json(event.model_dump(mode="json"))
                # "error" events are non-terminal (per-row exceptions).
                # "completed", "cancelled", and "failed" are terminal.
                if event.event_type in ("completed", "cancelled", "failed"):
                    await websocket.close(code=1000)
                    break
        except WebSocketDisconnect:
            pass  # Client disconnected — fall through to finally
        except (ConnectionError, OSError) as exc:
            slog.error(
                "websocket_handler_error",
                run_id=run_id,
                error=str(exc),
            )
            try:
                await websocket.close(code=1011, reason="Internal server error")
            except (WebSocketDisconnect, ConnectionError, OSError) as close_err:
                slog.error("websocket_close_failed", run_id=run_id, error=str(close_err))
        finally:
            broadcaster.unsubscribe(run_id, queue)

    return router
