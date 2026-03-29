"""Tests for execution REST endpoints and WebSocket.

Routes delegate to ExecutionServiceImpl — these tests verify HTTP
semantics, status codes, and request/response contracts.

The app factory's real wiring is bypassed by setting app.state.*
directly with mocks, matching the dependency injection pattern used
by the route handlers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from elspeth.web.execution.schemas import (
    RunStatusResponse,
    ValidationCheck,
    ValidationResult,
)
from elspeth.web.sessions.protocol import RunAlreadyActiveError

# ── Helpers ───────────────────────────────────────────────────────────

_TEST_USER_ID = "test-user-123"


def _create_test_app(
    execution_service: MagicMock | None = None,
    broadcaster: MagicMock | None = None,
) -> FastAPI:
    """Create a minimal FastAPI app with execution routes wired.

    Bypasses the full create_app() to avoid real DB setup, auth provider
    construction, and lifespan side effects. Overrides get_current_user
    to return a fake user for auth. Sets up mock session_service for
    ownership verification.
    """
    from elspeth.web.auth.middleware import get_current_user
    from elspeth.web.auth.models import UserIdentity
    from elspeth.web.execution.routes import create_execution_router

    app = FastAPI()
    app.state.execution_service = execution_service or MagicMock()
    app.state.broadcaster = broadcaster or MagicMock()
    app.state.auth_provider = MagicMock()

    # Mock session_service for ownership checks
    mock_session_service = MagicMock()
    mock_session = MagicMock()
    mock_session.user_id = _TEST_USER_ID
    mock_session.auth_provider_type = "local"
    mock_session_service.get_session = AsyncMock(return_value=mock_session)
    mock_session_service.get_run = AsyncMock(return_value=MagicMock(session_id=uuid4()))
    app.state.session_service = mock_session_service

    # Mock settings for ownership checks
    mock_settings = MagicMock()
    mock_settings.auth_provider = "local"
    app.state.settings = mock_settings

    # Override auth dependency to return a fake user
    fake_user = UserIdentity(user_id=_TEST_USER_ID, username="testuser")
    app.dependency_overrides[get_current_user] = lambda: fake_user

    app.include_router(create_execution_router())

    # Register app-level exception handler matching Seam Contract D
    from fastapi import Request as FastAPIRequest
    from fastapi.responses import JSONResponse

    from elspeth.web.sessions.protocol import RunAlreadyActiveError

    @app.exception_handler(RunAlreadyActiveError)
    async def handle_run_already_active(request: FastAPIRequest, exc: RunAlreadyActiveError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc), "error_type": "run_already_active"},
        )

    return app


# ── REST Endpoint Tests ───────────────────────────────────────────────


class TestValidateEndpoint:
    """POST /api/sessions/{session_id}/validate"""

    @pytest.mark.asyncio
    async def test_valid_pipeline_returns_200(self) -> None:
        svc = MagicMock()
        svc.validate = AsyncMock(
            return_value=ValidationResult(
                is_valid=True,
                checks=[
                    ValidationCheck(name="settings_load", passed=True, detail="OK"),
                ],
                errors=[],
            )
        )
        app = _create_test_app(execution_service=svc)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/sessions/{uuid4()}/validate")
            assert resp.status_code == 200
            body = resp.json()
            assert body["is_valid"] is True
            assert len(body["checks"]) == 1

    @pytest.mark.asyncio
    async def test_validate_delegates_to_service(self) -> None:
        """AC #16: validate route delegates to service.validate()."""
        svc = MagicMock()
        svc.validate = AsyncMock(return_value=ValidationResult(is_valid=True, checks=[], errors=[]))
        app = _create_test_app(execution_service=svc)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/sessions/{uuid4()}/validate")
            assert resp.status_code == 200
            svc.validate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_pipeline_returns_200_with_errors(self) -> None:
        svc = MagicMock()
        svc.validate = AsyncMock(
            return_value=ValidationResult(
                is_valid=False,
                checks=[
                    ValidationCheck(name="settings_load", passed=False, detail="Bad YAML"),
                ],
                errors=[],
            )
        )
        app = _create_test_app(execution_service=svc)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/sessions/{uuid4()}/validate")
            assert resp.status_code == 200
            body = resp.json()
            assert body["is_valid"] is False


class TestExecuteEndpoint:
    """POST /api/sessions/{session_id}/execute"""

    @pytest.mark.asyncio
    async def test_execute_returns_202_with_run_id(self) -> None:
        expected_run_id = uuid4()
        svc = MagicMock()
        svc.execute = AsyncMock(return_value=expected_run_id)
        app = _create_test_app(execution_service=svc)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/sessions/{uuid4()}/execute")
            assert resp.status_code == 202
            body = resp.json()
            assert body["run_id"] == str(expected_run_id)

    @pytest.mark.asyncio
    async def test_execute_with_active_run_returns_409(self) -> None:
        svc = MagicMock()
        svc.execute = AsyncMock(side_effect=RunAlreadyActiveError("Already active"))
        app = _create_test_app(execution_service=svc)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/sessions/{uuid4()}/execute")
            assert resp.status_code == 409
            body = resp.json()
            # Seam Contract D: flat envelope, not nested
            assert body["error_type"] == "run_already_active"
            assert "detail" in body


class TestRunStatusEndpoint:
    """GET /api/runs/{run_id}"""

    @pytest.mark.asyncio
    async def test_status_returns_200(self) -> None:
        run_id = uuid4()
        svc = MagicMock()
        svc.get_status = AsyncMock(
            return_value=RunStatusResponse(
                run_id=str(run_id),
                status="completed",
                started_at=datetime.now(tz=UTC),
                finished_at=datetime.now(tz=UTC),
                rows_processed=10,
                rows_failed=0,
                error=None,
                landscape_run_id="lscape-1",
            )
        )
        app = _create_test_app(execution_service=svc)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/runs/{run_id}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "completed"
            assert body["rows_processed"] == 10


class TestCancelEndpoint:
    """POST /api/runs/{run_id}/cancel"""

    @pytest.mark.asyncio
    async def test_cancel_returns_200(self) -> None:
        run_id = uuid4()
        svc = MagicMock()
        svc.cancel = AsyncMock()
        svc.get_status = AsyncMock(
            return_value=RunStatusResponse(
                run_id=str(run_id),
                status="cancelled",
                started_at=datetime.now(tz=UTC),
                finished_at=datetime.now(tz=UTC),
                rows_processed=5,
                rows_failed=0,
                error=None,
                landscape_run_id="lscape-1",
            )
        )
        app = _create_test_app(execution_service=svc)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/runs/{run_id}/cancel")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "cancelled"


class TestResultsEndpoint:
    """GET /api/runs/{run_id}/results"""

    @pytest.mark.asyncio
    async def test_results_returns_200_for_completed_run(self) -> None:
        run_id = uuid4()
        svc = MagicMock()
        svc.get_status = AsyncMock(
            return_value=RunStatusResponse(
                run_id=str(run_id),
                status="completed",
                started_at=datetime.now(tz=UTC),
                finished_at=datetime.now(tz=UTC),
                rows_processed=10,
                rows_failed=0,
                error=None,
                landscape_run_id="lscape-1",
            )
        )
        app = _create_test_app(execution_service=svc)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/runs/{run_id}/results")
            assert resp.status_code == 200
            body = resp.json()
            assert body["rows_processed"] == 10
            assert body["landscape_run_id"] == "lscape-1"

    @pytest.mark.asyncio
    async def test_results_returns_409_for_running(self) -> None:
        run_id = uuid4()
        svc = MagicMock()
        svc.get_status = AsyncMock(
            return_value=RunStatusResponse(
                run_id=str(run_id),
                status="running",
                started_at=datetime.now(tz=UTC),
                finished_at=None,
                rows_processed=5,
                rows_failed=0,
                error=None,
                landscape_run_id=None,
            )
        )
        app = _create_test_app(execution_service=svc)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/runs/{run_id}/results")
            assert resp.status_code == 409
