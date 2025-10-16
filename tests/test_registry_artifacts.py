import pytest

from elspeth.core.registries.sink import sink_registry
from elspeth.core.validation_base import ConfigurationError


def test_sink_accepts_artifact_config():
    config = {
        "path": "out.csv",
        "security_level": "OFFICIAL",
        "determinism_level": "guaranteed",
        "artifacts": {
            "produces": [
                {"name": "csv", "type": "file/csv", "persist": True},
            ],
            "consumes": ["data/tabular"],
        },
    }

    assert sink_registry.validate("csv", config) is None


def test_sink_rejects_invalid_artifact_config():
    config = {
        "path": "out.csv",
        "security_level": "OFFICIAL",
        "determinism_level": "guaranteed",
        "artifacts": {
            "produces": [
                {"name": "csv"},
            ],
        },
    }

    with pytest.raises(ConfigurationError):
        sink_registry.validate("csv", config)
