"""Tests for the FastAPI application factory."""

from __future__ import annotations

from fastapi import Depends
from starlette.testclient import TestClient

from elspeth.web.app import create_app
from elspeth.web.config import WebSettings
from elspeth.web.dependencies import get_settings


class TestCreateApp:
    """Tests for create_app()."""

    def test_returns_fastapi_instance_with_correct_title(self) -> None:
        app = create_app(WebSettings())
        assert app.title == "ELSPETH Web"

    def test_returns_fastapi_instance_with_correct_version(self) -> None:
        app = create_app(WebSettings())
        assert app.version == "0.1.0"

    def test_default_settings_when_none_passed(self) -> None:
        app = create_app()
        assert app.state.settings.port == 8000

    def test_settings_stored_on_app_state(self) -> None:
        settings = WebSettings(port=9999)
        app = create_app(settings)
        assert app.state.settings is settings
        assert app.state.settings.port == 9999


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_200(self) -> None:
        app = create_app(WebSettings())
        client = TestClient(app)
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self) -> None:
        app = create_app(WebSettings())
        client = TestClient(app)
        response = client.get("/api/health")
        assert response.json() == {"status": "ok"}


class TestCORSMiddleware:
    """Tests that CORS middleware is configured."""

    def test_cors_allows_configured_origin(self) -> None:
        settings = WebSettings(cors_origins=["http://localhost:5173"])
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

    def test_cors_rejects_unconfigured_origin(self) -> None:
        settings = WebSettings(cors_origins=["http://localhost:5173"])
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

    def test_get_settings_returns_app_settings(self) -> None:
        settings = WebSettings(port=4242)
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

    def test_catalog_service_on_app_state(self) -> None:
        app = create_app(WebSettings())
        assert hasattr(app.state, "catalog_service")

    def test_catalog_sources_endpoint_reachable(self) -> None:
        app = create_app(WebSettings())
        client = TestClient(app)
        response = client.get("/api/catalog/sources")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
