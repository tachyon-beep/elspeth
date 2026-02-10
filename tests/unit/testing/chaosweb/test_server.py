"""Tests for ChaosWeb HTTP server."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from elspeth.testing.chaosllm.config import LatencyConfig, MetricsConfig
from elspeth.testing.chaosweb.config import (
    ChaosWebConfig,
    WebErrorInjectionConfig,
)
from elspeth.testing.chaosweb.server import ChaosWebServer, create_app


@pytest.fixture
def tmp_metrics_db(tmp_path):
    """Create a temporary metrics database path."""
    return str(tmp_path / "test-metrics.db")


@pytest.fixture
def config(tmp_metrics_db):
    """Create a basic ChaosWeb config for testing."""
    return ChaosWebConfig(
        metrics=MetricsConfig(database=tmp_metrics_db),
        latency=LatencyConfig(base_ms=0, jitter_ms=0),
    )


@pytest.fixture
def server(config):
    """Create a ChaosWebServer instance for testing."""
    return ChaosWebServer(config)


@pytest.fixture
def client(config):
    """Create a test client for the ChaosWeb server."""
    app = create_app(config)
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check(self, client: TestClient) -> None:
        """Health endpoint returns 200 OK with status and run_id."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "run_id" in data

    def test_health_includes_burst_status(self, tmp_metrics_db: str) -> None:
        """Health endpoint includes burst mode status."""
        config = ChaosWebConfig(
            metrics=MetricsConfig(database=tmp_metrics_db),
            error_injection=WebErrorInjectionConfig(
                burst={"enabled": True, "interval_sec": 30, "duration_sec": 5},
            ),
        )
        app = create_app(config)
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "in_burst" in data


class TestPageEndpoint:
    """Tests for GET /{path} content serving."""

    def test_get_page_returns_html(self, client: TestClient) -> None:
        """GET /{path} returns HTML on success."""
        response = client.get("/articles/test")
        assert response.status_code == 200
        content = response.text.lower()
        assert "<html" in content

    def test_get_root_returns_html(self, client: TestClient) -> None:
        """GET / returns HTML on success."""
        response = client.get("/")
        assert response.status_code == 200


class TestAdminEndpoints:
    """Tests for admin endpoints."""

    def test_admin_config_get(self, client: TestClient) -> None:
        """GET /admin/config returns current configuration."""
        response = client.get("/admin/config")
        assert response.status_code == 200
        data = response.json()
        assert "error_injection" in data
        assert "content" in data
        assert "latency" in data

    def test_admin_stats(self, client: TestClient) -> None:
        """GET /admin/stats returns metrics stats."""
        response = client.get("/admin/stats")
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert "total_requests" in data
        assert data["total_requests"] == 0

    def test_admin_reset(self, client: TestClient) -> None:
        """POST /admin/reset resets metrics and returns new run_id."""
        # Make some requests first
        client.get("/page1")
        client.get("/page2")

        stats = client.get("/admin/stats").json()
        assert stats["total_requests"] == 2
        original_run_id = stats["run_id"]

        # Reset
        response = client.post("/admin/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reset"
        assert "new_run_id" in data
        assert data["new_run_id"] != original_run_id

        # Verify stats cleared
        stats = client.get("/admin/stats").json()
        assert stats["total_requests"] == 0

    def test_admin_export(self, client: TestClient) -> None:
        """GET /admin/export returns metrics export data."""
        client.get("/page1")

        response = client.get("/admin/export")
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert "requests" in data
        assert "timeseries" in data
        assert "config" in data


class TestErrorInjection:
    """Tests for error injection behavior via HTTP."""

    def test_rate_limit_injection(self, tmp_metrics_db: str) -> None:
        """100% rate_limit_pct returns 429."""
        config = ChaosWebConfig(
            metrics=MetricsConfig(database=tmp_metrics_db),
            latency=LatencyConfig(base_ms=0, jitter_ms=0),
            error_injection=WebErrorInjectionConfig(rate_limit_pct=100.0),
        )
        app = create_app(config)
        client = TestClient(app)

        response = client.get("/test")
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    def test_forbidden_injection(self, tmp_metrics_db: str) -> None:
        """100% forbidden_pct returns 403."""
        config = ChaosWebConfig(
            metrics=MetricsConfig(database=tmp_metrics_db),
            latency=LatencyConfig(base_ms=0, jitter_ms=0),
            error_injection=WebErrorInjectionConfig(forbidden_pct=100.0),
        )
        app = create_app(config)
        client = TestClient(app)

        response = client.get("/test")
        assert response.status_code == 403

    def test_not_found_injection(self, tmp_metrics_db: str) -> None:
        """100% not_found_pct returns 404."""
        config = ChaosWebConfig(
            metrics=MetricsConfig(database=tmp_metrics_db),
            latency=LatencyConfig(base_ms=0, jitter_ms=0),
            error_injection=WebErrorInjectionConfig(not_found_pct=100.0),
        )
        app = create_app(config)
        client = TestClient(app)

        response = client.get("/test")
        assert response.status_code == 404

    def test_redirect_loop_injection(self, tmp_metrics_db: str) -> None:
        """100% redirect_loop_pct returns 301 with Location containing hop params."""
        config = ChaosWebConfig(
            metrics=MetricsConfig(database=tmp_metrics_db),
            latency=LatencyConfig(base_ms=0, jitter_ms=0),
            error_injection=WebErrorInjectionConfig(redirect_loop_pct=100.0),
        )
        app = create_app(config)
        client = TestClient(app, follow_redirects=False)

        response = client.get("/test")
        assert response.status_code == 301
        location = response.headers["location"]
        assert "hop=" in location
        assert "max=" in location
        assert "target=" in location

    def test_ssrf_redirect_injection(self, tmp_metrics_db: str) -> None:
        """100% ssrf_redirect_pct returns 301 to private IP."""
        config = ChaosWebConfig(
            metrics=MetricsConfig(database=tmp_metrics_db),
            latency=LatencyConfig(base_ms=0, jitter_ms=0),
            error_injection=WebErrorInjectionConfig(ssrf_redirect_pct=100.0),
        )
        app = create_app(config)
        client = TestClient(app, follow_redirects=False)

        response = client.get("/test")
        assert response.status_code == 301
        location = response.headers["location"]
        # Should be a private/internal IP
        assert any(
            segment in location
            for segment in [
                "169.254.169.254",
                "192.168.",
                "10.0.",
                "172.16.",
                "127.0.0.1",
                "[::1]",
                "100.64.",
                "0.0.0.0",
                "metadata.google.internal",
                "2852039166",
                "[::ffff:",
            ]
        )


class TestRuntimeConfigUpdate:
    """Tests for runtime configuration updates."""

    def test_update_error_injection(self, server: ChaosWebServer) -> None:
        """Server can update error injection config at runtime."""
        assert server._error_injector._config.rate_limit_pct == 0.0

        server.update_config({"error_injection": {"rate_limit_pct": 50.0}})
        assert server._error_injector._config.rate_limit_pct == 50.0

    def test_update_via_fixture_pattern(self, tmp_metrics_db: str) -> None:
        """update_config changes behavior for subsequent requests."""
        config = ChaosWebConfig(
            metrics=MetricsConfig(database=tmp_metrics_db),
            latency=LatencyConfig(base_ms=0, jitter_ms=0),
        )
        server = ChaosWebServer(config)
        client = TestClient(server.app)

        # Initially no errors
        response = client.get("/test")
        assert response.status_code == 200

        # Enable 100% rate limiting
        server.update_config({"error_injection": {"rate_limit_pct": 100.0}})

        response = client.get("/test")
        assert response.status_code == 429


class TestMetricsRecording:
    """Tests for metrics recording."""

    def test_successful_request_recorded(self, client: TestClient) -> None:
        """Successful requests are recorded in metrics."""
        client.get("/page1")

        response = client.get("/admin/stats")
        data = response.json()
        assert data["total_requests"] == 1
        assert data["requests_by_outcome"].get("success", 0) == 1

    def test_error_request_recorded(self, tmp_metrics_db: str) -> None:
        """Error responses are recorded in metrics."""
        config = ChaosWebConfig(
            metrics=MetricsConfig(database=tmp_metrics_db),
            latency=LatencyConfig(base_ms=0, jitter_ms=0),
            error_injection=WebErrorInjectionConfig(rate_limit_pct=100.0),
        )
        app = create_app(config)
        client = TestClient(app)

        client.get("/test")

        stats = client.get("/admin/stats").json()
        assert stats["total_requests"] == 1
        assert stats["requests_by_outcome"].get("error_injected", 0) == 1

    def test_stats_increment_after_multiple_requests(self, client: TestClient) -> None:
        """Stats count increases with each request."""
        for i in range(5):
            client.get(f"/page{i}")

        stats = client.get("/admin/stats").json()
        assert stats["total_requests"] == 5


class TestChaosWebServer:
    """Tests for the ChaosWebServer class."""

    def test_server_creation(self, config: ChaosWebConfig) -> None:
        """ChaosWebServer can be created from config."""
        server = ChaosWebServer(config)
        assert server.app is not None
        assert server.run_id is not None

    def test_server_reset(self, server: ChaosWebServer) -> None:
        """Server reset creates new run_id."""
        original_run_id = server.run_id
        new_run_id = server.reset()
        assert new_run_id != original_run_id
        assert server.run_id == new_run_id

    def test_get_stats(self, server: ChaosWebServer) -> None:
        """Server get_stats returns metrics dict."""
        stats = server.get_stats()
        assert "run_id" in stats
        assert "total_requests" in stats

    def test_export_metrics(self, server: ChaosWebServer) -> None:
        """Server export_metrics returns complete data."""
        data = server.export_metrics()
        assert "run_id" in data
        assert "requests" in data
        assert "config" in data


class TestCreateApp:
    """Tests for the create_app convenience function."""

    def test_create_app_returns_starlette(self, config: ChaosWebConfig) -> None:
        """create_app returns a Starlette application."""
        app = create_app(config)
        assert app is not None

    def test_create_app_stores_server_on_state(self, config: ChaosWebConfig) -> None:
        """create_app stores ChaosWebServer on app.state.server."""
        app = create_app(config)
        assert hasattr(app.state, "server")
        assert isinstance(app.state.server, ChaosWebServer)

    def test_create_app_functional(self, config: ChaosWebConfig) -> None:
        """App created by create_app handles requests."""
        app = create_app(config)
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
