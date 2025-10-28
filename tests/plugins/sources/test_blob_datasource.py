import pandas as pd
import pytest

from elspeth.plugins.nodes.sources.blob import BlobDataSource


def test_blob_datasource_success_and_retain_local(monkeypatch, tmp_path):
    def fake_load_blob_csv(config_path, profile, pandas_kwargs):  # noqa: ARG001
        return pd.DataFrame({"a": [1, 2]})

    monkeypatch.setattr("elspeth.plugins.nodes.sources.blob.load_blob_csv", fake_load_blob_csv)

    retain_path = tmp_path / "retained.csv"
    ds = BlobDataSource(
        config_path="dummy.yaml",
        profile="p",
        retain_local=True,
        retain_local_path=str(retain_path),
        on_error="abort",
        determinism_level="low",  # User-configurable per ADR-002-B
    )

    df = ds.load()
    assert len(df) == 2
    assert df.attrs["security_level"] == "UNOFFICIAL"  # ADR-002-B: Hard-coded in BlobDataSource
    assert df.attrs["determinism_level"] == "low"
    assert retain_path.exists()


def test_blob_datasource_skip_on_error_returns_empty(monkeypatch):
    def boom(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("network fail")

    monkeypatch.setattr("elspeth.plugins.nodes.sources.blob.load_blob_csv", boom)

    ds = BlobDataSource(
        config_path="missing.yaml",
        profile="default",
        retain_local=False,
        on_error="skip",
        determinism_level="none",  # User-configurable per ADR-002-B
    )

    df = ds.load()
    assert df.empty
    assert df.attrs["security_level"] == "UNOFFICIAL"  # ADR-002-B: Hard-coded in BlobDataSource
    assert df.attrs["determinism_level"] == "none"


def test_blob_datasource_invalid_on_error_raises():
    with pytest.raises(ValueError):
        BlobDataSource(
            config_path="x.yaml",
            profile="p",
            retain_local=False,
            on_error="halt",  # invalid
            determinism_level="none",  # User-configurable per ADR-002-B
        )
