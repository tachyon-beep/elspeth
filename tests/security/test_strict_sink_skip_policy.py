import os

import pytest

from elspeth.core.security.secure_mode import SecureMode, validate_sink_config


@pytest.mark.parametrize(
    "sink_cfg",
    [
        {"type": "csv", "path": "out.csv", "security_level": "OFFICIAL", "on_error": "skip"},
        {"type": "github_repo", "security_level": "OFFICIAL", "on_error": "skip"},
    ],
)
def test_strict_mode_disallows_skip_on_error(monkeypatch, sink_cfg):
    monkeypatch.setenv("ELSPETH_SECURE_MODE", SecureMode.STRICT.value)
    with pytest.raises(ValueError, match="on_error='skip' is not permitted"):
        validate_sink_config(dict(sink_cfg), mode=SecureMode.STRICT)
