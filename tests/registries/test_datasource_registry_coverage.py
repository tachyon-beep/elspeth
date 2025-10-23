from __future__ import annotations

from types import SimpleNamespace
import pytest

from elspeth.core.registries.datasource import datasource_registry


def test_datasource_registry_csv_variants(tmp_path):
    # Create a small CSV file
    p = tmp_path / "data.csv"
    p.write_text("id\n1\n", encoding="utf-8")

    # CSV blob
    ds1 = datasource_registry.create(
        name="csv_blob",
        options={
            "path": str(p),
            "retain_local": False,
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
        },
        require_determinism=True,
    )
    assert hasattr(ds1, "load")

    # Local CSV
    ds2 = datasource_registry.create(
        name="local_csv",
        options={
            "path": str(p),
            "retain_local": False,
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
        },
        require_determinism=True,
    )
    assert hasattr(ds2, "load")


def test_datasource_registry_azure_blob_validation(monkeypatch, tmp_path):
    # Stub blob config and endpoint validation to avoid external dependencies
    import elspeth.core.registries.datasource as mod

    monkeypatch.setattr(mod, "load_blob_config", lambda *a, **k: SimpleNamespace(account_url="https://acct.blob.core.windows.net"))
    monkeypatch.setattr(mod, "validate_azure_blob_endpoint", lambda **_k: None)

    # Use a fake config path; create() should still succeed due to stubs
    ds = datasource_registry.create(
        name="azure_blob",
        options={
            "config_path": str(tmp_path / "blob.yaml"),
            "profile": "default",
            "retain_local": False,
            "security_level": "OFFICIAL",
            "determinism_level": "guaranteed",
        },
        require_determinism=True,
    )
    assert hasattr(ds, "load")


def test_datasource_registry_azure_blob_validation_error(monkeypatch, tmp_path):
    import elspeth.core.registries.datasource as mod
    from elspeth.core.validation.base import ConfigurationError

    # Stub loader and force validator to raise
    monkeypatch.setattr(mod, "load_blob_config", lambda *a, **k: SimpleNamespace(account_url="https://bad.example.com"))

    def _raise(**_k):  # noqa: D401
        raise ValueError("not approved")

    monkeypatch.setattr(mod, "validate_azure_blob_endpoint", _raise)

    with pytest.raises(ConfigurationError):
        datasource_registry.create(
            name="azure_blob",
            options={
                "config_path": str(tmp_path / "blob.yaml"),
                "profile": "default",
                "retain_local": False,
                "security_level": "OFFICIAL",
                "determinism_level": "guaranteed",
            },
            require_determinism=True,
        )


def test_datasource_factory_fallback_account_url_branch(monkeypatch):
    # Exercise the 'account_url in options' fallback branch by calling factory directly
    import elspeth.core.registries.datasource as mod
    from elspeth.core.base.plugin_context import PluginContext

    # Accept arbitrary kwargs and avoid real class constructor
    class _Dummy:
        def __init__(self, **_opts):  # noqa: D401
            return None

    monkeypatch.setattr(mod, "BlobDataSource", _Dummy)
    monkeypatch.setattr(mod, "validate_azure_blob_endpoint", lambda **_k: None)

    ctx = PluginContext(plugin_name="suite", plugin_kind="suite", security_level="OFFICIAL")
    out = mod._create_blob_datasource({"account_url": "https://acct.blob.core.windows.net", "profile": "default"}, ctx)
    assert isinstance(out, _Dummy)
