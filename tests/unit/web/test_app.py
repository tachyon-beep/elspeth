"""Tests for the FastAPI application factory."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import Depends
from starlette.testclient import TestClient

from elspeth.web.app import create_app
from elspeth.web.config import WebSettings
from elspeth.web.dependencies import get_settings


def _settings(tmp_path: Path, **overrides) -> WebSettings:
    """Create WebSettings with data_dir pointed at a temp directory."""
    defaults = {"data_dir": tmp_path}
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
        assert app.state.settings.port == 8000

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
        with pytest.raises(RuntimeError, match="WEB_CONCURRENCY=4 is not supported"):
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
