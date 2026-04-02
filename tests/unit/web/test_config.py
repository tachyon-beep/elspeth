"""Tests for WebSettings configuration model."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from elspeth.web.config import WebSettings


class TestWebSettingsValidation:
    """Tests for field validation."""

    def test_invalid_auth_provider_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(auth_provider="invalid")

    def test_invalid_auth_provider_kerberos_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(auth_provider="kerberos")

    def test_port_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(port=0)

    def test_port_negative_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(port=-1)

    def test_port_above_65535_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(port=65536)

    def test_composer_max_composition_turns_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(composer_max_composition_turns=0)

    def test_composer_max_discovery_turns_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(composer_max_discovery_turns=0)

    def test_composer_timeout_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(composer_timeout_seconds=0)

    def test_composer_rate_limit_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(composer_rate_limit_per_minute=0)

    def test_max_upload_bytes_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            WebSettings(max_upload_bytes=0)


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

    def test_default_secret_key_allowed_on_localhost_name(self) -> None:
        settings = WebSettings(host="localhost")
        assert settings.secret_key == "change-me-in-production"

    def test_default_secret_key_allowed_on_ipv6_loopback(self) -> None:
        settings = WebSettings(host="::1")
        assert settings.secret_key == "change-me-in-production"

    def test_custom_secret_key_allowed_on_any_host(self) -> None:
        settings = WebSettings(host="0.0.0.0", secret_key="my-real-secret")
        assert settings.secret_key == "my-real-secret"


class TestAuthFieldValidation:
    """Tests for OIDC/Entra conditional field requirements."""

    def test_local_provider_no_oidc_fields_required(self) -> None:
        """Local auth (default) should work without any OIDC fields."""
        settings = WebSettings(auth_provider="local")
        assert settings.auth_provider == "local"

    def test_oidc_provider_missing_fields_raises(self) -> None:
        """OIDC provider without required fields should raise."""
        with pytest.raises(ValidationError, match="OIDC auth requires"):
            WebSettings(auth_provider="oidc")

    def test_oidc_provider_with_all_fields_valid(self) -> None:
        """OIDC provider with all required fields should succeed."""
        settings = WebSettings(
            auth_provider="oidc",
            oidc_issuer="https://issuer.example.com",
            oidc_audience="my-audience",
            oidc_client_id="my-client-id",
        )
        assert settings.auth_provider == "oidc"
        assert settings.oidc_issuer == "https://issuer.example.com"

    def test_oidc_provider_partial_fields_raises(self) -> None:
        """OIDC provider with only some fields should name the missing ones."""
        with pytest.raises(ValidationError, match="oidc_audience"):
            WebSettings(
                auth_provider="oidc",
                oidc_issuer="https://issuer.example.com",
            )

    def test_entra_provider_missing_fields_raises(self) -> None:
        """Entra provider without required fields should raise."""
        with pytest.raises(ValidationError, match="Entra auth requires"):
            WebSettings(auth_provider="entra")

    def test_entra_provider_missing_tenant_id_raises(self) -> None:
        """Entra with OIDC fields but no tenant_id should raise."""
        with pytest.raises(ValidationError, match="entra_tenant_id"):
            WebSettings(
                auth_provider="entra",
                oidc_issuer="https://login.microsoftonline.com/t/v2.0",
                oidc_audience="my-audience",
                oidc_client_id="my-client-id",
            )

    def test_entra_provider_with_all_fields_valid(self) -> None:
        """Entra provider with all required fields should succeed."""
        settings = WebSettings(
            auth_provider="entra",
            oidc_issuer="https://login.microsoftonline.com/t/v2.0",
            oidc_audience="my-audience",
            oidc_client_id="my-client-id",
            entra_tenant_id="my-tenant-id",
        )
        assert settings.auth_provider == "entra"
        assert settings.entra_tenant_id == "my-tenant-id"
