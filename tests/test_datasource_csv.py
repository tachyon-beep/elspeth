import pandas as pd
import pytest

from elspeth.plugins.nodes.sources.csv_blob import CSVBlobDataSource
from elspeth.plugins.nodes.sources.csv_local import CSVDataSource


def test_csv_datasource_loads(tmp_path):
    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame({"APPID": ["1", "2"], "value": [10, 20]})
    df.to_csv(csv_path, index=False)

    datasource = CSVDataSource(path=csv_path, retain_local=False)
    loaded = datasource.load()

    assert list(loaded["APPID"].astype(str)) == ["1", "2"]
    assert loaded["value"].sum() == 30


def test_csv_datasource_skip_on_missing(tmp_path):
    datasource = CSVDataSource(path=tmp_path / "missing.csv", on_error="skip", retain_local=False)
    loaded = datasource.load()
    assert loaded.empty


def test_csv_blob_datasource_loads(tmp_path):
    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame({"APPID": ["1", "2"], "value": [10, 20]})
    df.to_csv(csv_path, index=False)

    datasource = CSVBlobDataSource(path=csv_path, retain_local=False)
    loaded = datasource.load()

    assert list(loaded["APPID"].astype(str)) == ["1", "2"]
    assert loaded["value"].sum() == 30


def test_csv_datasource_missing_raises(tmp_path):
    datasource = CSVDataSource(path=tmp_path / "missing.csv", retain_local=False)
    with pytest.raises(FileNotFoundError):
        datasource.load()


def test_csv_datasource_security_level_and_dtype(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("APPID,value\n1,001\n2,002\n", encoding="utf-16")

    datasource = CSVDataSource(
        path=csv_path,
        dtype={"value": str},
        encoding="utf-16",
        security_level="Official",
        determinism_level="guaranteed",
        retain_local=False,
    )

    df = datasource.load()
    assert df.attrs["security_level"] == "OFFICIAL"
    assert df.attrs["determinism_level"] == "guaranteed"
    assert list(df["value"]) == ["001", "002"]


def test_csv_blob_datasource_skip_missing_returns_empty(tmp_path, caplog):
    datasource = CSVBlobDataSource(
        path=tmp_path / "missing.csv",
        on_error="skip",
        security_level="SECRET",
        determinism_level="guaranteed",
        retain_local=False,
    )
    with caplog.at_level("WARNING"):
        df = datasource.load()
    assert df.empty
    assert df.attrs["security_level"] == "SECRET"
    assert df.attrs["determinism_level"] == "guaranteed"
    assert any("missing file" in record.message for record in caplog.records)


def test_csv_blob_datasource_failure_returns_empty(monkeypatch, tmp_path, caplog):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("content", encoding="utf-8")

    datasource = CSVBlobDataSource(path=csv_path, on_error="skip", retain_local=False)

    def _raise_runtimeerror(*_args, **_kwargs):  # noqa: D401
        raise RuntimeError("boom")

    monkeypatch.setattr("pandas.read_csv", _raise_runtimeerror)

    with caplog.at_level("WARNING"):
        df = datasource.load()

    assert df.empty
    assert any("failed; returning empty" in record.message for record in caplog.records)


@pytest.mark.parametrize("cls", [CSVDataSource, CSVBlobDataSource])
def test_csv_datasource_invalid_on_error(cls, tmp_path):
    with pytest.raises(ValueError):
        cls(path=tmp_path / "data.csv", on_error="ignore", retain_local=False)


def test_csv_datasource_with_schema_config(tmp_path):
    """Test CSV datasource with explicit schema configuration."""
    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25]})
    df.to_csv(csv_path, index=False)

    schema_config = {
        "name": {"type": "string", "required": True},
        "age": {"type": "integer", "required": True},
    }

    datasource = CSVDataSource(path=csv_path, schema=schema_config, retain_local=False)
    loaded = datasource.load()

    assert loaded.attrs["schema"] is not None
    assert loaded.attrs["schema"].__name__ == "sample_ConfigSchema"


def test_csv_datasource_schema_inference(tmp_path):
    """Test CSV datasource with schema inference enabled."""
    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25]})
    df.to_csv(csv_path, index=False)

    datasource = CSVDataSource(path=csv_path, infer_schema=True, retain_local=False)
    loaded = datasource.load()

    assert loaded.attrs["schema"] is not None
    assert "InferredSchema" in loaded.attrs["schema"].__name__


def test_csv_datasource_with_retain_local(tmp_path):
    """Test CSV datasource with local retention enabled."""
    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame({"name": ["Alice"], "value": [100]})
    df.to_csv(csv_path, index=False)

    retain_dir = tmp_path / "retained"

    datasource = CSVDataSource(path=csv_path, retain_local=True, retain_local_path=str(retain_dir / "custom_name.csv"))
    loaded = datasource.load()

    assert loaded.attrs["retained_local_path"] == str(retain_dir / "custom_name.csv")
    assert (retain_dir / "custom_name.csv").exists()


def test_csv_datasource_with_retain_local_auto_path(tmp_path):
    """Test CSV datasource with automatic retention path generation."""
    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame({"name": ["Alice"], "value": [100]})
    df.to_csv(csv_path, index=False)

    datasource = CSVDataSource(path=csv_path, retain_local=True, retain_local_path=None)
    loaded = datasource.load()

    # Should have generated automatic path in audit_data/
    assert "retained_local_path" in loaded.attrs
    assert "audit_data" in loaded.attrs["retained_local_path"]
