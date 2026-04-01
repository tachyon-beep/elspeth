"""Tests for composer MCP session persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from elspeth.composer_mcp.session import (
    SessionManager,
    SessionNotFoundError,
)
from elspeth.web.composer.state import SourceSpec


class TestSessionManager:
    @pytest.fixture()
    def scratch_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "scratch"

    @pytest.fixture()
    def manager(self, scratch_dir: Path) -> SessionManager:
        return SessionManager(scratch_dir)

    def test_new_session_returns_empty_state(self, manager: SessionManager) -> None:
        session_id, state = manager.new_session()
        assert session_id
        assert state.source is None
        assert state.nodes == ()
        assert state.edges == ()
        assert state.outputs == ()
        assert state.version == 1

    def test_new_session_with_name(self, manager: SessionManager) -> None:
        _session_id, state = manager.new_session(name="my-pipeline")
        assert state.metadata.name == "my-pipeline"

    def test_save_and_load_round_trip(self, manager: SessionManager) -> None:
        session_id, state = manager.new_session()
        source = SourceSpec(
            plugin="csv",
            on_success="source_out",
            options={"path": "data/input.csv"},
            on_validation_failure="discard",
        )
        state = state.with_source(source)
        manager.save(session_id, state)
        loaded = manager.load(session_id)
        assert loaded.source is not None
        assert loaded.source.plugin == "csv"
        assert loaded.source.on_success == "source_out"
        assert loaded.version == state.version

    def test_load_nonexistent_raises(self, manager: SessionManager) -> None:
        with pytest.raises(SessionNotFoundError, match="no-such-id"):
            manager.load("no-such-id")

    def test_list_sessions_empty(self, manager: SessionManager) -> None:
        assert manager.list_sessions() == []

    def test_list_sessions_after_save(self, manager: SessionManager) -> None:
        sid1, s1 = manager.new_session(name="first")
        manager.save(sid1, s1)
        sid2, s2 = manager.new_session(name="second")
        manager.save(sid2, s2)
        sessions = manager.list_sessions()
        assert len(sessions) == 2
        names = {s["name"] for s in sessions}
        assert names == {"first", "second"}

    def test_save_creates_scratch_dir(self, tmp_path: Path) -> None:
        scratch = tmp_path / "nonexistent" / "scratch"
        manager = SessionManager(scratch)
        sid, state = manager.new_session()
        manager.save(sid, state)
        assert scratch.exists()

    def test_delete_session(self, manager: SessionManager) -> None:
        sid, state = manager.new_session()
        manager.save(sid, state)
        manager.delete(sid)
        with pytest.raises(SessionNotFoundError):
            manager.load(sid)

    def test_saved_file_is_valid_json(self, manager: SessionManager, scratch_dir: Path) -> None:
        sid, state = manager.new_session(name="json-check")
        manager.save(sid, state)
        files = list(scratch_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["metadata"]["name"] == "json-check"
