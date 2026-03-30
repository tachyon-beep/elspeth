"""BlobService protocol and record dataclasses.

Record types are frozen dataclasses representing database rows.
BlobCreateData is the input DTO for creating new blobs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

# Valid blob statuses and their meanings:
#   ready   — content is available for download/use
#   pending — placeholder for an output blob not yet written
#   error   — run failed before writing the output blob
BLOB_STATUSES = frozenset({"ready", "pending", "error"})

# Valid created_by values:
#   user      — uploaded by the user via REST or drag-and-drop
#   assistant — materialised by the assistant via create_blob tool
#   pipeline  — produced as output of a pipeline run
BLOB_CREATORS = frozenset({"user", "assistant", "pipeline"})

# MIME types accepted for data-oriented uploads.
ALLOWED_MIME_TYPES = frozenset(
    {
        "text/csv",
        "text/plain",
        "application/json",
        "application/x-jsonlines",
        "application/jsonl",
        "text/jsonl",
    }
)


@dataclass(frozen=True, slots=True)
class BlobRecord:
    """Represents a row from the blobs table.

    All fields are scalars or None — no freeze guard needed.
    """

    id: UUID
    session_id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    content_hash: str | None
    storage_path: str
    created_at: datetime
    created_by: str
    source_description: str | None
    status: str


@dataclass(frozen=True, slots=True)
class BlobRunLinkRecord:
    """Represents a row from the blob_run_links table.

    All fields are scalars — no freeze guard needed.
    """

    blob_id: UUID
    run_id: UUID
    direction: str


class BlobNotFoundError(Exception):
    """Raised when a blob lookup fails.

    Route handlers catching this error should return 404.
    """

    def __init__(self, blob_id: str) -> None:
        self.blob_id = blob_id
        super().__init__(f"Blob {blob_id} not found")


class BlobActiveRunError(Exception):
    """Raised when attempting to delete a blob linked to an active run.

    Route handlers catching this error should return 409.
    """

    def __init__(self, blob_id: str, run_id: str) -> None:
        self.blob_id = blob_id
        self.run_id = run_id
        super().__init__(f"Blob {blob_id} is linked to active run {run_id} and cannot be deleted")


class BlobQuotaExceededError(Exception):
    """Raised when a blob creation would exceed the session storage quota.

    Route handlers catching this error should return 413.
    """

    def __init__(self, session_id: str, current_bytes: int, limit_bytes: int) -> None:
        self.session_id = session_id
        self.current_bytes = current_bytes
        self.limit_bytes = limit_bytes
        super().__init__(f"Session {session_id} blob storage ({current_bytes} bytes) would exceed quota ({limit_bytes} bytes)")


@runtime_checkable
class BlobServiceProtocol(Protocol):
    """Protocol for blob persistence and lifecycle operations."""

    async def create_blob(
        self,
        session_id: UUID,
        filename: str,
        content: bytes,
        mime_type: str,
        created_by: str = "user",
        source_description: str | None = None,
    ) -> BlobRecord:
        """Create a blob from content bytes.

        Writes content to filesystem, computes hash, and persists metadata.
        """
        ...

    async def create_pending_blob(
        self,
        session_id: UUID,
        filename: str,
        mime_type: str,
        created_by: str = "pipeline",
        source_description: str | None = None,
    ) -> BlobRecord:
        """Reserve a pending output blob (status='pending').

        The backing file doesn't exist yet — it will be written by a
        pipeline sink. Call finalize_blob() after the run completes.
        """
        ...

    async def finalize_blob(
        self,
        blob_id: UUID,
        status: str,
        size_bytes: int | None = None,
        content_hash: str | None = None,
    ) -> BlobRecord:
        """Update a pending blob to ready or error after execution."""
        ...

    async def get_blob(self, blob_id: UUID) -> BlobRecord:
        """Get blob metadata. Raises BlobNotFoundError if missing."""
        ...

    async def list_blobs(
        self,
        session_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BlobRecord]:
        """List blobs for a session, newest first."""
        ...

    async def delete_blob(self, blob_id: UUID) -> None:
        """Delete blob metadata and backing file.

        Raises BlobActiveRunError if linked to a pending/running run.
        Raises BlobNotFoundError if the blob doesn't exist.
        """
        ...

    async def read_blob_content(self, blob_id: UUID) -> bytes:
        """Read the raw content of a blob.

        Raises BlobNotFoundError if the blob doesn't exist.
        """
        ...

    async def link_blob_to_run(
        self,
        blob_id: UUID,
        run_id: UUID,
        direction: str,
    ) -> None:
        """Record a blob-to-run linkage (input or output)."""
        ...

    async def get_blob_run_links(
        self,
        blob_id: UUID,
    ) -> list[BlobRunLinkRecord]:
        """Get all run links for a blob."""
        ...

    async def finalize_run_output_blobs(
        self,
        run_id: UUID,
        success: bool,
    ) -> list[BlobRecord]:
        """Finalize all pending output blobs for a completed/failed run."""
        ...
