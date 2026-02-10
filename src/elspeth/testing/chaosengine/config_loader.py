# src/elspeth/testing/chaosengine/config_loader.py
"""Shared configuration loading utilities for chaos testing servers.

Provides YAML preset loading and deep merge for configuration precedence
(CLI > config file > preset > defaults). Each chaos plugin calls these
utilities from its own `load_config()` function.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dicts, with override taking precedence.

    Args:
        base: Base configuration dict.
        override: Override values (takes precedence).

    Returns:
        Merged configuration dict (new dict, does not mutate inputs).
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def list_presets(presets_dir: Path) -> list[str]:
    """List available preset names from a directory.

    Args:
        presets_dir: Path to the directory containing preset YAML files.

    Returns:
        Sorted list of preset names (without .yaml extension).
    """
    if not presets_dir.exists():
        return []
    return sorted(p.stem for p in presets_dir.glob("*.yaml"))


def load_preset(presets_dir: Path, preset_name: str) -> dict[str, Any]:
    """Load a preset configuration by name.

    Args:
        presets_dir: Path to the directory containing preset YAML files.
        preset_name: Name of the preset (e.g., 'gentle', 'stress_aimd').

    Returns:
        Raw configuration dict from the preset YAML.

    Raises:
        FileNotFoundError: If preset does not exist.
        yaml.YAMLError: If preset YAML is malformed.
        ValueError: If preset is not a YAML mapping.
    """
    preset_path = presets_dir / f"{preset_name}.yaml"

    if not preset_path.exists():
        available = list_presets(presets_dir)
        raise FileNotFoundError(f"Preset '{preset_name}' not found. Available presets: {available}")

    with preset_path.open() as f:
        loaded = yaml.safe_load(f)
        if not isinstance(loaded, dict):
            raise ValueError(f"Preset '{preset_name}' must be a YAML mapping, got {type(loaded).__name__}")
        return loaded
