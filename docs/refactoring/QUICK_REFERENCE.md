# Complexity Reduction - Quick Reference Checklist

**Use this checklist during refactoring to ensure nothing is missed.**

**Source:** METHODOLOGY.md (full guide)
**Success Rate:** 2/2 (100%) - PR #10 (85%), PR #11 (88.4%)

---

## Pre-Flight Check (Before Starting)

- [ ] Function complexity ≥ 25
- [ ] Existing test coverage ≥ 70%
- [ ] No active feature work on this code
- [ ] 10-15 hours available over 3-5 days
- [ ] Reviewers available (security + peer)
- [ ] CI/CD, MyPy, linting infrastructure working
- [ ] Branch created: `refactor/<target>-complexity`

---

## Phase 0: Safety Net (4-6 hours)

### Risk Reduction (1-3 hours)

- [ ] Identify top 3-5 risk areas (score by Impact × Probability × Subtlety)
- [ ] For each risk area:
  - [ ] Create markdown documentation
  - [ ] Write 3-7 behavioral tests
  - [ ] Verify tests pass
- [ ] Commit risk reduction work

### Characterization Tests (2-3 hours)

- [ ] Write 6+ characterization tests:
  - [ ] Happy path (normal inputs/outputs)
  - [ ] Empty inputs
  - [ ] Maximum inputs (stress)
  - [ ] Error handling
  - [ ] Edge case 1
  - [ ] Edge case 2
- [ ] All tests passing (100%)
- [ ] Coverage ≥ 80% on target function
- [ ] MyPy clean
- [ ] Ruff clean
- [ ] **Commit Phase 0**

---

## Phase 1: Supporting Classes (1-1.5 hours)

- [ ] Identify state clusters (5+ scattered variables)
- [ ] Design 1-3 dataclasses:
  - [ ] Type hints on all fields
  - [ ] Factory methods (`create()`) for complex init
  - [ ] Comprehensive docstrings
- [ ] Write unit tests for dataclasses
- [ ] Integrate into target function
- [ ] All tests still passing
- [ ] MyPy clean
- [ ] **Commit Phase 1**

---

## Phase 2: Simple Helpers (2-3 hours)

For each simple helper (4-6 total):

- [ ] Choose simplest candidate (self-contained, clear I/O, 5-20 lines)
- [ ] Extract to new method:
  - [ ] Add comprehensive docstring
  - [ ] Add type hints (params + return)
  - [ ] Include "Complexity Reduction" note in docstring
- [ ] Replace original code with method call
- [ ] **Run tests immediately** - must pass!
- [ ] Run MyPy - must be clean!
- [ ] (Optional) Commit after 2-3 simple extractions

**Commit Phase 2** after all simple helpers extracted.

### Metrics Check

Expected after Phase 2:
- Lines reduced by ~30-40%
- Complexity reduced by ~30-40%

---

## Phase 3: Complex Helpers (3-4 hours)

### Planning (30 min)

- [ ] Identify complex extraction candidates (nested conditionals, loops, orchestration)
- [ ] Plan extraction order (innermost first, repeated patterns, by responsibility)
- [ ] Design method signatures and names

### Extraction (2-3 hours)

For EACH complex helper (5-7 total):

1. [ ] Extract ONE method with full docstring
2. [ ] Update run() to call new method
3. [ ] **Run tests immediately** - must pass!
4. [ ] Run MyPy - must be clean!
5. [ ] **Commit (or revert if tests fail)**
6. [ ] Repeat for next method

**⚠️ CRITICAL: ONE method at a time, test after each!**

### Verify run() Simplification (15 min)

- [ ] run() is now ~30-60 lines
- [ ] Reads like high-level task list
- [ ] Minimal conditionals (only essential guards)
- [ ] No nested blocks > 2 levels

**Commit Phase 3** after all complex helpers extracted.

### Metrics Check

Expected after Phase 3:
- Lines reduced by ~60%
- Complexity reduced by ~85-90%

---

## Phase 4: Documentation & Cleanup (1-1.5 hours)

- [ ] Enhance run() docstring:
  - [ ] One-line summary
  - [ ] 2-3 paragraph explanation
  - [ ] Execution Flow section (numbered steps)
  - [ ] Complete Args/Returns/Raises
  - [ ] Complexity metrics (before/after)
  - [ ] Usage example
  - [ ] See Also section (helpers + docs)
- [ ] Review all helper docstrings (ensure complete)
- [ ] Search for TODOs/FIXMEs (remove/address)
- [ ] Create REFACTORING_COMPLETE_<target>.md:
  - [ ] Executive summary with metrics table
  - [ ] Phase breakdown
  - [ ] Helper methods catalog
  - [ ] Design patterns applied
  - [ ] Testing pyramid
  - [ ] Verification results
  - [ ] Review focus areas

### Final Verification

- [ ] `pytest tests/test_<target>*.py -v` - 100% pass
- [ ] `pytest tests/ -v` - no new failures
- [ ] `mypy src/<path>/target.py` - clean
- [ ] `ruff check src/<path>/target.py` - clean
- [ ] Complexity ≤ 15 (use SonarQube/radon)
- [ ] Coverage maintained or improved

**Commit Phase 4**

---

## Post-Refactoring

- [ ] Push all commits to remote
- [ ] Create draft PR with comprehensive description
- [ ] Request security review
- [ ] Request peer review
- [ ] Address Copilot automated review
- [ ] Update PR status to "Ready for Review"
- [ ] Respond to feedback
- [ ] Merge after approval
- [ ] Monitor for issues post-merge

---

## Emergency Rollback

If tests fail and you can't figure out why:

```bash
git reset --hard HEAD~1  # Undo last commit
# OR
git revert <commit-hash>  # Revert specific commit
```

Then investigate the failure before proceeding.

---

## Success Metrics (Final)

Target goals:
- ✅ Complexity reduced by 85% (actual: 86.7% average)
- ✅ All tests passing (100%)
- ✅ Zero behavioral changes
- ✅ Zero regressions
- ✅ Test coverage maintained or improved
- ✅ MyPy clean
- ✅ Ruff clean

---

## Common Pitfalls

❌ **DON'T:**
- Skip Phase 0 (safety net)
- Extract multiple complex methods at once
- Change behavior during refactoring
- Skip tests between extractions
- Batch commits across phases
- Rush the documentation

✅ **DO:**
- Run tests after EVERY extraction
- Commit frequently (after each phase minimum)
- Keep run() as orchestration template
- Write comprehensive docstrings
- Document complexity metrics
- Ask for help if stuck

---

## Time Budget

| Phase | Time | % |
|-------|------|---|
| Phase 0 | 4-6 hours | 35% |
| Phase 1 | 1-1.5 hours | 10% |
| Phase 2 | 2-3 hours | 20% |
| Phase 3 | 3-4 hours | 30% |
| Phase 4 | 1-1.5 hours | 10% |
| **TOTAL** | **11-16 hours** | **100%** |

Average: ~13 hours per refactoring

---

## Questions During Refactoring?

1. **"Should I extract this?"**
   - Phase 2: Extract if self-contained, clear I/O, 5-20 lines
   - Phase 3: Extract if complexity > 10, nested blocks, or orchestration

2. **"Tests are failing after extraction. What do I do?"**
   - Revert immediately: `git reset --hard HEAD~1`
   - Investigate why tests failed
   - Try smaller extraction or different approach

3. **"Method has too many parameters (>5). Is that okay?"**
   - Use dataclass to group related parameters
   - Or: method might be doing too much, split further

4. **"How do I know when run() is 'done'?"**
   - Reads like task list
   - ~30-60 lines
   - Complexity ≤ 15
   - No nested blocks > 2 levels

5. **"Should I refactor the helper methods too?"**
   - Not in this PR! Focus on the target function only
   - Helper complexity can be addressed in future PRs if needed

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Full Guide:** See METHODOLOGY.md
**Success Rate:** 2/2 (100%)
**Team:** Elspeth Engineering
