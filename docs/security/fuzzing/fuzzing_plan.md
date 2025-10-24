# Phase 1 Fuzzing Roadmap (Quick Reference)

This document provides a concise, execution-focused roadmap for **Phase 1** fuzzing (Hypothesis property-based testing). For strategy, targets, oracles, and detailed procedures, see the canonical guide: [fuzzing.md](./fuzzing.md)

**Phase 1 (Active - Implement This)**:

- **Canonical strategy**: [fuzzing.md](./fuzzing.md) - Complete Phase 1 strategy with oracles
- **Quick roadmap**: This document - Week-by-week implementation checklist
- **IRAP risk acceptance**: [fuzzing_irap_risk_acceptance.md](./fuzzing_irap_risk_acceptance.md) - For assessors

**Phase 2 (Archived - Blocked 6+ months)**: [Why Archived?](../archive/phase2_blocked_atheris/README.md)

- Coverage-guided fuzzing with Atheris awaiting Python 3.12 support (Q2 2025+)
- Fully designed and ready to implement when unblocked
- See archive README for rationale and when to revisit

---

## Executive Summary

**Approach**: Hypothesis property-based testing on Python 3.12
**Timeline**: 3-4 weeks, 30-45 hours
**Key Innovation**: Explicit oracle specifications + bug injection validation

---

## Phased Timeline

### Phase 0: Foundation (Week 1, 8-15 hours)

**Goal**: Prove fuzzing effectiveness before full commitment

| Task | Hours | Deliverable | Success Criteria |
|------|-------|-------------|------------------|
| Define oracle specifications | 2 | Complete oracle table for 5 modules | [See fuzzing.md Section 1.3](./fuzzing.md) |
| Configure Hypothesis profiles | 1 | `pyproject.toml` with ci/explore profiles | [See fuzzing.md Section 1.4](./fuzzing.md) |
| Implement bug injection tests | 3 | 2-3 smoke tests in `tests/fuzz_smoke/` | [See fuzzing.md Section 2.2](./fuzzing.md) |
| Write initial property tests | 3-5 | 3-5 properties for `path_guard.py` | [See fuzzing.md Phase 1, Task 1](./fuzzing.md) |
| CI integration prototype | 2-4 | Fast PR workflow (<5 min) | [See fuzzing.md Section 2.3](./fuzzing.md) |

**Decision Point**: If bug injection tests catch 100% of injected bugs AND 1+ real bug found → Proceed to Phase 1

---

### Phase 1: Expansion (Weeks 2-3, 15-25 hours)

**Goal**: Production-ready fuzzing across security-critical modules

| Task | Hours | Deliverable | Details |
|------|-------|-------------|---------|
| Expand property test suite | 8-12 | 15-20 properties across 5 modules | [Target modules](./fuzzing.md) |
| Add regression seed tests | 3-5 | 10-15 explicit seeds per module | [See fuzzing.md Task 2](./fuzzing.md) |
| Nightly deep exploration | 2-3 | Nightly CI workflow (15 min) | [See fuzzing.md Section 2.3](./fuzzing.md) |
| Crash triage procedures | 2-5 | Severity taxonomy + GitHub templates | [See fuzzing.md Section 3.1](./fuzzing.md) |

**Decision Point**: If false positive rate <10% AND CI runtime <5 min → Proceed to Phase 2

---

### Phase 2: Stabilization (Week 4, 5-10 hours)

**Goal**: Optimize, document, and prepare for long-term maintenance

| Task | Hours | Deliverable |
|------|-------|-------------|
| Coverage optimization | 2-4 | Target 85% branch coverage on security modules |
| Performance tuning | 1-3 | Optimize slow properties, improve mocking |
| IRAP compliance docs | 2-3 | Evidence package for accreditation |
| Team training materials | 1-2 | Runbook for crash triage and property writing |

---

## Critical Success Factors

### Must-Haves (Non-Negotiable)

1. ✅ **Oracle specifications** - Explicit invariants for each target (fuzzing.md Section 1.3)
2. ✅ **Bug injection validation** - Prove tests catch vulnerabilities (fuzzing.md Section 2.2)
3. ✅ **CI guardrails** - Timeout budgets + crash artifacts (fuzzing.md Section 2.3)
4. ✅ **Severity taxonomy** - Clear S0-S4 triage SLAs (fuzzing.md Section 3.1)

### Key Metrics (See [fuzzing.md Success Criteria](./fuzzing.md) for full list)

- **Bug discovery**: ≥1 bug in Phase 0, ≥2 total in Phase 1
- **Coverage**: 85% branch coverage on security modules (not 95%)
- **Performance**: <5 min PR tests, <15 min nightly
- **Quality**: <10% false positive rate, <5% test flakiness

---

## Risks & Mitigations

Full risk analysis in [fuzzing_design_review.md](./fuzzing_design_review.md) and [external review](./fuzzing_design_review_external.md)

| Risk | Mitigation | Reference |
|------|-----------|-----------|
| Weak oracles (false negatives) | Bug injection smoke tests validate effectiveness | fuzzing.md Section 2.2 |
| Strict oracles (false positives) | Start with permissive oracles, tighten based on data | fuzzing_design_review.md |
| CI timeout runaway | Hard 5/15 min limits, HYPOTHESIS_PROFILE configs | fuzzing.md Section 2.3 |
| Resource exhaustion | Per-test deadline (500ms), tempdir cleanup | fuzzing.md Section 1.4 |

---

## Quick Start Checklist

Use this for week-by-week execution:

### Week 1 (Phase 0)

- [ ] Copy oracle table from fuzzing.md Section 1.3 → write first 3 oracles
- [ ] Add Hypothesis profiles to `pyproject.toml` (ci + explore)
- [ ] Write 2 bug injection tests (path traversal + URL validation)
- [ ] Implement 3 property tests for `path_guard.py`
- [ ] Add `.github/workflows/fuzz.yml` (fast PR tests)
- [ ] **Decision**: Bug injection passing? Real bugs found? → Continue

### Week 2 (Phase 1 - Part 1)

- [ ] Expand to 8-10 total property tests (add URL validation + sanitizers)
- [ ] Add `tests/fuzz_props/seeds.py` with 5+ regression seeds
- [ ] Implement `.github/workflows/fuzz-nightly.yml` (deep exploration)
- [ ] Document crash triage procedure (see fuzzing.md Section 3.1)

### Week 3 (Phase 1 - Part 2)

- [ ] Complete 15-20 property tests across 5 modules
- [ ] Add severity taxonomy + GitHub issue template
- [ ] Run coverage analysis (pytest --cov)
- [ ] **Decision**: FP rate <10%? CI <5min? → Continue

### Week 4 (Phase 2)

- [ ] Optimize slow properties (profiling, mocking)
- [ ] Document untested branches + rationale
- [ ] Create IRAP evidence package
- [ ] Write team training materials (crash triage playbook)

---

## Resource Requirements

**Team**: 1 senior Python developer with security testing experience
**Time**: 30-45 hours over 3-4 weeks (10-12 hours/week)
**Skills**: Python testing, Hypothesis basics (1-day learning curve), security awareness

**Infrastructure** (minimal):

- CI compute: +5-15 min per run (PR + nightly)
- Storage: ~50MB for `.hypothesis/examples/` corpus
- No dedicated fuzzing servers required

---

## Links to Detailed Information

| Topic | Where to Find It |
|-------|------------------|
| Oracle specifications (CRITICAL) | [fuzzing.md Section 1.3](./fuzzing.md) |
| Bug injection smoke tests | [fuzzing.md Section 2.2](./fuzzing.md) |
| Hypothesis profiles config | [fuzzing.md Section 1.4](./fuzzing.md) |
| CI workflow templates | [fuzzing.md Section 2.3](./fuzzing.md) |
| Severity taxonomy (S0-S4) | [fuzzing.md Section 3.1](./fuzzing.md) |
| Crash triage procedures | [fuzzing.md Phase 1 Task 3](./fuzzing.md) |
| Success criteria (full list) | [fuzzing.md Success Criteria](./fuzzing.md) |
| Risk analysis | [fuzzing_design_review.md](./fuzzing_design_review.md) |
| External review recommendations | [fuzzing_design_review_external.md](./fuzzing_design_review_external.md) |
| Property test examples | [fuzzing.md Phase 1 Task 1](./fuzzing.md) |
| Seed corpus management | [fuzzing.md Phase 1 Task 2](./fuzzing.md) |

---

## Notes

- **Python version**: All fuzzing uses Python 3.12 (no version juggling)
- **Tool choice**: Hypothesis only (Atheris deferred - see fuzzing.md Appendix A)
- **CI strategy**: Fast on PR (5 min), deep nightly (15 min)
- **Corpus**: Use Hypothesis native `.hypothesis/examples/`, don't create separate corpus directory
- **Timeout handling**: Use Hypothesis `deadline` setting, not custom timeout utilities
- **Metrics**: Focus on bug discovery and false positive rate, not rigid coverage percentages
- **External review integration**: See fuzzing.md "Recommendations" section for adopted/adapted/deferred items

---

## Success Stories (Update After Implementation)

<!-- Document bugs found, security improvements, and lessons learned here -->

**Phase 0 Results** (TBD):

- Bugs found:
- Coverage improvement:
- Time invested:

**Phase 1 Results** (TBD):

- Total bugs found:
- False positive rate:
- CI impact:
- IRAP value:

---

## Path to Phase 2: Coverage-Guided Fuzzing

### When to Consider Phase 2

**Evaluate after Phase 1 completion if**:

- ✅ Phase 1 found ≥2 security bugs (proves fuzzing ROI)
- ✅ System handles classified data or PII (higher security bar)
- ✅ IRAP/compliance requires defense-in-depth
- ✅ Team has capacity for additional 40-80 hours

### Phase 2 Value Proposition

**Coverage-guided fuzzing (Atheris) complements property testing**:

- **Hypothesis (Phase 1)**: Tests *known* invariants you specify
- **Atheris (Phase 2)**: Discovers *unknown* edge cases through instrumentation

**Historical precedent**: Most critical parser CVEs found via coverage-guided fuzzing (URL parsers, path traversal, template engines)

### Current Status

🔶 **BLOCKED** - Awaiting Atheris Python 3.12 support

**Track progress**:

- **Readiness checklist**: [fuzzing_coverage_guided_readiness.md](./fuzzing_coverage_guided_readiness.md)
- **Monthly monitoring**: Check Atheris releases for Python 3.12 support
- **Estimated availability**: Q2 2025 or later

### Pre-Approved Strategy

Phase 2 implementation is **pre-designed and ready to execute** once unblocked:

- **Complete strategy**: [fuzzing_coverage_guided.md](./fuzzing_coverage_guided.md)
- **Execution roadmap**: [fuzzing_coverage_guided_plan.md](./fuzzing_coverage_guided_plan.md)
- **Resource requirements**: 40-80 hours, ~$50-110/month CI costs

**No additional design work needed** - just resource allocation when Python 3.12 support arrives.
