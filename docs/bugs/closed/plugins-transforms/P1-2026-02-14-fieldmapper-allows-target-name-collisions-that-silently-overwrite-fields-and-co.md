## Summary

`FieldMapper` allows target-name collisions that silently overwrite fields, and in collision cases it can emit a `PipelineRow` whose contract metadata (type/original_name lineage) no longer matches the actual output value.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/transforms/field_mapper.py
- Line(s): 112-138, 150-154
- Function/Method: `FieldMapper.process`

## Evidence

`FieldMapper.process()` writes mapped values directly into `output[target]` without collision checks:

- `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/field_mapper.py:137`
- `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/field_mapper.py:112-136`

It then delegates contract rebuilding to `narrow_contract_to_output(...)`:

- `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/field_mapper.py:150-154`

But `narrow_contract_to_output` only treats rename metadata when the target is a **new** field (`if name not in existing_names`), so a rename into an already-existing field keeps the old field contract instead of source-field metadata:

- `/home/john/elspeth-rapid/src/elspeth/contracts/contract_propagation.py:110-111`
- `/home/john/elspeth-rapid/src/elspeth/contracts/contract_propagation.py:127-147`

Repro run in this workspace:

- Input contract: `a:int (original A)`, `b:str (original B)`
- Mapping: `{"a": "b"}`
- Output row: `{"b": 1}`
- Output contract field: `("b", original_name="B", python_type=str)`

So value comes from `a` (int), but contract claims `b` (str). This is a lineage/type contract mismatch and silent field loss (`b`'s original value is dropped without explicit error).

This also propagates to sinks that rely on contract original names for header restoration:

- `/home/john/elspeth-rapid/src/elspeth/plugins/sinks/csv_sink.py:477-483`
- `/home/john/elspeth-rapid/src/elspeth/plugins/sinks/csv_sink.py:491-500`

## Root Cause Hypothesis

`FieldMapper` assumes mappings are non-colliding but never enforces that invariant. It permits:

1. Multiple sources mapping to one target (last write wins)
2. Source mapping into an existing target field name

The contract narrowing helper does not fully resolve these collision semantics, so metadata can become inconsistent with emitted row data.

## Suggested Fix

In `FieldMapper` (target file), enforce collision-safe mapping before applying writes:

1. Reject duplicate targets in config (`a->x`, `b->x`) at init time.
2. In `process`, reject runtime collisions where `target` already exists in input/output unless it is a true identity rename (`source == target` after resolution).
3. Return `TransformResult.error({"reason": "mapping_collision", ...})` with source/target details instead of silently overwriting.
4. Keep calling `narrow_contract_to_output` only for collision-free mappings.

This keeps fixes localized to `field_mapper.py` and avoids emitting invalid contract lineage.

## Impact

- Silent field data loss during mapping collisions.
- Contract/type metadata can diverge from actual output values.
- Incorrect original-name lineage can leak into sink headers and audit explanations.
- Downstream transforms/sinks may make decisions using incorrect contract assumptions, reducing audit reliability.
