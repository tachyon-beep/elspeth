import pytest
import pandas as pd

from elspeth.plugins.datasources.csv_blob import CSVBlobDataSource
from elspeth.plugins.datasources.csv_local import CSVDataSource


def test_csv_datasource_loads(tmp_path):
    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame({"APPID": ["1", "2"], "value": [10, 20]})
    df.to_csv(csv_path, index=False)

    datasource = CSVDataSource(path=csv_path)
    loaded = datasource.load()

    assert list(loaded["APPID"].astype(str)) == ["1", "2"]
    assert loaded["value"].sum() == 30


def test_csv_datasource_skip_on_missing(tmp_path):
    datasource = CSVDataSource(path=tmp_path / "missing.csv", on_error="skip")
    loaded = datasource.load()
    assert loaded.empty


def test_csv_blob_datasource_loads(tmp_path):
    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame({"APPID": ["1", "2"], "value": [10, 20]})
    df.to_csv(csv_path, index=False)

    datasource = CSVBlobDataSource(path=csv_path)
    loaded = datasource.load()

    assert list(loaded["APPID"].astype(str)) == ["1", "2"]
    assert loaded["value"].sum() == 30


def test_csv_datasource_missing_raises(tmp_path):
    datasource = CSVDataSource(path=tmp_path / "missing.csv")
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
    )

    df = datasource.load()
    assert df.attrs["security_level"] == "official"
    assert list(df["value"]) == ["001", "002"]


def test_csv_blob_datasource_skip_missing_returns_empty(tmp_path, caplog):
    datasource = CSVBlobDataSource(path=tmp_path / "missing.csv", on_error="skip", security_level="top-secret")
    with caplog.at_level("WARNING"):
        df = datasource.load()
    assert df.empty
    assert df.attrs["security_level"] == "top-secret"
    assert any("missing file" in record.message for record in caplog.records)


def test_csv_blob_datasource_failure_returns_empty(monkeypatch, tmp_path, caplog):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("content", encoding="utf-8")

    datasource = CSVBlobDataSource(path=csv_path, on_error="skip")
    monkeypatch.setattr("pandas.read_csv", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with caplog.at_level("WARNING"):
        df = datasource.load()

    assert df.empty
    assert any("failed; returning empty" in record.message for record in caplog.records)


@pytest.mark.parametrize("cls", [CSVDataSource, CSVBlobDataSource])
def test_csv_datasource_invalid_on_error(cls, tmp_path):
    with pytest.raises(ValueError):
        cls(path=tmp_path / "data.csv", on_error="ignore")
