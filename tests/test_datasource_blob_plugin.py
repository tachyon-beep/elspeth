import pandas as pd
import pytest

from elspeth.plugins.datasources.blob import BlobDataSource


def test_blob_datasource_loads_with_kwargs(monkeypatch, tmp_path):
    calls = {}

    def fake_load(path, *, profile, pandas_kwargs):
        calls["path"] = path
        calls["profile"] = profile
        calls["kwargs"] = pandas_kwargs
        return pd.DataFrame({"value": [1, 2]})

    monkeypatch.setattr("elspeth.plugins.datasources.blob.load_blob_csv", fake_load)

    datasource = BlobDataSource(
        config_path=str(tmp_path / "config.yaml"),
        profile="alt",
        pandas_kwargs={"sep": ";"},
        security_level="Secret",
    )

    df = datasource.load()

    assert df.attrs["security_level"] == "secret"
    assert calls == {
        "path": str(tmp_path / "config.yaml"),
        "profile": "alt",
        "kwargs": {"sep": ";"},
    }


def test_blob_datasource_skip_on_error(monkeypatch, caplog, tmp_path):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("elspeth.plugins.datasources.blob.load_blob_csv", boom)

    datasource = BlobDataSource(
        config_path=str(tmp_path / "config.yaml"),
        on_error="skip",
        security_level="official-sensitive",
    )

    with caplog.at_level("WARNING"):
        df = datasource.load()

    assert df.empty
    assert df.attrs["security_level"] == "official-sensitive"
    assert any("Blob datasource failed" in record.message for record in caplog.records)


def test_blob_datasource_invalid_on_error(tmp_path):
    with pytest.raises(ValueError):
        BlobDataSource(config_path=str(tmp_path / "config.yaml"), on_error="ignore")
