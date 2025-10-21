from __future__ import annotations

import sys
import types
from types import ModuleType

import pytest

import elspeth.core.security.keyvault as kv


def test_parse_secret_uri_valid_and_invalid():
    # Valid with version
    ref = kv._parse_secret_uri("https://myvault.vault.azure.net/secrets/signing/1234")
    assert ref.vault_url == "https://myvault.vault.azure.net"
    assert ref.name == "signing"
    assert ref.version == "1234"

    # Valid without version
    ref = kv._parse_secret_uri("https://x.vault.azure.net/secrets/name")
    from urllib.parse import urlparse

    assert urlparse(ref.vault_url).netloc == "x.vault.azure.net"
    assert ref.name == "name"
    assert ref.version is None

    # Invalid schemes/paths
    with pytest.raises(ValueError):
        kv._parse_secret_uri("ftp://x/secrets/name")
    with pytest.raises(ValueError):
        kv._parse_secret_uri("https://x/")


def test_fetch_secret_from_keyvault_import_guard(monkeypatch):
    # Force ImportError by intercepting imports for azure.*
    import builtins as _b

    real_import = _b.__import__

    def _fake_import(name, *args, **kwargs):  # noqa: D401
        if name.startswith("azure.identity") or name.startswith("azure.keyvault.secrets"):
            raise ImportError("azure not available")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(_b, "__import__", _fake_import)
    with pytest.raises(ImportError):
        kv.fetch_secret_from_keyvault("https://my.vault.azure.net/secrets/name")


def test_fetch_secret_from_keyvault_success_with_and_without_version(monkeypatch):
    # Build fake azure modules in sys.modules
    azure_identity = ModuleType("azure.identity")
    azure_kv = ModuleType("azure.keyvault.secrets")

    class DummyCred:  # noqa: D401 - simple stub
        pass

    class DummySecret:
        def __init__(self, value: str):
            self.value = value

    class DummyClient:
        def __init__(self, *, vault_url: str, credential: object):  # noqa: ARG002
            self.vault_url = vault_url

        def get_secret(self, name: str, version: str | None = None) -> DummySecret:  # noqa: D401
            # Return distinct values for versioned/non-versioned to assert path
            return DummySecret(f"VAL-{name}-{'v' if version else 'nov'}")

    # Attach to modules
    azure_identity.DefaultAzureCredential = DummyCred  # type: ignore[attr-defined]
    azure_kv.SecretClient = DummyClient  # type: ignore[attr-defined]

    # Register in sys.modules
    monkeypatch.setitem(sys.modules, "azure", ModuleType("azure"))
    monkeypatch.setitem(sys.modules, "azure.identity", azure_identity)
    monkeypatch.setitem(sys.modules, "azure.keyvault", ModuleType("azure.keyvault"))
    monkeypatch.setitem(sys.modules, "azure.keyvault.secrets", azure_kv)

    # With version
    v = kv.fetch_secret_from_keyvault("https://my.vault.azure.net/secrets/name/123")
    assert v == "VAL-name-v"

    # Without version
    v2 = kv.fetch_secret_from_keyvault("https://my.vault.azure.net/secrets/name")
    assert v2 == "VAL-name-nov"
