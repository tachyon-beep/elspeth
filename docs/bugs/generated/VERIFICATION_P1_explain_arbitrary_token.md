# Bug Verification Report: Explain Returns Arbitrary Token When Multiple Tokens Exist

## Status: VERIFIED

**Bug ID:** P1-explain-arbitrary-token
**Claimed Location:** `src/elspeth/core/landscape/lineage.py`
**Verification Date:** 2026-01-22
**Verifier:** Claude Code

---

## Summary of Bug Claim

The bug report claims that `explain(row_id)` resolves by picking the first token, yielding incomplete/wrong lineage when multiple tokens share the same `row_id` (fork/expand/coalesce/resume). The documented API specifies sink-based disambiguation which is not implemented.

## Code Analysis

### 1. explain() Function Implementation (lineage.py:63-91)

```python
# From lineage.py:63-91
def explain(
    recorder: "LandscapeRecorder",
    run_id: str,
    token_id: str | None = None,
    row_id: str | None = None,
) -> LineageResult | None:
    """Query complete lineage for a token or row.

    Args:
        recorder: LandscapeRecorder with query methods.
        run_id: Run ID to query.
        token_id: Token ID for precise lineage (preferred).
        row_id: Row ID (will use first token for that row).  # <-- ACKNOWLEDGES LIMITATION

    Returns:
        LineageResult with complete lineage, or None if not found.
    """
    if token_id is None and row_id is None:
        raise ValueError("Must provide either token_id or row_id")

    # Resolve token_id from row_id if needed
    if token_id is None and row_id is not None:
        tokens = recorder.get_tokens(row_id)
        if not tokens:
            return None
        token_id = tokens[0].token_id  # <-- ARBITRARY SELECTION (first in list)
```

**Critical Issue:** Line 91 simply takes `tokens[0]` without any:
- Checking if multiple tokens exist
- Sink-based disambiguation
- Warning about ambiguity
- Selection of terminal token

### 2. Documented API (architecture.md:341-347)

The architecture document specifies three API variants:

```markdown
| Signature | Use Case |
|-----------|----------|
| `explain(run_id, token_id, field)` | Precise - works for any DAG |
| `explain(run_id, row_id, sink, field)` | Convenience - disambiguates by target sink |
| `explain(run_id, row_id, field)` | Only valid when row has single terminal path |
```

**Gap:** The documented `sink` parameter for disambiguation is **NOT IMPLEMENTED**.

### 3. Current Function Signature (lineage.py:63-68)

```python
def explain(
    recorder: "LandscapeRecorder",
    run_id: str,
    token_id: str | None = None,
    row_id: str | None = None,
) -> LineageResult | None:
```

**Missing parameters:** No `sink` or `field` parameters exist in the actual implementation.

### 4. Token Multiplicity Scenarios

Multiple tokens for a single `row_id` can occur in several scenarios:

**Fork:** A gate forks the row into multiple parallel paths:
```python
# Row 123 forks into 3 branches
tokens = [
    Token(token_id="tok_a", row_id="row_123", branch_name="fast"),
    Token(token_id="tok_b", row_id="row_123", branch_name="slow"),
    Token(token_id="tok_c", row_id="row_123", branch_name="fallback"),
]
```

**Expand/Deaggregate:** An aggregation outputs multiple rows from one input:
```python
# Batch containing row 456 expands to 5 output tokens
tokens = [
    Token(token_id="tok_1", row_id="row_456", expand_group_id="exp_001"),
    Token(token_id="tok_2", row_id="row_456", expand_group_id="exp_001"),
    # ... etc
]
```

**Resume:** A resumed run creates new tokens for previously processed rows:
```python
# Original run created tok_orig, resume creates tok_resume
tokens = [
    Token(token_id="tok_orig", row_id="row_789"),
    Token(token_id="tok_resume", row_id="row_789"),  # From resume
]
```

### 5. What "First Token" Actually Means

The `recorder.get_tokens(row_id)` method returns tokens in **creation order** (typically by `created_at`). This means:

- For forks: Returns the first forked token (arbitrary choice among branches)
- For expands: Returns the first expanded token
- For resumes: Returns the original token (not the completed one)

**None of these are necessarily the "correct" token for audit queries.**

## Reproduction Scenario

**Pipeline with fork:**

```yaml
gates:
  - name: parallel_analysis
    condition: "True"
    routes:
      all: fork
    fork_to:
      - sentiment_path   # -> sentiment_sink
      - entity_path      # -> entity_sink
```

**Execution:**

1. Row "row_001" is processed
2. Fork creates:
   - Token "tok_sent" (branch: sentiment_path) -> writes to sentiment_sink
   - Token "tok_ent" (branch: entity_path) -> writes to entity_sink

**Audit query:**

```python
# User wants to understand why row_001 went to sentiment_sink
lineage = explain(recorder, run_id, row_id="row_001")

# Returns lineage for tok_sent OR tok_ent (whichever was created first)
# User has NO CONTROL over which path they get
# If they wanted entity_path lineage, they get wrong answer
```

**Correct API (per docs):**

```python
# Should be able to specify sink for disambiguation
lineage = explain(recorder, run_id, row_id="row_001", sink="entity_sink")
# Returns lineage for tok_ent (the token that reached entity_sink)
```

## Evidence Summary

| Location | Finding |
|----------|---------|
| `lineage.py:75` | Docstring acknowledges "will use first token for that row" |
| `lineage.py:91` | Implementation: `token_id = tokens[0].token_id` |
| `lineage.py:63-68` | Function signature lacks `sink` parameter |
| `architecture.md:346` | Documents `explain(run_id, row_id, sink, field)` variant |
| `architecture.md:347` | States row-only valid "when row has single terminal path" |

## Gap Analysis: Implementation vs Documentation

| Feature | Documented | Implemented |
|---------|------------|-------------|
| `explain(token_id)` | Yes | Yes |
| `explain(row_id)` | "Only valid for single terminal path" | Yes, but no validation |
| `explain(row_id, sink)` | Yes | **NO** |
| Ambiguity warning | Implicit (single path rule) | **NO** |
| `field` parameter | Yes | **NO** |

## Impact Assessment

| Factor | Assessment |
|--------|------------|
| **Severity** | Major - Returns wrong lineage silently |
| **Frequency** | Medium - Any forked row or batch expansion |
| **Detection** | Very Hard - Returns valid-looking but incorrect lineage |
| **Consequence** | Auditors receive misleading explanations for forked rows |

## CLAUDE.md Alignment

This violates the auditability standard:

> "I don't know what happened" is never an acceptable answer for any output

With arbitrary token selection, `explain(row_id)` CAN give a wrong answer without any indication that the answer is incomplete or potentially incorrect. An auditor asking "why did row 42 go to sink X?" might receive lineage for a different path entirely.

---

## Conclusion

**VERIFIED:** The bug is accurate. The `explain()` function:

1. **Lacks sink disambiguation** - The documented `explain(row_id, sink)` variant is not implemented
2. **Arbitrarily selects first token** - No terminal path validation or selection logic
3. **Provides no ambiguity warning** - Silent wrong answer is worse than an error
4. **Missing `field` parameter** - Field-level lineage not implemented

The fix should:

1. Add `sink: str | None = None` parameter
2. Add `field: str | None = None` parameter (optional, for future)
3. When `row_id` provided without `sink`:
   - Get all tokens for row
   - If exactly one terminal token exists, use it
   - If multiple terminals exist, raise `ValueError` with disambiguation guidance
4. When `row_id` and `sink` both provided:
   - Find token whose terminal state is at the specified sink
   - Return that token's lineage
