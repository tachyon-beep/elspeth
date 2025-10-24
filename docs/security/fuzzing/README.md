# Fuzzing Documentation

**Security testing for Elspeth using property-based fuzzing (Hypothesis)**

**Status**: Phase 1 ready for implementation • Phase 2 archived (blocked 6+ months)

---

## 📋 Quick Start

**New to fuzzing Elspeth?** Start here:

1. **Read**: [IMPLEMENTATION.md](./IMPLEMENTATION.md) (tactical guide) - Start here for hands-on implementation
2. **Reference**: [fuzzing.md](./fuzzing.md) (strategy) - Deep dive on oracles, invariants, rationale
3. **Check**: [fuzzing_plan.md](./fuzzing_plan.md) (roadmap) - Week-by-week checklist

**For IRAP Assessors**: [fuzzing_irap_risk_acceptance.md](./fuzzing_irap_risk_acceptance.md)

---

## 📁 Document Overview

| Document | Purpose | Audience | When to Read |
|----------|---------|----------|--------------|
| **[IMPLEMENTATION.md](./IMPLEMENTATION.md)** | Tactical step-by-step guide (635 lines) | Developers | **Read FIRST** - Hands-on implementation |
| **[fuzzing.md](./fuzzing.md)** | Canonical strategy (939 lines) | Security team, developers | Reference for oracles, rationale, decisions |
| **[fuzzing_plan.md](./fuzzing_plan.md)** | Quick reference roadmap (228 lines) | Project managers, leads | High-level planning |
| **[fuzzing_irap_risk_acceptance.md](./fuzzing_irap_risk_acceptance.md)** | Risk assessment for Phase 2 deferral (510 lines) | IRAP assessors, CISO | Compliance evidence |

**Total**: 4 documents, ~2,300 lines (down from 8 docs, 3,641 lines)

---

## 🎯 Implementation Status

**Phase 1 (Property-Based Fuzzing)**: Ready to implement

- **Tool**: Hypothesis (property-based testing on Python 3.12)
- **Target**: 5 security modules (path_guard, URL validation, sanitizers, etc.)
- **Timeline**: 30-45 hours over 3-4 weeks
- **Success Criteria**: ≥15 property tests, ≥2 bugs found, ≥85% coverage

**Phase 2 (Coverage-Guided Fuzzing)**: Archived - blocked 6+ months

- **Tool**: Atheris (when Python 3.12 support available)
- **Blocker**: Awaiting Atheris Python 3.12 support (Q2 2025+ estimate)
- **Status**: [Archived](../archive/phase2_blocked_atheris/README.md) - fully designed, ready when unblocked
- **Decision**: Focus 100% on Phase 1 implementation; revisit Phase 2 after Phase 1 demonstrates value

---

## 🚀 Getting Started (30 seconds)

```bash
# 1. Read tactical guide
cat docs/security/fuzzing/IMPLEMENTATION.md

# 2. Install Hypothesis
pip install hypothesis pytest-hypothesis

# 3. Create test directories
mkdir -p tests/fuzz_props tests/fuzz_smoke

# 4. Configure pyproject.toml
# See IMPLEMENTATION.md Week 0, Step 3

# 5. Write first property test
# See IMPLEMENTATION.md Week 1, Step 2
```

---

## 📊 Key Concepts

### What is Property-Based Fuzzing?

**Traditional testing**: Write specific examples

```python
def test_path_guard():
    assert resolve("../../../etc/passwd") raises SecurityError
```

**Property-based fuzzing**: Define invariants, generate thousands of examples

```python
@given(candidate=st.text())
def test_path_guard(tmp_path, candidate):
    result = resolve_under_base(tmp_path, candidate)
    # Oracle: result MUST be under tmp_path (always)
    assert result.is_relative_to(tmp_path)
```

**Value**: Discovers edge cases you didn't think to test

### Oracle Specifications (CRITICAL)

**Oracles define "correct behavior"**. Without oracles, fuzzing just exercises code without catching bugs.

Example oracle table (from `fuzzing.md` Section 1.3):

| Target | Invariants (MUST hold) | Allowed Exceptions |
|--------|------------------------|-------------------|
| **Path Guard** | • Result always under `base_dir`<br>• No symlink escape<br>• Normalized | `ValueError`, `SecurityError` |
| **URL Validation** | • Scheme in {`https`, `http`}<br>• No credentials in URL | `ValueError`, `URLError` |

**See**: `fuzzing.md` Section 1.3 for complete oracle table

### Bug Injection Validation (Proof Tests Work)

**Problem**: How do you know your property tests actually catch bugs?

**Solution**: Bug injection smoke tests

1. Write property test with oracle
2. Create intentionally vulnerable implementation
3. Run test with `BUG_INJECTION_ENABLED=1`
4. Test MUST FAIL (proves it catches bugs)
5. Run test normally → test MUST PASS

**See**: `IMPLEMENTATION.md` Week 1, Step 4 for example

---

## 🏆 Success Criteria

**Phase 1 is complete when ALL are true**:

- ✅ **Bug injection validation**: 100% of injected bugs caught
- ✅ **Property tests**: ≥15 tests across 5 security modules
- ✅ **Bug discovery**: ≥2 real security bugs found (S0-S2)
- ✅ **CI integration**: <5 min PR tests, <15 min nightly
- ✅ **Coverage**: ≥85% branch coverage on security modules
- ✅ **Quality**: <10% false positive rate

**Then**: Update IRAP risk acceptance → Production shakedown cruise (PROTECTED data)

---

## 🔍 Coverage Philosophy

**Target**: 85% branch coverage, not 95%

**Rationale**:

- Last 15% often unreachable code (error handlers, dead code)
- Property-based testing naturally achieves ~85%
- Diminishing returns: 85%→95% requires 3x effort
- Better ROI: More modules at 85% than fewer at 95%

**See**: `fuzzing.md` Goals section for full rationale

---

## 📦 Archived Documents

### Phase 2: Coverage-Guided Fuzzing

**Location**: [docs/security/archive/phase2_blocked_atheris/](../archive/phase2_blocked_atheris/)

**Why Archived**: Atheris (coverage-guided fuzzing tool) doesn't support Python 3.12 yet. Blocked for 6+ months (Q2 2025+ estimate).

**What's There**: Complete Phase 2 strategy, roadmap, readiness tracking (1,251 lines) - fully designed and ready to implement when unblocked.

**When to Revisit**:

- ✅ Phase 1 operational (≥15 property tests)
- ✅ Phase 1 found ≥2 bugs (proves ROI)
- ✅ Atheris Python 3.12 support available
- ✅ Resource allocation approved (40-80 hours)

**Check Monthly**: [Atheris releases](https://github.com/google/atheris/releases)

### Review Documents

**Location**: [docs/security/archive/](../archive/)

**Why Archived**: Feedback incorporated into main documents

- `fuzzing_design_review.md` - Internal risk review (feedback in `fuzzing.md`)
- `fuzzing_design_review_external.md` - External review (feedback incorporated)

---

## 🛠️ Tools & Dependencies

**Phase 1** (Active):

- **Hypothesis**: Property-based testing framework
- **pytest**: Test runner
- **pytest-hypothesis**: Hypothesis pytest integration

```bash
pip install hypothesis pytest-hypothesis
# Or from lockfile:
pip install -r requirements-dev.lock --require-hashes
```

**Phase 2** (Blocked):

- **Atheris**: Coverage-guided fuzzing (Google) - Python 3.12 support pending

---

## 📈 Metrics & Tracking

**Current Status**: Not started (0/15 property tests implemented)

**Planned**:

- Metrics dashboard: `docs/security/fuzzing/METRICS.md` (created during implementation)
- Bug tracking: GitHub issues with `[FUZZ]` prefix
- Coverage reports: Generated weekly, tracked in METRICS.md

**See**: `IMPLEMENTATION.md` Week 4 for metrics dashboard template

---

## 🤝 Contributing

**Adding new property tests**:

1. Identify security-critical module
2. Define oracle specifications (what MUST always be true?)
3. Write property test with oracle assertions
4. Add bug injection test (prove it catches bugs)
5. Document in METRICS.md

**See**: `IMPLEMENTATION.md` Week 2 for examples

---

## 📞 Support

**Questions about**:

- **Implementation**: See `IMPLEMENTATION.md` Troubleshooting section
- **Strategy decisions**: See `fuzzing.md` FAQs or contact Security Engineering Lead
- **IRAP compliance**: See `fuzzing_irap_risk_acceptance.md`

**Report bugs found**: Create GitHub issue with `[FUZZ]` prefix, severity S0-S4

---

## 🔗 External Resources

- **Hypothesis Documentation**: <https://hypothesis.readthedocs.io/>
- **Property-Based Testing Intro**: <https://fsharpforfunandprofit.com/posts/property-based-testing/>
- **Fuzzing Book** (advanced): <https://www.fuzzingbook.org/>

---

## 📜 Version History

| Date | Change | By |
|------|--------|-----|
| 2025-10-25 | Documentation reorganization: 8 docs → 4 docs | Claude Code peer review |
| 2025-10-25 | Created IMPLEMENTATION.md (tactical guide) | Claude Code |
| 2025-10-25 | Archived Phase 2 docs (blocked 6+ months) | Claude Code |
| 2025-10-25 | Fixed Hypothesis config syntax, coverage targets | Claude Code |
| 2025-10-25 | Fixed filename typo: `fuzzing_desing` → `fuzzing_design` | Claude Code |
| 2025-01-XX | Initial fuzzing strategy created | Original author |

---

**Last Updated**: 2025-10-25

**Next Review**: After Phase 1 Week 1 completion (first property test working)
