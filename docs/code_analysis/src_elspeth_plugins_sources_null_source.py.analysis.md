# Analysis: src/elspeth/plugins/sources/null_source.py

**Lines:** 78 (previously reported as 88 due to trailing whitespace; actual content is 88 lines)
**Role:** Null source plugin -- yields no rows. Used during resume operations where row data comes from the payload store rather than the original source. Satisfies `PipelineConfig.source` typing requirements while producing no output. Also used for pipeline validation and dry-run mode.
**Key dependencies:** `pydantic.ConfigDict`, `elspeth.contracts.Determinism`, `elspeth.contracts.PluginSchema`, `elspeth.contracts.SourceRow`, `elspeth.plugins.base.BaseSource`, `elspeth.plugins.context.PluginContext`. Imported by: `elspeth.cli` (resume operations, lines 1933 and 2121).
**Analysis depth:** FULL

## Summary

NullSource is a minimal, correctly implemented placeholder source for resume operations. At 78 lines, there is very little surface area for bugs. The code is clean, the docstrings are thorough, and the design decisions (NullSourceSchema with `extra="allow"`, `Determinism.DETERMINISTIC`, `_on_validation_failure = "discard"`) are all correct for the resume use case. The one notable observation is that the schema contract is never set, which means `get_schema_contract()` always returns `None` -- this is correct for resume mode where the original run's contract is used, but should be understood by callers.

## Critical Findings

*None identified.*

## Warnings

*None identified.*

## Observations

### [19-33] NullSourceSchema design is correct and well-documented

The docstring on lines 25-31 explains why `extra="allow"` is critical: the DAG validator uses `len(model_fields) == 0 AND model_config["extra"] == "allow"` to identify observed schemas. Without this, NullSourceSchema would be treated as an explicit schema with zero fields, causing resume graph validation to fail. This is a non-obvious but important detail that is properly documented.

### [56-67] Config injection with schema default

The constructor injects `{"mode": "observed"}` into the config if `schema` is not present (lines 65-66). This is a pragmatic approach that ensures `BaseSource.__init__` succeeds without requiring callers to provide schema config for a source that never validates data. The `dict(config)` copy on line 64 avoids mutating the caller's config dict.

### [71-83] `load()` returns `iter([])` instead of using `yield` syntax

The `load()` method returns `iter([])` rather than using a generator with no yield statements (which would also produce an empty iterator). Both approaches are functionally equivalent. Using `iter([])` is slightly more explicit about the intent ("returns empty, not a generator that might yield") and avoids the Python behavior where a function with `yield` that never reaches it still creates a generator object. This is a reasonable choice.

### [52] `output_schema` set as class attribute

Unlike CSVSource and JSONSource which set `output_schema` as an instance attribute in `__init__`, NullSource sets it as a class attribute (line 52: `output_schema: type[PluginSchema] = NullSourceSchema`). This is correct since NullSource always uses the same schema. It also means the schema is available before `__init__` is called, which is useful for introspection.

### [54] `_on_validation_failure = "discard"` is correct

NullSource yields no rows, so it can never encounter validation failures. Setting `_on_validation_failure = "discard"` satisfies the BaseSource protocol requirement without creating unnecessary quarantine routing configuration.

### [No line] No schema contract lifecycle

NullSource never calls `set_schema_contract()`, so `get_schema_contract()` always returns `None`. This is correct for resume mode where the engine provides the schema contract from the original run's audit trail. However, this means NullSource cannot be used as a drop-in replacement for a regular source in non-resume contexts where downstream code expects a schema contract. The module docstring and class docstring both document the resume-only purpose clearly.

### [36-46] Clean class docstring

The docstring correctly identifies the three key aspects: (1) used during resume, (2) source slot must be filled, (3) schema comes from original run's audit trail. This is precise documentation.

## Verdict

**Status:** SOUND
**Recommended action:** No changes needed. This is a minimal, correctly implemented placeholder. The code is clean, well-documented, and serves its specific purpose. The only improvement would be to add a brief inline comment at the class level noting that `get_schema_contract()` intentionally returns `None` for resume mode, to prevent a future maintainer from adding contract initialization "as a fix."
**Confidence:** HIGH -- The file is 78 lines of straightforward code with no external I/O, no complex control flow, and no mutable state. Complete analysis was trivial.
