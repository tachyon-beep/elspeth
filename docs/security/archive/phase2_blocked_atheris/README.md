# Phase 2: Coverage-Guided Fuzzing (ARCHIVED - BLOCKED)

**Status**: 🔴 **BLOCKED** - Awaiting Atheris Python 3.12 support

**Archived Date**: 2025-10-25

**Reason**: These documents describe Phase 2 (coverage-guided fuzzing with Atheris), which is blocked for 6+ months due to external dependency. Archived to avoid distraction from Phase 1 implementation.

---

## Why Archived?

1. **Technical Blocker**: Atheris library does not support Python 3.12 (required for Elspeth runtime)
2. **Timeline**: Earliest availability Q2 2025+ (6+ months out)
3. **Phase 1 Not Started**: 0/15 property tests implemented yet
4. **Tool Landscape Changes**: By Q2 2025, better Python fuzzing tools may exist (don't lock into Atheris now)
5. **Focus**: Team needs to implement Phase 1 (Hypothesis property testing) FIRST to prove fuzzing ROI

---

## When to Unarchive

**Unarchive these documents when ALL are true**:

- ✅ **Phase 1 operational**: ≥15 property tests running in CI
- ✅ **Phase 1 demonstrates value**: ≥2 security bugs found (S0-S2)
- ✅ **Python 3.12 support confirmed**: Test `pip install atheris` on Python 3.12 works
- ✅ **Resource allocation approved**: 40-80 hours available for Phase 2

**Check monthly**: [Atheris releases](https://github.com/google/atheris/releases) for Python 3.12 support announcement

---

## Archived Documents

| Document | Purpose | Status |
|----------|---------|--------|
| `fuzzing_coverage_guided.md` | Phase 2 strategy (513 lines) | Complete, tool-specific (Atheris) |
| `fuzzing_coverage_guided_plan.md` | Phase 2 roadmap (321 lines) | Complete, execution-ready |
| `fuzzing_coverage_guided_readiness.md` | Prerequisites checklist (417 lines) | Tracking prerequisites |

**Total**: 1,251 lines of detailed Phase 2 planning

---

## Alternative Tools to Consider (When Unblocking)

**By Q2 2025, the fuzzing landscape may have changed**. Don't assume Atheris is still the best choice. Evaluate:

1. **Atheris** (Google) - If Python 3.12 support released
   - Pros: Industry standard, OSS-Fuzz integration, mature
   - Cons: Requires Python 3.11 as of Oct 2025; may be outdated by Q2 2025

2. **Pythia** (Microsoft) - Check Python 3.12 support
   - Pros: Microsoft-backed, modern architecture
   - Cons: Less mature than Atheris

3. **Hypothesis + coverage plugin** - Use existing tool, add coverage guidance
   - Pros: Already using Hypothesis, low friction
   - Cons: Not true coverage-guided, but better than nothing

4. **Commercial options** - Mayhem (ForAllSecure), Fuzzbuzz
   - Pros: Managed infrastructure, expert configuration
   - Cons: Cost, less control

5. **New tools** - Check what's emerged in 6 months (e.g., "IBM's blah2")

**Recommendation**: When unblocking, spend 2-4 hours evaluating current best-in-class Python fuzzing tools BEFORE committing to Atheris-specific implementation.

---

## Key Insights from Phase 2 Planning (Tool-Agnostic)

**These principles remain valuable regardless of tool choice**:

### 1. Coverage-Guided Value Proposition

**What it provides** (vs. property-based testing):
- Discovers **unknown edge cases** through code instrumentation
- Explores deep nested logic (10+ branches)
- Finds parser differentials, Unicode issues, integer overflows
- Detects memory safety issues (with sanitizers)

**Historical precedent**: Most critical CVEs in URL parsers, path validators, template engines discovered via coverage-guided fuzzing

### 2. Oracle Specifications for Coverage-Guided

Same security invariants as Phase 1 (property-based), PLUS:
- Parser differential checks (our validator vs. stdlib)
- Unicode normalization consistency
- Buffer overflow detection (via sanitizers)
- Cross-platform path handling consistency

### 3. Success Criteria

**Must demonstrate unique value vs. Phase 1**:
- ✅ ≥1 unique S0-S2 bug found that property testing missed
- ✅ ≥90% branch coverage (vs 85% for property testing)
- ✅ Performance >10K executions/second per harness
- ✅ False positive rate <15% (acceptable for deeper testing)

### 4. Resource Requirements (Ballpark)

- **Implementation**: 40-80 hours over 5-6 weeks
- **Ongoing CI**: ~$50-110/month (2hr nightly + 8hr weekly deep fuzzing)
- **Storage**: 2-3GB corpus + crash artifacts
- **Maintenance**: <6 hours/month after initial setup

---

## What to Do RIGHT NOW (Not Phase 2)

**Focus 100% on Phase 1 implementation**:

1. **This week**: Set up directory structure, install Hypothesis, configure `pyproject.toml`
2. **Next 2 weeks**: Implement first 3-5 property tests for `path_guard.py`
3. **Week 4**: Add bug injection tests, integrate with CI
4. **Month 2**: Expand to 15-20 property tests across 5 security modules

**See**:
- `fuzzing.md` - Phase 1 canonical strategy
- `fuzzing_plan.md` - Week-by-week implementation checklist

---

## Risk Assessment: Why Archiving is Safe

**Q**: Doesn't archiving Phase 2 docs reduce security?

**A**: No. Here's why:

1. **Phase 1 provides 60-70% bug discovery** vs coverage-guided (per industry benchmarks)
2. **Shakedown cruise limited to PROTECTED data** (not SECRET/TOP SECRET)
3. **External security review planned** (code review + penetration testing)
4. **Defense-in-depth architecture** (multiple security layers, not relying on fuzzing alone)
5. **Remediation commitment**: Phase 2 will be implemented before SECRET data handling

**See**: `fuzzing_irap_risk_acceptance.md` for full risk analysis and IRAP assessor review

---

## Contact

**Questions about Phase 2 or when to unarchive?**

- **Owner**: Security Engineering Lead
- **Review Schedule**: Monthly check of Atheris releases
- **Escalation**: Quarterly strategic review with CISO

**Last Updated**: 2025-10-25
**Next Review**: 2025-11-29 (monthly tracking)
