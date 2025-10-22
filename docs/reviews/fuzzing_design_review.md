# Fuzzing Plan – Peer Review & Risk Reduction

Reviewer: Internal self‑review and checklist for fuzzing strategy in `docs/fuzzing.md`.

## Summary
The plan proposes Atheris for coverage‑guided fuzzing on high‑value parsers and guardrails, with Hypothesis to lock in invariants. CI adds a nightly fuzz job (time‑boxed) and keeps property tests in normal runs. This is an appropriate balance for a Python codebase handling paths, URIs, and config schemas.

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

## Action Items
- [ ] Add `fuzz/` harnesses for `path_guard`, `zip_sanitize`
- [ ] Add Hypothesis property suites under `tests/fuzz_props/`
- [ ] Add `fuzz.yml` nightly workflow (3.11 runtime, 10–15m per harness)
- [ ] Pin `atheris` in `requirements-dev.lock` and confirm lock installs in CI
- [ ] Add corpus seeds and contribution guide for adding minimized crashes
- [ ] Document local run instructions and resource caps in `docs/fuzzing.md`

## Acceptance Criteria (Phase 1)
- Nightly fuzz workflow runs reliably for 7 days
- At least one meaningful crash found/fixed or properties expanded to cover edge invariants
- Zero regressions in property tests for two subsequent releases

