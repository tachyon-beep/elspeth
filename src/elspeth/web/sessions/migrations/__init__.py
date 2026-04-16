"""Sessions database migration infrastructure.

Provides run_migrations() for programmatic migration at app startup,
replacing the prior metadata.create_all() call.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine


def _alembic_config(engine: Engine) -> Config:
    """Build an Alembic Config pointing at the sessions migration environment.

    The URL rendered here is only used for offline/CLI modes and Alembic's
    internal diagnostics; in the programmatic path `run_migrations()` injects
    a live connection into `cfg.attributes` so env.py bypasses URL-based
    engine construction entirely. Passwords are NOT redacted (would
    produce an un-connectable DSN) and `%` is escaped because
    Alembic's Config backs onto ConfigParser which interpolates `%`.
    """
    ini_path = Path(__file__).parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option(
        "sqlalchemy.url",
        engine.url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return cfg


def run_migrations(engine: Engine, *, auth_provider: str = "local") -> None:
    """Run all pending migrations against the given engine.

    For fresh databases, this creates all tables from scratch.
    For existing pre-migration databases (created by the old create_all()
    path), the baseline migration detects existing tables and stamps
    without re-creating them.

    Called from create_app() at startup.

    The caller's Engine identity is preserved end-to-end: we open a live
    connection from it and hand that connection to Alembic via
    `cfg.attributes["connection"]`. env.py consumes this connection
    directly rather than rebuilding a fresh engine from the rendered URL,
    so StaticPool in-memory databases, connection-local PRAGMAs, and
    password-protected DSNs all round-trip correctly.

    Parameters
    ----------
    auth_provider:
        The deployment's configured auth provider type (e.g. "local",
        "oidc", "entra").  Passed through to migrations that need to
        backfill provider-scoped data — migration 006 uses this to stamp
        existing user_secrets rows with the correct provider instead of
        unconditionally defaulting to "local".
    """
    cfg = _alembic_config(engine)
    cfg.attributes["auth_provider"] = auth_provider
    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
