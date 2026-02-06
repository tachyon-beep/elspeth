# Analysis: src/elspeth/tui/types.py

**Lines:** 143
**Role:** Type definitions and data containers for TUI components. Defines TypedDicts for data passed between TUI components: lineage tree data, node state information, and display types for parsed Landscape audit data (errors, artifacts).
**Key dependencies:** Imports only from `typing` (standard library). Imported by `elspeth.tui.screens.explain_screen` and `elspeth.tui.widgets.node_detail`, `elspeth.tui.widgets.lineage_tree`.
**Analysis depth:** FULL

## Summary

This is a clean, well-documented type definitions file. The TypedDicts enforce the data contracts between TUI components correctly. The `total=False` usage on `NodeStateInfo` is the one area that warrants scrutiny -- it makes all fields optional at the type level even though some are documented as required. Overall the file is sound.

## Warnings

### [57-96] NodeStateInfo uses total=False but documents some fields as "required"

**What:** `NodeStateInfo` is declared with `total=False`, which makes every field optional at the type level. However, the docstring clearly states that `node_id`, `plugin_name`, and `node_type` are "Required - always present from node registration." The consumer (`NodeDetailPanel.render_content()`) accesses these fields directly with `self._state["plugin_name"]` (line 108 of `node_detail.py`), which would raise `KeyError` if the field were missing. This is correct behavior per the Tier 1 trust model (crash on our bug), but the type system does not enforce it.

**Why it matters:** A future developer could construct a `NodeStateInfo` without the "required" fields and the type checker would not flag it. The runtime crash would be correct (it's a bug), but the type system should ideally prevent this at development time. Since `TypedDict` does not support mixed required/optional fields elegantly (you'd need inheritance with a required base and optional extension), this is a known Python typing limitation.

**Evidence:**
```python
class NodeStateInfo(TypedDict, total=False):
    # Required - always present from node registration
    node_id: str          # Accessed directly in node_detail.py
    plugin_name: str      # Accessed directly in node_detail.py
    node_type: str        # Accessed directly in node_detail.py

    # Optional - present after execution
    state_id: str         # Accessed via .get() in node_detail.py
    ...
```

Python 3.11+ supports the `Required[]`/`NotRequired[]` annotations from `typing` that could make this explicit:
```python
class NodeStateInfo(TypedDict, total=False):
    node_id: Required[str]
    plugin_name: Required[str]
    ...
```

This is an improvement opportunity, not a bug.

### [16-27] NodeInfo and SourceInfo are structurally identical

**What:** `NodeInfo` and `SourceInfo` are separate TypedDicts with identical fields: `name: str` and `node_id: str | None`. They are used in different contexts (`transforms`/`sinks` list vs `source` field in `LineageData`), but they are structurally indistinguishable.

**Why it matters:** This is a minor duplication issue. Having separate types for semantic clarity is defensible (a source is conceptually different from a transform/sink node), but if one changes independently of the other, it could cause subtle contract mismatches. If the intent is truly that they always have the same shape, a single type with an alias would be clearer.

## Observations

### [106-143] Display types correctly model the error discrimination pattern

**What:** `ExecutionErrorDisplay`, `TransformErrorDisplay`, and `ArtifactDisplay` correctly mirror the contracts in `elspeth.contracts.errors` and `elspeth.contracts.audit`. The required/optional field split using `NotRequired` is appropriate and well-documented. The `node_detail.py` consumer uses these types correctly via the `_validate_*` functions.

### [30-54] LineageData contract is well-designed

**What:** `LineageData` uses `total=True` (the default), meaning all fields are required. This is correct -- the docstring explicitly states "All fields are required. If data is unavailable, the caller must handle that BEFORE constructing LineageData." The `explain_screen.py` `_load_pipeline_structure` method correctly populates all fields before constructing `LineageData`.

### [39] TokenDisplayInfo.path is a list[str] but semantics are unclear

**What:** The `path` field is typed as `list[str]` and documented as "for breadcrumb display." In `lineage_tree.py` (line 116), `path[-1]` is used as a terminal node ID to find which sink a token ended at. The semantic meaning of each element in the path list is not documented -- is it node IDs? Names? A mix?

**Why it matters:** Without documentation of what each path element represents, future maintainers could populate it incorrectly. The `lineage_tree.py` consumer assumes the last element is a node_id that can be used as a dictionary key in `sink_nodes`. If someone populates it with node names instead, the token-to-sink mapping silently fails (tokens don't appear under any sink).

## Verdict

**Status:** SOUND
**Recommended action:** Consider using `Required[]` annotations on `NodeStateInfo` for the three always-present fields (Python 3.11+ feature). Document the semantics of `TokenDisplayInfo.path` elements. Minor improvements only -- no functional issues.
**Confidence:** HIGH -- this is a pure type definition file with no logic, making analysis straightforward.
