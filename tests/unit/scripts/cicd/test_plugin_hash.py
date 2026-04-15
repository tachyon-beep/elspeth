"""Tests for plugin_hash.py — shared hash computation for plugin source files.

Tests cover:
1. Hash computation with self-referential normalization
2. AST extraction of plugin class attributes
3. In-place hash line rewriting

Uses tmp_path fixtures for file-based operations.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from scripts.cicd.plugin_hash import (
    compute_source_file_hash,
    extract_plugin_attributes,
    fix_source_file_hash,
)

# =============================================================================
# Helper: write a plugin file
# =============================================================================


def _write_plugin(tmp_path: Path, source: str, filename: str = "plugin.py") -> Path:
    """Write dedented source to a temp file and return the path."""
    file_path = tmp_path / filename
    file_path.write_text(textwrap.dedent(source), encoding="utf-8")
    return file_path


# =============================================================================
# compute_source_file_hash
# =============================================================================


class TestComputeHash:
    """Tests for compute_source_file_hash."""

    def test_compute_hash_excludes_own_value(self, tmp_path: Path) -> None:
        """Same hash regardless of declared source_file_hash value.

        The self-referential normalization must ensure the hash doesn't
        change when only the hash value itself differs.
        """
        source_a = """\
            class MyPlugin:
                name = "my-plugin"
                plugin_version = "1.0.0"
                source_file_hash = "sha256:aaaaaaaaaaaaaaaa"
        """
        source_b = """\
            class MyPlugin:
                name = "my-plugin"
                plugin_version = "1.0.0"
                source_file_hash = "sha256:bbbbbbbbbbbbbbbb"
        """
        file_a = _write_plugin(tmp_path, source_a, "plugin_a.py")
        file_b = _write_plugin(tmp_path, source_b, "plugin_b.py")

        hash_a = compute_source_file_hash(file_a)
        hash_b = compute_source_file_hash(file_b)

        assert hash_a == hash_b
        assert hash_a.startswith("sha256:")
        assert len(hash_a) == len("sha256:") + 16  # sha256: + 16 hex chars

    def test_compute_hash_changes_on_content_change(self, tmp_path: Path) -> None:
        """Different hash when actual content (not just hash value) changes."""
        source_a = """\
            class MyPlugin:
                name = "my-plugin"
                plugin_version = "1.0.0"
                source_file_hash = "sha256:aaaaaaaaaaaaaaaa"

                def process(self):
                    return "version_a"
        """
        source_b = """\
            class MyPlugin:
                name = "my-plugin"
                plugin_version = "1.0.0"
                source_file_hash = "sha256:aaaaaaaaaaaaaaaa"

                def process(self):
                    return "version_b"
        """
        file_a = _write_plugin(tmp_path, source_a, "plugin_a.py")
        file_b = _write_plugin(tmp_path, source_b, "plugin_b.py")

        hash_a = compute_source_file_hash(file_a)
        hash_b = compute_source_file_hash(file_b)

        assert hash_a != hash_b

    def test_compute_hash_uses_raw_bytes(self, tmp_path: Path) -> None:
        """Non-ASCII content works — hashing uses raw bytes, not decoded text."""
        source = """\
            class MyPlugin:
                name = "my-plugin"
                plugin_version = "1.0.0"
                description = "Ünïcödé — «fancy» plugin™"
        """
        file_path = _write_plugin(tmp_path, source)
        result = compute_source_file_hash(file_path)

        assert result.startswith("sha256:")
        assert len(result) == len("sha256:") + 16

    def test_compute_hash_file_without_hash_line(self, tmp_path: Path) -> None:
        """File with no source_file_hash line still hashes correctly."""
        source = """\
            class MyPlugin:
                name = "my-plugin"
                plugin_version = "1.0.0"

                def process(self):
                    pass
        """
        file_path = _write_plugin(tmp_path, source)
        result = compute_source_file_hash(file_path)

        assert result.startswith("sha256:")
        assert len(result) == len("sha256:") + 16


# =============================================================================
# extract_plugin_attributes
# =============================================================================


class TestExtractPluginAttributes:
    """Tests for extract_plugin_attributes."""

    def test_extract_class_attribute_simple(self, tmp_path: Path) -> None:
        """Basic extraction of name, plugin_version, source_file_hash."""
        source = """\
            class MyPlugin:
                name = "my-plugin"
                plugin_version = "1.0.0"
                source_file_hash = "sha256:abcdef0123456789"
        """
        file_path = _write_plugin(tmp_path, source)
        results = extract_plugin_attributes(file_path)

        assert len(results) == 1
        attrs = results[0]
        assert attrs.class_name == "MyPlugin"
        assert attrs.plugin_version == "1.0.0"
        assert attrs.source_file_hash == "sha256:abcdef0123456789"
        assert attrs.hash_line_number is not None
        assert attrs.hash_line_number > 0

    def test_extract_class_attribute_annotated(self, tmp_path: Path) -> None:
        """Annotated assignment form: source_file_hash: str = "sha256:..."."""
        source = """\
            class MyPlugin:
                name = "my-plugin"
                plugin_version: str = "2.0.0"
                source_file_hash: str = "sha256:1111222233334444"
        """
        file_path = _write_plugin(tmp_path, source)
        results = extract_plugin_attributes(file_path)

        assert len(results) == 1
        attrs = results[0]
        assert attrs.class_name == "MyPlugin"
        assert attrs.plugin_version == "2.0.0"
        assert attrs.source_file_hash == "sha256:1111222233334444"

    def test_extract_class_attribute_none_default(self, tmp_path: Path) -> None:
        """source_file_hash = None is detected (value is None)."""
        source = """\
            class MyPlugin:
                name = "my-plugin"
                plugin_version = "1.0.0"
                source_file_hash = None
        """
        file_path = _write_plugin(tmp_path, source)
        results = extract_plugin_attributes(file_path)

        assert len(results) == 1
        attrs = results[0]
        assert attrs.class_name == "MyPlugin"
        assert attrs.source_file_hash is None

    def test_extract_ignores_non_plugin_classes(self, tmp_path: Path) -> None:
        """Classes without a `name` class attribute are not plugin classes."""
        source = """\
            class NotAPlugin:
                plugin_version = "1.0.0"
                source_file_hash = "sha256:abcdef0123456789"

            class AlsoNotAPlugin:
                def name(self):
                    return "method, not attribute"

            class IsAPlugin:
                name = "real-plugin"
                plugin_version = "1.0.0"
                source_file_hash = "sha256:abcdef0123456789"
        """
        file_path = _write_plugin(tmp_path, source)
        results = extract_plugin_attributes(file_path)

        assert len(results) == 1
        assert results[0].class_name == "IsAPlugin"


# =============================================================================
# fix_source_file_hash
# =============================================================================


class TestFixSourceFileHash:
    """Tests for fix_source_file_hash."""

    def test_fix_updates_hash_in_place(self, tmp_path: Path) -> None:
        """fix_source_file_hash rewrites the hash line with correct value."""
        source = """\
            class MyPlugin:
                name = "my-plugin"
                plugin_version = "1.0.0"
                source_file_hash = "sha256:0000000000000000"

                def process(self):
                    return 42
        """
        file_path = _write_plugin(tmp_path, source)
        new_hash = "sha256:abcdef0123456789"

        fix_source_file_hash(file_path, "MyPlugin", new_hash)

        content = file_path.read_text(encoding="utf-8")
        assert new_hash in content
        # The stale placeholder should be gone
        assert "sha256:0000000000000000" not in content
        # Rest of the file is preserved
        assert 'name = "my-plugin"' in content
        assert "def process(self):" in content
        assert "return 42" in content

    def test_fix_is_idempotent(self, tmp_path: Path) -> None:
        """Fixing twice with the same hash produces the same result."""
        source = """\
            class MyPlugin:
                name = "my-plugin"
                plugin_version = "1.0.0"
                source_file_hash = "sha256:0000000000000000"
        """
        file_path = _write_plugin(tmp_path, source)
        new_hash = "sha256:abcdef0123456789"

        fix_source_file_hash(file_path, "MyPlugin", new_hash)
        content_after_first = file_path.read_text(encoding="utf-8")

        fix_source_file_hash(file_path, "MyPlugin", new_hash)
        content_after_second = file_path.read_text(encoding="utf-8")

        assert content_after_first == content_after_second
