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
    """Tests for the web command when [webui] is installed."""

    def test_calls_uvicorn_run_with_factory_true(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            runner.invoke(app, ["web", "--port", "9999", "--host", "0.0.0.0"])

        mock_uvicorn.run.assert_called_once()
        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs[1]["factory"] is True or call_kwargs.kwargs["factory"] is True

    def test_passes_correct_host_and_port_to_uvicorn(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            runner.invoke(app, ["web", "--port", "9999", "--host", "0.0.0.0"])

        call_kwargs = mock_uvicorn.run.call_args
        assert call_kwargs.kwargs.get("host") == "0.0.0.0" or call_kwargs[1].get("host") == "0.0.0.0"
        assert call_kwargs.kwargs.get("port") == 9999 or call_kwargs[1].get("port") == 9999

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


class TestWebCommandAuthWarning:
    """Tests for the --auth non-default warning."""

    def test_non_default_auth_prints_warning(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            result = runner.invoke(app, ["web", "--auth", "oidc"])

        assert "not yet effective" in result.output

    def test_default_auth_no_warning(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            result = runner.invoke(app, ["web", "--auth", "local"])

        assert "not yet effective" not in result.output

    def test_invalid_auth_rejected_by_pydantic(self) -> None:
        mock_uvicorn = MagicMock()
        with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
            mock_uvicorn.run = MagicMock()
            result = runner.invoke(app, ["web", "--auth", "kerberos"])

        assert result.exit_code != 0
