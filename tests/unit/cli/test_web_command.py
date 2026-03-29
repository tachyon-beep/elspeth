"""Tests for the elspeth web CLI command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from elspeth.cli import app

runner = CliRunner()


class TestWebCommandImportGuard:
    """Tests for the [webui] import guard."""

    def test_missing_uvicorn_prints_install_instruction(self) -> None:
        with patch.dict("sys.modules", {"uvicorn": None}):
            result = runner.invoke(app, ["web"])
        assert result.exit_code == 1
        assert "[webui]" in result.output

    def test_missing_uvicorn_exits_code_1(self) -> None:
        with patch.dict("sys.modules", {"uvicorn": None}):
            result = runner.invoke(app, ["web"])
        assert result.exit_code == 1


class TestWebCommandHappyPath:
    """Tests for the web command when [webui] is installed.

    Note: WebSettings validates that non-local hosts require a non-default
    secret_key (_enforce_secret_key_in_production). Tests using --host 0.0.0.0
    must also set ELSPETH_WEB__SECRET_KEY to pass validation.
    """

    def test_calls_uvicorn_run_with_factory_true(self) -> None:
        """Use default host (127.0.0.1) with custom port — avoids secret_key guard."""
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            runner.invoke(app, ["web", "--port", "9999"])

        mock_uvicorn.run.assert_called_once()
        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs.kwargs.get("factory") is True or call_kwargs[1].get("factory") is True

    def test_passes_correct_host_and_port_to_uvicorn(self) -> None:
        """Use localhost with custom port — verifies host and port forwarding."""
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            runner.invoke(app, ["web", "--port", "9999", "--host", "127.0.0.1"])

        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs.kwargs.get("host") == "127.0.0.1" or call_kwargs[1].get("host") == "127.0.0.1"
        assert call_kwargs.kwargs.get("port") == 9999 or call_kwargs[1].get("port") == 9999

    def test_non_local_host_with_default_secret_key_fails(self) -> None:
        """0.0.0.0 with default secret_key triggers the production guard."""
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            result = runner.invoke(app, ["web", "--host", "0.0.0.0"])

        assert result.exit_code != 0
        mock_uvicorn.run.assert_not_called()

    def test_uses_create_app_factory_string(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            runner.invoke(app, ["web"])

        call_args = mock_uvicorn.run.call_args
        assert call_args[0][0] == "elspeth.web.app:create_app"

    def test_reload_flag_forwarded(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            runner.invoke(app, ["web", "--reload"])

        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs.kwargs.get("reload") is True or call_kwargs[1].get("reload") is True

    def test_default_host_requires_no_secret_key(self) -> None:
        """Default host (127.0.0.1) should work with the default secret_key."""
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            result = runner.invoke(app, ["web"])

        assert result.exit_code == 0
        mock_uvicorn.run.assert_called_once()


class TestWebCommandAuthWarning:
    """Tests for --auth non-default handling.

    Since Sub-2, OIDC/Entra auth providers require their configuration fields
    (oidc_issuer, oidc_audience, etc.). The CLI validates these via WebSettings
    and exits with an error if they're missing.
    """

    def test_oidc_without_required_fields_fails_validation(self) -> None:
        """--auth=oidc without OIDC config fields rejects at WebSettings validation."""
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            result = runner.invoke(app, ["web", "--auth", "oidc"])

        assert result.exit_code != 0
        # Pydantic validation error is captured in the exception, not stdout
        assert result.exception is not None
        error_text = str(result.exception)
        assert "oidc_issuer" in error_text or "OIDC" in error_text

    def test_default_auth_no_warning(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            result = runner.invoke(app, ["web", "--auth", "local"])

        assert result.exit_code == 0

    def test_invalid_auth_rejected_by_pydantic(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            result = runner.invoke(app, ["web", "--auth", "kerberos"])

        assert result.exit_code != 0
