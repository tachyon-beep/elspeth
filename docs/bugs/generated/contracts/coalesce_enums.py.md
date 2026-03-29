## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/contracts/coalesce_enums.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/contracts/coalesce_enums.py
- Line(s): 11-25
- Function/Method: Module-scope enum definitions (`CoalescePolicy`, `MergeStrategy`)

## Evidence

`/home/john/elspeth/src/elspeth/contracts/coalesce_enums.py:11-25` defines two small `StrEnum` types with values:
- `CoalescePolicy`: `require_all`, `quorum`, `best_effort`, `first`
- `MergeStrategy`: `union`, `nested`, `select`

Those values match the validated config contract in `/home/john/elspeth/src/elspeth/core/config.py:713-718`, where `CoalesceSettings.policy` and `CoalesceSettings.merge` use the same literal strings. Production code converts settings into these enums at runtime in `/home/john/elspeth/src/elspeth/engine/coalesce_executor.py:743-745` and also at other coalesce metadata construction sites (`405`, `552`, `624-625`), so any drift here would surface immediately as a `ValueError`.

The repository also has direct tests for this module in `/home/john/elspeth/tests/unit/contracts/test_coalesce_enums.py:6-50`, including member-set checks, literal-value checks, round-trip construction, and invalid-value rejection. Integration/property coverage exercises real usage through coalesce metadata in `/home/john/elspeth/tests/property/engine/test_coalesce_properties.py:702-725` and canonical serialization in `/home/john/elspeth/tests/property/contracts/test_context_canonical.py:83-91`.

I did not find a contract mismatch, audit-trail omission, tier-model violation, or untested value path whose primary fix belongs in `coalesce_enums.py`.

## Root Cause Hypothesis

No bug identified

## Suggested Fix

No fix necessary based on the current code and verified call sites.

## Impact

No confirmed breakage from this file. The enum definitions appear internally consistent with configuration validation, executor usage, audit metadata serialization, and existing tests.
