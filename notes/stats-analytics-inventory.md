# Legacy Analytics Inventory (Task 2.2.1)

This document catalogues the statistical capabilities from the legacy
`StatsAnalyzer` (`old/experiment_stats.py`) and compares them to what the modern
plugin stack currently provides. It informs Tasks 2.2.2/2.2.3 by identifying gaps
and required dependencies.

## Summary Table

| Feature Category | Legacy Implementation | Current Support | Dependencies | Notes / Action |
| --- | --- | --- | --- | --- |
| **Score extraction & summaries** | Extract scores from LLM output, mean/median/std, pass-rate, histograms | ✅ `score_extractor`, `score_stats` provide per-criteria metrics | numpy, pandas | Complete |
| **Recommendations** | Text guidance combining effect size, power, penalties | ✅ `score_recommendation` aggregator | numpy | Complete |
| **Effect sizes** | Cohen’s d (+ bootstrap CI), Cliff’s delta | ✅ Cohen’s d via `score_stats`; ❌ Cliff’s delta | numpy, scipy | Need Cliff’s delta baseline plugin |
| **Significance tests (parametric)** | t-test, assumption checks (Shapiro, Levene) | ❌ | scipy.stats | Candidate: diagnostics aggregator producing normality/variance results |
| **Significance tests (non-parametric)** | Mann–Whitney, Wilcoxon | ✅ Mann–Whitney/Wilcoxon in `score_distribution` | scipy.stats | Already covered; ensure docs mention usage |
| **Multiple comparisons** | Bonferroni, FDR corrections | ❌ | statsmodels | Option to add aggregator utility or integrate into baseline plugins |
| **Bayesian analysis** | PyMC3 model + bootstrap fallback | ✅ `score_bayes` (beta posterior) provides probability of improvement; ❌ PyMC3 mode/CI | scipy (beta), optional pymc3 | Determine if PyMC3 support needed; fallback already present |
| **Distribution shift** | KL divergence, KS test, histograms | ✅ `score_distribution` (KL, KS, summary) | numpy, scipy | Histogram plotting not yet ported |
| **Practical significance** | NNT, meaningful-change counts | ✅ `score_practical` baseline plugin | numpy | Delivered in Phase 2.2.2 |
| **Power analysis** | TTestIndPower, required sample size | ✅ `score_power` aggregator | statsmodels (optional) | Present; ensure docs highlight prerequisites |
| **Reliability/Agreement** | Krippendorff alpha, kappa, correlations | ✅ `score_agreement` (Cronbach’s alpha, avg corr, pingouin fallback) | numpy, pingouin, sklearn | Weighted kappa not ported; consider extras |
| **Ordinal regression** | statsmodels OrderedModel | ❌ | statsmodels | Consider advanced plugin or defer |
| **Composite ranking** | Score variants by effect, power, risk | ✅ `score_variant_ranking` aggregator | numpy | Delivered; richer reporting still future work |
| **Visualisations** | Matplotlib dashboards (heatmaps, distributions) | ❌ | matplotlib | Candidate for future report sink (Task 2.2.3) |
| **Reporting / JSON summaries** | Write markdown/JSON outputs, recommendations | ✅ Analytics report sink (JSON/Markdown) | stdlib | Delivered in Task 2.2.3 |

## Dependencies Overview

- **Core**: numpy, pandas, scipy.stats (already required).  
- **Optional**: pingouin (agreement), statsmodels (power, ordinal regression), sklearn (kappa fallback), pymc3 (advanced Bayes), matplotlib (visualisations).
- Current `pyproject.toml` extras already cover many of these (stats-core, stats-agreement, stats-bayesian, stats-planning, stats-distribution). Ordinal regression and weighted kappa may require extending extras or documenting setup.

## Identified Gaps (for Task 2.2.2 & 2.2.3)

1. **Cliff’s Delta Plugin** – ✅ implemented (`score_cliffs_delta`).
2. **Assumption Diagnostics** – ✅ implemented (`score_assumptions`).
3. **Multiple-Comparison Utilities** – ✅ integrated via `score_significance` adjustments.
4. **Practical Significance Metrics** – ✅ implemented (`score_practical`).
5. **Composite Ranking** – ✅ implemented (`score_variant_ranking`); richer reporting deferred.
6. **Reporting Sink** – ✅ analytics report sink (JSON/Markdown).
7. **Visualization Support** – Optional sink producing plots when matplotlib is available (pending).
8. **Ordinal Regression** – Decide whether to provide statsmodels-backed plugin or defer due to complexity.

## Proposed Next Steps

- Update `notes/stats-refactor-plan.md` with decisions above (scope vs. defer).
- Break down implementation tickets per gap during Task 2.2.2 planning.
- Ensure README/docs reference optional extras required for advanced analytics.

This inventory completes Task 2.2.1 by providing a baseline for the analytics parity plan. Future tasks will implement the missing pieces and introduce stakeholder-friendly outputs.
