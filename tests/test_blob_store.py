import sys
import types

import pytest

from dmp.datasources import (
    BlobConfig,
    BlobDataLoader,
    BlobConfigurationError,
    load_blob_config,
    load_blob_csv,
)


def test_load_blob_config_success(tmp_path):
    config_path = tmp_path / "blob.yaml"
    config_path.write_text(
        """
        default:
          connection_name: workspaceblobstore
          azureml_datastore_uri: azureml://example
          storage_uri: https://account.blob.core.windows.net/container/path/to/blob.csv
        """,
        encoding="utf-8",
    )

    config = load_blob_config(config_path)

    assert config.connection_name == "workspaceblobstore"
    assert config.azureml_datastore_uri == "azureml://example"
    assert config.account_url == "https://account.blob.core.windows.net"
    assert config.container_name == "container"
    assert config.blob_path == "path/to/blob.csv"


def test_load_blob_config_with_components():
    config = BlobConfig.from_mapping(
        {
            "connection_name": "workspaceblobstore",
            "azureml_datastore_uri": "azureml://example",
            "account_name": "myaccount",
            "container_name": "container",
            "blob_path": "path/to/blob.csv",
            "sas_token": "?sig=abc",
        }
    )

    assert config.account_url == "https://myaccount.blob.core.windows.net"
    assert config.sas_token == "sig=abc"


def test_load_blob_config_missing_required_key(tmp_path):
    config_path = tmp_path / "blob.yaml"
    config_path.write_text(
        """
        default:
          connection_name: workspaceblobstore
        """,
        encoding="utf-8",
    )

    with pytest.raises(BlobConfigurationError):
        load_blob_config(config_path)


def test_blob_data_loader_load_text(monkeypatch, tmp_path):
    payload = b"col1,col2\nvalue1,value2\n"

    azure_module = types.ModuleType("azure")
    azure_module.__path__ = []
    storage_module = types.ModuleType("azure.storage")
    storage_module.__path__ = []
    blob_module = types.ModuleType("azure.storage.blob")
    identity_module = types.ModuleType("azure.identity")

    class DummyCredential:  # pragma: no cover - trivial
        def __init__(self, *args, **kwargs):
            pass

    class DummyDownloader:
        def __init__(self, data):
            self._data = data

        def readall(self):
            return self._data

    class DummyBlobClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        def download_blob(self):
            return DummyDownloader(payload)

    identity_module.DefaultAzureCredential = DummyCredential
    blob_module.BlobClient = DummyBlobClient

    azure_module.storage = storage_module
    azure_module.identity = identity_module

    monkeypatch.setitem(sys.modules, "azure", azure_module)
    monkeypatch.setitem(sys.modules, "azure.storage", storage_module)
    monkeypatch.setitem(sys.modules, "azure.storage.blob", blob_module)
    monkeypatch.setitem(sys.modules, "azure.identity", identity_module)

    config = BlobConfig.from_mapping(
        {
            "connection_name": "workspaceblobstore",
            "azureml_datastore_uri": "azureml://example",
            "storage_uri": "https://account.blob.core.windows.net/container/blob.csv",
        }
    )

    loader = BlobDataLoader(config)
    text = loader.load_text()

    assert "value1" in text
    client = loader.blob_client
    assert isinstance(client, DummyBlobClient)
    assert client.kwargs["container_name"] == "container"


def test_load_blob_csv_convenience(monkeypatch, tmp_path):
    cfg_path = tmp_path / "blob.yaml"
    cfg_path.write_text(
        """
        default:
          connection_name: workspaceblobstore
          azureml_datastore_uri: azureml://example
          storage_uri: https://account.blob.core.windows.net/container/blob.csv
        """,
        encoding="utf-8",
    )

    captured = {}

    import dmp.datasources.blob_store as blob_store_module

    class DummyLoader:
        def __init__(self, config, credential=None, timeout=60):
            captured["config"] = config
            captured["credential"] = credential
            captured["timeout"] = timeout

        def load_csv(self, **kwargs):
            captured["kwargs"] = kwargs
            return "DATAFRAME"

    monkeypatch.setattr(blob_store_module, "BlobDataLoader", DummyLoader)

    result = load_blob_csv(
        cfg_path,
        profile="default",
        timeout=120,
        pandas_kwargs={"sep": ";"},
    )

    assert result == "DATAFRAME"
    assert captured["config"].blob_path == "blob.csv"
    assert captured["timeout"] == 120
    assert captured["kwargs"] == {"sep": ";"}


def test_blob_loader_uses_sas_token(monkeypatch):
    payload = b"col1\nvalue\n"

    class DummyDownloader:
        def readall(self):
            return payload

    class DummyBlobClient:
        def __init__(self, *args, **kwargs):
            captured["credential"] = kwargs.get("credential")

        def download_blob(self):
            return DummyDownloader()

    captured = {}

    azure_module = types.ModuleType("azure")
    azure_module.__path__ = []
    storage_module = types.ModuleType("azure.storage")
    storage_module.__path__ = []
    blob_module = types.ModuleType("azure.storage.blob")

    blob_module.BlobClient = DummyBlobClient
    azure_module.storage = storage_module

    monkeypatch.setitem(sys.modules, "azure", azure_module)
    monkeypatch.setitem(sys.modules, "azure.storage", storage_module)
    monkeypatch.setitem(sys.modules, "azure.storage.blob", blob_module)

    config = BlobConfig.from_mapping(
        {
            "connection_name": "workspaceblobstore",
            "azureml_datastore_uri": "azureml://example",
            "account_name": "acct",
            "container_name": "container",
            "blob_path": "blob.csv",
            "sas_token": "sig=123",
        }
    )

    loader = BlobDataLoader(config)
    loader.load_bytes()

    assert captured["credential"] == "sig=123"
