# Analysis: src/elspeth/plugins/sources/field_normalization.py

**Lines:** 253
**Role:** Field name normalization for external data sources. Normalizes messy external headers (e.g., "CaSE Study1 !!!! xx!") to valid Python identifiers (e.g., "case_study1_xx") at the source boundary. Handles Unicode NFC normalization, special characters, duplicate detection, collision resolution, and algorithm versioning for audit trail reproducibility.
**Key dependencies:** `keyword` (stdlib), `re` (stdlib), `unicodedata` (stdlib). Imported by: `elspeth.plugins.sources.csv_source.CSVSource`, `elspeth.plugins.azure.blob_source.AzureBlobSource`.
**Analysis depth:** FULL

## Summary

This module is well-engineered with careful attention to correctness: NFC normalization, collision detection, algorithm versioning, and defense-in-depth `isidentifier()` checks. The code is pure (no side effects, no I/O) which makes it inherently testable and safe. There are no critical production bugs. However, there are two notable findings: soft keywords (`match`, `case`, `type`) are not handled, which could cause subtle issues in edge cases; and Unicode homoglyph attacks can produce visually identical but distinct field names that bypass collision detection. Both are unlikely to occur with typical CSV data but represent gaps in adversarial input handling.

## Critical Findings

*None identified.*

## Warnings

### [84] `keyword.iskeyword()` does not cover Python 3.10+ soft keywords

**What:** Line 84 uses `keyword.iskeyword(normalized)` to detect Python keywords and append an underscore suffix. However, `iskeyword()` returns `False` for soft keywords introduced in Python 3.10+ (`match`, `case`, `type`, `_`). These are context-sensitive keywords that are only reserved in specific syntactic positions (e.g., `match` and `case` in match statements). As valid Python identifiers, they pass through normalization unchanged.

**Why it matters:** While soft keywords are technically valid identifiers and work fine as dict keys, they can cause confusion and potential issues:
1. A CSV header "MATCH" normalizes to `match`, which could shadow pattern matching usage in downstream code.
2. A header "TYPE" normalizes to `type`, which shadows the built-in `type()` function.
3. The `_` soft keyword is especially problematic -- a header that normalizes to just `_` would collide with Python's conventional "throwaway" variable and the interactive interpreter's last result.

However, the practical impact is low because these are dict keys in row data, not variable names in executable code. This is more of a consistency concern: if the intent is to avoid Python keywords, soft keywords should be included for completeness.

**Evidence:**
```python
>>> import keyword
>>> keyword.iskeyword('match')
False
>>> keyword.issoftkeyword('match')  # Python 3.12+
True
```

### [38-97] Unicode homoglyph attack vector -- visually identical but distinct field names

**What:** The normalization algorithm applies NFC normalization (Step 1, line 62) which handles canonical equivalences (e.g., precomposed vs decomposed accent characters). However, NFC does NOT address homoglyphs -- visually identical characters from different Unicode scripts. For example:
- Latin `a` (U+0061) and Cyrillic `a` (U+0430) look identical but are different codepoints
- Latin `o` (U+006F) and Cyrillic `o` (U+043E) look identical but are different codepoints

Both are matched by `\w` in the regex (line 34), both are valid Python identifiers, and both survive NFC normalization unchanged. The collision check (`check_normalization_collisions`, line 100) compares by string equality, so `"abc"` (all Latin) and `"\u0430bc"` (Cyrillic a + Latin bc) would be treated as two distinct fields.

**Why it matters:** In a CSV with headers that appear identical to a human reader (e.g., one from a Cyrillic keyboard, one from Latin), the system would create two separate fields with indistinguishable names. An auditor viewing the field resolution mapping would see what appear to be duplicate fields but cannot tell them apart visually. This is an adversarial input scenario -- unlikely to occur accidentally but relevant for a system designed to "withstand formal inquiry" with an audit trail.

**Evidence:**
```python
>>> 'abc' == '\u0430bc'
False  # Different strings!
>>> # Both are valid identifiers
>>> 'abc'.isidentifier()
True
>>> '\u0430bc'.isidentifier()
True
```

A NFKC normalization (compatibility decomposition + canonical composition) or confusable detection (via `unicodedata` or the `confusables` library) would catch some of these cases, but neither is a complete solution.

### [100-124] Collision detection only checks normalized names, not original-to-normalized mapping uniqueness

**What:** `check_normalization_collisions` verifies that no two raw headers normalize to the same value. This is correct. However, the function does not verify the inverse: that no normalized name collides with a raw header that was not normalized (because `normalize_fields=False`). This inverse collision is impossible in the current code because `check_normalization_collisions` is only called when `normalize_fields=True` (line 219 of `resolve_field_names`), so all headers go through normalization. This is a non-issue in the current implementation but worth noting for documentation.

**Why it matters:** Future changes that allow partial normalization (e.g., only normalizing some headers) could introduce this collision vector. The current code is safe.

## Observations

### [23-25] Algorithm versioning is a strong pattern

The `NORMALIZATION_ALGORITHM_VERSION` constant stored in the audit trail enables debugging cross-run field name drift when the algorithm evolves. This is an excellent pattern for an audit-critical system.

### [34-35] Pre-compiled regex patterns

Module-level regex compilation is correct for performance. The patterns are simple and correct: `[^\w]+` matches one or more non-identifier characters, `_+` matches one or more underscores.

### [61-97] Normalization algorithm is thorough and well-ordered

The 9-step algorithm is applied in the correct order:
1. NFC before case folding (correct -- some characters change category after NFC)
2. Strip before processing (correct -- leading/trailing whitespace removed first)
3. Lowercase before regex (correct -- case-insensitive normalization)
4. Replace non-identifiers with underscore (correct -- preserves word boundaries)
5. Collapse underscores (correct -- cleanup from step 4)
6. Strip underscores (correct -- leading/trailing from step 4)
7. Digit prefix handling (correct -- `0field` -> `_0field`)
8. Keyword avoidance (correct -- `class` -> `class_`, minus soft keywords)
9. Empty string rejection (correct -- catches headers like `!!!`)

The defense-in-depth `isidentifier()` check at line 92 is an excellent safety net.

### [155-183] `FieldResolution` dataclass is well-designed

Frozen dataclass with clear attributes. The `reverse_mapping` property with the caching note (line 180-181) is a good performance hint for callers.

### [186-253] `resolve_field_names` has clean control flow

The function handles all three modes (headerless with columns, headers with normalization, headers without normalization) with clear branching. The `field_mapping` validation (checking for missing keys and post-mapping collisions) is thorough.

### [236-238] `if h in field_mapping` pattern with noqa comment

The explicit `if h in field_mapping else h` pattern is documented as preferred over `.get()` per the project's no-bug-hiding policy. The `# noqa: SIM401` suppresses the linter suggestion to use `.get()`. This is consistent with the project's coding standards.

## Verdict

**Status:** SOUND
**Recommended action:** The soft keyword gap (Warning 1) should be addressed for completeness -- adding `keyword.issoftkeyword()` check (Python 3.12+) or a hardcoded set of soft keywords for backward compatibility. The homoglyph issue (Warning 2) is a known limitation of Unicode text processing and may not warrant a code change, but should be documented as a known limitation. No urgent changes required.
**Confidence:** HIGH -- The module is pure (no I/O, no state), making analysis straightforward. All edge cases were verified empirically with the project's Python interpreter.
