# Coverage-Guided Fuzzing Strategy (Phase 2 - High-Assurance Systems)

**Status**: 🔶 **BLOCKED** - Awaiting Atheris Python 3.12 support

**Related docs**:
- **Phase 1 (Active)**: [fuzzing.md](./fuzzing.md) - Hypothesis property-based testing (Python 3.12)
- **Roadmap**: [fuzzing_coverage_guided_plan.md](./fuzzing_coverage_guided_plan.md) - Implementation timeline
- **Readiness tracking**: [fuzzing_coverage_guided_readiness.md](./fuzzing_coverage_guided_readiness.md) - Prerequisites checklist
- **External review**: [fuzzing_design_review_external.md](./fuzzing_design_review_external.md)

---

## Executive Summary

This document defines the strategy for **coverage-guided fuzzing** using Atheris/libFuzzer for Elspeth's highest-risk security modules. This is Phase 2 of the fuzzing strategy, complementing the Hypothesis property-based testing implemented in Phase 1.

**Approach**: Atheris coverage-guided fuzzing for top 3 security-critical modules
**Timeline**: 5-6 weeks, 40-80 hours (after Python 3.12 support available)
**Prerequisite**: Phase 1 (Hypothesis) must be operational and demonstrating value (≥2 bugs found)

**Key Value Proposition**: Coverage-guided fuzzing discovers **unknown edge cases** that property testing misses by instrumenting code to guide input generation toward unexplored execution paths.

---

## Strategic Rationale

### Why Coverage-Guided Fuzzing for Mission-Critical Systems

**Threat Profile**: Elspeth handles classified data and PII in a mission-critical context with nation-state threat actors. This justifies defense-in-depth fuzzing:

| Risk Factor | Property-Based Only | + Coverage-Guided |
|-------------|---------------------|-------------------|
| Known attack patterns (OWASP, CVEs) | ✅ Excellent | ✅ Excellent |
| Unknown parser edge cases | ⚠️ Limited | ✅ Excellent |
| Deep nested logic (10+ branches) | ⚠️ Low probability | ✅ High probability |
| Integer arithmetic bugs | ⚠️ Limited | ✅ Excellent |
| Memory safety issues | ❌ Not detected | ✅ With sanitizers |
| State machine vulnerabilities | ⚠️ Requires stateful design | ✅ Corpus evolution |
| Unicode normalization bypasses | ⚠️ Limited | ✅ Excellent |
| Differential parser bugs | ⚠️ Requires explicit oracles | ✅ Automatic discovery |

### Complementary Approaches

**Hypothesis (Phase 1)**: Validates *known* security invariants you explicitly specify
**Atheris (Phase 2)**: Discovers *unknown* edge cases through coverage-guided exploration

**Example**:
- Hypothesis tests: `"../../../etc/passwd"` (oracle: must reject)
- Atheris discovers: `".." + "\x00" * 256 + "/etc/passwd"` (buffer overflow in validation code)

---

## Scope and Target Modules

### High-Priority Targets (Coverage-Guided Fuzzing Justified)

Based on threat analysis and classification level:

| Module | Risk Level | Atheris Value | Rationale |
|--------|-----------|---------------|-----------|
| **approved_endpoints.py** | CRITICAL | ⭐⭐⭐⭐⭐ | SSRF to classified networks; URL parsers notoriously complex; differential bugs common |
| **path_guard.py** | CRITICAL | ⭐⭐⭐⭐⭐ | File disclosure of classified data; Unicode normalization, symlink races, filesystem edge cases |
| **prompt_renderer.py** | HIGH | ⭐⭐⭐⭐ | Template injection → RCE; parser bypasses, recursion limits, encoding issues |
| **sanitizers.py** (CSV/Excel) | MEDIUM-HIGH | ⭐⭐⭐ | Formula injection → data exfiltration; encoding tricks, BOM manipulation |
| **config_parser.py** | MEDIUM | ⭐⭐ | Deserialization RCE; recursion bombs, parser edge cases |

**Phase 2 Scope**: Focus on top 3 modules (approved_endpoints, path_guard, prompt_renderer)

### Out of Scope (Hypothesis Sufficient)

- Low-complexity validators with simple logic
- Pure Python code with no C extensions
- Modules with <50 lines and low cyclomatic complexity
- Non-security-critical utility functions

---

## Technical Approach

### Atheris Integration Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CI/CD Pipeline                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  PR Tests (5 min)                                       │
│  └─→ Hypothesis property tests (Python 3.12)           │
│                                                          │
│  Nightly Tests (2 hours)                                │
│  ├─→ Hypothesis deep exploration (15 min, Python 3.12) │
│  └─→ Atheris coverage-guided (105 min, Python 3.12)    │
│      ├─→ URL validator harness (30 min)                │
│      ├─→ Path guard harness (30 min)                   │
│      ├─→ Template renderer harness (30 min)            │
│      └─→ Crash minimization (15 min)                   │
│                                                          │
│  Weekly Deep Fuzz (8 hours, on-demand)                 │
│  └─→ Extended Atheris runs with large corpus           │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Harness Design Pattern

**Standard Atheris Harness Structure**:

```python
# fuzz/atheris/fuzz_url_validator.py
"""
Coverage-guided fuzzing harness for approved_endpoints.py

Oracle: URL validation should either:
  1. Accept URLs meeting security invariants (HTTPS, approved hosts, no credentials)
  2. Reject with ValueError/URLError (no silent bypasses)

Target: Discover parser edge cases, encoding issues, differential bugs.
"""
import atheris
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from elspeth.core.validators.approved_endpoints import validate_approved_endpoint
from elspeth.core.exceptions import SecurityError

@atheris.instrument_func  # Instrument for coverage tracking
def TestOneInput(data):
    """
    Atheris entry point. Called with mutated byte sequences.

    Atheris will:
    - Track which code paths are reached
    - Mutate inputs to maximize coverage
    - Save interesting inputs to corpus
    - Detect crashes, hangs, memory issues
    """
    fdp = atheris.FuzzedDataProvider(data)

    # Generate URL components (Atheris learns which formats trigger branches)
    scheme = fdp.PickValueInList([
        b"http", b"https", b"ftp", b"file", b"data", b"javascript",
        b"HTTP", b"hTTp",  # Case variations
        b"http\x00s",      # Null byte injection
    ])

    username = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 100))
    password = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 100))

    # Host with various encodings
    host_type = fdp.ConsumeIntInRange(0, 5)
    if host_type == 0:
        # Domain name
        host = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 253))
    elif host_type == 1:
        # IPv4
        host = f"{fdp.ConsumeIntInRange(0, 255)}.{fdp.ConsumeIntInRange(0, 255)}." \
               f"{fdp.ConsumeIntInRange(0, 255)}.{fdp.ConsumeIntInRange(0, 255)}"
    elif host_type == 2:
        # IPv6
        host = "[" + fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 50)) + "]"
    elif host_type == 3:
        # IDN (punycode)
        host = "xn--" + fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 50))
    elif host_type == 4:
        # Unicode domain (homograph attack)
        host = fdp.ConsumeUnicode(fdp.ConsumeIntInRange(0, 100))
    else:
        # Empty/whitespace
        host = fdp.PickValueInList(["", " ", "\t", "\n", "\x00"])

    port = fdp.ConsumeIntInRange(0, 65535)
    path = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 500))
    query = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 200))
    fragment = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 100))

    # Construct URL (various formats to explore parser logic)
    url_format = fdp.ConsumeIntInRange(0, 3)

    try:
        if url_format == 0:
            # Standard format
            url = f"{scheme.decode(errors='ignore')}://"
            if username:
                url += username
                if password:
                    url += f":{password}"
                url += "@"
            url += host
            if port not in [80, 443, 0]:
                url += f":{port}"
            url += f"/{path}"
            if query:
                url += f"?{query}"
            if fragment:
                url += f"#{fragment}"
        elif url_format == 1:
            # Malformed (missing //)
            url = f"{scheme.decode(errors='ignore')}:{host}/{path}"
        elif url_format == 2:
            # With encoding
            url = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 500))
        else:
            # Raw bytes (encoding issues)
            url = data.decode(errors='ignore')

        # Test validation (Oracle enforcement)
        result = validate_approved_endpoint(url)

        # If validation passed, enforce security invariants
        # (Atheris will find inputs that violate these assertions)
        assert result.scheme in ["http", "https"], \
            f"Invalid scheme allowed: {result.scheme}"
        assert "@" not in result.netloc, \
            f"Credentials in validated URL: {result.netloc}"
        assert result.hostname, \
            "Empty hostname passed validation"

        # Check for parser differentials (validate vs. actual request)
        # This catches bugs where validation logic differs from urllib/requests
        from urllib.parse import urlparse
        stdlib_parsed = urlparse(url)
        assert result.hostname == stdlib_parsed.hostname or stdlib_parsed.hostname is None, \
            f"Parser differential: our={result.hostname}, stdlib={stdlib_parsed.hostname}"

    except (ValueError, SecurityError, UnicodeError) as e:
        # Expected exceptions for invalid URLs - this is correct behavior
        pass
    except AssertionError:
        # Oracle violation - Atheris found a bypass!
        raise
    except Exception as e:
        # Unexpected exception - potential bug
        # Atheris will save this input as a crash
        raise

def main():
    """Entry point for Atheris fuzzer."""
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()

if __name__ == "__main__":
    main()
```

### Key Atheris Features Used

1. **Coverage Instrumentation**: `@atheris.instrument_func` tracks code paths
2. **FuzzedDataProvider**: Generates structured fuzzing inputs (not just random bytes)
3. **Corpus Evolution**: Saves inputs that discover new code paths
4. **Automatic Minimization**: Reduces crashing inputs to minimal examples
5. **Integration with Sanitizers**: AddressSanitizer, UndefinedBehaviorSanitizer for memory issues

---

## Oracle Specifications for Coverage-Guided Fuzzing

### Oracles vs. Crash Detection

**Hypothesis oracles**: Explicit invariants you specify
**Atheris oracles**: Same invariants PLUS automatic crash/hang/memory issue detection

### Oracle Table (Extends Property-Based Oracles)

| Target | Property-Based Oracle (Phase 1) | Coverage-Guided Oracle (Phase 2) |
|--------|----------------------------------|----------------------------------|
| **URL Validation** | Scheme in {http, https}<br>No credentials<br>Host in allowlist | + Parser differential checks<br>+ Unicode normalization consistency<br>+ No buffer overflows in parsing<br>+ Request library parity |
| **Path Guard** | Result under base_dir<br>No symlink escape<br>Normalized | + Filesystem-specific edge cases<br>+ Unicode NFC/NFD consistency<br>+ No race conditions<br>+ Cross-platform path handling |
| **Template Renderer** | No eval/exec<br>Variables resolved<br>Depth < 10 | + No recursion stack overflow<br>+ Encoding consistency<br>+ No parser state confusion<br>+ Sandbox escape detection |

### Crash Severity for Coverage-Guided Findings

| Crash Type | Severity | Examples | Triage Priority |
|-----------|----------|----------|-----------------|
| **Assertion failure** (oracle violation) | S0-S1 | Path escape, credential bypass, scheme validation bypass | Immediate (4h) |
| **Unhandled exception** | S1-S2 | Unexpected errors, state confusion | 24 hours |
| **Timeout/hang** | S2 | Infinite loops, algorithmic complexity attacks | 3 days |
| **Memory issue** (ASan) | S0-S1 | Buffer overflow, use-after-free, memory leak | Immediate (4h) |
| **Parser differential** | S1 | Our validator accepts, stdlib rejects (or vice versa) | 24 hours |

---

## Implementation Phases

### Prerequisites (Before Starting)

See [fuzzing_coverage_guided_readiness.md](./fuzzing_coverage_guided_readiness.md) for tracking:

- ✅ Phase 1 (Hypothesis) operational and demonstrating value (≥2 bugs found)
- ✅ Atheris supports Python 3.12 (check: `pip install atheris && python -c "import atheris; print(atheris.__version__)"`)
- ✅ Team familiar with Hypothesis fuzzing concepts
- ✅ CI infrastructure capacity for 2-hour nightly runs
- ✅ Stakeholder approval for 40-80 hour investment

### Phase 2a: Infrastructure Setup (Week 1, 10-15 hours)

**Objectives**:
- Set up Atheris development environment
- Create harness template and utilities
- Configure CI for coverage-guided fuzzing
- Establish corpus storage and management

**Deliverables**:
- `fuzz/atheris/` directory structure
- Harness utilities (`fuzz/atheris/_harness_utils.py`)
- CI workflow (`.github/workflows/fuzz-atheris-nightly.yml`)
- Corpus storage (S3/Artifacts with 90-day retention)
- Documentation: "Writing Atheris Harnesses" guide

### Phase 2b: Harness Development (Weeks 2-3, 15-25 hours)

**Objectives**:
- Implement harnesses for top 3 security modules
- Seed corpus with known attack patterns
- Validate harnesses find injected bugs
- Tune performance (target: >10K exec/sec)

**Deliverables**:
- `fuzz/atheris/fuzz_url_validator.py`
- `fuzz/atheris/fuzz_path_guard.py`
- `fuzz/atheris/fuzz_template_renderer.py`
- Seed corpus (50+ inputs per target)
- Performance benchmarks

### Phase 2c: CI Integration & Automation (Week 4, 10-15 hours)

**Objectives**:
- Nightly 2-hour coverage-guided fuzzing runs
- Automatic crash minimization
- Integration with GitHub Issues for triage
- Corpus growth monitoring

**Deliverables**:
- Automated crash triage workflow
- Corpus management scripts (dedupe, minimize)
- Monitoring dashboard (coverage, exec/sec, crashes)
- Alert system for S0/S1 findings

### Phase 2d: Optimization & Hardening (Weeks 5-6, 10-20 hours)

**Objectives**:
- Maximize code coverage per module
- Reduce false positives
- Integrate with AddressSanitizer
- Long-term maintenance procedures

**Deliverables**:
- Coverage reports (branch/line per module)
- Sanitizer integration (ASan/MSan/UBSan)
- Runbook: "Atheris Crash Triage"
- Quarterly review process

---

## Success Criteria

### Phase 2a (Infrastructure)
- ✅ Atheris harness template runs successfully
- ✅ CI nightly workflow executes 30-minute fuzzing run
- ✅ Corpus persists between runs
- ✅ Crashes uploaded as artifacts

### Phase 2b (Harnesses)
- ✅ 3 harnesses operational for top security modules
- ✅ >10,000 executions/second per harness
- ✅ Bug injection tests: 100% detection of planted vulnerabilities
- ✅ Initial corpus: 50+ seeds per target

### Phase 2c (Production)
- ✅ Nightly 2-hour runs discovering new code paths
- ✅ Automatic crash minimization working
- ✅ S0/S1 findings create GitHub issues within 1 hour
- ✅ Corpus growth: >100 new interesting inputs/week

### Phase 2d (Long-term)
- ✅ Branch coverage: ≥90% on fuzzed modules (higher than Hypothesis)
- ✅ ≥1 unique S0-S2 bug found that Hypothesis missed
- ✅ False positive rate <15% (higher tolerance than property testing)
- ✅ Maintenance time <6 hours/month

### IRAP Compliance Evidence
- ✅ Coverage-guided fuzzing operational for highest-risk modules
- ✅ Corpus evolution demonstrates continuous testing
- ✅ Crash triage logs with severity classification
- ✅ Sanitizer integration (memory safety validation)
- ✅ Quarterly security posture reports

---

## Resource Requirements

### Team Skills

| Skill | Level | Phase | Hours |
|-------|-------|-------|-------|
| Python testing | Senior | All | 40-80 |
| Fuzzing concepts | Intermediate | 2a-2b | 20-30 |
| CI/CD automation | Intermediate | 2c | 10-15 |
| Security analysis | Senior | 2b-2d | 15-25 |
| C/Memory debugging | Intermediate (optional) | 2d | 5-10 |

### Infrastructure

**CI Compute**:
- Nightly: 2 hours × 4 vCPUs = 8 vCPU-hours/day (~$50-100/month)
- Weekly deep: 8 hours × 8 vCPUs = 64 vCPU-hours/week (on-demand)

**Storage**:
- Corpus: 500MB-2GB (growing)
- Crash artifacts: 100MB-500MB (90-day retention)
- Total: ~2.5GB with quarterly pruning

**Tools**:
- Atheris (free, open-source)
- AddressSanitizer (free, part of Clang/GCC)
- Optional: Fuzzbench for benchmarking

---

## Risk Analysis

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Atheris doesn't support Python 3.12 in timeframe | Medium | High | Monitor Atheris releases; consider alternatives (Pythia, lain) |
| False positive rate too high (>20%) | Medium | Medium | Start with permissive oracles; iterative refinement |
| Performance <5K exec/sec | Low | Medium | Optimize harnesses; mock slow I/O; use in-memory FS |
| CI timeout issues | Low | Low | Hard 2-hour limit; incremental corpus builds |
| Corpus grows unbounded | Medium | Low | Weekly deduplication; monthly pruning; size limits |

### Operational Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Team lacks fuzzing expertise | Medium | High | Training in Phase 2a; pair with security expert |
| Maintenance burden exceeds 6h/month | Low | Medium | Automate crash triage; clear runbooks |
| Findings overlap with Hypothesis | Medium | Low | Track unique bugs; justify ROI quarterly |
| Python 3.12 support delayed >6 months | High | Medium | Defer implementation; revisit in 2026 |

---

## Comparison: Property-Based vs Coverage-Guided

### When to Use Each Approach

| Scenario | Property-Based (Hypothesis) | Coverage-Guided (Atheris) |
|----------|----------------------------|---------------------------|
| **Known attack patterns** | ✅ Preferred (faster, clearer) | ⚠️ Supplement |
| **Unknown edge cases** | ⚠️ Limited | ✅ Preferred |
| **Deep nested logic** | ⚠️ Low probability | ✅ Excellent |
| **Parser fuzzing** | ⚠️ Requires good strategies | ✅ Automatic |
| **Rapid feedback (PR tests)** | ✅ <5 min | ❌ Too slow |
| **Deep security testing (nightly)** | ⚠️ Limited | ✅ Excellent |
| **Memory safety** | ❌ Not applicable | ✅ With sanitizers |
| **Clear oracles** | ✅ Preferred (explicit) | ⚠️ Same + crash detection |
| **Team learning curve** | ✅ Low (pytest-like) | ⚠️ Medium (fuzzing concepts) |

### Recommended Hybrid Strategy

**Use Both**: Hypothesis for known invariants + Atheris for unknown edge cases

**Workflow**:
1. **Every PR**: Hypothesis (5 min, fast oracle validation)
2. **Nightly**: Hypothesis explore (15 min) + Atheris (2 hours)
3. **Weekly**: Extended Atheris deep fuzzing (8 hours, on-demand)
4. **Findings**: Convert Atheris crashes → Hypothesis regression tests

---

## Next Steps

1. **Track readiness**: Monitor [fuzzing_coverage_guided_readiness.md](./fuzzing_coverage_guided_readiness.md)
2. **Atheris Python 3.12 support**: Check monthly: https://github.com/google/atheris/releases
3. **Phase 1 validation**: Ensure Hypothesis finds ≥2 bugs (proves fuzzing ROI)
4. **Resource allocation**: Reserve 40-80 hours in sprint planning once unblocked
5. **Training**: Team lead reviews Atheris documentation and tutorials

**Estimated earliest start date**: Q2 2025 (pending Atheris Python 3.12 support)

---

## References

- **Atheris Documentation**: https://github.com/google/atheris
- **libFuzzer Tutorial**: https://llvm.org/docs/LibFuzzer.html
- **Google OSS-Fuzz**: https://google.github.io/oss-fuzz/
- **Fuzzing Book**: https://www.fuzzingbook.org/
- **AddressSanitizer**: https://github.com/google/sanitizers

---

## Appendix A: Example Findings from Coverage-Guided Fuzzing

### Real-World CVEs Found by Coverage-Guided Fuzzing

**URL Parsers** (relevant to `approved_endpoints.py`):
- CVE-2021-22555: Parser differential allowing SSRF
- CVE-2019-11236: CRLF injection in urllib3
- CVE-2020-8492: Python urllib ReDOS

**Path Traversal** (relevant to `path_guard.py`):
- CVE-2019-16163: Oniguruma ReDOS via deeply nested patterns
- CVE-2021-21300: Git path traversal via Unicode normalization

**Template Engines** (relevant to `prompt_renderer.py`):
- CVE-2019-8341: Jinja2 sandbox escape
- CVE-2020-14343: PyYAML arbitrary code execution

These were discovered through fuzzing techniques similar to what Atheris provides.
