"""Configuration validation guards for secure mode enforcement.

This module provides high-level validation functions that enforce security
requirements based on the active secure mode (STRICT, STANDARD, DEVELOPMENT).

These validators are designed to be called during configuration loading to
ensure all plugin configurations meet security requirements before instantiation.
"""

import logging
from typing import Any, Mapping

from elspeth.core.security.secure_mode import (
    SecureMode,
    get_secure_mode,
    validate_datasource_config,
    validate_llm_config,
    validate_middleware_config,
    validate_sink_config,
)
from elspeth.core.validation_base import ConfigurationError

logger = logging.getLogger(__name__)


def validate_full_configuration(
    profile_data: Mapping[str, Any],
    mode: SecureMode | None = None,
) -> None:
    """Validate entire configuration according to secure mode requirements.

    This is the main entry point for configuration validation. It validates
    datasources, LLMs, sinks, and middleware configurations.

    Args:
        profile_data: Full profile configuration dictionary
        mode: Secure mode (auto-detected if None)

    Raises:
        ConfigurationError: If configuration violates secure mode requirements

    Examples:
        >>> config = {
        ...     "datasource": {"type": "local_csv", "path": "data.csv"},
        ...     "llm": {"type": "azure_openai", "endpoint": "https://api.openai.com"},
        ...     "sinks": [{"type": "csv", "path": "output.csv"}]
        ... }
        >>> validate_full_configuration(config)  # doctest: +SKIP
        Traceback (most recent call last):
        ...
        ConfigurationError: Datasource missing required 'security_level' (STANDARD mode)
    """
    if mode is None:
        mode = get_secure_mode()

    logger.info(f"Validating configuration in {mode.value.upper()} mode")

    # Validate datasource
    datasource_config = profile_data.get("datasource")
    if datasource_config:
        if not isinstance(datasource_config, Mapping):
            raise ConfigurationError("Datasource configuration must be a mapping")
        try:
            validate_datasource_config(dict(datasource_config), mode=mode)
        except ValueError as exc:
            raise ConfigurationError(f"Datasource validation failed: {exc}") from exc

    # Validate LLM
    llm_config = profile_data.get("llm")
    if llm_config:
        if not isinstance(llm_config, Mapping):
            raise ConfigurationError("LLM configuration must be a mapping")
        try:
            validate_llm_config(dict(llm_config), mode=mode)
        except ValueError as exc:
            raise ConfigurationError(f"LLM validation failed: {exc}") from exc

    # Validate sinks
    sinks_config = profile_data.get("sinks", [])
    if sinks_config and isinstance(sinks_config, list):
        for idx, sink_config in enumerate(sinks_config):
            if not isinstance(sink_config, Mapping):
                raise ConfigurationError(f"Sink[{idx}] configuration must be a mapping")
            try:
                validate_sink_config(dict(sink_config), mode=mode)
            except ValueError as exc:
                raise ConfigurationError(f"Sink[{idx}] validation failed: {exc}") from exc

    # Validate middleware
    middleware_config = profile_data.get("llm_middlewares", [])
    if middleware_config and isinstance(middleware_config, list):
        try:
            validate_middleware_config(
                [dict(mw) if isinstance(mw, Mapping) else {} for mw in middleware_config],
                mode=mode,
            )
        except ValueError as exc:
            raise ConfigurationError(f"Middleware validation failed: {exc}") from exc


def validate_plugin_definition(
    definition: Mapping[str, Any],
    plugin_type: str,
    mode: SecureMode | None = None,
) -> None:
    """Validate a single plugin definition according to secure mode.

    Args:
        definition: Plugin configuration dictionary
        plugin_type: Type of plugin ('datasource', 'llm', 'sink', etc.)
        mode: Secure mode (auto-detected if None)

    Raises:
        ConfigurationError: If plugin definition violates secure mode requirements

    Examples:
        >>> definition = {"type": "local_csv", "path": "data.csv", "security_level": "OFFICIAL"}
        >>> validate_plugin_definition(definition, "datasource")  # doctest: +SKIP
    """
    if mode is None:
        mode = get_secure_mode()

    # Merge plugin-level and options-level configuration
    options = dict(definition.get("options", {}) or {})
    merged_config = dict(definition)
    merged_config.update(options)

    try:
        if plugin_type == "datasource":
            validate_datasource_config(merged_config, mode=mode)
        elif plugin_type == "llm":
            validate_llm_config(merged_config, mode=mode)
        elif plugin_type == "sink":
            validate_sink_config(merged_config, mode=mode)
        else:
            # Unknown plugin type - no specific validation
            logger.debug(f"No specific validation for plugin type: {plugin_type}")
    except ValueError as exc:
        raise ConfigurationError(
            f"Plugin '{plugin_type}' validation failed: {exc}"
        ) from exc


def validate_suite_configuration(
    suite_config: Mapping[str, Any],
    mode: SecureMode | None = None,
) -> None:
    """Validate suite-level configuration including experiments and defaults.

    Args:
        suite_config: Suite configuration dictionary
        mode: Secure mode (auto-detected if None)

    Raises:
        ConfigurationError: If suite configuration violates secure mode requirements
    """
    if mode is None:
        mode = get_secure_mode()

    logger.info(f"Validating suite configuration in {mode.value.upper()} mode")

    # Validate suite defaults if present
    suite_defaults = suite_config.get("suite_defaults")
    if suite_defaults and isinstance(suite_defaults, Mapping):
        validate_full_configuration(dict(suite_defaults), mode=mode)

    # Validate each experiment configuration
    experiments = suite_config.get("experiments", [])
    if experiments and isinstance(experiments, list):
        for idx, exp_config in enumerate(experiments):
            if not isinstance(exp_config, Mapping):
                continue

            # Check for datasource override
            if "datasource" in exp_config:
                datasource_config = exp_config["datasource"]
                if isinstance(datasource_config, Mapping):
                    try:
                        validate_datasource_config(dict(datasource_config), mode=mode)
                    except ValueError as exc:
                        raise ConfigurationError(
                            f"Experiment[{idx}] datasource validation failed: {exc}"
                        ) from exc

            # Check for LLM override
            if "llm" in exp_config:
                llm_config = exp_config["llm"]
                if isinstance(llm_config, Mapping):
                    try:
                        validate_llm_config(dict(llm_config), mode=mode)
                    except ValueError as exc:
                        raise ConfigurationError(
                            f"Experiment[{idx}] LLM validation failed: {exc}"
                        ) from exc

            # Check for sinks override
            if "sinks" in exp_config:
                sinks_config = exp_config["sinks"]
                if isinstance(sinks_config, list):
                    for sink_idx, sink_config in enumerate(sinks_config):
                        if isinstance(sink_config, Mapping):
                            try:
                                validate_sink_config(dict(sink_config), mode=mode)
                            except ValueError as exc:
                                raise ConfigurationError(
                                    f"Experiment[{idx}] Sink[{sink_idx}] validation failed: {exc}"
                                ) from exc


def validate_prompt_pack(
    pack_config: Mapping[str, Any],
    mode: SecureMode | None = None,
) -> None:
    """Validate prompt pack configuration.

    Args:
        pack_config: Prompt pack configuration dictionary
        mode: Secure mode (auto-detected if None)

    Raises:
        ConfigurationError: If prompt pack violates secure mode requirements
    """
    if mode is None:
        mode = get_secure_mode()

    logger.debug(f"Validating prompt pack in {mode.value.upper()} mode")

    # Validate sinks if present in pack
    sinks_config = pack_config.get("sinks", [])
    if sinks_config and isinstance(sinks_config, list):
        for idx, sink_config in enumerate(sinks_config):
            if isinstance(sink_config, Mapping):
                try:
                    validate_sink_config(dict(sink_config), mode=mode)
                except ValueError as exc:
                    raise ConfigurationError(
                        f"Prompt pack Sink[{idx}] validation failed: {exc}"
                    ) from exc

    # Validate middleware if present in pack
    middleware_config = pack_config.get("llm_middlewares", [])
    if middleware_config and isinstance(middleware_config, list):
        try:
            validate_middleware_config(
                [dict(mw) if isinstance(mw, Mapping) else {} for mw in middleware_config],
                mode=mode,
            )
        except ValueError as exc:
            raise ConfigurationError(f"Prompt pack middleware validation failed: {exc}") from exc


__all__ = [
    "validate_full_configuration",
    "validate_plugin_definition",
    "validate_suite_configuration",
    "validate_prompt_pack",
]
