## Summary

`PipelineConfig.__post_init__()` only shallow-freezes `config`, so nested dictionaries/lists remain mutable even though the type promises run-time immutability; because that same config object is both audited and passed to plugins, a plugin can mutate effective run configuration after the audit snapshot is recorded.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/orchestrator/types.py
- Line(s): 88-100, especially 97
- Function/Method: `PipelineConfig.__post_init__`

## Evidence

`PipelineConfig` explicitly promises immutable run configuration:

```python
# /home/john/elspeth/src/elspeth/engine/orchestrator/types.py:64-68
Frozen after construction — pipeline
configuration must not change during execution.
```

But the implementation only wraps the top-level mapping:

```python
# /home/john/elspeth/src/elspeth/engine/orchestrator/types.py:95-100
object.__setattr__(self, "transforms", tuple(self.transforms))
object.__setattr__(self, "sinks", MappingProxyType(dict(self.sinks)))
object.__setattr__(self, "config", MappingProxyType(dict(self.config)))
object.__setattr__(self, "gates", tuple(self.gates))
object.__setattr__(self, "aggregation_settings", MappingProxyType(dict(self.aggregation_settings)))
object.__setattr__(self, "coalesce_settings", tuple(self.coalesce_settings))
```

`MappingProxyType(dict(...))` is shallow only. The project’s freeze utility exists specifically to prevent this:

```python
# /home/john/elspeth/src/elspeth/contracts/freeze.py:23-27, 80-87
def deep_freeze(value: Any) -> Any:
    """Recursively freeze mutable containers."""

def freeze_fields(instance: object, *field_names: str) -> None:
    """Freeze named container fields on a frozen dataclass instance."""
```

The config passed into `PipelineConfig` is normal nested JSON-like data from `model_dump(mode="json")`:

```python
# /home/john/elspeth/src/elspeth/core/config.py:2084-2086
config_dict = settings.model_dump(mode="json")
return _fingerprint_config_for_audit(config_dict)
```

That same `PipelineConfig.config` object is then used for both audit recording and runtime plugin access:

```python
# /home/john/elspeth/src/elspeth/engine/orchestrator/core.py:1008-1014
run = recorder.begin_run(
    config=config.config,
    canonical_version=self._canonical_version,
    ...
)

# /home/john/elspeth/src/elspeth/engine/orchestrator/core.py:1543-1546
ctx = PluginContext(
    run_id=run_id,
    config=config.config,
    landscape=recorder,
    ...
)
```

`begin_run()` hashes and persists the config immediately:

```python
# /home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py:86-89
settings_json = canonical_json(config)
config_hash = stable_hash(config)
```

So if a nested structure like `ctx.config["telemetry"]["exporters"]` or `ctx.config["source"]["options"]` is mutated later, the live behavior diverges from the recorded `settings_json`/`config_hash`. The existing tests only verify top-level immutability (`MappingProxyType`/tuple), not nested immutability:

```python
# /home/john/elspeth/tests/unit/engine/orchestrator/test_types.py:303-320
assert isinstance(config.config, MappingProxyType)
with pytest.raises(TypeError):
    config.config["new"] = "value"
```

They never assert that nested values are frozen.

## Root Cause Hypothesis

`PipelineConfig` was converted to a frozen dataclass, but its `__post_init__()` uses hand-rolled shallow wrappers instead of the repository’s required deep-freeze pattern. That preserves top-level assignment safety while leaving nested runtime config mutable through shared references. Because the same object is reused for audit storage and plugin execution, the shallow freeze creates audit/runtime drift.

## Suggested Fix

Deep-freeze the `config` field in `PipelineConfig.__post_init__()` instead of wrapping it with `MappingProxyType(dict(...))`. For example:

```python
from elspeth.contracts.freeze import freeze_fields

def __post_init__(self) -> None:
    if not self.sinks:
        ...
    object.__setattr__(self, "transforms", tuple(self.transforms))
    object.__setattr__(self, "sinks", MappingProxyType(dict(self.sinks)))
    object.__setattr__(self, "gates", tuple(self.gates))
    object.__setattr__(self, "aggregation_settings", MappingProxyType(dict(self.aggregation_settings)))
    object.__setattr__(self, "coalesce_settings", tuple(self.coalesce_settings))
    freeze_fields(self, "config")
```

Also add a regression test that mutating a nested value from the original input dict after `PipelineConfig` construction does not change `config.config`, and that nested mutation through `config.config` raises.

## Impact

A plugin or orchestrator helper can mutate nested runtime config after the run’s `settings_json` and `config_hash` have already been recorded. That breaks the audit guarantee that the stored configuration fully explains the decisions made during the run. In a formal inquiry, ELSPETH could show a configuration snapshot that no longer matches the one actually used to process rows.
