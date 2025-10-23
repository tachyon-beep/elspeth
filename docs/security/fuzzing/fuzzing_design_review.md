# Fuzzing Plan – Peer Review & Risk Reduction

Reviewer: Internal self‑review of the canonical strategy in `docs/security/fuzzing/fuzzing.md`.

Related docs:
- Strategy & targets (canonical): [fuzzing.md](./fuzzing.md)
- Concise implementation roadmap: [fuzzing_plan.md](./fuzzing_plan.md)

## Summary
We will use Atheris for coverage‑guided fuzzing on high‑value parsers and guardrails, paired with Hypothesis to lock in invariants. CI adds a time‑boxed nightly job, while property tests run in normal suites. This balances fidelity and cost for a Python codebase with path, URI, and config surfaces.

## Strengths
- Targets the riskiest surfaces (path normalization, sanitization, validators)
- Clear invariants; easy to convert crashes into tests
- Resource‑bounded and isolated; avoids network access
- Minimizes toil: one harness per target; reproducible corpus

## Gaps / Risks & Mitigations
1) Tooling drift (Atheris vs. Python 3.12)
   - Risk: Upstream changes break fuzz harness on newer Python.
   - Mitigation: Run fuzz jobs under 3.11; pin atheris in `requirements-dev.lock`; keep runtime code on 3.12.

2) Resource runaway (disk, time)
   - Risk: Excessive file creation/large inputs slow jobs or fill disk.
   - Mitigation: Cap number & size of test files per iteration; time‑box jobs (10–15m/harness); use tmpfs where available; upload only minimized crashes.

3) Flaky triage due to non‑determinism
   - Risk: Non‑deterministic failures hinder root‑cause analysis.
   - Mitigation: Record seed, Python version, platform; minimize input before opening an issue; turn crash into a Hypothesis property with explicit invariants.

4) Secret exposure in artifacts
   - Risk: Crash payloads may accidentally contain PII/paths.
   - Mitigation: Sanitize crash outputs; restrict artifact retention to 7 days; never include env dumps; only upload minimized raw bytes when necessary.

5) Over‑fitting docstrings/format to make lint pass
   - Risk: Property tests become style checks rather than functional.
   - Mitigation: Keep properties focused on behavior (safety and contracts), not formatting.

6) Test cross‑talk via filesystem state
   - Risk: Harnesses interfere with each other’s tmp dirs.
   - Mitigation: Use `TemporaryDirectory()` in each harness; randomize dir names; ensure cleanup on every iteration.

7) False positives on network operations
   - Risk: URI fuzz may accidentally trigger real outbound requests in future code.
   - Mitigation: Validators only; no network clients; if clients added, guard with an explicit “no network” adapter and mocks.

8) Coverage blind spots
   - Risk: Only a few targets fuzzed; bugs persist elsewhere.
   - Mitigation: Expand targets iteratively based on crash data and code churn; consider instrumenting coverage in fuzz runs to measure marginal value.

## Action Items (non‑duplicating)
- [ ] Add `fuzz/` harnesses for `path_guard`, `zip_sanitize`
- [ ] Add Hypothesis property suites under `tests/fuzz_props/`
- [ ] Add `fuzz.yml` nightly workflow (3.11 runtime, 10–15m per harness)
- [ ] Pin `atheris` in `requirements-dev.lock` and confirm lock installs in CI
- [ ] Add corpus seeds and contribution guide for adding minimized crashes
- [ ] Ensure resource caps and local run instructions are present in [fuzzing.md](./fuzzing.md)

## Acceptance Criteria (Phase 1)
Use the authoritative “Success Criteria (Phase 1)” in the canonical strategy: [fuzzing.md](./fuzzing.md).
