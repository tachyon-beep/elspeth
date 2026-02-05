# Analysis: src/elspeth/plugins/config_base.py

**Lines:** 397
**Role:** Base Pydantic configuration models for all plugin types. Provides a class hierarchy (PluginConfig -> DataPluginConfig -> PathConfig -> SourceDataConfig -> TabularSourceDataConfig, SinkPathConfig, TransformDataConfig) that validates plugin-specific YAML settings. Handles schema config extraction, path resolution, field normalization options, header output modes, and error routing.
**Key dependencies:** Imports from `elspeth.contracts.header_modes` (HeaderMode, parse_header_mode), `elspeth.contracts.schema` (SchemaConfig), `elspeth.core.identifiers` (validate_field_names). Imported by virtually every plugin implementation (sources, transforms, sinks, LLM plugins) and by `validation.py`.
**Analysis depth:** FULL

## Summary

This file is well-structured and follows the project's conventions. The class hierarchy is clear and serves the config-driven schema pattern well. The most significant concern is the retention of legacy backwards-compatibility fields (`display_headers`, `restore_source_headers`) in `SinkPathConfig`, which directly violates the project's No Legacy Code Policy. There is also a minor inconsistency in how `SinkPathConfig` and `TabularSourceDataConfig` are not re-exported from `plugins/__init__.py` despite being used by downstream plugins.

## Critical Findings

No critical findings that would cause production incidents.

## Warnings

### [201-322] SinkPathConfig retains legacy backwards-compatibility fields

**What:** `SinkPathConfig` maintains three parallel header configuration mechanisms: the new `headers` field (lines 230-233), and two legacy fields: `display_headers` (lines 235-238) and `restore_source_headers` (lines 240-243). The docstring explicitly labels these as "Legacy Options (for backwards compatibility)" (line 214) and describes a priority system where legacy options are honored when the new `headers` field is not set.

**Why it matters:** The project's CLAUDE.md has an explicit "No Legacy Code Policy" section that states: "Legacy code, backwards compatibility, and compatibility shims are strictly forbidden." and "Backwards Compatibility Code ... No feature flags for old behavior ... No 'compatibility mode' switches." The `_validate_display_options` method (lines 265-284) is a textbook compatibility shim -- it validates legacy options and the `headers_mode` property (lines 286-305) implements a priority cascade between new and legacy fields. This is exactly the pattern CLAUDE.md prohibits.

Furthermore, the legacy fields propagate extensively into sink implementations. CSVSink, JSONSink, and AzureBlobSink all have parallel code paths for `_display_headers`, `_restore_source_headers`, and `_resolved_display_headers` alongside the newer contract-based header resolution, creating significant maintenance burden and potential for divergence between the two paths.

**Evidence:**
```python
# Line 214-227: Explicit "Legacy Options" documentation
# Legacy Options (for backwards compatibility):
#     display_headers: Explicit mapping...
#     restore_source_headers: Flag to restore...
# Priority Order (highest to lowest):
#     1. headers (if specified)
#     2. restore_source_headers (legacy, maps to ORIGINAL)
#     3. display_headers (legacy, maps to CUSTOM)
```

### [115] PathConfig.path field lacks filesystem traversal protection

**What:** The `path` field in `PathConfig` validates only that the path is non-empty (line 119-123). The `resolved_path` method (lines 125-138) does path resolution relative to a base directory but does not validate against directory traversal attacks (e.g., `../../etc/passwd`) or symlink attacks.

**Why it matters:** While plugins are system-owned code and YAML configs are operator-controlled (not user input), the path is still external configuration (Tier 3 in the trust model). A misconfigured or adversarial YAML file could cause a source to read from or a sink to write to arbitrary filesystem locations. The `resolved_path` method joins user-provided paths with `base_dir` without canonicalizing or checking that the result is within the expected directory tree.

**Evidence:**
```python
def resolved_path(self, base_dir: Path | None = None) -> Path:
    p = Path(self.path)
    if base_dir and not p.is_absolute():
        return base_dir / p  # "../../../etc/passwd" would traverse out
    return p
```

## Observations

### [46-76] PluginConfig.from_dict schema extraction is well-designed

The `from_dict` factory method correctly extracts the `schema` key from config, validates it is a dict, converts it to `SchemaConfig`, and wraps Pydantic validation errors in `PluginConfigError`. The type guard on line 65 (`if not isinstance(schema_dict, dict)`) is appropriate defensive validation at a config boundary.

### [162-198] TabularSourceDataConfig normalization validation is thorough

The model validator correctly enforces that `normalize_fields + columns` is invalid, that `field_mapping` requires either `normalize_fields` or `columns`, and validates both column names and field mapping values as valid identifiers. The deferred import of `validate_field_names` avoids circular dependencies.

### [355-397] TransformDataConfig.validate_required_input_fields preserves semantic distinction

The validator correctly preserves the semantic distinction between `None` (not specified), `[]` (explicit opt-out), and `[fields...]` (explicit declaration). This three-way semantics is documented and important for LLM transforms that may intentionally accept runtime risk.

### [42-43] SinkPathConfig and TabularSourceDataConfig not re-exported from __init__.py

`SinkPathConfig` and `TabularSourceDataConfig` are used by downstream plugins (csv_sink, json_sink, csv_source) but are not re-exported from `plugins/__init__.py`. This is inconsistent with other config base classes (`DataPluginConfig`, `PathConfig`, `SourceDataConfig`, `TransformDataConfig`) which are re-exported. While not a bug (plugins import directly from `config_base`), it creates an inconsistent public API surface.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Remove the legacy `display_headers` and `restore_source_headers` fields from `SinkPathConfig` per the No Legacy Code Policy. Migrate all sink implementations to use the unified `headers` field exclusively. The path traversal concern is lower priority but worth addressing with a `resolved_path` that validates the result stays within the base directory.
**Confidence:** HIGH -- the legacy code violation is clear and well-documented by the code itself. The path traversal risk is contextual (operator-controlled config reduces severity).
