"""Tier 1 strictness regression tests for blob response schemas.

``BlobMetadataResponse`` deliberately excludes ``storage_path`` — that is
an internal implementation detail.  ``extra="forbid"`` mechanically
enforces the exclusion: any future refactor that accidentally forwards
``record.storage_path`` into the response constructor crashes rather
than leaking the internal path to clients.

``CreateInlineBlobRequest`` is a Tier 3 request model and already uses
its own ``extra="forbid"`` / field validator contract — it is not a
target of this tightening.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from elspeth.web.blobs.schemas import BlobMetadataResponse


def _valid_kwargs() -> dict[str, object]:
    return {
        "id": "blob-1",
        "session_id": "sess-1",
        "filename": "data.csv",
        "mime_type": "text/csv",
        "size_bytes": 1024,
        "content_hash": "sha256:abc",
        "created_at": datetime.now(UTC),
        "created_by": "user",
        "source_description": None,
        "status": "ready",
    }


class TestBlobStrictCoercionRejected:
    def test_rejects_string_int_size_bytes(self) -> None:
        kwargs = _valid_kwargs()
        kwargs["size_bytes"] = "1024"
        with pytest.raises(ValidationError):
            BlobMetadataResponse(**kwargs)  # type: ignore[arg-type]

    def test_rejects_iso_string_created_at(self) -> None:
        kwargs = _valid_kwargs()
        kwargs["created_at"] = "2026-04-15T10:00:00+00:00"
        with pytest.raises(ValidationError):
            BlobMetadataResponse(**kwargs)  # type: ignore[arg-type]

    def test_rejects_invalid_mime_type(self) -> None:
        """mime_type is a narrowed Literal — arbitrary values must be rejected."""
        kwargs = _valid_kwargs()
        kwargs["mime_type"] = "application/unknown"
        with pytest.raises(ValidationError):
            BlobMetadataResponse(**kwargs)  # type: ignore[arg-type]

    def test_rejects_invalid_status(self) -> None:
        kwargs = _valid_kwargs()
        kwargs["status"] = "archived"
        with pytest.raises(ValidationError):
            BlobMetadataResponse(**kwargs)  # type: ignore[arg-type]


class TestBlobExtraFieldsRejected:
    def test_rejects_extra_field(self) -> None:
        kwargs = _valid_kwargs()
        kwargs["checksum_algorithm"] = "sha256"
        with pytest.raises(ValidationError, match="extra"):
            BlobMetadataResponse(**kwargs)  # type: ignore[arg-type]

    def test_rejects_storage_path_leak(self) -> None:
        """storage_path is an internal detail — must never reach the wire."""
        kwargs = _valid_kwargs()
        kwargs["storage_path"] = "/var/blobs/sess-1/blob-1"
        with pytest.raises(ValidationError, match="extra"):
            BlobMetadataResponse(**kwargs)  # type: ignore[arg-type]


class TestBlobHappyPath:
    def test_full_construction(self) -> None:
        resp = BlobMetadataResponse(**_valid_kwargs())  # type: ignore[arg-type]
        assert resp.status == "ready"
        assert resp.mime_type == "text/csv"

    def test_nullable_content_hash(self) -> None:
        kwargs = _valid_kwargs()
        kwargs["content_hash"] = None
        resp = BlobMetadataResponse(**kwargs)  # type: ignore[arg-type]
        assert resp.content_hash is None
