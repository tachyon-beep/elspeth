"""Tests for session record dataclasses and protocol definition."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from elspeth.web.sessions.protocol import (
    ChatMessageRecord,
    CompositionStateData,
    CompositionStateRecord,
    RunAlreadyActiveError,
    RunRecord,
    SessionRecord,
    SessionServiceProtocol,
)


class TestSessionRecord:
    def test_frozen_immutability(self) -> None:
        record = SessionRecord(
            id=uuid4(),
            user_id="alice",
            auth_provider_type="local",
            title="Test",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            record.title = "Changed"  # type: ignore[misc]


class TestChatMessageRecord:
    def test_tool_calls_frozen_when_present(self) -> None:
        record = ChatMessageRecord(
            id=uuid4(),
            session_id=uuid4(),
            role="assistant",
            content="Hello",
            tool_calls={"name": "search", "args": {"q": "test"}},
            created_at=datetime.now(UTC),
        )
        with pytest.raises(TypeError):
            record.tool_calls["new_key"] = "value"  # type: ignore[index]

    def test_tool_calls_none_is_fine(self) -> None:
        record = ChatMessageRecord(
            id=uuid4(),
            session_id=uuid4(),
            role="user",
            content="Hello",
            tool_calls=None,
            created_at=datetime.now(UTC),
        )
        assert record.tool_calls is None


class TestCompositionStateData:
    def test_mutable_inputs_are_frozen(self) -> None:
        source = {"type": "csv", "path": "/data/test.csv"}
        nodes = [{"id": "n1", "type": "source"}]
        data = CompositionStateData(
            source=source,
            nodes=nodes,
            is_valid=True,
        )
        # Original dicts should not affect the frozen copy
        source["type"] = "json"
        assert data.source["type"] == "csv"  # type: ignore[index]
        # Frozen containers should reject mutation
        with pytest.raises(TypeError):
            data.source["new_key"] = "value"  # type: ignore[index]
        with pytest.raises((TypeError, AttributeError)):
            data.nodes.append({"id": "n2"})  # type: ignore[union-attr]

    def test_none_fields_not_frozen(self) -> None:
        data = CompositionStateData(is_valid=False)
        assert data.source is None
        assert data.nodes is None

    def test_frozen_immutability(self) -> None:
        data = CompositionStateData(is_valid=True)
        with pytest.raises(AttributeError):
            data.is_valid = False  # type: ignore[misc]


class TestCompositionStateRecord:
    def test_mutable_fields_are_frozen(self) -> None:
        record = CompositionStateRecord(
            id=uuid4(),
            session_id=uuid4(),
            version=1,
            source={"type": "csv"},
            nodes=[{"id": "n1"}],
            edges=None,
            outputs=None,
            metadata_=None,
            is_valid=True,
            validation_errors=None,
            created_at=datetime.now(UTC),
            derived_from_state_id=None,
        )
        with pytest.raises(TypeError):
            record.source["new"] = "value"  # type: ignore[index]


class TestRunRecord:
    def test_frozen_immutability(self) -> None:
        record = RunRecord(
            id=uuid4(),
            session_id=uuid4(),
            state_id=uuid4(),
            status="running",
            started_at=datetime.now(UTC),
            finished_at=None,
            rows_processed=0,
            rows_failed=0,
            error=None,
            landscape_run_id=None,
            pipeline_yaml=None,
        )
        with pytest.raises(AttributeError):
            record.status = "completed"  # type: ignore[misc]


class TestRunAlreadyActiveError:
    def test_construction_and_message(self) -> None:
        err = RunAlreadyActiveError("session-123")
        assert err.session_id == "session-123"
        assert "session-123" in str(err)
        assert isinstance(err, Exception)


class TestSessionServiceProtocol:
    def test_is_runtime_checkable(self) -> None:
        # Verify @runtime_checkable works by checking a non-conforming object fails
        assert not isinstance(object(), SessionServiceProtocol)
