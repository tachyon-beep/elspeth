"""Configuration merge utilities for experiment suite runner.

This module provides helpers to merge configuration from three layers:
1. Suite defaults
2. Prompt pack (optional)
3. Experiment config

The three-layer merge pattern was previously duplicated throughout
build_runner() method, leading to ~100 lines of repetitive code.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar, cast

from elspeth.core.experiments.config import ExperimentConfig

T = TypeVar("T")


class ConfigMerger:
    """Handles three-layer configuration merging for experiment runners.

    This class consolidates the merge logic previously duplicated across
    build_runner() method, reducing complexity and improving maintainability.

    The merge hierarchy (lowest to highest priority):
    1. Suite defaults
    2. Prompt pack (if specified)
    3. Experiment config

    Example:
        >>> merger = ConfigMerger(defaults, pack, config)
        >>> middleware_defs = merger.merge_list("llm_middleware_defs", "llm_middlewares")
        >>> prompt_defaults = merger.merge_dict("prompt_defaults")
        >>> prompt_system = merger.merge_scalar("prompt_system", default="")
    """

    def __init__(
        self,
        defaults: dict[str, Any],
        pack: dict[str, Any] | None,
        config: ExperimentConfig,
    ):
        """Initialize merger with configuration layers.

        Args:
            defaults: Suite-level defaults
            pack: Prompt pack configuration (optional)
            config: Experiment-specific configuration
        """
        self.defaults = defaults
        self.pack = pack
        self.config = config

    def merge_list(
        self,
        key: str,
        *alternative_keys: str,
        transform: Callable[[list[Any]], list[Any]] | None = None,
    ) -> list[Any]:
        """Merge list-valued configuration from all three layers.

        Lists are concatenated (extended) in order: defaults, pack, config.
        This allows each layer to add to the list.

        Args:
            key: Primary configuration key
            *alternative_keys: Alternative keys to check (for backward compat)
            transform: Optional function to transform each source before merging

        Returns:
            Merged list combining all layers

        Example:
            >>> # Merge middleware definitions
            >>> merger.merge_list("llm_middleware_defs", "llm_middlewares")
            [
                {"name": "audit_logger", ...},  # from defaults
                {"name": "prompt_shield", ...}, # from pack
                {"name": "cost_tracker", ...}   # from config
            ]
        """
        result: list[Any] = []

        # Layer 1: Defaults
        for alt_key in [key, *alternative_keys]:
            source = self.defaults.get(alt_key)
            if source:
                items = list(source)
                if transform:
                    items = transform(items)
                result.extend(items)
                break  # Use first matching key

        # Layer 2: Pack
        if self.pack:
            for alt_key in [key, *alternative_keys]:
                source = self.pack.get(alt_key)
                if source:
                    items = list(source)
                    if transform:
                        items = transform(items)
                    result.extend(items)
                    break

        # Layer 3: Config
        config_value = getattr(self.config, key, None)
        if config_value:
            items = list(config_value)
            if transform:
                items = transform(items)
            result.extend(items)

        return result

    def merge_dict(self, key: str, *alternative_keys: str) -> dict[str, Any]:
        """Merge dict-valued configuration from all three layers.

        Dicts are merged via update(), so later layers override earlier ones
        for the same keys. This allows configuration inheritance with overrides.

        Args:
            key: Primary configuration key
            *alternative_keys: Alternative keys to check

        Returns:
            Merged dictionary

        Example:
            >>> # Merge prompt defaults
            >>> merger.merge_dict("prompt_defaults")
            {
                "temperature": 0.7,  # from defaults
                "max_tokens": 1000,  # from pack (overrides defaults if present)
                "top_p": 0.95        # from config (overrides earlier layers)
            }
        """
        result: dict[str, Any] = {}

        # Layer 1: Defaults
        for alt_key in [key, *alternative_keys]:
            source = self.defaults.get(alt_key)
            if source:
                result.update(source)
                break

        # Layer 2: Pack
        if self.pack:
            for alt_key in [key, *alternative_keys]:
                source = self.pack.get(alt_key)
                if source:
                    result.update(source)
                    break

        # Layer 3: Config
        config_value = getattr(self.config, key, None)
        if config_value:
            result.update(config_value)

        return result

    def merge_scalar(
        self,
        key: str,
        *alternative_keys: str,
        default: T | None = None,
    ) -> T | None:
        """Merge scalar-valued configuration (last wins).

        For scalar values, the highest-priority layer that defines the value wins.
        Priority order: config > pack > defaults > default

        Special handling: Empty strings are treated as "not found" for prompt fields
        (prompt_system, prompt_template) to allow defaults to provide values even
        when ExperimentConfig has empty strings from missing prompt files.

        Args:
            key: Primary configuration key
            *alternative_keys: Alternative keys to check
            default: Default value if not found in any layer

        Returns:
            Scalar value from highest-priority layer

        Example:
            >>> # Merge prompt system
            >>> merger.merge_scalar("prompt_system", default="")
            "You are a helpful assistant"  # from config (highest priority)
        """
        # Layer 3 (highest priority): Config
        config_value = getattr(self.config, key, None)
        # Special case: treat empty strings as "not found" for prompt fields
        # This allows defaults to provide prompts even when config has "" from missing files
        if config_value is not None and config_value != "":
            return cast(T, config_value)

        # Layer 2: Pack
        if self.pack:
            for alt_key in [key, *alternative_keys]:
                pack_value = self.pack.get(alt_key)
                if pack_value is not None and pack_value != "":
                    return cast(T, pack_value)

        # Layer 1: Defaults
        for alt_key in [key, *alternative_keys]:
            default_value = self.defaults.get(alt_key)
            if default_value is not None and default_value != "":
                return cast(T, default_value)

        # Fallback: Default
        return default

    def merge_plugin_definitions(
        self,
        def_key: str,
        pack_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Merge plugin definitions (specialized list merge for plugins).

        Plugin definitions follow a specific pattern:
        - Defaults use "{type}_plugin_defs" key
        - Pack uses "{type}_plugins" key (different!)
        - Config uses "{type}_plugin_defs" key
        - Pack plugins are prepended to defaults (unusual priority)

        Args:
            def_key: Definition key (e.g., "row_plugin_defs")
            pack_key: Pack key (e.g., "row_plugins"), defaults to strip "_defs"

        Returns:
            Merged list of plugin definitions

        Example:
            >>> merger.merge_plugin_definitions("row_plugin_defs", "row_plugins")
            [
                {"name": "score_extractor", ...},  # from pack (prepended!)
                {"name": "cost_analyzer", ...},    # from defaults
                {"name": "custom_metric", ...}     # from config (appended)
            ]
        """
        if pack_key is None:
            # Default: "row_plugin_defs" -> "row_plugins"
            pack_key = def_key.replace("_plugin_defs", "_plugins").replace("_defs", "s")

        result: list[dict[str, Any]] = []

        # Layer 1: Defaults
        result.extend(list(self.defaults.get(def_key, [])))

        # Layer 2: Pack (PREPENDED to defaults - unusual!)
        if self.pack and self.pack.get(pack_key):
            # Note: Pack plugins come BEFORE defaults
            result = list(self.pack.get(pack_key, [])) + result

        # Layer 3: Config (appended)
        config_value = getattr(self.config, def_key, None)
        if config_value:
            result.extend(config_value)

        return result


__all__ = ["ConfigMerger"]
