"""BlobService protocol and record dataclasses.

Record types are frozen dataclasses representing database rows.
BlobCreateData is the input DTO for creating new blobs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, get_args, runtime_checkable
from uuid import UUID

from elspeth.contracts.freeze import freeze_fields

# Lifecycle literal aliases.
#
# BlobStatus is the full enum stored on a BlobRecord.  FinalizeBlobStatus
# is the narrower set a pending blob may transition to — pending itself
# is not a valid finalize target.  BlobCreator mirrors ck_blobs_created_by,
# BlobRunLinkDirection mirrors ck_blob_run_links_direction, and
# AllowedMimeType is the closed set of data-oriented MIME types accepted
# for uploads.
#
# The Literal aliases are authoritative — their matching runtime
# frozensets are *derived* via typing.get_args() so adding a member is
# a single-site edit.  The static assert below anchors the derivation
# (a frozenset literal that drifted from the Literal would now be an
# immediate import-time crash rather than a silent Tier 1 gap).
BlobStatus = Literal["ready", "pending", "error"]
FinalizeBlobStatus = Literal["ready", "error"]
BlobCreator = Literal["user", "assistant", "pipeline"]
BlobRunLinkDirection = Literal["input", "output"]
AllowedMimeType = Literal[
    "text/csv",
    "text/plain",
    "application/json",
    "application/x-jsonlines",
    "application/jsonl",
    "text/jsonl",
]

# Runtime frozensets derived from the Literal aliases above.  These are
# used by the DB CHECK-mirroring read guards (_row_to_record) and by
# boundary assertions at write sites (create_blob, create_pending_blob).
# Deriving via get_args guarantees the static and runtime views cannot
# drift apart — a single-edit-site contract.
#   ready   — content is available for download/use
#   pending — placeholder for an output blob not yet written
#   error   — run failed before writing the output blob
BLOB_STATUSES: frozenset[str] = frozenset(get_args(BlobStatus))
#   user      — uploaded by the user via REST or drag-and-drop
#   assistant — materialised by the assistant via create_blob tool
#   pipeline  — produced as output of a pipeline run
BLOB_CREATORS: frozenset[str] = frozenset(get_args(BlobCreator))
# MIME types accepted for data-oriented uploads.
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(get_args(AllowedMimeType))


@dataclass(frozen=True, slots=True)
class BlobRecord:
    """Represents a row from the blobs table.

    All fields are scalars or None — no freeze guard needed.
    """

    id: UUID
    session_id: UUID
    filename: str
    mime_type: AllowedMimeType
    size_bytes: int
    content_hash: str | None
    storage_path: str
    created_at: datetime
    created_by: BlobCreator
    source_description: str | None
    status: BlobStatus


@dataclass(frozen=True, slots=True)
class BlobRunLinkRecord:
    """Represents a row from the blob_run_links table.

    All fields are scalars — no freeze guard needed.
    """

    blob_id: UUID
    run_id: UUID
    direction: BlobRunLinkDirection


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


class BlobStateError(Exception):
    """Raised when a blob's status precludes the requested operation.

    Distinct from RuntimeError so per-blob catch clauses can be precise:
    BlobStateError is an operational condition (concurrent finalization,
    status already terminal), while RuntimeError indicates a code-level
    anomaly (e.g. row vanishing mid-transaction) that should propagate.
    """

    def __init__(self, blob_id: str, message: str) -> None:
        self.blob_id = blob_id
        super().__init__(message)


class BlobIntegrityError(Exception):
    """Raised when a blob's on-disk content does not match its stored hash.

    This is a Tier 1 integrity violation: we wrote both the file and the
    hash, so a mismatch means filesystem corruption, tampering, or a bug
    in our write path.  The web layer should return 500 (not suppress it).

    Deliberately NOT in BlobServiceImpl._PER_BLOB_SUPPRESSED — integrity
    failures must propagate, never be swallowed.
    """

    def __init__(self, blob_id: str, expected: str, actual: str) -> None:
        self.blob_id = blob_id
        self.expected_hash = expected
        self.actual_hash = actual
        super().__init__(f"Blob {blob_id} content integrity failure: stored hash {expected[:16]}... != computed hash {actual[:16]}...")


@dataclass(frozen=True, slots=True)
class BlobFinalizationError:
    """Record of a per-blob finalization failure.

    Returned in BlobFinalizationResult.errors so callers can decide
    how to surface failures (telemetry, logging, or corrective action)
    without the blob service owning that decision.
    """

    blob_id: UUID
    exc_type: str
    detail: str


@dataclass(frozen=True, slots=True)
class BlobFinalizationResult:
    """Result of batch blob finalization — successes and errors.

    Partial failure is expected: one blob's operational error (concurrent
    deletion, I/O failure) must not prevent finalization of remaining
    blobs.  Callers inspect ``errors`` to determine severity.
    """

    finalized: Sequence[BlobRecord]
    errors: Sequence[BlobFinalizationError]

    def __post_init__(self) -> None:
        freeze_fields(self, "finalized", "errors")


@runtime_checkable
class BlobServiceProtocol(Protocol):
    """Protocol for blob persistence and lifecycle operations."""

    async def create_blob(
        self,
        session_id: UUID,
        filename: str,
        content: bytes,
        mime_type: AllowedMimeType,
        created_by: BlobCreator = "user",
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
        mime_type: AllowedMimeType,
        created_by: BlobCreator = "pipeline",
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
        status: FinalizeBlobStatus,
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
        limit: int | None = 50,
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

        Only ``ready`` blobs are readable.  Verifies the stored
        ``content_hash`` against the bytes on disk before returning.

        Raises BlobNotFoundError if the blob doesn't exist.
        Raises BlobStateError if the blob is not in ``ready`` status.
        Raises BlobIntegrityError if the content hash doesn't match.
        """
        ...

    async def link_blob_to_run(
        self,
        blob_id: UUID,
        run_id: UUID,
        direction: BlobRunLinkDirection,
    ) -> None:
        """Record a blob-to-run linkage (input or output)."""
        ...

    async def get_blob_run_links(
        self,
        blob_id: UUID,
    ) -> list[BlobRunLinkRecord]:
        """Get all run links for a blob."""
        ...

    async def copy_blobs_for_fork(
        self,
        source_session_id: UUID,
        target_session_id: UUID,
    ) -> dict[UUID, BlobRecord]:
        """Copy all ready blobs from source to target session.

        Creates new blob records with new IDs and new storage paths.
        Copies backing files. Respects the per-session quota.

        Returns a mapping of old blob ID → new BlobRecord, enabling
        callers to remap source references in the forked state.
        """
        ...

    async def finalize_run_output_blobs(
        self,
        run_id: UUID,
        success: bool,
    ) -> BlobFinalizationResult:
        """Finalize pending output blobs for a completed/failed run.

        Processes each blob independently — a per-blob operational error
        (concurrent deletion, I/O failure, DB hiccup) does not abort
        finalization of remaining blobs.  Failed blobs are transitioned
        to ``error`` status on a best-effort basis.

        Returns a BlobFinalizationResult with both successfully finalized
        blobs and per-blob error records.  Callers inspect ``result.errors``
        to decide how to surface failures.
        """
        ...
