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
    """Build an Alembic Config pointing at the sessions migration environment."""
    ini_path = Path(__file__).parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    return cfg


def run_migrations(engine: Engine) -> None:
    """Run all pending migrations against the given engine.

    For fresh databases, this creates all tables from scratch.
    For existing pre-migration databases (created by the old create_all()
    path), the baseline migration detects existing tables and stamps
    without re-creating them.

    Called from create_app() at startup.
    """
    cfg = _alembic_config(engine)
    command.upgrade(cfg, "head")
