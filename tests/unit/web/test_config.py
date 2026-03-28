"""Tests for WebSettings configuration model."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from elspeth.web.config import WebSettings


class TestWebSettingsDefaults:
    """Tests for default field values."""

    def test_host_default(self) -> None:
        settings = WebSettings()
        assert settings.host == "127.0.0.1"

    def test_port_default(self) -> None:
        settings = WebSettings()
        assert settings.port == 8000

    def test_auth_provider_default(self) -> None:
        settings = WebSettings()
        assert settings.auth_provider == "local"

    def test_cors_origins_default(self) -> None:
        settings = WebSettings()
        assert settings.cors_origins == ["http://localhost:5173"]

    def test_data_dir_default(self) -> None:
        settings = WebSettings()
        assert settings.data_dir == Path("data")

    def test_composer_model_default(self) -> None:
        settings = WebSettings()
        assert settings.composer_model == "gpt-4o"

    def test_composer_max_turns_default(self) -> None:
        settings = WebSettings()
        assert settings.composer_max_turns == 20

    def test_composer_timeout_seconds_default(self) -> None:
        settings = WebSettings()
        assert settings.composer_timeout_seconds == 120.0

    def test_composer_rate_limit_per_minute_default(self) -> None:
        settings = WebSettings()
        assert settings.composer_rate_limit_per_minute == 10

    def test_secret_key_default(self) -> None:
        settings = WebSettings()
        assert settings.secret_key == "change-me-in-production"

    def test_max_upload_bytes_default(self) -> None:
        settings = WebSettings()
        assert settings.max_upload_bytes == 104857600  # 100 MB

    def test_landscape_url_default_is_none(self) -> None:
        settings = WebSettings()
        assert settings.landscape_url is None

    def test_payload_store_path_default_is_none(self) -> None:
        settings = WebSettings()
        assert settings.payload_store_path is None

    def test_oidc_fields_default_none(self) -> None:
        settings = WebSettings()
        assert settings.oidc_issuer is None
        assert settings.oidc_audience is None
        assert settings.oidc_client_id is None

    def test_entra_tenant_id_default_none(self) -> None:
        settings = WebSettings()
        assert settings.entra_tenant_id is None

    def test_session_db_url_default_is_none(self) -> None:
        settings = WebSettings()
        assert settings.session_db_url is None


class TestWebSettingsCustomValues:
    """Tests for custom field overrides."""

    def test_custom_port_and_host(self) -> None:
        settings = WebSettings(port=9090, host="0.0.0.0", secret_key="test-secret")
        assert settings.port == 9090
        assert settings.host == "0.0.0.0"

    def test_auth_provider_oidc(self) -> None:
        settings = WebSettings(auth_provider="oidc")
        assert settings.auth_provider == "oidc"

    def test_auth_provider_entra(self) -> None:
        settings = WebSettings(auth_provider="entra")
        assert settings.auth_provider == "entra"

    def test_custom_cors_origins(self) -> None:
        settings = WebSettings(cors_origins=["https://app.example.com", "https://staging.example.com"])
        assert len(settings.cors_origins) == 2
        assert "https://app.example.com" in settings.cors_origins

    def test_explicit_landscape_url(self) -> None:
        settings = WebSettings(landscape_url="postgresql://db/audit")
        assert settings.landscape_url == "postgresql://db/audit"

    def test_explicit_payload_store_path(self) -> None:
        settings = WebSettings(payload_store_path=Path("/mnt/payloads"))
        assert settings.payload_store_path == Path("/mnt/payloads")


class TestWebSettingsValidation:
    """Tests for field validation."""

    def test_invalid_auth_provider_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(auth_provider="invalid")  # type: ignore[arg-type]

    def test_invalid_auth_provider_kerberos_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(auth_provider="kerberos")  # type: ignore[arg-type]

    def test_port_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(port=0)

    def test_port_negative_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(port=-1)

    def test_port_above_65535_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(port=65536)

    def test_composer_max_turns_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(composer_max_turns=0)

    def test_composer_timeout_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(composer_timeout_seconds=0)

    def test_composer_rate_limit_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(composer_rate_limit_per_minute=0)

    def test_max_upload_bytes_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(max_upload_bytes=0)


class TestWebSettingsImmutability:
    """Tests that frozen=True prevents post-construction mutation."""

    def test_field_assignment_raises(self) -> None:
        settings = WebSettings()
        with pytest.raises(ValueError):
            settings.port = 9090  # type: ignore[misc]


class TestWebSettingsDerivedAccessors:
    """Tests for get_landscape_url() and get_payload_store_path()."""

    def test_get_landscape_url_default_derives_from_data_dir(self) -> None:
        settings = WebSettings(data_dir=Path("/app/data"))
        url = settings.get_landscape_url()
        assert url == "sqlite:////app/data/runs/audit.db"

    def test_get_landscape_url_explicit_value_returned(self) -> None:
        settings = WebSettings(landscape_url="postgresql://db/audit")
        url = settings.get_landscape_url()
        assert url == "postgresql://db/audit"

    def test_get_payload_store_path_default_derives_from_data_dir(self) -> None:
        settings = WebSettings(data_dir=Path("/app/data"))
        path = settings.get_payload_store_path()
        assert path == Path("/app/data/payloads")

    def test_get_payload_store_path_explicit_value_returned(self) -> None:
        settings = WebSettings(payload_store_path=Path("/mnt/payloads"))
        path = settings.get_payload_store_path()
        assert path == Path("/mnt/payloads")

    def test_default_data_dir_landscape_url(self) -> None:
        """Default data_dir='data' produces a relative sqlite path."""
        settings = WebSettings()
        url = settings.get_landscape_url()
        assert url == f"sqlite:///{Path('data') / 'runs' / 'audit.db'}"

    def test_default_data_dir_payload_store_path(self) -> None:
        """Default data_dir='data' produces a relative payload path."""
        settings = WebSettings()
        path = settings.get_payload_store_path()
        assert path == Path("data") / "payloads"

    def test_get_session_db_url_default_derives_from_data_dir(self) -> None:
        settings = WebSettings(data_dir=Path("/app/data"))
        url = settings.get_session_db_url()
        assert url == "sqlite:////app/data/sessions.db"

    def test_get_session_db_url_explicit_value_returned(self) -> None:
        settings = WebSettings(session_db_url="postgresql://db/sessions")
        url = settings.get_session_db_url()
        assert url == "postgresql://db/sessions"

    def test_default_data_dir_session_db_url(self) -> None:
        """Default data_dir='data' produces a relative sqlite path."""
        settings = WebSettings()
        url = settings.get_session_db_url()
        assert url == f"sqlite:///{Path('data') / 'sessions.db'}"


class TestSecretKeyGuard:
    """Tests for the secret_key production guard validator."""

    def test_default_secret_key_rejected_on_non_local_host(self) -> None:
        with pytest.raises(ValidationError, match="secret_key must be set"):
            WebSettings(host="0.0.0.0")

    def test_default_secret_key_allowed_on_localhost(self) -> None:
        # Should not raise
        settings = WebSettings(host="127.0.0.1")
        assert settings.secret_key == "change-me-in-production"

    def test_custom_secret_key_allowed_on_any_host(self) -> None:
        settings = WebSettings(host="0.0.0.0", secret_key="my-real-secret")
        assert settings.secret_key == "my-real-secret"
