"""Web application configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class WebSettings(BaseModel):
    """Configuration for the ELSPETH web application.

    All fields have sensible defaults for local development.
    auth_provider uses a Literal type so Pydantic rejects invalid
    values automatically -- no manual @field_validator needed.
    """

    host: str = "127.0.0.1"
    port: int = 8000
    auth_provider: Literal["local", "oidc", "entra"] = "local"
    cors_origins: list[str] = ["http://localhost:5173"]
    data_dir: Path = Path("data")
    composer_model: str = "gpt-4o"
    composer_max_turns: int = 20
    composer_timeout_seconds: float = 120.0
    composer_rate_limit_per_minute: int = 10
    secret_key: str = "change-me-in-production"  # S3: startup guard in Sub-2 enforces non-default in production
    max_upload_bytes: int = 100 * 1024 * 1024  # 100 MB

    # Execution infrastructure (B3 fix)
    # Defaults derive from data_dir when not explicitly set
    landscape_url: str | None = None
    payload_store_path: Path | None = None

    # OIDC / Entra-specific (optional)
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_client_id: str | None = None
    entra_tenant_id: str | None = None

    # Session database (sessions, messages, composition states, runs)
    # Separate from landscape_url (audit DB)
    session_db_url: str | None = None

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
