# WP1 – Spreadsheet/CSV Output Mitigation

## Objectives
- Neutralise spreadsheet formula injection across all CSV/Excel artifacts.
- Maintain automation compatibility via configurable guard characters and opt-out controls.
- Propagate sanitation metadata for downstream auditing.

## Adjusted Scope
- Sanitize leading formula-triggering characters (`=`, `+`, `-`, `@`, tab, carriage return, newline, single quote) after trimming BOM markers.
- Default escape strategy: prefix a single-character guard (apostrophe `'`) that preserves cell content while preventing evaluation.
- Sanitize headers, manifest summaries, and any value destined for CSV/Excel, ensuring idempotency (no double prefix).
- Expose `sanitize_formulas` (default `True`) and `sanitize_guard` options on `ExcelResultSink`, `CsvResultSink`, and the CSV branch of `LocalBundleSink`; record choices in manifest metadata.
- Add compatibility validation for common consumers (Excel, LibreOffice, Python `csv`, pandas).

## Implementation Plan
1. **Helper Module**
   - Create `elspeth/plugins/outputs/_sanitize.py` with pure functions: `should_sanitize`, `sanitize_cell`, optional `aggressive` flag.
   - Document guard behaviour (default `'`, configurable), handle Unicode safely, and ensure helper is no-op for non-string inputs.
2. **Sink Integration**
   - Thread `sanitize_formulas` and `sanitize_guard` through `ExcelResultSink`, `CsvResultSink`, `LocalBundleSink`.
   - Apply sanitation to row data, headers, and manifest fields before emission.
   - Emit WARN log when sanitization disabled to highlight security implications.
3. **Schema & Metadata**
   - Update configuration schemas to accept new options with validation (guard must be length 1).
   - Extend manifest metadata to capture sanitation status/guard; ensure `LocalBundle` manifest reflects per-artifact settings.
4. **Compatibility Matrix**
   - Add `scripts/compatibility/run_sanitization_matrix.py` to exercise sanitized outputs with Excel (via `xlwings` stub), LibreOffice CLI, pandas, and Python `csv`.
   - Capture results in `docs/notes/sanitization_compat.md` for audit trail.
5. **Risk Reduction Activities**
   - Add CI target (`tox -e sanitization-matrix`) wrapping the compatibility script; gate merges on pass/failure.
   - Create reusable pytest fixture (`assert_sanitized_artifact`) that inspects generated CSV/Excel outputs for unsanitized prefixes and integrates with sink tests.
   - Wire manifest metadata assertions into integration tests to guarantee every artifact advertises sanitation settings.
   - Emit structured WARN log and metrics counter when sanitization is disabled, enabling telemetry and alerting hooks.

## Risk Assessment
| Risk | Likelihood | Impact | Rating | Risk Reduction / Controls |
| --- | --- | --- | --- | --- |
| Sanitized outputs break downstream consumers that cannot handle leading apostrophes or custom guards. | Medium | High | High | Compatibility matrix CI gate, guard override option, release notes and docs guiding consumers to alternative guards. |
| Some export path bypasses sanitation (e.g., headers, manifests, non-string values). | Medium | Critical | High | Shared fixture enforcing sanitized prefixes, manifest metadata assertions, comprehensive unit coverage on helper and sinks. |
| Sanitization introduces material performance regression on large exports. | Low | Medium | Medium | Microbenchmarks in CI, helper optimized for minimal allocations, regression detection via baseline comparison. |
| Operators disable sanitization (opt-out) in production, reintroducing injection risk. | Low | Critical | High | WARN log with telemetry counter, secure-mode policy collaboration (WP6), documentation emphasising risk, optional monitoring dashboard. |
| Guard character misconfiguration (empty/multi-length) leads to broken exports or partial protection. | Low | High | Medium | Schema validation enforcing single-character guard, defaults documented, automated tests covering override edge cases. |

## Testing & Validation
- Unit tests (`tests/plugins/outputs/test_sanitize.py`): ASCII/Unicode, whitespace, existing apostrophe, guard overrides, idempotency, numeric-only values.
- Sink tests (`tests/plugins/outputs/test_outputs_csv.py`, `test_outputs_excel.py`, `test_outputs_local_bundle.py`): parameterize sanitize on/off, guard variations, metadata assertions, downgrade behaviour.
- Integration test (`tests/integration/test_sample_suite_outputs.py`): run sample suite, verify manifests mark sanitation and sanitized CSV loads via pandas without formula execution.
- Microbenchmarks (optional `pytest --benchmark-only`) to quantify helper overhead on large datasets.
- Manual validation: `make sample-suite`, inspect artifacts in Excel and LibreOffice to confirm expected apostrophe display and formula bar behaviour.

## Documentation Deliverables
- README updates covering default sanitization, guard overrides, and opt-out risks.
- `docs/end_to_end_scenarios.md` additions outlining sanitation expectations and manifest excerpts.
- `docs/notes/sanitization_compat.md` summarising compatibility findings.
- Release notes entry describing new defaults and upgrade guidance.

## Dependencies & Coordination
- Coordinate with WP6 schema updates to align validation/secure-mode requirements.
- Sync with documentation owners for README and scenario updates.
- Engage QA for compatibility matrix execution post-merge.
