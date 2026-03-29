## Summary

Duplicate Azure moderation categories are accepted and silently overwritten, so a malformed response can downgrade a previously flagged category to a safe severity and let unsafe content pass.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/azure/content_safety.py
- Line(s): 179-205
- Function/Method: `_analyze_content`

## Evidence

`_analyze_content()` treats `categoriesAnalysis` as trusted-enough to overwrite prior values for the same category:

```python
result: dict[str, int] = dict.fromkeys(_EXPECTED_CATEGORIES, 0)

for item in data["categoriesAnalysis"]:
    azure_category = item["category"]
    internal_name = _AZURE_CATEGORY_MAP.get(azure_category)
    ...
    severity = item["severity"]
    ...
    result[internal_name] = severity
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/azure/content_safety.py:180-196`

It later validates only that each expected category name appeared at least once:

```python
returned_categories = {
    _AZURE_CATEGORY_MAP[item["category"]] for item in data["categoriesAnalysis"] if item["category"] in _AZURE_CATEGORY_MAP
}
missing = _EXPECTED_CATEGORIES - returned_categories
if missing:
    raise MalformedResponseError(...)
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/azure/content_safety.py:201-210`

That means this malformed external payload is accepted:

```json
{
  "categoriesAnalysis": [
    {"category": "Hate", "severity": 5},
    {"category": "Hate", "severity": 0},
    {"category": "Violence", "severity": 0},
    {"category": "Sexual", "severity": 0},
    {"category": "SelfHarm", "severity": 0}
  ]
}
```

The second `"Hate"` entry overwrites the first, `missing` is empty, and `_check_thresholds()` sees `"hate": 0`, so the row is marked safe.

This is a Tier 3 validation gap in a fail-closed security transform: contradictory external data should be rejected, not resolved by “last write wins.”

The current tests cover unknown categories, missing categories, and bad severity types, but not duplicate categories:
- `/home/john/elspeth/tests/unit/plugins/transforms/azure/test_content_safety.py:648-779`
- `/home/john/elspeth/tests/property/plugins/transforms/azure/test_azure_safety_properties.py:341-395`

## Root Cause Hypothesis

The code validates category membership and completeness, but not uniqueness. Because `result` is a mutable dict keyed by internal category name, repeated categories collapse silently. This likely came from focusing on “unknown/missing category” fail-closed behavior without considering contradictory duplicate entries from the external API boundary.

## Suggested Fix

Reject duplicate categories during boundary validation before storing the severity. For example, keep a `seen_categories` set and raise `MalformedResponseError` if the same internal category appears twice.

Example shape:

```python
result: dict[str, int] = {}
seen_categories: set[str] = set()

for item in data["categoriesAnalysis"]:
    ...
    if internal_name in seen_categories:
        raise MalformedResponseError(
            f"Duplicate Azure Content Safety category: {azure_category!r}"
        )
    seen_categories.add(internal_name)
    result[internal_name] = severity

missing = _EXPECTED_CATEGORIES - seen_categories
if missing:
    raise MalformedResponseError(...)
```

Also add a unit test with two entries for the same Azure category and assert `error_type == "malformed_response"`.

## Impact

A malformed or intermediary-corrupted Azure response can turn a blocking severity into a passing severity for the same category, causing unsafe content to be marked validated. This is a fail-open decision error in a security control, and it undermines the audit trail because the recorded decision reflects an internally-resolved contradiction rather than the actual conflicting payload returned by the external service.
