"""BlobServiceImpl — filesystem-backed blob persistence."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import Engine, select

from elspeth.web.blobs.protocol import (
    ALLOWED_MIME_TYPES,
    BlobActiveRunError,
    BlobNotFoundError,
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
    return sanitized


class BlobServiceImpl:
    """Filesystem-backed blob service.

    Follows the same async-over-sync pattern as SessionServiceImpl:
    all public methods are async, database I/O runs in a thread pool
    executor via _run_sync().
    """

    def __init__(self, engine: Engine, data_dir: Path) -> None:
        self._engine = engine
        self._data_dir = data_dir

    async def _run_sync(self, func: Callable[..., _T]) -> _T:
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
            schema_info=row.schema_info,
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
        safe_filename = sanitize_filename(filename)
        blob_id = str(uuid4())
        session_id_str = str(session_id)
        file_hash = content_hash(content)
        storage = self._storage_path(session_id_str, blob_id, safe_filename)

        def _sync() -> BlobRecord:
            # Write file
            storage.parent.mkdir(parents=True, exist_ok=True)
            storage.write_bytes(content)

            # Insert metadata
            now = self._now()
            with self._engine.begin() as conn:
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
                        schema_info=None,
                        status="ready",
                    )
                )

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
                schema_info=None,
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
                        content_hash="",
                        storage_path=str(storage),
                        created_at=now,
                        created_by=created_by,
                        source_description=source_description,
                        schema_info=None,
                        status="pending",
                    )
                )

            return BlobRecord(
                id=UUID(blob_id),
                session_id=session_id,
                filename=safe_filename,
                mime_type=mime_type,
                size_bytes=0,
                content_hash="",
                storage_path=str(storage),
                created_at=now,
                created_by=created_by,
                source_description=source_description,
                schema_info=None,
                status="pending",
            )

        return await self._run_sync(_sync)

    async def finalize_blob(
        self,
        blob_id: UUID,
        status: str,
        size_bytes: int | None = None,
        content_hash_value: str | None = None,
    ) -> BlobRecord:
        """Update a pending blob to ready or error after execution."""
        blob_id_str = str(blob_id)

        def _sync() -> BlobRecord:
            with self._engine.begin() as conn:
                row = conn.execute(select(blobs_table).where(blobs_table.c.id == blob_id_str)).first()
                if row is None:
                    raise BlobNotFoundError(blob_id_str)

                updates: dict[str, Any] = {"status": status}
                if size_bytes is not None:
                    updates["size_bytes"] = size_bytes
                if content_hash_value is not None:
                    updates["content_hash"] = content_hash_value

                conn.execute(blobs_table.update().where(blobs_table.c.id == blob_id_str).values(**updates))

                updated = conn.execute(select(blobs_table).where(blobs_table.c.id == blob_id_str)).first()
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
        limit: int = 50,
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

                # Delete metadata (cascades to blob_run_links)
                conn.execute(blobs_table.delete().where(blobs_table.c.id == blob_id_str))

            # Delete backing file
            storage = Path(row.storage_path)
            if storage.exists():
                storage.unlink()

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

    @staticmethod
    def validate_mime_type(mime_type: str) -> bool:
        """Check if a MIME type is in the allowed data-oriented set."""
        return mime_type in ALLOWED_MIME_TYPES
