## Summary

Group `core/config.py` (1,747 lines) Settings classes into submodules. Contains 17 Pydantic Settings classes plus 9 utility functions. Logical groupings exist: settings models, template expansion, environment variable expansion.

## Severity

- Severity: minimal
- Priority: P4
- Type: task
- Status: open
- Bead ID: elspeth-rapid-0984

## Details

Current organization is workable but would benefit from submodule structure as the config surface area grows.

## Blocked By

- `w2q7` — ELSPETH-NEXT (deferred to post-RC3)

## Affected Subsystems

- `core/config.py`
