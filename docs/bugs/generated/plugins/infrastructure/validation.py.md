## Summary

Built-in plugin validation is driven by stale hard-coded name maps, so registered plugins `dataverse`, `chroma_sink`, and `rag_retrieval` are treated as unknown or config-less by the validation subsystem.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/validation.py
- Line(s): 92-117, 230-309, 311-335
- Function/Method: `_get_source_config_model`, `_get_transform_config_model`, `_get_sink_config_model`

## Evidence

`PluginConfigValidator` hard-codes supported plugin names:

```python
# validation.py
if source_type == "csv": ...
elif source_type == "json": ...
elif source_type == "azure_blob": ...
elif source_type == "null": ...
else:
    raise ValueError(f"Unknown source type: {source_type}")
```

Equivalent hard-coded chains exist for transforms and sinks at [validation.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/validation.py#L230) and [validation.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/validation.py#L311).

But discovery and registration say these plugins are built-in:

- [test_discovery.py](/home/john/elspeth/tests/unit/plugins/test_discovery.py#L247) expects source count `5` including `dataverse`.
- [test_discovery.py](/home/john/elspeth/tests/unit/plugins/test_discovery.py#L249) expects transform count including `rag_retrieval`.
- [test_discovery.py](/home/john/elspeth/tests/unit/plugins/test_discovery.py#L251) expects sink count including `dataverse` and `chroma_sink`.
- [dataverse.py](/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py#L191) defines source `name = "dataverse"`.
- [transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/rag/transform.py#L57) defines transform `name = "rag_retrieval"`.
- [dataverse.py](/home/john/elspeth/src/elspeth/plugins/sinks/dataverse.py#L150) defines sink `name = "dataverse"`.
- [chroma_sink.py](/home/john/elspeth/src/elspeth/plugins/sinks/chroma_sink.py#L123) defines sink `name = "chroma_sink"`.

Integration behavior confirms the validator is on the creation path for manager-backed callers:

- [manager.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L221) calls `validate_source_config(...)` before `create_source(...)`.
- [manager.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L248) calls `validate_transform_config(...)`.
- [manager.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/manager.py#L275) calls `validate_sink_config(...)`.

So `PluginManager.create_source("dataverse", ...)`, `create_transform("rag_retrieval", ...)`, and `create_sink("dataverse"/"chroma_sink", ...)` fail in validation even though those plugins are registered.

The catalog path is also broken. [service.py](/home/john/elspeth/src/elspeth/web/catalog/service.py#L139) explicitly documents that plugins like `dataverse` are “not yet wired into PluginConfigValidator's mapping”, and [service.py](/home/john/elspeth/src/elspeth/web/catalog/service.py#L155) converts that `ValueError` into `None`, causing `get_schema()` to return `{}` instead of the real config schema.

## Root Cause Hypothesis

The validator duplicates plugin discovery knowledge in manual `if/elif` tables. New plugins were added to discovery/registration, but the parallel validation map was not updated. Because the validator is now a separate subsystem, it has drifted from the plugin registry.

## Suggested Fix

Replace the hand-maintained maps with a single source of truth.

Good options:

```python
# Example direction
SOURCE_CONFIG_MODELS = {
    "csv": CSVSourceConfig,
    "json": JSONSourceConfig,
    "azure_blob": AzureBlobSourceConfig,
    "dataverse": DataverseSourceConfig,
    "null": None,
}
```

or better, expose a public “config model for plugin class” API from discovery/registration and derive the model from the registered plugin class rather than duplicating names here.

At minimum, add the missing entries:

- source: `dataverse`
- transform: `rag_retrieval`
- sink: `dataverse`, `chroma_sink`

Also add validator-facing tests that iterate all registered plugin names and assert their config models resolve.

## Impact

Manager-backed validation and catalog/schema introspection are inconsistent with actual plugin registration. Valid built-in plugins can be rejected as “unknown,” and catalog consumers can receive empty schemas for real plugins. This breaks configuration UX and can block any integration that relies on `PluginManager.create_*()` or the web catalog to validate/configure those plugins.
