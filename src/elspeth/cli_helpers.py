"""CLI helper functions for plugin instantiation."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspeth.core.config import ElspethSettings


def instantiate_plugins_from_config(config: "ElspethSettings") -> dict[str, Any]:
    """Instantiate all plugins from configuration.

    Creates plugin instances BEFORE graph construction,
    enabling schema extraction from instance attributes.

    Args:
        config: Validated ElspethSettings instance

    Returns:
        Dict with keys:
            - source: SourceProtocol instance
            - transforms: list[TransformProtocol] (row_plugins only)
            - sinks: dict[str, SinkProtocol]
            - aggregations: dict[str, tuple[TransformProtocol, AggregationSettings]]

    Raises:
        ValueError: If config references unknown plugins (raised by PluginManager)
    """
    from elspeth.cli import _get_plugin_manager

    manager = _get_plugin_manager()

    # Instantiate source (raises on unknown plugin)
    source_cls = manager.get_source_by_name(config.source.plugin)
    source = source_cls(dict(config.source.options))

    # Instantiate transforms
    transforms = []
    for plugin_config in config.transforms:
        transform_cls = manager.get_transform_by_name(plugin_config.plugin)
        transforms.append(transform_cls(dict(plugin_config.options)))

    # Instantiate aggregations
    aggregations = {}
    for agg_config in config.aggregations:
        transform_cls = manager.get_transform_by_name(agg_config.plugin)
        transform = transform_cls(dict(agg_config.options))
        aggregations[agg_config.name] = (transform, agg_config)

    # Instantiate sinks
    sinks = {}
    for sink_name, sink_config in config.sinks.items():
        sink_cls = manager.get_sink_by_name(sink_config.plugin)
        sinks[sink_name] = sink_cls(dict(sink_config.options))

    return {
        "source": source,
        "transforms": transforms,
        "sinks": sinks,
        "aggregations": aggregations,
    }
