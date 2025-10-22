# Elspeth Fuzzing Strategy

This document describes a practical, high‑quality fuzzing approach for Elspeth that finds real bugs in risky surfaces (paths, URIs, schema/config parsing) without adding flaky or heavyweight infrastructure. It pairs coverage‑guided fuzzing (Atheris) with property‑based tests (Hypothesis) and integrates a time‑boxed nightly GitHub Action.

## Objectives
- Uncover crashes, assertion failures, and invariant violations in:
  - Path/FS guards and name sanitization
  - HTTP/Blob endpoint validators
  - Config/schema/middleware validation paths
  - CSV source base‑path resolution
- Turn regressions into stable properties in our pytest suite
- Keep fuzzing resource‑bounded, isolated, deterministic, and maintainable

## Scope & Targets (Phase 1)
1) Path & FS guards
   - `src/elspeth/core/utils/path_guard.py`
     - `resolve_under_base`, `ensure_no_symlinks_in_ancestors`, `safe_atomic_write`
2) Name/URI sanitization
   - `src/elspeth/plugins/nodes/sinks/zip_bundle.py` (`_safe_name` policy)
   - HTTP/Blob validators (reject non‑localhost HTTP, validate Azure Blob endpoints)
3) Config/schema edges
   - `src/elspeth/core/registries/*` (`validate()`, `create()`, middleware creation)
4) CSV sources
   - `src/elspeth/plugins/nodes/sources/_csv_base.py` base path containment

## Engines & Rationale
- Coverage‑guided fuzzing: Atheris (Google)
  - Finds novel inputs quickly; great for parsers and path normalization
  - If toolchain friction with 3.12, run fuzz jobs with Python 3.11 (fuzz‑only)
- Property‑based testing: Hypothesis (pytest)
  - Fast CI invariants and regression locks for fuzz‑found issues

## Harness Design (Atheris)
- Location: `fuzz/`
- One harness per target, e.g.:
  - `fuzz/fuzz_path_guard.py`
  - `fuzz/fuzz_zip_sanitize.py`
  - `fuzz/fuzz_http_endpoint_validator.py`
- Oracles / invariants:
  - `resolve_under_base`: result is under base, non‑empty, and never escapes via traversal or symlinks
  - `ensure_*`: raises `ValueError` on symlinked ancestor/destination per contract
  - `_safe_name`: contains no path separators or NUL; only `[A-Za-z0-9._-]`, non‑empty
  - HTTP validator: HTTP allowed only for localhost/127./::1; HTTPS ok with valid host
- Hygiene:
  - Use `tempfile.TemporaryDirectory()` with fixed quotas on file/dir/symlink creation per iteration
  - No network/file writes outside tmp; no environment access
  - Timeouts and iteration caps enforced by the runner

## Property Tests (Hypothesis)
- Location: `tests/fuzz_props/`
- Mirror the same invariants for CI speed and stability
- Convert any fuzz‑found crash into a Hypothesis test (or a concrete regression test)

## Corpus Strategy
- Seed corpora at `fuzz/corpus/<target>/` with interesting cases:
  - Paths: `"."`, `".."`, `"/"`, `"a/../b"`, deep traversals, long names, unicode
  - Zip names: control chars, `"../../.."`, empty, `"."`, `".."`
  - Endpoints: `http://localhost`, `http://127.0.0.1`, `http://[::1]`, `http://example.com`, `https://valid.tld`
- Persist minimized crashes as seeds after triage

## Automation (GitHub Actions)
- Add `fuzz.yml` (nightly + manual) that:
  - Uses Python 3.11 for Atheris harnesses (to reduce toolchain friction)
  - Runs each harness for 10–15 minutes
  - Uploads crash repros and minimized corpus on failures
- Keep Hypothesis tests in normal CI (`pytest -m "not slow"`)

## Local Usage
- Atheris (example):
  - `python -m venv .fuzz-venv && source .fuzz-venv/bin/activate`
  - `pip install -e .[dev] atheris` (or a dedicated `fuzz` extra)
  - `python fuzz/fuzz_path_guard.py --atheris_runs=0` (infinite) or time‑box via GNU `timeout`
- Hypothesis: `pytest -q tests/fuzz_props/`

## Triage & Promotion
1) Reproduce with saved crashing input
2) Minimize (Atheris can help) and fix the root cause
3) Add a Hypothesis/property test or concrete regression test
4) Add minimized input to `fuzz/corpus/<target>/`

## Risk Reduction & Safety
- Resource bounds:
  - Time‑box fuzz runs (CI and local) and limit per‑iteration filesystem ops
  - Disable network; operate only inside a temporary directory tree
- Determinism & reproducibility:
  - Pin Python minor version for fuzz (e.g., 3.11) and freeze deps via `requirements-dev.lock`
  - Log seeds and archive crash reproducers with exact runner versions
- Secrets & isolation:
  - Don’t load env vars; avoid reading repo secrets or external files
  - Ensure fuzz outputs (corpora/crashes) don’t include PII; quarantine if needed
- Sandboxing:
  - Run under unprivileged user in CI; no Docker‑in‑Docker; limited permissions
- Quality gates:
  - Every fixed crash gets a property test to prevent regressions
- Telemetry:
  - Track number of unique crashes found and fixed, and coverage deltas (optional)

## Non‑Goals
- Fuzzing external services or SDKs over the network
- Full OSS‑Fuzz integration (we can add ClusterFuzzLite later if desired)

## Rollout (Phase 1)
- Week 1–2: Add two harnesses (path_guard, zip sanitize) + two Hypothesis suites; add nightly fuzz workflow
- Week 3+: Add HTTP validator harness and registry schema edges based on ROI
- Ongoing: Triage, convert to properties, grow corpus

---

# Appendix: Example Invariants
- Path Guard
  - `resolve_under_base(t, b)` returns `p` where `p.is_absolute()` and `p` is a descendant of `b`
  - `ensure_no_symlinks_in_ancestors(p)` raises on any symlinked ancestor
  - `safe_atomic_write(p, cb)` writes to `p` atomically; no partial files left on exceptions
- Zip Name Sanitizer (`_safe_name`)
  - Output contains only `[A-Za-z0-9._-]` and is non‑empty; path traversal impossible; no NUL
- HTTP Validator
  - HTTP endpoints must be localhost/loopback; HTTPS allowed; invalid URIs rejected

