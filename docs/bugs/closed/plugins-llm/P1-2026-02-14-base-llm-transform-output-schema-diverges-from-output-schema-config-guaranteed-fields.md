## Summary

`BaseLLMTransform` publishes guaranteed LLM output fields in `output_schema_config` but keeps `output_schema` equal to the input schema, causing contract/type divergence and edge-validation failures for explicit downstream consumers.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1: only affects explicit-schema pipelines; dynamic mode unaffected)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py`
- Line(s): `246-247`, `257-263`, `350-360`
- Function/Method: `BaseLLMTransform.__init__`, `process`

## Evidence

In `__init__`, the transform sets:

- `self.input_schema = schema`
- `self.output_schema = schema`
  (`src/elspeth/plugins/llm/base.py:246-247`)

Then it builds `_output_schema_config` with guaranteed/audit LLM fields (`src/elspeth/plugins/llm/base.py:257-263`), while `fields` remain original schema fields.

At runtime it actually emits new fields (`src/elspeth/plugins/llm/base.py:350-360`).

DAG validation uses:
- `output_schema_config` for guaranteed-field contract checks (`src/elspeth/core/dag/graph.py:1288-1345`)
- `output_schema` for type compatibility (`src/elspeth/core/dag/graph.py:1023-1041`)

Read-only probe showed:
- producer guaranteed fields include `llm_response`
- `validate_edge_compatibility()` still fails with `Missing fields: llm_response` because producer `output_schema` lacks it.

This also bypasses explicit `SchemaConfig` subset invariants normally enforced in `SchemaConfig.from_dict` (`src/elspeth/contracts/schema.py:394-400`), since `SchemaConfig(...)` is built directly.

## Root Cause Hypothesis

Two schema representations are kept out of sync: contract-level guaranteed fields are widened, but type-level output schema is not.

## Suggested Fix

In `BaseLLMTransform.__init__`, make `output_schema` consistent with emitted fields and `_output_schema_config`:
- Build an augmented output schema (including response/model/usage and audit fields with appropriate types), or
- Use an explicit observed output schema strategy and align guarantees accordingly.

Add an integration test with explicit downstream schema requiring `llm_response` to ensure `validate_edge_compatibility()` passes when contracts say it should.

## Impact

Valid explicit-schema pipelines can fail DAG validation despite correct guaranteed-field contracts, and the plugin violates its own interface expectation that `output_schema` matches produced rows.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/base.py.md`
- Finding index in source report: 2
- Beads: pending
