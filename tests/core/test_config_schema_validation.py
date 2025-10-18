import pytest

from elspeth.core.config.schema import validate_experiment_config
from elspeth.core.validation.base import ConfigurationError


def test_experiment_config_valid_minimal():
    cfg = {"name": "exp1", "temperature": 0.2, "max_tokens": 256, "enabled": True}
    # Should not raise
    validate_experiment_config(cfg)


@pytest.mark.parametrize(
    "bad_cfg",
    [
        {},
        {"name": "exp", "max_tokens": 256, "enabled": True},
        {"name": "exp", "temperature": 0.5, "enabled": True},
        {"name": "exp", "temperature": -0.1, "max_tokens": 256, "enabled": True},
        {"name": "exp", "temperature": 0.5, "max_tokens": 0, "enabled": True},
    ],
)
def test_experiment_config_invalid_cases(bad_cfg):
    with pytest.raises(ConfigurationError):
        validate_experiment_config(bad_cfg)
