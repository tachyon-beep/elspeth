# Test Bug Report Template

## Summary

- [Brief description of the test quality issue]

## Severity

- Severity: [trivial/minor]
- Priority: [P2/P3]
- Verdict: **[KEEP/REWRITE/SPLIT/DELETE]**

## Reporter

- Name or handle: Test Audit
- Date: [YYYY-MM-DD]
- Audit file: docs/test_audit/[filename].audit.md

## Test File

- **File:** `tests/[path]/test_[name].py`
- **Lines:** [line count]
- **Test count:** [number of tests]

## Findings

- **Line X-Y:** [Description of issue]
- **Line Z:** [Description of another issue]

## Verdict Detail

[Full verdict text from audit explaining why this action is recommended]

## Proposed Fix

- [ ] [First acceptance criterion]
- [ ] [Second acceptance criterion]
- [ ] [Additional criteria as needed]

## Tests

- Run after fix: `.venv/bin/python -m pytest [test_file_path] -v`

## Notes

- Source audit: `docs/test_audit/[filename].audit.md`

---

# Test Bug Tracking

This directory tracks test quality issues identified during the test audit process. Unlike production bugs, these issues affect test reliability, maintainability, and coverage effectiveness.

## Verdicts

| Verdict | Priority | Meaning |
|---------|----------|---------|
| **REWRITE** | P2 | Tests have fundamental issues (weak assertions, wrong patterns) requiring significant rework |
| **SPLIT** | P2 | Monolithic test file should be decomposed into focused modules |
| **DELETE** | P3 | Redundant or valueless tests that should be removed |
| **KEEP** | P3 | Tests are useful but have minor issues to address |

## Directory Structure

```
docs/test_bugs/
├── TEST_BUGS.md          # This file (template and index)
├── open/                 # Active issues
│   ├── cli/             # CLI test issues
│   ├── contracts/       # Contract test issues
│   ├── core-checkpoint/ # Checkpoint test issues
│   ├── core-config/     # Config test issues
│   ├── core-landscape/  # Landscape test issues
│   ├── core-security/   # Security test issues
│   ├── engine/          # Engine test issues
│   ├── audit/           # Audit test issues
│   └── plugins/         # Plugin test issues
└── closed/              # Resolved issues
```

## Statistics

Generated from test audit (2026-02-06):
- **Total audited**: 223 test files
- **Issues found**: 52 test files
- **REWRITE needed**: 12 files
- **SPLIT needed**: 3 files
- **DELETE recommended**: 1 file
- **KEEP with fixes**: 36 files

## Priority Guidelines

- **P2**: Tests that could pass incorrectly or hide bugs (weak assertions, permissive patterns)
- **P3**: Tests with inefficiencies or minor issues (redundancy, style problems)

## Closing a Test Bug

When fixing a test issue:
1. Make the necessary changes to the test file
2. Run the test suite to verify no regressions
3. Move the ticket from `open/` to `closed/`
4. Add a "## Resolution" section with details of the fix

## Source Audits

All test bugs are derived from the audit files in `docs/test_audit/`. Each ticket references its source audit for full context.
