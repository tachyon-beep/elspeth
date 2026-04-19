"""Secret-scrubbing helper for DeclarationContractViolation payloads."""

from __future__ import annotations

from elspeth.contracts.secret_scrub import scrub_payload_for_audit


def test_plain_values_pass_through() -> None:
    p = {"field": "name", "count": 3, "flag": True}
    assert scrub_payload_for_audit(p) == {"field": "name", "count": 3, "flag": True}


def test_api_key_like_value_is_redacted() -> None:
    p = {"api_key": "sk-1234567890abcdef1234567890abcdef"}
    out = scrub_payload_for_audit(p)
    assert out["api_key"] == "<redacted-secret>"


def test_aws_access_key_redacted() -> None:
    p = {"note": "AKIAIOSFODNN7EXAMPLE in log"}
    out = scrub_payload_for_audit(p)
    assert "AKIA" not in out["note"]


def test_nested_mapping_scrubbed() -> None:
    p = {"outer": {"inner_key": "sk-abcdef1234567890abcdef1234567890"}}
    out = scrub_payload_for_audit(p)
    assert out["outer"]["inner_key"] == "<redacted-secret>"


def test_sequence_values_scrubbed() -> None:
    p = {"secrets": ["sk-abcdef1234567890abcdef1234567890", "normal"]}
    out = scrub_payload_for_audit(p)
    assert out["secrets"] == ["<redacted-secret>", "normal"]
