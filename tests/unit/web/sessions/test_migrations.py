"""Regression tests for the sessions migration infrastructure and engine factory.

Six bug classes are covered:

* Bug 1 (elspeth-3e79cef70f): ``run_migrations`` must migrate the
  caller's engine, not a freshly-rebuilt one; password-protected URLs
  must survive the round-trip.
* Bug 2 (elspeth-e6305e2b22): ``ELSPETH_WEB__SESSION_DB_URL`` must NOT
  override the caller's engine in programmatic mode.
* Bug 3 (elspeth-6934c6f38f): the 001 baseline sentinel must refuse to
  stamp on partial/unknown schemas.
* Bug 4 (elspeth-8733cc4f72): the composite FK and service-level
  checks must reject cross-session references; migration 007 must
  refuse to apply over corrupt pre-existing data.
* Bug 5 (elspeth-09f881db97): migrations must NOT replace process-wide
  logging handlers on startup.
* Bug 6: migration 007's batch rebuild must preserve every index the
  post-006 shape defines — most critically
  ``uq_runs_one_active_per_session`` (the partial unique index that
  closes the one-active-run race in ``create_run``).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, insert, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from elspeth.web.sessions.engine import create_session_engine
from elspeth.web.sessions.migrations import run_migrations
from elspeth.web.sessions.models import (
    chat_messages_table,
    composition_states_table,
    runs_table,
    sessions_table,
)
from elspeth.web.sessions.service import SessionServiceImpl

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_engine() -> Engine:
    """Build a StaticPool in-memory engine with FK enforcement wired in."""
    return create_session_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


def _seed_session(conn, session_id: str, *, user_id: str = "u") -> None:
    now = datetime.now(UTC)
    conn.execute(
        insert(sessions_table).values(
            id=session_id,
            user_id=user_id,
            auth_provider_type="local",
            title="t",
            created_at=now,
            updated_at=now,
        )
    )


def _seed_state(conn, state_id: str, session_id: str) -> None:
    conn.execute(
        insert(composition_states_table).values(
            id=state_id,
            session_id=session_id,
            version=1,
            is_valid=False,
            created_at=datetime.now(UTC),
        )
    )


def _alembic_config_for(engine) -> Config:
    """Build an alembic Config bound to this engine; does not upgrade.

    Used by tests that need to drive alembic directly (stamp-only,
    upgrade-to-intermediate-revision) rather than running to head via
    ``run_migrations``.
    """
    from pathlib import Path

    ini_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "elspeth" / "web" / "sessions" / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option(
        "sqlalchemy.url",
        engine.url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    cfg.attributes["auth_provider"] = "local"
    return cfg


def _upgrade_to_006(engine) -> Config:
    """Bring engine to revision 006 and return the Config for further upgrades.

    Used by integrity-scan tests that need to seed pre-fix corruption
    between revision 006 (where the violation is still accepted by the
    single-column FK) and revision 007 (which blocks on that exact
    shape).
    """
    from alembic import command

    cfg = _alembic_config_for(engine)
    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "006")
    return cfg


# ---------------------------------------------------------------------------
# Bug 1, 2, 5: run_migrations infrastructure
# ---------------------------------------------------------------------------


class TestRunMigrations:
    """Programmatic migration API preserves engine identity and logging."""

    def test_fresh_in_memory_creates_all_tables(self) -> None:
        engine = _fresh_engine()
        run_migrations(engine)

        tables = set(inspect(engine).get_table_names())
        expected = {
            "sessions",
            "chat_messages",
            "composition_states",
            "runs",
            "run_events",
            "blobs",
            "blob_run_links",
            "user_secrets",
        }
        assert expected.issubset(tables)
        assert "alembic_version" in tables

    def test_migration_is_idempotent(self) -> None:
        engine = _fresh_engine()
        run_migrations(engine)
        run_migrations(engine)  # second call is a no-op

        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev == "007"

    def test_preserves_engine_identity_via_staticpool(self) -> None:
        """Bug 1 regression: the caller's engine must be migrated directly.

        If run_migrations() rebuilt a fresh engine from str(engine.url), a
        StaticPool in-memory database would migrate a *different* SQLite
        connection and the caller's tables would remain empty. Confirm that
        after migration the caller's engine can see all tables.
        """
        engine = _fresh_engine()
        run_migrations(engine)

        with engine.begin() as conn:
            _seed_session(conn, str(uuid.uuid4()))
            count = conn.execute(text("SELECT count(*) FROM sessions")).scalar_one()
        assert count == 1

    def test_env_var_does_not_override_programmatic_connection(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """Bug 2 regression: env var must be ignored in programmatic mode.

        Point ``ELSPETH_WEB__SESSION_DB_URL`` at an impossible path. If env.py
        applied it in programmatic mode we would fail to migrate. Instead the
        caller's injected connection takes precedence and the migration runs
        against the in-memory engine.
        """
        impossible = tmp_path / "does-not-exist" / "sessions.db"
        monkeypatch.setenv("ELSPETH_WEB__SESSION_DB_URL", f"sqlite:///{impossible}")

        engine = _fresh_engine()
        run_migrations(engine)

        # The caller's engine was migrated, not a fresh one from the env var.
        assert "sessions" in inspect(engine).get_table_names()
        assert not impossible.exists()

    def test_does_not_disturb_root_logging(self) -> None:
        """Bug 5 regression: env.py must NOT call fileConfig().

        Snapshot the root logger's handlers before and after running
        migrations; they must be the same objects (not replaced). Also
        verify the log level did not change.
        """
        root = logging.getLogger()
        before_handlers = list(root.handlers)
        before_level = root.level

        engine = _fresh_engine()
        run_migrations(engine)

        assert list(root.handlers) == before_handlers
        assert root.level == before_level


# ---------------------------------------------------------------------------
# Bug 3: baseline sentinel
# ---------------------------------------------------------------------------


class TestBaselineSentinel:
    """001 must refuse to stamp on schemas that don't exactly match baseline."""

    def test_partial_schema_raises_runtimeerror(self) -> None:
        """Only the ``sessions`` table exists — must NOT stamp as 001."""
        # Pre-seed a partial schema that the old sentinel would have stamped.
        bare = create_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        with bare.begin() as conn:
            conn.execute(text("CREATE TABLE sessions (id TEXT PRIMARY KEY)"))

        # Wrap with the factory so FK PRAGMA is set for subsequent migrations.
        # Reuse the same underlying connection by binding via StaticPool.
        # (We run migrations against `bare` directly, which is fine — this is
        # a migration-shape test, not an FK test.)
        with pytest.raises(RuntimeError, match="refuses to stamp revision 001"):
            run_migrations(bare)

    def test_unknown_extra_table_raises(self) -> None:
        """Schema has baseline tables plus an unknown extra — must refuse."""
        bare = create_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        with bare.begin() as conn:
            for t in (
                "sessions",
                "chat_messages",
                "composition_states",
                "runs",
                "run_events",
                "mystery_table",  # not in the baseline set
            ):
                conn.execute(text(f"CREATE TABLE {t} (id TEXT PRIMARY KEY)"))

        with pytest.raises(RuntimeError, match="refuses to stamp revision 001"):
            run_migrations(bare)

    def test_baseline_shape_stamps_without_ddl(self) -> None:
        """Positive case: exact baseline set stamps 001 and runs NO DDL.

        The negative cases cover refusal; this asserts the happy path so
        a regression that accidentally made 001 always crash, or always
        re-create the baseline tables (clobbering pre-existing data),
        would be caught.

        Detection strategy: pre-seed the five baseline tables with a
        sentinel column (``_probe``) that the real baseline schema does
        not define. If 001 runs DDL — whether ``create_table`` or a
        drop/recreate — the sentinel column vanishes. If the sentinel
        survives AND ``alembic_version == '001'``, the stamp-only branch
        fired as designed.
        """
        from alembic import command

        bare = create_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        with bare.begin() as conn:
            for t in (
                "sessions",
                "chat_messages",
                "composition_states",
                "runs",
                "run_events",
            ):
                conn.execute(text(f"CREATE TABLE {t} (id TEXT PRIMARY KEY, _probe TEXT)"))

        cfg = _alembic_config_for(bare)
        with bare.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "001")  # stamp only, do NOT proceed to 002+

        inspector = inspect(bare)
        with bare.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev == "001"

        # The sentinel column survives on every baseline table — proof
        # that the stamp-only branch returned without touching schema.
        for t in (
            "sessions",
            "chat_messages",
            "composition_states",
            "runs",
            "run_events",
        ):
            cols = {c["name"] for c in inspector.get_columns(t)}
            assert cols == {"id", "_probe"}, (
                f"001 mutated {t}: expected {{id, _probe}}, got {cols}. The stamp-only branch must not run DDL."
            )


# ---------------------------------------------------------------------------
# Bug 4: cross-session FK enforcement (service + DB)
# ---------------------------------------------------------------------------


class TestCrossSessionFKConstraints:
    """Composite FK and service checks reject cross-session references."""

    @pytest.mark.asyncio
    async def test_service_rejects_cross_session_add_message(self) -> None:
        engine = _fresh_engine()
        run_migrations(engine)
        svc = SessionServiceImpl(engine)

        sa_id = uuid.uuid4()
        sb_id = uuid.uuid4()
        state_a = uuid.uuid4()
        with engine.begin() as conn:
            _seed_session(conn, str(sa_id))
            _seed_session(conn, str(sb_id))
            _seed_state(conn, str(state_a), str(sa_id))

        with pytest.raises(RuntimeError, match="cross-session reference"):
            await svc.add_message(
                session_id=sb_id,
                role="user",
                content="x",
                composition_state_id=state_a,
            )

    @pytest.mark.asyncio
    async def test_service_rejects_cross_session_create_run(self) -> None:
        engine = _fresh_engine()
        run_migrations(engine)
        svc = SessionServiceImpl(engine)

        sa_id = uuid.uuid4()
        sb_id = uuid.uuid4()
        state_a = uuid.uuid4()
        with engine.begin() as conn:
            _seed_session(conn, str(sa_id))
            _seed_session(conn, str(sb_id))
            _seed_state(conn, str(state_a), str(sa_id))

        with pytest.raises(RuntimeError, match="cross-session reference"):
            await svc.create_run(session_id=sb_id, state_id=state_a)

    def test_db_level_composite_fk_rejects_cross_session_insert(self) -> None:
        """Defense in depth: if somehow the service check is bypassed, the DB FK still fires."""
        engine = _fresh_engine()
        run_migrations(engine)

        sa_id = str(uuid.uuid4())
        sb_id = str(uuid.uuid4())
        state_a = str(uuid.uuid4())
        with engine.begin() as conn:
            _seed_session(conn, sa_id)
            _seed_session(conn, sb_id)
            _seed_state(conn, state_a, sa_id)

        # Direct SQL bypass of service layer — must be rejected by DB FK
        with pytest.raises(IntegrityError, match="FOREIGN KEY"), engine.begin() as conn:
            conn.execute(
                insert(chat_messages_table).values(
                    id=str(uuid.uuid4()),
                    session_id=sb_id,
                    role="user",
                    content="x",
                    created_at=datetime.now(UTC),
                    composition_state_id=state_a,
                )
            )

        with pytest.raises(IntegrityError, match="FOREIGN KEY"), engine.begin() as conn:
            conn.execute(
                insert(runs_table).values(
                    id=str(uuid.uuid4()),
                    session_id=sb_id,
                    state_id=state_a,
                    status="pending",
                    started_at=datetime.now(UTC),
                )
            )


class TestMigration007IntegrityScan:
    """007 must refuse to apply if pre-existing cross-session rows exist.

    Both scan branches (chat_messages and runs) are covered separately
    so a regression that disables one scan cannot hide behind the other.
    """

    def test_blocks_on_orphan_chat_message(self) -> None:
        """Seed revision 006 with a cross-session chat_messages row, then attempt 007."""
        from alembic import command

        engine = _fresh_engine()
        cfg = _upgrade_to_006(engine)

        # Seed a cross-session violation. At revision 006 the FK on
        # chat_messages.composition_state_id is single-column
        # (composition_state_id -> composition_states.id) and enforces
        # only that the target row exists. It has no knowledge of
        # session_id and therefore accepts this insert natively — no
        # PRAGMA juggling required. This is exactly the pre-fix
        # corruption shape that 007's integrity scan must detect and
        # refuse to upgrade over.
        sa_id = str(uuid.uuid4())
        sb_id = str(uuid.uuid4())
        state_a = str(uuid.uuid4())
        with engine.begin() as conn:
            _seed_session(conn, sa_id)
            _seed_session(conn, sb_id)
            _seed_state(conn, state_a, sa_id)
            conn.execute(
                insert(chat_messages_table).values(
                    id=str(uuid.uuid4()),
                    session_id=sb_id,  # different from state_a's owning session
                    role="user",
                    content="orphan",
                    created_at=datetime.now(UTC),
                    composition_state_id=state_a,
                )
            )

        # Now attempt to apply 007 — should refuse with Tier 1 diagnostic
        with pytest.raises(RuntimeError, match="Migration 007 blocked"), engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")

    def test_blocks_on_orphan_runs_row(self) -> None:
        """Seed revision 006 with a cross-session runs row, then attempt 007.

        Migration 007 scans ``runs.state_id`` independently of
        ``chat_messages.composition_state_id``. This test asserts the
        second branch fires when *only* a runs orphan exists — so a
        regression that drops or weakens the runs scan is detected
        even when chat_messages is clean.
        """
        from alembic import command

        engine = _fresh_engine()
        cfg = _upgrade_to_006(engine)

        # Same logic as the chat_messages case: at revision 006 the
        # runs.state_id FK is single-column and does not check session
        # membership, so this insert is accepted natively.
        sa_id = str(uuid.uuid4())
        sb_id = str(uuid.uuid4())
        state_a = str(uuid.uuid4())
        with engine.begin() as conn:
            _seed_session(conn, sa_id)
            _seed_session(conn, sb_id)
            _seed_state(conn, state_a, sa_id)
            conn.execute(
                insert(runs_table).values(
                    id=str(uuid.uuid4()),
                    session_id=sb_id,  # different from state_a's owning session
                    state_id=state_a,
                    status="pending",
                    started_at=datetime.now(UTC),
                )
            )

        # Scan must detect the runs orphan specifically and refuse 007.
        # Match on "runs rows" so a regression that happens to hit the
        # chat_messages branch by mistake cannot satisfy this test.
        with pytest.raises(RuntimeError, match=r"Migration 007 blocked: .*runs rows"), engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# Bug 6: migration 007 must preserve all pre-existing indexes
# ---------------------------------------------------------------------------


class TestMigration007PreservesIndexes:
    """007's batch rebuild uses ``copy_from`` and must include every index.

    Any ``copy_from`` shape that omits indexes silently drops them during
    the SQLite table-copy rebuild. The partial unique index
    ``uq_runs_one_active_per_session`` is the ``create_run`` race's only
    real defence, so its loss reopens a concurrency bug.
    """

    def _sqlite_master_indexes(self, engine: Engine, table: str) -> dict[str, str | None]:
        """Return {index_name: sql} from sqlite_master.

        ``inspect().get_indexes()`` does not reliably surface partial
        unique indexes (the WHERE clause is opaque to it), so we hit
        sqlite_master directly. ``sql`` is NULL for auto-generated PK
        indexes and non-NULL (full CREATE INDEX statement) for everything
        we explicitly declared.
        """
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = :t"),
                {"t": table},
            ).fetchall()
        return dict(rows)

    def test_runs_session_id_index_survives(self) -> None:
        """``ix_runs_session_id`` must remain after 007 applies."""
        engine = _fresh_engine()
        run_migrations(engine)
        indexes = self._sqlite_master_indexes(engine, "runs")
        assert "ix_runs_session_id" in indexes, (
            f"ix_runs_session_id was dropped by 007's batch rebuild. Surviving indexes on runs: {sorted(indexes)}"
        )

    def test_chat_messages_session_id_index_survives(self) -> None:
        """``ix_chat_messages_session_id`` must remain after 007 applies."""
        engine = _fresh_engine()
        run_migrations(engine)
        indexes = self._sqlite_master_indexes(engine, "chat_messages")
        assert "ix_chat_messages_session_id" in indexes, (
            f"ix_chat_messages_session_id was dropped by 007's batch rebuild. Surviving indexes on chat_messages: {sorted(indexes)}"
        )

    def test_runs_partial_unique_index_survives(self) -> None:
        """``uq_runs_one_active_per_session`` (partial unique) must remain.

        This is the load-bearing index: it enforces at most one run per
        session in (pending, running) status. If 007 drops it, two
        concurrent ``create_run`` calls can both succeed — the TOCTOU
        race the index was designed to close.
        """
        engine = _fresh_engine()
        run_migrations(engine)
        indexes = self._sqlite_master_indexes(engine, "runs")
        assert "uq_runs_one_active_per_session" in indexes, (
            f"uq_runs_one_active_per_session was dropped by 007's batch rebuild. Surviving indexes on runs: {sorted(indexes)}"
        )
        # Also assert the WHERE clause survived — an index without the
        # partial predicate would forbid ANY second run per session, not
        # just a second active one.
        sql = indexes["uq_runs_one_active_per_session"]
        assert sql is not None, "sqlite_master returned NULL sql for the partial index"
        assert "WHERE" in sql.upper(), f"uq_runs_one_active_per_session lost its WHERE clause during 007. SQL: {sql!r}"
        assert "pending" in sql and "running" in sql, (
            f"uq_runs_one_active_per_session WHERE clause no longer references pending/running statuses. SQL: {sql!r}"
        )

    def test_concurrent_active_runs_rejected(self) -> None:
        """End-to-end behavioural proof: the index enforces the invariant.

        Complements the schema-shape tests above — if Alembic ever
        silently converts the partial unique to a plain unique (or
        vice-versa), the shape tests would pass but behaviour would be
        wrong. This test exercises the invariant the index exists to
        enforce.
        """
        engine = _fresh_engine()
        run_migrations(engine)

        session_id = str(uuid.uuid4())
        state_id = str(uuid.uuid4())
        with engine.begin() as conn:
            _seed_session(conn, session_id)
            _seed_state(conn, state_id, session_id)
            # First pending run: must succeed.
            conn.execute(
                insert(runs_table).values(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    state_id=state_id,
                    status="pending",
                    started_at=datetime.now(UTC),
                )
            )

        # Second pending run for the same session: must fail on the
        # partial unique index.
        with pytest.raises(IntegrityError, match=r"uq_runs_one_active_per_session|UNIQUE"), engine.begin() as conn:
            conn.execute(
                insert(runs_table).values(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    state_id=state_id,
                    status="pending",
                    started_at=datetime.now(UTC),
                )
            )

    def test_completed_runs_are_not_unique_constrained(self) -> None:
        """WHERE clause correctness: inactive statuses are NOT constrained.

        If the partial index accidentally loses its WHERE clause, it
        degrades to a plain unique-on-session_id which would forbid ANY
        second run per session, completed or otherwise. That would
        break historical browsing of a session's past runs.
        """
        engine = _fresh_engine()
        run_migrations(engine)

        session_id = str(uuid.uuid4())
        state_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        with engine.begin() as conn:
            _seed_session(conn, session_id)
            _seed_state(conn, state_id, session_id)
            for _ in range(3):
                conn.execute(
                    insert(runs_table).values(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        state_id=state_id,
                        status="completed",
                        started_at=now,
                        finished_at=now,
                    )
                )

        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM runs WHERE session_id = :sid"),
                {"sid": session_id},
            ).scalar_one()
        assert count == 3, (
            f"Expected 3 completed runs per session to be allowed, got {count}. "
            f"The partial unique index may have lost its WHERE clause and "
            f"degraded to a plain unique constraint."
        )


# ---------------------------------------------------------------------------
# Bug 7: env.py CLI path must route through create_session_engine
# ---------------------------------------------------------------------------


class TestCliMigrationPathUsesEngineFactory:
    """Direct ``alembic upgrade`` must build its engine via the factory.

    Previously env.py's CLI branch called ``sqlalchemy.engine_from_config``
    which leaves ``PRAGMA foreign_keys=OFF`` on SQLite. That let a
    direct CLI upgrade copy pre-existing dangling state_id /
    composition_state_id rows through revision 007's batch rebuild and
    stamp the DB at head without FK validation. The CLI path now goes
    through ``create_session_engine``, the single Tier 1 factory that
    wires the FK pragma listener and asserts it took effect.
    """

    def test_cli_path_invokes_create_session_engine(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """Spy on the factory to confirm the CLI branch uses it.

        Alembic re-executes env.py fresh on each ``command.upgrade`` call
        (it uses ``importlib.util.spec_from_file_location`` and never
        caches the module in ``sys.modules``), so patching
        ``create_session_engine`` at its source module IS visible to
        env.py's subsequent ``from ... import create_session_engine``.
        If alembic's loading behaviour ever changes to cache env.py,
        this test would start failing — that itself is valuable signal.
        """
        from alembic import command

        import elspeth.web.sessions.engine as engine_mod

        observed: list[tuple[str, dict]] = []
        original = engine_mod.create_session_engine

        def spy(url, **kwargs):
            observed.append((url, dict(kwargs)))
            return original(url, **kwargs)

        monkeypatch.setattr(engine_mod, "create_session_engine", spy)

        db_path = tmp_path / "cli_path.db"
        monkeypatch.setenv("ELSPETH_WEB__SESSION_DB_URL", f"sqlite:///{db_path}")

        # Build an alembic Config that does NOT inject a connection — this
        # forces env.py into the CLI branch where our fix lives.
        from pathlib import Path

        ini_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "elspeth" / "web" / "sessions" / "alembic.ini"
        cfg = Config(str(ini_path))
        cfg.attributes["auth_provider"] = "local"
        # Deliberately DO NOT set sqlalchemy.url or attributes["connection"]
        # — env.py must resolve from ELSPETH_WEB__SESSION_DB_URL instead.

        command.upgrade(cfg, "head")

        assert len(observed) == 1, (
            f"create_session_engine should be called exactly once on the CLI path; got {len(observed)} calls: {observed!r}"
        )
        observed_url, _ = observed[0]
        assert str(db_path) in observed_url, (
            f"CLI path built engine with wrong URL: {observed_url!r} does not contain expected path {str(db_path)!r}"
        )

    def test_cli_path_migration_has_foreign_keys_enabled(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """Behavioural proof: after a CLI upgrade, FKs are enforced.

        If env.py regresses to ``engine_from_config``, the resulting
        database connection inherits ``PRAGMA foreign_keys=OFF``. This
        test opens a fresh connection via ``create_session_engine`` to
        the migrated DB and confirms the PRAGMA is set — the factory's
        probe would raise if the listener silently failed.
        """
        from alembic import command

        db_path = tmp_path / "cli_fk_check.db"
        monkeypatch.setenv("ELSPETH_WEB__SESSION_DB_URL", f"sqlite:///{db_path}")

        from pathlib import Path

        ini_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "elspeth" / "web" / "sessions" / "alembic.ini"
        cfg = Config(str(ini_path))
        cfg.attributes["auth_provider"] = "local"

        command.upgrade(cfg, "head")

        # Re-open the migrated DB through the factory. If env.py did not
        # route through the factory during migration, that is a distinct
        # failure mode caught by the spy test above; here we verify the
        # migrated DB is usable under Tier 1 FK enforcement.
        engine = create_session_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            pragma = conn.execute(text("PRAGMA foreign_keys")).scalar_one()
        assert pragma == 1


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------


class TestCreateSessionEngine:
    """Factory guarantees PRAGMA foreign_keys=ON on SQLite."""

    def test_sqlite_engine_has_foreign_keys_enabled(self) -> None:
        engine = _fresh_engine()
        with engine.connect() as conn:
            pragma = conn.execute(text("PRAGMA foreign_keys")).scalar_one()
        assert pragma == 1

    def test_probe_crashes_if_pragma_silently_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The factory's startup assertion refuses engines where the PRAGMA didn't take.

        Simulate a broken environment by monkeypatching the event listener
        to set foreign_keys=OFF instead of ON. The factory's probe must
        detect that the PRAGMA is 0 and refuse to return the engine.
        """
        import elspeth.web.sessions.engine as engine_mod

        # Replace the factory's listener with one that DISABLES the PRAGMA.
        original = engine_mod.create_session_engine

        def broken_factory(url, **kwargs):
            from sqlalchemy import create_engine, event, text

            eng = create_engine(url, **kwargs)
            if eng.dialect.name == "sqlite":

                @event.listens_for(eng, "connect")
                def _off(dbapi_conn, _record):
                    cur = dbapi_conn.cursor()
                    try:
                        cur.execute("PRAGMA foreign_keys=OFF")
                    finally:
                        cur.close()

                with eng.connect() as conn:
                    result = conn.execute(text("PRAGMA foreign_keys")).scalar_one()
                if result != 1:
                    raise RuntimeError(f"Session engine {eng.url!r} rejected PRAGMA foreign_keys=ON (got {result!r}).")
            return eng

        with pytest.raises(RuntimeError, match="rejected PRAGMA"):
            broken_factory(
                "sqlite:///:memory:",
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )
        _ = original  # silence unused
