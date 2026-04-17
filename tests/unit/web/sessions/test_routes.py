"""Tests for session API routes -- CRUD, IDOR, fork, YAML."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml
from fastapi import FastAPI
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import UserIdentity
from elspeth.web.composer.protocol import ComposerPluginCrashError, ComposerResult
from elspeth.web.composer.state import CompositionState, PipelineMetadata
from elspeth.web.config import WebSettings
from elspeth.web.sessions.engine import create_session_engine
from elspeth.web.sessions.migrations import run_migrations
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
    engine = create_session_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    run_migrations(engine)
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
        composer_max_composition_turns=15,
        composer_max_discovery_turns=10,
        composer_timeout_seconds=85.0,
        composer_rate_limit_per_minute=10,
    )
    # composer_service is set to None here; tests that POST messages
    # must replace it with a mock before sending requests.
    app.state.composer_service = None

    from unittest.mock import MagicMock

    from elspeth.web.middleware.rate_limit import ComposerRateLimiter

    app.state.rate_limiter = ComposerRateLimiter(limit=100)

    # Minimal mock for execution service — delete_session calls
    # cleanup_session_lock() after archiving.
    app.state.execution_service = MagicMock()

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

        # Verify cleanup_session_lock was called with the correct session ID
        app.state.execution_service.cleanup_session_lock.assert_called_once_with(session_id)

        # Verify it's gone
        get_resp = client.get(f"/api/sessions/{session_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_session_blocked_by_active_run(self, tmp_path) -> None:
        """Deleting a session with a pending/running run returns 409.

        Without this guard, archive_session() deletes run rows and blob
        directories out from under the background pipeline worker.
        """
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        create_resp = client.post("/api/sessions", json={"title": "Active Run"})
        session_id = uuid.UUID(create_resp.json()["id"])

        # Create a pending run via the service layer
        state = await service.save_composition_state(
            session_id,
            CompositionStateData(is_valid=True),
        )
        await service.create_run(session_id, state.id)

        del_resp = client.delete(f"/api/sessions/{session_id}")
        assert del_resp.status_code == 409
        assert "active" in del_resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_session_allowed_after_run_completes(self, tmp_path) -> None:
        """After a run reaches a terminal state, deletion is allowed."""
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        create_resp = client.post("/api/sessions", json={"title": "Completed Run"})
        session_id = uuid.UUID(create_resp.json()["id"])

        state = await service.save_composition_state(
            session_id,
            CompositionStateData(is_valid=True),
        )
        run = await service.create_run(session_id, state.id)
        await service.update_run_status(run.id, "running")
        await service.update_run_status(run.id, "completed")

        del_resp = client.delete(f"/api/sessions/{session_id}")
        assert del_resp.status_code == 204


class TestIDORProtection:
    """Tests for W5 -- IDOR protection on all session-scoped routes.

    Creates a session as user A, then attempts to access it as user B.
    All should return 404 (not 403).
    """

    def test_idor_session_crud(self, tmp_path) -> None:
        """Shared-DB IDOR test: alice creates, bob tries to access."""
        engine = create_session_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        run_migrations(engine)
        service = SessionServiceImpl(engine)

        # Create two apps sharing the same service
        def make_app_for_user(uid: str) -> FastAPI:
            app = FastAPI()
            identity = UserIdentity(user_id=uid, username=uid)

            async def mock_user():
                return identity

            app.dependency_overrides[get_current_user] = mock_user
            app.state.session_service = service
            app.state.settings = WebSettings(
                data_dir=tmp_path,
                composer_max_composition_turns=15,
                composer_max_discovery_turns=10,
                composer_timeout_seconds=85.0,
                composer_rate_limit_per_minute=10,
            )
            app.state.catalog_service = None

            from elspeth.web.middleware.rate_limit import ComposerRateLimiter

            app.state.rate_limiter = ComposerRateLimiter(limit=100)
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

    def test_send_message_with_state_id(self, tmp_path) -> None:
        """Message with state_id references a specific composition state snapshot.

        Exercises the UUID-typed state_id field in SendMessageRequest end-to-end:
        FastAPI parses the JSON string into a UUID, the route validates the state
        belongs to the session, and the user message is persisted with the
        client-asserted state_id as its composition_state_id (AD-2 provenance).
        """
        import asyncio

        mock_composer = _make_composer_mock(response_text="Acknowledged")

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app)

        # Create a session
        resp = client.post("/api/sessions", json={"title": "Chat"})
        session_id = resp.json()["id"]

        # Create a composition state via the service (the mock composer
        # returns version=1 which won't trigger state persistence in the
        # route, so we seed one directly).
        loop = asyncio.new_event_loop()
        state_record = loop.run_until_complete(
            service.save_composition_state(
                uuid.UUID(session_id),
                CompositionStateData(
                    metadata_={"name": "Test", "description": ""},
                    is_valid=True,
                ),
            ),
        )
        loop.close()
        state_id = str(state_record.id)

        # Send message WITH state_id as UUID string in JSON body
        msg_resp = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Hello", "state_id": state_id},
        )
        assert msg_resp.status_code == 200
        body = msg_resp.json()
        assert body["message"]["role"] == "assistant"
        assert body["message"]["content"] == "Acknowledged"

        # Verify provenance: the user message was persisted with the
        # client-asserted state_id as its composition_state_id.
        msgs_resp = client.get(f"/api/sessions/{session_id}/messages")
        messages = msgs_resp.json()
        user_msg = next(m for m in messages if m["role"] == "user")
        assert user_msg["composition_state_id"] == state_id

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


class TestRecomposeConvergencePartialState:
    """Tests for partial state persistence on composer convergence failure."""

    def test_recompose_convergence_preserves_partial_state(self, tmp_path) -> None:
        """When recompose hits convergence error with partial state,
        the state is persisted and included in the 422 response."""
        import asyncio

        from elspeth.web.composer.protocol import ComposerConvergenceError

        partial = CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(),
            version=2,  # > initial (1), so it's a real mutation
        )

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerConvergenceError(
                max_turns=5,
                budget_exhausted="composition",
                partial_state=partial,
            ),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        # Create session
        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        # Simulate a failed send_message: user message saved, no assistant
        # response. This is the precondition for recompose — the last
        # message must be a user turn.
        loop = asyncio.new_event_loop()
        loop.run_until_complete(service.add_message(uuid.UUID(session_id), "user", "Build a CSV pipeline"))
        loop.close()

        recompose_resp = client.post(f"/api/sessions/{session_id}/recompose")

        assert recompose_resp.status_code == 422
        detail = recompose_resp.json()["detail"]
        assert detail["error_type"] == "convergence"
        assert "partial_state" in detail

    def test_recompose_convergence_without_partial_state(self, tmp_path) -> None:
        """When convergence error has no partial state (no mutations),
        response omits partial_state key."""
        import asyncio

        from elspeth.web.composer.protocol import ComposerConvergenceError

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerConvergenceError(
                max_turns=3,
                budget_exhausted="discovery",
                partial_state=None,
            ),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        loop = asyncio.new_event_loop()
        loop.run_until_complete(service.add_message(uuid.UUID(session_id), "user", "Build something"))
        loop.close()

        recompose_resp = client.post(f"/api/sessions/{session_id}/recompose")

        assert recompose_resp.status_code == 422
        detail = recompose_resp.json()["detail"]
        assert detail["error_type"] == "convergence"
        assert "partial_state" not in detail

    def test_convergence_redacts_blob_path_from_response_but_preserves_in_db(self, tmp_path) -> None:
        """When partial_state has a blob-backed source, the HTTP response must
        redact the internal storage path while the DB copy retains it."""
        import asyncio

        from elspeth.contracts.freeze import deep_freeze
        from elspeth.web.composer.protocol import ComposerConvergenceError
        from elspeth.web.composer.state import SourceSpec

        partial = CompositionState(
            source=SourceSpec(
                plugin="csv",
                options=deep_freeze(
                    {
                        "path": "/internal/blobs/data.csv",
                        "blob_ref": "abc123",
                        "schema": {"mode": "observed"},
                    }
                ),
                on_success="t1",
                on_validation_failure="quarantine",
            ),
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(),
            version=2,
        )

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerConvergenceError(
                max_turns=5,
                budget_exhausted="composition",
                partial_state=partial,
            ),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        # Create session and seed a user message for recompose precondition
        resp = client.post("/api/sessions", json={"title": "Blob test"})
        session_id = resp.json()["id"]

        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            service.add_message(uuid.UUID(session_id), "user", "Load my CSV"),
        )
        loop.close()

        recompose_resp = client.post(f"/api/sessions/{session_id}/recompose")

        assert recompose_resp.status_code == 422
        detail = recompose_resp.json()["detail"]
        assert detail["error_type"] == "convergence"

        # HTTP response: path must be redacted, blob_ref must be present
        response_source_opts = detail["partial_state"]["source"]["options"]
        assert "path" not in response_source_opts
        assert response_source_opts["blob_ref"] == "abc123"

        # DB copy: path must be preserved alongside blob_ref
        loop = asyncio.new_event_loop()
        db_record = loop.run_until_complete(
            service.get_current_state(uuid.UUID(session_id)),
        )
        loop.close()

        assert db_record is not None
        assert db_record.source is not None, "composition state must carry a source"
        db_source_opts = db_record.source["options"]
        assert db_source_opts["path"] == "/internal/blobs/data.csv"
        assert db_source_opts["blob_ref"] == "abc123"


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
        engine = create_session_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        run_migrations(engine)
        service = SessionServiceImpl(engine)

        def make_app_for_user(uid: str) -> FastAPI:
            app = FastAPI()
            identity = UserIdentity(user_id=uid, username=uid)

            async def mock_user():
                return identity

            app.dependency_overrides[get_current_user] = mock_user
            app.state.session_service = service
            app.state.settings = WebSettings(
                data_dir=tmp_path,
                composer_max_composition_turns=15,
                composer_max_discovery_turns=10,
                composer_timeout_seconds=85.0,
                composer_rate_limit_per_minute=10,
            )

            from elspeth.web.middleware.rate_limit import ComposerRateLimiter

            app.state.rate_limiter = ComposerRateLimiter(limit=100)
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


class TestYamlEndpoint:
    """Tests for GET /api/sessions/{id}/state/yaml."""

    @pytest.mark.asyncio
    async def test_yaml_returns_yaml_when_state_exists(self, tmp_path) -> None:
        """Returns generated YAML for a valid state even when edge_contracts is empty."""
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        await service.save_composition_state(
            session.id,
            CompositionStateData(
                source={"plugin": "csv", "on_success": "out", "options": {"path": "/data.csv"}, "on_validation_failure": "quarantine"},
                outputs=[
                    {
                        "name": "out",
                        "plugin": "csv",
                        "options": {"path": "outputs/out.csv", "schema": {"mode": "observed"}},
                        "on_write_failure": "discard",
                    }
                ],
                metadata_={"name": "Test Pipeline", "description": ""},
                is_valid=False,
            ),
        )

        resp = client.get(f"/api/sessions/{session.id}/state/yaml")
        assert resp.status_code == 200
        body = resp.json()
        assert "yaml" in body
        assert "csv" in body["yaml"]

    @pytest.mark.asyncio
    async def test_yaml_allows_connection_valid_state_without_ui_edges(self, tmp_path) -> None:
        """Connection-defined pipelines should export even when the editor graph is incomplete."""
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        await service.save_composition_state(
            session.id,
            CompositionStateData(
                source={
                    "plugin": "text",
                    "on_success": "mapper_in",
                    "options": {
                        "path": "/data/input.txt",
                        "column": "text",
                        "schema": {"mode": "observed"},
                    },
                    "on_validation_failure": "quarantine",
                },
                nodes=[
                    {
                        "id": "map_body",
                        "node_type": "transform",
                        "plugin": "field_mapper",
                        "input": "mapper_in",
                        "on_success": "main",
                        "on_error": "discard",
                        "options": {
                            "schema": {"mode": "observed"},
                            "mapping": {"text": "body"},
                        },
                        "condition": None,
                        "routes": None,
                        "fork_to": None,
                        "branches": None,
                        "policy": None,
                        "merge": None,
                    },
                ],
                edges=[],
                outputs=[
                    {
                        "name": "main",
                        "plugin": "csv",
                        "options": {
                            "path": "outputs/out.csv",
                            "schema": {"mode": "observed", "required_fields": ["body"]},
                        },
                        "on_write_failure": "discard",
                    }
                ],
                metadata_={"name": "Connection-only Pipeline", "description": ""},
                is_valid=False,
            ),
        )

        resp = client.get(f"/api/sessions/{session.id}/state/yaml")
        assert resp.status_code == 200
        assert "field_mapper" in resp.json()["yaml"]
        assert "body" in resp.json()["yaml"]

    @pytest.mark.asyncio
    async def test_yaml_serializes_coalesce_on_success_runtime_route(self, tmp_path) -> None:
        """Coalesce terminal routing must survive export/reload parity checks."""
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        await service.save_composition_state(
            session.id,
            CompositionStateData(
                source={
                    "plugin": "csv",
                    "on_success": "gate_in",
                    "options": {"path": "/data/input.csv"},
                    "on_validation_failure": "quarantine",
                },
                nodes=[
                    {
                        "id": "fork_gate",
                        "node_type": "gate",
                        "plugin": None,
                        "input": "gate_in",
                        "on_success": None,
                        "on_error": None,
                        "options": {},
                        "condition": "True",
                        "routes": {},
                        "fork_to": ["path_a", "path_b"],
                        "branches": None,
                        "policy": None,
                        "merge": None,
                    },
                    {
                        "id": "merge_point",
                        "node_type": "coalesce",
                        "plugin": None,
                        "input": "join",
                        "on_success": "main",
                        "on_error": None,
                        "options": {},
                        "condition": None,
                        "routes": None,
                        "fork_to": None,
                        "branches": ["path_a", "path_b"],
                        "policy": "require_all",
                        "merge": "nested",
                    },
                ],
                edges=[],
                outputs=[
                    {
                        "name": "main",
                        "plugin": "csv",
                        "options": {"path": "outputs/out.csv"},
                        "on_write_failure": "discard",
                    }
                ],
                metadata_={"name": "Fork and merge", "description": ""},
                is_valid=False,
            ),
        )

        resp = client.get(f"/api/sessions/{session.id}/state/yaml")

        assert resp.status_code == 200
        doc = yaml.safe_load(resp.json()["yaml"])
        assert doc["coalesce"][0]["on_success"] == "main"

    @pytest.mark.asyncio
    async def test_yaml_returns_409_when_current_state_is_invalid(self, tmp_path) -> None:
        app, service = _make_app(tmp_path)
        client = TestClient(app)

        session = await service.create_session("alice", "Pipeline", "local")
        await service.save_composition_state(
            session.id,
            CompositionStateData(
                source={
                    "plugin": "csv",
                    "on_success": "t1",
                    "options": {"path": "/data/blobs/input.csv", "schema": {"mode": "observed"}},
                    "on_validation_failure": "quarantine",
                },
                nodes=[
                    {
                        "id": "t1",
                        "node_type": "transform",
                        "plugin": "value_transform",
                        "input": "t1",
                        "on_success": "main",
                        "on_error": "discard",
                        "options": {
                            "required_input_fields": ["text"],
                            "operations": [{"target": "out", "expression": "row['text']"}],
                            "schema": {"mode": "observed"},
                        },
                        "condition": None,
                        "routes": None,
                        "fork_to": None,
                        "branches": None,
                        "policy": None,
                        "merge": None,
                    },
                ],
                outputs=[
                    {
                        "name": "main",
                        "plugin": "csv",
                        "options": {"path": "outputs/out.csv", "schema": {"mode": "observed"}},
                        "on_write_failure": "discard",
                    }
                ],
                metadata_={"name": "Invalid Contract Pipeline", "description": ""},
                is_valid=True,
            ),
        )

        resp = client.get(f"/api/sessions/{session.id}/state/yaml")
        assert resp.status_code == 409
        assert "invalid" in resp.json()["detail"].lower()

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


class TestComposePluginCrashResponse:
    """Plugin TypeError/ValueError from compose() must produce a structured 500.

    After the Task 4 narrowing, plugin bugs escape the service layer instead
    of being laundered as LLM retries. The route handler MUST shape these
    into a documented response rather than letting FastAPI's default handler
    emit an arbitrary traceback.

    Audit-integrity invariant: exception message content — especially
    fragments from __cause__-chained exceptions that may include DB URLs,
    filesystem paths, or secret material — MUST NOT appear in the response
    body. Only the documented error_type + generic detail string is echoed.
    """

    SECRET_PATH = "/etc/elspeth/secrets/bootstrap.key"

    def test_compose_plugin_value_error_returns_structured_500(self, tmp_path) -> None:
        original = ValueError(f"plugin bug: {self.SECRET_PATH}")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=None),
        )

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Build me a pipeline"},
        )

        assert response.status_code == 500
        body = response.json()
        # FastAPI serializes HTTPException(detail={...}) as {"detail": {...}}.
        assert isinstance(body.get("detail"), dict), body
        assert body["detail"]["error_type"] == "composer_plugin_error"
        assert "user-retryable" in body["detail"]["detail"].lower()

        # Audit-integrity: exception message and cause content MUST NOT leak.
        body_text = response.text
        assert "plugin bug" not in body_text
        assert self.SECRET_PATH not in body_text
        assert "ValueError" not in body_text  # exception class also redacted

    def test_recompose_plugin_type_error_returns_structured_500(self, tmp_path) -> None:
        import asyncio

        original = TypeError(f"plugin bug: NoneType has no attribute 'read' from {self.SECRET_PATH}")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=None),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        # Recompose requires a pre-existing trailing user message (see
        # TestRecomposeConvergencePartialState for the template).
        loop = asyncio.new_event_loop()
        loop.run_until_complete(service.add_message(uuid.UUID(session_id), "user", "Build something"))
        loop.close()

        response = client.post(f"/api/sessions/{session_id}/recompose")

        assert response.status_code == 500
        body = response.json()
        assert isinstance(body.get("detail"), dict), body
        assert body["detail"]["error_type"] == "composer_plugin_error"

        body_text = response.text
        assert "plugin bug" not in body_text
        assert self.SECRET_PATH not in body_text
        assert "NoneType" not in body_text
        assert "TypeError" not in body_text

    def test_compose_plugin_crash_persists_partial_state(self, tmp_path) -> None:
        """P1 regression fix: when a plugin crashes AFTER one or more tool
        calls succeeded in the same request, the accumulated ``partial_state``
        MUST be persisted into ``composition_states`` before the 500 is
        returned.  Without this, recompose restarts from the stale
        pre-request state and silently reverts the LLM's successful mutations.

        Symmetric with ``TestRecomposeConvergencePartialState`` for the
        convergence-error path.
        """
        import asyncio

        partial = CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(name="after-first-mutation"),
            version=5,
        )
        original = ValueError(f"plugin bug after mutation: {self.SECRET_PATH}")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=partial),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Build me a pipeline"},
        )
        assert response.status_code == 500
        body = response.json()
        assert body["detail"]["error_type"] == "composer_plugin_error"
        # Response body still fully redacted — persisting partial_state
        # into composition_states does NOT echo it on the failure response.
        assert self.SECRET_PATH not in response.text

        # The partial_state row MUST exist in composition_states now.
        loop = asyncio.new_event_loop()
        try:
            persisted = loop.run_until_complete(service.get_current_state(uuid.UUID(session_id)))
        finally:
            loop.close()
        assert persisted is not None, "partial_state must be persisted to composition_states on plugin crash"
        assert persisted.metadata_ is not None
        assert persisted.metadata_.get("name") == "after-first-mutation"

    def test_compose_plugin_crash_no_partial_state_persists_nothing(self, tmp_path) -> None:
        """When a plugin crashes BEFORE any mutation (partial_state is None),
        no new ``composition_states`` row is written. The 500 response shape
        is identical to the persisted-partial case.
        """
        import asyncio

        original = ValueError("plugin bug on first call")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=None),
        )

        app, service = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Build me a pipeline"},
        )
        assert response.status_code == 500

        loop = asyncio.new_event_loop()
        try:
            persisted = loop.run_until_complete(service.get_current_state(uuid.UUID(session_id)))
        finally:
            loop.close()
        # A brand-new session with no successful mutations → no composition
        # state row should have been created by the crash path.
        assert persisted is None

    def test_compose_plugin_crash_log_has_no_traceback_fields(self, tmp_path) -> None:
        """P2 regression fix: the plugin-crash structured log MUST NOT
        carry traceback-shaped fields. ``exc_info=True`` was dropped
        because plugin exception ``__cause__`` chains may include DB
        URLs, filesystem paths, or secret fragments.
        """
        from structlog.testing import capture_logs

        original = ValueError(f"plugin bug with secret {self.SECRET_PATH}")
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=None),
        )

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        with capture_logs() as cap_logs:
            response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"content": "Build me a pipeline"},
            )
        assert response.status_code == 500

        crash_events = [e for e in cap_logs if e.get("event") == "compose_plugin_crash"]
        assert len(crash_events) == 1, cap_logs
        event = crash_events[0]
        # Triage fields present.
        assert event["exc_class"] == "ValueError"
        assert event["session_id"] == session_id
        # Traceback-shaped fields absent.
        assert "exc_info" not in event
        assert "exception" not in event
        assert "stack_info" not in event
        # Exception message / secret fragments MUST NOT appear anywhere
        # in the structured event (defense-in-depth).
        serialised = str(event)
        assert self.SECRET_PATH not in serialised
        assert "plugin bug" not in serialised

    def test_compose_plugin_crash_sentinel_leak(self, tmp_path) -> None:
        """Multi-sentinel test: inject an exception whose ``__str__`` and
        whose ``__cause__.__str__`` each carry a distinct secret sentinel.
        Neither must appear in the HTTP response body nor in any captured
        log record. This guards against future regressions where a
        structlog processor or log field addition inadvertently serialises
        exception content.
        """
        from structlog.testing import capture_logs

        message_secret = "postgres://user:p4ss@prod-db.internal:5432/audit"
        cause_secret = "/var/secrets/elspeth/bootstrap-key.pem"

        original = RuntimeError(f"upstream failure: {message_secret}")
        original.__cause__ = FileNotFoundError(cause_secret)

        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=ComposerPluginCrashError(original, partial_state=None),
        )

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        with capture_logs() as cap_logs:
            response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={"content": "Build me a pipeline"},
            )
        assert response.status_code == 500

        # Neither sentinel in response body.
        assert message_secret not in response.text
        assert cause_secret not in response.text

        # Neither sentinel in any captured log record.
        for event in cap_logs:
            serialised = str(event)
            assert message_secret not in serialised, event
            assert cause_secret not in serialised, event

    def test_compose_unknown_exception_class_is_not_absorbed(self, tmp_path) -> None:
        """Deliberately narrow typed catch: RuntimeError (not in the handler's
        catch list) must propagate past the composer_plugin_error handler.
        With raise_server_exceptions=False, TestClient returns FastAPI's
        default 500 response; the critical invariant is that the structured
        composer_plugin_error body is NOT produced for unknown classes.
        """
        mock_composer = AsyncMock()
        mock_composer.compose = AsyncMock(
            side_effect=RuntimeError("unknown failure class"),
        )

        app, _ = _make_app(tmp_path)
        app.state.composer_service = mock_composer
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/sessions", json={"title": "Test"})
        session_id = resp.json()["id"]

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"content": "Build me a pipeline"},
        )

        assert response.status_code == 500
        # Unconditional: the composer_plugin_error marker MUST NOT appear
        # anywhere in the response body, regardless of whether FastAPI
        # renders detail as a dict or a string.  This closes the vacuous-
        # pass risk of an `if isinstance(...)` guard.
        assert "composer_plugin_error" not in response.text
