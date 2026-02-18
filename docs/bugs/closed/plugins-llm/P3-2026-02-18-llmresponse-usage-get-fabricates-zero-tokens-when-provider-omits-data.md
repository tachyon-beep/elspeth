## Summary

`LLMResponse.total_tokens` and multiple LLM transform files use `.get("prompt_tokens", 0)` and `.get("completion_tokens", 0)` on the `usage` dict. When the LLM provider omits usage data (streaming mode, certain configs), `usage` is set to `{}` and these `.get()` calls return `0` — fabricating "0 tokens used" when the truth is "unknown."

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/plugins/clients/llm.py` — Line 54 (`total_tokens` property)
- File: `src/elspeth/plugins/llm/azure_multi_query.py` — Lines 294, 315
- File: `src/elspeth/plugins/llm/openrouter_multi_query.py` — Lines 358, 373

## Evidence

**Tier 3 boundary** (llm.py:398-404):

```python
if response.usage is not None:
    usage = {"prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens}
else:
    usage = {}  # Provider omitted usage data
```

When usage is `{}`, downstream `.get("prompt_tokens", 0)` returns `0`. This means `total_tokens` reports `0` when we genuinely don't know the token count.

## Design Principle

The core issue is the distinction between **coercion** and **fabrication** at Tier 3 boundaries:

- **Coercion** (meaning-preserving): `"42"` -> `42` — the semantic value is the same, just the type changed. This is fine.
- **Fabrication** (meaning-changing): `None` -> `0` — the semantic value changed from "unknown" to "zero." This is a lie.

The Tier 3 contract is "we don't trust you" — and that distrust extends to silence. When a provider omits expected data, that absence is itself a fact worth recording. Converting it to a plausible-looking value (`0`) is indistinguishable from a real measurement, which violates the audit principle: "if it's not recorded, it didn't happen" — and its corollary: if it didn't happen, don't record a fabricated version of it.

The test for whether a Tier 3 normalization is legitimate: **can the downstream consumer distinguish real data from synthetic?** If `total_tokens` returns `0`, the consumer cannot tell whether the LLM genuinely used zero tokens (impossible) or the provider didn't report usage. That ambiguity is the problem.

## Design Decision Required

The fix depends on a design choice:

**Option A: Represent unknown as None (Recommended)**

- Change `usage = {}` to `usage = {"prompt_tokens": None, "completion_tokens": None}`
- Change `total_tokens` return type to `int | None`
- Downstream consumers must handle `None` (no fabrication)
- The absence is clearly telegraphed through the type system

**Option B: Represent unknown as absent keys with explicit check**

- Keep `usage = {}` but change consumers to check key existence
- `total_tokens` returns `int | None` when keys are absent

**Option C: Accept the fabrication (document it)**

- Keep current behavior, add comment: "Returns 0 when provider omits usage data — this is a known approximation, not actual token count"
- Least disruptive but violates the "no fabrication" principle

## Root Cause

The Tier 3 normalization at the boundary (llm.py:398-404) converts "no data" to "empty dict," which propagates as fabricated zeros through all consumers. The absence of expected data should be recorded as a first-class fact (None), not normalized away to a plausible-looking default.

## Impact

Token usage telemetry, cost tracking, and truncation heuristics receive `0` instead of "unknown" when providers omit usage data. This could affect Langfuse cost calculations and truncation detection in multi-query transforms.
