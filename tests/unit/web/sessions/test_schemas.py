"""Edge-case validation tests for session API schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from elspeth.web.sessions.schemas import (
    CreateSessionRequest,
    ForkSessionRequest,
    RevertStateRequest,
    RunResponse,
    SendMessageRequest,
)


class TestCreateSessionRequest:
    def test_default_title(self) -> None:
        req = CreateSessionRequest()
        assert req.title == "New session"

    def test_custom_title(self) -> None:
        req = CreateSessionRequest(title="My pipeline")
        assert req.title == "My pipeline"


class TestSendMessageRequest:
    def test_rejects_empty_content(self) -> None:
        with pytest.raises(ValidationError, match="content"):
            SendMessageRequest(content="")

    def test_accepts_nonempty_content(self) -> None:
        req = SendMessageRequest(content="hello")
        assert req.content == "hello"


class TestForkSessionRequest:
    def test_rejects_invalid_uuid(self) -> None:
        with pytest.raises(ValidationError):
            ForkSessionRequest(from_message_id="not-a-uuid", new_message_content="fork")

    def test_accepts_valid_uuid(self) -> None:
        import uuid

        req = ForkSessionRequest(from_message_id=uuid.uuid4(), new_message_content="fork")
        assert req.new_message_content == "fork"


class TestRevertStateRequest:
    def test_rejects_invalid_uuid(self) -> None:
        with pytest.raises(ValidationError):
            RevertStateRequest(state_id="not-a-uuid")


class TestRunResponse:
    def test_rejects_invalid_status(self) -> None:
        from datetime import UTC, datetime

        with pytest.raises(ValidationError, match="status"):
            RunResponse(
                id="run-1",
                session_id="sess-1",
                status="invalid_status",
                rows_processed=0,
                rows_failed=0,
                started_at=datetime.now(UTC),
                composition_version=1,
            )

    def test_accepts_valid_status(self) -> None:
        from datetime import UTC, datetime

        resp = RunResponse(
            id="run-1",
            session_id="sess-1",
            status="completed",
            rows_processed=10,
            rows_failed=0,
            started_at=datetime.now(UTC),
            composition_version=1,
        )
        assert resp.status == "completed"
