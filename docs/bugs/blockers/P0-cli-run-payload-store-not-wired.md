# Bug Report: CLI `run` Command Does Not Wire PayloadStore

## Summary

- The `elspeth run` command does not instantiate or pass a PayloadStore to the engine, causing source row payloads to never be persisted. This violates the core audit requirement that raw source data must be stored before any processing.

## Severity

- Severity: critical
- Priority: P0 (RC-1 Blocker)

## Reporter

- Name or handle: Release Validation Analysis
- Date: 2026-01-29
- Related run/issue ID: CLI-016, CFG-039

## Environment

- Commit/branch: fix/P2-aggregation-metadata-hardcoded
- OS: Linux
- Python version: 3.12+
- Config profile / env vars: Any
- Data set or fixture: Any pipeline using `elspeth run`

## Agent Context (if relevant)

- Goal or task prompt: RC-1 release validation - identify blockers
- Model/version: Claude Opus 4.5
- Tooling and permissions: Read-only analysis
- Determinism details: N/A
- Notable tool calls or steps: Cross-referenced requirements.md, RC1-remediation.md, cli.py

## Steps To Reproduce

1. Create any valid pipeline configuration
2. Run `elspeth run -s settings.yaml --execute`
3. After completion, query the audit database for source row payloads
4. Check `source_rows.source_data_ref` column

## Expected Behavior

- `source_data_ref` should contain a reference to the stored payload
- PayloadStore filesystem directory should contain the raw source data
- `explain_token()` should return full source row data

## Actual Behavior

- `source_data_ref` is NULL or empty
- PayloadStore directory may not exist or be empty
- `explain_token()` returns hash but no payload data
- Source row data is lost after processing

## Evidence

- `src/elspeth/cli.py:269-396` - `_execute_pipeline()` does not create PayloadStore
- `src/elspeth/cli.py:720-880` - `resume` command DOES create PayloadStore (line 925)
- `src/elspeth/cli.py:466-595` - `purge` command DOES create PayloadStore (line 632)
- `src/elspeth/engine/orchestrator.py:406` - `run()` accepts `payload_store` parameter
- `src/elspeth/engine/tokens.py:73-95` - TokenManager stores payloads when payload_store provided

## Impact

- User-facing impact: Cannot retrieve original source data after pipeline completion
- Data integrity / security impact: **VIOLATES CORE AUDIT REQUIREMENT** - "Source entry - Raw data stored before any processing" (CLAUDE.md)
- Performance or cost impact: None

## Root Cause Hypothesis

- The `run` command was implemented before PayloadStore was fully integrated
- `resume` command was updated to wire PayloadStore, but `run` was not
- No integration test catches this because tests may wire PayloadStore directly

## Proposed Fix

- Code changes (modules/files):
  ```python
  # src/elspeth/cli.py - in _execute_pipeline(), before orchestrator.run()

  # Create PayloadStore from config
  payload_store = None
  if config.payload_store and config.payload_store.enabled:
      from elspeth.core.payload_store import FilesystemPayloadStore
      payload_store = FilesystemPayloadStore(
          base_path=Path(config.payload_store.path),
          retention_days=config.payload_store.retention_days,
      )

  # Pass to orchestrator
  result = orchestrator.run(
      ...,
      payload_store=payload_store,
  )
  ```

- Config or schema changes: None (PayloadStoreSettings already exists)

- Tests to add/update:
  - Add integration test: `test_cli_run_persists_source_payloads`
  - Test should verify `source_data_ref` is populated after `elspeth run`

- Risks or migration steps:
  - Low risk - additive change
  - Existing runs without payloads remain valid (hash still recorded)

## Architectural Deviations

- Spec or doc reference: CLAUDE.md "Data storage points (non-negotiable)" - "Source entry - Raw data stored before any processing"
- Observed divergence: `run` command does not store raw data
- Reason (if known): Implementation gap - `resume` was updated but `run` was not

## Verification Criteria

- [ ] `elspeth run` creates PayloadStore when configured
- [ ] `source_rows.source_data_ref` populated for all rows
- [ ] `explain_token()` returns full source data
- [ ] Integration test proves end-to-end payload persistence

## Cross-References

- RC1-remediation.md: CFG-039, CLI-016
- requirements.md: CFG-039, CLI-016, PLD-006
- docs/release/rc1-checklist.md: Section 1.1, 3.1
