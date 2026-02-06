# Analysis: src/elspeth/core/checkpoint/compatibility.py

**Lines:** 123
**Role:** Validates that a checkpoint can be safely resumed with the current pipeline configuration by checking three conditions: checkpoint node exists, node config unchanged, and full DAG topology unchanged. Separated from RecoveryManager to isolate topology validation logic.
**Key dependencies:** Imports `Checkpoint` and `ResumeCheck` from contracts, `compute_full_topology_hash` and `stable_hash` from canonical, and `ExecutionGraph` from DAG. Imported by `elspeth.core.checkpoint.recovery` (used by `RecoveryManager.can_resume()`).
**Analysis depth:** FULL

## Summary

This module is clean, well-documented, and follows a clear validation sequence. The separation from RecoveryManager is a good design decision. The BUG-COMPAT-01 fix (full DAG hashing instead of upstream-only) is correctly implemented. The only notable concerns are a thin delegation method that adds indirection without value, and the lack of diagnostic detail in topology mismatch errors. No critical issues found.

## Observations

### [86-94] compute_full_topology_hash is a pure delegation with no added value

**What:** The `compute_full_topology_hash` method on the validator class simply delegates to `canonical.compute_full_topology_hash()` with no transformation, validation, or added logic:

```python
def compute_full_topology_hash(self, graph: ExecutionGraph) -> str:
    return compute_full_topology_hash(graph)
```

This introduces a layer of indirection that a reader must trace through. The method exists as an instance method on the class, but it doesn't use `self` at all. Line 77 in `validate()` calls `self.compute_full_topology_hash(current_graph)` when it could call `compute_full_topology_hash(current_graph)` directly (the import is already present on line 10).

**Why it matters:** This is a minor maintainability concern. The delegation pattern would make sense if the validator needed to be mocked or if the hash computation might change per-instance, but neither is the case. It adds cognitive overhead when tracing the validation logic.

### [96-122] Topology mismatch error provides hash comparison but no structural diff

**What:** The `_create_topology_mismatch_error` method accepts the checkpoint, current graph, expected hash, and actual hash as parameters (lines 97-101), but only uses the hashes in the error message (lines 116-121). The comment on line 114 acknowledges this: "Could add more diagnostics here: which nodes changed, etc."

**Why it matters:** When a resume fails due to topology mismatch, the operator gets two truncated hash values and no information about what actually changed. For an emergency dispatch system where rapid recovery is critical, knowing "node X was added" or "edge Y was removed" would dramatically speed up diagnosis. The graph is available as a parameter but unused beyond the hash.

### [53-84] Three-step validation sequence is correctly ordered

The validation proceeds in the correct order:
1. **Node existence** (line 54) -- cheapest check first, immediate reject if node removed
2. **Node config hash** (line 65) -- moderately cheap, catches config changes for the specific node
3. **Full topology hash** (line 79) -- most expensive, catches any change anywhere in the DAG

This ordering is an efficient short-circuit pattern. If the checkpoint node doesn't exist, there's no need to compute topology hashes.

### [34-36] Stateless validator uses structlog logger

The validator initializes a structlog logger in `__init__` (line 36) but never uses it anywhere in the module. The logger is initialized but not called by any method.

**Why it matters:** This is dead code. The logger exists but serves no purpose. Either it should be removed, or the methods should use it for diagnostic logging (e.g., logging when validation passes or fails, which would aid operational debugging).

### [65-72] Config hash comparison uses stable_hash correctly

The node config hash comparison correctly uses `stable_hash(current_node_info.config)` (line 63) which is the same function used in `CheckpointManager.create_checkpoint()` (manager.py line 106). This ensures the comparison is apples-to-apples -- both sides use the same canonical hashing. The hash truncation in the error message (`[:8]`) is appropriate for human readability while the full hash is used for comparison.

### [25-31] BUG-COMPAT-01 documentation is thorough

The class docstring clearly explains the bug that motivated full DAG validation (upstream-only validation missed sibling branch changes in multi-sink DAGs) and the invariant being enforced (one run_id = one configuration). This is exemplary documentation that future maintainers will benefit from.

## Verdict

**Status:** SOUND
**Recommended action:** Minor cleanup would improve the module: remove the unused logger, consider inlining the delegation method, and add structural diff information to topology mismatch errors for operational diagnostics. None of these are correctness issues.
**Confidence:** HIGH -- The module is 123 lines with a single clear validation purpose. The logic is straightforward and the hash-based comparison is sound. The ordering of validations is correct and efficient.
