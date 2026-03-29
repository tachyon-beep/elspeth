## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/contracts/schema_contract_factory.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/contracts/schema_contract_factory.py
- Line(s): 28-109
- Function/Method: `map_schema_mode`, `create_contract_from_config`

## Evidence

I audited the target file and verified its behavior against the surrounding schema/config and source-plugin integration paths.

Relevant code in the target file:
- [`schema_contract_factory.py:28`](\/home\/john\/elspeth\/src\/elspeth\/contracts\/schema_contract_factory.py:28) maps YAML schema modes to runtime contract modes via `map_schema_mode()`.
- [`schema_contract_factory.py:65`](\/home\/john\/elspeth\/src\/elspeth\/contracts\/schema_contract_factory.py:65) normalizes the mode before deriving behavior.
- [`schema_contract_factory.py:71`](\/home\/john\/elspeth\/src\/elspeth\/contracts\/schema_contract_factory.py:71) rejects `fixed`/`flexible` configs without explicit fields.
- [`schema_contract_factory.py:77`](\/home\/john\/elspeth\/src\/elspeth\/contracts\/schema_contract_factory.py:77) reverses the source field-resolution mapping to preserve `original_name`.
- [`schema_contract_factory.py:90`](\/home\/john\/elspeth\/src\/elspeth\/contracts\/schema_contract_factory.py:90) constructs `FieldContract` objects from declared schema fields.
- [`schema_contract_factory.py:103`](\/home\/john\/elspeth\/src\/elspeth\/contracts\/schema_contract_factory.py:103) derives `locked` from normalized mode, so `FIXED` contracts start locked and `FLEXIBLE`/`OBSERVED` do not.

Integration checks:
- [`schema.py:325`](\/home\/john\/elspeth\/src\/elspeth\/contracts\/schema.py:325) already validates that only `"fixed"`, `"flexible"`, and `"observed"` modes are accepted and that explicit schemas have non-empty field lists.
- [`schema_contract.py:85`](\/home\/john\/elspeth\/src\/elspeth\/contracts\/schema_contract.py:85) enforces unique normalized field names and builds deterministic lookup indices; nothing produced by the factory violates those invariants.
- [`field_normalization.py:199`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sources\/field_normalization.py:199) guarantees source header normalization/mapping collisions are rejected before their mappings reach the factory.
- [`csv_source.py:334`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sources\/csv_source.py:334) and [`azure_blob_source.py:602`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sources\/azure_blob_source.py:602) call the factory with validated field-resolution mappings.
- [`json_source.py:150`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sources\/json_source.py:150) and [`dataverse.py:228`](\/home\/john\/elspeth\/src\/elspeth\/plugins\/sources\/dataverse.py:228) call it without field resolution where identity naming is expected.
- [`test_schema_contract_factory.py:141`](\/home\/john\/elspeth\/tests\/unit\/contracts\/test_schema_contract_factory.py:141) covers the prior invariant bug around deriving `locked` from raw rather than normalized mode.
- [`test_schema_contract_factory.py:235`](\/home\/john\/elspeth\/tests\/unit\/contracts\/test_schema_contract_factory.py:235) covers original-name preservation and partial-resolution fallback behavior.

Based on those reads, I did not find a credible audit-trail, trust-tier, contract, validation, state-management, or integration bug whose primary fix belongs in this file.

## Root Cause Hypothesis

No bug identified.

## Suggested Fix

No code change recommended in /home/john/elspeth/src/elspeth/contracts/schema_contract_factory.py.

## Impact

No confirmed breakage attributable to this file from the audited paths. Residual risk is limited to untested future call sites that might pass inconsistent `field_resolution` data, but current in-repo callers normalize and collision-check that input before invoking the factory.
