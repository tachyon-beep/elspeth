import pytest

from dmp.core import registry
from dmp.core.validation import ConfigurationError


def test_sink_accepts_artifact_config():
    config = {
        "path": "out.csv",
        "artifacts": {
            "produces": [
                {"name": "csv", "type": "file/csv", "persist": True},
            ],
            "consumes": ["data/tabular"],
        },
    }

    registry.registry.validate_sink("csv", config)


def test_sink_rejects_invalid_artifact_config():
    config = {
        "path": "out.csv",
        "artifacts": {
            "produces": [
                {"name": "csv"},
            ],
        },
    }

    with pytest.raises(ConfigurationError):
        registry.registry.validate_sink("csv", config)
