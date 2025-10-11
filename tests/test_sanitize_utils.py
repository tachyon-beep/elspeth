import pytest

from elspeth.plugins.outputs._sanitize import DANGEROUS_PREFIXES, sanitize_cell, should_sanitize


def test_should_sanitize_dangerous_prefixes():
    for prefix in DANGEROUS_PREFIXES:
        if prefix == "'":
            continue
        value = f"{prefix}formula"
        assert should_sanitize(value) is True
        assert sanitize_cell(value) == "'" + value


def test_sanitize_idempotent_for_guarded_values():
    value = "'already_guarded"
    assert should_sanitize(value) is False
    assert sanitize_cell(value) == value


def test_sanitize_handles_bom_prefix():
    value = "\ufeff=SUM(A1:A2)"
    sanitized = sanitize_cell(value)
    assert sanitized.startswith("\ufeff'=")
    assert sanitized.endswith("SUM(A1:A2)")


def test_sanitize_custom_guard():
    value = "=payload"
    sanitized = sanitize_cell(value, guard=";")
    assert sanitized == ";=payload"
    assert should_sanitize(value, guard=";") is True


def test_sanitize_non_string_passthrough():
    assert sanitize_cell(42) == 42
    assert should_sanitize(42) is False


def test_invalid_guard_raises():
    assert sanitize_cell("=bad", guard="") == "'=bad"
    with pytest.raises(ValueError):
        sanitize_cell("=bad", guard="multi")
