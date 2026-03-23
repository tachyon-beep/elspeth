"""Tests for LandscapeRecorder.store_payload()."""

import pytest

from elspeth.contracts.errors import FrameworkBugError
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder


class TestStorePayload:
    def test_stores_content_and_returns_sha256_hex(self):
        """store_payload() returns a 64-char hex string (SHA-256)."""
        db = LandscapeDB.in_memory()
        import tempfile
        from pathlib import Path

        from elspeth.core.payload_store import FilesystemPayloadStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemPayloadStore(Path(tmpdir))
            recorder = LandscapeRecorder(db, payload_store=store)

            content = b"test processed content for audit"
            result = recorder.store_payload(content, purpose="processed_content")

            # SHA-256 hex digest is 64 characters
            assert isinstance(result, str)
            assert len(result) == 64
            assert all(c in "0123456789abcdef" for c in result)

            # Content is retrievable
            retrieved = store.retrieve(result)
            assert retrieved == content

    def test_raises_framework_bug_error_when_no_payload_store(self):
        """store_payload() crashes with FrameworkBugError when payload_store is None."""
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db, payload_store=None)

        with pytest.raises(FrameworkBugError, match=r"store_payload.*payload_store"):
            recorder.store_payload(b"content", purpose="test")

    def test_store_payload_empty_bytes(self):
        """Empty content is valid — SHA-256 of empty is well-defined."""
        db = LandscapeDB.in_memory()
        import tempfile
        from pathlib import Path

        from elspeth.core.payload_store import FilesystemPayloadStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemPayloadStore(Path(tmpdir))
            recorder = LandscapeRecorder(db, payload_store=store)

            result = recorder.store_payload(b"", purpose="empty_test")
            assert len(result) == 64  # SHA-256 hex

    def test_purpose_label_is_documentation_only(self):
        """The purpose parameter does not affect storage — same content, same hash."""
        db = LandscapeDB.in_memory()
        import tempfile
        from pathlib import Path

        from elspeth.core.payload_store import FilesystemPayloadStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemPayloadStore(Path(tmpdir))
            recorder = LandscapeRecorder(db, payload_store=store)

            content = b"identical content"
            hash1 = recorder.store_payload(content, purpose="purpose_a")
            hash2 = recorder.store_payload(content, purpose="purpose_b")

            assert hash1 == hash2
