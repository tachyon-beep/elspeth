# Bug Verification Report: Duplicate Fork/Coalesce Branch Names Break Merge Semantics

## Status: VERIFIED

**Bug ID:** P1-duplicate-branch-names
**Claimed Location:** `src/elspeth/core/config.py` (Bug #2)
**Verification Date:** 2026-01-22
**Verifier:** Claude Code

---

## Summary of Bug Claim

The bug report claims that `fork_to` and `coalesce.branches` allow duplicate branch names; coalesce tracking uses a dict keyed by branch name, so duplicates overwrite tokens and can prevent `require_all`/`quorum` merges from ever completing.

## Code Analysis

### 1. GateSettings.fork_to Validation (config.py:238-252)

The validator only checks for reserved labels, NOT uniqueness:

```python
# From config.py:238-252
@field_validator("fork_to")
@classmethod
def validate_fork_to_labels(cls, v: list[str] | None) -> list[str] | None:
    """Validate fork branch names don't use reserved edge labels.

    Fork branches become edge labels in the DAG, so they must not collide
    with reserved labels like 'continue'.
    """
    if v is None:
        return v

    for branch in v:
        if branch in _RESERVED_EDGE_LABELS:
            raise ValueError(f"Fork branch '{branch}' is reserved and cannot be used. Reserved labels: {sorted(_RESERVED_EDGE_LABELS)}")
    return v  # <-- NO UNIQUENESS CHECK
```

**Missing validation:** `fork_to: ["path_a", "path_a"]` is accepted.

### 2. CoalesceSettings.branches Definition (config.py:327-331)

The branches field has `min_length=2` but **NO uniqueness validation**:

```python
# From config.py:327-331
branches: list[str] = Field(
    min_length=2,
    description="Branch names to wait for (from fork_to paths)",
)
# No uniqueness validator exists
```

**Missing validation:** `branches: ["path_a", "path_a"]` is accepted.

### 3. CoalesceExecutor._PendingCoalesce (coalesce_executor.py:40-45)

The pending coalesce state uses a dict keyed by branch name:

```python
# From coalesce_executor.py:40-45
@dataclass
class _PendingCoalesce:
    """Tracks pending tokens for a single row_id at a coalesce point."""

    arrived: dict[str, TokenInfo]  # branch_name -> token  <-- OVERWRITES ON DUPLICATE
    arrival_times: dict[str, float]  # branch_name -> monotonic time
    first_arrival: float  # For timeout calculation
```

### 4. CoalesceExecutor.accept (coalesce_executor.py:172-174)

When a token arrives, it's stored by branch name:

```python
# From coalesce_executor.py:172-174
pending = self._pending[key]

# Record arrival
pending.arrived[token.branch_name] = token  # <-- OVERWRITES PREVIOUS TOKEN
pending.arrival_times[token.branch_name] = now
```

If two tokens arrive with the same branch name, the first one is **LOST**.

### 5. CoalesceExecutor._should_merge (coalesce_executor.py:195-196)

The merge condition compares arrived count to branch count:

```python
# From coalesce_executor.py:195-196
arrived_count = len(pending.arrived)
expected_count = len(settings.branches)

if settings.policy == "require_all":
    return arrived_count == expected_count  # <-- NEVER SATISFIED WITH DUPLICATES
```

With `branches: ["path_a", "path_a"]`:
- `expected_count = 2` (list length includes duplicate)
- `arrived_count` can only reach `1` (dict dedups by key)
- `require_all` policy NEVER triggers

### 6. DAG Builder branch_to_coalesce (dag.py:408-435)

The branch-to-coalesce mapping also overwrites duplicates:

```python
# From dag.py:408-435
branch_to_coalesce: dict[str, str] = {}

for coalesce_config in config.coalesce:
    cid = node_id("coalesce", coalesce_config.name)
    coalesce_ids[coalesce_config.name] = cid

    for branch in coalesce_config.branches:
        branch_to_coalesce[branch] = coalesce_config.name  # <-- OVERWRITES ACROSS COALESCE CONFIGS
```

If two coalesce configs share a branch name, only the LAST one is recorded.

## Reproduction Scenarios

### Scenario 1: Duplicate fork_to branches

```yaml
gates:
  - name: parallel_analysis
    condition: "True"
    routes:
      all: fork
    fork_to:
      - path_a
      - path_a  # DUPLICATE

coalesce:
  - name: merge_results
    branches:
      - path_a
      - path_a  # DUPLICATE (matches fork)
    policy: require_all
```

**What happens:**

1. Fork creates 2 tokens with `branch_name="path_a"` each
2. First token arrives at coalesce: `arrived = {"path_a": token1}`
3. Second token arrives: `arrived = {"path_a": token2}` (OVERWRITES token1)
4. `len(arrived) = 1`, `len(branches) = 2`
5. `require_all` condition: `1 == 2` is False
6. **Pipeline HANGS** - coalesce never completes

### Scenario 2: Cross-coalesce branch collision

```yaml
coalesce:
  - name: merge_a
    branches:
      - fast_path
      - slow_path
    policy: require_all

  - name: merge_b
    branches:
      - slow_path   # COLLISION with merge_a
      - alternate_path
    policy: require_all
```

**What happens:**

1. `branch_to_coalesce["slow_path"]` = `"merge_a"` (first coalesce)
2. `branch_to_coalesce["slow_path"]` = `"merge_b"` (OVERWRITES)
3. Tokens on `slow_path` route ONLY to `merge_b`
4. `merge_a` never receives `slow_path` tokens
5. **`merge_a` HANGS** - never completes

## Evidence Summary

| Location | Finding |
|----------|---------|
| `config.py:238-252` | `fork_to` validator checks reserved labels only, NOT uniqueness |
| `config.py:327-331` | `branches` field has no uniqueness constraint |
| `config.py` | **NO validator** for unique branches within `fork_to` or `coalesce.branches` |
| `coalesce_executor.py:43` | `arrived: dict[str, TokenInfo]` - dedups by branch name |
| `coalesce_executor.py:173` | `pending.arrived[token.branch_name] = token` - overwrites |
| `coalesce_executor.py:195-196` | `len(pending.arrived) == len(settings.branches)` - fails with duplicates |
| `dag.py:416` | `branch_to_coalesce[branch] = coalesce_config.name` - cross-coalesce collision |

## Impact Assessment

| Factor | Assessment |
|--------|------------|
| **Severity** | Major - Pipeline hangs indefinitely |
| **Frequency** | Low - Requires config typo or copy-paste error |
| **Detection** | Hard - Config loads successfully, pipeline stalls silently |
| **Consequence 1** | Coalesce never completes with `require_all`/`quorum` |
| **Consequence 2** | First token lost, audit trail incomplete |
| **Consequence 3** | Cross-coalesce collision causes wrong routing |

## CLAUDE.md Alignment

This violates multiple principles:

1. **Auditability:** "Every decision must be traceable to source data" - Tokens silently lost
2. **Data Loss Prevention:** Coalesce dict overwrites cause silent data loss
3. **No Silent Drops:** "Every row reaches exactly one terminal state" - Rows stuck in pending coalesce forever

---

## Conclusion

**VERIFIED:** The bug is accurate. Duplicate branch names are:

1. **Accepted by config validation** in both `fork_to` and `coalesce.branches`
2. **Cause token overwrites** in CoalesceExecutor's `arrived` dict
3. **Prevent merge completion** for `require_all`/`quorum` policies
4. **Enable cross-coalesce routing collision** when same branch name used in multiple coalesce configs

The fix requires:

1. Add uniqueness validator for `GateSettings.fork_to`
2. Add uniqueness validator for `CoalesceSettings.branches`
3. (Optional) Add cross-coalesce uniqueness check in `ElspethSettings` for branch names
