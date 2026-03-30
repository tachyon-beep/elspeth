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
from typing import cast
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import AuthenticationError, UserIdentity
from elspeth.web.execution.protocol import ExecutionService
from elspeth.web.execution.schemas import RunResultsResponse, RunStatusResponse, ValidationResult
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
    settings = request.app.state.settings
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
    settings = request.app.state.settings
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
        run_id = await service.execute(session_id, state_id, user_id=user.user_id)
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
        return await service.get_status(run_id)

    @router.post("/api/runs/{run_id}/cancel")
    async def cancel_run(
        run_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        service: ExecutionService = Depends(_get_execution_service),  # noqa: B008
    ) -> dict[str, str]:
        """Cancel a run. Idempotent on terminal runs."""
        await _verify_run_ownership(run_id, user, request)
        await service.cancel(run_id)
        status = await service.get_status(run_id)
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
        status = await service.get_status(run_id)
        if status.status in ("pending", "running"):
            raise HTTPException(
                status_code=409,
                detail=f"Run is still {status.status}",
            )
        return RunResultsResponse(
            run_id=status.run_id,
            status=status.status,
            rows_processed=status.rows_processed,
            rows_failed=status.rows_failed,
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
        broadcaster = websocket.app.state.broadcaster
        auth_provider = websocket.app.state.auth_provider
        service: ExecutionService = websocket.app.state.execution_service

        # Auth: validate JWT from query parameter
        if token is None:
            await websocket.close(code=4001, reason="Missing authentication token")
            return
        try:
            user = await auth_provider.authenticate(token)
        except (AuthenticationError, Exception):
            await websocket.close(code=4001, reason="Invalid authentication token")
            return

        await websocket.accept()

        # IDOR protection: verify authenticated user owns this run's session
        try:
            run_ownership = await service.verify_run_ownership(user, run_id)
            if not run_ownership:
                await websocket.close(code=4004, reason="Run not found")
                return
        except Exception:
            await websocket.close(code=4004, reason="Run not found")
            return

        queue = broadcaster.subscribe(run_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=60.0)
                except TimeoutError:
                    # Heartbeat timeout — pipeline may have crashed without terminal event.
                    try:
                        await websocket.send_json({"type": "heartbeat"})
                    except Exception:
                        break  # Client disconnected
                    continue
                await websocket.send_json(event.model_dump(mode="json"))
                # "error" events are non-terminal (per-row exceptions).
                # "completed", "cancelled", and "failed" are terminal.
                if event.event_type in ("completed", "cancelled", "failed"):
                    await websocket.close(code=1000)
                    break
        except WebSocketDisconnect:
            pass  # Client disconnected — fall through to finally
        except Exception as exc:
            slog.error(
                "websocket_handler_error",
                run_id=run_id,
                error=str(exc),
            )
            try:
                await websocket.close(code=1011, reason="Internal server error")
            except Exception as close_err:
                slog.error("websocket_close_failed", run_id=run_id, error=str(close_err))
        finally:
            broadcaster.unsubscribe(run_id, queue)

    return router
