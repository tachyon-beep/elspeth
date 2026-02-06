# Test Audit: tests/core/landscape/test_formatters.py

**Lines:** 520
**Test count:** 24
**Audit status:** PASS

## Summary

This test file provides comprehensive coverage of export formatters (CSVFormatter, JSONFormatter, LineageTextFormatter) and serialization utilities (serialize_datetime, dataclass_to_dict). Tests are well-structured, follow the codebase conventions, and properly verify edge cases including NaN/Infinity rejection per CLAUDE.md audit integrity requirements. Test naming is clear and docstrings explain intent.

## Findings

### 🔵 Info

1. **Lines 277, 291, 303**: `import math` appears inside test methods rather than at module top. This is a minor style inconsistency but does not affect correctness.

2. **Line 365**: The test `test_json_formatter_handles_datetime_via_default` uses a weak assertion (`assert "2024-01-15" in parsed["timestamp"]`) that checks partial string match instead of exact ISO format. This is acceptable because JSONFormatter uses `default=str` which may vary slightly by Python version, but could be made more explicit.

3. **Lines 398-520**: The `TestLineageTextFormatter` class imports from `elspeth.contracts` and `elspeth.core.landscape.*` inside each test method. While this works, these could be module-level imports for consistency. However, this pattern may be intentional to isolate import-time failures.

## Verdict

**KEEP** - This is a high-quality test file with thorough coverage of formatter behaviors, edge cases (NaN, Infinity, nested structures, empty dicts, None values), and proper verification of audit integrity requirements. No defects, no overmocking, no missing critical coverage, and all tests perform meaningful assertions.
