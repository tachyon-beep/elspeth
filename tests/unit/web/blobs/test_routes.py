"""Tests for blob REST API routes — upload, download, IDOR, MIME enforcement.

Security boundaries tested:
- IDOR protection: blobs cannot be accessed across session boundaries
- storage_path exclusion: internal filesystem paths never leak to API consumers
- MIME type allowlist: only data-oriented types accepted (no executables, images)
- Size limit enforcement: prevents resource exhaustion via oversized uploads
- Content-Disposition header: safe download filename for audit evidence export
"""

from __future__ import annotations

import io

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import UserIdentity
from elspeth.web.blobs.routes import create_blobs_router
from elspeth.web.blobs.service import BlobServiceImpl
from elspeth.web.config import WebSettings
from elspeth.web.sessions.models import metadata
from elspeth.web.sessions.routes import create_session_router
from elspeth.web.sessions.service import SessionServiceImpl

# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------


def _make_app(
    tmp_path,
    user_id: str = "alice",
    max_upload_bytes: int = 10 * 1024 * 1024,
) -> tuple[FastAPI, SessionServiceImpl, BlobServiceImpl]:
    """Create a test app with session and blob routes."""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    metadata.create_all(engine)
    session_service = SessionServiceImpl(engine)
    blob_service = BlobServiceImpl(engine, tmp_path)

    app = FastAPI()

    identity = UserIdentity(user_id=user_id, username=user_id)

    async def mock_user():
        return identity

    app.dependency_overrides[get_current_user] = mock_user

    settings = WebSettings(
        data_dir=tmp_path,
        max_upload_bytes=max_upload_bytes,
    )
    app.state.settings = settings
    app.state.session_service = session_service
    app.state.blob_service = blob_service

    from elspeth.web.middleware.rate_limit import ComposerRateLimiter

    app.state.rate_limiter = ComposerRateLimiter(limit=100)

    app.include_router(create_session_router())
    app.include_router(create_blobs_router())

    return app, session_service, blob_service


def _create_session(client: TestClient, title: str = "Test") -> str:
    """Create a session and return its ID."""
    resp = client.post("/api/sessions", json={"title": title})
    assert resp.status_code == 201
    return resp.json()["id"]


def _upload_blob(
    client: TestClient,
    session_id: str,
    content: bytes = b"col1,col2\na,b",
    filename: str = "data.csv",
    content_type: str = "text/csv",
) -> dict:
    """Upload a blob and return the response body."""
    resp = client.post(
        f"/api/sessions/{session_id}/blobs",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------


class TestUploadBlob:
    """Blob upload: creation, MIME validation, size enforcement."""

    def test_upload_blob_returns_201_with_metadata(self, tmp_path) -> None:
        app, _, _ = _make_app(tmp_path)
        client = TestClient(app)
        session_id = _create_session(client)

        body = _upload_blob(client, session_id)

        assert "id" in body
        assert body["filename"] == "data.csv"
        assert body["mime_type"] == "text/csv"
        assert body["status"] == "ready"
        # storage_path MUST NOT be in the response — internal implementation detail
        assert "storage_path" not in body

    def test_upload_blob_rejects_disallowed_mime_type(self, tmp_path) -> None:
        """MIME allowlist: image/jpeg is not a data format."""
        app, _, _ = _make_app(tmp_path)
        client = TestClient(app)
        session_id = _create_session(client)

        resp = client.post(
            f"/api/sessions/{session_id}/blobs",
            files={"file": ("photo.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg")},
        )
        assert resp.status_code == 415

    def test_upload_blob_enforces_size_limit(self, tmp_path) -> None:
        """Resource exhaustion: oversized uploads rejected before full read."""
        app, _, _ = _make_app(tmp_path, max_upload_bytes=100)
        client = TestClient(app)
        session_id = _create_session(client)

        big_content = b"x" * 200
        resp = client.post(
            f"/api/sessions/{session_id}/blobs",
            files={"file": ("big.csv", io.BytesIO(big_content), "text/csv")},
        )
        assert resp.status_code == 413


# ---------------------------------------------------------------------------
# List and metadata
# ---------------------------------------------------------------------------


class TestListAndMetadata:
    """Blob listing and metadata retrieval."""

    def test_list_blobs_returns_session_blobs(self, tmp_path) -> None:
        app, _, _ = _make_app(tmp_path)
        client = TestClient(app)
        session_id = _create_session(client)

        _upload_blob(client, session_id, filename="a.csv")
        _upload_blob(client, session_id, filename="b.csv")

        resp = client.get(f"/api/sessions/{session_id}/blobs")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_blob_metadata_excludes_storage_path(self, tmp_path) -> None:
        """storage_path is an internal detail — never exposed to API consumers."""
        app, _, _ = _make_app(tmp_path)
        client = TestClient(app)
        session_id = _create_session(client)

        blob = _upload_blob(client, session_id)
        blob_id = blob["id"]

        resp = client.get(f"/api/sessions/{session_id}/blobs/{blob_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "storage_path" not in body
        assert body["filename"] == "data.csv"


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


class TestDownloadBlob:
    """Blob download: content integrity and Content-Disposition header."""

    def test_download_blob_returns_content(self, tmp_path) -> None:
        app, _, _ = _make_app(tmp_path)
        client = TestClient(app)
        session_id = _create_session(client)

        content = b"col1,col2\n1,2\n3,4"
        blob = _upload_blob(client, session_id, content=content)
        blob_id = blob["id"]

        resp = client.get(f"/api/sessions/{session_id}/blobs/{blob_id}/content")
        assert resp.status_code == 200
        assert resp.content == content

    def test_download_content_disposition_header(self, tmp_path) -> None:
        """RFC 5987 encoded filename in Content-Disposition for safe export."""
        app, _, _ = _make_app(tmp_path)
        client = TestClient(app)
        session_id = _create_session(client)

        blob = _upload_blob(client, session_id, filename="data.csv")
        blob_id = blob["id"]

        resp = client.get(f"/api/sessions/{session_id}/blobs/{blob_id}/content")
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "data.csv" in cd


# ---------------------------------------------------------------------------
# IDOR protection — CRITICAL security boundary
# ---------------------------------------------------------------------------


class TestIDORProtection:
    """IDOR: blob access from a different session must return 404, not the blob.

    These tests protect against the most dangerous class of authorization
    bypass: accessing another user's audit evidence by guessing blob IDs.
    404 (not 403) prevents information leakage about blob existence.
    """

    def _make_two_session_app(self, tmp_path):
        """Create shared-DB app with two users, each with a session."""
        engine = create_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        metadata.create_all(engine)
        session_service = SessionServiceImpl(engine)
        blob_service = BlobServiceImpl(engine, tmp_path)

        settings = WebSettings(data_dir=tmp_path)

        def make_app_for_user(uid: str) -> FastAPI:
            app = FastAPI()
            identity = UserIdentity(user_id=uid, username=uid)

            async def mock_user():
                return identity

            app.dependency_overrides[get_current_user] = mock_user
            app.state.session_service = session_service
            app.state.blob_service = blob_service
            app.state.settings = settings

            from elspeth.web.middleware.rate_limit import ComposerRateLimiter

            app.state.rate_limiter = ComposerRateLimiter(limit=100)

            app.include_router(create_session_router())
            app.include_router(create_blobs_router())
            return app

        alice_app = make_app_for_user("alice")
        bob_app = make_app_for_user("bob")

        return TestClient(alice_app), TestClient(bob_app)

    def test_blob_access_from_wrong_session_returns_404(self, tmp_path) -> None:
        """GET metadata for another user's blob returns 404."""
        alice, bob = self._make_two_session_app(tmp_path)

        alice_session = _create_session(alice, "Alice Session")
        bob_session = _create_session(bob, "Bob Session")
        blob = _upload_blob(alice, alice_session)

        resp = bob.get(f"/api/sessions/{bob_session}/blobs/{blob['id']}")
        assert resp.status_code == 404

    def test_blob_delete_from_wrong_session_returns_404(self, tmp_path) -> None:
        """DELETE another user's blob returns 404."""
        alice, bob = self._make_two_session_app(tmp_path)

        alice_session = _create_session(alice, "Alice Session")
        bob_session = _create_session(bob, "Bob Session")
        blob = _upload_blob(alice, alice_session)

        resp = bob.delete(f"/api/sessions/{bob_session}/blobs/{blob['id']}")
        assert resp.status_code == 404

    def test_blob_download_from_wrong_session_returns_404(self, tmp_path) -> None:
        """GET content for another user's blob returns 404."""
        alice, bob = self._make_two_session_app(tmp_path)

        alice_session = _create_session(alice, "Alice Session")
        bob_session = _create_session(bob, "Bob Session")
        blob = _upload_blob(alice, alice_session)

        resp = bob.get(f"/api/sessions/{bob_session}/blobs/{blob['id']}/content")
        assert resp.status_code == 404
