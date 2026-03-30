"""Tests for secret contract types — security invariants."""

from __future__ import annotations

from elspeth.contracts.secrets import ResolvedSecret, SecretInventoryItem


class TestResolvedSecret:
    def test_repr_does_not_contain_value(self):
        """SECURITY: __repr__ must never expose plaintext."""
        rs = ResolvedSecret(name="API_KEY", value="sk-secret-123", scope="user", fingerprint="abc123")
        repr_str = repr(rs)
        assert "sk-secret-123" not in repr_str
        assert "API_KEY" in repr_str

    def test_str_does_not_contain_value(self):
        rs = ResolvedSecret(name="API_KEY", value="sk-secret-123", scope="user", fingerprint="abc123")
        assert "sk-secret-123" not in str(rs)

    def test_fields_accessible(self):
        rs = ResolvedSecret(name="KEY", value="val", scope="server", fingerprint="fp")
        assert rs.name == "KEY"
        assert rs.value == "val"
        assert rs.scope == "server"
        assert rs.fingerprint == "fp"

    def test_frozen(self):
        import pytest

        rs = ResolvedSecret(name="KEY", value="val", scope="server", fingerprint="fp")
        with pytest.raises(AttributeError):
            rs.value = "new"  # type: ignore[misc]


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
