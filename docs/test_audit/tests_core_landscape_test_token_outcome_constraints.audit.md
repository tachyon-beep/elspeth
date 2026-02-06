# Test Audit: tests/core/landscape/test_token_outcome_constraints.py

**Lines:** 341
**Test count:** 7
**Audit status:** PASS

## Summary

This test file verifies critical audit integrity constraints for token outcomes, specifically the database constraint preventing multiple terminal outcomes for the same token. The tests are well-documented with clear rationale for why each constraint matters for audit integrity. The second test class covers canonical JSON enforcement for token outcome context, testing NaN/Infinity rejection per CLAUDE.md requirements.

## Findings

### 🔵 Info

1. **Excellent documentation of audit integrity rationale** - Test docstrings (lines 28-36, 76-81, 143-149) clearly explain WHY each constraint matters for the audit trail, not just what is being tested. This is exemplary test documentation.

2. **Proper constraint testing** - `test_double_terminal_outcome_raises_integrity_error` (lines 27-73) correctly verifies that the partial UNIQUE index `UNIQUE(token_id) WHERE is_terminal=1` is enforced at the database level.

3. **Comprehensive state transition coverage** - Tests cover:
   - Terminal -> Terminal (must fail, lines 27-73)
   - Non-terminal -> Terminal (must succeed, lines 75-141)
   - Non-terminal -> Non-terminal (must succeed, lines 143-219)

4. **Bug reference in docstring** - Line 225 references `P2-2026-01-31-token-outcome-context-non-canonical`, providing traceability to the original issue.

5. **Canonical JSON enforcement tests** - Lines 232-341 verify that NaN and Infinity in context data are rejected with `ValueError`, enforcing the CLAUDE.md requirement that "NaN and Infinity are strictly rejected, not silently converted."

6. **Flexible regex patterns** - Lines 263 and 298 use regex patterns like `r"[Nn]a[Nn]|non-finite"` that match various error message formats, making tests resilient to minor message changes.

7. **No mocking of database constraints** - Tests use real `LandscapeDB.in_memory()` instances and verify actual SQLAlchemy `IntegrityError` exceptions, ensuring the constraint is enforced at the database level.

## Verdict

**KEEP** - This is an exemplary test file that verifies critical audit integrity constraints. The tests are well-documented, use real database instances, and cover important edge cases. The connection between test cases and the audit integrity requirements is clear.
