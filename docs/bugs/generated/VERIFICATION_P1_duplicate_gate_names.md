# Bug Verification Report: Duplicate Config Gate Names Overwrite Node Mapping

## Status: VERIFIED

**Bug ID:** P1-duplicate-gate-names
**Claimed Location:** `src/elspeth/core/config.py` (Bug #1)
**Verification Date:** 2026-01-22
**Verifier:** Claude Code

---

## Summary of Bug Claim

The bug report claims that gate names are documented as unique but not validated, so duplicates overwrite `config_gate_id_map` and cause multiple gates to share a node ID, corrupting routing/audit attribution.

## Code Analysis

### 1. GateSettings Definition (config.py:158-296)

The `GateSettings` class defines a `name` field:

```python
# From config.py:158-182
class GateSettings(BaseModel):
    """Gate configuration for config-driven routing.

    Gates are defined in YAML and evaluated by the engine using ExpressionParser.
    The condition expression determines routing; route labels map to destinations.

    Example YAML:
        gates:
          - name: quality_check
            condition: "row['confidence'] >= 0.85"
            routes:
              high: continue
              low: review_sink
    """

    model_config = {"frozen": True}

    name: str = Field(description="Gate identifier (unique within pipeline)")  # <-- CLAIMS UNIQUE
    condition: str = Field(description="Expression to evaluate")
    routes: dict[str, str] = Field(description="Maps route labels to destinations")
    fork_to: list[str] | None = Field(default=None, description="List of paths for fork operations")
```

The docstring says "unique within pipeline" but there is **NO VALIDATOR** to enforce this.

### 2. ElspethSettings Validation (config.py:661-707)

The `ElspethSettings` class has validators for aggregation uniqueness, but **NO GATE UNIQUENESS VALIDATOR**:

```python
# From config.py:680-687
@model_validator(mode="after")
def validate_unique_aggregation_names(self) -> "ElspethSettings":
    """Ensure aggregation names are unique."""
    names = [agg.name for agg in self.aggregations]
    duplicates = [name for name in names if names.count(name) > 1]
    if duplicates:
        raise ValueError(f"Duplicate aggregation name(s): {set(duplicates)}")
    return self
```

There is **NO CORRESPONDING VALIDATOR** for `self.gates`.

### 3. ExecutionGraph.from_config (dag.py:332-404)

The DAG builder uses gate names as dict keys:

```python
# From dag.py:332-404
config_gate_ids: dict[str, str] = {}
gate_sequence: list[tuple[str, GateSettings]] = []  # Track for continue edge creation
for gate_config in config.gates:
    gid = node_id("config_gate", gate_config.name)
    config_gate_ids[gate_config.name] = gid  # <-- OVERWRITES ON DUPLICATE

    # ... node creation ...

# Store explicit mapping for get_config_gate_id_map()
graph._config_gate_id_map = config_gate_ids  # <-- ONLY LAST GATE'S ID STORED
```

When two gates have the same name:
1. First gate: `config_gate_ids["quality_check"] = "config_gate_quality_check_abc123"`
2. Second gate: `config_gate_ids["quality_check"] = "config_gate_quality_check_def456"` (OVERWRITES)

### 4. Processor Gate Resolution (processor.py:885-886)

The processor resolves gate node IDs by name:

```python
# From processor.py:885-886
node_id = self._config_gate_id_map[gate_config.name]
```

With duplicates, BOTH gates resolve to the SAME node ID (the last one), causing:
1. First gate's actual node ID is never used
2. Audit trail records wrong node for first gate's routing decisions
3. Node states are misattributed

## Reproduction Scenario

**Config with duplicate gate names:**

```yaml
gates:
  - name: quality_check       # First gate
    condition: "row['score'] > 0.8"
    routes:
      true: continue
      false: review_sink

  - name: quality_check       # DUPLICATE NAME
    condition: "row['priority'] == 'high'"
    routes:
      true: fast_track_sink
      false: continue
```

**What happens:**

1. `load_settings()` accepts this config without error
2. DAG builder creates TWO nodes but maps BOTH to second gate's ID
3. Processor executes first gate but records routing against second gate's node
4. Audit trail shows incorrect routing attribution

## Evidence Summary

| Location | Finding |
|----------|---------|
| `config.py:182` | Gate `name` field docstring claims "unique within pipeline" |
| `config.py:618-621` | `gates: list[GateSettings]` - no uniqueness constraint |
| `config.py:680-687` | Aggregation uniqueness validator exists (proof pattern available) |
| `config.py` | **NO validator** for gate name uniqueness |
| `dag.py:336` | `config_gate_ids[gate_config.name] = gid` - overwrites on duplicate |
| `processor.py:886` | Lookup by name - returns wrong node ID for first gate |

## Impact Assessment

| Factor | Assessment |
|--------|------------|
| **Severity** | Major - Audit trail corruption |
| **Frequency** | Low-Medium - Config typos or copy-paste errors |
| **Detection** | Hard - Config loads successfully, runs to completion |
| **Consequence** | Routing decisions attributed to wrong gate in audit trail |

## CLAUDE.md Alignment

This violates the auditability standard:

> Every decision must be traceable to source data, configuration, and code version

With duplicate gate names, routing decisions are traced to the WRONG gate node, making the audit trail misleading.

---

## Conclusion

**VERIFIED:** The bug is accurate. Duplicate gate names are:

1. **Accepted by config validation** despite being documented as unique
2. **Silently overwritten** in `config_gate_id_map` during DAG construction
3. **Cause audit misattribution** when processor records routing events

The fix is straightforward: add a `model_validator` in `ElspethSettings` for gate name uniqueness, matching the existing pattern for aggregation names.
