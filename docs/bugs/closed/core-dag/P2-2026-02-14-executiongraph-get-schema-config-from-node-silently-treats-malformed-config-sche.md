## Summary

`ExecutionGraph.get_schema_config_from_node()` silently treats malformed `config["schema"]` payloads as “no schema,” bypassing contract validation instead of raising.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/dag/graph.py`
- Line(s): `1314-1323`
- Function/Method: `ExecutionGraph.get_schema_config_from_node`

## Evidence

Current logic:

```python
schema_dict = node_info.config.get("schema")
if schema_dict is None:
    return None
if isinstance(schema_dict, dict):
    return SchemaConfig.from_dict(schema_dict)
return None
```

Source: `/home/john/elspeth-rapid/src/elspeth/core/dag/graph.py:1314`

If `schema` exists but has wrong type, method returns `None` (interpreted as no schema) rather than failing. This bypasses guaranteed/required-field contract checks that depend on schema config.

This behavior conflicts with stated safety intent in allowlist metadata (“Non-dict payloads are rejected and converted to explicit validation failures”): `/home/john/elspeth-rapid/config/cicd/enforce_tier_model/core.yaml:400`.

## Root Cause Hypothesis

A permissive fallback was kept for mixed node types, but it conflates “schema absent” with “schema malformed,” hiding internal/config-shape bugs.

## Suggested Fix

Differentiate absent vs malformed schema:

- If `"schema"` key is absent: return `None`.
- If present but not `dict`: raise `GraphValidationError` with node/type details.
- Optionally wrap `SchemaConfig.from_dict()` errors to include `node_id` context.

## Impact

Malformed schema payloads can silently disable DAG contract validation (required/guaranteed fields), allowing invalid wiring to proceed and shifting failures to later runtime stages.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/dag/graph.py.md`
- Finding index in source report: 2
- Beads: pending
