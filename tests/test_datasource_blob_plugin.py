import pandas as pd
import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.nodes.sources.blob import BlobDataSource


def test_blob_datasource_loads_with_kwargs(monkeypatch, tmp_path):
    calls = {}

    def fake_load(path, *, profile, pandas_kwargs):
        calls["path"] = path
        calls["profile"] = profile
        calls["kwargs"] = pandas_kwargs
        return pd.DataFrame({"value": [1, 2]})

    monkeypatch.setattr("elspeth.plugins.nodes.sources.blob.load_blob_csv", fake_load)

    datasource = BlobDataSource(
        config_path=str(tmp_path / "config.yaml"),
        profile="alt",
        pandas_kwargs={"sep": ";"},
        determinism_level="guaranteed",
        retain_local=False,
    )

    df = datasource.load()

    # SecureDataFrame wraps the DataFrame - access attrs via .data
    assert df.data.attrs["security_level"] == "UNOFFICIAL"
    assert df.data.attrs["determinism_level"] == "guaranteed"
    assert df.security_level == SecurityLevel.UNOFFICIAL
    assert calls == {
        "path": str(tmp_path / "config.yaml"),
        "profile": "alt",
        "kwargs": {"sep": ";"},
    }


def test_blob_datasource_skip_on_error(monkeypatch, caplog, tmp_path):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("elspeth.plugins.nodes.sources.blob.load_blob_csv", boom)

    datasource = BlobDataSource(
        config_path=str(tmp_path / "config.yaml"),
        on_error="skip",
        determinism_level="guaranteed",
        retain_local=False,
    )

    with caplog.at_level("WARNING"):
        df = datasource.load()

    # SecureDataFrame wraps the DataFrame - access via .data
    assert df.data.empty
    assert df.data.attrs["security_level"] == "UNOFFICIAL"
    assert df.data.attrs["determinism_level"] == "guaranteed"
    assert df.security_level == SecurityLevel.UNOFFICIAL
    assert any("Blob datasource failed" in record.message for record in caplog.records)


def test_blob_datasource_invalid_on_error(tmp_path):
    with pytest.raises(ValueError):
        BlobDataSource(config_path=str(tmp_path / "config.yaml"), on_error="ignore", retain_local=False)
