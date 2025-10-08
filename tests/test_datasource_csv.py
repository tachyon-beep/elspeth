import pandas as pd

from dmp.plugins.datasources.csv_blob import CSVBlobDataSource
from dmp.plugins.datasources.csv_local import CSVDataSource


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
