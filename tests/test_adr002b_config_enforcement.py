"""Test ADR-002-B: security_level rejection in configuration layer."""

import pytest
from pathlib import Path
from elspeth.config import load_settings
from elspeth.core.validation.base import ConfigurationError


def test_config_rejects_datasource_security_level(tmp_path: Path) -> None:
    """ADR-002-B: config.py rejects security_level in datasource definition."""
    config = tmp_path / "settings.yaml"
    config.write_text("""
default:
  datasource:
    plugin: local_csv
    security_level: SECRET
    options:
      path: data.csv
      retain_local: false
  llm:
    plugin: mock
  sinks: []
""")

    with pytest.raises(ConfigurationError, match="security_level cannot be specified.*ADR-002-B"):
        load_settings(config)


def test_config_rejects_llm_security_level(tmp_path: Path) -> None:
    """ADR-002-B: config.py rejects security_level in LLM definition."""
    config = tmp_path / "settings.yaml"
    config.write_text("""
default:
  datasource:
    plugin: local_csv
    options:
      path: data.csv
      retain_local: false
  llm:
    plugin: mock
    security_level: PROTECTED
  sinks: []
""")

    with pytest.raises(ConfigurationError, match="security_level cannot be specified.*ADR-002-B"):
        load_settings(config)


def test_config_rejects_sink_security_level(tmp_path: Path) -> None:
    """ADR-002-B: config.py rejects security_level in sink definition."""
    config = tmp_path / "settings.yaml"
    config.write_text("""
default:
  datasource:
    plugin: local_csv
    options:
      path: data.csv
      retain_local: false
  llm:
    plugin: mock
  sinks:
    - plugin: csv
      security_level: SECRET
      options:
        path: output.csv
""")

    with pytest.raises(ConfigurationError, match="security_level cannot be specified.*ADR-002-B"):
        load_settings(config)


def test_config_rejects_security_level_in_options(tmp_path: Path) -> None:
    """ADR-002-B: config.py rejects security_level in options dict."""
    config = tmp_path / "settings.yaml"
    config.write_text("""
default:
  datasource:
    plugin: local_csv
    options:
      path: data.csv
      retain_local: false
      security_level: SECRET
  llm:
    plugin: mock
  sinks: []
""")

    with pytest.raises(ConfigurationError, match="security_level cannot be specified.*ADR-002-B"):
        load_settings(config)


def test_determinism_level_still_accepted(tmp_path: Path) -> None:
    """ADR-002-B: determinism_level is user-configurable (still accepted)."""
    config = tmp_path / "settings.yaml"
    config.write_text("""
default:
  datasource:
    plugin: local_csv
    determinism_level: guaranteed
    options:
      path: data.csv
      retain_local: false
  llm:
    plugin: mock
  sinks: []
""")

    # Should not raise
    settings = load_settings(config)
    assert settings.datasource is not None
