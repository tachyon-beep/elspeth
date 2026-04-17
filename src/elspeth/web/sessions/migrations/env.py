"""Alembic environment for the sessions database.

Supports two invocation modes:

1. Programmatic (default, via ``run_migrations(engine)``): the caller
   passes a live SQLAlchemy ``Connection`` through
   ``config.attributes["connection"]``. We use it directly, preserving
   engine identity (StaticPool, in-memory SQLite, connection-local
   PRAGMAs, open transactions). No URL resolution happens in this mode.

2. CLI (``alembic upgrade head`` invoked directly): no connection is
   injected. We resolve the URL from, in order:
     a. ``ELSPETH_WEB__SESSION_DB_URL`` environment variable
     b. ``alembic.ini`` sqlalchemy.url fallback
   then build a short-lived engine with NullPool.

``logging.config.fileConfig`` is deliberately NOT called here — doing so
at import time resets process-wide logging and clobbers the ELSPETH
structlog ProcessorFormatter, silencing the last-resort logger that
records audit/telemetry system failures.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import pool

from elspeth.web.sessions.engine import create_session_engine
from elspeth.web.sessions.migrations._config import escape_alembic_config_value
from elspeth.web.sessions.models import metadata as target_metadata

config = context.config


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL without a live connection.

    Offline mode has no injected connection to preempt, so the env var
    override applies directly. Without it, ``alembic upgrade head --sql``
    would render SQL against ``alembic.ini``'s placeholder URL instead of
    the operator's intended target — silently producing SQL for the
    wrong database or dialect.

    Raises
    ------
    RuntimeError
        When neither ``ELSPETH_WEB__SESSION_DB_URL`` nor the ini
        ``sqlalchemy.url`` resolves to a non-empty value.  Tier 1
        discipline: crash rather than emit dialect-less SQL.
    """
    if "ELSPETH_WEB__SESSION_DB_URL" in os.environ:
        config.set_main_option(
            "sqlalchemy.url",
            escape_alembic_config_value(os.environ["ELSPETH_WEB__SESSION_DB_URL"]),
        )

    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError(
            "Alembic offline mode: sqlalchemy.url is not configured. Set "
            "ELSPETH_WEB__SESSION_DB_URL or populate sqlalchemy.url in "
            "alembic.ini before generating migration SQL."
        )

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — against a live database connection.

    If the caller injected a connection via ``config.attributes["connection"]``
    (the programmatic path used by ``run_migrations(engine)``), use it
    directly. Otherwise fall back to CLI mode: honor the env var override,
    then build a fresh engine from ``alembic.ini``.
    """
    injected = config.attributes.get("connection")

    if injected is not None:
        context.configure(
            connection=injected,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    # CLI mode: honor env var override, then ini fallback.
    if "ELSPETH_WEB__SESSION_DB_URL" in os.environ:
        config.set_main_option(
            "sqlalchemy.url",
            escape_alembic_config_value(os.environ["ELSPETH_WEB__SESSION_DB_URL"]),
        )

    # Route through create_session_engine so SQLite gets its
    # ``PRAGMA foreign_keys=ON`` listener and startup probe. Using
    # ``sqlalchemy.engine_from_config`` here skips those and would let
    # a direct ``alembic upgrade head`` run with FK enforcement
    # silently disabled — Tier 1 requires enforcement on every path,
    # not just the programmatic one.
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError(
            "Alembic CLI mode: sqlalchemy.url is not configured. Set "
            "ELSPETH_WEB__SESSION_DB_URL or populate sqlalchemy.url in "
            "alembic.ini before running migrations directly."
        )
    connectable = create_session_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
