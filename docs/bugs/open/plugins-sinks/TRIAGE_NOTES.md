# Plugins-Sinks Bug Triage Notes (2026-02-14)

## Summary Table

| # | Bug | File | Original | Triaged | Verdict |
|---|-----|------|----------|---------|---------|
| 1 | CSVSink partial batch write before raising | csv_sink.py | P1 | P1 | Confirmed |
| 2 | DatabaseSink silently accepts schema-invalid rows (validate_input=False) | database_sink.py | P1 | P2 | Downgraded |
| 3 | Header display mapping collisions in JSONSink overwrite fields | json_sink.py | P1 | P1 | Confirmed |
| 4 | JSONSink append mode without schema validation | json_sink.py | P1 | P2 | Downgraded |
| 5 | Schema type `any` mapped to SQL Text without serialization | database_sink.py | P1 | P1 | Confirmed |
| 6 | DROP/CREATE TABLE without ctx.record_call instrumentation | database_sink.py | P2 | P2 | Confirmed |

**Result:** 3 confirmed at original priority (2 P1, 1 P2), 2 downgraded (P1 to P2), 0 closed.

## Detailed Assessments

### Bug 1: CSVSink partial batch write (P1 confirmed)

Genuine P1. The `write()` method at `csv_sink.py:272-274` iterates rows one-by-one via `writer.writerow(row)`. If row N in a batch causes `DictWriter` to raise (e.g., unexpected extra fields with `extrasaction='raise'`), rows 0..N-1 are already written to the file. The sink executor (`sink.py:215-226`) then marks ALL token states as FAILED and re-raises, but the CSV file contains partial output. This creates a divergence between the audit trail (all tokens FAILED, no artifact) and the physical file (partially written rows). This violates the core auditability guarantee that recorded terminal states match actual artifacts.

The fix (stage to `io.StringIO` buffer, validate all rows before file write) is straightforward and contained within csv_sink.py.

### Bug 2: DatabaseSink validate_input=False defaults (P1 -> P2)

The gap is real: with `validate_input=False` (the default), rows bypass `model_validate()` and go straight to `conn.execute(insert(...), rows)` at `database_sink.py:352`. Extra keys are silently ignored by SQLAlchemy, and missing required fields become NULL.

**However, the practical impact is limited by two factors:**

1. **Tier 2 trust model:** Sinks receive pipeline data that has already been validated by the source (Tier 3 -> Tier 2 boundary). Wrong types at the sink indicate an upstream plugin bug, which is a systemic issue that would manifest across all sinks, not just DatabaseSink.

2. **Schema enforcement exists at other layers.** `CSVSink` uses `DictWriter(extrasaction='raise')` to catch extras and has explicit `_validate_required_fields_present()`. DatabaseSink's lack of these is an asymmetry, not a P1 data integrity gap, because the upstream schema contract should already be enforcing field presence and type correctness.

The fix (enforce required-field checks like CSVSink does, reject extras in fixed mode) is correct and worth implementing for defense-in-depth. But the default `validate_input=False` is a conscious design choice documented in the codebase, not an oversight. Downgraded to P2.

### Bug 3: JSONSink header display mapping collisions (P1 confirmed)

Genuine P1. `_apply_display_headers` at `json_sink.py:549` uses a dict comprehension `{display_map.get(k, k): v for k, v in row.items()}`. When two different source keys map to the same display name (non-injective mapping), the later key silently overwrites the earlier one. The config validator at `config_base.py:226-244` does not check uniqueness of mapping values.

This is especially dangerous because the sink executor records token output using the original (pre-display-mapping) row data (`sink.py:262`), so the audit trail shows both fields present while the actual artifact only contains one. This is a direct audit integrity violation.

**Cross-reference:** This bug is related to `plugins/P1-sinkpathconfig-header-mapping-collision` which addresses the config_base.py validation gap. They have different root causes (this one is the runtime dict comprehension behavior; the other is the missing config-time validation). Both should remain open as complementary fixes -- the config-time validation prevents the configuration, and the runtime detection is defense-in-depth.

### Bug 4: JSONSink append mode without schema validation (P1 -> P2)

The gap is real: `_write_jsonl_batch()` at `json_sink.py:309-321` opens the file in append mode without calling `validate_output_target()`, unlike CSVSink which validates headers before appending (`csv_sink.py:340-352`). However:

1. **Append mode in normal runs is uncommon.** The default mode is `"write"` (`json_sink.py:43`). Append mode is primarily used during resume, where `validate_output_target()` IS called by the CLI resume path (`cli.py:1769`).

2. **JSONL format is inherently schema-flexible.** Unlike CSV (which has a fixed header row that must match), JSONL records are self-describing JSON objects. Appending records with different schemas produces valid JSONL that can be consumed by schema-aware readers. The "schema drift" is less catastrophic than the CSV equivalent.

3. **The configuration required is explicit.** A user must set both `mode: append` AND have a pre-existing file with different schema to trigger this. This is not an accidental path.

The fix (call `validate_output_target()` before first append write) mirrors CSVSink behavior and is a clear improvement. Downgraded to P2 because the blast radius and likelihood are limited.

### Bug 5: Schema type `any` mapped to SQL Text crashes on dict/list (P1 confirmed)

Genuine P1. `SCHEMA_TYPE_TO_SQLALCHEMY` at `database_sink.py:39` maps `"any": Text`. When a row contains a dict or list value for an `any`-typed field, `conn.execute(insert(...), rows)` at line 352 passes the Python dict/list directly to the SQL driver, which raises `InterfaceError` (sqlite: "type 'dict' is not supported").

This is a real crash on valid pipeline data. The schema contract explicitly allows `any` to hold nested values (dicts, lists), and sources/transforms can legitimately produce such data. The crash occurs in the sink, not upstream, so it's not preventable by upstream validation. The fix (serialize non-scalar `any` values to JSON strings before insert, or reject `any` at config time for DatabaseSink) is required.

### Bug 6: DROP/CREATE TABLE without audit instrumentation (P2 confirmed)

Real gap. `_drop_table_if_exists()` at `database_sink.py:245-263` and `_metadata.create_all()` at line 243 execute DDL operations outside the `ctx.record_call()` instrumentation block. Only INSERT has call-level audit recording (lines 348-383). If DROP or CREATE fails, the exception propagates without a corresponding call record in the Landscape.

P2 is appropriate. DDL failures are rare and the operation-level error from the executor still captures the failure. The missing call-level granularity is an observability gap, not a data integrity issue.

## Cross-Cutting Observations

### 1. CSVSink and JSONSink have asymmetric append-mode validation

CSVSink validates schema compatibility before appending (lines 340-352). JSONSink does not. Both should have consistent behavior. Bug 4 addresses the JSONSink gap, but the fix should also add integration tests that verify both sinks behave identically in append mode.

### 2. DatabaseSink has no defensive field validation

Unlike CSVSink (which uses DictWriter's `extrasaction='raise'` and has `_validate_required_fields_present()`), DatabaseSink relies entirely on optional `validate_input` and SQLAlchemy's implicit behavior. Bugs 2 and 5 both stem from this gap. Fixing both together as a "DatabaseSink field validation" effort would be efficient.

### 3. Display header collision affects multiple sinks

Bug 3 (JSONSink collision) and the cross-referenced `plugins/P1-sinkpathconfig-header-mapping-collision` affect the same logical issue at different layers. CSVSink is also affected by the same `_apply_display_headers` pattern (it has its own display header implementation). A comprehensive fix should address config-time validation (config_base.py) plus runtime guards in both sinks.
