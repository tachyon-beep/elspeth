# Coverage-Guided Fuzzing Readiness Tracking

**Purpose**: Track prerequisites for Phase 2 (Atheris coverage-guided fuzzing) implementation

**Status**: 🔶 **BLOCKED** - Awaiting Atheris Python 3.12 support

**Last Updated**: 2025-10-25

**Related docs**:
- **Phase 2 strategy**: [fuzzing_coverage_guided.md](./fuzzing_coverage_guided.md)
- **Phase 2 roadmap**: [fuzzing_coverage_guided_plan.md](./fuzzing_coverage_guided_plan.md)
- **IRAP risk acceptance**: [fuzzing_irap_risk_acceptance.md](./fuzzing_irap_risk_acceptance.md) - For assessor review
- **Phase 1 (Active)**: [fuzzing.md](./fuzzing.md) - Hypothesis property-based testing

---

## Quick Status Overview

| Category | Status | Details |
|----------|--------|---------|
| **Atheris Python 3.12 Support** | 🔴 **BLOCKED** | Not yet available (as of Oct 2025) |
| **Phase 1 Operational** | 🟡 **IN PROGRESS** | Hypothesis implementation underway |
| **Phase 1 Demonstrates Value** | 🟡 **PENDING** | Need ≥2 bugs found |
| **Team Readiness** | 🟡 **PARTIAL** | Training needed |
| **CI Infrastructure** | 🟢 **READY** | Capacity available |
| **Resource Allocation** | 🟡 **PENDING** | Needs approval |

**Overall**: **NOT READY** - Est. earliest start: Q2 2025

---

## Prerequisite Tracking

### 1. Atheris Python 3.12 Support 🔴 **BLOCKER**

**Requirement**: Atheris library must support Python 3.12

**Current Status**: ❌ NOT AVAILABLE
- **Last checked**: 2025-10-25
- **Atheris version**: 2.3.0 (supports up to Python 3.11)
- **GitHub issue**: https://github.com/google/atheris/issues/XXX (track here)

**How to Check**:
```bash
# Test on Python 3.12 environment
python3.12 -m pip install atheris
python3.12 -c "import atheris; print(atheris.__version__)"

# If successful, check basic functionality
python3.12 -c "
import atheris
@atheris.instrument_func
def TestOneInput(data):
    pass
atheris.Setup([], TestOneInput)
print('Atheris Python 3.12 support: OK')
"
```

**Expected Outcome**: No import errors, basic instrumentation works

**Tracking**:
- [ ] Monitor GitHub releases monthly: https://github.com/google/atheris/releases
- [ ] Subscribe to issue notifications
- [ ] Check Python 3.12 in Atheris CI matrix
- [ ] Test pre-release versions if available

**Fallback Options** (if Atheris delayed >6 months):
1. **Pythia**: Alternative Python fuzzer (check Python 3.12 support)
2. **lain**: Lightweight Python fuzzer (less mature)
3. **Hypothesis with coverage guidance**: Use `hypothesis-jsonschema` + custom strategies
4. **Defer to Python 3.13**: Wait for broader ecosystem support

**Decision Date**: Review monthly; escalate if blocked >12 months

---

### 2. Phase 1 (Hypothesis) Operational 🟡 **IN PROGRESS**

**Requirement**: Hypothesis property-based testing running in CI with ≥15 property tests

**Current Status**: 🟡 IN PROGRESS
- **Property tests implemented**: 0 / 15 target
- **CI integration**: ❌ Not yet configured
- **Bug injection tests**: ❌ Not yet implemented
- **Oracle specifications**: ❌ Not yet documented

**Tracking Checklist**:
- [ ] Oracle table complete for 5 modules (fuzzing.md Section 1.3)
- [ ] Hypothesis profiles configured in `pyproject.toml`
- [ ] Bug injection smoke tests: 2-3 tests in `tests/fuzz_smoke/`
- [ ] Property tests: ≥15 across 5 security modules
  - [ ] `path_guard.py`: 5 properties
  - [ ] `approved_endpoints.py`: 5 properties
  - [ ] `sanitizers.py`: 3 properties
  - [ ] `prompt_renderer.py`: 4 properties (if applicable)
  - [ ] `config_parser.py`: 3 properties (if applicable)
- [ ] CI workflows operational:
  - [ ] `.github/workflows/fuzz.yml` (PR fast tests, <5 min)
  - [ ] `.github/workflows/fuzz-nightly.yml` (deep exploration, 15 min)
- [ ] Crash triage procedures documented
- [ ] Severity taxonomy (S0-S4) documented

**How to Verify**:
```bash
# Check property tests exist
pytest tests/fuzz_props/ --collect-only | grep "test_" | wc -l
# Should be ≥15

# Check CI integration
gh workflow list | grep fuzz

# Check oracle documentation
grep -r "Oracle:" tests/fuzz_props/*.py | wc -l
```

**Target Completion**: Week 3-4 of Phase 1

---

### 3. Phase 1 Demonstrates Value 🟡 **PENDING**

**Requirement**: Hypothesis fuzzing must find ≥2 security bugs (S0-S2) to prove ROI

**Current Status**: 🟡 PENDING Phase 1 implementation
- **Bugs found**: 0 / 2 target
- **Severity breakdown**: N/A

**Success Criteria**:
- ✅ ≥2 unique security bugs discovered (S0, S1, or S2 severity)
- ✅ At least 1 bug is S0 or S1 (critical/high severity)
- ✅ Bugs confirmed as real vulnerabilities (not false positives)
- ✅ Fixes implemented and verified

**Tracking**:
| Date | Bug Description | Severity | Module | Status |
|------|-----------------|----------|--------|--------|
| TBD | | | | |
| TBD | | | | |

**Alternative Success Criteria** (if <2 bugs):
- ⚠️ If 0-1 bugs found after Phase 1: Reevaluate Phase 2 investment
- ⚠️ Strong justification needed: IRAP requirement, compliance mandate, or high-confidence hypothesis about Atheris discovering new bug classes

**Decision Point**: End of Phase 1 (Week 3-4)

---

### 4. Team Readiness 🟡 **PARTIAL**

**Requirement**: Team familiar with fuzzing concepts and Atheris basics

**Current Status**: 🟡 PARTIAL
- **Fuzzing concepts**: ⚠️ Limited (basic understanding)
- **Hypothesis experience**: 🟡 Building (Phase 1 in progress)
- **Atheris experience**: ❌ None
- **Crash triage skills**: 🟡 Moderate
- **ASan/sanitizers**: ⚠️ Limited

**Training Checklist**:
- [ ] **Team lead completes Atheris tutorial** (2-4 hours)
  - https://github.com/google/atheris/tree/master/example_fuzzers
  - Build and run 2-3 example harnesses locally
  - Understand FuzzedDataProvider, corpus, coverage guidance
- [ ] **Review fuzzing fundamentals** (1-2 hours)
  - https://www.fuzzingbook.org/ (chapters 1, 2, 11, 12)
  - libFuzzer concepts: https://llvm.org/docs/LibFuzzer.html
- [ ] **AddressSanitizer basics** (1 hour)
  - https://github.com/google/sanitizers/wiki/AddressSanitizer
  - Understand ASan output, common bugs (use-after-free, buffer overflow)
- [ ] **Hands-on practice** (2-3 hours)
  - Fuzz a simple Python function with Atheris
  - Plant a bug, verify Atheris finds it
  - Practice crash minimization

**Skills Assessment** (update after training):
| Skill | Required Level | Current | Gap | Training Plan |
|-------|----------------|---------|-----|---------------|
| Fuzzing concepts | Intermediate | Beginner | Medium | Fuzzing Book ch 1-2, 11-12 |
| Atheris API | Intermediate | None | High | Atheris tutorial + examples |
| Harness development | Intermediate | None | High | Build 2-3 practice harnesses |
| Crash triage | Intermediate | Basic | Medium | Hands-on with planted bugs |
| AddressSanitizer | Basic | None | Medium | ASan documentation + practice |
| CI/automation | Intermediate | Good | Low | Atheris CI examples |

**Target**: All gaps reduced to "Low" before Phase 2a

---

### 5. CI Infrastructure 🟢 **READY**

**Requirement**: CI capacity for 2-hour nightly Atheris runs

**Current Status**: 🟢 READY
- **GitHub Actions capacity**: ✅ Sufficient
- **Nightly job slots**: ✅ Available
- **Compute resources**: ✅ Can allocate 2 hours/day
- **Storage**: ✅ Can accommodate 2-3GB corpus + artifacts

**Resource Requirements**:
- **Nightly fuzzing**: 2 hours × 4 vCPUs = 8 vCPU-hours/day
- **Weekly deep fuzzing**: 8 hours × 8 vCPUs = 64 vCPU-hours/week (on-demand)
- **Storage**: ~2.5GB (corpus + crash artifacts with 90-day retention)

**Cost Estimate**: $50-100/month (GitHub Actions or equivalent)

**Infrastructure Checklist**:
- [x] GitHub Actions workflow quota sufficient
- [x] Can run 2-hour timeout jobs
- [x] Artifact storage available (90-day retention)
- [x] Notifications configured (Slack/email for crash alerts)
- [ ] Corpus storage solution chosen (S3, GitHub Artifacts, or local)
- [ ] Monitoring dashboard prepared (optional but recommended)

**Note**: Infrastructure ready, but will be configured during Phase 2a

---

### 6. Resource Allocation 🟡 **PENDING**

**Requirement**: 40-80 hours approved for Phase 2 implementation

**Current Status**: 🟡 PENDING APPROVAL
- **Hours requested**: 40-80 hours over 5-6 weeks
- **Team allocation**: 1 senior Python developer + advisor
- **Budget**: ~$50-110/month ongoing CI costs
- **Approval status**: ❌ Not yet requested

**Resource Breakdown**:
| Phase | Hours | Timeline | Deliverables |
|-------|-------|----------|--------------|
| Phase 2a (Infrastructure) | 10-15 | Week 1 | Atheris environment, CI, corpus storage |
| Phase 2b (Harnesses) | 15-25 | Weeks 2-3 | 3 harnesses for top security modules |
| Phase 2c (Automation) | 10-15 | Week 4 | Nightly runs, crash triage automation |
| Phase 2d (Optimization) | 10-20 | Weeks 5-6 | Coverage optimization, ASan, docs |
| **Total** | **45-75** | **5-6 weeks** | Production-ready coverage-guided fuzzing |

**Approval Checklist**:
- [ ] Sprint capacity available (10-15 hours/week for 5-6 weeks)
- [ ] Budget approved for CI costs ($50-110/month ongoing)
- [ ] Stakeholder buy-in (security team, tech lead, product)
- [ ] IRAP/compliance justification documented (if needed)
- [ ] Alternative priorities deprioritized or deferred

**Decision Process**:
1. **Phase 1 completes** → Demonstrates fuzzing ROI (≥2 bugs)
2. **Atheris Python 3.12 available** → Technical blocker removed
3. **Resource request** → Present to tech lead with ROI evidence
4. **Approval** → Allocate sprint capacity

**Target Approval Date**: After Phase 1 success + Atheris availability (Est. Q2 2025)

---

## Go/No-Go Decision Framework

### GO Criteria (All must be TRUE)

- ✅ **Atheris Python 3.12 support available** (BLOCKER)
- ✅ **Phase 1 operational**: ≥15 property tests, CI integrated
- ✅ **Phase 1 demonstrates value**: ≥2 S0-S2 bugs found
- ✅ **Team readiness**: Lead developer completed Atheris training
- ✅ **Resource allocation**: 40-80 hours approved

### NO-GO / DEFER Criteria (Any TRUE)

- ❌ **Phase 1 finds <2 bugs**: Hypothesis may be sufficient; revisit in 6 months
- ❌ **Atheris blocked >12 months**: Consider alternative fuzzers or defer
- ❌ **Team capacity unavailable**: Defer until bandwidth available
- ❌ **False positive rate >15% in Phase 1**: Address Hypothesis issues first
- ❌ **IRAP/compliance doesn't require**: Lower priority; focus on other security initiatives

---

## Monitoring & Review Schedule

### Monthly Review (Until Unblocked)

**Check**: Last Friday of each month, 15-minute review

**Review Items**:
1. **Atheris Python 3.12 status**: Check GitHub releases, issues, CI matrix
2. **Phase 1 progress**: Property test count, bugs found, CI status
3. **Team training**: Any progress on Atheris familiarity
4. **Resource availability**: Sprint planning for next quarter

**Owner**: Security Engineering Lead

**Tracking**:
| Review Date | Atheris Status | Phase 1 Progress | Decision |
|-------------|----------------|------------------|----------|
| 2025-10-25 | Not available | Not started | Continue waiting |
| 2025-11-29 | TBD | TBD | TBD |
| 2025-12-27 | TBD | TBD | TBD |
| 2026-01-31 | TBD | TBD | TBD |

---

### Quarterly Strategic Review

**Check**: End of each quarter

**Review Items**:
1. **Strategic value**: Does Atheris still align with security roadmap?
2. **Alternative approaches**: Are there better fuzzing solutions available?
3. **Resource commitment**: Can we still commit 40-80 hours?
4. **Compliance requirements**: Any changes to IRAP/accreditation needs?

**Owner**: CISO / Security Leadership

**Decision Points**:
- **Continue waiting**: Atheris still best option, justified by threat profile
- **Explore alternatives**: Pythia, lain, or other Python fuzzers
- **Defer indefinitely**: Lower priority, focus elsewhere
- **Escalate**: Request vendor support or alternative solution

---

## Notification Plan

### When to Notify Team

**Trigger**: Atheris Python 3.12 support announced

**Notification**:
```
Subject: [FUZZING] Atheris Python 3.12 Support Available - Phase 2 Ready

Team,

Atheris now supports Python 3.12! We can begin Phase 2 (coverage-guided fuzzing) implementation.

Next Steps:
1. Complete Phase 1 (Hypothesis) if not already done
2. Verify Phase 1 found ≥2 security bugs (proves ROI)
3. Team lead: Complete Atheris tutorial (2-4 hours)
4. Request resource allocation: 40-80 hours over 5-6 weeks
5. Review readiness: docs/security/fuzzing/fuzzing_coverage_guided_readiness.md

Estimated start: [DATE] (pending approval)

References:
- Strategy: docs/security/fuzzing/fuzzing_coverage_guided.md
- Roadmap: docs/security/fuzzing/fuzzing_coverage_guided_plan.md

[Security Lead Name]
```

---

## Alternatives to Consider (If Atheris Delayed >12 Months)

### Option A: Alternative Python Fuzzers

1. **Pythia** (https://github.com/microsoft/pythia)
   - Microsoft-developed Python fuzzer
   - Check Python 3.12 support
   - Less mature than Atheris

2. **lain** (https://github.com/laineus/lain)
   - Lightweight Python fuzzer
   - Limited coverage guidance
   - May support Python 3.12 sooner

3. **Hypothesis with coverage** (https://hypothesis.readthedocs.io/)
   - Use Hypothesis `hypothesis.database` + coverage.py
   - Not true coverage-guided, but better than random
   - Already using Hypothesis (low friction)

### Option B: Defer to Python 3.13+

- Wait for broader Python 3.12+ fuzzing ecosystem
- Focus on optimizing Hypothesis in the meantime
- Revisit decision in 2026

### Option C: External Fuzzing Service

- **OSS-Fuzz** (Google): For open-source projects
- **Mayhem** (ForAllSecure): Commercial, on-prem option
- **Fuzzbuzz**: Managed fuzzing platform

**Tradeoff**: Less control, but expert configuration and infrastructure

---

## Status History

| Date | Status | Blocker | Notes |
|------|--------|---------|-------|
| 2025-10-25 | 🔴 BLOCKED | Atheris Python 3.12 | Initial documentation created; Phase 1 not started |
| 2025-XX-XX | TBD | TBD | (Update monthly) |

---

## Quick Reference: Am I Ready to Start Phase 2?

**Use this checklist before beginning Phase 2 implementation**:

```
Prerequisites Checklist:

[ ] Atheris works on Python 3.12 (tested and verified)
[ ] Phase 1 (Hypothesis) has ≥15 property tests running in CI
[ ] Phase 1 found ≥2 security bugs (S0-S2 severity)
[ ] Team lead completed Atheris tutorial (2-4 hours)
[ ] Resource allocation approved (40-80 hours over 5-6 weeks)
[ ] CI infrastructure ready (2-hour nightly capacity)
[ ] Budget approved (~$50-110/month for CI)

If ALL checked: ✅ READY - Proceed to Phase 2a
If ANY unchecked: ❌ NOT READY - Address gaps first
```

**Contact**: Security Engineering Lead for questions or status updates

**Last Updated**: 2025-10-25 | **Next Review**: 2025-11-29
