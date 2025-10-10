# Advanced Statistics Migration Plan

See `notes/stats-analytics-inventory.md` for the detailed comparison of legacy
analytics versus the refactored plugin stack. Outstanding gaps now focus on:

- Visualization support (matplotlib) for distribution/heatmap views.
- Optional extras to evaluate: weighted kappa, ordinal regression, PyMC3-based Bayes.

## Packs & Scope
1. **Core Significance Pack (Phase 1)**
   - Cohen's d, mean difference, pooled standard deviation per criteria.
   - Two-sample t-test (Welch) with optional SciPy dependency for p-values.
   - Implemented as baseline comparison plugin (`score_significance`) reusing `scores` metrics produced by `score_extractor`.
   - Optional extra `stats-core` providing SciPy; degrade gracefully (p-values `None`) when SciPy unavailable.

2. **Agreement Pack (Phase 2)**
   - Krippendorff's alpha, Cohen's kappa, ICC.
   - Requires heavier stack (`pingouin`, `statsmodels`, `sklearn`) gated behind `stats-agreement` extra.
   - Delivered via aggregation plugins generating row-level reliability summaries.

3. **Bayesian Pack (Phase 3)**
   - Posterior probability variant > baseline, HDI calculation.
   - Optional dependencies (`pymc`, `arviz`); fallback to analytic approximations when not installed.
   - Exposed as baseline plugin returning posterior summary and credible interval.

4. **Planning Pack (Phase 4)**
   - Power analysis, sample size recommendations, variance forecasts.
   - Depends on `statsmodels`; packaged under `stats-planning` extra.
   - Aggregation plugin surfaces recommended sample size for target power.

5. **Distribution Shift Pack (Phase 5)**
   - KS test, Mann-Whitney, divergence metrics.
   - Minimal dependency (numpy/scipy); integrate with `stats-core` extra.
   - Baseline plugin reports shift metrics per criteria.

## Phase 1 Execution Steps (Core Pack)
1. Update `pyproject.toml` with `[project.optional-dependencies] stats-core = ["scipy>=1.10"]`.
2. Add baseline plugin `score_significance` in `src/elspeth/plugins/experiments/metrics.py`:
   - Collect baseline/variant scores per criterion.
   - Compute mean difference, pooled variance, Cohen's d, Welch t-statistic.
   - Attempt to import `scipy.stats`; if present, compute p-value; otherwise set `p_value = None` and record reason.
   - Honour `on_error` policy (default `abort`).
3. Extend plugin schema to include options (criteria filters, alternative hypothesis, `on_error`).
4. Write tests:
   - Deterministic baseline/variant payloads verifying computed stats and effect size.
   - Test behaviour when SciPy unavailable (monkeypatch import failure) -> p_value `None`.
   - Test `on_error="skip"` path by forcing internal exception.
5. Document usage:
   - Update README / sample config to reference `score_significance` baseline plugin and optional `[stats-core]` extra.
   - Note p-value availability depends on SciPy.

## Later Phases
- Phase 2+: follow similar pattern once core pack stabilises.
  - Agreement Pack: implemented `score_agreement` (Cronbach's alpha, Krippendorff's alpha, avg correlations).
  - Bayesian Pack: implemented `score_bayes` for posterior probabilities and credible intervals.
  - Planning Pack: implemented `score_power` for sample size/power estimates.
- Phase 5: Distribution/Drift detection via `score_distribution` baseline plugin (KS, Mann-Whitney, JS divergence).
