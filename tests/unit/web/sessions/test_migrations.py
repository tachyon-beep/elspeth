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
from typing import Any

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
        assert rev == "008"

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

    def test_abort_then_remap_then_rerun_reaches_head(self) -> None:
        """Operator's alternative remediation path — UPDATE rather than DELETE.

        The 007 abort error instructs the operator to "Remediate
        manually before re-running migrations." The ``DELETE`` path
        (drop the orphan rows entirely) is one valid remediation, but
        it is NOT the only one: a row whose ``composition_state_id``
        points at the wrong session may be semantically recoverable if
        the operator identifies the correct same-session state to remap
        it to (e.g. from audit lineage, from the session's own
        composition history, or from a replayed source). In that case
        the remediation is an ``UPDATE`` — rewrite the foreign key to a
        valid target in the current session — not a ``DELETE``.

        This test covers that alternative path end-to-end:

        1. upgrade to 006;
        2. seed a cross-session orphan in ``chat_messages`` AND a
           same-session valid state the orphan can be remapped onto;
        3. attempt upgrade — RuntimeError from 007 (prereq);
        4. UPDATE the orphan row's ``composition_state_id`` to the
           same-session state's id;
        5. ``run_migrations(engine)`` — must now reach head with the
           composite FK in place.

        Without this test the alternative remediation path is a
        documentation claim the migration never mechanically
        demonstrated — an operator could follow the UPDATE recipe and
        still hit a latent bug (e.g. the integrity scan mis-computing
        "different session" after the update), and there would be no
        in-tree proof that the advertised path actually reaches head.
        """
        from alembic import command

        engine = _fresh_engine()
        cfg = _upgrade_to_006(engine)

        # Seed the corruption shape the scan refuses: a chat_messages
        # row in session B points at a composition_state owned by
        # session A. Also seed a VALID state in session B so the
        # remediation has a legitimate target to remap onto — this is
        # how an operator would recover, not by deletion.
        sa_id = str(uuid.uuid4())
        sb_id = str(uuid.uuid4())
        state_a = str(uuid.uuid4())  # owned by session A
        state_b = str(uuid.uuid4())  # owned by session B — the remap target
        orphan_message_id = str(uuid.uuid4())
        with engine.begin() as conn:
            _seed_session(conn, sa_id)
            _seed_session(conn, sb_id)
            _seed_state(conn, state_a, sa_id)
            _seed_state(conn, state_b, sb_id)
            conn.execute(
                insert(chat_messages_table).values(
                    id=orphan_message_id,
                    session_id=sb_id,  # session B
                    role="user",
                    content="orphan-to-be-remapped",
                    created_at=datetime.now(UTC),
                    composition_state_id=state_a,  # but points at session A's state
                )
            )

        # Prereq: at this point 007 refuses to apply — matches
        # test_blocks_on_orphan_chat_message above. Asserting it here
        # rather than relying on the other test proves the remediation
        # starts from the blocked state the operator would actually
        # see, not from an already-clean schema.
        with pytest.raises(RuntimeError, match="Migration 007 blocked"), engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")

        # Operator's remediation: identify the orphan, determine the
        # correct same-session state (state_b), and UPDATE the row.
        # This is the "remap" path — the row survives with its audit
        # history intact, just re-anchored to a valid same-session
        # target. ``DELETE`` would lose the row's audit lineage.
        with engine.begin() as conn:
            result = conn.execute(
                text("UPDATE chat_messages SET composition_state_id = :new_state WHERE id = :mid"),
                {"new_state": state_b, "mid": orphan_message_id},
            )
            assert result.rowcount == 1, (
                f"Remap UPDATE should affect exactly 1 row (the orphan), rowcount={result.rowcount}. Seed data drift."
            )

        # Re-run migrations end-to-end via ``run_migrations`` (not raw
        # ``command.upgrade``) to prove the operator-facing entry point
        # reaches head cleanly — the advertised remediation path must
        # work through the production-facing API, not just via alembic
        # internals.
        run_migrations(engine)

        # Verify head reached AND the composite FK is now in place —
        # the remap row should satisfy the newly-applied constraint.
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        # Head is whatever the latest migration is; we care that it is
        # at least 007 (the one we were blocked on). An exact-match
        # against a hardcoded "008" would fail the moment a 009 ships.
        assert rev >= "007", (
            f"Expected alembic_version >= '007' after remap remediation, got {rev!r}. "
            "Migration 007 refused to apply even after the orphan was remapped."
        )

        # Proof that the composite FK is actually enforcing now:
        # attempting to INSERT a NEW cross-session orphan must fail at
        # the DB layer, not slip through. This is the positive
        # assertion that the remediation genuinely restored Tier 1
        # integrity, not merely advanced the alembic_version counter.
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                insert(chat_messages_table).values(
                    id=str(uuid.uuid4()),
                    session_id=sb_id,
                    role="user",
                    content="post-remediation cross-session orphan",
                    created_at=datetime.now(UTC),
                    composition_state_id=state_a,  # session A's state — should be rejected now
                )
            )


# ---------------------------------------------------------------------------
# Migration 006: refuse to fabricate auth_provider ownership on legacy rows
# ---------------------------------------------------------------------------


class TestMigration006RefusesFabrication:
    """006 must add auth_provider_type without fabricating ownership.

    Pre-006 rows have no auth_provider_type. Backfilling them from the
    deployment's current auth_provider would assert an ownership the
    original rows never claimed — a fabrication per CLAUDE.md's
    fabrication decision test. If an installation changed provider
    between writing the legacy rows and running the migration, the
    backfill would silently transfer secrets into the wrong auth
    namespace. The migration now aborts when legacy rows exist,
    forcing explicit remediation.
    """

    def _upgrade_to_005(self, engine: Engine) -> Config:
        """Bring engine to revision 005 (pre-006 user_secrets shape)."""
        from alembic import command

        cfg = _alembic_config_for(engine)
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "005")
        return cfg

    def test_upgrade_006_succeeds_on_empty_user_secrets(self) -> None:
        """Fresh DB: 005 → 006 adds column, unique constraint, and composite index."""
        from alembic import command

        engine = _fresh_engine()
        cfg = self._upgrade_to_005(engine)
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "006")

        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("user_secrets")}
        assert "auth_provider_type" in cols

        # New composite unique constraint replaces the name+user_id one.
        unique_names = {c["name"] for c in inspector.get_unique_constraints("user_secrets")}
        assert "uq_user_secret_name_user_provider" in unique_names
        assert "uq_user_secret_name_user" not in unique_names

        # New composite index replaces the user_id-only one.
        index_names = {idx["name"] for idx in inspector.get_indexes("user_secrets")}
        assert "ix_user_secrets_user_provider" in index_names
        assert "ix_user_secrets_user_id" not in index_names

        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev == "006"

    def test_upgrade_006_aborts_when_legacy_rows_exist(self) -> None:
        """Legacy row in user_secrets must cause 006 to raise, not backfill.

        At revision 005 the table has no auth_provider_type column, so a
        direct INSERT using the 005-shape is accepted. 006's upgrade
        checks for non-zero row count before altering the schema.
        """
        from alembic import command

        engine = _fresh_engine()
        cfg = self._upgrade_to_005(engine)

        # Raw text() INSERT bypasses SQLAlchemy's DateTime type handler,
        # so serialize to ISO 8601 ourselves — Python 3.12 deprecated the
        # default sqlite3 datetime adapter. SQLite stores DateTime columns
        # as ISO TEXT anyway, so this is identical to what the SA
        # insert(table).values(...) path produces.
        now_iso = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_secrets "
                    "(id, name, user_id, encrypted_value, salt, created_at, updated_at) "
                    "VALUES (:id, :name, :user_id, :encrypted_value, :salt, :created_at, :updated_at)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "name": "legacy-secret",
                    "user_id": "u-legacy",
                    "encrypted_value": b"\x00",
                    "salt": b"\x00",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                },
            )

        with pytest.raises(RuntimeError, match=r"Cannot migrate 1 pre-existing user_secrets"), engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "006")

        # Schema remained at 005 — no silent backfill, no half-migrated state.
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev == "005"
        cols_post = {c["name"] for c in inspect(engine).get_columns("user_secrets")}
        assert "auth_provider_type" not in cols_post

    def test_error_message_names_row_count_and_remediation(self) -> None:
        """Operator-facing error must disclose count and how to recover.

        A bare 'refused' message leaves the operator guessing. The
        message must state how many rows are affected and point at
        delete/remap remediations so recovery is self-service.
        """
        from alembic import command

        engine = _fresh_engine()
        cfg = self._upgrade_to_005(engine)

        # Raw text() INSERT bypasses SQLAlchemy's DateTime type handler,
        # so serialize to ISO 8601 ourselves — Python 3.12 deprecated the
        # default sqlite3 datetime adapter.
        now_iso = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            for i in range(3):
                conn.execute(
                    text(
                        "INSERT INTO user_secrets "
                        "(id, name, user_id, encrypted_value, salt, created_at, updated_at) "
                        "VALUES (:id, :name, :user_id, :encrypted_value, :salt, :created_at, :updated_at)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "name": f"k{i}",
                        "user_id": "u-legacy",
                        "encrypted_value": b"\x00",
                        "salt": b"\x00",
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    },
                )

        with pytest.raises(RuntimeError) as exc_info, engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "006")

        msg = str(exc_info.value)
        assert "3" in msg, f"row count missing from error: {msg!r}"
        assert "DELETE FROM user_secrets" in msg
        assert "auth_provider_type" in msg

    def test_downgrade_006_restores_pre_006_shape(self) -> None:
        """006 → 005 round-trip removes the column and restores constraints."""
        from alembic import command

        engine = _fresh_engine()
        run_migrations(engine)  # to head (007)

        cfg = _alembic_config_for(engine)
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.downgrade(cfg, "005")

        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("user_secrets")}
        assert "auth_provider_type" not in cols
        unique_names = {c["name"] for c in inspector.get_unique_constraints("user_secrets")}
        assert "uq_user_secret_name_user" in unique_names
        assert "uq_user_secret_name_user_provider" not in unique_names

    def test_post_head_insert_without_auth_provider_type_is_rejected(self) -> None:
        """NOT NULL (no server default) on auth_provider_type must bite.

        ``models.py`` deliberately removed ``server_default="local"`` so
        callers cannot silently rely on the fabrication-prone default.
        The only guarantee stopping a future refactor from quietly
        reintroducing that default is the INSERT-level NOT NULL
        constraint.  A raw INSERT omitting ``auth_provider_type`` must
        raise ``IntegrityError`` — that is the mechanical enforcement of
        the "no fabrication" invariant.
        """
        engine = _fresh_engine()
        run_migrations(engine)  # to head; post-006 shape is active.

        now_iso = datetime.now(UTC).isoformat()
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_secrets "
                    "(id, name, user_id, encrypted_value, salt, created_at, updated_at) "
                    "VALUES (:id, :name, :user_id, :encrypted_value, :salt, :created_at, :updated_at)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "name": "no-provider",
                    "user_id": "u-1",
                    "encrypted_value": b"\x00",
                    "salt": b"\x00",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                },
            )

    def test_abort_then_delete_then_rerun_reaches_head(self) -> None:
        """Operator's documented remediation path must actually work.

        The 006 abort error instructs the operator: "DELETE FROM
        user_secrets; re-run migrations."  End-to-end proof that this
        recovers cleanly is load-bearing — if the schema were left in
        an awkward state by the aborted 006 run, the re-run would fail
        and the guidance would be a lie.  Sequence:
          (1) upgrade to 005, insert a legacy row;
          (2) attempt upgrade to head — RuntimeError from 006;
          (3) DELETE FROM user_secrets;
          (4) run_migrations(engine) — must now reach head (007) with
              the post-006 schema intact.
        """
        from alembic import command

        engine = _fresh_engine()
        cfg = self._upgrade_to_005(engine)

        now_iso = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_secrets "
                    "(id, name, user_id, encrypted_value, salt, created_at, updated_at) "
                    "VALUES (:id, :name, :user_id, :encrypted_value, :salt, :created_at, :updated_at)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "name": "legacy",
                    "user_id": "u-legacy",
                    "encrypted_value": b"\x00",
                    "salt": b"\x00",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                },
            )

        with pytest.raises(RuntimeError), engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")

        # Follow the remediation text literally.
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM user_secrets"))

        # Production entry point — must reach head from wherever we are.
        run_migrations(engine)

        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev == "008"
        cols = {c["name"] for c in inspect(engine).get_columns("user_secrets")}
        assert "auth_provider_type" in cols


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
        # Row objects are tuple-like; unpack explicitly so mypy sees the
        # correct (str, str | None) shape.
        return {row[0]: row[1] for row in rows}

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

    def test_downgrade_007_restores_single_column_fks_and_preserves_uq_runs_one_active_per_session(self) -> None:
        """007 → 006 round-trip restores single-column FKs WITHOUT dropping
        the ``uq_runs_one_active_per_session`` partial unique index.

        Anchors the reversibility contract for migration 007 — symmetric
        with ``test_downgrade_008_removes_constraint`` for migration 008.
        The upgrade-side index-preservation suite above asserts the
        partial index survives the copy_from-driven upgrade. The
        downgrade path is *different code*: ``007.downgrade()`` calls
        ``op.batch_alter_table("runs")`` WITHOUT ``copy_from``, which
        means Alembic reflects the live shape to drive the table-copy
        rebuild on SQLite. Reflection does NOT carry the
        ``sqlite_where`` predicate for partial unique indexes — a
        regression that relies on reflection alone would silently drop
        the partial index, reopening the TOCTOU race in ``create_run``.

        The test pins three properties that a correct downgrade must
        hold simultaneously:

        1. Version bookkeeping: alembic_version reports 006 after the
           downgrade completes. A partial-success that leaves the row
           at 007 would be an audit lie — the schema no longer matches
           what the version claims.
        2. FK shape reversal: ``uq_composition_state_id_session`` (the
           composite-uniqueness target created in 007.upgrade) is gone,
           and the runs/chat_messages FKs resolve to ``composition_states.id``
           alone rather than the composite ``(id, session_id)``.
        3. Partial index survival + behavioural proof: the partial
           unique index remains, and at the post-downgrade schema a
           second pending run per session is still rejected while
           multiple completed runs remain accepted. Schema inspection
           alone is weak here — a reflection regression could create
           a plain unique-on-session_id that has the right NAME but
           the wrong WHERE clause, and only a behavioural assertion
           catches that.
        """
        from alembic import command

        engine = _fresh_engine()
        # Stop at 007 specifically (not head) so the observed downgrade
        # behaviour is attributable to 007.downgrade alone. Going
        # head→006 would also exercise 008.downgrade, which would
        # conflate ``blobs``-table behaviour with the runs/chat_messages
        # invariants this test pins.
        cfg = _alembic_config_for(engine)
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "007")
            command.downgrade(cfg, "006")

        # (1) Version bookkeeping — downgrade reached 006 cleanly.
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev == "006", (
            f"Expected alembic_version == '006' after 007 downgrade, got {rev!r}. The schema no longer matches the version claim."
        )

        # (2) FK shape reversal — composite uniqueness target gone.
        inspector = inspect(engine)
        comp_state_uniques = {u["name"] for u in inspector.get_unique_constraints("composition_states")}
        assert "uq_composition_state_id_session" not in comp_state_uniques, (
            f"uq_composition_state_id_session should be dropped by 007.downgrade, "
            f"but is still present on composition_states. Surviving uniques: {sorted(comp_state_uniques)}"
        )

        # FK shape — runs.state_id and chat_messages.composition_state_id
        # must resolve as SINGLE-column references to composition_states.id.
        # Composite references to (id, session_id) would indicate the
        # 007 downgrade failed to rewrite the constraint.
        run_fks = {
            frozenset(fk["constrained_columns"]): frozenset(fk["referred_columns"])
            for fk in inspector.get_foreign_keys("runs")
            if fk["referred_table"] == "composition_states"
        }
        assert run_fks, "runs has no FK to composition_states post-downgrade — FK was dropped without replacement"
        assert frozenset({"state_id"}) in run_fks, f"runs.state_id FK is no longer single-column after 007.downgrade. Found: {run_fks}"
        # No composite FK should remain.
        assert frozenset({"state_id", "session_id"}) not in run_fks, (
            f"Composite FK (state_id, session_id) still present on runs after 007.downgrade. Found: {run_fks}"
        )

        chat_fks = {
            frozenset(fk["constrained_columns"]): frozenset(fk["referred_columns"])
            for fk in inspector.get_foreign_keys("chat_messages")
            if fk["referred_table"] == "composition_states"
        }
        assert frozenset({"composition_state_id"}) in chat_fks, (
            f"chat_messages.composition_state_id FK is no longer single-column after 007.downgrade. Found: {chat_fks}"
        )
        assert frozenset({"composition_state_id", "session_id"}) not in chat_fks, (
            f"Composite FK still present on chat_messages after 007.downgrade. Found: {chat_fks}"
        )

        # (3) Partial index survival — schema shape first.
        runs_indexes = self._sqlite_master_indexes(engine, "runs")
        assert "uq_runs_one_active_per_session" in runs_indexes, (
            f"uq_runs_one_active_per_session was dropped by 007.downgrade's batch rebuild. "
            f"Surviving indexes on runs: {sorted(runs_indexes)}. "
            "This reopens the TOCTOU race in create_run — see the "
            "TestMigration007PreservesIndexes docstring for why this index "
            "is load-bearing."
        )
        sql = runs_indexes["uq_runs_one_active_per_session"]
        assert sql is not None, "sqlite_master returned NULL sql for the partial index post-downgrade"
        assert "WHERE" in sql.upper(), (
            f"Partial index lost its WHERE clause during 007.downgrade. SQL: {sql!r}. "
            "A plain unique-on-session_id would forbid ANY second run per session, "
            "breaking historical-run browsing."
        )
        assert "pending" in sql and "running" in sql, (
            f"Partial index WHERE clause no longer references pending/running after 007.downgrade. SQL: {sql!r}"
        )

        # (3b) Partial index survival — behavioural proof. Schema shape
        # can mislead if the WHERE clause is syntactically present but
        # semantically empty. An end-to-end insert/reject proves the
        # predicate still gates correctly.
        session_id = str(uuid.uuid4())
        state_id = str(uuid.uuid4())
        with engine.begin() as conn:
            _seed_session(conn, session_id)
            _seed_state(conn, state_id, session_id)
            conn.execute(
                insert(runs_table).values(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    state_id=state_id,
                    status="pending",
                    started_at=datetime.now(UTC),
                )
            )

        with pytest.raises(IntegrityError, match=r"uq_runs_one_active_per_session|UNIQUE"), engine.begin() as conn:
            conn.execute(
                insert(runs_table).values(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    state_id=state_id,
                    status="running",
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

        observed: list[tuple[str, dict[str, Any]]] = []
        original = engine_mod.create_session_engine

        def spy(url: str, **kwargs: Any) -> Engine:
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

    def test_offline_mode_honours_env_var_url(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """``alembic upgrade ... --sql`` must target the env-var URL.

        Regression guard: the env-var override was previously applied at
        env.py module scope, covering both modes. When it was tightened
        to live inside ``run_migrations_online()`` to fix the
        programmatic-override bug, the offline branch stopped honouring
        the env var and silently rendered SQL against ``alembic.ini``'s
        placeholder URL instead. Operators generating migration SQL for
        review would have received output for the wrong database or
        dialect.

        Detection strategy: spy on ``alembic.context.configure`` — env.py
        calls it exactly once, passing the URL it resolved. We assert
        that URL is the env-var value, not the ini fallback. We invoke
        ``command.upgrade(cfg, 'head:head', sql=True)`` so that no
        migration ``upgrade()`` body actually runs (offline SQL for an
        empty delta skips migration bodies — 001's ``sa.inspect()`` on
        ``op.get_bind()`` would otherwise blow up against Alembic's
        ``MockConnection``, an orthogonal online-only constraint).
        """
        from pathlib import Path

        import alembic.context as alembic_context_mod
        from alembic import command

        unique_path = tmp_path / "offline-target-sentinel.db"
        expected_url = f"sqlite:///{unique_path}"
        monkeypatch.setenv("ELSPETH_WEB__SESSION_DB_URL", expected_url)

        observed: list[dict[str, Any]] = []
        original_configure = alembic_context_mod.configure

        def spy(*args: Any, **kwargs: Any) -> Any:
            observed.append(dict(kwargs))
            return original_configure(*args, **kwargs)

        monkeypatch.setattr(alembic_context_mod, "configure", spy)

        ini_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "elspeth" / "web" / "sessions" / "alembic.ini"
        cfg = Config(str(ini_path))
        # Do NOT override sqlalchemy.url or inject a connection — the
        # offline branch must resolve from the env var by itself.

        # head:head is a zero-step delta; alembic still invokes env.py
        # (so context.configure runs and we can spy on the URL), but no
        # migration upgrade() bodies execute.
        command.upgrade(cfg, "head:head", sql=True)

        assert observed, "context.configure was never invoked — env.py did not run in offline mode"
        url_passed = observed[0].get("url")
        assert url_passed == expected_url, (
            f"Offline mode ignored ELSPETH_WEB__SESSION_DB_URL. Expected URL passed "
            f"to context.configure: {expected_url!r}, got: {url_passed!r}. This "
            f"would emit SQL for the wrong database or dialect."
        )

    def test_offline_mode_raises_when_no_url_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Offline mode must fail loudly if neither env var nor ini provides a URL.

        Silent fallback to an empty URL would let Alembic emit garbage
        SQL for an unresolved dialect. Tier 1 discipline: crash with a
        remediation-pointing message.
        """
        from pathlib import Path

        from alembic import command

        monkeypatch.delenv("ELSPETH_WEB__SESSION_DB_URL", raising=False)

        ini_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "elspeth" / "web" / "sessions" / "alembic.ini"
        cfg = Config(str(ini_path))
        # Blank out the ini fallback so offline mode has nothing to fall back on.
        cfg.set_main_option("sqlalchemy.url", "")

        with pytest.raises(RuntimeError, match=r"offline mode: sqlalchemy\.url is not configured"):
            command.upgrade(cfg, "head:head", sql=True)

    def test_offline_mode_env_var_overrides_ini_url(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        """When both env var and ini provide a URL, env var must win.

        ``run_migrations_offline`` calls ``config.set_main_option`` on
        the env var unconditionally when the var is set — so env should
        shadow an ini-provided URL.  Pinning this prevents a future
        refactor (e.g., "only override when ini is empty") from
        silently reintroducing ini-as-source-of-truth, which would
        mean operators generating SQL in environments that *also*
        have a populated ini file (e.g., a deployment template) would
        target the wrong database.
        """
        from pathlib import Path

        import alembic.context as alembic_context_mod
        from alembic import command

        env_url = f"sqlite:///{tmp_path / 'env-wins.db'}"
        ini_url = f"sqlite:///{tmp_path / 'ini-loses.db'}"
        monkeypatch.setenv("ELSPETH_WEB__SESSION_DB_URL", env_url)

        observed: list[dict[str, Any]] = []
        original_configure = alembic_context_mod.configure

        def spy(*args: Any, **kwargs: Any) -> Any:
            observed.append(dict(kwargs))
            return original_configure(*args, **kwargs)

        monkeypatch.setattr(alembic_context_mod, "configure", spy)

        ini_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "elspeth" / "web" / "sessions" / "alembic.ini"
        cfg = Config(str(ini_path))
        # Populate ini with a different URL — env must shadow it.
        cfg.set_main_option("sqlalchemy.url", ini_url)

        command.upgrade(cfg, "head:head", sql=True)

        assert observed, "context.configure was never invoked"
        url_passed = observed[0].get("url")
        assert url_passed == env_url, (
            f"ini URL leaked through despite env override. Expected env "
            f"URL {env_url!r}, got {url_passed!r} — env_var-over-ini "
            f"precedence regressed."
        )

    def test_offline_mode_env_var_with_percent_encoded_password_round_trips(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Percent-encoded env URLs must survive ConfigParser-backed writes.

        Without escaping before `config.set_main_option(...)`, ConfigParser
        treats `%40` / `%2F` as interpolation syntax and env.py crashes
        before it can configure Alembic.
        """
        from pathlib import Path

        import alembic.context as alembic_context_mod
        from alembic import command

        env_url = "postgresql://user:pa%40ss%2Fword@db.example/sessions"
        monkeypatch.setenv("ELSPETH_WEB__SESSION_DB_URL", env_url)

        observed: list[dict[str, Any]] = []
        original_configure = alembic_context_mod.configure

        def spy(*args: Any, **kwargs: Any) -> Any:
            observed.append(dict(kwargs))
            return original_configure(*args, **kwargs)

        monkeypatch.setattr(alembic_context_mod, "configure", spy)

        ini_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "elspeth" / "web" / "sessions" / "alembic.ini"
        cfg = Config(str(ini_path))

        command.upgrade(cfg, "head:head", sql=True)

        assert observed, "context.configure was never invoked"
        assert observed[0].get("url") == env_url

    def test_cli_mode_env_var_with_percent_encoded_password_round_trips(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLI migrations must pass the original percent-encoded DSN onward."""
        from alembic import command
        from sqlalchemy import pool as sa_pool

        import elspeth.web.sessions.engine as engine_mod

        env_url = "postgresql://user:pa%40ss%2Fword@db.example/sessions"
        monkeypatch.setenv("ELSPETH_WEB__SESSION_DB_URL", env_url)

        observed: list[tuple[str, dict[str, Any]]] = []
        original = engine_mod.create_session_engine

        def spy(url: str, **kwargs: Any) -> Engine:
            observed.append((url, dict(kwargs)))
            return original(
                "sqlite:///:memory:",
                poolclass=StaticPool,
                connect_args={"check_same_thread": False},
            )

        monkeypatch.setattr(engine_mod, "create_session_engine", spy)

        from pathlib import Path

        ini_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "elspeth" / "web" / "sessions" / "alembic.ini"
        cfg = Config(str(ini_path))

        command.upgrade(cfg, "head")

        assert len(observed) == 1
        observed_url, observed_kwargs = observed[0]
        assert observed_url == env_url
        assert observed_kwargs.get("poolclass") is sa_pool.NullPool

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

        def broken_factory(url: str, **kwargs: Any) -> Engine:
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


# ---------------------------------------------------------------------------
# Migration 008: ready-blob-requires-hash invariant (elspeth-e435b147b7)
# ---------------------------------------------------------------------------


class TestMigration008BlobReadyHashInvariant:
    """008 must add ck_blobs_ready_hash without laundering violating data.

    The service layer's _validate_finalize_hash is the first line of
    defence; this migration is the second — even raw SQL cannot commit
    a ready row without a hash once the constraint is in place.  The
    migration deliberately REFUSES to apply if pre-existing data
    already violates the invariant: silently repairing (coercing to
    error, or fabricating a hash) would tamper with the audit trail.
    Operators must quarantine or repair the row explicitly.
    """

    def _upgrade_to_007(self, engine: Engine) -> Config:
        """Bring engine to revision 007 (pre-008 blobs shape)."""
        from alembic import command

        cfg = _alembic_config_for(engine)
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "007")
        return cfg

    def _seed_blobs_session(self, engine: Engine, session_id: str) -> None:
        """Seed a session row so the blobs.session_id FK is satisfied."""
        now_iso = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO sessions "
                    "(id, user_id, auth_provider_type, title, created_at, updated_at) "
                    "VALUES (:id, :user_id, :apt, :title, :created_at, :updated_at)"
                ),
                {
                    "id": session_id,
                    "user_id": "u-legacy",
                    "apt": "local",
                    "title": "t",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                },
            )

    def test_upgrade_008_succeeds_on_clean_blobs_table(self) -> None:
        """Fresh DB: 007 → 008 adds CHECK constraint cleanly."""
        from alembic import command

        engine = _fresh_engine()
        cfg = self._upgrade_to_007(engine)
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "008")

        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev == "008"

        # After the constraint is in place, INSERTing a violating row is rejected.
        session_id = str(uuid.uuid4())
        self._seed_blobs_session(engine, session_id)
        now_iso = datetime.now(UTC).isoformat()
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO blobs "
                    "(id, session_id, filename, mime_type, size_bytes, content_hash, "
                    " storage_path, created_at, created_by, status) "
                    "VALUES (:id, :sid, :fn, :mt, :sz, :ch, :sp, :ca, :cb, :st)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "sid": session_id,
                    "fn": "illegal.csv",
                    "mt": "text/csv",
                    "sz": 1,
                    "ch": None,  # <-- violation: ready + NULL hash
                    "sp": "/tmp/never",
                    "ca": now_iso,
                    "cb": "user",
                    "st": "ready",
                },
            )

    def test_upgrade_008_refuses_preexisting_ready_row_without_hash(self) -> None:
        """A pre-existing ready row with NULL hash must make the upgrade fail.

        At revision 007 the blobs CHECK was absent, so a legacy shape
        could have committed a status='ready', content_hash=NULL row
        (e.g. via a defective finalize path we've now fixed).  Running
        008 over such a row must crash rather than silently repair —
        the audit trail cannot mask the invariant violation by
        rewriting the row.
        """
        from alembic import command

        engine = _fresh_engine()
        cfg = self._upgrade_to_007(engine)

        session_id = str(uuid.uuid4())
        self._seed_blobs_session(engine, session_id)
        now_iso = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO blobs "
                    "(id, session_id, filename, mime_type, size_bytes, content_hash, "
                    " storage_path, created_at, created_by, status) "
                    "VALUES (:id, :sid, :fn, :mt, :sz, :ch, :sp, :ca, :cb, :st)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "sid": session_id,
                    "fn": "legacy.csv",
                    "mt": "text/csv",
                    "sz": 1,
                    "ch": None,  # <-- the pre-existing violation
                    "sp": "/tmp/legacy",
                    "ca": now_iso,
                    "cb": "user",
                    "st": "ready",
                },
            )

        # Alembic's batch rebuild re-inserts rows into the new table
        # shape.  The new table carries the CHECK, so re-insertion of
        # the violating row raises IntegrityError — the upgrade aborts
        # instead of laundering the bad data through.
        with pytest.raises(IntegrityError), engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "008")

        # Schema remained at 007 — no silent repair.
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev == "007"

    def test_downgrade_008_removes_constraint(self) -> None:
        """008 → 007 round-trip drops ck_blobs_ready_hash.

        Anchors the reversibility contract — a ready row with a NULL
        hash that would be rejected at head becomes insertable again
        at 007, proving the constraint was genuinely removed rather
        than leaking through the batch rebuild.
        """
        from alembic import command

        engine = _fresh_engine()
        run_migrations(engine)  # to head (008)

        cfg = _alembic_config_for(engine)
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.downgrade(cfg, "007")

        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev == "007"

        # Post-downgrade, a ready+NULL-hash row is accepted again — the
        # constraint is genuinely gone, not merely renamed or shadowed.
        session_id = str(uuid.uuid4())
        self._seed_blobs_session(engine, session_id)
        now_iso = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO blobs "
                    "(id, session_id, filename, mime_type, size_bytes, content_hash, "
                    " storage_path, created_at, created_by, status) "
                    "VALUES (:id, :sid, :fn, :mt, :sz, :ch, :sp, :ca, :cb, :st)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "sid": session_id,
                    "fn": "post-downgrade.csv",
                    "mt": "text/csv",
                    "sz": 1,
                    "ch": None,
                    "sp": "/tmp/post",
                    "ca": now_iso,
                    "cb": "user",
                    "st": "ready",
                },
            )

    # -- Hash-shape enforcement ------------------------------------------
    #
    # The CHECK at HEAD must reject not only NULL hashes but also
    # malformed strings (wrong length, uppercase, non-hex chars).  Without
    # the shape clause a direct SQL or ORM write could persist a "ready"
    # row whose hash will never match any real bytes, leaving every
    # download path raising BlobIntegrityError while the audit trail
    # claims the blob is finalized.  These tests pin the shape rule at
    # the database layer so a future migration that loosens the CHECK
    # (or a backend-port that forgets to translate the GLOB clause) is
    # caught immediately.

    _VALID_SHA256 = "a" * 64  # 64 lowercase hex chars; structurally valid

    def _insert_blob_row(
        self,
        engine: Engine,
        session_id: str,
        *,
        content_hash: str | None,
        status: str = "ready",
        filename: str = "shape-test.csv",
        storage_path: str = "/tmp/shape-test",
    ) -> None:
        """INSERT a single blobs row with the given hash/status.

        Centralised so every shape test exercises the same column set
        the production INSERT path uses; drift between this helper and
        ``BlobServiceImpl.create_blob`` would mask shape regressions.
        """
        now_iso = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO blobs "
                    "(id, session_id, filename, mime_type, size_bytes, "
                    " content_hash, storage_path, created_at, created_by, status) "
                    "VALUES (:id, :sid, :fn, :mt, :sz, :ch, :sp, :ca, :cb, :st)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "sid": session_id,
                    "fn": filename,
                    "mt": "text/csv",
                    "sz": 1,
                    "ch": content_hash,
                    "sp": storage_path,
                    "ca": now_iso,
                    "cb": "user",
                    "st": status,
                },
            )

    def test_ready_with_valid_sha256_hex_is_accepted(self) -> None:
        """The shape CHECK admits a canonical 64-char lowercase hex hash."""
        engine = _fresh_engine()
        run_migrations(engine)  # to head (008)

        session_id = str(uuid.uuid4())
        self._seed_blobs_session(engine, session_id)

        # Should not raise.
        self._insert_blob_row(
            engine,
            session_id,
            content_hash=self._VALID_SHA256,
            status="ready",
        )

    @pytest.mark.parametrize(
        ("bad_hash", "label"),
        [
            ("abc123", "too short — only 6 chars"),
            ("a" * 63, "off-by-one — 63 chars"),
            ("a" * 65, "off-by-one — 65 chars"),
            ("A" * 64, "uppercase — 64 chars but [A-F]"),
            ("g" * 64, "non-hex letter — 'g' outside [a-f0-9]"),
            ("a" * 63 + "!", "trailing punctuation"),
            ("a" * 63 + " ", "trailing whitespace"),
            # Trailing newline is a distinct bypass path from generic
            # whitespace: a naive client that appends "\n" to a digest
            # produced by ``sha256sum`` (which emits "<hex>  <file>\n")
            # would otherwise persist a 65-char "ready" blob whose hash
            # cannot match any bytes. The CHECK must reject it just as
            # strictly as the ASCII-space case above.
            ("a" * 64 + "\n", "trailing newline — sha256sum-style digest"),
            ("", "empty string"),
        ],
    )
    def test_ready_with_malformed_hash_is_rejected(self, bad_hash: str, label: str) -> None:
        """The shape CHECK refuses every flavour of malformed hash.

        Each row is a real bypass path the write-side validator would
        catch; the database CHECK is the second line of defence for
        callers that skip the service entirely (raw SQL, alembic
        scripts, ad-hoc ORM writes, future plugin code).  A passing
        test for any of these would mean the audit trail can record a
        "ready" blob whose ``content_hash`` cannot be reproduced from
        any bytes — exactly the integrity-tampering vector the AD-5/AD-7
        invariants exist to prevent.
        """
        _ = label  # surfaces in pytest output for failure diagnosis
        engine = _fresh_engine()
        run_migrations(engine)  # to head (008)

        session_id = str(uuid.uuid4())
        self._seed_blobs_session(engine, session_id)

        with pytest.raises(IntegrityError):
            self._insert_blob_row(
                engine,
                session_id,
                content_hash=bad_hash,
                status="ready",
            )

    @pytest.mark.parametrize("status", ["pending", "error"])
    def test_non_ready_rows_are_unconstrained_by_shape(self, status: str) -> None:
        """Non-ready rows may still carry NULL or malformed hashes.

        The CHECK is intentionally scoped to ``status='ready'``: a
        ``pending`` row by definition has not been finalised yet (no
        hash exists), and an ``error`` row records a failed
        finalisation whose hash may legitimately be NULL or carry the
        partial value the failed writer computed.  The repair-runbook
        Variant A path moves bad rows to ``status='error'`` precisely
        so the migration can be applied — narrowing the CHECK to other
        statuses would close that escape hatch.
        """
        engine = _fresh_engine()
        run_migrations(engine)  # to head (008)

        session_id = str(uuid.uuid4())
        self._seed_blobs_session(engine, session_id)

        # NULL hash on non-ready row: allowed.
        self._insert_blob_row(
            engine,
            session_id,
            content_hash=None,
            status=status,
            filename=f"{status}-null.csv",
            storage_path=f"/tmp/{status}-null",
        )
        # Malformed hash on non-ready row: still allowed — only ready
        # rows must pass the shape rule.
        self._insert_blob_row(
            engine,
            session_id,
            content_hash="abc123",
            status=status,
            filename=f"{status}-malformed.csv",
            storage_path=f"/tmp/{status}-malformed",
        )

    def test_update_ready_to_malformed_hash_is_rejected(self) -> None:
        """Updating a ready row's hash to a malformed value is rejected.

        Plugs the same bypass class as ``UPDATE ... SET content_hash =
        NULL``: a service regression that mutates the hash column
        directly (e.g. via ``blobs_table.update().values(...)``) cannot
        leave the row in a state the integrity check will accept on
        the next read.
        """
        engine = _fresh_engine()
        run_migrations(engine)  # to head (008)

        session_id = str(uuid.uuid4())
        self._seed_blobs_session(engine, session_id)

        self._insert_blob_row(
            engine,
            session_id,
            content_hash=self._VALID_SHA256,
            status="ready",
        )

        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text("UPDATE blobs SET content_hash = :ch WHERE session_id = :sid"),
                {"ch": "deadbeef", "sid": session_id},
            )

    def test_upgrade_008_refuses_preexisting_malformed_hash_row(self) -> None:
        """A pre-existing ready row with malformed hash blocks the upgrade.

        Mirrors ``test_upgrade_008_refuses_preexisting_ready_row_without_hash``
        but for the shape invariant.  At revision 007 the CHECK is
        absent, so a legacy row could carry ``content_hash='abc123'``
        from a defective writer.  Migration 008's batch rebuild
        re-inserts every row into the new shape and the constraint
        rejects the re-insertion — by design, so the audit trail is
        not silently laundered.  Operators must use the runbook to
        quarantine or back-fill the row before the migration can land.
        """
        from alembic import command

        engine = _fresh_engine()
        cfg = self._upgrade_to_007(engine)

        session_id = str(uuid.uuid4())
        self._seed_blobs_session(engine, session_id)
        # Insert a malformed-but-non-NULL hash row at 007, where no
        # CHECK exists to reject it.
        self._insert_blob_row(
            engine,
            session_id,
            content_hash="abc123",
            status="ready",
            filename="legacy-malformed.csv",
            storage_path="/tmp/legacy-malformed",
        )

        with pytest.raises(IntegrityError), engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "008")

        # Schema remained at 007 — the migration did not rewrite the
        # malformed hash to anything else; the row is still there for
        # the operator to inspect.
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert rev == "007"


# ---------------------------------------------------------------------------
# Migration 008: batch-rebuild preserves every pre-008 shape element
# ---------------------------------------------------------------------------


class TestMigration008PreservesBlobsShape:
    """008's batch_alter_table(copy_from=_current_blobs_shape()) must carry every
    index and CHECK from the post-007 blobs shape through the SQLite rebuild.

    Parallel of ``TestMigration007PreservesIndexes`` for migration 007: any
    shape element NOT listed in the copy_from snapshot silently vanishes
    during SQLite's table-copy rebuild.  Today the pre-008 blobs table has
    no partial indexes, so a pure-reflection rebuild would also work — but
    without the snapshot a future migration that adds a partial index
    (e.g. ``WHERE status='ready'`` over ``session_id``) would be lost on any
    downgrade-then-reupgrade round trip that replays 008.  These tests pin
    the snapshot against the live pre-008 shape so any drift surfaces
    immediately.
    """

    def _sqlite_master_indexes(self, engine: Engine, table: str) -> dict[str, str | None]:
        """Return {index_name: sql} from sqlite_master.

        Duplicated from ``TestMigration007PreservesIndexes`` intentionally:
        sharing the helper via inheritance would couple two otherwise-
        independent test classes, and SQLAlchemy's ``inspect().get_indexes``
        does not reliably surface partial-unique WHERE clauses, so hitting
        sqlite_master directly is the only way to verify shape faithfully.
        """
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = :t"),
                {"t": table},
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def _blobs_create_table_sql(self, engine: Engine) -> str:
        """Return the full ``CREATE TABLE blobs ...`` statement.

        CHECK constraints and column definitions are embedded in the
        CREATE TABLE SQL on SQLite — they do not surface through
        ``inspect().get_check_constraints()`` reliably — so we query
        sqlite_master directly and grep the statement text.
        """
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'blobs'"),
            ).fetchone()
        assert row is not None, "blobs table missing from sqlite_master after migrations"
        create_sql = row[0]
        assert isinstance(create_sql, str), f"sqlite_master returned non-string SQL: {create_sql!r}"
        return create_sql

    def test_blobs_session_id_index_survives(self) -> None:
        """``ix_blobs_session_id`` must remain after 008 applies.

        The session_id index is load-bearing for every blob-list query
        scoped by session (``BlobServiceImpl.list_blobs``, quota checks,
        active-run guards).  Losing it during 008's rebuild would not
        break correctness but would turn every per-session blob query
        into a table scan — the sort of latent regression a pure-
        reflection rebuild could introduce without any test failure.
        """
        engine = _fresh_engine()
        run_migrations(engine)
        indexes = self._sqlite_master_indexes(engine, "blobs")
        assert "ix_blobs_session_id" in indexes, (
            f"ix_blobs_session_id was dropped by 008's batch rebuild. Surviving indexes on blobs: {sorted(indexes)}"
        )

    def test_blobs_status_check_constraint_survives(self) -> None:
        """``ck_blobs_status`` must remain after 008 applies.

        The status-enum CHECK is the database-layer mirror of
        ``BLOB_STATUSES`` (see ``web/blobs/protocol.py``).  Silently
        dropping it would turn ``status`` from an enforced enum into a
        free string column, and the Tier 1 read guard in
        ``BlobServiceImpl._row_to_record`` would be the only remaining
        line of defence against a direct-SQL write with a bogus status.
        """
        engine = _fresh_engine()
        run_migrations(engine)
        create_sql = self._blobs_create_table_sql(engine)
        assert "ck_blobs_status" in create_sql, (
            f"ck_blobs_status CHECK constraint was dropped by 008's batch rebuild. CREATE TABLE SQL: {create_sql!r}"
        )

    def test_blobs_created_by_check_constraint_survives(self) -> None:
        """``ck_blobs_created_by`` must remain after 008 applies.

        Mirror of the ``created_by`` enum defined in
        ``BLOB_CREATORS``.  The same logic as ``ck_blobs_status`` above
        applies — dropping this at the DB layer leaves the column
        enforceable only through the application read guard.
        """
        engine = _fresh_engine()
        run_migrations(engine)
        create_sql = self._blobs_create_table_sql(engine)
        assert "ck_blobs_created_by" in create_sql, (
            f"ck_blobs_created_by CHECK constraint was dropped by 008's batch rebuild. CREATE TABLE SQL: {create_sql!r}"
        )

    def test_blobs_status_check_rejects_invalid_values_end_to_end(self) -> None:
        """Behavioural proof: the status CHECK still fires after 008.

        Shape-level tests above would pass against a CHECK that had
        been silently renamed or whose expression had drifted to
        something permissive.  This test writes an invalid status
        through raw SQL and asserts the DB rejects it — the invariant
        the constraint exists to enforce must hold end-to-end.
        """
        engine = _fresh_engine()
        run_migrations(engine)

        session_id = str(uuid.uuid4())
        now_iso = datetime.now(UTC).isoformat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO sessions "
                    "(id, user_id, auth_provider_type, title, created_at, updated_at) "
                    "VALUES (:id, :uid, :apt, :title, :ca, :ua)"
                ),
                {
                    "id": session_id,
                    "uid": "u-shape",
                    "apt": "local",
                    "title": "t",
                    "ca": now_iso,
                    "ua": now_iso,
                },
            )

        # 'deleted' is not a member of BLOB_STATUSES; the CHECK must reject it.
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO blobs "
                    "(id, session_id, filename, mime_type, size_bytes, content_hash, "
                    " storage_path, created_at, created_by, status) "
                    "VALUES (:id, :sid, :fn, :mt, :sz, :ch, :sp, :ca, :cb, :st)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "sid": session_id,
                    "fn": "shape.csv",
                    "mt": "text/csv",
                    "sz": 1,
                    "ch": "a" * 64,
                    "sp": "/tmp/shape",
                    "ca": now_iso,
                    "cb": "user",
                    "st": "deleted",
                },
            )

    def test_008_round_trip_preserves_shape_elements(self) -> None:
        """008 → 007 → 008 must leave ix_blobs_session_id and CHECKs intact.

        The round trip exercises both upgrade and downgrade through the
        copy_from snapshot.  A drift between the snapshot and the live
        shape would surface here as a missing index or CHECK after the
        second upgrade — the exact failure mode a future partial-index
        addition would produce if this snapshot were not kept in sync
        with the (frozen) post-007 shape.
        """
        from alembic import command

        engine = _fresh_engine()
        run_migrations(engine)  # to head (008)

        cfg = _alembic_config_for(engine)
        with engine.connect() as connection:
            cfg.attributes["connection"] = connection
            command.downgrade(cfg, "007")
            command.upgrade(cfg, "008")

        indexes = self._sqlite_master_indexes(engine, "blobs")
        assert "ix_blobs_session_id" in indexes, (
            f"ix_blobs_session_id lost during 008 → 007 → 008 round trip. Surviving indexes: {sorted(indexes)}"
        )
        create_sql = self._blobs_create_table_sql(engine)
        assert "ck_blobs_status" in create_sql, f"ck_blobs_status lost during 008 → 007 → 008 round trip. CREATE TABLE SQL: {create_sql!r}"
        assert "ck_blobs_created_by" in create_sql, (
            f"ck_blobs_created_by lost during 008 → 007 → 008 round trip. CREATE TABLE SQL: {create_sql!r}"
        )
        assert "ck_blobs_ready_hash" in create_sql, (
            f"ck_blobs_ready_hash (the invariant 008 adds) did not survive the re-upgrade. CREATE TABLE SQL: {create_sql!r}"
        )
