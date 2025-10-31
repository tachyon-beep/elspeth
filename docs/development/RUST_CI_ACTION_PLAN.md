# Rust CI/CD Implementation - Action Plan for Coding Agent

## 📋 Executive Summary

**Objective:** Implement comprehensive Rust CI/CD for the sidecar daemon, matching the sophistication of the existing Python CI/CD infrastructure.

**Status:** ✅ All configuration files created, ready for fixes + commit

**Files Created:**
- ✅ `sidecar/deny.toml` - Security policy enforcement
- ✅ `sidecar/Makefile` - Development convenience commands
- ✅ `.github/workflows/reusable-rust-ci.yml` - Reusable CI workflow
- ✅ `.github/workflows/rust-build.yml` - Main build workflow
- ✅ `.github/workflows/integration-tests.yml` - Python ↔ Rust tests
- ✅ `.github/dependabot.yml` - Updated with Rust support
- ✅ `sidecar/RUST_CI_SETUP_GUIDE.md` - Detailed implementation guide

---

## 🎯 Action Items for Coding Agent

### Phase 1: Fix Existing Issues (BLOCKING - Required Before CI Passes)

#### Task 1.1: Fix Rust Clippy Errors

**Location:** `sidecar/tests/`

**Command:**
```bash
cd sidecar
cargo clippy --fix --all-targets --allow-dirty --allow-staged
cargo test  # Verify tests still pass
git add -u
git commit -m "fix(rust): Auto-fix clippy linting errors"
cd ..
```

**Expected Changes:**
- `tests/grants_test.rs:52` - Replace `matches!(result, Err(_))` with `result.is_err()`
- `tests/handlers_test.rs` (8 locations) - Remove redundant `.try_into()` conversions

**Verification:**
```bash
cd sidecar && cargo clippy --all-targets --all-features -- -D warnings
```

Should output: `0 warnings emitted`

---

#### Task 1.2: Fix Python Type Safety Issues

**Location:** `src/elspeth/core/security/sidecar_client.py`

**Issues:**
1. Line 166: Tuple size mismatch (4 elements assigned to 3-element tuple)
2. Lines 234, 334, 364, 444: Returning `Any` from typed functions

**Fix Pattern:**
```python
# Before:
def _send_request(self, request: dict) -> dict:
    response = cbor2.loads(response_bytes)  # Returns Any
    return response  # ❌ Returning Any

# After:
def _send_request(self, request: dict) -> dict:
    response_data = cbor2.loads(response_bytes)

    # Runtime validation
    if not isinstance(response_data, dict):
        raise ValueError(f"Invalid response type: {type(response_data)}")

    return response_data  # ✅ Guaranteed dict
```

**Apply to:**
- `_send_request()` method
- `authorize_construct()` method
- `redeem_grant()` method
- `compute_seal()` method
- `verify_seal()` method

**Verification:**
```bash
python -m mypy src/elspeth/core/security/sidecar_client.py
python -m mypy src/elspeth/core/security/digest.py
```

Should output: `Success: no issues found`

---

#### Task 1.3: Fix Python Import Issues

**Location:** `src/elspeth/core/security/`

**Command:**
```bash
python -m ruff check --fix src/elspeth/core/security/
git add -u
git commit -m "fix(python): Remove unused imports"
```

**Expected Changes:**
- Remove unused `TYPE_CHECKING`, `Any`, `Hashable` from `digest.py`
- Remove unused `struct` from `sidecar_client.py`
- Remove unused `Optional` from `sidecar_client.py`
- Fix import block ordering

---

### Phase 2: Commit New CI/CD Files

#### Task 2.1: Commit All New Files

**Command:**
```bash
git add sidecar/deny.toml
git add sidecar/Makefile
git add sidecar/RUST_CI_SETUP_GUIDE.md
git add .github/workflows/reusable-rust-ci.yml
git add .github/workflows/rust-build.yml
git add .github/workflows/integration-tests.yml
git add .github/dependabot.yml
git add RUST_CI_ACTION_PLAN.md

git commit -m "ci(rust): Add comprehensive CI/CD infrastructure

Files added:
- sidecar/deny.toml - Security policy (licenses, CVEs, sources)
- sidecar/Makefile - Development convenience commands
- .github/workflows/reusable-rust-ci.yml - Reusable CI workflow
- .github/workflows/rust-build.yml - Main build + security
- .github/workflows/integration-tests.yml - Python ↔ Rust tests
- .github/dependabot.yml - Rust dependency management

CI/CD Features:
✅ Format checking (rustfmt)
✅ Linting with -D warnings (clippy)
✅ Security scanning (cargo-deny, cargo-audit)
✅ License enforcement (permissive only, matches CLAUDE.md)
✅ MSRV check (Rust 1.77)
✅ Binary size analysis
✅ Unsafe code audit (cargo-geiger)
✅ Integration tests (daemon + Python client)
✅ Automated dependency updates (Dependabot)

Matches Python CI/CD patterns:
- SHA-pinned GitHub Actions
- Locked dependencies (Cargo.lock)
- Coverage enforcement (optional cargo-tarpaulin)
- Security-first policies (zero CVE tolerance)

See: sidecar/RUST_CI_SETUP_GUIDE.md for details
"
```

---

#### Task 2.2: Push and Verify CI Passes

**Command:**
```bash
git push origin feature/sidecar-security-daemon
```

**Verification:**
1. Go to GitHub Actions tab
2. Verify these workflows pass:
   - ✅ Rust Build (Sidecar Daemon)
   - ✅ Integration Tests (Python ↔ Rust Sidecar)
   - ✅ Reusable Rust CI (called by rust-build.yml)

3. Check individual jobs:
   - rust-ci (format, lint, test, security)
   - msrv-check (Rust 1.77 compatibility)
   - unsafe-check (unsafe code audit)
   - binary-size (prevent bloat)
   - python-rust-integration (end-to-end tests)

**Expected Outcome:**
All workflows green ✅

---

### Phase 3: Local Testing (Before Pushing)

#### Task 3.1: Run Full CI Pipeline Locally

**Command:**
```bash
cd sidecar
make ci  # Or: make all

# This runs:
# - cargo check (type checking)
# - cargo fmt --check (formatting)
# - cargo clippy -D warnings (linting)
# - cargo test (all tests)
# - cargo deny check (security policies)
# - cargo audit (CVE scanning)
# - cargo build --release (production build)
```

**Expected Output:**
```
✅ All checks passed! Ready to commit.
```

---

#### Task 3.2: Test Integration Tests Locally

**Command:**
```bash
# From project root
ELSPETH_RUN_INTEGRATION_TESTS=1 python -m pytest tests/test_sidecar_integration.py -v
```

**Expected Output:**
```
test_authorize_construct_flow PASSED
test_redeem_grant_flow PASSED
... (11 tests should run, not be skipped)
```

---

### Phase 4: Install Development Tools (Local Machine)

**Command:**
```bash
cd sidecar
make install-tools

# This installs:
# - cargo-deny (license & security)
# - cargo-audit (CVE scanning)
# - cargo-watch (auto-rebuild)
# - cargo-geiger (unsafe code audit)
```

**Note:** These tools are used locally and in CI. Installing locally enables pre-commit checks.

---

## 🔍 Verification Checklist

Use this checklist to verify implementation:

### Pre-Push Verification

- [ ] Rust clippy errors fixed (`cargo clippy -- -D warnings` → 0 warnings)
- [ ] Python MyPy errors fixed (`mypy src/elspeth/core/security/` → Success)
- [ ] Python ruff errors fixed (`ruff check src/elspeth/core/security/` → All checks passed)
- [ ] All Rust tests pass (`cargo test` → all tests passed)
- [ ] Local CI passes (`make ci` → All checks passed)
- [ ] Integration tests pass (with `ELSPETH_RUN_INTEGRATION_TESTS=1`)

### Post-Push Verification

- [ ] GitHub Actions workflows appear in Actions tab
- [ ] Rust Build workflow passes (all jobs green)
- [ ] Integration Tests workflow passes
- [ ] No merge conflicts with `main` branch
- [ ] Dependabot creates test Rust PR within 1 week (Thursday)

### Branch Protection (Optional - Manual Setup)

- [ ] Add "Rust CI (Format, Lint, Test)" to required checks
- [ ] Add "Python ↔ Rust Integration Tests" to required checks
- [ ] Configure auto-merge for Dependabot patch updates (optional)

---

## 📚 Reference Documentation

### For Coding Agent

- **Implementation Guide:** `sidecar/RUST_CI_SETUP_GUIDE.md` (detailed walkthrough)
- **Makefile Commands:** `sidecar/Makefile` (development shortcuts)
- **Security Policy:** `sidecar/deny.toml` (license + CVE rules)

### For Developers

- **CI Workflows:** `.github/workflows/` (GitHub Actions configs)
- **Dependency Config:** `.github/dependabot.yml` (automated updates)
- **Project Guidelines:** `CLAUDE.md` (coding standards)

---

## 🚨 Common Issues & Solutions

### Issue: "cargo-deny not found"

**Solution:**
```bash
cargo install --locked cargo-deny
```

### Issue: "Integration tests skipped"

**Solution:**
```bash
# Ensure environment variable is set
export ELSPETH_RUN_INTEGRATION_TESTS=1
pytest tests/test_sidecar_integration.py -v
```

### Issue: "Binary size exceeds 20 MB"

**Solution:**
```bash
# Analyze bloat
cargo install cargo-bloat
cargo bloat --release

# Check for duplicate dependencies
cargo tree -d
```

### Issue: "Dependabot not creating Rust PRs"

**Solution:**
- Verify `.github/dependabot.yml` includes `cargo` ecosystem
- Check Dependabot logs: Settings > Security > Dependabot
- Ensure `sidecar/Cargo.lock` exists and is committed

---

## 🎯 Success Criteria

Implementation is complete when:

✅ **All workflows pass** on GitHub Actions
✅ **Zero clippy warnings** (`-D warnings` enforced)
✅ **Zero MyPy errors** (type safety enforced)
✅ **Security scans pass** (deny.toml + cargo-audit)
✅ **Integration tests pass** (Python ↔ Rust daemon)
✅ **Dependabot configured** (Rust PRs on Thursdays)
✅ **Local tools work** (`make ci` runs successfully)

---

## 📞 Next Steps After Implementation

1. **Monitor Dependabot:** Check for first Rust PR (next Thursday)
2. **Configure Branch Protection:** Add CI checks to required status
3. **Enable Coverage:** Uncomment `cargo-tarpaulin` section in workflow (optional)
4. **Add Benchmarks:** Create `sidecar/benches/` for performance tracking (optional)
5. **Document CI:** Update `CLAUDE.md` with Rust CI commands (optional)

---

**Implementation Time Estimate:** 30-45 minutes
**Difficulty:** Easy (mostly auto-fixes + copy-paste)
**Risk:** Low (all changes are additive, no breaking changes)

---

**Last Updated:** 2025-10-30
**Owner:** ELSPETH DevOps Team
**Related:** ADR-002 (Multi-Level Security), CLAUDE.md (Development Guidelines)
