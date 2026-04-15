"""Tests for the FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends
from starlette.testclient import TestClient

from elspeth.web.app import _periodic_orphan_cleanup, _settings_from_env, create_app
from elspeth.web.config import WebSettings
from elspeth.web.dependencies import get_settings


def _settings(tmp_path: Path, **overrides) -> WebSettings:
    """Create WebSettings with data_dir pointed at a temp directory."""
    defaults = {
        "data_dir": tmp_path,
        "composer_max_composition_turns": 15,
        "composer_max_discovery_turns": 10,
        "composer_timeout_seconds": 85.0,
        "composer_rate_limit_per_minute": 10,
    }
    defaults.update(overrides)
    return WebSettings(**defaults)


class TestCreateApp:
    """Tests for create_app()."""

    def test_returns_fastapi_instance_with_correct_title(self, tmp_path) -> None:
        app = create_app(_settings(tmp_path))
        assert app.title == "ELSPETH Web"

    def test_returns_fastapi_instance_with_correct_version(self, tmp_path) -> None:
        app = create_app(_settings(tmp_path))
        assert app.version == "0.1.0"

    def test_default_settings_when_none_passed(self, tmp_path) -> None:
        # create_app(None) uses WebSettings() which defaults data_dir to "data".
        # That won't exist in tests, so we pass explicit settings instead.
        app = create_app(_settings(tmp_path))
        assert app.state.settings.port == 8451

    def test_settings_stored_on_app_state(self, tmp_path) -> None:
        settings = _settings(tmp_path, port=9999)
        app = create_app(settings)
        assert app.state.settings is settings
        assert app.state.settings.port == 9999


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_200(self, tmp_path) -> None:
        app = create_app(_settings(tmp_path))
        client = TestClient(app)
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self, tmp_path) -> None:
        app = create_app(_settings(tmp_path))
        client = TestClient(app)
        response = client.get("/api/health")
        assert response.json() == {"status": "ok"}


class TestCORSMiddleware:
    """Tests that CORS middleware is configured."""

    def test_cors_allows_configured_origin(self, tmp_path) -> None:
        settings = _settings(tmp_path, cors_origins=["http://localhost:5173"])
        app = create_app(settings)
        client = TestClient(app)
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_cors_rejects_unconfigured_origin(self, tmp_path) -> None:
        settings = _settings(tmp_path, cors_origins=["http://localhost:5173"])
        app = create_app(settings)
        client = TestClient(app)
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Starlette CORS middleware omits the header for disallowed origins
        assert "access-control-allow-origin" not in response.headers


class TestGetSettingsDependency:
    """Tests for get_settings() dependency provider."""

    def test_get_settings_returns_app_settings(self, tmp_path) -> None:
        settings = _settings(tmp_path, port=4242)
        app = create_app(settings)

        # Remove the SPA catch-all mount so the dynamically added test
        # route is reachable (the SPA mount at "/" with html=True serves
        # index.html for any unmatched path, swallowing late-added routes).
        app.routes[:] = [r for r in app.routes if getattr(r, "name", None) != "spa"]

        @app.get("/api/_test_settings")
        async def _test_endpoint(s: WebSettings = Depends(get_settings)) -> dict[str, int]:  # noqa: B008
            return {"port": s.port}

        client = TestClient(app)
        response = client.get("/api/_test_settings")
        assert response.status_code == 200
        assert response.json() == {"port": 4242}


class TestCatalogWiring:
    """Tests that create_app() wires the catalog service into app state."""

    def test_catalog_service_on_app_state(self, tmp_path) -> None:
        app = create_app(_settings(tmp_path))
        assert app.state.catalog_service is not None

    def test_catalog_sources_endpoint_reachable(self, tmp_path) -> None:
        app = create_app(_settings(tmp_path))
        client = TestClient(app)
        response = client.get("/api/catalog/sources")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0


class TestAuthWiring:
    """Tests that create_app() wires auth provider into app state."""

    def test_auth_provider_on_app_state(self, tmp_path) -> None:
        app = create_app(_settings(tmp_path))
        assert app.state.auth_provider is not None

    def test_auth_routes_registered(self, tmp_path) -> None:
        app = create_app(_settings(tmp_path))
        client = TestClient(app)
        # /api/auth/config is a public endpoint
        response = client.get("/api/auth/config")
        assert response.status_code == 200


class TestSessionWiring:
    """Tests that create_app() wires session service into app state."""

    def test_session_service_on_app_state(self, tmp_path) -> None:
        app = create_app(_settings(tmp_path))
        assert app.state.session_service is not None

    def test_session_routes_registered(self, tmp_path) -> None:
        app = create_app(_settings(tmp_path))
        client = TestClient(app)
        # Without auth, should get 401
        response = client.get("/api/sessions")
        assert response.status_code == 401


class TestMultiWorkerEnforcement:
    """W10 -> R6: Hard-enforce single worker for WebSocket support."""

    @patch.dict("os.environ", {"WEB_CONCURRENCY": "4"})
    def test_raises_on_multi_worker(self, tmp_path) -> None:
        """Application factory rejects WEB_CONCURRENCY > 1."""
        with pytest.raises(RuntimeError, match=r"WEB_CONCURRENCY=4\) but is not supported"):
            create_app(_settings(tmp_path))

    @patch.dict("os.environ", {"WEB_CONCURRENCY": "1"})
    def test_single_worker_accepted(self, tmp_path) -> None:
        """No error when running with a single worker."""
        app = create_app(_settings(tmp_path))
        assert app is not None


class TestExecutionWiring:
    """Tests that create_app() wires execution routes."""

    def test_execution_routes_registered(self, tmp_path) -> None:
        app = create_app(_settings(tmp_path))
        route_paths = [path for route in app.routes if isinstance(path := getattr(route, "path", None), str)]
        assert "/api/sessions/{session_id}/validate" in route_paths
        assert "/api/sessions/{session_id}/execute" in route_paths
        assert "/api/runs/{run_id}" in route_paths
        assert "/api/runs/{run_id}/cancel" in route_paths
        assert "/ws/runs/{run_id}" in route_paths


class TestSettingsFromEnv:
    """Tests for _settings_from_env() environment variable parsing."""

    @pytest.fixture(autouse=True)
    def _set_composer_env(self, monkeypatch) -> None:
        """Provide required composer fields via env vars for _settings_from_env()."""
        monkeypatch.setenv("ELSPETH_WEB__COMPOSER_MAX_COMPOSITION_TURNS", "15")
        monkeypatch.setenv("ELSPETH_WEB__COMPOSER_MAX_DISCOVERY_TURNS", "10")
        monkeypatch.setenv("ELSPETH_WEB__COMPOSER_TIMEOUT_SECONDS", "85.0")
        monkeypatch.setenv("ELSPETH_WEB__COMPOSER_RATE_LIMIT_PER_MINUTE", "10")

    def test_parses_json_tuple_values(self, monkeypatch) -> None:
        """JSON-encoded lists are converted to tuples for tuple-typed fields."""
        monkeypatch.setenv("ELSPETH_WEB__CORS_ORIGINS", '["https://app.example.com"]')
        settings = _settings_from_env()
        assert settings.cors_origins == ("https://app.example.com",)

    def test_parses_json_list_with_multiple_items(self, monkeypatch) -> None:
        monkeypatch.setenv(
            "ELSPETH_WEB__CORS_ORIGINS",
            '["https://a.example.com", "https://b.example.com"]',
        )
        settings = _settings_from_env()
        assert settings.cors_origins == ("https://a.example.com", "https://b.example.com")

    def test_plain_string_passes_through(self, monkeypatch) -> None:
        monkeypatch.setenv("ELSPETH_WEB__HOST", "127.0.0.1")
        settings = _settings_from_env()
        assert settings.host == "127.0.0.1"

    def test_json_integer_parsed(self, monkeypatch) -> None:
        monkeypatch.setenv("ELSPETH_WEB__PORT", "9090")
        settings = _settings_from_env()
        assert settings.port == 9090
        assert isinstance(settings.port, int)

    def test_server_secret_allowlist_from_json(self, monkeypatch) -> None:
        monkeypatch.setenv("ELSPETH_WEB__SERVER_SECRET_ALLOWLIST", '["MY_KEY"]')
        settings = _settings_from_env()
        assert settings.server_secret_allowlist == ("MY_KEY",)


class TestPeriodicOrphanCleanup:
    """Tests for _periodic_orphan_cleanup background task."""

    @pytest.mark.asyncio
    async def test_calls_cancel_all_with_max_age(self) -> None:
        """Periodic cleanup passes max_age_seconds (not None) to cancel_all_orphaned_runs."""
        mock_service = AsyncMock()
        mock_service.cancel_all_orphaned_runs.return_value = 0
        mock_exec = MagicMock()
        mock_exec.get_live_run_ids.return_value = frozenset()

        task = asyncio.create_task(_periodic_orphan_cleanup(mock_service, mock_exec, interval_seconds=0, max_age_seconds=900))
        # Let the loop run long enough for at least one call
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        mock_service.cancel_all_orphaned_runs.assert_called_with(
            max_age_seconds=900,
            exclude_run_ids=frozenset(),
            reason="Orphaned by periodic cleanup — no active executor thread",
        )

    @pytest.mark.asyncio
    async def test_continues_after_exception(self) -> None:
        """Periodic cleanup logs errors but keeps running."""
        mock_service = AsyncMock()
        mock_service.cancel_all_orphaned_runs.side_effect = [
            RuntimeError("db connection lost"),
            2,  # recovers on second call
        ]
        mock_exec = MagicMock()
        mock_exec.get_live_run_ids.return_value = frozenset()

        task = asyncio.create_task(_periodic_orphan_cleanup(mock_service, mock_exec, interval_seconds=0, max_age_seconds=3600))
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert mock_service.cancel_all_orphaned_runs.call_count >= 2

    @pytest.mark.asyncio
    async def test_cancellation_is_clean(self) -> None:
        """Task cancellation doesn't raise or leave dangling state."""
        mock_service = AsyncMock()
        mock_service.cancel_all_orphaned_runs.return_value = 0
        mock_exec = MagicMock()
        mock_exec.get_live_run_ids.return_value = frozenset()

        task = asyncio.create_task(_periodic_orphan_cleanup(mock_service, mock_exec, interval_seconds=10, max_age_seconds=3600))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_excludes_live_run_ids(self) -> None:
        """Periodic cleanup passes live run IDs as exclude_run_ids."""
        mock_service = AsyncMock()
        mock_service.cancel_all_orphaned_runs.return_value = 0
        mock_exec = MagicMock()
        live_ids = frozenset({"run-1", "run-2"})
        mock_exec.get_live_run_ids.return_value = live_ids

        task = asyncio.create_task(_periodic_orphan_cleanup(mock_service, mock_exec, interval_seconds=0, max_age_seconds=3600))
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        mock_exec.get_live_run_ids.assert_called()
        mock_service.cancel_all_orphaned_runs.assert_called_with(
            max_age_seconds=3600,
            exclude_run_ids=live_ids,
            reason="Orphaned by periodic cleanup — no active executor thread",
        )


class TestDataDirCreation:
    """Bug 4: create_app() must create data_dir before any DB access."""

    def test_create_app_creates_nonexistent_data_dir(self, tmp_path) -> None:
        fresh_dir = tmp_path / "nonexistent" / "nested"
        settings = WebSettings(
            data_dir=fresh_dir,
            composer_max_composition_turns=15,
            composer_max_discovery_turns=10,
            composer_timeout_seconds=85.0,
            composer_rate_limit_per_minute=10,
        )
        create_app(settings)
        assert fresh_dir.exists()
        assert fresh_dir.is_dir()


class TestValidationErrorRedaction:
    """SECURITY: 422 responses must never echo sensitive request body values.

    The global RequestValidationError handler registered in create_app()
    allowlists only {type, loc, msg} — stripping ``input``, ``ctx``, and
    ``url`` to prevent credential leakage on any route.

    These tests exercise the *real* handler wired by create_app(), unlike the
    unit tests in test_routes.py which register a local duplicate.
    """

    _SAFE_KEYS = frozenset({"type", "loc", "msg"})

    @staticmethod
    def _authed_client(tmp_path: Path) -> TestClient:
        """Build a TestClient against create_app() with auth bypassed."""
        from elspeth.web.auth.middleware import get_current_user
        from elspeth.web.auth.models import UserIdentity

        app = create_app(_settings(tmp_path))

        identity = UserIdentity(user_id="test-user", username="test-user")

        async def _mock_user() -> UserIdentity:
            return identity

        app.dependency_overrides[get_current_user] = _mock_user
        return TestClient(app, raise_server_exceptions=False)

    def test_secrets_route_redacts_input(self, tmp_path) -> None:
        """POST /api/secrets with wrong value type must not echo the value."""
        client = self._authed_client(tmp_path)
        resp = client.post(
            "/api/secrets",
            json={"name": "API_KEY", "value": {"nested": "super-secret-hunter2"}},
        )
        assert resp.status_code == 422
        body = resp.json()
        body_text = resp.text
        assert "super-secret-hunter2" not in body_text
        for error in body["detail"]:
            assert set(error.keys()) <= self._SAFE_KEYS

    def test_redaction_preserves_error_structure(self, tmp_path) -> None:
        """Redacted errors retain type, loc, msg for client debugging."""
        client = self._authed_client(tmp_path)
        resp = client.post(
            "/api/secrets",
            json={"name": "API_KEY", "value": {"bad": "type"}},
        )
        assert resp.status_code == 422
        errors = resp.json()["detail"]
        assert len(errors) > 0
        for error in errors:
            assert "type" in error
            assert "loc" in error
            assert "msg" in error

    def test_redaction_strips_input_ctx_url_keys(self, tmp_path) -> None:
        """Forbidden keys (input, ctx, url) must never appear in 422 detail."""
        client = self._authed_client(tmp_path)
        resp = client.post(
            "/api/secrets",
            json={"name": "API_KEY", "value": 12345},
        )
        assert resp.status_code == 422
        _FORBIDDEN_KEYS = {"input", "ctx", "url"}
        for error in resp.json()["detail"]:
            assert not _FORBIDDEN_KEYS & set(error.keys()), f"Forbidden keys leaked in 422 response: {_FORBIDDEN_KEYS & set(error.keys())}"

    def test_sessions_message_route_redacts_input(self, tmp_path) -> None:
        """POST to a session message route with invalid body must not echo content."""
        client = self._authed_client(tmp_path)
        # Send a message with state_id as a non-UUID string — triggers 422
        resp = client.post(
            "/api/sessions/00000000-0000-0000-0000-000000000000/messages",
            json={"content": "leaked-password-value", "state_id": "not-a-uuid"},
        )
        assert resp.status_code == 422
        body_text = resp.text
        assert "leaked-password-value" not in body_text
        for error in resp.json()["detail"]:
            assert set(error.keys()) <= self._SAFE_KEYS
