"""Web application configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class WebSettings(BaseModel):
    """Configuration for the ELSPETH web application.

    All fields have sensible defaults for local development.
    auth_provider uses a Literal type so Pydantic rejects invalid
    values automatically -- no manual @field_validator needed.

    Frozen to prevent accidental mutation in async request handlers —
    settings are constructed once and shared via app.state.
    """

    model_config = ConfigDict(frozen=True)

    host: str = "127.0.0.1"
    port: int = Field(default=8451, ge=1, le=65535)
    auth_provider: Literal["local", "oidc", "entra"] = "local"
    registration_mode: Literal["open", "email_verified", "closed"] = "open"
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    data_dir: Path = Path("data")
    composer_model: str = "gpt-4o"
    composer_max_composition_turns: int = Field(default=15, ge=1)
    composer_max_discovery_turns: int = Field(default=10, ge=1)
    composer_timeout_seconds: float = Field(default=85.0, gt=0)
    composer_rate_limit_per_minute: int = Field(default=10, ge=1)
    secret_key: str = (
        "change-me-in-production"  # Security rule S3 (seam-contracts.md): Sub-2 startup guard enforces non-default in production
    )
    max_upload_bytes: int = Field(default=100 * 1024 * 1024, ge=1)
    max_blob_storage_per_session_bytes: int = Field(default=500 * 1024 * 1024, ge=1)
    server_secret_allowlist: tuple[str, ...] = (
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AZURE_API_KEY",
    )
    orphan_run_max_age_seconds: int = Field(default=3600, ge=60)

    # Execution infrastructure — defaults derive from data_dir when not explicitly set
    landscape_url: str | None = None
    landscape_passphrase: str | None = None
    payload_store_path: Path | None = None

    # OIDC / Entra-specific (optional)
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_client_id: str | None = None
    oidc_authorization_endpoint: str | None = None
    entra_tenant_id: str | None = None

    # Session database (sessions, messages, composition states, runs)
    # Separate from landscape_url (audit DB)
    session_db_url: str | None = None

    @model_validator(mode="after")
    def _validate_auth_fields(self) -> WebSettings:
        """Enforce that OIDC/Entra providers have their required fields."""
        if self.auth_provider == "oidc":
            missing = [
                name
                for name, val in (
                    ("oidc_issuer", self.oidc_issuer),
                    ("oidc_audience", self.oidc_audience),
                    ("oidc_client_id", self.oidc_client_id),
                )
                if val is None
            ]
            if missing:
                raise ValueError(f"OIDC auth requires: {', '.join(missing)}")
        elif self.auth_provider == "entra":
            # oidc_issuer is NOT required — EntraAuthProvider derives it
            # from entra_tenant_id (login.microsoftonline.com/{tid}/v2.0).
            missing = [
                name
                for name, val in (
                    ("oidc_audience", self.oidc_audience),
                    ("oidc_client_id", self.oidc_client_id),
                    ("entra_tenant_id", self.entra_tenant_id),
                )
                if val is None
            ]
            if missing:
                raise ValueError(f"Entra auth requires: {', '.join(missing)}")
        return self

    @model_validator(mode="after")
    def _enforce_secret_key_in_production(self) -> WebSettings:
        """Reject the default secret key when host suggests non-local deployment."""
        if self.secret_key == "change-me-in-production" and self.host not in _LOCAL_HOSTS:
            raise ValueError(
                "secret_key must be set to a secure value for non-local deployments "
                "(host is not a loopback address). Set ELSPETH_WEB__SECRET_KEY or pass secret_key explicitly."
            )
        return self

    def get_landscape_url(self) -> str:
        """Resolve landscape DB URL, defaulting to data_dir-relative path."""
        if self.landscape_url is not None:
            return self.landscape_url
        db_path = self.data_dir / "runs" / "audit.db"
        return f"sqlite:///{db_path}"

    def get_payload_store_path(self) -> Path:
        """Resolve payload store path, defaulting to data_dir-relative path."""
        if self.payload_store_path is not None:
            return self.payload_store_path
        return self.data_dir / "payloads"

    def get_session_db_url(self) -> str:
        """Resolve session DB URL, defaulting to data_dir-relative path."""
        if self.session_db_url is not None:
            return self.session_db_url
        db_path = self.data_dir / "sessions.db"
        return f"sqlite:///{db_path}"
