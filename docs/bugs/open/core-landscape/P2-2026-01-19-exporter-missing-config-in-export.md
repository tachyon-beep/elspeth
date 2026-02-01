# Bug Report: LandscapeExporter export is not self-contained (run/node config JSON omitted)

## Summary

- The exporter is described as producing audit data “suitable for compliance review and legal inquiry”.
- `LandscapeExporter` currently exports:
  - `runs.config_hash` but not `runs.settings_json`
  - `nodes.config_hash` but not `nodes.config_json` (nor determinism/schema config fields)
- This makes exported audit trails less useful outside the originating system because configuration required for traceability is missing.

## Severity

- Severity: major
- Priority: P2

## Reporter

- Name or handle: codex
- Date: 2026-01-19
- Related run/issue ID: N/A

## Environment

- Commit/branch: `main` @ `8ca061c9293db459c9a900f2f74b19b59a364a42`
- OS: Linux (Ubuntu kernel 6.8.0-90-generic)
- Python version: 3.13.1
- Config profile / env vars: N/A
- Data set or fixture: N/A

## Agent Context (if relevant)

- Goal or task prompt: deep dive subsystem 4 (Landscape) and create bug tickets
- Model/version: GPT-5.2 (Codex CLI)
- Tooling and permissions (sandbox/approvals): workspace-write, network restricted, approvals on-request
- Determinism details (seed, run ID): N/A
- Notable tool calls or steps: static inspection of export record mappings

## Steps To Reproduce

1. Create any run and nodes (normal pipeline execution).
2. Export the run via `LandscapeExporter.export_run(run_id)`.
3. Observe that:
   - the `run` record lacks `settings_json`
   - the `node` record lacks `config_json`

## Expected Behavior

- Exported audit trail contains the resolved configuration needed to explain decisions:
  - `runs.settings_json`
  - `nodes.config_json`
  - (optionally) node determinism, schema_mode/schema_fields

## Actual Behavior

- Export includes hashes but omits the underlying config JSON payloads.

## Evidence

- Exporter omits settings/config JSON:
  - `src/elspeth/core/landscape/exporter.py:162-185` (`run` record omits `settings_json`)
  - `src/elspeth/core/landscape/exporter.py:173-185` (`node` record omits `config_json`)
- Schema stores these values explicitly:
  - `src/elspeth/core/landscape/schema.py` (`runs.settings_json`, `nodes.config_json`)
- Audit standard requires configuration traceability:
  - `CLAUDE.md` (“Every decision must be traceable to … configuration …”)

## Impact

- User-facing impact: exported audit trail may be insufficient for third-party review without separate access to the original config artifacts.
- Data integrity / security impact: moderate (export incompleteness).
- Performance or cost impact: including config JSON may increase export size; needs explicit decision.

## Root Cause Hypothesis

- Exporter was implemented with a minimal record schema and hasn’t been revisited for “portable audit trail” requirements.

## Proposed Fix

- Code changes (modules/files):
  - Decide export contract:
    - If “self-contained export” is required: include `settings_json` and `config_json` in export records.
    - If not: explicitly document that exported audit trails require separate config artifacts.
  - `src/elspeth/core/landscape/exporter.py` add fields accordingly.
- Config or schema changes: none.
- Tests to add/update:
  - Add exporter tests asserting config JSON presence (if desired behavior).
- Risks or migration steps:
  - Export size growth; may require optional inclusion controlled by config (`landscape.export.include_config_json`).

## Architectural Deviations

- Spec or doc reference: `CLAUDE.md` auditability standard
- Observed divergence: export not portable/self-contained for config traceability.
- Reason (if known): minimal initial exporter schema.
- Alignment plan or decision needed: decide portability requirements for exported audit artifacts.

## Acceptance Criteria

- A documented and tested decision exists:
  - either export includes resolved config JSON, or docs clearly state export is hash-only for config and requires separate artifacts.

## Tests

- Suggested tests to run: `pytest tests/core/landscape/test_exporter.py`
- New tests required: maybe (depends on decision)

## Notes / Links

- Related issues/PRs: N/A

## Verification (2026-02-01)

**Status: STILL VALID**

- `export_run()` still emits `config_hash` but omits `settings_json` and `config_json` for run/node records. (`src/elspeth/core/landscape/exporter.py:163-186`)

## Verification (2026-01-25)

**Status: STILL VALID**

Verified against current codebase on branch `fix/rc1-bug-burndown-session-4`.

### Current State

The bug is **confirmed and still present**. The database schema and recorder correctly store and retrieve configuration data, but the exporter deliberately excludes it from exported records.

**Evidence:**

1. **Database schema correctly defines config fields** (`src/elspeth/core/landscape/schema.py`):
   - Line 34: `runs.settings_json` (Text, nullable=False)
   - Line 59: `nodes.config_json` (Text, nullable=False)
   - Additional node fields also available: `determinism`, `schema_mode`, `schema_fields_json`

2. **Recorder correctly populates and retrieves config data**:
   - `recorder.get_run()` returns `Run` model with `settings_json` (line 360)
   - `recorder._row_to_node()` returns `Node` model with `config_json` (line 642)

3. **Exporter deliberately omits config fields** (`src/elspeth/core/landscape/exporter.py`):
   - Lines 162-171: Run export includes `config_hash` but NOT `settings_json`
   - Lines 173-185: Node export includes `config_hash` but NOT `config_json`, `determinism`, or schema fields

4. **Tests do not validate config field presence** (`tests/core/landscape/test_exporter.py`):
   - Lines 69-79: Test checks for "required fields" but only lists: `run_id`, `status`, `started_at`, `completed_at`, `canonical_version`, `config_hash`
   - No test validates presence of `settings_json` or `config_json` in exports

### Git History

No commits since the bug report date (2026-01-19) have addressed this issue:
- Searched for commits mentioning `settings_json`, `config_json`, or export config fields: **none found**
- Recent exporter changes (commit `0f21ecb`) only added PENDING status handling for node states

### Impact Assessment

This is a **genuine portability gap** for audit trail exports:

- **Hash verification is possible** (config_hash present), but hash reversal is impossible
- **Third-party auditors** cannot see the actual configuration that drove decisions
- **Forensic analysis** requires access to the original database, defeating the purpose of "export for compliance review"
- **Alignment with CLAUDE.md**: Violates "Every decision must be traceable to source data, configuration, and code version"

### Recommendation

This requires an **architectural decision**, not just a bug fix:

**Option 1: Full portability** - Include `settings_json`, `config_json`, and schema fields in exports
- Pros: Self-contained audit trail for legal/compliance review
- Cons: Larger export size (config JSON can be substantial)

**Option 2: Hash-only with documentation** - Keep current behavior, explicitly document limitation
- Pros: Smaller exports, no code changes
- Cons: Exports are not self-contained, requires original database for full audit

**Option 3: Configurable inclusion** - Add `include_config: bool` parameter to `export_run()`
- Pros: Flexibility for different use cases
- Cons: More complex API, config decision burden on users

Given the "suitable for compliance review and legal inquiry" docstring claim, **Option 1 or 3** appears most aligned with stated intent.
