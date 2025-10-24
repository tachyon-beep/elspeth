# Coverage-Guided Fuzzing Roadmap (Phase 2 - Quick Reference)

**Status**: 🔶 **BLOCKED** - Awaiting Atheris Python 3.12 support

This document provides a concise, execution-focused roadmap for coverage-guided fuzzing (Phase 2). For complete strategy, see: [fuzzing_coverage_guided.md](./fuzzing_coverage_guided.md)

**Related docs**:
- **Phase 2 strategy**: [fuzzing_coverage_guided.md](./fuzzing_coverage_guided.md) - Complete Atheris implementation details
- **Readiness tracking**: [fuzzing_coverage_guided_readiness.md](./fuzzing_coverage_guided_readiness.md) - Prerequisites checklist
- **IRAP risk acceptance**: [fuzzing_irap_risk_acceptance.md](./fuzzing_irap_risk_acceptance.md) - For compliance/assessor review
- **Phase 1 (Active)**: [fuzzing.md](./fuzzing.md) - Hypothesis property-based testing
- **Phase 1 roadmap**: [fuzzing_plan.md](./fuzzing_plan.md) - Current implementation

---

## Executive Summary

**Approach**: Atheris coverage-guided fuzzing for top 3 security-critical modules
**Timeline**: 5-6 weeks, 40-80 hours (after Python 3.12 support)
**Value**: Discover unknown edge cases that property testing misses

**Key difference from Phase 1**:
- **Phase 1 (Hypothesis)**: Tests known invariants you specify
- **Phase 2 (Atheris)**: Discovers unknown bugs through coverage-guided exploration

---

## Prerequisites Checklist

Before starting Phase 2, ALL must be TRUE:

- [ ] **Phase 1 operational**: Hypothesis fuzzing running in CI, ≥15 property tests
- [ ] **Phase 1 demonstrates value**: ≥2 security bugs found (S0-S2)
- [ ] **Atheris supports Python 3.12**: Check `pip install atheris` on Python 3.12
- [ ] **CI capacity**: Can run 2-hour nightly jobs
- [ ] **Resource allocation**: 40-80 hours approved over 5-6 weeks
- [ ] **Team training**: Lead developer completed Atheris tutorial

**Track status**: [fuzzing_coverage_guided_readiness.md](./fuzzing_coverage_guided_readiness.md)

---

## Phased Timeline

### Phase 2a: Infrastructure Setup (Week 1, 10-15 hours)

**Goal**: Prepare development and CI environment for Atheris

| Task | Hours | Deliverable | Reference |
|------|-------|-------------|-----------|
| Set up Atheris dev environment | 2-3 | Python 3.12 + atheris working locally | [fuzzing_coverage_guided.md Phase 2a](./fuzzing_coverage_guided.md) |
| Create harness template | 3-4 | `fuzz/atheris/_template.py` with utilities | [Harness Design](./fuzzing_coverage_guided.md) |
| Configure nightly CI | 3-4 | `.github/workflows/fuzz-atheris-nightly.yml` | [fuzzing_coverage_guided.md Phase 2a](./fuzzing_coverage_guided.md) |
| Set up corpus storage | 2-4 | S3/Artifacts with 90-day retention | [fuzzing_coverage_guided.md Phase 2a](./fuzzing_coverage_guided.md) |

**Decision Point**: Can run 30-min Atheris harness successfully in CI? → Proceed to Phase 2b

---

### Phase 2b: Harness Development (Weeks 2-3, 15-25 hours)

**Goal**: Implement harnesses for top 3 security modules

| Module | Priority | Hours | Deliverable |
|--------|----------|-------|-------------|
| `approved_endpoints.py` | CRITICAL | 6-8 | `fuzz/atheris/fuzz_url_validator.py` + 50 seeds |
| `path_guard.py` | CRITICAL | 6-8 | `fuzz/atheris/fuzz_path_guard.py` + 50 seeds |
| `prompt_renderer.py` | HIGH | 5-7 | `fuzz/atheris/fuzz_template_renderer.py` + 50 seeds |

**Per-Harness Checklist**:
- [ ] Harness achieves >10K executions/second
- [ ] Bug injection test: catches planted vulnerability
- [ ] Seed corpus: 50+ inputs (known attacks + edge cases)
- [ ] Oracle assertions enforce security invariants
- [ ] 30-minute CI run completes successfully

**Decision Point**: All 3 harnesses operational + ≥1 new bug found? → Proceed to Phase 2c

---

### Phase 2c: CI Integration & Automation (Week 4, 10-15 hours)

**Goal**: Production-ready nightly fuzzing with automated triage

| Task | Hours | Deliverable |
|------|-------|-------------|
| Nightly 2-hour fuzzing runs | 3-4 | All 3 harnesses run in parallel |
| Automatic crash minimization | 3-4 | Minimized crashes uploaded as artifacts |
| GitHub issue auto-creation | 2-3 | S0/S1 crashes → issues with `[FUZZ-ATHERIS]` label |
| Corpus management automation | 2-4 | Dedupe, minimize, prune corpus weekly |

**Success Metrics**:
- ✅ Nightly runs complete in <2 hours
- ✅ Crashes minimized automatically
- ✅ S0/S1 findings alert within 1 hour
- ✅ Corpus grows by 100+ interesting inputs/week

---

### Phase 2d: Optimization & Hardening (Weeks 5-6, 10-20 hours)

**Goal**: Maximize coverage, integrate sanitizers, establish maintenance

| Task | Hours | Deliverable |
|------|-------|-------------|
| Coverage optimization | 4-6 | ≥90% branch coverage on fuzzed modules |
| AddressSanitizer integration | 3-5 | ASan detects memory issues |
| Performance tuning | 2-4 | >15K exec/sec per harness |
| Documentation & runbooks | 3-5 | "Atheris Crash Triage" playbook |

**Success Criteria**:
- ✅ Branch coverage >90% on fuzzed modules (higher than Hypothesis 85%)
- ✅ ≥1 unique bug found that Hypothesis missed
- ✅ ASan/MSan integrated in nightly runs
- ✅ Team trained on Atheris crash triage

---

## Critical Success Factors

### Must-Haves (Non-Negotiable)

1. ✅ **Performance**: >10K executions/second per harness (else too slow to find bugs)
2. ✅ **Oracles**: Same security invariants as Hypothesis + crash detection
3. ✅ **Bug injection validation**: Prove Atheris catches planted vulnerabilities (100% detection)
4. ✅ **Unique findings**: Must discover ≥1 bug Hypothesis missed (proves complementary value)

### Key Metrics

- **Discovery**: ≥1 unique S0-S2 bug per quarter
- **Coverage**: ≥90% branch coverage (vs 85% for Hypothesis)
- **Performance**: >10K exec/sec sustained
- **False positives**: <15% (higher tolerance than Hypothesis <10%)
- **Maintenance**: <6 hours/month

---

## Week-by-Week Execution Checklist

### Week 1: Infrastructure Setup

**Prerequisites**:
- [ ] Atheris Python 3.12 support confirmed
- [ ] Phase 1 (Hypothesis) demonstrating value (≥2 bugs found)
- [ ] Team lead completed Atheris tutorial

**Tasks**:
- [ ] Install atheris on Python 3.12: `pip install atheris`
- [ ] Create `fuzz/atheris/` directory structure
- [ ] Write harness template `fuzz/atheris/_template.py`
- [ ] Write utilities `fuzz/atheris/_harness_utils.py` (FDP helpers, oracles)
- [ ] Configure `.github/workflows/fuzz-atheris-nightly.yml`
- [ ] Test 30-min harness run in CI
- [ ] Set up corpus storage (S3 bucket or GitHub Artifacts with 90-day retention)

**Deliverable**: Template harness runs successfully for 30 min in nightly CI

---

### Week 2: First Harness (URL Validator)

**Target**: `approved_endpoints.py` (CRITICAL - SSRF risk)

**Tasks**:
- [ ] Implement `fuzz/atheris/fuzz_url_validator.py` (see fuzzing_coverage_guided.md example)
- [ ] Create seed corpus: 50+ URLs (known attacks, edge cases, valid URLs)
- [ ] Add bug injection test (plant URL bypass, verify Atheris catches it)
- [ ] Tune performance: target >10K exec/sec
- [ ] Run 1-hour local fuzzing session
- [ ] Document any crashes found

**Deliverable**: URL validator harness operational, seed corpus created

---

### Week 3: Second & Third Harnesses

**Targets**: `path_guard.py` + `prompt_renderer.py`

**Tasks**:
- [ ] Implement `fuzz/atheris/fuzz_path_guard.py`
- [ ] Implement `fuzz/atheris/fuzz_template_renderer.py`
- [ ] Create seed corpora (50+ inputs each)
- [ ] Bug injection tests for both harnesses
- [ ] Performance validation (>10K exec/sec each)
- [ ] Test all 3 harnesses in parallel (90 min nightly run)

**Deliverable**: All 3 harnesses operational in nightly CI

---

### Week 4: Automation & Integration

**Tasks**:
- [ ] Implement crash minimization script (`scripts/minimize_atheris_crash.sh`)
- [ ] Add GitHub issue auto-creation for S0/S1 crashes
- [ ] Create corpus management automation:
  - [ ] Deduplicate corpus (remove redundant inputs)
  - [ ] Minimize corpus (reduce input sizes while preserving coverage)
  - [ ] Prune old corpus (remove stale inputs, cap at 500MB per target)
- [ ] Set up monitoring dashboard (coverage, exec/sec, crashes/week)
- [ ] Test end-to-end: crash → minimize → issue creation

**Deliverable**: Automated nightly workflow with crash triage

---

### Week 5: AddressSanitizer Integration

**Tasks**:
- [ ] Configure ASan in nightly runs (`ASAN_OPTIONS`, `UBSAN_OPTIONS`)
- [ ] Test ASan detects memory issues (plant use-after-free bug)
- [ ] Document ASan crash interpretation
- [ ] Add MSan/UBSan if applicable (C extensions)
- [ ] Run extended fuzzing: 8-hour deep run on weekend

**Deliverable**: Memory safety validation operational

---

### Week 6: Documentation & Stabilization

**Tasks**:
- [ ] Write "Atheris Crash Triage Runbook" (`docs/security/fuzzing/atheris_triage.md`)
- [ ] Document unique findings vs Hypothesis
- [ ] Create IRAP evidence package section for coverage-guided fuzzing
- [ ] Coverage analysis: report branch coverage per module
- [ ] Team training session: "Responding to Atheris Crashes"
- [ ] Quarterly review process documented

**Deliverable**: Production-ready coverage-guided fuzzing with documentation

---

## Resource Requirements

**Team**: 1 senior Python developer + security engineer (advisor)
**Time**: 40-80 hours over 5-6 weeks
**Skills**: Python testing, fuzzing concepts (Atheris tutorial), security analysis

**Infrastructure**:
- **CI**: 2 hours/day nightly + 8 hours/week deep fuzzing = ~$50-100/month
- **Storage**: 2-3GB corpus + crash artifacts = ~$5-10/month
- **Tools**: Atheris (free), AddressSanitizer (free)

**Total monthly cost**: ~$50-110/month in cloud resources

---

## Risks & Mitigation

| Risk | Mitigation | Tracking |
|------|-----------|----------|
| Atheris Python 3.12 support delayed | Monitor releases monthly; consider alternatives (Pythia) | [Readiness doc](./fuzzing_coverage_guided_readiness.md) |
| Performance <10K exec/sec | Mock I/O, use in-memory filesystem, optimize harness | Week 2-3 checkpoints |
| False positives >20% | Start with permissive oracles, iterate based on findings | Week 4 metrics review |
| No unique bugs found | Extend fuzzing time, improve seed corpus, tune harnesses | Week 5 decision point |

---

## Success Stories (Update After Implementation)

<!-- Document unique bugs found by Atheris that Hypothesis missed -->

**Phase 2a Results** (TBD):
- Infrastructure setup time:
- First harness performance (exec/sec):

**Phase 2b Results** (TBD):
- Harnesses implemented:
- Unique bugs found:
- Performance achieved:

**Phase 2c Results** (TBD):
- Nightly runtime:
- Crashes auto-triaged:
- False positive rate:

**Phase 2d Results** (TBD):
- Final branch coverage:
- Memory issues found (ASan):
- Quarterly maintenance hours:
- **Unique value**: Bugs Atheris found that Hypothesis missed:

---

## Next Actions

1. **Monitor Atheris releases**: https://github.com/google/atheris/releases (check monthly)
2. **Track prerequisites**: Update [fuzzing_coverage_guided_readiness.md](./fuzzing_coverage_guided_readiness.md)
3. **Validate Phase 1**: Ensure Hypothesis finds ≥2 bugs (proves fuzzing ROI)
4. **Training**: Team lead reviews Atheris docs + tutorials
5. **Resource planning**: Reserve 40-80 hours once Atheris supports Python 3.12

**Estimated earliest start**: Q2 2025 (pending Atheris Python 3.12 support)

---

## Links to Detailed Information

| Topic | Where to Find It |
|-------|------------------|
| Complete Atheris strategy | [fuzzing_coverage_guided.md](./fuzzing_coverage_guided.md) |
| Readiness tracking | [fuzzing_coverage_guided_readiness.md](./fuzzing_coverage_guided_readiness.md) |
| Harness examples | [fuzzing_coverage_guided.md Harness Design](./fuzzing_coverage_guided.md) |
| Oracle specifications | [fuzzing_coverage_guided.md Oracle Table](./fuzzing_coverage_guided.md) |
| Success criteria | [fuzzing_coverage_guided.md Success Criteria](./fuzzing_coverage_guided.md) |
| Risk analysis | [fuzzing_coverage_guided.md Risk Analysis](./fuzzing_coverage_guided.md) |
| CI workflow examples | [fuzzing_coverage_guided.md Technical Approach](./fuzzing_coverage_guided.md) |
| Comparison with Hypothesis | [fuzzing_coverage_guided.md Comparison Table](./fuzzing_coverage_guided.md) |

---

## Notes

- **Python version**: All fuzzing on Python 3.12 (once Atheris supports it)
- **Parallel with Hypothesis**: Both approaches run (Hypothesis PR tests, Atheris nightly)
- **Unique value proposition**: Atheris must find ≥1 bug Hypothesis missed to justify investment
- **Maintenance commitment**: <6 hours/month after initial setup
- **Decision points**: Clear go/no-go criteria at end of each phase
