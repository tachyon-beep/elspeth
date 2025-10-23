import json
from pathlib import Path

import pytest

from elspeth.adapters.blob_store import (
    BlobConfig,
    BlobConfigurationError,
    _parse_storage_uri,
    load_blob_config,
)


@pytest.mark.parametrize(
    "uri, msg",
    [
        ("ftp://acct.blob.core.windows.net/c/b.csv", "Unsupported storage URI scheme"),
        ("https:///c/b.csv", "missing a host"),
        ("https://acct.blob.core.windows.net/container_only", "include container and blob path"),
    ],
)
def test_parse_storage_uri_invalid(uri, msg):
    with pytest.raises(BlobConfigurationError, match=msg):
        _parse_storage_uri(uri)


def test_blob_config_from_mapping_with_storage_uri_and_sas_trim():
    data = {
        "connection_name": "ds",
        "azureml_datastore_uri": "azureml://datastores/ds/paths/path",
        "storage_uri": "https://acct.blob.core.windows.net/container/blob.csv",
        "sas_token": "?sig=abc",
    }
    cfg = BlobConfig.from_mapping(data)
    assert cfg.account_url == "https://acct.blob.core.windows.net"
    assert cfg.container_name == "container"
    assert cfg.blob_path == "blob.csv"
    assert cfg.sas_token == "sig=abc"


def test_blob_config_from_mapping_requires_all_account_fields():
    data = {
        "connection_name": "ds",
        "azureml_datastore_uri": "azureml://datastores/ds/paths/path",
        # missing account_name / container_name / blob_path
    }
    with pytest.raises(BlobConfigurationError):
        BlobConfig.from_mapping(data)


def test_load_blob_config_file_missing(tmp_path: Path):
    with pytest.raises(BlobConfigurationError):
        load_blob_config(tmp_path / "nope.yaml")


def test_load_blob_config_invalid_yaml(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("\t\t: not yaml", encoding="utf-8")
    with pytest.raises(BlobConfigurationError):
        load_blob_config(p)


def test_load_blob_config_profile_missing(tmp_path: Path):
    p = tmp_path / "config.yaml"
    p.write_text(
        json.dumps(
            {
                "default": {
                    "connection_name": "c",
                    "azureml_datastore_uri": "x",
                    "account_name": "a",
                    "container_name": "c",
                    "blob_path": "b",
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BlobConfigurationError):
        load_blob_config(p, profile="other")


def test_load_blob_config_profile_string_invalid_json(tmp_path: Path):
    p = tmp_path / "config.yaml"
    # profile value is a string but not valid JSON
    p.write_text(json.dumps({"default": "{not json}"}), encoding="utf-8")
    with pytest.raises(BlobConfigurationError):
        load_blob_config(p)
