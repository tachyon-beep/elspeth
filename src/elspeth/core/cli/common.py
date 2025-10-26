"""Shared CLI helpers for artifact directories and publishing.

This module contains small utilities used by multiple CLI commands to:
- create timestamped artifact directories
- persist simple artifact files (results and settings snapshot)
- load YAML configs for artifact sinks
- optionally build a signed reproducibility bundle
- optionally publish bundles via a configured artifact sink
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

import elspeth.core.registries.sink as sink_reg
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.types import SecurityLevel
from elspeth.core.registries.sink import CAP_SUPPORTS_FOLDER_PATH_INJECTION
from elspeth.core.validation.base import ConfigurationError

# Optional sink; not required for all CLI flows
try:
    _repro_mod = importlib.import_module("elspeth.plugins.nodes.sinks.reproducibility_bundle")
    ReproBundleSinkCls = getattr(_repro_mod, "ReproducibilityBundleSink", None)
except Exception:  # pragma: no cover - optional dependency pattern
    ReproBundleSinkCls = None

logger = logging.getLogger(__name__)


def ensure_artifacts_dir(base: Path | None) -> Path:
    """Create and return a timestamped artifacts directory under ``base``.

    When ``base`` is None, use a default ``artifacts/`` root in the CWD.
    """
    ts = pd.Timestamp.utcnow().strftime("%Y%m%dT%H%M%SZ")
    root = base if base else Path("artifacts")
    path = root / ts
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_simple_artifacts(art_dir: Path, name: str, payload: dict[str, Any], settings: Any) -> None:
    """Write a results JSON and a settings YAML snapshot into ``art_dir``.

    - ``{name}_results.json`` contains the provided ``payload``.
    - ``{name}_settings.yaml`` mirrors the original config file when available.
    """
    # Results JSON
    (art_dir / f"{name}_results.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    # Settings YAML snapshot
    try:
        cfg_path = Path(getattr(settings, "config_path", ""))
        if cfg_path and cfg_path.exists():
            dest = art_dir / f"{name}_settings.yaml"
            dest.write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
    except (OSError, UnicodeError):
        logger.debug("Failed to copy settings file", exc_info=True)


def load_yaml_json(path: Path) -> dict[str, Any]:
    """Load a YAML file as a dict for artifact sink configuration.

    Raises ``ValueError`` for invalid files or parse errors.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        raise ValueError("artifact sink config must be a mapping")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Invalid artifact sink config: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid artifact sink config: {exc}") from exc


def create_signed_bundle(
    art_dir: Path,
    name: str,
    payload: dict[str, Any],
    settings: Any,
    df: pd.DataFrame,
    *,
    signing_key_env: str,
    operating_level: SecurityLevel | str | None = None,
) -> Path | None:
    """Create a signed reproducibility bundle if the sink is available.

    Args:
        operating_level: Pipeline operating level (ADR-002) - required for audit trail

    Returns the output directory path on success, otherwise ``None``.
    """
    if ReproBundleSinkCls is None:  # pragma: no cover - optional
        logger.warning("Reproducibility bundle sink unavailable; skipping bundle creation")
        return None
    bundle_dir = art_dir / f"{name}_bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    sink = ReproBundleSinkCls(
        base_path=str(bundle_dir),
        bundle_name=f"{name}",
        timestamped=False,
        include_framework_code=False,
        key_env=signing_key_env,
    )
    metadata = {
        "security_level": getattr(settings, "security_level", None),
        "operating_level": operating_level,  # ADR-002: Pipeline operating level for artifact publishing
        "datasource_config": getattr(settings, "datasource_config", None),
        "source_data": df,
    }
    try:
        sink.write(payload, metadata=metadata)
        logger.info("Created signed reproducibility bundle at %s", bundle_dir)
        return bundle_dir
    except (OSError, RuntimeError, ValueError) as exc:
        logger.error("Failed to create reproducibility bundle: %s", exc)
        return None


def maybe_publish_artifacts_bundle(
    bundle_dir: Path,
    *,
    plugin_name: str | None,
    config_path: Path | str | None,
    operating_level: SecurityLevel | str | None = None,
) -> None:
    """Publish the bundle via a configured sink if provided.

    The sink is created from ``plugin_name`` and optional configuration at
    ``config_path``. Sinks that support folder publishing may receive the
    ``folder_path`` automatically.

    Args:
        bundle_dir: Path to the signed bundle directory.
        plugin_name: Name of the artifact publisher sink plugin.
        config_path: Path to YAML/JSON configuration for the sink.
        operating_level: Security level at which the bundle was created (pipeline operating level).
            If None, reads from bundle manifest. This MUST match the classification of data in the bundle.
    """
    if not plugin_name:
        return

    # ADR-002-B: Determine operating_level from bundle manifest if not provided
    # Bundles contain classified data at the pipeline's operating level
    if operating_level is None:
        manifest_path = bundle_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                # Try metadata.security_level first (pipeline operating level), then metadata.operating_level
                operating_level = (
                    manifest_data.get("metadata", {}).get("operating_level")
                    or manifest_data.get("metadata", {}).get("security_level")
                )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read bundle manifest for security_level: %s", exc)

        if operating_level is None:
            logger.error("Cannot determine operating_level for artifact bundle - refusing to publish (security risk)")
            return

    cfg_path = Path(config_path) if config_path is not None else None
    opts: dict[str, Any] = {}
    if cfg_path is not None:
        try:
            opts = load_yaml_json(cfg_path)
        except ValueError as exc:
            logger.warning("artifact sink config invalid; skipping publish: %s", exc)
            return
    try:
        capabilities = sink_reg.sink_registry.get_plugin_capabilities(plugin_name)
    except KeyError:
        logger.warning("Unknown artifact sink plugin '%s'; attempting publish without capability hints", plugin_name)
        capabilities = frozenset()
    # Auto-inject folder_path for sinks that advertise capability support
    if CAP_SUPPORTS_FOLDER_PATH_INJECTION in capabilities and not opts.get("folder_path"):
        opts["folder_path"] = str(bundle_dir)

    # ADR-002-B: Create parent_context at bundle's operating level (bundles contain classified data)
    artifact_context = PluginContext(
        plugin_name="cli_artifact_publisher",
        plugin_kind="artifact_sink",
        security_level=operating_level,  # Match the bundle's classification level
        determinism_level="guaranteed",
        provenance=("cli.artifact_publisher",),
    )

    try:
        sink = sink_reg.sink_registry.create(plugin_name, opts, parent_context=artifact_context)
    except (ValueError, ConfigurationError, RuntimeError) as exc:
        logger.warning("Failed to create artifact sink '%s': %s", plugin_name, exc)
        return
    try:
        sink.write({"artifacts": [str(bundle_dir)]}, metadata={"path": str(bundle_dir)})
        logger.info("Published bundle via artifact sink '%s'", plugin_name)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("Artifact publish failed: %s", exc)


__all__ = [
    "ensure_artifacts_dir",
    "write_simple_artifacts",
    "load_yaml_json",
    "create_signed_bundle",
    "maybe_publish_artifacts_bundle",
]
