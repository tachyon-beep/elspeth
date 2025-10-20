from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def ensure_artifacts_dir(base: Path | None) -> Path:
    ts = pd.Timestamp.utcnow().strftime("%Y%m%dT%H%M%SZ")
    root = base if base else Path("artifacts")
    path = root / ts
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_simple_artifacts(art_dir: Path, name: str, payload: dict[str, Any], settings: Any) -> None:
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
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - PyYAML should be present in CLI env
        raise ValueError("PyYAML is required to load artifact sink configs") from exc

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
) -> Path | None:
    try:
        from elspeth.plugins.nodes.sinks.reproducibility_bundle import ReproducibilityBundleSink
    except ImportError as exc:  # pragma: no cover - optional import
        logger.warning("Reproducibility bundle unavailable: %s", exc)
        return
    bundle_dir = art_dir / f"{name}_bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    sink = ReproducibilityBundleSink(
        base_path=str(bundle_dir),
        bundle_name=f"{name}",
        timestamped=False,
        include_framework_code=False,
        key_env=signing_key_env,
    )
    metadata = {
        "security_level": getattr(settings, "security_level", None),
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
) -> None:
    import elspeth.core.registries.sink as sink_reg

    if not plugin_name:
        return

    cfg_path = Path(config_path) if config_path is not None else None
    opts: dict[str, Any] = {}
    if cfg_path is not None:
        try:
            opts = load_yaml_json(cfg_path)
        except ValueError as exc:
            logger.warning("artifact sink config invalid; skipping publish: %s", exc)
            return
    if plugin_name == "azure_devops_artifact_repo" and not opts.get("folder_path"):
        opts["folder_path"] = str(bundle_dir)
    try:
        from elspeth.core.validation.base import ConfigurationError as configuration_error  # local import to avoid cycles
    except ImportError:  # pragma: no cover - defensive
        configuration_error = RuntimeError  # type: ignore
    try:
        sink = sink_reg.sink_registry.create(plugin_name, opts, parent_context=None)
    except (ValueError, configuration_error, RuntimeError) as exc:
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
