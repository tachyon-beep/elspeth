# Analysis: src/elspeth/tui/widgets/lineage_tree.py

**Lines:** 197
**Role:** Tree widget that builds and displays row lineage (source -> transforms -> sink) as a navigable tree structure. Converts `LineageData` into a `TreeNode` hierarchy, supports expansion/collapse, and provides flat rendering for display.
**Key dependencies:** Imports `elspeth.tui.types.LineageData`. Imported by `elspeth.tui.screens.explain_screen` and `elspeth.tui.widgets.__init__`.
**Analysis depth:** FULL

## Summary

The tree construction logic is straightforward and correct for linear pipelines. However, it has significant limitations for DAG topologies (forks, multiple sinks), and the token-to-sink mapping silently drops tokens that don't match any sink. The `_flatten_tree` method uses unbounded recursion that could stack overflow on pathological inputs. The code is clean and well-documented.

## Warnings

### [73-85] Transform chain assumes linear topology, not DAG

**What:** The `_build_tree` method builds transforms as a strict linear chain: each transform becomes the child of the previous one. The code sets `current_parent = transform_node` in a loop, creating a single linked chain. In ELSPETH, pipelines compile to DAGs where transforms can fork to multiple paths. With the current implementation, forked paths, parallel branches, and non-linear topologies are flattened into a single chain ordered by whatever sequence `_data["transforms"]` provides.

**Why it matters:** For a pipeline with a gate that forks to two transform paths (e.g., path_a -> transform_1 and path_b -> transform_2), the tree would display:
```
Source: csv_source
  Transform: gate_1
    Transform: transform_1
      Transform: transform_2  <- wrong nesting, transform_2 is parallel, not nested
```
This misrepresents the pipeline topology. Users investigating routing decisions would see a misleading structure.

**Evidence:**
```python
for transform in transforms:
    transform_node = TreeNode(label=f"Transform: {transform_name}", ...)
    current_parent.children.append(transform_node)
    current_parent = transform_node  # Always chains linearly
```

The DAG execution model (from CLAUDE.md) supports forks and joins, but this widget assumes linearity.

### [103-119] Tokens silently disappear if path doesn't match a sink node_id

**What:** For each token, the code looks up `path[-1]` (the terminal node ID) in the `sink_nodes` dictionary. If the terminal node ID is not found (e.g., the token terminated at a gate rather than a sink, or `path` is populated with non-matching IDs), the token is silently omitted from the tree. Tokens with empty `path` lists also trigger the `if path and len(path) > 0` guard and are silently skipped.

**Why it matters:** Tokens that were quarantined, failed, or routed to non-sink terminals will not appear in the tree at all. This is a silent data loss in the display layer -- the user has no way to know that tokens exist but are not shown. For an audit system, this gap means "I don't know what happened" for certain rows, directly contradicting the project's attributability requirement.

**Evidence:**
```python
if path and len(path) > 0:
    terminal_node_id = path[-1]
    if terminal_node_id in sink_nodes:
        sink_nodes[terminal_node_id].children.append(token_node)
    # else: token silently dropped
# else: token silently dropped (empty path)
```

### [115] Redundant condition: `path and len(path) > 0`

**What:** The condition `if path and len(path) > 0` is redundant. In Python, `if path` is `False` for empty lists, so `len(path) > 0` is never needed after a truthiness check on `path`. This is not a bug but indicates the code may have been written hastily.

### [132-153] Recursive _flatten_tree has no depth limit

**What:** `_flatten_tree` recurses through children with no maximum depth check. While the tree is constructed from pipeline data (which is bounded by the number of pipeline nodes), if the tree construction had a bug that created a cycle (e.g., a node added as its own descendant), this would stack overflow.

**Why it matters:** The `TreeNode` dataclass uses a mutable `children` list. A bug in tree construction (or in `toggle_node` which mutates the tree) could theoretically create a cycle. Python's default recursion limit is 1000, so this would crash with a `RecursionError` rather than hang. The risk is low given the current construction logic, but it's worth noting.

### [89-101] Sink node_id key mapping assumes non-None node_ids

**What:** The `sink_nodes` dictionary is only populated when `sink_node_id` is not None (line 100: `if sink_node_id:`). Sinks with `node_id: None` are added to the tree visually but cannot receive tokens, since they're not in the lookup dict. The `LineageData` contract allows `node_id: str | None` in `NodeInfo`.

**Why it matters:** If a sink has `node_id: None` (which the `SourceInfo` and `NodeInfo` types allow), it will appear in the tree but no tokens will ever be placed under it. The sink appears empty even if tokens were routed to it.

## Observations

### [9-17] TreeNode dataclass is mutable by design

**What:** `TreeNode` is a mutable dataclass (not `frozen=True`) with a mutable `children` list and mutable `expanded` boolean. This is intentional -- `toggle_node` (line 184) mutates the `expanded` field. The mutable design is correct for an interactive tree widget.

### [155-182] get_node_by_id and _find_node are O(n) linear searches

**What:** Finding a node by ID requires traversing the entire tree. For typical pipeline sizes (tens to low hundreds of nodes), this is fine. For extremely large pipelines this could become noticeable, but it's not a practical concern.

### [184-197] toggle_node returns False for non-existent nodes

**What:** If `get_node_by_id` returns `None`, `toggle_node` returns `False`. This silently handles the "node not found" case. Since this is a UI interaction (toggling expansion), returning `False` is a reasonable UX choice rather than crashing.

### [52-120] _build_tree correctly uses direct field access per contract

**What:** All access to `LineageData`, `SourceInfo`, `NodeInfo`, and `TokenDisplayInfo` fields uses direct dictionary access (`source["name"]`, `transform["node_id"]`, etc.) rather than `.get()`. This correctly follows the Tier 1 trust model -- malformed data will crash immediately rather than producing a subtly wrong tree.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) The linear transform chain assumption should be documented as a known limitation or refactored to support DAG display (using edge data from the database). (2) Tokens that don't match any sink should be rendered in an "Unmatched" or "Orphaned" section rather than silently dropped. (3) The redundant `path and len(path) > 0` should be simplified to `if path:`.
**Confidence:** HIGH -- the tree construction logic is straightforward and the issues are clearly identifiable from the data model and the code structure.
