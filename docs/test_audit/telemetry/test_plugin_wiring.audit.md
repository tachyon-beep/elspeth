# Audit: tests/telemetry/test_plugin_wiring.py

## Summary
**Lines:** 150
**Test Classes:** 1 (TelemetryWiring)
**Quality:** EXCELLENT - Critical regression guard for telemetry wiring

## Findings

### Strengths

1. **Plugin Discovery Test** (Lines 121-150)
   - Scans all Python files in plugins/ for AuditedLLMClient/AuditedHTTPClient usage
   - Verifies all plugins are either in EXTERNAL_CALL_PLUGINS, TELEMETRY_EXEMPT_PLUGINS, or CLIENT_DEFINITION_FILES
   - **CRITICAL**: Will fail if new plugin added without telemetry consideration

2. **Explicit Plugin Registry** (Lines 18-57)
   - Documents every plugin that makes external calls
   - Documents pattern used (on_start_capture vs ctx_passthrough)
   - Documents client type used

3. **Exempt Plugins With Reasons** (Lines 59-63)
   - `azure_batch.py` - "Batch API - uses file uploads, not per-row calls"
   - `openrouter_batch.py` - "Batch API - uses file uploads, not per-row calls"
   - Forces explicit documentation of exemptions

4. **Source Code Inspection** (Lines 81-119)
   - Reads actual source code to verify patterns
   - Tests `on_start_capture` pattern: checks for `self._run_id` or `ctx.run_id`
   - Tests `ctx_passthrough` pattern: checks for direct ctx usage
   - Verifies `run_id=` and `telemetry_emit=` passed to client

### Test Design Excellence

This is a **regression prevention** test, not a behavior test:
- Doesn't test telemetry actually works
- Tests that the wiring is present
- Catches "forgot to wire up telemetry" bugs

### Minor Issues

1. **File Path Strings** (Lines 21-56)
   - Hardcoded paths like `"src/elspeth/plugins/llm/azure.py"`
   - Will break if files are moved
   - But will fail loudly (file not found), so acceptable

2. **Pattern Detection is String-Based**
   - `"self._run_id" in source` could have false positives
   - Unlikely in practice given specific variable names

### Maintenance Burden

When adding a new external-call plugin:
1. Add to EXTERNAL_CALL_PLUGINS with pattern
2. Or add to TELEMETRY_EXEMPT_PLUGINS with reason
3. Test will fail until documentation added

This is **intentional friction** to ensure telemetry consideration.

## Verdict
**PASS** - Excellent regression guard. This test ensures no plugin slips through without telemetry consideration.
