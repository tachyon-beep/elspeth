# Test Audit: tests/examples/test_llm_examples.py

**Audit Date:** 2026-02-05
**Auditor:** Claude Opus 4.5
**File:** `/home/john/elspeth-rapid/tests/examples/test_llm_examples.py`
**Lines:** 224

## Summary

This file contains integration tests for LLM examples (openrouter_sentiment and template_lookups). The tests verify end-to-end pipeline execution by running actual pipelines via subprocess and checking output files. These are legitimate integration tests that exercise production code paths.

**Overall Assessment:** PASS with minor observations

## Findings

### 1. No Defects Found

The tests are well-structured and test meaningful behavior:
- Pipeline execution via subprocess uses production CLI (`elspeth run`)
- Output verification checks both structure and content
- Parametrized tests cover multiple configurations (basic, pooled, batched)

### 2. No Overmocking Issues

These tests make real API calls (when OPENROUTER_API_KEY is available) and use production code paths. No mocking is present - this is appropriate for integration tests.

### 3. Test Path Integrity: PASS

The tests correctly use production code paths:
- Pipelines are run via the actual CLI (`uv run elspeth run -s settings.yaml --execute`)
- No manual graph construction or direct attribute assignment
- Tests exercise the same code path that production uses

### 4. Test Discovery: PASS

Both test classes are correctly named with "Test" prefix:
- `TestOpenRouterSentiment` - will be discovered
- `TestTemplateLookups` - will be discovered

### 5. Minor Observations (Not Defects)

#### 5.1 Expected Sentiments Assumption (Low Risk)

```python
# Line 111-118
EXPECTED_SENTIMENTS = {
    1: "positive",  # "I absolutely love this product!"
    2: "negative",  # "The service was terrible"
    3: "neutral",  # "It was okay"
    4: "positive",  # "Amazing experience!"
    5: "negative",  # "Completely disappointed"
}
```

The comment says "deterministic with temperature=0" but LLM outputs can vary even with temperature=0 (especially across different model versions or providers). If these tests fail intermittently in CI, this would be the cause. However, for integration tests that verify the pipeline works, this is acceptable - the test would catch pipeline failures even if sentiment predictions vary.

#### 5.2 Cleanup Before Not After

```python
# Line 134-136
_clean_output_dir(output_path.parent)
_clean_runs_dir(runs_dir)
```

Tests clean up before running but not after. This leaves output files around after test runs, which could be useful for debugging but may accumulate over time. This is a style choice, not a defect.

#### 5.3 isinstance Check for Analysis Field

```python
# Line 155-157
analysis = row["sentiment_analysis"]
if isinstance(analysis, str):
    analysis = json.loads(analysis)
```

This `isinstance` check is legitimate - the test is handling external data (pipeline output) where the format may vary depending on the transform configuration. This is consistent with the Three-Tier Trust Model (Tier 3 - external data from the pipeline's perspective since we're testing the pipeline as a black box).

### 6. Coverage Assessment

The tests cover:
- Basic sentiment analysis pipeline
- Pooled sentiment analysis pipeline
- Batched sentiment analysis pipeline
- Basic template lookups pipeline
- Batched template lookups pipeline

Each test verifies:
- Output file creation
- Correct number of rows
- Required fields present
- Field value validity (sentiment values, confidence ranges)
- Template/lookup hash tracking (for template_lookups)

**Missing coverage:** None identified. These are example/integration tests and appropriately test the example configurations.

### 7. Efficiency Assessment

- Tests are appropriately marked as `integration` (can be skipped in fast test runs)
- Tests are skipped when API key is not available
- Each test runs a separate pipeline (appropriate for integration tests)
- No copy-paste duplication - parametrized tests share common verification logic

## Verdict

**PASS** - These are well-written integration tests that:
1. Use production code paths (CLI subprocess)
2. Make meaningful assertions about pipeline output
3. Are properly marked and skippable
4. Cover multiple example configurations

No changes required.
