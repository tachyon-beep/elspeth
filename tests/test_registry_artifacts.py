import pytest

from elspeth.core import registry
from elspeth.core.validation import ConfigurationError


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

    registry.registry.validate_sink("csv", config)


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
        registry.registry.validate_sink("csv", config)
