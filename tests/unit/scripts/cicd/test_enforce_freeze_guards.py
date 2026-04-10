"""Tests for enforce_freeze_guards.py CI scanner.

Tests the FreezeGuardVisitor AST analysis, allowlist matching, and scan
integration. Uses inline source strings via textwrap.dedent for hermetic
tests — no filesystem fixtures needed for visitor tests.

Follows the pattern established by test_enforce_frozen_annotations.py.
"""

from __future__ import annotations

import ast
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from scripts.cicd.enforce_freeze_guards import (
    Allowlist,
    Finding,
    FreezeGuardVisitor,
    PerFileRule,
    load_allowlist,
    scan_file,
)


def _scan(source: str, file_path: str = "test.py") -> list[Finding]:
    """Run the freeze guard visitor on a source string and return findings."""
    source = textwrap.dedent(source)
    tree = ast.parse(source)
    source_lines = source.splitlines()
    visitor = FreezeGuardVisitor(file_path, source_lines)
    visitor.visit(tree)
    return visitor.findings


# =============================================================================
# FG1: Bare MappingProxyType detection
# =============================================================================


class TestFG1Detection:
    """FG1 detects bare MappingProxyType wraps in __post_init__."""

    def test_name_form_detected(self) -> None:
        """MappingProxyType(dict(self.x)) using Name import form."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    object.__setattr__(self, "x", MappingProxyType(dict(self.x)))
        """)
        assert len(findings) == 1
        assert findings[0].rule_id == "FG1"
        assert findings[0].symbol_context == ("Foo", "__post_init__")

    def test_attribute_form_detected(self) -> None:
        """types.MappingProxyType(...) using Attribute access form."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    object.__setattr__(self, "x", types.MappingProxyType(dict(self.x)))
        """)
        assert len(findings) == 1
        assert findings[0].rule_id == "FG1"

    def test_not_flagged_outside_post_init(self) -> None:
        """MappingProxyType in other methods is not flagged."""
        findings = _scan("""
            class Foo:
                def some_method(self):
                    return MappingProxyType(dict(self.x))
        """)
        assert len(findings) == 0

    def test_multiple_wraps_detected(self) -> None:
        """Multiple MappingProxyType calls each produce a finding."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    object.__setattr__(self, "a", MappingProxyType(dict(self.a)))
                    object.__setattr__(self, "b", MappingProxyType(dict(self.b)))
        """)
        assert len(findings) == 2
        assert all(f.rule_id == "FG1" for f in findings)


# =============================================================================
# FG2: isinstance freeze guard detection
# =============================================================================


class TestFG2Detection:
    """FG2 detects isinstance type guards in __post_init__."""

    def test_single_type_detected(self) -> None:
        """isinstance(self.x, dict) with single freeze-guard type."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    if isinstance(self.data, dict):
                        pass
        """)
        assert len(findings) == 1
        assert findings[0].rule_id == "FG2"
        assert "dict" in findings[0].message

    def test_tuple_of_types_detected(self) -> None:
        """isinstance(self.x, (dict, tuple)) with multiple freeze-guard types."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    if isinstance(self.data, (dict, tuple)):
                        pass
        """)
        assert len(findings) == 1
        assert findings[0].rule_id == "FG2"
        assert "dict" in findings[0].message
        assert "tuple" in findings[0].message

    def test_non_self_attribute_not_flagged(self) -> None:
        """isinstance(other_var, dict) without self.x is not flagged."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    if isinstance(other_var, dict):
                        pass
        """)
        assert len(findings) == 0

    def test_non_freeze_type_not_flagged(self) -> None:
        """isinstance(self.x, str) with non-freeze-guard type is not flagged."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    if isinstance(self.name, str):
                        pass
        """)
        assert len(findings) == 0

    def test_not_flagged_outside_post_init(self) -> None:
        """isinstance in other methods is not flagged."""
        findings = _scan("""
            class Foo:
                def validate(self):
                    if isinstance(self.data, dict):
                        pass
        """)
        assert len(findings) == 0


# =============================================================================
# Scope handling
# =============================================================================


class TestScopeHandling:
    """Scope tracking for __post_init__ detection."""

    def test_nested_function_not_flagged(self) -> None:
        """Nested def inside __post_init__ exits the detection scope."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    def helper():
                        MappingProxyType(x)
                    helper()
        """)
        assert len(findings) == 0

    def test_module_level_post_init_not_flagged(self) -> None:
        """Module-level function named __post_init__ is not a dataclass method."""
        findings = _scan("""
            def __post_init__(self):
                MappingProxyType(dict(self.x))
        """)
        assert len(findings) == 0

    def test_nested_class_own_post_init_flagged(self) -> None:
        """Nested class with its own __post_init__ is flagged independently."""
        findings = _scan("""
            class Outer:
                def __post_init__(self):
                    pass

                class Inner:
                    def __post_init__(self):
                        MappingProxyType(dict(self.x))
        """)
        assert len(findings) == 1
        assert "Inner" in findings[0].symbol_context

    def test_sibling_method_not_flagged(self) -> None:
        """Other methods in the same class are not in __post_init__ scope."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    pass

                def other_method(self):
                    MappingProxyType(dict(self.x))
        """)
        assert len(findings) == 0

    def test_direct_post_init_body_flagged(self) -> None:
        """Code directly in __post_init__ body is flagged (not just nested)."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    MappingProxyType(dict(self.x))
                    if isinstance(self.y, dict):
                        pass
        """)
        assert len(findings) == 2
        assert {f.rule_id for f in findings} == {"FG1", "FG2"}

    def test_nested_class_does_not_inherit_outer_scope(self) -> None:
        """Class defined inside __post_init__ does not inherit detection scope."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    class Helper:
                        x = MappingProxyType({})
        """)
        assert len(findings) == 0


# =============================================================================
# Allowlist
# =============================================================================


class TestAllowlist:
    """Allowlist matching, staleness, and loading."""

    def test_suppresses_finding(self) -> None:
        """Allowlisted finding is not reported as a violation."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    MappingProxyType(dict(self.x))
        """)
        assert len(findings) == 1

        allowlist = Allowlist(
            per_file_rules=[
                PerFileRule(
                    pattern="test.py",
                    rules=["FG1"],
                    reason="test",
                    expires=None,
                ),
            ]
        )
        match = allowlist.match(findings[0])
        assert match is not None

    def test_non_matching_pattern_not_suppressed(self) -> None:
        """Finding with non-matching pattern is not suppressed."""
        findings = _scan("""
            class Foo:
                def __post_init__(self):
                    MappingProxyType(dict(self.x))
        """)
        allowlist = Allowlist(
            per_file_rules=[
                PerFileRule(
                    pattern="other.py",
                    rules=["FG1"],
                    reason="test",
                    expires=None,
                ),
            ]
        )
        match = allowlist.match(findings[0])
        assert match is None

    def test_max_hits_exceeded_reported(self) -> None:
        """Rules with matched_count > max_hits are reported as exceeded."""
        rule = PerFileRule(
            pattern="test.py",
            rules=["FG1"],
            reason="test",
            expires=None,
            max_hits=1,
        )
        rule.matched_count = 2
        allowlist = Allowlist(per_file_rules=[rule])
        exceeded = allowlist.get_exceeded_rules()
        assert len(exceeded) == 1

    def test_unused_rule_reported(self) -> None:
        """Rules with zero matches are reported as unused."""
        rule = PerFileRule(
            pattern="nonexistent.py",
            rules=["FG1"],
            reason="test",
            expires=None,
        )
        allowlist = Allowlist(per_file_rules=[rule])
        unused = allowlist.get_unused_rules()
        assert len(unused) == 1

    def test_expired_rule_reported(self) -> None:
        """Rules past their expiry date are reported."""
        yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
        rule = PerFileRule(
            pattern="test.py",
            rules=["FG1"],
            reason="test",
            expires=yesterday,
        )
        allowlist = Allowlist(per_file_rules=[rule])
        expired = allowlist.get_expired_rules()
        assert len(expired) == 1

    def test_non_expired_rule_not_reported(self) -> None:
        """Rules before their expiry date are not reported."""
        tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()
        rule = PerFileRule(
            pattern="test.py",
            rules=["FG1"],
            reason="test",
            expires=tomorrow,
        )
        allowlist = Allowlist(per_file_rules=[rule])
        expired = allowlist.get_expired_rules()
        assert len(expired) == 0

    def test_directory_loading(self, tmp_path: Path) -> None:
        """load_allowlist reads a directory of YAML files with _defaults.yaml."""
        defaults = tmp_path / "_defaults.yaml"
        defaults.write_text("defaults:\n  fail_on_stale: false\n")

        rules_file = tmp_path / "test_rules.yaml"
        rules_file.write_text(
            yaml.dump(
                {
                    "per_file_rules": [
                        {
                            "pattern": "foo.py",
                            "rules": ["FG1"],
                            "reason": "test",
                        }
                    ]
                }
            )
        )

        allowlist = load_allowlist(tmp_path)
        assert allowlist.fail_on_stale is False
        assert len(allowlist.per_file_rules) == 1
        assert allowlist.per_file_rules[0].pattern == "foo.py"

    def test_unknown_rule_id_exits(self, tmp_path: Path) -> None:
        """Unknown rule IDs in allowlist cause sys.exit(1)."""
        rules_file = tmp_path / "bad.yaml"
        rules_file.write_text(
            yaml.dump(
                {
                    "per_file_rules": [
                        {
                            "pattern": "foo.py",
                            "rules": ["NONEXISTENT"],
                            "reason": "bad",
                        }
                    ]
                }
            )
        )

        with pytest.raises(SystemExit) as exc_info:
            load_allowlist(tmp_path)
        assert exc_info.value.code == 1


# =============================================================================
# File scanning
# =============================================================================


class TestScanFile:
    """Integration tests for scan_file."""

    def test_syntax_error_returns_empty(self, tmp_path: Path) -> None:
        """Files with syntax errors return empty findings, not crash."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def foo(:\n    pass\n")
        findings = scan_file(bad_file, tmp_path)
        assert findings == []

    def test_encoding_error_returns_empty(self, tmp_path: Path) -> None:
        """Files with encoding errors return empty findings, not crash."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")
        findings = scan_file(bad_file, tmp_path)
        assert findings == []

    def test_clean_file_returns_empty(self, tmp_path: Path) -> None:
        """Files with no violations return empty findings."""
        good_file = tmp_path / "good.py"
        good_file.write_text(
            textwrap.dedent("""
            from dataclasses import dataclass
            from elspeth.contracts.freeze import freeze_fields

            @dataclass(frozen=True)
            class Record:
                data: dict

                def __post_init__(self):
                    freeze_fields(self, "data")
        """)
        )
        findings = scan_file(good_file, tmp_path)
        assert findings == []

    def test_violation_detected_in_file(self, tmp_path: Path) -> None:
        """scan_file detects violations and returns correct file paths."""
        bad_file = tmp_path / "bad.py"
        bad_file.write_text(
            textwrap.dedent("""
            class Record:
                def __post_init__(self):
                    object.__setattr__(self, "x", MappingProxyType(dict(self.x)))
        """)
        )
        findings = scan_file(bad_file, tmp_path)
        assert len(findings) == 1
        assert findings[0].rule_id == "FG1"
        assert findings[0].file_path == "bad.py"
