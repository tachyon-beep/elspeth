"""Tests for secret contract types — security invariants."""

from __future__ import annotations

import pytest

from elspeth.contracts.secrets import CreateSecretResult, ResolvedSecret, SecretInventoryItem

_VALID_FINGERPRINT = "a" * 64


class TestResolvedSecret:
    def test_repr_does_not_contain_value(self):
        """SECURITY: __repr__ must never expose plaintext."""
        rs = ResolvedSecret(name="API_KEY", value="sk-secret-123", scope="user", fingerprint=_VALID_FINGERPRINT)
        repr_str = repr(rs)
        assert "sk-secret-123" not in repr_str
        assert "API_KEY" in repr_str

    def test_str_does_not_contain_value(self):
        rs = ResolvedSecret(name="API_KEY", value="sk-secret-123", scope="user", fingerprint=_VALID_FINGERPRINT)
        assert "sk-secret-123" not in str(rs)

    def test_fields_accessible(self):
        rs = ResolvedSecret(name="KEY", value="val", scope="server", fingerprint=_VALID_FINGERPRINT)
        assert rs.name == "KEY"
        assert rs.value == "val"
        assert rs.scope == "server"
        assert rs.fingerprint == _VALID_FINGERPRINT

    def test_frozen(self):
        rs = ResolvedSecret(name="KEY", value="val", scope="server", fingerprint=_VALID_FINGERPRINT)
        with pytest.raises(AttributeError):
            rs.value = "new"

    def test_invalid_scope_rejected(self) -> None:
        with pytest.raises(ValueError, match="scope must be one of"):
            ResolvedSecret(
                name="KEY",
                value="val",
                scope="bogus",  # type: ignore[arg-type]
                fingerprint=_VALID_FINGERPRINT,
            )

    @pytest.mark.parametrize("fingerprint", ["abc123", "A" * 64, "g" * 64])
    def test_invalid_fingerprint_rejected(self, fingerprint: str) -> None:
        with pytest.raises(ValueError, match="64-char lowercase hex"):
            ResolvedSecret(name="KEY", value="val", scope="server", fingerprint=fingerprint)


class TestCreateSecretResult:
    def test_valid_construction(self) -> None:
        result = CreateSecretResult(name="KEY", scope="org", fingerprint=_VALID_FINGERPRINT)
        assert result.scope == "org"
        assert result.fingerprint == _VALID_FINGERPRINT

    def test_invalid_scope_rejected(self) -> None:
        with pytest.raises(ValueError, match="scope must be one of"):
            CreateSecretResult(
                name="KEY",
                scope="bogus",  # type: ignore[arg-type]
                fingerprint=_VALID_FINGERPRINT,
            )

    @pytest.mark.parametrize("fingerprint", ["nothex", "A" * 64, "g" * 64])
    def test_invalid_fingerprint_rejected(self, fingerprint: str) -> None:
        with pytest.raises(ValueError, match="64-char lowercase hex"):
            CreateSecretResult(name="KEY", scope="user", fingerprint=fingerprint)


class TestSecretInventoryItem:
    def test_no_value_field(self):
        """Inventory items must not carry secret values."""
        item = SecretInventoryItem(name="KEY", scope="user", available=True)
        assert not hasattr(item, "value")

    def test_fields(self):
        item = SecretInventoryItem(name="KEY", scope="server", available=False, source_kind="env")
        assert item.name == "KEY"
        assert item.scope == "server"
        assert item.available is False
        assert item.source_kind == "env"

    def test_invalid_scope_rejected(self) -> None:
        with pytest.raises(ValueError, match="scope must be one of"):
            SecretInventoryItem(name="KEY", scope="bogus", available=True)  # type: ignore[arg-type]
