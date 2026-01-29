"""Tests for contracts enforcement script."""

from pathlib import Path
from unittest.mock import patch

from scripts.check_contracts import (
    SettingsViolation,
    check_settings_alignment,
    find_settings_classes,
    find_type_definitions,
    load_whitelist,
)


def test_finds_dataclass_definitions(tmp_path: Path) -> None:
    """Finds @dataclass decorated classes."""
    test_file = tmp_path / "test.py"
    test_file.write_text("""
from dataclasses import dataclass

@dataclass
class MyType:
    name: str
""")

    definitions = find_type_definitions(test_file)
    assert len(definitions) == 1
    assert definitions[0][0] == "MyType"
    assert definitions[0][2] == "dataclass"


def test_finds_dataclass_with_args(tmp_path: Path) -> None:
    """Finds @dataclass(frozen=True) decorated classes."""
    test_file = tmp_path / "test.py"
    test_file.write_text("""
from dataclasses import dataclass

@dataclass(frozen=True)
class FrozenType:
    value: int
""")

    definitions = find_type_definitions(test_file)
    assert len(definitions) == 1
    assert definitions[0][0] == "FrozenType"
    assert definitions[0][2] == "dataclass"


def test_finds_enum_definitions(tmp_path: Path) -> None:
    """Finds Enum subclasses."""
    test_file = tmp_path / "test.py"
    test_file.write_text("""
from enum import Enum

class MyEnum(Enum):
    A = "a"
""")

    definitions = find_type_definitions(test_file)
    assert len(definitions) == 1
    assert definitions[0][0] == "MyEnum"
    assert definitions[0][2] == "Enum"


def test_finds_typeddict_definitions(tmp_path: Path) -> None:
    """Finds TypedDict subclasses."""
    test_file = tmp_path / "test.py"
    test_file.write_text("""
from typing import TypedDict

class MyDict(TypedDict):
    name: str
    value: int
""")

    definitions = find_type_definitions(test_file)
    assert len(definitions) == 1
    assert definitions[0][0] == "MyDict"
    assert definitions[0][2] == "TypedDict"


def test_finds_namedtuple_definitions(tmp_path: Path) -> None:
    """Finds NamedTuple subclasses."""
    test_file = tmp_path / "test.py"
    test_file.write_text("""
from typing import NamedTuple

class MyTuple(NamedTuple):
    x: int
    y: int
""")

    definitions = find_type_definitions(test_file)
    assert len(definitions) == 1
    assert definitions[0][0] == "MyTuple"
    assert definitions[0][2] == "NamedTuple"


def test_ignores_pydantic_basemodel(tmp_path: Path) -> None:
    """Does not flag Pydantic BaseModel classes."""
    test_file = tmp_path / "test.py"
    test_file.write_text("""
from pydantic import BaseModel

class MyModel(BaseModel):
    name: str
""")

    definitions = find_type_definitions(test_file)
    assert len(definitions) == 0


def test_ignores_plugin_schema(tmp_path: Path) -> None:
    """Does not flag PluginSchema classes."""
    test_file = tmp_path / "test.py"
    test_file.write_text("""
from elspeth.contracts import PluginSchema

class MyPluginConfig(PluginSchema):
    setting: str
""")

    definitions = find_type_definitions(test_file)
    assert len(definitions) == 0


def test_finds_multiple_definitions(tmp_path: Path) -> None:
    """Finds multiple type definitions in a single file."""
    test_file = tmp_path / "test.py"
    test_file.write_text("""
from dataclasses import dataclass
from enum import Enum
from typing import TypedDict

@dataclass
class DataType:
    value: int

class StatusEnum(Enum):
    ACTIVE = "active"

class ConfigDict(TypedDict):
    name: str
""")

    definitions = find_type_definitions(test_file)
    assert len(definitions) == 3
    names = {d[0] for d in definitions}
    assert names == {"DataType", "StatusEnum", "ConfigDict"}


def test_whitelist_loading(tmp_path: Path) -> None:
    """Loads whitelist from YAML."""
    whitelist_file = tmp_path / ".contracts-whitelist.yaml"
    whitelist_file.write_text("""
allowed_external_types:
  - "foo/bar:MyType"
""")

    whitelist, entries = load_whitelist(whitelist_file)
    assert "foo/bar:MyType" in whitelist["types"]
    assert len(entries) == 1
    assert entries[0].value == "foo/bar:MyType"
    assert entries[0].category == "type"


def test_whitelist_loading_empty_file(tmp_path: Path) -> None:
    """Handles empty whitelist file."""
    whitelist_file = tmp_path / ".contracts-whitelist.yaml"
    whitelist_file.write_text("")

    whitelist, entries = load_whitelist(whitelist_file)
    assert whitelist == {"types": set(), "dicts": set()}
    assert entries == []


def test_whitelist_loading_nonexistent_file(tmp_path: Path) -> None:
    """Handles missing whitelist file."""
    whitelist_file = tmp_path / "nonexistent.yaml"

    whitelist, entries = load_whitelist(whitelist_file)
    assert whitelist == {"types": set(), "dicts": set()}
    assert entries == []


def test_whitelist_loading_multiple_entries(tmp_path: Path) -> None:
    """Loads multiple whitelist entries."""
    whitelist_file = tmp_path / ".contracts-whitelist.yaml"
    whitelist_file.write_text("""
allowed_external_types:
  - "module/a:TypeA"
  - "module/b:TypeB"
  - "module/c:TypeC"
""")

    whitelist, entries = load_whitelist(whitelist_file)
    assert len(whitelist["types"]) == 3
    assert "module/a:TypeA" in whitelist["types"]
    assert "module/b:TypeB" in whitelist["types"]
    assert "module/c:TypeC" in whitelist["types"]
    assert len(entries) == 3
    assert all(e.category == "type" for e in entries)


def test_handles_syntax_errors(tmp_path: Path) -> None:
    """Gracefully handles files with syntax errors."""
    test_file = tmp_path / "broken.py"
    test_file.write_text("def broken(\n")  # Invalid syntax

    definitions = find_type_definitions(test_file)
    assert definitions == []


def test_handles_unicode_errors(tmp_path: Path) -> None:
    """Gracefully handles files with encoding issues."""
    test_file = tmp_path / "binary.py"
    test_file.write_bytes(b"\x80\x81\x82")  # Invalid UTF-8

    definitions = find_type_definitions(test_file)
    assert definitions == []


# =============================================================================
# Settings Alignment Tests
# =============================================================================


def test_find_settings_classes_finds_settings_suffix(tmp_path: Path) -> None:
    """Finds classes ending in 'Settings'."""
    test_file = tmp_path / "config.py"
    test_file.write_text("""
from pydantic import BaseModel

class RetrySettings(BaseModel):
    max_attempts: int

class RateLimitSettings(BaseModel):
    enabled: bool

class SomeConfig(BaseModel):  # Should NOT match - doesn't end in 'Settings'
    value: str
""")

    settings = find_settings_classes(test_file)
    names = {s[0] for s in settings}
    assert names == {"RetrySettings", "RateLimitSettings"}
    assert "SomeConfig" not in names


def test_find_settings_classes_returns_line_numbers(tmp_path: Path) -> None:
    """Returns correct line numbers for Settings classes."""
    test_file = tmp_path / "config.py"
    test_file.write_text("""
class FirstSettings:
    pass

class SecondSettings:
    pass
""")

    settings = find_settings_classes(test_file)
    # Line 2 and Line 5 (accounting for leading newline)
    assert len(settings) == 2
    assert settings[0] == ("FirstSettings", 2)
    assert settings[1] == ("SecondSettings", 5)


def test_find_settings_classes_handles_empty_file(tmp_path: Path) -> None:
    """Handles empty files gracefully."""
    test_file = tmp_path / "empty.py"
    test_file.write_text("")

    settings = find_settings_classes(test_file)
    assert settings == []


def test_find_settings_classes_handles_syntax_errors(tmp_path: Path) -> None:
    """Handles syntax errors gracefully."""
    test_file = tmp_path / "broken.py"
    test_file.write_text("class BrokenSettings(\n")  # Invalid syntax

    settings = find_settings_classes(test_file)
    assert settings == []


def test_check_settings_alignment_passes_with_mapping(tmp_path: Path) -> None:
    """Settings class with Runtime counterpart passes."""
    test_file = tmp_path / "config.py"
    test_file.write_text("""
class RetrySettings:
    pass
""")

    # Mock the alignment module to have RetrySettings in SETTINGS_TO_RUNTIME
    with (
        patch(
            "elspeth.contracts.config.alignment.SETTINGS_TO_RUNTIME",
            {"RetrySettings": "RuntimeRetryConfig"},
        ),
        patch("elspeth.contracts.config.alignment.EXEMPT_SETTINGS", set()),
    ):
        violations = check_settings_alignment(test_file)
        assert violations == []


def test_check_settings_alignment_passes_with_exempt(tmp_path: Path) -> None:
    """Settings class in EXEMPT_SETTINGS passes."""
    test_file = tmp_path / "config.py"
    test_file.write_text("""
class SourceSettings:
    pass
""")

    # Mock the alignment module to have SourceSettings in EXEMPT_SETTINGS
    with (
        patch("elspeth.contracts.config.alignment.SETTINGS_TO_RUNTIME", {}),
        patch("elspeth.contracts.config.alignment.EXEMPT_SETTINGS", {"SourceSettings"}),
    ):
        violations = check_settings_alignment(test_file)
        assert violations == []


def test_check_settings_alignment_detects_orphaned(tmp_path: Path) -> None:
    """Orphaned Settings class is detected as violation."""
    test_file = tmp_path / "config.py"
    test_file.write_text("""
class OrphanedSettings:
    pass
""")

    # Mock empty mappings - OrphanedSettings is not mapped or exempt
    with (
        patch("elspeth.contracts.config.alignment.SETTINGS_TO_RUNTIME", {}),
        patch("elspeth.contracts.config.alignment.EXEMPT_SETTINGS", set()),
    ):
        violations = check_settings_alignment(test_file)
        assert len(violations) == 1
        assert violations[0].class_name == "OrphanedSettings"
        assert violations[0].line == 2


def test_check_settings_alignment_multiple_classes(tmp_path: Path) -> None:
    """Mixed scenario: mapped, exempt, and orphaned."""
    test_file = tmp_path / "config.py"
    test_file.write_text("""
class MappedSettings:
    pass

class ExemptSettings:
    pass

class OrphanedSettings:
    pass
""")

    with (
        patch(
            "elspeth.contracts.config.alignment.SETTINGS_TO_RUNTIME",
            {"MappedSettings": "RuntimeMappedConfig"},
        ),
        patch("elspeth.contracts.config.alignment.EXEMPT_SETTINGS", {"ExemptSettings"}),
    ):
        violations = check_settings_alignment(test_file)
        # Only OrphanedSettings should be flagged
        assert len(violations) == 1
        assert violations[0].class_name == "OrphanedSettings"


def test_check_settings_alignment_uses_real_mappings() -> None:
    """Integration test: actual core/config.py with real mappings.

    This verifies that the current codebase passes the check.
    If this fails, a new Settings class was added without updating
    SETTINGS_TO_RUNTIME or EXEMPT_SETTINGS in alignment.py.
    """
    from pathlib import Path

    config_path = Path("src/elspeth/core/config.py")
    if not config_path.exists():
        # Skip if running from different directory
        return

    violations = check_settings_alignment(config_path)
    assert violations == [], (
        f"Orphaned Settings classes found: {[v.class_name for v in violations]}. "
        "Add to SETTINGS_TO_RUNTIME or EXEMPT_SETTINGS in contracts/config/alignment.py"
    )


def test_settings_violation_dataclass() -> None:
    """SettingsViolation dataclass holds expected fields."""
    violation = SettingsViolation(
        class_name="TestSettings",
        file="/path/to/config.py",
        line=42,
    )
    assert violation.class_name == "TestSettings"
    assert violation.file == "/path/to/config.py"
    assert violation.line == 42
