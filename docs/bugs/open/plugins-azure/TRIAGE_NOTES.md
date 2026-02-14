# Plugins-Azure Bug Triage Notes (2026-02-14)

## Summary Table

| # | Bug | File | Original | Triaged | Verdict |
|---|-----|------|----------|---------|---------|
| 1 | AzureAuthConfig accepts invalid mixed auth config with partial SP fields | auth.py | P1 | P2 | Downgraded |
| 2 | Azure Blob Sink misses required field validation | blob_sink.py | P1 | P2 | Downgraded |
| 3 | blob_source.load re-wraps Azure exceptions with type(e) which can fail | blob_source.py | P1 | P1 | Confirmed |
| 4 | JSONL decode failures raise ValueError instead of quarantining | blob_source.py | P1 | P1 | Confirmed |
| 5 | JSON structure errors recorded with schema_mode="structure" | blob_source.py | P2 | P2 | Confirmed |
| 6 | On post-upload audit-recording failure, AzureBlobSink records incorrect request metadata | blob_sink.py | P2 | P2 | Confirmed |

**Result:** 2 confirmed at original priority (1 P1, 1 P2), 2 downgraded (P1 to P2), 2 confirmed as-is (P2).

## Detailed Assessments

### Bug 1: AzureAuthConfig mixed auth config with partial SP fields (P1 -> P2)

The analysis is technically correct: setting `connection_string` + `tenant_id` + `client_id` + `client_secret` (without `account_url`) passes validation with `active_count=1` and `sp_field_count=3`, bypassing the partial-SP check. However, examining the actual impact, this is a config-time validation gap, not a runtime data corruption or audit integrity issue. The runtime correctly uses `connection_string` path (which is what would work anyway since `account_url` is missing). The user's intent is ambiguous in this scenario -- they may genuinely want connection string auth with stale SP fields in their config. More importantly, this requires a very specific invalid combination and the blast radius is limited to a confusing config acceptance. The fix is straightforward (include `account_url` in SP field count). Downgraded to P2 because it is a validation completeness issue, not a correctness or data integrity issue.

### Bug 2: Azure Blob Sink misses required field validation (P1 -> P2)

The bug is real: `AzureBlobSink` does not call `_validate_required_fields_present()` or equivalent before serialization, unlike `CSVSink` which does. However, this is a Tier 2 concern -- sinks receive pipeline data that has already been validated by the source and passed through transforms. If a required field is missing at the sink, that is an upstream plugin bug per the project's trust model. The project's own documentation in `blob_sink.py` lines 6-7 says: "Sinks use allow_coercion=False - wrong types are upstream bugs. This is NOT the trust boundary (Sources are). Sinks receive PIPELINE DATA." Adding the validation would be defense-in-depth hardening consistent with what `CSVSink` does, but the missing check is not a P1 correctness gap because the upstream contract should prevent this state. Downgraded to P2.

### Bug 3: blob_source.load re-wraps exceptions with type(e) (P1 confirmed)

Genuine P1. The `type(e)(...)` pattern on line 446 can fail for Azure SDK exceptions with multi-parameter constructors (e.g., `HttpResponseError`, `ResourceNotFoundError`). This is not theoretical -- the sister plugin `blob_sink.py` explicitly documents this hazard at line 641 and avoids it using `RuntimeError`. When the re-wrapping fails, the original Azure exception is masked by a secondary `TypeError`, making the actual failure undiagnosable. The fix is a one-liner (`RuntimeError` instead of `type(e)`) but the impact on operator debuggability is significant.

### Bug 4: JSONL decode failures raise ValueError instead of quarantining (P1 confirmed)

Genuine P1. `_load_jsonl()` at line 673 raises `ValueError` on `UnicodeDecodeError`, which crashes the entire run. This violates the Tier 3 trust model: source-boundary encoding failures should be quarantined and recorded, not crash the pipeline. The sibling method `_load_json_array()` in the same file correctly quarantines decode failures at line 620-624 using `schema_mode="parse"`. The baseline `JSONSource` also quarantines encoding errors at line 226-238. This is a clear inconsistency within the same file and contradicts documented trust model behavior.

### Bug 5: JSON structure errors recorded with schema_mode="structure" (P2 confirmed)

Confirmed P2. The `_load_json_array()` method uses `schema_mode="structure"` at lines 637, 641, and 647, but the contract (documented at `plugin_context.py:405` and the schema column comment at `schema.py:411`) specifies allowed values as `"fixed"`, `"flexible"`, `"observed"`, or `"parse"`. The value `"structure"` is non-canonical and will cause downstream queries/reports that filter on known schema_mode values to miss these records. The fix is trivial (change to `"parse"` which is the correct mode for file/structure boundary errors) but the impact is real for audit consistency.

### Bug 6: AzureBlobSink records incorrect overwrite metadata on error path (P2 confirmed)

Confirmed P2. The error path at line 628 recomputes `self._overwrite or self._has_uploaded` after `_has_uploaded` was set to `True` on line 587, so the error record can claim `overwrite=True` when the actual upload used `overwrite=False`. This is a factual audit trail inaccuracy. The path is reachable (post-upload `record_call` success path failure falls through to the error handler). The fix is straightforward: capture `upload_overwrite` before the `try` block and reuse it in both paths.

## Cross-Cutting Observations

### 1. Trust boundary consistency gap in blob_source.py

Bugs 4 and 5 both stem from inconsistent trust-boundary handling within `blob_source.py`. The JSON array path (`_load_json_array`) properly quarantines parse failures but uses a non-canonical schema_mode label. The JSONL path (`_load_jsonl`) doesn't quarantine at all for encoding failures. Both should be fixed together to bring the entire file into alignment with the trust model and the canonical `json_source.py` implementation.

### 2. Error-path metadata must be captured before mutation

Bug 6 illustrates a general pattern where error-path audit metadata is recomputed from mutable state instead of using the values that were active at call time. Any audit recording in an `except` block should use pre-captured variables, not re-derived state. This pattern should be checked across all plugins that record calls with mutable request metadata.
