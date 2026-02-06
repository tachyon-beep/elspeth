# Analysis: src/elspeth/core/landscape/__init__.py

**Lines:** 151
**Role:** Module initialization and public API facade for the Landscape audit subsystem. Re-exports types, table definitions, and key classes from submodules to provide a unified import surface.
**Key dependencies:** Imports from `elspeth.contracts` (all model types), `database.py` (LandscapeDB), `exporter.py`, `formatters.py`, `lineage.py`, `recorder.py`, `reproducibility.py`, `row_data.py`, `schema.py` (table definitions). Imported by engine, CLI, MCP server, and tests.
**Analysis depth:** FULL

## Summary

This file is a straightforward re-export facade. It is well-structured and serves its purpose of providing a single import point. The primary concern is an incomplete `__all__` list that omits several table definitions added in later phases, creating an inconsistency between what `schema.py` defines and what the public API advertises. No critical issues found.

## Warnings

### [73-88] Incomplete table re-exports from schema.py

**What:** The import block from `schema.py` (lines 73-88) and the corresponding `__all__` list (lines 130-148) export only 13 of the 19 tables defined in `schema.py`. Missing tables: `token_outcomes_table`, `operations_table`, `validation_errors_table`, `transform_errors_table`, `checkpoints_table`, `secret_resolutions_table`.

**Why it matters:** Consumers that import from `elspeth.core.landscape` expecting all table objects will get `ImportError` for the missing tables. Currently, consumers (MCP server, checkpoint manager, retention purge, recorder) import directly from `elspeth.core.landscape.schema`, which works but creates an inconsistency: some tables are available via the facade and some are not. This is a maintenance hazard -- new code might import from the facade, not find the table, and add a direct schema import, further fragmenting the import patterns.

**Evidence:**
- `schema.py` defines: `token_outcomes_table`, `operations_table`, `validation_errors_table`, `transform_errors_table`, `checkpoints_table`, `secret_resolutions_table`
- None of these appear in `__init__.py` lines 73-88 or 130-148
- `mcp/server.py` imports these directly from `schema.py` (e.g., line 489: `from elspeth.core.landscape.schema import transform_errors_table, validation_errors_table`)

### [25-53] Import list drift risk with contracts module

**What:** The import block from `elspeth.contracts` (lines 25-53) lists 25 types. The `__all__` list must be maintained in sync with these imports. Any addition to contracts that should be re-exported requires updating both the import and `__all__`.

**Why it matters:** If a new contract type is imported but not added to `__all__`, it will be silently available via `from elspeth.core.landscape import *` in some Python versions but will fail with explicit star-import checks. This is a minor drift risk, not a current bug.

**Evidence:** Both lists currently appear synchronized. The concern is forward-looking.

## Observations

### [90-150] __all__ list is well-maintained for current exports

The `__all__` list is alphabetically sorted and matches the actual imports. This is good practice and makes drift easy to spot visually.

### [1-23] Docstring is accurate and comprehensive

The module docstring accurately describes the public API surface, including the Phase 5 schema contract types. This is useful documentation.

### No circular import risk

The file uses only direct imports (no `TYPE_CHECKING` guards), which means all imports are resolved at module load time. Given the dependency direction (this file is the consumer, not the provider), this is safe. The landscape submodules do not import from `__init__.py`.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Add the 6 missing table re-exports to both the import block and `__all__` list to maintain consistency with `schema.py`. This is a minor cleanup task that prevents future import confusion.
**Confidence:** HIGH -- The file is simple and the analysis is exhaustive. The incomplete export list is the only issue.
