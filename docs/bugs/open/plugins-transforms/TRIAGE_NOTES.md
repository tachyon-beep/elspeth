# Plugins-Transforms Bug Triage Notes (2026-02-14)

## Summary Table

| # | Bug | File | Original | Triaged | Verdict |
|---|-----|------|----------|---------|---------|
| 1 | analyze_content accepts bool/out-of-range severity | content_safety.py | P1 | P1 | Confirmed |
| 2 | analyze_prompt accepts empty documentsAnalysis as clean | prompt_shield.py | P1 | P1 | Confirmed |
| 3 | AzureContentSafety _process_row retry-time race on ctx.state_id | content_safety.py | P1 | P1 | Confirmed |
| 4 | Prompt shield accepts fields=[] and returns validated | prompt_shield.py | P1 | P1 | Confirmed |
| 5 | BatchReplicate accepts bool in copies_field | batch_replicate.py | P1 | P2 | Downgraded |
| 6 | BatchReplicate has no upper bound on copies | batch_replicate.py | P1 | P2 | Downgraded |
| 7 | FieldMapper allows target-name collisions | field_mapper.py | P1 | P1 | Confirmed |
| 8 | group_by can overwrite computed aggregate fields | batch_stats.py | P1 | P1 | Confirmed |
| 9 | JSONExplode infers output_field type from first row only | json_explode.py | P1 | P2 | Downgraded |
| 10 | JSONExplode silently overwrites existing field on collision | json_explode.py | P1 | P1 | Confirmed |
| 11 | KeywordFilterConfig accepts empty/blank fields | keyword_filter.py | P1 | P1 | Confirmed |
| 12 | KeywordFilterConfig allows empty regex entries | keyword_filter.py | P1 | P2 | Downgraded |
| 13 | bool values accepted as numeric in BatchStats | batch_stats.py | P2 | P2 | Confirmed |

**Result:** 7 confirmed at P1, 2 confirmed at P2, 4 downgraded (3 P1 to P2, 1 already P2), 0 closed.

## Detailed Assessments

### Bug 1: analyze_content accepts bool/out-of-range severity (P1 confirmed)

Genuine P1. `_analyze_content` at `content_safety.py:507` uses `isinstance(item["severity"], int)` which accepts `bool` values (`isinstance(True, int)` is True in Python). `False` evaluates as 0, which is below any non-zero threshold, causing the content to pass as safe. Additionally, negative integers like `-1` pass the check and are also below all thresholds, creating another fail-open path.

This is a Tier 3 external boundary validation gap in a security-critical transform. Azure API responses are external data that must be validated strictly. The fix (`type(severity) is not int or not (0 <= severity <= 6)`) is a one-liner and directly addresses the fail-open risk.

### Bug 2: analyze_prompt accepts empty documentsAnalysis as clean (P1 confirmed)

Genuine P1. When `analysis_type` is `"both"` or `"document"`, the request sends one document (`[text]`) at `prompt_shield.py:447-450`. But the response validation at lines 484-497 only checks that `documentsAnalysis` is a list and validates items within it. An empty list `[]` passes the `isinstance(..., list)` check, the `for` loop body never executes, and `doc_attack` remains `False`. The function returns `"document_attack": False` at line 501.

This is a cardinality violation at a Tier 3 boundary: we sent 1 document, the response claims 0 document analyses, and we treat that as "clean." A malformed or degraded Azure response could cause prompt injection content to pass validation.

### Bug 3: AzureContentSafety retry-time race on ctx.state_id (P1 confirmed)

Genuine P1. `_process_row` at `content_safety.py:283-297` reads `ctx.state_id` twice: once at line 288 to pass to `_process_single_with_state`, and again at line 292 in the `finally` block for HTTP client cleanup. Between these two reads, a retry path can reassign `ctx.state_id` via `transform.py:188` (`ctx.state_id = state.state_id`).

The batch adapter's retry safety mechanism (`batch_adapter.py:20-26`) correctly captures `state_id` at the start of `_process_and_complete` (line 246), but `_process_row` itself does NOT capture state_id before the try/finally. If a timeout triggers a retry, the new attempt's `ctx.state_id` is set by the executor, and the original worker's `finally` block reads the new state_id, potentially closing the retry's HTTP client instead of its own.

The fix is a single-line change: capture `state_id = ctx.state_id` at method entry and use the captured value in the `finally` block.

### Bug 4: Prompt shield accepts fields=[] returning validated (P1 confirmed)

Genuine P1. `AzurePromptShieldConfig` at `prompt_shield.py:70-73` declares `fields` as `str | list[str]` with no non-empty validator. An empty list `[]` is accepted by Pydantic. `_get_fields_to_scan` at line 378-379 returns the empty list directly. `_process_single_with_state` at lines 288-370 loops over `fields_to_scan` -- with an empty list, the loop body never executes, and the method falls through to line 367 returning `TransformResult.success(row, success_reason={"action": "validated"})`.

This records a successful "validated" outcome in the audit trail with zero API calls made. For a security transform, this is a fail-open configuration gap.

### Bug 5: BatchReplicate accepts bool in copies_field (P1 -> P2)

The gap is real: `batch_replicate.py:155` uses `isinstance(raw_copies, int)` which accepts `True`/`False`. `True` produces 1 copy, `False` produces 0 copies (caught by the `< 1` check at line 163 and quarantined).

**However, the practical impact is limited:**

1. `True` producing 1 copy is numerically correct (1 copy = identity), so no data corruption occurs in the `True` case.
2. `False` is caught by the `< 1` quarantine check, so it doesn't produce wrong output -- it produces a quarantine, which is the correct failure mode.
3. This is Tier 2 pipeline data. A `bool` value in a field declared as `int` indicates an upstream source/transform bug. The correct fix is to fix the upstream schema, not to add bool-rejection at every downstream consumer.

The fix (`type(raw_copies) is not int`) is still worth doing for contract strictness and to avoid masking upstream bugs. Downgraded to P2.

### Bug 6: BatchReplicate no upper bound on copies (P1 -> P2)

The gap is real: `batch_replicate.py:163-183` only validates `raw_copies >= 1`, with no upper bound. A row with `copies=1000000` would produce 1,000,000 output rows.

**However, this is an operational safety concern, not a correctness or audit integrity issue:**

1. The copies value comes from Tier 2 pipeline data (post-source validation). Pathologically large values indicate either a misconfigured source or an intentional stress test.
2. The engine already has backpressure mechanisms (batch sizing, memory limits) that constrain the downstream impact.
3. The `default_copies` config has `ge=1` validation at config time -- adding `le=N` for config-level bounds is the right pattern, but the unbounded runtime case is a resource safety issue, not a data corruption issue.

A configurable `max_copies_per_row` with a reasonable default (e.g., 10000) would address this. Downgraded to P2 -- important for operational robustness but not a correctness/audit issue.

### Bug 7: FieldMapper allows target-name collisions (P1 confirmed)

Genuine P1. `FieldMapper.process()` at `field_mapper.py:137` writes `output[target] = value` without checking if `target` already exists from a previous mapping or from the original row data. When two source fields map to the same target, the later one silently overwrites the earlier one. Additionally, `narrow_contract_to_output` at `contract_propagation.py:110-111` keeps the OLD field contract metadata for existing names, so the contract can claim the field has the old field's type/original_name while the actual value comes from the new source field.

This creates both data loss (the overwritten field value disappears) and contract/type metadata divergence (the contract says one type, the value is another). Downstream sinks that use contract `original_name` for header restoration will produce incorrect headers.

The fix should validate at init time that mapping targets are unique, and at runtime that a target doesn't collide with existing row fields (unless it's the source field being renamed in-place).

### Bug 8: group_by can overwrite computed aggregate fields (P1 confirmed)

Genuine P1. `BatchStats.process()` at `batch_stats.py:186-190` builds a result dict with keys `count`, `sum`, `batch_size`, `mean`, `skipped_non_finite`. Then at line 213, `result[self._group_by] = group_value` overwrites any of these keys if `group_by` matches. The config at lines 31-34 has no reserved-name validation.

A configuration like `group_by="count"` causes the computed row count to be silently replaced by the group label string. The transform returns success, and the audit trail records semantically corrupted aggregate statistics. This is a silent data integrity violation.

The fix is a config-time validator that rejects reserved output field names for `group_by`.

### Bug 9: JSONExplode first-row type inference (P1 -> P2)

The gap is real but nuanced. `narrow_contract_to_output` at `contract_propagation.py:126-146` infers the type of new fields from their values in `output_rows[0]` only. For heterogeneous arrays like `["a", {"k": 1}]`, the first element's type (`str`) becomes the contract type, while subsequent elements may have different types (`dict`).

**However, the fallback at `json_explode.py:203-217` already adds the field with `python_type=object` when `find_field` returns None.** The issue is that `narrow_contract_to_output` successfully infers the type from the first row (adding it as `str`), so `find_field` returns non-None and the `object` fallback is skipped.

**Mitigating factors:**

1. Heterogeneous arrays (mixed scalar/complex types) are uncommon in well-formed pipeline data. Most exploded arrays contain homogeneous types.
2. The contract type mismatch does not cause crashes -- it only means downstream components see an inaccurate type annotation. Pipeline data is still Tier 2 (type-valid from source), and transforms should not rely on contract metadata for correctness.
3. The fix suggested in the bug report (always set to `object`) would lose type information for the common case of homogeneous arrays.

A better fix: check if all exploded items have the same type; if not, set to `object`. Downgraded to P2 -- contract metadata inaccuracy, not data loss.

### Bug 10: JSONExplode silently overwrites existing field on collision (P1 confirmed)

Genuine P1. `json_explode.py:161` builds `base` from all non-array fields, then line 177 assigns `output[self._output_field] = item`. If `output_field` collides with an existing field in `base`, the original value is silently overwritten. The contract propagation at lines 199-217 also gets confused: if the field already existed in the input contract, `narrow_contract_to_output` keeps the old metadata, so the contract type/original_name no longer matches the actual exploded value.

This is silent data loss and contract corruption in a single operation. The fix (check for collision before assignment and raise `ValueError`) is straightforward.

### Bug 11: KeywordFilterConfig accepts empty/blank fields (P1 confirmed)

Genuine P1. `KeywordFilterConfig` at `keyword_filter.py:65-68` declares `fields` as required (`...`) but has no content validator. `fields=[]`, `fields=""`, and `fields=[""]` are all accepted by Pydantic.

With `fields=[]`, `_get_fields_to_scan()` at line 193 returns the empty list, the `for` loop at line 152 never executes, and `process()` returns success at line 181 -- the keyword filter becomes a no-op. Rows with blocked content pass through, and the audit trail records `success_reason={"action": "filtered"}`, which is semantically incorrect (nothing was actually filtered/scanned).

For a content moderation transform, a no-op configuration that reports success is a security risk. The fix (add `@field_validator("fields")` rejecting empty/blank values) mirrors the fix needed for prompt_shield's `fields`.

### Bug 12: KeywordFilterConfig allows empty regex entries (P1 -> P2)

The gap is real: `validate_patterns_not_empty` at `keyword_filter.py:74-80` checks `if not v` (list-level emptiness) but not element-level emptiness. `[""]` passes validation, and `re.compile("")` creates a regex that matches every string at position 0 (zero-length match).

**However, the impact direction is fail-CLOSED, not fail-OPEN:**

1. An empty regex pattern blocks ALL rows, not none. Every row matches the empty pattern and is routed to error.
2. This produces false positives (blocking benign content), not false negatives (passing blocked content).
3. False positives are operationally disruptive but not a security vulnerability. The operator would notice immediately that all rows are being blocked.

The fix (reject empty pattern elements in the validator) is simple. Downgraded to P2 because the failure mode is noisy and fail-closed, not silent and fail-open.

### Bug 13: bool values accepted as numeric in BatchStats (P2 confirmed)

Real gap. `batch_stats.py:157` uses `isinstance(raw_value, (int, float))` which accepts `bool`. `True`/`False` are treated as `1`/`0` in sum/mean calculations. This can produce misleading aggregate statistics when boolean fields are accidentally routed through a numeric aggregation.

P2 is appropriate. This is a Tier 2 type contract strictness issue, not a crash or data loss. The fix (`type(raw_value) in (int, float)`) is a one-liner.

## Cross-Cutting Observations

### 1. The `isinstance(x, int)` / bool subclass pattern affects 3 bugs

Bugs 1, 5, and 13 all stem from `isinstance(x, int)` accepting `bool`. This is a systemic pattern in the codebase. A codebase-wide audit for `isinstance(..., int)` in type-checking contexts (not in Tier 3 boundary validation where coercion is expected) would identify any additional instances. The fix is always `type(x) is int` or explicit `isinstance(x, bool)` rejection.

### 2. Security transforms (content_safety, prompt_shield, keyword_filter) share the `fields` config gap

Bugs 4 and 11 are the same pattern: `fields: str | list[str]` without non-empty validation. Both prompt_shield and keyword_filter accept `fields=[]` and become no-ops. The fix should be applied consistently across all security transforms. Consider extracting a shared `@field_validator("fields")` to a base class or utility.

### 3. The collision/overwrite pattern affects multiple transforms

Bugs 7, 8, and 10 all involve silent field overwriting in output dicts: FieldMapper target collisions, BatchStats group_by collisions, and JSONExplode output_field collisions. The common fix is config-time or runtime collision detection before dict assignment. This pattern should be checked in any transform that adds fields to output rows.

### 4. Azure safety transforms need strict Tier 3 boundary validation

Bugs 1 and 2 are both Tier 3 boundary validation gaps in Azure API response handling. The response parsing validates type (`isinstance` checks) but not domain (`0 <= severity <= 6`) or cardinality (`len(documentsAnalysis) == 1`). Security transforms should enforce the strictest possible validation at external boundaries -- type, domain, cardinality, and expected-vs-actual structure.

### 5. Bugs 3 and the batch adapter retry model

Bug 3 (ctx.state_id race) exists because `_process_row` uses the shared mutable `ctx` object directly instead of capturing `state_id` at entry. The `_process_and_complete` method in the mixin correctly captures `state_id = ctx.state_id` at line 246, but `_process_row` (the processor callback) does not. This means the retry safety guarantee documented in `batch_adapter.py:20-26` is partially undermined by the plugin's own cleanup logic. The fix is contained to `content_safety.py` but prompt_shield.py should also be audited for the same pattern.
