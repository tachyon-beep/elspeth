import pytest

from dmp.core import artifacts


def test_file_type_helpers():
    assert artifacts.is_file_type("file/csv")
    assert not artifacts.is_file_type("data/tabular")
    assert artifacts.is_data_type("data/tabular")
    assert not artifacts.is_data_type("file/json")


def test_validate_artifact_type():
    artifacts.validate_artifact_type("file/csv")
    artifacts.validate_artifact_type("data/tabular")

    with pytest.raises(ValueError):
        artifacts.validate_artifact_type("unknown/custom")

    with pytest.raises(ValueError):
        artifacts.validate_artifact_type("file/")


def test_normalize_metadata():
    assert artifacts.normalize_metadata(None) == {}
    meta = {"a": 1}
    assert artifacts.normalize_metadata(meta) == meta
