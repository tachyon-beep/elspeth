# Complexity Reduction - Execution Checklist

**Version:** 1.1
**Target Function:** `__________________`
**File:** `__________________`
**Start Date:** `__________________`
**Branch:** `refactor/<target>-complexity`

---

## Pre-Flight Check

**Decision Matrix Score:** `_____ / 9` (0-3: proceed, 4-6: add safeguards, 7-9: high risk)

- [ ] Complexity score ≥ 25 (Current: `_____`)
- [ ] Test coverage ≥ 70% (Current: `_____`%)
- [ ] No active feature development on this code
- [ ] 10-15 hours available over 3-5 days
- [ ] Reviewers identified: Security `__________`, Peer `__________`
- [ ] CI/CD, MyPy, Ruff infrastructure working
- [ ] Branch created: `refactor/<target>-complexity`

---

## Phase 0: Safety Net (4-6 hours, 35% of time)

**Start Time:** `__________` | **End Time:** `__________` | **Actual:** `_____ hours`

### Step 0.1: Read the Code (30 min)
- [ ] Read target function, understand WHAT it does (not HOW)
- [ ] Document inputs, outputs, side effects
- [ ] List edge cases (empty inputs, None values, boundaries)
- [ ] Create markdown notes documenting behavior

### Step 0.2: Identify Risk Areas (30-60 min)
- [ ] Identify complexity hotspots (nested conditionals, loops)
- [ ] Check change history (frequently modified code)
- [ ] Find implicit dependencies (call order, shared state)
- [ ] Create risk assessment document with scores

### Step 0.3: Risk Reduction Activities (1-3 hours)
For each high-risk area (score ≥ 1.0):
- [ ] Risk Area 1: `__________` (Score: `_____`)
  - [ ] Create documentation explaining behavior
  - [ ] Write 3-7 tests covering normal + edge cases
  - [ ] Verify tests pass
- [ ] Risk Area 2: `__________` (Score: `_____`)
  - [ ] Create documentation
  - [ ] Write tests
  - [ ] Verify tests pass
- [ ] Risk Area 3: `__________` (Score: `_____`)
  - [ ] Create documentation
  - [ ] Write tests
  - [ ] Verify tests pass

### Step 0.4: Write Characterization Tests (2-3 hours)
- [ ] Test 1: Happy path (normal inputs/outputs)
- [ ] Test 2: Empty inputs
- [ ] Test 3: Maximum inputs (stress test)
- [ ] Test 4: Error handling
- [ ] Test 5: Edge case `__________`
- [ ] Test 6: Edge case `__________`
- [ ] Additional tests as needed

**Test Count:** `_____ tests created`

### Step 0.5: Verify Safety Net (30 min)
- [ ] Run all new tests: `pytest tests/test_<target>_*.py -v`
- [ ] Verify 100% pass rate
- [ ] Check coverage: `pytest --cov=src/<path>/target.py` (Target: ≥ 80%, Actual: `_____`%)
- [ ] Run MyPy: `mypy src/<path>/target.py` ✅ Clean
- [ ] Run Ruff: `ruff check src/<path>/target.py` ✅ Clean

### Step 0.6: Non-Functional Baseline (30 min) - Optional but Recommended
- [ ] Capture performance baseline (p50/p95 runtime)
- [ ] Capture memory baseline (peak RSS/heap)
- [ ] Capture logging baseline (event count/severity)
- [ ] Document baseline metrics for Phase 4 comparison

### Step 0.7: Mutation Testing (30-60 min)
- [ ] Install mutmut: `pip install mutmut`
- [ ] Run mutation testing: `mutmut run --paths-to-mutate src/<path>/target.py`
- [ ] Check results: `mutmut results`
- [ ] Mutation score ≤ 10% survivors (Actual: `_____`%)
- [ ] If > 10% survivors, add more tests before proceeding

### Step 0.8: Commit Safety Net
- [ ] `git add tests/ docs/`
- [ ] `git commit -m "Phase 0: Safety net for <target> refactoring"`
- [ ] Push to remote

**Phase 0 Complete:** `✅ / ❌`

---

## Phase 1: Supporting Classes (1-2 hours, 10% of time)

**Start Time:** `__________` | **End Time:** `__________` | **Actual:** `_____ hours`

### Step 1.1: Identify State Clusters (15 min)
- [ ] Identify 5+ scattered local variables
- [ ] Identify parameter clumps (same 3-4 params passed to helpers)
- [ ] Group related state into clusters

**Clusters Identified:** `_____`

### Step 1.2: Design Dataclasses (30 min)
- [ ] Dataclass 1: `__________` (consolidates `_____` variables)
  - [ ] Type hints on all fields
  - [ ] Factory method (`create()`) if needed
  - [ ] Prefer `frozen=True` for immutability
  - [ ] Comprehensive docstring
- [ ] Dataclass 2: `__________` (consolidates `_____` variables)
  - [ ] Type hints, factory, docstring
- [ ] Dataclass 3: `__________` (optional)
  - [ ] Type hints, factory, docstring

### Step 1.3: Add Unit Tests (15-30 min)
- [ ] Test dataclass initialization
- [ ] Test factory methods with normal inputs
- [ ] Test with empty/minimal inputs
- [ ] All tests passing

### Step 1.4: Integrate into Target Function (15-30 min)
- [ ] Replace scattered variables with dataclass instance(s)
- [ ] Update all variable references to `ctx.field`
- [ ] Run tests: ALL must still pass ✅
- [ ] Run MyPy: must be clean ✅

### Step 1.5: Commit Phase 1
- [ ] `git add src/ tests/`
- [ ] `git commit -m "Phase 1: Supporting dataclasses for <target>"`

**Phase 1 Complete:** `✅ / ❌`

---

## Phase 2: Simple Helper Extractions (2-3 hours, 20% of time)

**Start Time:** `__________` | **End Time:** `__________` | **Actual:** `_____ hours`

**Target:** Extract 4-6 simple helpers (5-20 lines each)

For EACH simple helper:
1. [ ] Helper 1: `__________` (`_____` lines)
   - [ ] Extract method with docstring + type hints
   - [ ] Replace original code with call
   - [ ] Run tests immediately ✅
   - [ ] Run MyPy ✅
   - [ ] (Optional) Commit

2. [ ] Helper 2: `__________` (`_____` lines)
   - [ ] Extract, test, mypy ✅

3. [ ] Helper 3: `__________` (`_____` lines)
   - [ ] Extract, test, mypy ✅

4. [ ] Helper 4: `__________` (`_____` lines)
   - [ ] Extract, test, mypy ✅

5. [ ] Helper 5: `__________` (`_____` lines) - Optional
   - [ ] Extract, test, mypy ✅

6. [ ] Helper 6: `__________` (`_____` lines) - Optional
   - [ ] Extract, test, mypy ✅

### Metrics Check (Phase 2)
- [ ] Lines reduced by ~30-40% (Before: `_____`, After: `_____`, Reduction: `_____`%)
- [ ] Complexity reduced by ~30-40% (Before: `_____`, After: `_____`, Reduction: `_____`%)

### Commit Phase 2
- [ ] `git add src/`
- [ ] `git commit -m "Phase 2: Simple helper extractions (X methods)"`

**Phase 2 Complete:** `✅ / ❌`

---

## Phase 3: Complex Method Extractions (3-4 hours, 30% of time)

**Start Time:** `__________` | **End Time:** `__________` | **Actual:** `_____ hours`

**Target:** Extract 5-7 complex helpers (15-40 lines each)

**⚠️ CRITICAL: ONE extraction at a time, test after EACH, commit/revert based on results!**

For EACH complex helper:
1. [ ] Helper 1: `__________` (`_____` lines, complexity: `_____`)
   - [ ] Extract ONE method with full docstring
   - [ ] Update run() to call new method
   - [ ] Run tests IMMEDIATELY ✅
   - [ ] Run MyPy ✅
   - [ ] **COMMIT or REVERT**

2. [ ] Helper 2: `__________` (`_____` lines, complexity: `_____`)
   - [ ] Extract, test, mypy, commit ✅

3. [ ] Helper 3: `__________` (`_____` lines, complexity: `_____`)
   - [ ] Extract, test, mypy, commit ✅

4. [ ] Helper 4: `__________` (`_____` lines, complexity: `_____`)
   - [ ] Extract, test, mypy, commit ✅

5. [ ] Helper 5: `__________` (`_____` lines, complexity: `_____`)
   - [ ] Extract, test, mypy, commit ✅

6. [ ] Helper 6: `__________` (`_____` lines, complexity: `_____`) - Optional
   - [ ] Extract, test, mypy, commit ✅

7. [ ] Helper 7: `__________` (`_____` lines, complexity: `_____`) - Optional
   - [ ] Extract, test, mypy, commit ✅

### Verify run() Simplification (15 min)
- [ ] run() is now ~30-60 lines (Actual: `_____` lines)
- [ ] Reads like high-level task list
- [ ] Minimal conditionals (only essential guards)
- [ ] No nested blocks > 2 levels

### Metrics Check (Phase 3)
- [ ] Lines reduced by ~60% (Original: `_____`, After: `_____`, Reduction: `_____`%)
- [ ] Complexity reduced by ≥ 85% (Original: `_____`, After: `_____`, Reduction: `_____`%)

### Commit Phase 3
- [ ] `git add src/`
- [ ] `git commit -m "Phase 3: Complex extractions (X methods, Y% complexity reduction)"`

**Phase 3 Complete:** `✅ / ❌`

---

## Phase 4: Documentation & Cleanup (1-2 hours, 10% of time)

**Start Time:** `__________` | **End Time:** `__________` | **Actual:** `_____ hours`

### Step 4.1: Enhance run() Docstring (30 min)
- [ ] One-line summary
- [ ] 2-3 paragraph explanation of pattern used
- [ ] Execution Flow section (numbered steps)
- [ ] Complete Args/Returns/Raises
- [ ] Complexity metrics (before/after)
- [ ] Usage example
- [ ] See Also section (helpers + docs)

### Step 4.2: Review Helper Docstrings (15 min)
- [ ] All helpers have one-line summary
- [ ] All helpers have 1-3 paragraph explanation
- [ ] All helpers have Args/Returns
- [ ] All helpers have Complexity Reduction note

### Step 4.3: Check for TODOs and Cleanup (15 min)
- [ ] Search for TODO comments: `grep -r "TODO" src/<path>/target.py`
- [ ] Search for FIXME comments: `grep -r "FIXME" src/<path>/target.py`
- [ ] Search for debug code: `grep -r "print(" src/<path>/target.py`
- [ ] Remove or address all findings

### Step 4.4: Create Refactoring Summary (30 min)
- [ ] Create `REFACTORING_COMPLETE_<target>.md` in docs/
- [ ] Include executive summary with metrics table
- [ ] Include phase-by-phase breakdown
- [ ] Include helper methods catalog
- [ ] Include design patterns applied
- [ ] Include testing pyramid
- [ ] Include verification results
- [ ] Include review focus areas

### Step 4.5: Create ADR (30 min)
- [ ] Determine next ADR number: `_____`
- [ ] Create `docs/architecture/decisions/XXX-complexity-reduction-<target>.md`
- [ ] Fill in Status, Context, Decision, Consequences
- [ ] Link to PR, implementation files, METHODOLOGY.md
- [ ] Update `docs/architecture/decisions/README.md` index

### Step 4.6: Final Verification (15 min)
- [ ] `pytest tests/test_<target>*.py -v` → 100% pass
- [ ] `pytest tests/ -v` → No new failures
- [ ] `mypy src/<path>/target.py` → Clean
- [ ] `ruff check src/<path>/target.py` → Clean
- [ ] Complexity ≤ 15 (Actual: `_____`)
- [ ] Coverage maintained or improved (Actual: `_____`%)

### Step 4.7: Non-Functional Verification (15 min) - If baseline captured
- [ ] Performance delta within ±5% (Actual: `_____`%)
- [ ] Memory delta within ±10% (Actual: `_____`%)
- [ ] Logging structure unchanged (event count: `_____`)
- [ ] Security posture unchanged (no new permissions/sinks)

### Step 4.8: Commit Phase 4
- [ ] `git add src/ docs/`
- [ ] `git commit -m "Phase 4: Documentation and cleanup"`
- [ ] Push all commits to remote

**Phase 4 Complete:** `✅ / ❌`

---

## Post-Refactoring

- [ ] Create draft PR with comprehensive description
- [ ] Link ADR in PR description
- [ ] Request security review from `__________`
- [ ] Request peer review from `__________`
- [ ] Address Copilot automated review
- [ ] Update PR status to "Ready for Review"
- [ ] Respond to feedback
- [ ] Merge after approval
- [ ] Monitor for issues post-merge (30 days)

---

## Final Metrics Summary

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| **Cognitive Complexity** | _____ | _____ | _____% |
| **Lines** | _____ | _____ | _____% |
| **Helper Methods** | 0 | _____ | +_____ |
| **Test Coverage** | _____% | _____% | ±_____pp |
| **Tests Created** | 0 | _____ | +_____ |
| **Mutation Score** | - | _____% | ≤ 10% |
| **Time Investment** | - | _____ h | Target: 10-15h |

**Behavioral Changes:** `0` ✅
**Regressions:** `0` ✅

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Version:** 1.1
**Last Updated:** 2025-10-25
**Team:** Elspeth Engineering
