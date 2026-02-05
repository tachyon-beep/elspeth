# Analysis: src/elspeth/plugins/transforms/web_scrape_fingerprint.py

**Lines:** 42
**Role:** URL fingerprinting for web scrape -- creates deterministic SHA-256 hashes of content for change detection and deduplication. Supports `content` mode (normalized whitespace) and `full` mode (raw content).
**Key dependencies:** `hashlib`, `re`. Consumed by `web_scrape.py` via `compute_fingerprint()`.
**Analysis depth:** FULL

## Summary

This is a small, focused utility with correct SHA-256 hashing and whitespace normalization. The primary concern is that unknown `mode` values silently fall through to `full` mode behavior instead of raising an error. The `structure` mode raises `NotImplementedError`, which is dead code. Overall the hashing logic is sound but the mode validation has a gap.

## Critical Findings

### [35-41] Unknown `mode` values silently fall through to raw-content hashing

**What:** The function handles three mode values: `"content"` (normalizes whitespace), `"structure"` (raises `NotImplementedError`), and implicitly `"full"` (uses raw content). However, the `full` mode is handled by falling through both `if` and `elif` clauses. Any unrecognized mode value (e.g., `"contnet"` -- a typo) will silently hash the raw content as if `mode="full"` was specified.

**Why it matters:** In a compliance monitoring system, a typo in the `fingerprint_mode` configuration would silently change fingerprinting behavior from whitespace-normalized to raw. This means cosmetic whitespace changes in a monitored webpage would suddenly trigger false-positive change alerts. The user would not know their normalization was not being applied. For audit integrity, the fingerprint mode recorded in configuration would not match actual behavior.

**Evidence:**
```python
if mode == "content":
    content = normalize_for_fingerprint(content)
elif mode == "structure":
    raise NotImplementedError("Structure mode not yet implemented")
# mode == "full" uses raw content as-is

return hashlib.sha256(content.encode("utf-8")).hexdigest()
```
A call like `compute_fingerprint(text, mode="contnet")` would silently skip normalization.

Per the CLAUDE.md principle: "If we read garbage from our own data, something catastrophic happened." A misspelled mode string is our configuration data, and it should crash, not silently degrade.

## Warnings

### [38-39] `NotImplementedError` for `structure` mode is dead code

**What:** The `structure` mode raises `NotImplementedError` at runtime. This is essentially a placeholder for future functionality.

**Why it matters:** Per the No Legacy Code policy, code for future features should not be pre-declared. The `structure` mode branch should either be implemented or removed entirely. If a user configures `fingerprint_mode: structure`, they get a runtime crash with a `NotImplementedError` instead of a clear configuration validation error at startup. The validation should happen in `WebScrapeConfig`, not at processing time.

### [20] Whitespace normalization collapses ALL whitespace including newlines

**What:** `re.sub(r"\s+", " ", content)` replaces all whitespace sequences (including `\n`, `\t`, `\r`, form feeds) with a single space. This means structural whitespace changes in content (e.g., adding a paragraph break) will not change the fingerprint in `content` mode.

**Why it matters:** This is likely the intended behavior for change detection (ignoring cosmetic formatting), but it means genuinely meaningful structural changes (new paragraphs, list items separated by newlines) will be invisible to the fingerprint. Whether this is a bug or feature depends on the use case. For compliance monitoring where paragraph structure matters, this could mask significant content changes.

## Observations

### [42] SHA-256 is an appropriate hash choice

**What:** `hashlib.sha256(content.encode("utf-8")).hexdigest()` produces a 64-character hex digest. SHA-256 is collision-resistant and deterministic, suitable for change detection.

### [42] UTF-8 encoding is explicit

**What:** `content.encode("utf-8")` explicitly specifies encoding rather than relying on system defaults. This ensures fingerprints are consistent across platforms with different default encodings.

### [20-22] Normalization is idempotent

**What:** Applying `normalize_for_fingerprint` twice produces the same result as applying it once. This is correct -- `re.sub(r"\s+", " ", ...)` followed by `.strip()` is idempotent since the output contains only single spaces and no leading/trailing whitespace. Tests verify this property.

### [7-22] `normalize_for_fingerprint` is exported as a public function

**What:** The function is public and tested independently. This enables callers to inspect normalized content for debugging, which is good for audit transparency.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Add explicit validation for unknown mode values -- raise `ValueError` for any mode not in `{"content", "full", "structure"}`. (2) Either implement `structure` mode or remove the branch entirely, validating the allowed modes at config time in `WebScrapeConfig`.
**Confidence:** HIGH -- Tiny module, clear logic, the fallthrough issue is unambiguous.
