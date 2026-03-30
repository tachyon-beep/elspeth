"""BlobServiceImpl — filesystem-backed blob persistence."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, select

from elspeth.web.blobs.protocol import (
    ALLOWED_MIME_TYPES,
    BLOB_CREATORS,
    BlobActiveRunError,
    BlobNotFoundError,
    BlobQuotaExceededError,
    BlobRecord,
    BlobRunLinkRecord,
)
from elspeth.web.sessions.models import (
    blob_run_links_table,
    blobs_table,
    runs_table,
)

_T = TypeVar("_T")


def content_hash(data: bytes) -> str:
    """Compute SHA-256 hex digest of raw content bytes.

    This is the shared hash helper referenced by AD-5 and AD-7 in the
    blob manager plan. When a pipeline reads from a blob, the engine
    records the raw data hash in PayloadStore. Using the same algorithm
    here guarantees the hashes match when the bytes match.
    """
    return hashlib.sha256(data).hexdigest()


def sanitize_filename(filename: str) -> str:
    """Extract a safe basename from a potentially malicious filename.

    Strips all directory components (path traversal protection) and
    rejects empty results or dot-only names.
    """
    sanitized = Path(filename).name
    if not sanitized or sanitized in (".", ".."):
        raise ValueError(f"Invalid filename: {filename!r}")
    # Cap length to leave room for UUID prefix in storage path
    if len(sanitized.encode("utf-8")) > 200:
        # Preserve the extension
        stem = Path(sanitized).stem
        suffix = Path(sanitized).suffix
        max_stem = 200 - len(suffix.encode("utf-8"))
        sanitized = stem.encode("utf-8")[:max_stem].decode("utf-8", errors="ignore") + suffix
    return sanitized


class BlobServiceImpl:
    """Filesystem-backed blob service.

    Follows the same async-over-sync pattern as SessionServiceImpl:
    all public methods are async, database I/O runs in a thread pool
    executor via _run_sync().
    """

    def __init__(self, engine: Engine, data_dir: Path, max_storage_per_session: int = 500 * 1024 * 1024) -> None:
        self._engine = engine
        self._data_dir = data_dir
        self._max_storage_per_session = max_storage_per_session

    async def _run_sync(self, func: Callable[[], _T]) -> _T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func)

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _blob_dir(self, session_id: str) -> Path:
        return self._data_dir / "blobs" / session_id

    def _storage_path(self, session_id: str, blob_id: str, filename: str) -> Path:
        return self._blob_dir(session_id) / f"{blob_id}_{filename}"

    def _row_to_record(self, row: Any) -> BlobRecord:
        return BlobRecord(
            id=UUID(row.id),
            session_id=UUID(row.session_id),
            filename=row.filename,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            content_hash=row.content_hash,
            storage_path=row.storage_path,
            created_at=row.created_at,
            created_by=row.created_by,
            source_description=row.source_description,
            status=row.status,
        )

    def _row_to_link_record(self, row: Any) -> BlobRunLinkRecord:
        return BlobRunLinkRecord(
            blob_id=UUID(row.blob_id),
            run_id=UUID(row.run_id),
            direction=row.direction,
        )

    async def create_blob(
        self,
        session_id: UUID,
        filename: str,
        content: bytes,
        mime_type: str,
        created_by: str = "user",
        source_description: str | None = None,
    ) -> BlobRecord:
        """Create a blob from content bytes."""
        assert created_by in BLOB_CREATORS, f"Invalid created_by: {created_by!r}"
        assert mime_type in ALLOWED_MIME_TYPES, f"Invalid mime_type: {mime_type!r}"
        safe_filename = sanitize_filename(filename)
        blob_id = str(uuid4())
        session_id_str = str(session_id)
        file_hash = content_hash(content)
        storage = self._storage_path(session_id_str, blob_id, safe_filename)

        def _sync() -> BlobRecord:
            # Write file first (before DB transaction)
            storage.parent.mkdir(parents=True, exist_ok=True)
            storage.write_bytes(content)

            # Single transaction: quota check + insert (atomic, no TOCTOU)
            now = self._now()
            try:
                with self._engine.begin() as conn:
                    # Quota check inside the write transaction
                    current_total = conn.execute(
                        select(func.coalesce(func.sum(blobs_table.c.size_bytes), 0)).where(blobs_table.c.session_id == session_id_str)
                    ).scalar()
                    # COALESCE guarantees an int; non-int = Tier 1 anomaly
                    current_total = int(current_total)  # type: ignore[arg-type]
                    if current_total + len(content) > self._max_storage_per_session:
                        raise BlobQuotaExceededError(session_id_str, current_total, self._max_storage_per_session)

                    conn.execute(
                        blobs_table.insert().values(
                            id=blob_id,
                            session_id=session_id_str,
                            filename=safe_filename,
                            mime_type=mime_type,
                            size_bytes=len(content),
                            content_hash=file_hash,
                            storage_path=str(storage),
                            created_at=now,
                            created_by=created_by,
                            source_description=source_description,
                            status="ready",
                        )
                    )
            except BaseException:
                # Clean up file on quota exceeded or any DB failure
                if storage.exists():
                    storage.unlink()
                raise

            return BlobRecord(
                id=UUID(blob_id),
                session_id=session_id,
                filename=safe_filename,
                mime_type=mime_type,
                size_bytes=len(content),
                content_hash=file_hash,
                storage_path=str(storage),
                created_at=now,
                created_by=created_by,
                source_description=source_description,
                status="ready",
            )

        return await self._run_sync(_sync)

    async def create_pending_blob(
        self,
        session_id: UUID,
        filename: str,
        mime_type: str,
        created_by: str = "pipeline",
        source_description: str | None = None,
    ) -> BlobRecord:
        """Reserve a pending output blob."""
        assert created_by in BLOB_CREATORS, f"Invalid created_by: {created_by!r}"
        safe_filename = sanitize_filename(filename)
        blob_id = str(uuid4())
        session_id_str = str(session_id)
        storage = self._storage_path(session_id_str, blob_id, safe_filename)

        def _sync() -> BlobRecord:
            # Ensure directory exists (file will be written by sink later)
            storage.parent.mkdir(parents=True, exist_ok=True)

            now = self._now()
            with self._engine.begin() as conn:
                conn.execute(
                    blobs_table.insert().values(
                        id=blob_id,
                        session_id=session_id_str,
                        filename=safe_filename,
                        mime_type=mime_type,
                        size_bytes=0,
                        content_hash=None,
                        storage_path=str(storage),
                        created_at=now,
                        created_by=created_by,
                        source_description=source_description,
                        status="pending",
                    )
                )

            return BlobRecord(
                id=UUID(blob_id),
                session_id=session_id,
                filename=safe_filename,
                mime_type=mime_type,
                size_bytes=0,
                content_hash=None,
                storage_path=str(storage),
                created_at=now,
                created_by=created_by,
                source_description=source_description,
                status="pending",
            )

        return await self._run_sync(_sync)

    async def finalize_blob(
        self,
        blob_id: UUID,
        status: str,
        size_bytes: int | None = None,
        content_hash: str | None = None,
    ) -> BlobRecord:
        """Update a pending blob to ready or error after execution."""
        blob_id_str = str(blob_id)

        def _sync() -> BlobRecord:
            with self._engine.begin() as conn:
                row = conn.execute(select(blobs_table).where(blobs_table.c.id == blob_id_str)).first()
                if row is None:
                    raise BlobNotFoundError(blob_id_str)

                if row.status != "pending":
                    raise RuntimeError(f"Cannot finalize blob {blob_id_str} — status is '{row.status}', expected 'pending'")
                if status not in ("ready", "error"):
                    raise RuntimeError(f"Invalid finalize status '{status}' — must be 'ready' or 'error'")

                updates: dict[str, Any] = {"status": status}
                if size_bytes is not None:
                    updates["size_bytes"] = size_bytes
                if content_hash is not None:
                    updates["content_hash"] = content_hash

                conn.execute(blobs_table.update().where(blobs_table.c.id == blob_id_str).values(**updates))

                updated = conn.execute(select(blobs_table).where(blobs_table.c.id == blob_id_str)).first()
                if updated is None:
                    raise RuntimeError(f"Blob {blob_id_str} vanished during finalize — concurrent deletion?")
                return self._row_to_record(updated)

        return await self._run_sync(_sync)

    async def get_blob(self, blob_id: UUID) -> BlobRecord:
        """Get blob metadata."""
        blob_id_str = str(blob_id)

        def _sync() -> BlobRecord:
            with self._engine.connect() as conn:
                row = conn.execute(select(blobs_table).where(blobs_table.c.id == blob_id_str)).first()
                if row is None:
                    raise BlobNotFoundError(blob_id_str)
                return self._row_to_record(row)

        return await self._run_sync(_sync)

    async def list_blobs(
        self,
        session_id: UUID,
        limit: int | None = 50,
        offset: int = 0,
    ) -> list[BlobRecord]:
        """List blobs for a session, newest first."""
        session_id_str = str(session_id)

        def _sync() -> list[BlobRecord]:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    select(blobs_table)
                    .where(blobs_table.c.session_id == session_id_str)
                    .order_by(blobs_table.c.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                ).fetchall()
                return [self._row_to_record(r) for r in rows]

        return await self._run_sync(_sync)

    async def delete_blob(self, blob_id: UUID) -> None:
        """Delete blob metadata and backing file."""
        blob_id_str = str(blob_id)

        def _sync() -> None:
            with self._engine.begin() as conn:
                # Check blob exists
                row = conn.execute(select(blobs_table).where(blobs_table.c.id == blob_id_str)).first()
                if row is None:
                    raise BlobNotFoundError(blob_id_str)

                # Check for active run links
                active_link = conn.execute(
                    select(blob_run_links_table)
                    .join(
                        runs_table,
                        blob_run_links_table.c.run_id == runs_table.c.id,
                    )
                    .where(blob_run_links_table.c.blob_id == blob_id_str)
                    .where(runs_table.c.status.in_(["pending", "running"]))
                ).first()
                if active_link is not None:
                    raise BlobActiveRunError(blob_id_str, active_link.run_id)

                # Delete backing file first — orphaned DB row is recoverable,
                # orphaned file with no metadata is not
                storage = Path(row.storage_path)
                if storage.exists():
                    storage.unlink()

                # Delete metadata (cascades to blob_run_links)
                conn.execute(blobs_table.delete().where(blobs_table.c.id == blob_id_str))

        await self._run_sync(_sync)

    async def read_blob_content(self, blob_id: UUID) -> bytes:
        """Read the raw content of a blob."""
        blob_id_str = str(blob_id)

        def _sync() -> bytes:
            with self._engine.connect() as conn:
                row = conn.execute(select(blobs_table).where(blobs_table.c.id == blob_id_str)).first()
                if row is None:
                    raise BlobNotFoundError(blob_id_str)

                storage = Path(row.storage_path)
                if not storage.exists():
                    raise BlobNotFoundError(blob_id_str)
                return storage.read_bytes()

        return await self._run_sync(_sync)

    async def link_blob_to_run(
        self,
        blob_id: UUID,
        run_id: UUID,
        direction: str,
    ) -> None:
        """Record a blob-to-run linkage."""

        def _sync() -> None:
            with self._engine.begin() as conn:
                conn.execute(
                    blob_run_links_table.insert().values(
                        blob_id=str(blob_id),
                        run_id=str(run_id),
                        direction=direction,
                    )
                )

        await self._run_sync(_sync)

    async def get_blob_run_links(
        self,
        blob_id: UUID,
    ) -> list[BlobRunLinkRecord]:
        """Get all run links for a blob."""
        blob_id_str = str(blob_id)

        def _sync() -> list[BlobRunLinkRecord]:
            with self._engine.connect() as conn:
                rows = conn.execute(select(blob_run_links_table).where(blob_run_links_table.c.blob_id == blob_id_str)).fetchall()
                return [self._row_to_link_record(r) for r in rows]

        return await self._run_sync(_sync)

    async def finalize_run_output_blobs(
        self,
        run_id: UUID,
        success: bool,
    ) -> list[BlobRecord]:
        """Finalize all pending output blobs for a completed/failed run.

        On success: compute content_hash and size_bytes from the backing
        file, set status to 'ready'. If the file wasn't written, mark
        as 'error'.
        On failure: set status to 'error', leave size/hash as None.

        Returns the list of finalized blob records.
        """
        run_id_str = str(run_id)

        def _sync() -> list[BlobRecord]:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    select(blobs_table)
                    .join(
                        blob_run_links_table,
                        blob_run_links_table.c.blob_id == blobs_table.c.id,
                    )
                    .where(blob_run_links_table.c.run_id == run_id_str)
                    .where(blob_run_links_table.c.direction == "output")
                    .where(blobs_table.c.status == "pending")
                ).fetchall()

            finalized: list[BlobRecord] = []
            for row in rows:
                blob_id = UUID(row.id)
                if success:
                    storage = Path(row.storage_path)
                    if storage.exists():
                        file_bytes = storage.read_bytes()
                        try:
                            record = self._finalize_blob_sync(
                                blob_id,
                                "ready",
                                size_bytes=len(file_bytes),
                                content_hash_val=content_hash(file_bytes),
                            )
                        except BlobQuotaExceededError:
                            # Run succeeded but this blob would breach the
                            # session quota — mark as error so the run
                            # finalization isn't aborted entirely.
                            # Delete the backing file to prevent untracked
                            # disk growth from repeated over-quota outputs.
                            if storage.exists():
                                storage.unlink()
                            record = self._finalize_blob_sync(blob_id, "error")
                    else:
                        record = self._finalize_blob_sync(blob_id, "error")
                else:
                    record = self._finalize_blob_sync(blob_id, "error")
                finalized.append(record)
            return finalized

        return await self._run_sync(_sync)

    async def copy_blobs_for_fork(
        self,
        source_session_id: UUID,
        target_session_id: UUID,
    ) -> dict[UUID, BlobRecord]:
        """Copy all ready blobs from source session to target session.

        Pre-checks total source blob size against the target session's
        quota before copying any files. This eliminates partial-write
        scenarios — either all blobs are copied or none are.

        On any failure during the copy loop, cleans up files already
        written before re-raising.
        """
        source_blobs = await self.list_blobs(source_session_id, limit=None)
        ready_blobs = [b for b in source_blobs if b.status == "ready"]

        if not ready_blobs:
            return {}

        # Pre-check: will the total source blob size fit in the target quota?
        total_source_bytes = sum(b.size_bytes for b in ready_blobs)
        target_session_id_str = str(target_session_id)

        def _check_quota() -> int:
            with self._engine.connect() as conn:
                current = conn.execute(
                    select(func.coalesce(func.sum(blobs_table.c.size_bytes), 0)).where(blobs_table.c.session_id == target_session_id_str)
                ).scalar()
                return int(current)  # type: ignore[arg-type]

        current_usage = await self._run_sync(_check_quota)
        if current_usage + total_source_bytes > self._max_storage_per_session:
            raise BlobQuotaExceededError(target_session_id_str, current_usage, self._max_storage_per_session)

        # Copy blobs — clean up partial writes on any failure.
        # Build old_id → new_blob mapping for source reference rewriting.
        blob_map: dict[UUID, BlobRecord] = {}
        copied: list[BlobRecord] = []
        try:
            for blob in ready_blobs:
                content = await self.read_blob_content(blob.id)
                new_blob = await self.create_blob(
                    session_id=target_session_id,
                    filename=blob.filename,
                    content=content,
                    mime_type=blob.mime_type,
                    created_by=blob.created_by,
                    source_description=f"copied from session fork (original: {blob.id})",
                )
                copied.append(new_blob)
                blob_map[blob.id] = new_blob
        except BaseException:
            # Clean up both files AND database rows for any blobs already
            # committed. create_blob() commits each blob atomically, so
            # without this cleanup the forked session would have "ready"
            # blob metadata pointing at files we're about to delete.
            for written_blob in copied:
                try:
                    await self.delete_blob(written_blob.id)
                except Exception:
                    # Best-effort cleanup — if delete_blob fails (e.g.
                    # DB already disconnected), at least unlink the file
                    storage = Path(written_blob.storage_path)
                    if storage.exists():
                        storage.unlink(missing_ok=True)
            raise

        return blob_map

    def _finalize_blob_sync(
        self,
        blob_id: UUID,
        status: str,
        size_bytes: int | None = None,
        content_hash_val: str | None = None,
    ) -> BlobRecord:
        """Synchronous single-blob finalize for use inside _run_sync closures."""
        blob_id_str = str(blob_id)
        with self._engine.begin() as conn:
            row = conn.execute(select(blobs_table).where(blobs_table.c.id == blob_id_str)).first()
            if row is None:
                raise BlobNotFoundError(blob_id_str)
            if row.status != "pending":
                raise RuntimeError(f"Cannot finalize blob {blob_id_str} — status is '{row.status}', expected 'pending'")
            if status not in ("ready", "error"):
                raise RuntimeError(f"Invalid finalize status '{status}' — must be 'ready' or 'error'")

            # Enforce quota when finalizing with a real size — pending blobs
            # were reserved at size_bytes=0, so this is the first time the
            # actual size is known.  Without this check, pipeline-generated
            # output could bypass the per-session storage cap entirely.
            if status == "ready" and size_bytes is not None and size_bytes > 0:
                session_id_str = row.session_id
                current_total = conn.execute(
                    select(func.coalesce(func.sum(blobs_table.c.size_bytes), 0)).where(
                        blobs_table.c.session_id == session_id_str,
                        blobs_table.c.id != blob_id_str,
                    )
                ).scalar()
                current_total = int(current_total)  # type: ignore[arg-type]
                if current_total + size_bytes > self._max_storage_per_session:
                    raise BlobQuotaExceededError(session_id_str, current_total, self._max_storage_per_session)

            updates: dict[str, Any] = {"status": status}
            if size_bytes is not None:
                updates["size_bytes"] = size_bytes
            if content_hash_val is not None:
                updates["content_hash"] = content_hash_val

            conn.execute(blobs_table.update().where(blobs_table.c.id == blob_id_str).values(**updates))
            updated = conn.execute(select(blobs_table).where(blobs_table.c.id == blob_id_str)).first()
            if updated is None:
                raise RuntimeError(f"Blob {blob_id_str} vanished during finalize — concurrent deletion?")
            return self._row_to_record(updated)
