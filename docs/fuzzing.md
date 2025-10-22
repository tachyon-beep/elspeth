# Elspeth Fuzzing Strategy

This document describes a practical, high‑quality fuzzing approach for Elspeth that finds real bugs in risky surfaces (paths, URIs, schema/config parsing) without adding flaky or heavyweight infrastructure. It pairs coverage‑guided fuzzing (Atheris) with property‑based tests (Hypothesis) and integrates a time‑boxed nightly GitHub Action.

## Objectives
- Uncover crashes, assertion failures, and invariant violations in:
  - Path/FS guards and name sanitization
  - HTTP/Blob endpoint validators
  - Config/schema/middleware validation paths
  - CSV source base‑path resolution
  - Security controls and prompt template rendering
- Turn regressions into stable properties in our pytest suite
- Keep fuzzing resource‑bounded, isolated, deterministic, and maintainable

### Success Criteria (Phase 1)
- Achieve 80%+ line coverage on targeted modules
- Find and fix at least 1 real bug per target area
- 30-day period with zero unfixed crashes after stabilization
- All crashes converted to regression tests (Hypothesis or concrete)
- Fuzzing workflow runs reliably in CI without flakiness

## Scope & Targets (Phase 1)
1) Path & FS guards
   - `src/elspeth/core/utils/path_guard.py`
     - `resolve_under_base`, `ensure_no_symlinks_in_ancestors`, `safe_atomic_write`
2) Name/URI sanitization
   - `src/elspeth/plugins/nodes/sinks/zip_bundle.py` (`_safe_name` policy)
3) Security validators (CRITICAL)
   - `src/elspeth/core/security/approved_endpoints.py` (endpoint allowlist validation)
   - `src/elspeth/core/prompts/` (Jinja2 template rendering, injection prevention)
4) Config/schema edges
   - `src/elspeth/core/registries/*` (`validate()`, `create()`, middleware creation)
5) CSV sources
   - `src/elspeth/plugins/nodes/sources/_csv_base.py` base path containment

## Engines & Rationale

| Engine    | Pros                                    | Cons                          | Decision |
|-----------|-----------------------------------------|-------------------------------|----------|
| Atheris   | Python-native, easy setup, libFuzzer-backed | Limited Python 3.12 support   | ✅ Use   |
| AFL++     | Industry standard, mature               | Requires C bindings           | ❌ Skip  |
| Hypothesis| Fast CI, excellent DX, pytest integration | Not coverage-guided           | ✅ Use   |

- **Coverage‑guided fuzzing: Atheris (Google)**
  - Finds novel inputs quickly; excellent for parsers, path normalization, validators
  - Uses libFuzzer instrumentation under the hood
  - Run fuzz jobs with Python 3.11 to avoid toolchain friction (3.12 support limited)
- **Property‑based testing: Hypothesis (pytest)**
  - Fast CI invariants and regression locks for fuzz‑found issues
  - Better developer experience and test readability
  - Integrates seamlessly with existing pytest suite

## Harness Design (Atheris)
- Location: `fuzz/`
- One harness per target, e.g.:
  - `fuzz/fuzz_path_guard.py`
  - `fuzz/fuzz_zip_sanitize.py`
  - `fuzz/fuzz_endpoint_validator.py`
  - `fuzz/fuzz_prompt_renderer.py`
  - `fuzz/fuzz_config_parser.py`

### Oracles / Invariants
- **Path Guard (`resolve_under_base`)**:
  - On success: result is absolute, under base, normalized (no `..` segments after resolution)
  - On rejection: raises `ValueError` (not crash/hang)
  - Race-safe: concurrent calls don't interfere (TOCTOU protection)
- **Symlink Guard (`ensure_no_symlinks_in_ancestors`)**:
  - Raises `ValueError` on symlinked ancestor/destination per contract (not crash)
  - Never follows symlinks silently
- **Zip Name Sanitizer (`_safe_name`)**:
  - Output contains only `[A-Za-z0-9._-]` and is non-empty
  - No path separators (`/`, `\`) or NUL bytes
  - Unicode normalized (NFC) to prevent homograph attacks
  - Idempotent: `_safe_name(_safe_name(x)) == _safe_name(x)`
  - Path traversal impossible after sanitization
- **Endpoint Validator**:
  - HTTP endpoints must be localhost/loopback (127.0.0.1, ::1, localhost)
  - HTTPS allowed with valid host
  - Invalid URIs rejected with clear error (not crash)
  - No bypass via Unicode tricks, IP encoding variations, or port manipulation
- **Prompt Renderer**:
  - No code execution via template injection
  - Invalid templates raise clear errors (not crash)
  - Output never contains unescaped user input in dangerous contexts

### Hygiene
- Use `tempfile.TemporaryDirectory()` with fixed quotas:
  - Max 100 files per iteration
  - Max 10 directories per iteration
  - Max 10 symlinks per iteration
  - Max 100MB total disk usage per harness run
- No network/file writes outside tmp; no environment variable access
- Timeouts: 100ms per input (configurable), 15 minutes total per harness
- CPU limits: Use `ulimit -t` or cgroup constraints in CI

## Property Tests (Hypothesis)
- Location: `tests/fuzz_props/`
- Mirror the same invariants for CI speed and stability
- Convert any fuzz‑found crash into a Hypothesis test (or a concrete regression test)
- Mark tests with `@pytest.mark.fuzz` for selective execution

### Example Structure
```python
# tests/fuzz_props/test_path_guard_props.py
from hypothesis import given, strategies as st
from elspeth.core.utils.path_guard import resolve_under_base
import pytest

@pytest.mark.fuzz
@given(st.text(), st.text())
def test_resolve_under_base_never_escapes(candidate, base):
    """Property: resolved paths must stay under base or raise ValueError."""
    try:
        result = resolve_under_base(candidate, base)
        assert result.is_absolute()
        assert result.is_relative_to(base)
    except ValueError:
        pass  # Rejection is acceptable

@pytest.mark.fuzz
@given(st.text(alphabet=st.characters(blacklist_categories=('Cs',))))
def test_safe_name_idempotent(input_name):
    """Property: _safe_name is idempotent."""
    from elspeth.plugins.nodes.sinks.zip_bundle import _safe_name
    try:
        safe1 = _safe_name(input_name)
        safe2 = _safe_name(safe1)
        assert safe1 == safe2
    except ValueError:
        pass  # Empty input rejection is acceptable
```

## Corpus Strategy

### Seed Corpora
Store at `fuzz/corpus/<target>/` with interesting edge cases by category:

- **Paths:**
  - Basic: `"."`, `".."`, `"/"`, `""`, `"a/../b"`, `"./././a"`
  - Traversals: `"../../../../etc/passwd"`, `"a/../../b"`
  - Long: 4096-character paths, 255-character components
  - Unicode: NFD vs NFC normalization, RTL override, zero-width joiners, homographs
  - Special: `"\x00"`, newlines, spaces, tabs

- **Zip Names:**
  - Traversals: `"../../.."`, `"../etc/passwd"`
  - Control chars: `"\x00"`, `"\n"`, `"\r"`, ASCII 1-31
  - Empty/dots: `""`, `"."`, `".."`, `"..."`, `".hidden"`
  - Unicode: Homograph attacks (`"раssword"` vs `"password"`), combining characters

- **Endpoints:**
  - Localhost: `http://localhost`, `http://127.0.0.1`, `http://[::1]`, `http://0.0.0.0`
  - Valid HTTPS: `https://api.openai.com`, `https://example.azure.net`
  - Invalid: `http://example.com`, `ftp://localhost`, `javascript:alert(1)`
  - Edge cases: `http://localhost:99999`, `http://[::ffff:127.0.0.1]`, Unicode domains

- **Config/YAML:**
  - YAML bombs: `a: &a [*a,*a,*a,*a,*a]`
  - Deeply nested: 1000-level nested dicts
  - Invalid types: `{"llm": 12345}` (expected dict)
  - Unicode keys: `{"中文": "value"}`, RTL keys
  - Special values: `null`, `~`, `true`, `"True"`, `1e308`

### Corpus Management
- **Version control:** Store seeds in git (limit: 100KB total per target)
- **Deduplication:** Use `atheris --minimize_crash` to reduce redundancy
- **Evolution:** Track coverage deltas; prune low-value seeds quarterly
- **Post-crash:** Add minimized crash inputs to seed corpus after fix
- **Format:** One file per seed, named by hash: `fuzz/corpus/path_guard/sha256_abc123.txt`

## Automation (GitHub Actions)

### Triggers
- **Nightly:** 02:00 UTC (low-traffic window)
- **Manual:** Workflow dispatch for on-demand fuzzing
- **PR changes:** Trigger on modifications to:
  - `src/elspeth/core/{utils,security,registries,prompts}/`
  - `src/elspeth/plugins/nodes/sources/_csv_base.py`
  - `src/elspeth/plugins/nodes/sinks/zip_bundle.py`

### Workflow (`fuzz.yml`)
- **Environment:**
  - Use Python 3.11 in dedicated container (avoid 3.12 toolchain issues)
  - Install deps: `pip install -e .[fuzz]` (see Dependencies section)
  - Run as unprivileged user with limited permissions

- **Execution:**
  - Run each harness for 10-15 minutes (parallel matrix strategy)
  - Per-harness timeouts: 100ms per input, 15min total
  - Corpus seeding: Use `fuzz/corpus/<target>/` as input

- **Artifacts:**
  - Upload crash repros with minimized inputs (`.crash` files)
  - Upload evolved corpus (coverage-improving inputs)
  - Store coverage report as JSON: `fuzz/coverage.json`

- **Notifications:**
  - **On new crash:** Create GitHub Issue with:
    - Crash repro steps
    - Stack trace
    - Minimized input
    - Severity classification (P0/P1/P2)
    - Link to workflow run
  - **On crash:** Comment on triggering PR (if applicable)
  - **On crash:** Notify `#security` Slack channel (if configured)

- **Metrics:**
  - Track coverage % in commit: `fuzz/coverage.json`
  - Track unique crash count in workflow summary
  - Report coverage delta on PRs

### CI Integration
- **Regular CI:** Run Hypothesis tests in normal pipeline (`pytest -m "not slow"`)
- **Fuzz CI:** Atheris harnesses run only in dedicated fuzz workflow (not per-commit)
- **Test marking:** Use `@pytest.mark.fuzz` for all fuzz-related Hypothesis tests

## Local Usage

### Atheris (Coverage-Guided Fuzzing)
```bash
# Setup
python3.11 -m venv .fuzz-venv
source .fuzz-venv/bin/activate
pip install -e .[fuzz]  # Install with fuzzing dependencies

# Run specific harness (infinite mode)
python fuzz/fuzz_path_guard.py --atheris_runs=0

# Run with time limit (5 minutes)
timeout 300 python fuzz/fuzz_path_guard.py

# Continue from previous corpus
python fuzz/fuzz_path_guard.py -corpus_dir=fuzz/corpus/path_guard/

# Run all harnesses (parallel)
for harness in fuzz/fuzz_*.py; do
  timeout 300 python "$harness" &
done
wait
```

### Hypothesis (Property-Based Testing)
```bash
# Run all property tests
pytest tests/fuzz_props/ -v

# Run specific target with verbose output
pytest tests/fuzz_props/test_path_guard_props.py -vv --hypothesis-show-statistics

# Run fuzz-marked tests only
pytest -m fuzz

# Run with increased example count (more thorough)
pytest tests/fuzz_props/ --hypothesis-seed=42 -v
```

## Triage & Promotion

### Crash Response Workflow
1) **Reproduce** with saved crashing input:
   ```bash
   python fuzz/fuzz_path_guard.py crash-abc123.txt
   ```

2) **Classify severity:**
   - **P0 (Critical):** RCE, path traversal escape, arbitrary code execution, injection
   - **P1 (High):** DoS on untrusted input, crash exposing sensitive data
   - **P2 (Medium):** Assertion failure, resource leak, non-exploitable crash
   - **P3 (Low):** Edge case handling, performance degradation

3) **Minimize** crash input:
   ```bash
   # Atheris can minimize automatically
   python fuzz/fuzz_path_guard.py -minimize_crash=crash-abc123.txt
   ```

4) **Fix** root cause in source code

5) **Add regression test:**
   - For invariant violations → Hypothesis property test in `tests/fuzz_props/`
   - For specific crashes → Concrete test in `tests/` with actual input
   - Include minimized input as test fixture

6) **Document** in `CHANGELOG.md` under "Security" section (if applicable)

7) **Promote** minimized input to seed corpus:
   ```bash
   cp crash-abc123-minimized.txt fuzz/corpus/path_guard/
   ```

8) **Close** GitHub Issue created by fuzzing workflow

## Risk Reduction & Safety

### Resource Bounds
- **Time limits:**
  - CI: 10-15 minutes per harness (total: ~90 minutes for 6 harnesses)
  - Local: Use `timeout` command or `-atheris_runs` flag
- **Filesystem quotas:**
  - Max 100 files per iteration
  - Max 10 directories per iteration
  - Max 100MB disk usage per harness run
  - Temp dirs cleaned after each run
- **CPU limits:**
  - Use `ulimit -t 900` (15 minutes CPU time)
  - Cgroup memory limit: 4GB per harness
- **Network:**
  - Disable all network access (no sockets, no HTTP)
  - Operate only inside temporary directory tree

### Determinism & Reproducibility
- **Python version:** Pin to 3.11 for Atheris (avoid 3.12 toolchain issues)
- **Dependencies:** Freeze via `requirements-fuzz.lock` (generated from `[fuzz]` extra)
- **Seeds:** Store in git with content-addressable filenames (SHA256 hash)
- **Crash logs:** Archive with:
  - Exact Python version
  - Atheris version
  - Input that triggered crash
  - Stack trace
  - Timestamp

### Secrets & Isolation
- **No environment access:** Don't load API keys, tokens, or credentials
- **No repo secrets:** Fuzz in isolated temp dirs; never touch `.env` files
- **PII quarantine:** Ensure crash artifacts don't leak sensitive data:
  - Review crash inputs before committing to corpus
  - Sanitize stack traces (remove absolute paths, usernames)
- **Sandboxing:**
  - Run under unprivileged user in CI (not root)
  - No Docker-in-Docker (security risk)
  - Minimal filesystem permissions (read-only except temp dir)

### Quality Gates
- **Regression prevention:** Every fixed crash gets a test (property or concrete)
- **Coverage tracking:** Require coverage delta > 0 for corpus additions
- **Review process:** Security team reviews P0/P1 crashes before merge

### Telemetry & Metrics
- **Track in `fuzz/metrics.json`:**
  - Unique crashes found (by hash)
  - Unique crashes fixed
  - Coverage % per target
  - Execution speed (execs/sec)
- **Report in workflow summary:**
  - New crashes this run
  - Total unfixed crashes
  - Coverage delta since last run

### Performance Baselines
- Reference existing performance tests: `tests/test_performance_baseline.py`
- Add timeout assertions to fuzz harnesses (e.g., < 100ms per input)
- Target execution speed: 1000+ execs/sec for hot paths like `resolve_under_base`
- Flag exponential complexity (hangs detected via per-input timeout)

## Non‑Goals (Phase 1)
- Fuzzing external services or SDKs over the network
- Full OSS‑Fuzz integration (consider ClusterFuzzLite in Phase 2)
- Differential fuzzing (comparing Elspeth behavior to other frameworks)
- Symbolic execution tools (angr, KLEE - out of scope for Python app)
- Kernel/syscall fuzzing (not applicable)
- Fuzzing third-party dependencies (pandas, openai, azure-sdk)

## Rollout (Phase 1)

### Week 1-2: Foundation
- [ ] Add harnesses:
  - `fuzz/fuzz_path_guard.py` (path resolution, symlink checks)
  - `fuzz/fuzz_zip_sanitize.py` (name sanitization)
- [ ] Add Hypothesis tests:
  - `tests/fuzz_props/test_path_guard_props.py`
  - `tests/fuzz_props/test_zip_sanitize_props.py`
- [ ] Set up `fuzz.yml` GitHub Action (nightly schedule)
- [ ] Create seed corpora (50+ inputs per target)
- [ ] **Milestone:** 1 complete fuzz run in CI (no crashes expected yet)

### Week 3-4: Expansion
- [ ] Add harnesses:
  - `fuzz/fuzz_endpoint_validator.py` (approved_endpoints.py)
  - `fuzz/fuzz_prompt_renderer.py` (Jinja2 template safety)
  - `fuzz/fuzz_config_parser.py` (registry validation)
- [ ] Add corresponding Hypothesis tests
- [ ] Enhance seed corpora to 100+ inputs per target
- [ ] **Milestone:** Find and fix first real bug (expected 1-3 bugs)

### Week 5-6: Stabilization
- [ ] Triage all crashes; classify by severity (P0/P1/P2)
- [ ] Convert crashes to property tests (no direct regression allowed)
- [ ] Achieve 85%+ line coverage on fuzzed modules
- [ ] Document findings in `SECURITY.md` (if security-relevant)
- [ ] **Milestone:** 30-day period with zero unfixed P0/P1 crashes

### Week 7+: Continuous Improvement
- [ ] Monitor nightly runs; respond to new crashes within 48 hours
- [ ] Quarterly corpus review: prune low-value seeds, add edge cases
- [ ] Track metrics in `fuzz/metrics.json` (commit to repo)
- [ ] Consider Phase 2 targets (sink plugins, middleware chain, LLM response parsing)

---

## Dependencies

### Installation
Add `fuzz` extra to `pyproject.toml`:
```toml
[project.optional-dependencies]
fuzz = [
    "atheris>=2.3.0",
    "hypothesis>=6.90.0",
]
```

### Lockfile Management
```bash
# Generate fuzzing lockfile (separate from dev deps)
python -m pip install pip-tools
pip-compile --extra=fuzz --output-file=requirements-fuzz.lock pyproject.toml

# Install for local fuzzing
pip install -r requirements-fuzz.lock
pip install -e . --no-deps
```

### Version Constraints
- **Python:** 3.11 (required for Atheris; 3.12 has limited support)
- **Atheris:** >= 2.3.0 (latest stable with Python 3.11)
- **Hypothesis:** >= 6.90.0 (for modern strategy API)

---

## Test Suite Integration

### Test Organization
- **Atheris harnesses:** `fuzz/fuzz_*.py` (not part of pytest suite)
- **Hypothesis tests:** `tests/fuzz_props/test_*_props.py` (part of pytest suite)
- **Concrete regressions:** `tests/test_*.py` (for specific crash inputs)

### Running Tests
```bash
# Run only fuzz-related property tests
pytest -m fuzz

# Run all tests except fuzz and slow
pytest -m "not slow and not fuzz"

# Run everything (normal CI)
pytest -m "not slow"

# Atheris harnesses (manual/nightly only)
python fuzz/fuzz_path_guard.py --atheris_runs=10000
```

### Test Markers
```python
import pytest

# Mark property tests for selective execution
@pytest.mark.fuzz
def test_path_guard_property():
    ...

# Mark slow fuzzing tests
@pytest.mark.slow
@pytest.mark.fuzz
def test_exhaustive_config_parsing():
    ...
```

---

## Security Disclosure

### Vulnerability Response
If fuzzing discovers a security vulnerability:

1. **Do NOT create public issue** - Use private communication
2. **Create GitHub Security Advisory** (private draft)
3. **Classify severity** using CVSS 3.1:
   - Critical (9.0-10.0): RCE, auth bypass, data exfiltration
   - High (7.0-8.9): Privilege escalation, path traversal
   - Medium (4.0-6.9): DoS, information disclosure
   - Low (0.1-3.9): Edge cases, minor issues
4. **Develop patch** in private fork/branch
5. **Coordinate disclosure:**
   - 90-day embargo (standard responsible disclosure)
   - Notify security@<domain> if applicable
   - Request CVE via GitHub (if CVSS >= 7.0)
6. **Public disclosure:**
   - Publish security advisory
   - Release patched version
   - Credit finder in `SECURITY.md` and advisory
   - Notify users via security mailing list
7. **Post-mortem:** Document in `docs/security/incidents/YYYY-MM-incident.md`

### Reporting Channel
- **Internal:** Security team via private Slack/email
- **External researchers:** `SECURITY.md` contact instructions
- **GitHub:** Security Advisories (for CVE assignment)

See `docs/SECURITY.md` for full vulnerability disclosure policy.

---

# Appendix: Example Invariants & Test Cases

## Path Guard

### `resolve_under_base(candidate, base)`
**Invariants:**
- ✅ On success: returns absolute path under `base`
- ✅ Result never contains `..` segments after resolution
- ❌ On escape attempt: raises `ValueError` (not crash/hang)
- ✅ Race-safe: concurrent calls don't interfere (TOCTOU protection)

**Test Cases:**
```python
# Success cases
assert resolve_under_base("foo/bar.txt", "/tmp") == Path("/tmp/foo/bar.txt")
assert resolve_under_base("./a/./b", "/tmp") == Path("/tmp/a/b")

# Rejection cases (must raise ValueError)
with pytest.raises(ValueError):
    resolve_under_base("../etc/passwd", "/tmp")  # Traversal escape
with pytest.raises(ValueError):
    resolve_under_base("/etc/passwd", "/tmp")  # Absolute path escape
with pytest.raises(ValueError):
    resolve_under_base("a/b/../../../../etc", "/tmp")  # Deep traversal
```

### `ensure_no_symlinks_in_ancestors(path)`
**Invariants:**
- ❌ Raises `ValueError` if any ancestor is a symlink
- ✅ Never follows symlinks silently
- ✅ Handles broken symlinks correctly (raises)

**Test Cases:**
```python
# Create symlink in path
link = tmp_path / "link"
link.symlink_to(tmp_path / "target")
file_under_link = link / "file.txt"

# Must raise because 'link' is a symlink ancestor
with pytest.raises(ValueError, match="symlink"):
    ensure_no_symlinks_in_ancestors(file_under_link)
```

## Zip Name Sanitizer

### `_safe_name(input)`
**Invariants:**
- ✅ Output matches `^[A-Za-z0-9._-]+$`
- ✅ Idempotent: `_safe_name(_safe_name(x)) == _safe_name(x)`
- ✅ Unicode normalized (NFC) to prevent homograph attacks
- ❌ Empty input raises `ValueError`
- ✅ Path traversal impossible after sanitization

**Test Cases:**
```python
# Success cases
assert _safe_name("report.csv") == "report.csv"
assert _safe_name("data_2024.json") == "data_2024.json"

# Sanitization
assert _safe_name("../../etc/passwd") == "etc_passwd"
assert _safe_name("file\x00name") == "file_name"  # NUL removed
assert _safe_name("über.txt") == "uber.txt"  # Unicode normalized

# Rejection
with pytest.raises(ValueError):
    _safe_name("")  # Empty not allowed
```

## Endpoint Validator

### `validate_endpoint(endpoint, service_type, security_level)`
**Invariants:**
- ✅ HTTP allowed only for localhost/127.0.0.1/::1
- ✅ HTTPS allowed for any valid host
- ❌ Invalid URIs raise `ValueError` (not crash)
- ✅ No bypass via Unicode tricks, IP encoding, port manipulation

**Test Cases:**
```python
# Allowed
validate_endpoint("http://localhost:8080", "azure_openai", "internal")
validate_endpoint("http://127.0.0.1", "azure_openai", "internal")
validate_endpoint("https://api.openai.com", "azure_openai", "public")

# Rejected
with pytest.raises(ValueError):
    validate_endpoint("http://example.com", "azure_openai", "internal")
with pytest.raises(ValueError):
    validate_endpoint("ftp://localhost", "azure_openai", "internal")
```

## Prompt Renderer

### `render_template(template, context)`
**Invariants:**
- ❌ No code execution via `{{ }}` injection
- ❌ Invalid templates raise `TemplateSyntaxError` (not crash)
- ✅ Output never contains unescaped HTML/JS in user input
- ✅ Strict undefined variables (raise on missing context keys)

**Test Cases:**
```python
# Safe rendering
assert render_template("Hello {{ name }}", {"name": "Alice"}) == "Hello Alice"

# Injection prevention (must not execute)
result = render_template("{{ user_input }}", {"user_input": "{{ __import__('os').system('ls') }}"})
assert "__import__" in result  # Rendered as string, not executed

# Invalid template
with pytest.raises(TemplateSyntaxError):
    render_template("{{ unclosed", {})
```

