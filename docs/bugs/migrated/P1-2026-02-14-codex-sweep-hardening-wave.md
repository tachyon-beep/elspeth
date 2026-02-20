## Summary

Cross-cutting P0/P1 hardening wave from full codex sweep (2026-02-13). Umbrella tracking bead for the remaining fix backlog after initial P0/P1 patches landed on RC3.1-bug-hunt.

## Severity

- Severity: critical
- Priority: P1
- Status: in_progress
- Bead ID: elspeth-rapid-9zwn

## Context

Initial fixes completed:
- P0 recovery mixed buffered/non-buffered token row-drop in RecoveryManager.get_unprocessed_rows
- P1 operation payload hash/ref loss for explicit empty payloads in CallRecordingMixin

## Remaining Prioritized Backlog

### 1. Core/Contracts
- Node-state terminal invariant enforcement in `core/landscape/_node_state_recording.py`
- `load_settings` unknown-key fail-closed behavior in `core/config.py`

### 2. Engine
- Executor terminality guarantees (gate/transform/sink/aggregation post-processing failures)
- MockClock NaN/inf/backward-time guards

### 3. CLI/MCP
- CLI retention-days >0 guard and resume DB path validation
- MCP call_tool error signaling and analyzer input validation

### 4. Plugins
- AzureBlobSink required-field validation before write
- OpenRouterBatch success/failure demarcation when row contains "error" key

## Acceptance Criteria

- Fixes landed with focused unit/integration regressions for each item
- Subset prioritized by audit-integrity impact first
- Track completed items and close when queue is exhausted or split into child issues

## Affected Subsystems

- `core/landscape/`, `core/config.py`
- `engine/executors/`, `engine/clock.py`
- `cli.py`, `mcp/server.py`
- `plugins/sinks/`, `plugins/llm/`
