# Plugin Instantiation Audit

**Date:** 2026-01-25
**Audit Scope:** All direct plugin instantiation in src/elspeth/

## Production Code Instantiation Sites

### Sources

```
src/elspeth/cli.py:1361:        null_source = NullSource({})
src/elspeth/cli.py:365:    source_cls = manager.get_source_by_name(source_plugin)
src/elspeth/cli.py:366:    source = source_cls(source_options)
src/elspeth/cli_helpers.py:33:    source_cls = manager.get_source_by_name(config.datasource.plugin)
src/elspeth/cli_helpers.py:34:    source = source_cls(dict(config.datasource.options))
```

- Total: 3 sites
- Files affected: cli.py, cli_helpers.py

### Transforms

```
src/elspeth/cli.py:388:            transform_cls = manager.get_transform_by_name(plugin_name)
src/elspeth/cli.py:389:            transforms.append(transform_cls(plugin_options))
src/elspeth/cli.py:405:            transform_cls = manager.get_transform_by_name(plugin_name)
src/elspeth/cli.py:409:            transform = transform_cls(agg_options)
src/elspeth/cli_helpers.py:39:        transform_cls = manager.get_transform_by_name(plugin_config.plugin)
src/elspeth/cli_helpers.py:40:        transforms.append(transform_cls(dict(plugin_config.options)))
src/elspeth/cli_helpers.py:45:        transform_cls = manager.get_transform_by_name(agg_config.plugin)
src/elspeth/cli_helpers.py:46:        transform = transform_cls(dict(agg_config.options))
```

- Total: 4 sites
- Files affected: cli.py, cli_helpers.py

### Gates

No instantiation sites found (gates are config-driven).

- Total: 0 sites
- Files affected: none

### Sinks

```
src/elspeth/cli.py:374:        sink_cls = manager.get_sink_by_name(sink_plugin)
src/elspeth/cli.py:375:        sinks[sink_name] = sink_cls(sink_options)
src/elspeth/cli_helpers.py:52:        sink_cls = manager.get_sink_by_name(sink_config.plugin)
src/elspeth/cli_helpers.py:53:        sinks[sink_name] = sink_cls(dict(sink_config.options))
```

- Total: 2 sites
- Files affected: cli.py, cli_helpers.py

## Summary

- **Total production instantiation sites:** 9
- **Files requiring updates:** 2 (cli.py, cli_helpers.py)
- **Test instantiation sites:** 224 (will continue to work)

## Migration Strategy

Phase 2 will update production sites to use PluginManager.create_*()
Test sites continue using direct instantiation (correct pattern)
