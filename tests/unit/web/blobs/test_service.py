"""Tests for BlobServiceImpl — audit-critical blob persistence and lifecycle.

Security boundaries tested:
- Content hash integrity (AD-5/AD-7: hash must match for lineage verification)
- Session-scoped isolation (blobs cannot leak across sessions)
- Active-run deletion guard (cannot destroy evidence during a live run)
- Filename sanitization (path traversal defense at the storage layer)
- Status lifecycle (pending -> ready/error only; no backwards transitions)
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from elspeth.web.blobs.protocol import (
    BlobActiveRunError,
    BlobNotFoundError,
)
from elspeth.web.blobs.service import (
    BlobServiceImpl,
    content_hash,
    sanitize_filename,
)
from elspeth.web.sessions.models import metadata, sessions_table

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    """In-memory SQLite engine with all session tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    metadata.create_all(engine)
    return engine


@pytest.fixture()
def session_id(db_engine) -> UUID:
    """Insert a session row and return its ID — blobs have FK to sessions."""
    sid = str(uuid4())
    now = datetime.now(UTC)
    with db_engine.begin() as conn:
        conn.execute(
            sessions_table.insert().values(
                id=sid,
                user_id="test-user",
                auth_provider_type="local",
                title="Test Session",
                created_at=now,
                updated_at=now,
            )
        )
    return UUID(sid)


@pytest.fixture()
def blob_service(db_engine, tmp_path) -> BlobServiceImpl:
    """BlobServiceImpl backed by the shared engine and a temp directory."""
    return BlobServiceImpl(db_engine, tmp_path)


# ---------------------------------------------------------------------------
# sanitize_filename — path traversal defense
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    """B5: filename sanitization prevents path traversal at the storage layer."""

    def test_path_traversal_strips_directory_components(self) -> None:
        assert sanitize_filename("../../etc/passwd") == "passwd"

    def test_absolute_path_strips_to_basename(self) -> None:
        assert sanitize_filename("/absolute/path/file.csv") == "file.csv"

    def test_normal_filename_passes_through(self) -> None:
        assert sanitize_filename("normal.csv") == "normal.csv"

    def test_dot_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid filename"):
            sanitize_filename(".")

    def test_dotdot_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid filename"):
            sanitize_filename("..")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid filename"):
            sanitize_filename("")

    def test_long_filename_truncated(self) -> None:
        long_name = "a" * 300 + ".csv"
        result = sanitize_filename(long_name)
        assert len(result.encode("utf-8")) <= 200


# ---------------------------------------------------------------------------
# content_hash — audit integrity
# ---------------------------------------------------------------------------


class TestContentHash:
    """AD-5/AD-7: content hash must be SHA-256 for lineage verification."""

    def test_known_input(self) -> None:
        expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        assert content_hash(b"hello") == expected

    def test_stability(self) -> None:
        data = b"audit-critical-content"
        assert content_hash(data) == content_hash(data)

    def test_empty_bytes(self) -> None:
        expected = hashlib.sha256(b"").hexdigest()
        assert content_hash(b"") == expected


# ---------------------------------------------------------------------------
# create_blob + read_blob_content — round-trip integrity
# ---------------------------------------------------------------------------


class TestCreateAndRead:
    """Blob creation writes to filesystem and DB; read returns identical bytes."""

    @pytest.mark.asyncio
    async def test_create_blob_and_read(self, blob_service, session_id, tmp_path) -> None:
        content = b"col1,col2\na,b\nc,d"
        record = await blob_service.create_blob(
            session_id=session_id,
            filename="data.csv",
            content=content,
            mime_type="text/csv",
            created_by="user",
        )

        # Record fields
        assert isinstance(record.id, UUID)
        assert record.session_id == session_id
        assert record.filename == "data.csv"
        assert record.mime_type == "text/csv"
        assert record.size_bytes == len(content)
        assert record.status == "ready"
        assert record.created_by == "user"

        # Read back content
        read_back = await blob_service.read_blob_content(record.id)
        assert read_back == content

        # File exists on disk
        from pathlib import Path

        assert Path(record.storage_path).exists()

    @pytest.mark.asyncio
    async def test_create_blob_stores_correct_hash(self, blob_service, session_id) -> None:
        """AD-7: stored hash must match content_hash() for the same bytes."""
        content = b"audit-trail-integrity-check"
        record = await blob_service.create_blob(
            session_id=session_id,
            filename="audit.txt",
            content=content,
            mime_type="text/plain",
            created_by="user",
        )
        assert record.content_hash == content_hash(content)


# ---------------------------------------------------------------------------
# list_blobs — session-scoped isolation
# ---------------------------------------------------------------------------


class TestListBlobs:
    """Session scoping: blobs from one session must not leak into another."""

    @pytest.mark.asyncio
    async def test_list_blobs_returns_session_scoped(self, blob_service, db_engine) -> None:
        now = datetime.now(UTC)
        s1_id = UUID(str(uuid4()))
        s2_id = UUID(str(uuid4()))

        with db_engine.begin() as conn:
            for sid, uid, title in [
                (str(s1_id), "user-a", "Session 1"),
                (str(s2_id), "user-b", "Session 2"),
            ]:
                conn.execute(
                    sessions_table.insert().values(
                        id=sid,
                        user_id=uid,
                        auth_provider_type="local",
                        title=title,
                        created_at=now,
                        updated_at=now,
                    )
                )

        await blob_service.create_blob(
            session_id=s1_id,
            filename="s1.csv",
            content=b"session-1",
            mime_type="text/csv",
            created_by="user",
        )
        await blob_service.create_blob(
            session_id=s2_id,
            filename="s2.csv",
            content=b"session-2",
            mime_type="text/csv",
            created_by="user",
        )

        s1_blobs = await blob_service.list_blobs(s1_id)
        s2_blobs = await blob_service.list_blobs(s2_id)

        assert len(s1_blobs) == 1
        assert s1_blobs[0].filename == "s1.csv"
        assert len(s2_blobs) == 1
        assert s2_blobs[0].filename == "s2.csv"


# ---------------------------------------------------------------------------
# delete_blob — file cleanup and active-run guard
# ---------------------------------------------------------------------------


class TestDeleteBlob:
    """Deletion removes file and record; active-run guard prevents evidence destruction."""

    @pytest.mark.asyncio
    async def test_delete_blob_removes_file_and_record(self, blob_service, session_id) -> None:
        from pathlib import Path

        record = await blob_service.create_blob(
            session_id=session_id,
            filename="delete-me.csv",
            content=b"temporary",
            mime_type="text/csv",
            created_by="user",
        )

        storage = Path(record.storage_path)
        assert storage.exists()

        await blob_service.delete_blob(record.id)

        assert not storage.exists()
        with pytest.raises(BlobNotFoundError):
            await blob_service.get_blob(record.id)

    @pytest.mark.asyncio
    async def test_delete_blob_rejects_when_active_run_linked(self, blob_service, session_id, db_engine) -> None:
        """Active-run guard: cannot delete a blob that is evidence for a live run."""
        from elspeth.web.sessions.models import (
            blob_run_links_table,
            composition_states_table,
            runs_table,
        )

        record = await blob_service.create_blob(
            session_id=session_id,
            filename="evidence.csv",
            content=b"important",
            mime_type="text/csv",
            created_by="user",
        )

        # Insert a composition state (runs FK to composition_states)
        state_id = str(uuid4())
        session_id_str = str(session_id)
        run_id = str(uuid4())

        with db_engine.begin() as conn:
            conn.execute(
                composition_states_table.insert().values(
                    id=state_id,
                    session_id=session_id_str,
                    version=1,
                    is_valid=True,
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
            conn.execute(
                runs_table.insert().values(
                    id=run_id,
                    session_id=session_id_str,
                    state_id=state_id,
                    status="running",
                    started_at=datetime(2026, 1, 1, tzinfo=UTC),
                    rows_processed=0,
                    rows_failed=0,
                )
            )
            conn.execute(
                blob_run_links_table.insert().values(
                    blob_id=str(record.id),
                    run_id=run_id,
                    direction="input",
                )
            )

        with pytest.raises(BlobActiveRunError):
            await blob_service.delete_blob(record.id)

    @pytest.mark.asyncio
    async def test_delete_blob_allows_when_completed_run_linked(self, blob_service, session_id, db_engine) -> None:
        """Completed runs do not block deletion — evidence is already recorded."""
        from elspeth.web.sessions.models import (
            blob_run_links_table,
            composition_states_table,
            runs_table,
        )

        record = await blob_service.create_blob(
            session_id=session_id,
            filename="done.csv",
            content=b"finished",
            mime_type="text/csv",
            created_by="user",
        )

        state_id = str(uuid4())
        session_id_str = str(session_id)
        run_id = str(uuid4())

        with db_engine.begin() as conn:
            conn.execute(
                composition_states_table.insert().values(
                    id=state_id,
                    session_id=session_id_str,
                    version=1,
                    is_valid=True,
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
            conn.execute(
                runs_table.insert().values(
                    id=run_id,
                    session_id=session_id_str,
                    state_id=state_id,
                    status="completed",
                    started_at=datetime(2026, 1, 1, tzinfo=UTC),
                    rows_processed=10,
                    rows_failed=0,
                )
            )
            conn.execute(
                blob_run_links_table.insert().values(
                    blob_id=str(record.id),
                    run_id=run_id,
                    direction="input",
                )
            )

        # Should succeed — completed run does not block deletion
        await blob_service.delete_blob(record.id)

        with pytest.raises(BlobNotFoundError):
            await blob_service.get_blob(record.id)


# ---------------------------------------------------------------------------
# finalize_blob — pending lifecycle transitions
# ---------------------------------------------------------------------------


class TestFinalizeBlob:
    """Pending -> ready/error lifecycle: only valid transitions allowed."""

    @pytest.mark.asyncio
    async def test_finalize_blob_transitions_pending_to_ready(self, blob_service, session_id) -> None:
        pending = await blob_service.create_pending_blob(
            session_id=session_id,
            filename="output.csv",
            mime_type="text/csv",
            created_by="pipeline",
        )
        assert pending.status == "pending"

        finalized = await blob_service.finalize_blob(
            blob_id=pending.id,
            status="ready",
            size_bytes=42,
            content_hash="abc123",
        )
        assert finalized.status == "ready"
        assert finalized.size_bytes == 42
        assert finalized.content_hash == "abc123"

    @pytest.mark.asyncio
    async def test_finalize_blob_rejects_non_pending(self, blob_service, session_id) -> None:
        """Cannot finalize a blob that is already ready — status rollback is forbidden."""
        record = await blob_service.create_blob(
            session_id=session_id,
            filename="already-ready.csv",
            content=b"done",
            mime_type="text/csv",
            created_by="user",
        )
        assert record.status == "ready"

        with pytest.raises(RuntimeError, match="expected 'pending'"):
            await blob_service.finalize_blob(
                blob_id=record.id,
                status="ready",
                size_bytes=4,
            )

    @pytest.mark.asyncio
    async def test_finalize_blob_rejects_invalid_status(self, blob_service, session_id) -> None:
        """Only 'ready' and 'error' are valid finalize targets."""
        pending = await blob_service.create_pending_blob(
            session_id=session_id,
            filename="output.csv",
            mime_type="text/csv",
            created_by="pipeline",
        )

        with pytest.raises(RuntimeError, match="Invalid finalize status"):
            await blob_service.finalize_blob(
                blob_id=pending.id,
                status="deleted",
            )


# ---------------------------------------------------------------------------
# Blob quota — per-session storage limit (AD-10)
# ---------------------------------------------------------------------------


class TestBlobQuota:
    """Per-session cumulative storage quota prevents unbounded disk growth."""

    @pytest.mark.asyncio
    async def test_quota_rejects_when_exceeded(self, db_engine, session_id, tmp_path) -> None:
        """Upload that would exceed the session quota returns BlobQuotaExceededError."""
        from elspeth.web.blobs.protocol import BlobQuotaExceededError

        # Tiny quota: 100 bytes
        service = BlobServiceImpl(db_engine, tmp_path, max_storage_per_session=100)

        # First blob: 60 bytes — fits
        await service.create_blob(
            session_id=session_id,
            filename="a.csv",
            content=b"x" * 60,
            mime_type="text/csv",
            created_by="user",
        )

        # Second blob: 60 bytes — total would be 120 > 100
        with pytest.raises(BlobQuotaExceededError):
            await service.create_blob(
                session_id=session_id,
                filename="b.csv",
                content=b"x" * 60,
                mime_type="text/csv",
                created_by="user",
            )

    @pytest.mark.asyncio
    async def test_quota_allows_within_limit(self, db_engine, session_id, tmp_path) -> None:
        """Uploads within the quota succeed."""
        service = BlobServiceImpl(db_engine, tmp_path, max_storage_per_session=200)

        await service.create_blob(
            session_id=session_id,
            filename="a.csv",
            content=b"x" * 90,
            mime_type="text/csv",
            created_by="user",
        )
        record = await service.create_blob(
            session_id=session_id,
            filename="b.csv",
            content=b"x" * 90,
            mime_type="text/csv",
            created_by="user",
        )
        assert record.status == "ready"


# ---------------------------------------------------------------------------
# copy_blobs_for_fork — rollback on partial failure
# ---------------------------------------------------------------------------


class TestCopyBlobsForForkRollback:
    """Rollback path: partial blob copies are cleaned up on failure.

    copy_blobs_for_fork creates blobs atomically (one at a time). If the
    second create_blob fails, the first already-committed blob must be
    deleted — both its DB row and its file on disk.
    """

    @pytest.fixture()
    def target_session_id(self, db_engine) -> UUID:
        """Second session for the fork target."""
        sid = str(uuid4())
        now = datetime.now(UTC)
        with db_engine.begin() as conn:
            conn.execute(
                sessions_table.insert().values(
                    id=sid,
                    user_id="test-user",
                    auth_provider_type="local",
                    title="Forked Session",
                    created_at=now,
                    updated_at=now,
                )
            )
        return UUID(sid)

    @pytest.mark.asyncio
    async def test_rollback_cleans_up_partial_copies(
        self,
        blob_service: BlobServiceImpl,
        session_id: UUID,
        target_session_id: UUID,
        tmp_path,
    ) -> None:
        """When create_blob fails mid-copy, already-created blobs are removed."""
        # Create two blobs in the source session
        await blob_service.create_blob(
            session_id=session_id,
            filename="first.csv",
            content=b"first file content",
            mime_type="text/csv",
            created_by="user",
        )
        await blob_service.create_blob(
            session_id=session_id,
            filename="second.csv",
            content=b"second file content",
            mime_type="text/csv",
            created_by="user",
        )

        # Patch create_blob to fail on the second call
        original_create = blob_service.create_blob
        call_count = 0

        async def _failing_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise RuntimeError("Simulated disk failure on second blob")
            return await original_create(*args, **kwargs)

        blob_service.create_blob = _failing_create  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="Simulated disk failure"):
            await blob_service.copy_blobs_for_fork(session_id, target_session_id)

        # Verify rollback: no blobs should remain in the target session
        target_blobs = await blob_service.list_blobs(target_session_id)
        assert target_blobs == [], f"Expected 0 blobs after rollback, found {len(target_blobs)}: {[b.filename for b in target_blobs]}"

    @pytest.mark.asyncio
    async def test_empty_source_returns_empty_map(
        self,
        blob_service: BlobServiceImpl,
        session_id: UUID,
        target_session_id: UUID,
    ) -> None:
        """No blobs in source session → empty mapping, no errors."""
        result = await blob_service.copy_blobs_for_fork(session_id, target_session_id)
        assert result == {}

    @pytest.mark.asyncio
    async def test_quota_exceeded_before_any_copy(
        self,
        blob_service: BlobServiceImpl,
        db_engine,
        session_id: UUID,
        target_session_id: UUID,
        tmp_path,
    ) -> None:
        """Quota check happens before copying — no partial writes."""
        from elspeth.web.blobs.protocol import BlobQuotaExceededError

        # Create a blob using the default (large-quota) service
        await blob_service.create_blob(
            session_id=session_id,
            filename="big.csv",
            content=b"x" * 100,
            mime_type="text/csv",
            created_by="user",
        )

        # Fork with a small-quota service — quota pre-check should reject
        small_quota = BlobServiceImpl(db_engine, tmp_path, max_storage_per_session=10)

        with pytest.raises(BlobQuotaExceededError):
            await small_quota.copy_blobs_for_fork(session_id, target_session_id)

        # Verify: no blobs in target (pre-check prevented any copies)
        target_blobs = await blob_service.list_blobs(target_session_id)
        assert target_blobs == []
