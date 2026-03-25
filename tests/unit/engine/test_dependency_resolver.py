"""Tests for pipeline dependency resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from elspeth.contracts.errors import DependencyFailedError
from elspeth.core.dependency_config import DependencyConfig
from elspeth.engine.dependency_resolver import detect_cycles, resolve_dependencies


class TestCycleDetection:
    def test_no_cycle_returns_none(self, tmp_path: Path) -> None:
        # A -> B, no cycle
        b = tmp_path / "b.yaml"
        b.write_text("source:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\nlandscape:\n  url: sqlite:///test.db\n")
        a = tmp_path / "a.yaml"
        a.write_text(
            f"depends_on:\n  - name: b\n    settings: {b}\nsource:\n  plugin: null_source\n"
            "sinks:\n  out:\n    plugin: json_sink\nlandscape:\n  url: sqlite:///test.db\n"
        )

        # Should not raise
        detect_cycles(a)

    def test_self_loop_detected(self, tmp_path: Path) -> None:
        a = tmp_path / "a.yaml"
        a.write_text(
            f"depends_on:\n  - name: self\n    settings: {a}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )

        with pytest.raises(ValueError, match=r"[Cc]ircular|[Cc]ycle"):
            detect_cycles(a)

    def test_two_hop_cycle_detected(self, tmp_path: Path) -> None:
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(
            f"depends_on:\n  - name: b\n    settings: {b}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )
        b.write_text(
            f"depends_on:\n  - name: a\n    settings: {a}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )

        with pytest.raises(ValueError, match=r"[Cc]ircular|[Cc]ycle"):
            detect_cycles(a)

    def test_three_hop_cycle_detected(self, tmp_path: Path) -> None:
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        c = tmp_path / "c.yaml"
        a.write_text(
            f"depends_on:\n  - name: b\n    settings: {b}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )
        b.write_text(
            f"depends_on:\n  - name: c\n    settings: {c}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )
        c.write_text(
            f"depends_on:\n  - name: a\n    settings: {a}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )

        with pytest.raises(ValueError, match=r"[Cc]ircular|[Cc]ycle"):
            detect_cycles(a)

    def test_depth_limit_exceeded(self, tmp_path: Path) -> None:
        # Create a chain: a -> b -> c -> d (depth 4, exceeds limit of 3)
        files: dict[str, Path] = {}
        for name in ["d", "c", "b", "a"]:
            files[name] = tmp_path / f"{name}.yaml"

        files["d"].write_text("source:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n")
        files["c"].write_text(
            f"depends_on:\n  - name: d\n    settings: {files['d']}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )
        files["b"].write_text(
            f"depends_on:\n  - name: c\n    settings: {files['c']}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )
        files["a"].write_text(
            f"depends_on:\n  - name: b\n    settings: {files['b']}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )

        with pytest.raises(ValueError, match=r"[Dd]epth"):
            detect_cycles(files["a"], max_depth=3)

    def test_uses_resolved_paths(self, tmp_path: Path) -> None:
        """Symlinks resolve to the same canonical path."""
        real = tmp_path / "real.yaml"
        real.write_text("source:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n")
        link = tmp_path / "link.yaml"
        link.symlink_to(real)

        main = tmp_path / "main.yaml"
        main.write_text(
            f"depends_on:\n  - name: dep\n    settings: {link}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )

        # Should not raise — link resolves to real, no cycle
        detect_cycles(main)

    def test_diamond_dependency_no_cycle(self, tmp_path: Path) -> None:
        """Diamond shape: A -> B, A -> C, B -> D, C -> D. No cycle."""
        d = tmp_path / "d.yaml"
        d.write_text("source:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n")

        b = tmp_path / "b.yaml"
        b.write_text(
            f"depends_on:\n  - name: d\n    settings: {d}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )

        c = tmp_path / "c.yaml"
        c.write_text(
            f"depends_on:\n  - name: d\n    settings: {d}\nsource:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )

        a = tmp_path / "a.yaml"
        a.write_text(
            f"depends_on:\n  - name: b\n    settings: {b}\n  - name: c\n    settings: {c}\n"
            "source:\n  plugin: null_source\nsinks:\n  out:\n    plugin: json_sink\n"
        )

        # Should not raise — diamond is not a cycle
        detect_cycles(a)


class TestResolveDependencies:
    def test_single_dependency_success(self, tmp_path: Path) -> None:
        dep = DependencyConfig(name="index", settings="./index.yaml")
        parent_path = tmp_path / "query.yaml"

        mock_result = MagicMock()
        mock_result.status.name = "COMPLETED"
        mock_result.run_id = "dep-run-123"

        with (
            patch("elspeth.engine.dependency_resolver.bootstrap_and_run") as mock_boot,
            patch("elspeth.engine.dependency_resolver._hash_settings_file", return_value="sha256:abc"),
        ):
            mock_boot.return_value = mock_result
            results = resolve_dependencies(
                depends_on=[dep],
                parent_settings_path=parent_path,
            )

        assert len(results) == 1
        assert results[0].name == "index"
        assert results[0].run_id == "dep-run-123"

    def test_dependency_failure_raises(self, tmp_path: Path) -> None:
        dep = DependencyConfig(name="index", settings="./index.yaml")
        parent_path = tmp_path / "query.yaml"

        mock_result = MagicMock()
        mock_result.status.name = "FAILED"
        mock_result.run_id = "dep-run-fail"

        with patch("elspeth.engine.dependency_resolver.bootstrap_and_run") as mock_boot:
            mock_boot.return_value = mock_result
            with pytest.raises(DependencyFailedError, match="index"):
                resolve_dependencies(
                    depends_on=[dep],
                    parent_settings_path=parent_path,
                )

    def test_keyboard_interrupt_propagated(self, tmp_path: Path) -> None:
        dep = DependencyConfig(name="index", settings="./index.yaml")
        parent_path = tmp_path / "query.yaml"

        with patch("elspeth.engine.dependency_resolver.bootstrap_and_run") as mock_boot:
            mock_boot.side_effect = KeyboardInterrupt()
            with pytest.raises(KeyboardInterrupt):
                resolve_dependencies(
                    depends_on=[dep],
                    parent_settings_path=parent_path,
                )

    def test_multiple_dependencies_sequential(self, tmp_path: Path) -> None:
        deps = [
            DependencyConfig(name="first", settings="./first.yaml"),
            DependencyConfig(name="second", settings="./second.yaml"),
        ]
        parent_path = tmp_path / "main.yaml"
        call_order: list[str] = []

        def track_calls(path: Path) -> MagicMock:
            call_order.append(path.name)
            result = MagicMock()
            result.status.name = "COMPLETED"
            result.run_id = f"run-{path.name}"
            return result

        with (
            patch("elspeth.engine.dependency_resolver.bootstrap_and_run") as mock_boot,
            patch("elspeth.engine.dependency_resolver._hash_settings_file", return_value="sha256:abc"),
        ):
            mock_boot.side_effect = track_calls
            resolve_dependencies(depends_on=deps, parent_settings_path=parent_path)

        assert call_order == ["first.yaml", "second.yaml"]

    def test_empty_depends_on_returns_empty(self, tmp_path: Path) -> None:
        parent_path = tmp_path / "main.yaml"
        results = resolve_dependencies(depends_on=[], parent_settings_path=parent_path)
        assert results == []
