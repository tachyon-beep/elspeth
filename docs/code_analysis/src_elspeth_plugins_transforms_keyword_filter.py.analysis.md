# Analysis: src/elspeth/plugins/transforms/keyword_filter.py

**Lines:** 176
**Role:** Content-based filtering transform that scans configured fields for regex pattern matches. Rows matching blocked patterns are routed to an error sink; rows without matches pass through unchanged. Used for content classification, safety filtering, and routing decisions.
**Key dependencies:** BaseTransform, TransformDataConfig, Determinism, PipelineRow, TransformResult, create_schema_from_config, re (standard library)
**Analysis depth:** FULL

## Summary

KeywordFilter is well-structured and follows the trust model correctly. The main security concern is the lack of ReDoS (Regular Expression Denial of Service) protection -- user-configured regex patterns can cause catastrophic backtracking. Additionally, the `match_context` field in error results can leak sensitive data into the audit trail. The pattern compilation at init time is a good practice. The transform shares input and output schemas (correct since it doesn't modify row shape).

## Critical Findings

### [83] No ReDoS protection on user-configured regex patterns

**What:** Regex patterns from config are compiled directly with `re.compile(pattern)` without any timeout, complexity limit, or pre-screening for catastrophic backtracking patterns.

**Why it matters:** Pipeline operators configure `blocked_patterns` in YAML. A pattern like `(a+)+b` or `(x+x+)+y` will cause catastrophic exponential backtracking when applied to a string like `"aaaaaaaaaaaaaaaaaac"`. A single row with a long string field can hang the entire pipeline indefinitely, consuming 100% CPU with no timeout. This is a denial-of-service vector in any deployment where pipeline configurations are not vetted by regex experts.

Python 3.11+ does not have built-in regex timeout. The `re2` library provides linear-time guarantees, or a timeout wrapper could be used.

**Evidence:**
```python
self._compiled_patterns: list[tuple[str, re.Pattern[str]]] = [
    (pattern, re.compile(pattern)) for pattern in cfg.blocked_patterns
]
# ...
match = compiled_pattern.search(value)  # No timeout, unbounded backtracking
```

In a production pipeline processing millions of rows, one adversarial or poorly-crafted string can cause the pipeline to appear stuck without any error or audit record. The row will never complete, the trigger/timeout for the operator will be "pipeline hung" with no diagnostic information.

### [126-134] match_context in error result can leak sensitive data into audit trail

**What:** When a pattern matches, the error result includes the matched text plus surrounding context:
```python
return TransformResult.error(
    {
        "reason": "blocked_content",
        "field": field_name,
        "matched_pattern": pattern_str,
        "match_context": context,  # 40 chars before + match + 40 chars after
    },
    retryable=False,
)
```

**Why it matters:** The `match_context` is stored in the audit trail (Landscape). If the keyword filter is used to detect and block sensitive content (passwords, API keys, PII), the very content being blocked gets recorded in the audit database. For example:

- Pattern: `\bpassword\b` (the docstring example)
- Field value: `"My password is hunter2 please reset"`
- match_context: `"My password is hunter2 please reset"` (entire string within 40 chars)

The password `hunter2` is now in the audit trail. The filter's purpose was to BLOCK this content from flowing through the pipeline, but the error recording preserves exactly the sensitive data that was supposed to be blocked.

**Evidence:**
```python
def _extract_context(self, text: str, match: re.Match[str], context_chars: int = 40) -> str:
    start = max(0, match.start() - context_chars)
    end = min(len(text), match.end() + context_chars)
    context = text[start:end]
```
40 characters of context on each side captures substantial amounts of surrounding text.

## Warnings

### [146-152] fields="all" scans all string fields -- performance concern on wide rows

**What:** When `fields` is set to `"all"`, the transform scans every field with a string value in the row:
```python
if self._fields == "all":
    return [k for k, v in row.items() if isinstance(v, str)]
```

**Why it matters:** For wide rows (50+ fields, common in enterprise data), every row requires iterating all fields to find strings, then running all patterns against each string field. With P patterns and F string fields, this is O(P * F * L) where L is average string length. For content-heavy rows (HTML, email bodies), this can be slow. Not a correctness issue, but a performance risk that should be documented.

### [91-92] Input and output schemas are the same object

**What:** `self.input_schema = schema; self.output_schema = schema` -- both point to the same Pydantic model.

**Why it matters:** This is correct because KeywordFilter does not change the row shape -- it either passes through unchanged or routes to error. However, it means any schema evolution (if someone added fields in the future) would affect both input and output validation simultaneously. This is fine for the current design.

### [113-114] Silently skips fields not present in row

**What:** When specific field names are configured but a field is not present in the row, the code silently continues:
```python
if field_name not in row_dict:
    continue  # Skip fields not present in this row
```

**Why it matters:** In OBSERVED/FLEXIBLE mode, optional fields may be absent from some rows. Silently skipping is the correct behavior. However, in FIXED mode where all fields should be present, a missing field configured for scanning would mean the row passes through unscanned for that field. If the content that should be blocked is in a field that happens to be missing, the row passes the filter incorrectly.

This is arguably correct (missing field = nothing to scan = not blocked), but operators might expect an error if a configured scan field is missing. The `strict` option from FieldMapper would be useful here.

### [119-120] Non-string values are silently skipped

**What:** When a configured field contains a non-string value (int, list, dict), it is silently skipped:
```python
if not isinstance(value, str):
    continue
```

**Why it matters:** If a field that was expected to be a string contains a different type (e.g., after a transform changed the type), the filter will silently pass the row through without scanning that field. This is correct per trust model (the value exists, it's just not a string, so regex doesn't apply), but it could mask upstream schema changes that cause previously-scanned fields to no longer be strings.

## Observations

### [70] Determinism.DETERMINISTIC is correctly set

Regex matching is deterministic -- same input always produces same output. This enables replay and verification modes to work correctly with this transform.

### [72-73] is_batch_aware=False, creates_tokens=False correctly set

KeywordFilter processes one row at a time and doesn't create new tokens. Both flags are correctly set.

### [35-41] Pattern validation ensures non-empty list

The Pydantic validator `validate_patterns_not_empty` prevents configuration with zero patterns. However, it does not validate that each pattern is valid regex -- that validation happens implicitly at `re.compile()` time in `__init__`, which is acceptable (fail-fast at initialization).

### [141] Pass-through preserves contract

```python
return TransformResult.success(row_dict, success_reason={"action": "filtered"}, contract=row.contract)
```
The original contract is preserved because the row shape is unchanged. This is correct.

### [138-141] success_reason uses "filtered" action

The action "filtered" means the row passed the filter (was NOT blocked). This naming is slightly ambiguous -- "filtered" could mean "was filtered out" or "was filtered through". The convention in this codebase appears to be that the action describes what was done, so "filtered" = "the filtering check was performed." Clear enough in context.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add ReDoS protection -- either use a regex timeout (via a wrapper), pre-screen patterns for backtracking potential, or document the risk prominently. (2) Redact or truncate the `match_context` in error results to avoid storing the sensitive content that triggered the block. Consider replacing with `match_context: "[REDACTED]"` or at minimum truncating to show only the pattern match without surrounding text. (3) Document the behavior when configured fields are missing from rows.
**Confidence:** HIGH -- ReDoS is a well-understood vulnerability class with clear reproduction paths. The sensitive data leakage is a direct logical consequence of the current implementation.
