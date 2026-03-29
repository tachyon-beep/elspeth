"""Tests for session API routes -- CRUD, IDOR, upload, path traversal."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import UserIdentity
from elspeth.web.composer.protocol import ComposerResult
from elspeth.web.composer.state import CompositionState, PipelineMetadata
from elspeth.web.config import WebSettings
from elspeth.web.sessions.models import metadata
from elspeth.web.sessions.protocol import CompositionStateData
from elspeth.web.sessions.routes import create_session_router
from elspeth.web.sessions.service import SessionServiceImpl

# Sentinel empty state for mock composer responses
_EMPTY_STATE = CompositionState(
    source=None,
    nodes=(),
    edges=(),
    outputs=(),
    metadata=PipelineMetadata(),
    version=1,
)


def _make_composer_mock(
    response_text: str = "Sure, I can help.",
    state: CompositionState | None = None,
) -> AsyncMock:
    """Create a mock ComposerServiceImpl.compose that returns a fixed result."""
    mock = AsyncMock()
    mock.compose = AsyncMock(
        return_value=ComposerResult(
            message=response_text,
            state=state or _EMPTY_STATE,
        ),
    )
    return mock


def _make_app(
    tmp_path: Path,
    user_id: str = "alice",
    max_upload_bytes: int = 10 * 1024 * 1024,
) -> tuple[FastAPI, SessionServiceImpl]:
    """Create a test app with session routes and a mock auth user."""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    metadata.create_all(engine)
    service = SessionServiceImpl(engine)

    app = FastAPI()

    # Override auth dependency to return a fixed user
    identity = UserIdentity(user_id=user_id, username=user_id)

    async def mock_user():
        return identity

    app.dependency_overrides[get_current_user] = mock_user

    # Set up app state
    app.state.session_service = service
    app.state.settings = WebSettings(
        data_dir=tmp_path,
        max_upload_bytes=max_upload_bytes,
    )
    # composer_service is set to None here; tests that POST messages
    # must replace it with a mock before sending requests.
    app.state.composer_service = None

    router = create_session_router()
    app.include_router(router)

    return app, service


class TestSessionCRUDRoutes:
    """Tests for session create, list, get, delete endpoints."""

    def test_create_session(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        response = client.post(
            "/api/sessions",
            json={"title": "My Pipeline"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "My Pipeline"
        assert body["user_id"] == "alice"
        assert "id" in body

    def test_create_session_default_title(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        response = client.post("/api/sessions", json={})
        assert response.status_code == 201
        assert response.json()["title"] == "New session"

    def test_list_sessions(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        client.post("/api/sessions", json={"title": "S1"})
        client.post("/api/sessions", json={"title": "S2"})

        response = client.get("/api/sessions")
        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) == 2

    def test_get_session(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        create_resp = client.post(
            "/api/sessions",
            json={"title": "Test"},
        )
        session_id = create_resp.json()["id"]

        get_resp = client.get(f"/api/sessions/{session_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == session_id

    def test_get_session_not_found(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        response = client.get(f"/api/sessions/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_delete_session(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        create_resp = client.post(
            "/api/sessions",
            json={"title": "To Delete"},
        )
        session_id = create_resp.json()["id"]

        del_resp = client.delete(f"/api/sessions/{session_id}")
        assert del_resp.status_code == 204

        # Verify it's gone
        get_resp = client.get(f"/api/sessions/{session_id}")
        assert get_resp.status_code == 404


class TestIDORProtection:
    """Tests for W5 -- IDOR protection on all session-scoped routes.

    Creates a session as user A, then attempts to access it as user B.
    All should return 404 (not 403).
    """

    def test_idor_session_crud(self, tmp_path) -> None:
        """Shared-DB IDOR test: alice creates, bob tries to access."""
        engine = create_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        metadata.create_all(engine)
        service = SessionServiceImpl(engine)

        # Create two apps sharing the same service
        def make_app_for_user(uid: str) -> FastAPI:
            app = FastAPI()
            identity = UserIdentity(user_id=uid, username=uid)

            async def mock_user():
                return identity

            app.dependency_overrides[get_current_user] = mock_user
            app.state.session_service = service
            app.state.settings = WebSettings(data_dir=tmp_path)
            app.state.catalog_service = None
            app.include_router(create_session_router())
            return app

        alice_app = make_app_for_user("alice")
        bob_app = make_app_for_user("bob")

        alice_client = TestClient(alice_app)
        bob_client = TestClient(bob_app)

        # Alice creates a session
        resp = alice_client.post(
            "/api/sessions",
            json={"title": "Alice Only"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["id"]

        # Bob tries to GET it -- should be 404
        resp = bob_client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 404

        # Bob tries to DELETE it -- should be 404
        resp = bob_client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 404

        # Bob tries to GET messages -- should be 404
        resp = bob_client.get(f"/api/sessions/{session_id}/messages")
        assert resp.status_code == 404

        # Bob tries to POST a message -- should be 404
        resp = bob_client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "hacked"},
        )
        assert resp.status_code == 404

        # Bob tries to GET state -- should be 404
        resp = bob_client.get(f"/api/sessions/{session_id}/state")
        assert resp.status_code == 404

        # Bob tries to GET state versions -- should be 404
        resp = bob_client.get(f"/api/sessions/{session_id}/state/versions")
        assert resp.status_code == 404

        # Bob tries to revert state -- should be 404
        resp = bob_client.post(
            f"/api/sessions/{session_id}/state/revert",
            json={"state_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

        # Alice can still access her own session
        resp = alice_client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200


class TestMessageRoutes:
    """Tests for message send and retrieval endpoints."""

    def test_send_message(self, tmp_path) -> None:
        mock_composer = _make_composer_mock(response_text="Got it!")

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Chat"})
        session_id = resp.json()["id"]

        msg_resp = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Hello, build me a pipeline"},
        )
        assert msg_resp.status_code == 200
        body = msg_resp.json()
        assert body["message"]["content"] == "Got it!"
        assert body["message"]["role"] == "assistant"
        # State unchanged (version stayed at 1) -> no state in response
        assert body["state"] is None

    def test_get_messages(self, tmp_path) -> None:
        mock_composer = _make_composer_mock()

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Chat"})
        session_id = resp.json()["id"]

        client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "First"},
        )
        client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Second"},
        )

        msgs_resp = client.get(f"/api/sessions/{session_id}/messages")
        assert msgs_resp.status_code == 200
        messages = msgs_resp.json()
        # Each POST creates a user message + assistant message = 4 total
        assert len(messages) == 4
        assert messages[0]["content"] == "First"
        assert messages[0]["role"] == "user"
        assert messages[1]["content"] == "Sure, I can help."
        assert messages[1]["role"] == "assistant"


class TestStateRoutes:
    """Tests for composition state endpoints."""

    def test_get_state_empty(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Empty"})
        session_id = resp.json()["id"]

        state_resp = client.get(f"/api/sessions/{session_id}/state")
        assert state_resp.status_code == 200
        assert state_resp.json() is None

    def test_get_state_versions(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Pipeline"})
        session_id = resp.json()["id"]

        versions_resp = client.get(
            f"/api/sessions/{session_id}/state/versions",
        )
        assert versions_resp.status_code == 200
        assert versions_resp.json() == []


class TestRevertEndpoint:
    """Tests for POST /api/sessions/{id}/state/revert (R1)."""

    @pytest.mark.asyncio
    async def test_revert_creates_new_version(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        # Create session and two state versions via the service
        session = await service.create_session("alice", "Pipeline", "local")
        v1 = await service.save_composition_state(
            session.id,
            CompositionStateData(source={"type": "csv"}, is_valid=True),
        )
        await service.save_composition_state(
            session.id,
            CompositionStateData(source={"type": "api"}, is_valid=True),
        )

        # Revert to v1
        resp = client.post(
            f"/api/sessions/{session.id}/state/revert",
            json={"state_id": str(v1.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == 3
        # Should match v1's source, not v2's
        assert body["source"] == {"type": "csv"}
        # Lineage: new version derives from v1
        assert body["derived_from_state_id"] == str(v1.id)

    @pytest.mark.asyncio
    async def test_revert_injects_system_message(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        v1 = await service.save_composition_state(
            session.id,
            CompositionStateData(is_valid=True),
        )
        await service.save_composition_state(
            session.id,
            CompositionStateData(is_valid=True),
        )

        client.post(
            f"/api/sessions/{session.id}/state/revert",
            json={"state_id": str(v1.id)},
        )

        # Check that a system message was injected
        msgs_resp = client.get(f"/api/sessions/{session.id}/messages")
        messages = msgs_resp.json()
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0]["content"] == "Pipeline reverted to version 1."

    @pytest.mark.asyncio
    async def test_revert_idor_protection(self, tmp_path) -> None:
        """Revert to a state in another user's session returns 404."""
        engine = create_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        metadata.create_all(engine)
        service = SessionServiceImpl(engine)

        def make_app_for_user(uid: str) -> FastAPI:
            app = FastAPI()
            identity = UserIdentity(user_id=uid, username=uid)

            async def mock_user():
                return identity

            app.dependency_overrides[get_current_user] = mock_user
            app.state.session_service = service
            app.state.settings = WebSettings(data_dir=tmp_path)
            app.include_router(create_session_router())
            return app

        bob_app = make_app_for_user("bob")
        bob_client = TestClient(bob_app)

        # Alice creates a session with a state
        session = await service.create_session("alice", "Alice Only", "local")
        v1 = await service.save_composition_state(
            session.id,
            CompositionStateData(is_valid=True),
        )

        # Bob tries to revert -- should be 404
        resp = bob_client.post(
            f"/api/sessions/{session.id}/state/revert",
            json={"state_id": str(v1.id)},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_revert_state_not_belonging_to_session(self, tmp_path) -> None:
        """Revert with a state_id from a different session returns 404."""
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        s1 = await service.create_session("alice", "Session 1", "local")
        s2 = await service.create_session("alice", "Session 2", "local")
        v1_s2 = await service.save_composition_state(
            s2.id,
            CompositionStateData(is_valid=True),
        )

        # Try to revert s1 using s2's state -- should fail
        resp = client.post(
            f"/api/sessions/{s1.id}/state/revert",
            json={"state_id": str(v1_s2.id)},
        )
        assert resp.status_code == 404


class TestUploadRoute:
    """Tests for file upload endpoint including path traversal (B5)."""

    def test_upload_file(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Upload"})
        session_id = resp.json()["id"]

        file_content = b"col1,col2\na,b\nc,d"
        upload_resp = client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("data.csv", io.BytesIO(file_content), "text/csv")},
        )
        assert upload_resp.status_code == 200
        body = upload_resp.json()
        assert body["filename"] == "data.csv"
        assert body["size_bytes"] == len(file_content)
        assert "path" in body

        # Path should be relative (not start with /)
        assert not body["path"].startswith("/")

        # Verify the file exists on disk via data_dir / relative path
        saved_path = tmp_path / body["path"]
        assert saved_path.exists()
        assert saved_path.read_bytes() == file_content

    def test_upload_path_traversal_user_id_sanitized(self, tmp_path) -> None:
        """B5: user_id containing ../../etc is sanitized to just 'etc'."""
        app, _ = _make_app(tmp_path, user_id="../../etc")
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Hack"})
        session_id = resp.json()["id"]

        file_content = b"malicious"
        upload_resp = client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("payload.txt", io.BytesIO(file_content), "text/plain")},
        )
        assert upload_resp.status_code == 200
        relative_path = upload_resp.json()["path"]
        saved_path = Path(relative_path)

        # Path should be relative (not start with /)
        assert not relative_path.startswith("/")
        # The path should NOT contain ".." components
        assert ".." not in str(saved_path)
        # Should be under uploads/etc/ (sanitized)
        assert "etc" in saved_path.parts
        assert (tmp_path / relative_path).is_relative_to(tmp_path / "uploads")

    def test_upload_path_traversal_filename_sanitized(self, tmp_path) -> None:
        """Filename containing path traversal is sanitized."""
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Hack"})
        session_id = resp.json()["id"]

        file_content = b"malicious"
        upload_resp = client.post(
            f"/api/sessions/{session_id}/upload",
            files={
                "file": (
                    "../../etc/passwd",
                    io.BytesIO(file_content),
                    "application/octet-stream",
                ),
            },
        )
        assert upload_resp.status_code == 200
        relative_path = upload_resp.json()["path"]
        saved_path = Path(relative_path)
        # Path should be relative (not start with /)
        assert not relative_path.startswith("/")
        # Filename should be just "passwd", not "../../etc/passwd"
        assert saved_path.name == "passwd"
        assert ".." not in str(saved_path)

    def test_upload_file_too_large(self, tmp_path) -> None:
        """Files exceeding max_upload_bytes are rejected with 413."""
        app, _ = _make_app(tmp_path, max_upload_bytes=100)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Big File"})
        session_id = resp.json()["id"]

        big_content = b"x" * 200  # 200 bytes > 100 byte limit
        upload_resp = client.post(
            f"/api/sessions/{session_id}/upload",
            files={
                "file": (
                    "big.dat",
                    io.BytesIO(big_content),
                    "application/octet-stream",
                ),
            },
        )
        assert upload_resp.status_code == 413

    def test_upload_empty_user_id_sanitization(self, tmp_path) -> None:
        """User ID of '..' sanitizes to empty via Path.name, which should raise."""
        app, _ = _make_app(tmp_path, user_id="..")
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Hack"})
        session_id = resp.json()["id"]

        upload_resp = client.post(
            f"/api/sessions/{session_id}/upload",
            files={"file": ("test.txt", io.BytesIO(b"data"), "text/plain")},
        )
        assert upload_resp.status_code == 400


class TestYamlEndpoint:
    """Tests for GET /api/sessions/{id}/state/yaml."""

    @pytest.mark.asyncio
    async def test_yaml_returns_yaml_when_state_exists(self, tmp_path) -> None:
        """Returns generated YAML when composition state exists."""
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        await service.save_composition_state(
            session.id,
            CompositionStateData(
                source={"plugin": "csv", "on_success": "out", "options": {"path": "/data.csv"}, "on_validation_failure": "quarantine"},
                outputs=[{"name": "out", "plugin": "csv", "options": {}, "on_write_failure": "quarantine"}],
                metadata_={"name": "Test Pipeline", "description": ""},
                is_valid=True,
            ),
        )

        resp = client.get(f"/api/sessions/{session.id}/state/yaml")
        assert resp.status_code == 200
        body = resp.json()
        assert "yaml" in body
        assert "csv" in body["yaml"]

    def test_yaml_returns_404_when_no_state(self, tmp_path) -> None:
        """No composition state yet -> 404."""
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Empty"})
        session_id = resp.json()["id"]

        yaml_resp = client.get(f"/api/sessions/{session_id}/state/yaml")
        assert yaml_resp.status_code == 404


class TestRunAlreadyActiveError:
    """Tests for seam contract D: RunAlreadyActiveError → 409 with error_type.

    The create_run endpoint does not exist yet (Sub-5), but the exception
    handler is wired. These tests exercise it via direct service calls +
    app-level exception propagation to verify the contract.
    """

    @pytest.mark.asyncio
    async def test_run_already_active_returns_409(self, tmp_path) -> None:
        """RunAlreadyActiveError produces 409 with error_type field."""
        from elspeth.web.sessions.protocol import RunAlreadyActiveError

        app, service = _make_app(tmp_path)

        session = await service.create_session("alice", "Pipeline", "local")
        v1 = await service.save_composition_state(
            session.id,
            CompositionStateData(is_valid=True),
        )
        # Create a run to block the session
        await service.create_run(session.id, v1.id)

        # Register the app-level exception handler (wired in create_app,
        # but our test app uses create_session_router directly). Wire it here.
        from fastapi.responses import JSONResponse

        @app.exception_handler(RunAlreadyActiveError)
        async def handle_run_already_active(
            request,
            exc: RunAlreadyActiveError,
        ) -> JSONResponse:
            return JSONResponse(
                status_code=409,
                content={"detail": str(exc), "error_type": "run_already_active"},
            )

        # Add a test endpoint that triggers the error
        @app.post("/api/_test_create_run")
        async def _test_create_run():
            await service.create_run(session.id, v1.id)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/_test_create_run")
        assert resp.status_code == 409
        body = resp.json()
        assert body["error_type"] == "run_already_active"
        assert "detail" in body


class TestNewStateHasNoLineage:
    """Test that fresh composition states have null derived_from_state_id."""

    @pytest.mark.asyncio
    async def test_fresh_state_has_null_derived_from(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        await service.save_composition_state(
            session.id,
            CompositionStateData(source={"type": "csv"}, is_valid=True),
        )

        resp = client.get(f"/api/sessions/{session.id}/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["derived_from_state_id"] is None


class TestPaginationRoutes:
    """Tests for limit/offset query parameters on list endpoints."""

    def test_list_sessions_pagination(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        for i in range(5):
            client.post("/api/sessions", json={"title": f"S{i}"})

        resp = client.get("/api/sessions?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        resp = client.get("/api/sessions?limit=2&offset=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_sessions_pagination_validation(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        # limit < 1
        resp = client.get("/api/sessions?limit=0")
        assert resp.status_code == 422

        # limit > 200
        resp = client.get("/api/sessions?limit=201")
        assert resp.status_code == 422

        # offset < 0
        resp = client.get("/api/sessions?offset=-1")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_messages_pagination(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Chat"})
        session_id = resp.json()["id"]

        # Add messages directly via service to avoid composer dependency
        session = await service.get_session(uuid.UUID(session_id))
        for i in range(5):
            await service.add_message(session.id, "user", f"Msg {i}")

        resp = client.get(f"/api/sessions/{session_id}/messages?limit=2")
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2
        assert messages[0]["content"] == "Msg 0"

        resp = client.get(
            f"/api/sessions/{session_id}/messages?limit=2&offset=3",
        )
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2
        assert messages[0]["content"] == "Msg 3"

    def test_get_messages_pagination_validation(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Chat"})
        session_id = resp.json()["id"]

        resp = client.get(f"/api/sessions/{session_id}/messages?limit=0")
        assert resp.status_code == 422

        resp = client.get(f"/api/sessions/{session_id}/messages?limit=501")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_state_versions_pagination(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        for _ in range(5):
            await service.save_composition_state(
                session.id,
                CompositionStateData(is_valid=False),
            )

        resp = client.get(
            f"/api/sessions/{session.id}/state/versions?limit=2",
        )
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) == 2
        assert versions[0]["version"] == 1

        resp = client.get(
            f"/api/sessions/{session.id}/state/versions?limit=2&offset=3",
        )
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) == 2
        assert versions[0]["version"] == 4

    def test_get_state_versions_pagination_validation(self, tmp_path) -> None:
        app, _ = _make_app(tmp_path)
        client = TestClient(app)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        resp = client.get(
            f"/api/sessions/{session_id}/state/versions?limit=0",
        )
        assert resp.status_code == 422

        resp = client.get(
            f"/api/sessions/{session_id}/state/versions?limit=201",
        )
        assert resp.status_code == 422
