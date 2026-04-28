"""Tests for shared path resolution helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from elspeth.web.paths import resolve_data_path


class TestResolveDataPath:
    """Unit tests for resolve_data_path — the single resolution function
    used by both validation and execution service."""

    def test_relative_path_resolved_against_data_dir(self) -> None:
        """A relative path is joined to data_dir before resolving."""
        result = resolve_data_path("blobs/data.csv", "/tmp/data")
        assert result == Path("/tmp/data/blobs/data.csv")

    def test_data_dir_prefixed_relative_path_is_not_double_prefixed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Legacy blob storage paths may already include the relative data_dir."""
        monkeypatch.chdir(tmp_path)

        result = resolve_data_path("data/blobs/session/input.csv", "data")

        assert result == tmp_path / "data" / "blobs" / "session" / "input.csv"

    def test_absolute_path_unchanged(self) -> None:
        """An absolute path resolves to itself (no data_dir involvement)."""
        result = resolve_data_path("/etc/passwd", "/tmp/data")
        assert result == Path("/etc/passwd")

    def test_traversal_resolved(self) -> None:
        """Traversal (../) is resolved by the OS — blocking is the allowlist's job."""
        result = resolve_data_path("../etc/passwd", "/tmp/data")
        assert result == Path("/tmp/etc/passwd")
