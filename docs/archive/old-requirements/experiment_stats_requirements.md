# old/experiment_stats.py Requirements

## Optional dependency flags (`HAS_SKLEARN`, `HAS_PINGOUIN`, old/experiment_stats.py:17-32)
- Functional requirements:
  - Attempt to import optional analysis libraries (`sklearn`, `pingouin`) at module import time.
  - Set boolean flags indicating availability for downstream conditional logic.
- Non-functional requirements:
  - Fail gracefully when dependencies are missing (no import-time crash).
  - Keep detection cost minimal and idempotent.

## Module logger (old/experiment_stats.py:14)
- Functional requirements:
  - Instantiate a module-level logger (`logging.getLogger(__name__)`) for consistent analytics diagnostics.
- Non-functional requirements:
  - Respect global logging configuration without reinitializing handlers.
  - Support multi-threaded access in long-running analysis jobs.

## `NumpyJSONEncoder` (old/experiment_stats.py:34-48)
- Functional requirements:
  - Subclass `json.JSONEncoder` to convert NumPy scalars, arrays, and booleans into native Python types during serialization.
  - Delegate unknown types to the parent encoder.
- Non-functional requirements:
  - Avoid altering default behavior for non-NumPy types.
  - Ensure compatibility with standard `json.dump`/`json.dumps`.

## `StatisticalResult` dataclass (old/experiment_stats.py:50-58)
- Functional requirements:
  - Provide a structured container for individual test outputs (`test_name`, `statistic`, `p_value`, `significant`, optional `effect_size`, optional `interpretation`).
- Non-functional requirements:
  - Serve as lightweight record type interoperable with dataclass utilities (e.g., `asdict`).

## `StatsAnalyzer` class (old/experiment_stats.py:60-707)
- Functional requirements (class-level):
  - Orchestrate comprehensive statistical analysis across experiment results, including baseline detection, significance testing, effect size computation, recommendation generation, report exports, and visualization.
  - Manage caching, optional dependency fallbacks, and data validation.
- Non-functional requirements (class-level):
  - Operate on in-memory data structures without mutating source data.
  - Handle missing or malformed data gracefully, emitting logs instead of crashing.
  - Scale to large datasets via batching/caching while keeping memory usage bounded (`MAX_CACHE_SIZE`).

### Class constants (`CRITERIA_NAMES`, `SIGNIFICANCE_LEVEL`, `MIN_SAMPLES`, `MIN_PAIRED_SAMPLES`, `MAX_CACHE_SIZE`, old/experiment_stats.py:65-75)
- Functional requirements:
  - Provide canonical mappings and thresholds governing statistical tests and validation.
  - Enable consistent interpretation across methods (e.g., minimum sample checks).
- Non-functional requirements:
  - Keep constants easy to adjust for future tuning without touching method logic.

### `__init__(self, all_results: Dict[str, Dict])` (old/experiment_stats.py:77-105)
- Functional requirements:
  - Store experiment results dictionary and determine baseline via `_identify_baseline`.
  - Establish `baseline_data` defaulting to first experiment when explicit baseline absent.
  - Initialize caching structures (`_cache`, `_cache_order`).
  - Emit warning when baseline is not found but fallback is used.
- Non-functional requirements:
  - Avoid deep copies of result data to conserve memory.
  - Ensure initialization is O(n) with respect to number of experiments.

### `_add_to_cache(self, key: str, value: Any)` (old/experiment_stats.py:107-118)
- Functional requirements:
  - Insert new values into cache, enforcing `MAX_CACHE_SIZE` by evicting oldest entries.
- Non-functional requirements:
  - Maintain cache order list consistently with dictionary contents.
  - Avoid duplicating entries when key already present.

### `_identify_baseline(self)` (old/experiment_stats.py:120-133)
- Functional requirements:
  - Locate the experiment marked as baseline via config attribute or name heuristic (“baseline” substring).
  - Default to lexicographically first experiment when no explicit baseline exists.
- Non-functional requirements:
  - Handle absence of experiments by returning `None`.
  - Avoid raising errors when configs lack expected attributes.

### `_generate_recommendation(self, results: List[Dict])` (old/experiment_stats.py:135-154)
- Functional requirements:
  - Analyze ranked variant results and craft human-readable recommendations based on significance, effect size, and statistical power.
  - Provide fallback messaging when data insufficient.
- Non-functional requirements:
  - Keep logic deterministic for identical inputs.
  - Compose concise yet informative recommendation strings.

### `_interpret_bayesian(self, prob_improvement: float)` (old/experiment_stats.py:156-173)
- Functional requirements:
  - Map probability metrics into qualitative descriptors (e.g., “strong evidence variant is better”).
- Non-functional requirements:
  - Ensure thresholds cover full [0,1] range without gaps.

### `_simple_bayesian(self, baseline_scores, variant_scores)` (old/experiment_stats.py:175-198)
- Functional requirements:
  - Perform bootstrap-based estimation of variant improvement probability when Bayesian library unavailable.
  - Return dict summarizing method, probability, mean difference, and interpretation.
- Non-functional requirements:
  - Use reproducible process for deterministic seeds when required (currently relies on NumPy RNG; document randomness).
  - Ensure computation completes in reasonable time even with default 10,000 bootstraps (consider future tuning).

### `bayesian_comparison(self, baseline_scores, variant_scores)` (old/experiment_stats.py:200-233)
- Functional requirements:
  - Attempt full Bayesian analysis via PyMC3, capturing probability of variant improvement and confidence intervals.
  - Fall back to `_simple_bayesian` when PyMC3 unavailable.
- Non-functional requirements:
  - Manage computational cost by using sensible sampling defaults (2k samples, 1k tuning).
  - Handle import errors gracefully, returning fallback results without raising.

### `calculate_cliffs_delta(self, group1, group2)` (old/experiment_stats.py:235-262)
- Functional requirements:
  - Compute Cliff’s delta effect size for ordinal data using pairwise dominance counts.
  - Return tuple of delta value and qualitative interpretation.
- Non-functional requirements:
  - Avoid division by zero by short-circuiting empty input lists.
  - Maintain consistent interpretation thresholds.

### `calculate_krippendorff_alpha(self, baseline_scores, variant_scores)` (old/experiment_stats.py:264-282)
- Functional requirements:
  - Compute Krippendorff’s alpha for ordinal agreement, falling back to weighted Cohen’s kappa when dependency missing.
- Non-functional requirements:
  - Handle exceptions gracefully by returning `np.nan` or alternative metrics.

### `analyze_practical_significance(self, variant_name)` (old/experiment_stats.py:284-325)
- Functional requirements:
  - Evaluate practical (real-world) significance via distribution shift, meaningful changes, and number needed to treat.
  - Return dictionary summarizing change metrics and boolean flags for practical significance.
- Non-functional requirements:
  - Guard against division by zero (e.g., zero baseline successes).
  - Provide interpretable metrics even with limited data.

### `apply_bonferroni_correction(self, p_values)` (old/experiment_stats.py:327-333)
- Functional requirements:
  - Multiply p-values by number of tests and clamp at 1.0.
- Non-functional requirements:
  - Preserve input ordering.

### `apply_fdr_correction(self, p_values)` (old/experiment_stats.py:335-339)
- Functional requirements:
  - Delegate to `statsmodels.stats.multitest.fdrcorrection` to obtain adjusted p-values and significance flags.
- Non-functional requirements:
  - Ensure dependency presence; surface errors when statsmodels unavailable (caller responsibility).

### `calculate_cohens_d_ci(self, group1, group2, confidence=0.95)` (old/experiment_stats.py:341-365)
- Functional requirements:
  - Compute Cohen’s d and bootstrap-based confidence intervals.
  - Return tuple (estimate, lower, upper).
- Non-functional requirements:
  - Handle small sample sizes by allowing bootstraps; ensure results remain finite.

### `ordinal_logistic_regression(self, baseline_scores, variant_scores)` (old/experiment_stats.py:367-385)
- Functional requirements:
  - Fit ordered logistic regression using `statsmodels` when available.
  - Return coefficient statistics or error message when dependency missing.
- Non-functional requirements:
  - Provide stable output structure for downstream reporting.

### `calculate_statistical_power(self, effect_size, n1, n2)` (old/experiment_stats.py:387-408)
- Functional requirements:
  - Compute statistical power via `statsmodels` or fallback approximation using normal distribution.
  - Return power estimate as float.
- Non-functional requirements:
  - Handle edge cases such as zero sample sizes gracefully.

### `required_sample_size(self, effect_size, power=0.8)` (old/experiment_stats.py:410-435)
- Functional requirements:
  - Estimate sample size required to achieve desired power, leveraging `statsmodels` or analytical approximation.
  - Cap effect-size epsilon to avoid division by zero.
- Non-functional requirements:
  - Return integer ceiling of required sample size; fall back to high number when effect size negligible.

### `test_assumptions(self, scores1, scores2)` (old/experiment_stats.py:437-463)
- Functional requirements:
  - Perform Shapiro-Wilk normality tests and Levene’s variance homogeneity test when sample sizes permit.
  - Return dictionary summarizing statistics and boolean assessments.
- Non-functional requirements:
  - Skip tests when sample counts insufficient without raising errors.

### `determine_best_variant(self)` (old/experiment_stats.py:465-516)
- Functional requirements:
  - Evaluate all non-baseline variants, computing metrics such as mean improvement, effect size, p-values, correlations, statistical power, and composite scores.
  - Sort variants by composite score, apply FDR correction, and determine overall recommendation.
  - Return dictionary with best variant, rankings, and textual recommendation.
- Non-functional requirements:
  - Handle variants lacking data by skipping gracefully.
  - Maintain deterministic ordering given identical inputs.

### `_calculate_variant_score(self, analysis, consistency, power)` (old/experiment_stats.py:518-548)
- Functional requirements:
  - Compute composite score based on variant properties, rewarding statistical significance, consistency, effect size, and penalizing low power.
- Non-functional requirements:
  - Avoid altering inputs; maintain pure function semantics.

### `extract_scores(self, results, criteria_idx=None)` (old/experiment_stats.py:552-585)
- Functional requirements:
  - Traverse result structures to collect numeric scores from both case studies, optionally filtered by criteria index.
  - Utilize `_convert_scores` to normalize score types.
- Non-functional requirements:
  - Skip malformed entries gracefully and continue aggregation.

### `_convert_scores(self, raw_scores)` (old/experiment_stats.py:587-611)
- Functional requirements:
  - Convert string or numeric representations to integer scores, filtering out invalid or zero placeholders.
- Non-functional requirements:
  - Log warnings for unparsable strings but continue processing.

### `validate_experiments(self)` (old/experiment_stats.py:613-654)
- Functional requirements:
  - Check each experiment for sufficient sample count, score volume, variance, and error rate (presence of “00” values).
  - Return mapping of experiment names to lists of detected issues.
- Non-functional requirements:
  - Evaluate without raising exceptions; reserved for preflight diagnostics.

### `calculate_distribution_shift_batch(self, variant_name, batch_size=1000)` (old/experiment_stats.py:656-689)
- Functional requirements:
  - Compute distribution metrics for large datasets by batching baseline and variant data extraction.
  - Utilize caching to avoid recomputation.
  - Return error dictionary when baseline or variant data unavailable.
- Non-functional requirements:
  - Keep memory usage bounded by processing batches.
  - Respect cache size limits.

### `calculate_distribution_shift(self, variant_name)` (old/experiment_stats.py:691-707)
- Functional requirements:
  - Route to batch method for large datasets; otherwise compute metrics directly using `_calculate_distribution_metrics`.
- Non-functional requirements:
  - Provide informative error when baseline data absent.

### `_safe_wilcoxon_test(self, baseline_paired, variant_paired)` (old/experiment_stats.py:709-724)
- Functional requirements:
  - Conduct Wilcoxon signed-rank test when sufficient paired samples exist; return None otherwise.
  - Handle zero-difference cases and catch runtime errors with logging.
- Non-functional requirements:
  - Avoid raising exceptions due to insufficient data or SciPy limitations.

### `_calculate_distribution_metrics(self, baseline_scores, variant_scores, variant_name)` (old/experiment_stats.py:726-784)
- Functional requirements:
  - Compute mean/median/std deltas, skew/kurtosis changes, effect size (Cohen’s d), KL divergence, significance tests (KS, Mann-Whitney, Wilcoxon), score distribution summaries, and sample counts.
  - Detect score 1/5 prevalence changes and track presence of “score 1” issue.
  - Log warning when statistical tests fail.
- Non-functional requirements:
  - Return structured dictionary with consistent keys.
  - Avoid numeric overflow by capping KL divergence.

### `_calculate_cohens_d(self, group1, group2)` (old/experiment_stats.py:786-816)
- Functional requirements:
  - Compute Cohen’s d using pooled standard deviation with safeguards for small sample sizes and zero variance.
- Non-functional requirements:
  - Return 0.0 when computation invalid rather than raising errors.

### `_interpret_cohens_d(self, d)` (old/experiment_stats.py:818-830)
- Functional requirements:
  - Translate effect size into qualitative descriptors (negligible/small/medium/large).
- Non-functional requirements:
  - Handle negative inputs by evaluating absolute value.

### `_calculate_kl_divergence(self, p_dist, q_dist)` (old/experiment_stats.py:832-848)
- Functional requirements:
  - Compute KL divergence across discrete score distributions with smoothing to avoid zero probabilities.
  - Cap maximum divergence to avoid infinities.
- Non-functional requirements:
  - Ensure consistent ordering of scores (1-5) for comparability.

### `_safe_correlation(self, x, y, method='pearson')` (old/experiment_stats.py:850-874)
- Functional requirements:
  - Compute specified correlation (Pearson, Spearman, Kendall) when data sufficient and variance non-zero.
  - Return `(np.nan, np.nan)` when computation invalid or fails.
- Non-functional requirements:
  - Catch and log exceptions without interrupting analysis flows.

### `calculate_consistency(self, variant_name)` (old/experiment_stats.py:876-919)
- Functional requirements:
  - Derive paired scores with `_get_paired_scores`, compute match rates, correlations, Cohen’s kappa, ICC, and summary statistics.
  - Return error dictionary when paired data absent.
- Non-functional requirements:
  - Leverage optional dependencies only when available.
  - Ensure metrics reflect same ordering across variants for comparison.

### `_calculate_icc(self, scores1, scores2)` (old/experiment_stats.py:921-937)
- Functional requirements:
  - Compute ICC(2) via Pingouin when available; otherwise return `None`.
- Non-functional requirements:
  - Handle exceptions with warning logs and fallback to `None`.

### `_get_paired_scores(self, variant_name)` (old/experiment_stats.py:939-981)
- Functional requirements:
  - Align baseline and variant results by ID, extract matching scores for each case study, and return list of `(baseline_score, variant_score)` tuples.
  - Log mismatched score counts.
- Non-functional requirements:
  - Ensure deterministic ordering (sorted IDs) for reproducibility.

### `model_transformation(self, variant_name)` (old/experiment_stats.py:983-1032)
- Functional requirements:
  - Require minimum paired samples; otherwise return error.
  - Fit linear and quadratic regressions to model transformation of scores.
  - Compute confusion matrix when `sklearn` available and residual statistics.
  - Interpret transformation via `_interpret_transformation`.
- Non-functional requirements:
  - Handle regression failures gracefully with logging and fallback results.

### `_calculate_r2(self, x, y, coeffs)` (old/experiment_stats.py:1034-1041)
- Functional requirements:
  - Compute R² for polynomial fit; return 0 when total sum of squares near zero.
- Non-functional requirements:
  - Accept NumPy arrays and avoid mutating inputs.

### `_interpret_transformation(self, slope, intercept)` (old/experiment_stats.py:1043-1058)
- Functional requirements:
  - Provide qualitative interpretation (compresses/expands scores, systematic shifts) based on model parameters.
- Non-functional requirements:
  - Combine multiple interpretations with clear conjunctions when applicable.

### `identify_outliers(self, variant_name, n_outliers=10)` (old/experiment_stats.py:1060-1093)
- Functional requirements:
  - Compare baseline and variant means per ID to find largest deviations, returning top `n_outliers` entries with diagnostic details.
- Non-functional requirements:
  - Handle missing data gracefully; return empty list when variant absent.

### `_extract_all_scores_from_result(self, result)` (old/experiment_stats.py:1095-1104)
- Functional requirements:
  - Consolidate all scores from case study fields into a single list.
- Non-functional requirements:
  - Ensure compatibility with `_convert_scores` outputs.

### `_analyze_criteria_effects(self, variant_name)` (old/experiment_stats.py:1106-1144)
- Functional requirements:
  - For each criterion mapping, compute baseline vs variant means, deltas, effect sizes, and p-values when data sufficient; otherwise record insufficiency.
- Non-functional requirements:
  - Log test failures; keep output consistent across criteria.

### `analyze_scoring_consistency(self, variant_name)` (old/experiment_stats.py:1146-1168)
- Functional requirements:
  - Compute within-ID variance for baseline and variant to measure consistency.
  - Return comparison metrics and boolean flag indicating variant consistency.
- Non-functional requirements:
  - Handle IDs lacking scores by treating variance as zero via NumPy semantics.

### `analyze_category_effects(self, variant_name)` (old/experiment_stats.py:1170-1210)
- Functional requirements:
  - Group results by category, compute mean differences and effect sizes per category, and rank most/least affected categories.
  - Return dictionary containing raw impacts and ranked subsets.
- Non-functional requirements:
  - Support categories set derived from baseline data; handle missing categories gracefully.

### `analyze_rationales(self, variant_name)` (old/experiment_stats.py:1212-1316)
- Functional requirements:
  - Collect rationales and scores, extract keywords for low/high scores, compute rationale length statistics, and compare score distributions.
  - Handle both dict and list rationale structures.
  - Utilize inline helpers (`collect_rationales_scores`, `extract_keywords`) to normalize rationale inputs and keyword tallies.
  - Return comprehensive dictionary of textual analytics.
- Non-functional requirements:
  - Filter stop words and short terms to retain meaningful keywords.
  - Avoid crashing when rationales missing or malformed; treat empty as zero-length.

### `analyze_score_flips(self, variant_name)` (old/experiment_stats.py:1318-1352)
- Functional requirements:
  - Evaluate paired scores to categorize flips (fail/pass, major gains/drops) and return counts with sample examples.
- Non-functional requirements:
  - Provide stable example ordering (first occurrences).

### `analyze_referee_alignment(self, variant_name)` (old/experiment_stats.py:1354-1446)
- Functional requirements:
  - Derive referee-derived scores, compare with LLM outputs, compute alignment metrics (mean differences, correlations), and produce interpretive summary.
  - Utilize `_interpret_referee_alignment` for descriptive text.
  - Normalize referee data and alignment distances via helper closures (`get_referee_score`, `calculate_alignment`).
- Non-functional requirements:
  - Handle cases with insufficient referee data by returning `np.nan` and `None` appropriately.

### `_interpret_referee_alignment(self, baseline_align, variant_align, baseline_corr, variant_corr)` (old/experiment_stats.py:1448-1465)
- Functional requirements:
  - Produce textual interpretation describing improvements or declines in alignment and correlation.
- Non-functional requirements:
  - Operate robustly when alignment or correlation is `np.nan`.

### `analyze_context_effects(self, variant_name)` (old/experiment_stats.py:1467-1501)
- Functional requirements:
  - Compare mean scores and effect sizes for contexts (Capability, Capacity) between baseline and variant.
  - Return dictionary keyed by context with metrics.
- Non-functional requirements:
  - Handle absence of context data by returning `NaN` values from NumPy means.

### `generate_recommendations(self)` (old/experiment_stats.py:1503-1568)
- Functional requirements:
  - Iterate variants to detect improvements (e.g., reintroducing score 1s, reducing overscoring, providing consistent alternatives).
  - Create prioritized recommendation entries with reason, details, and supporting metrics.
  - Sort recommendations by priority and correlation.
- Non-functional requirements:
  - Skip variants with analysis errors to avoid spurious recommendations.
  - Maintain stable priority ordering using defined priority map.

### `_safe_get_numeric(self, value, default=0.0)` (old/experiment_stats.py:1570-1581)
- Functional requirements:
  - Coerce value to float when possible, returning default on failure or None.
- Non-functional requirements:
  - Avoid raising exceptions; keep utility lightweight.

### `_get_basic_stats(self, results)` (old/experiment_stats.py:1583-1619)
- Functional requirements:
  - Compute descriptive statistics (mean, median, std, min, max, total, distribution, presence of extreme scores, skewness, kurtosis) for provided results list.
  - Return zeroed metrics when no scores available.
- Non-functional requirements:
  - Ensure dictionary values are JSON-serializable (cast to native types).

### `_get_config_diff(self, variant_name)` (old/experiment_stats.py:1621-1651)
- Functional requirements:
  - Compare variant config against baseline config, accounting for object or dict forms.
  - Return dictionary of differing keys with baseline/variant values.
- Non-functional requirements:
  - Handle missing configs gracefully by returning empty dict.

### `export_analysis_config(self, output_dir)` (old/experiment_stats.py:1653-1687)
- Functional requirements:
  - Serialize analysis metadata (version, timestamp, baseline, experiments, tests, criteria, thresholds) into `analysis_config.json`.
  - Use `NumpyJSONEncoder` for compatibility.
- Non-functional requirements:
  - Ensure output directory exists prior to writing.
  - Keep file writing atomic where possible (overwrite safely).

### `generate_failure_analysis_report(self, output_dir)` (old/experiment_stats.py:1689-1725)
- Functional requirements:
  - Compile per-variant diagnostics (consistency, category effects, score flips, context effects, rationales, referee alignment) into JSON report.
  - Exclude baseline and experiments with recorded errors.
  - Write report to `failure_analysis.json`.
- Non-functional requirements:
  - Use `NumpyJSONEncoder` to serialize NumPy types.
  - Log completion message for traceability.

### `generate_all_reports(self, output_root)` (old/experiment_stats.py:1727-1825)
- Functional requirements:
  - Create consolidated output directory, validate experiments, persist validation results, and orchestrate generation of multiple reports (individual stats, comparative analysis, distribution CSV, recommendations, config export, failure analysis, executive summary, Excel, visualizations).
  - Wrap each step in logging with error handling to continue pipeline when possible.
- Non-functional requirements:
  - Ensure pipeline resilience: failure in one step should not crash entire generation unless critical.
  - Provide user-friendly logging separators and status indicators.

### `_generate_individual_stats(self, output_root)` (old/experiment_stats.py:1827-1859)
- Functional requirements:
  - For each experiment, assemble stats payload (name, configuration, basic stats, criteria breakdown, timestamp) and save to `stats.json` under experiment-specific directory.
- Non-functional requirements:
  - Skip experiments with recorded errors without raising.
  - Maintain consistent JSON formatting using `NumpyJSONEncoder`.

### `_generate_comparative_analysis(self)` (old/experiment_stats.py:1861-1985)
- Functional requirements:
  - Build comprehensive comparative dataset covering baseline stats, variant analyses (config diff, distribution shift, consistency, transformation, outliers, criteria, scoring consistency, categories, score flips, context, rationale, referee alignment, advanced statistics), and best variant determination.
  - Leverage previously defined helper methods to populate sections.
- Non-functional requirements:
  - Ensure returned structure is JSON-serializable and internally consistent.
  - Handle variants with errors gracefully by embedding error messages.

### `_generate_distribution_csv(self, output_dir)` (old/experiment_stats.py:1987-2019)
- Functional requirements:
  - Compile per-experiment score distribution metrics into pandas DataFrame and export to `score_distributions.csv`.
  - Exclude experiments lacking scores or marked with errors.
- Non-functional requirements:
  - Avoid writing file when there are no valid rows.

### `_create_advanced_statistics_dataframe(self, comparative)` (old/experiment_stats.py:2021-2060)
- Functional requirements:
  - Construct DataFrame summarizing advanced statistics for each variant from comparative analysis (Cliff’s delta, Cohen’s d CI, power, Bayesian metrics, practical significance, Krippendorff alpha, assumption tests).
- Non-functional requirements:
  - Return `None` when no qualifying data available.

### `_generate_excel_report(self, output_dir, comparative, recommendations)` (old/experiment_stats.py:2062-2163)
- Functional requirements:
  - Produce multi-sheet Excel report with summary, distributions, statistical tests, recommendations, criteria analysis, outliers, advanced statistics, score flips.
  - Use `openpyxl` when available; fall back to `xlsxwriter` or skip with warning.
  - Apply formatting via `_format_excel_workbook`.
- Non-functional requirements:
  - Handle missing comparative data gracefully by logging error and skipping.
  - Ensure Excel writer context managers close files properly.

### `_write_excel_sheets_basic(self, writer, comparative, recommendations)` (old/experiment_stats.py:2165-2192)
- Functional requirements:
  - Provide minimal Excel export for fallback engine without advanced formatting.
- Non-functional requirements:
  - Flatten nested recommendation metrics for readability.

### `_create_summary_dataframe(self, comparative)` (old/experiment_stats.py:2194-2231)
- Functional requirements:
  - Build DataFrame summarizing baseline and variant metrics (mean score, mean delta, effect size, correlation, p-value significance).
- Non-functional requirements:
  - Return empty DataFrame when inputs insufficient to avoid downstream errors.

### `_create_distribution_dataframe(self)` (old/experiment_stats.py:2233-2261)
- Functional requirements:
  - Assemble DataFrame with raw counts and percentages for scores 1–5 across experiments.
- Non-functional requirements:
  - Exclude experiments flagged with errors to maintain accuracy.

### `_create_statistical_tests_dataframe(self, comparative)` (old/experiment_stats.py:2263-2297)
- Functional requirements:
  - Generate DataFrame listing statistical test results and correlations per variant.
- Non-functional requirements:
  - Return empty DataFrame if no valid variants.

### `_create_criteria_analysis_dataframe(self, comparative)` (old/experiment_stats.py:2299-2331)
- Functional requirements:
  - Flatten criteria analysis across variants into DataFrame with deltas and significance flags.
- Non-functional requirements:
  - Return `None` when no valid criteria data exists to reduce sheet clutter.

### `_create_outliers_dataframe(self, comparative)` (old/experiment_stats.py:2333-2361)
- Functional requirements:
  - Compile top outliers per variant into DataFrame for Excel export.
- Non-functional requirements:
  - Return `None` when no outliers present.

### `_format_excel_workbook(self, workbook)` (old/experiment_stats.py:2363-2410)
- Functional requirements:
  - Apply header styling, auto-adjust column widths, and set numeric formats across Excel worksheets using openpyxl.
- Non-functional requirements:
  - Catch exceptions and log warnings without aborting report generation.

### `_generate_executive_summary(self, output_dir, comparative, recommendations)` (old/experiment_stats.py:2412-2536)
- Functional requirements:
  - Produce markdown executive summary capturing baseline info, key findings, recommendations, statistical tables, comparison matrix, and significance overview.
  - Handle missing comparative or recommendation data by providing defaults.
  - Write summary to `executive_summary.md`.
- Non-functional requirements:
  - Ensure markdown is human-readable with headings and tables.
  - Avoid revealing sensitive data (e.g., raw prompt text) in summary.

### `_generate_visualizations(self, output_dir)` (old/experiment_stats.py:2538-2616)
- Functional requirements:
  - Generate composite PNG with violin plots, mean comparisons, correlation heatmap, and effect size bar chart using matplotlib/seaborn.
  - Save figure to `analysis_summary.png`.
- Non-functional requirements:
  - Handle missing visualization libraries gracefully (log warning).
  - Close figures after saving to prevent memory leaks.

### `_plot_distributions(self, ax)` (old/experiment_stats.py:2618-2651)
- Functional requirements:
  - Render violin plots for experiment score distributions with baseline highlighted.
- Non-functional requirements:
  - Adjust axes labels/ticks for readability; set consistent y-limits (0.5–5.5).

### `_plot_mean_comparison(self, ax)` (old/experiment_stats.py:2653-2680)
- Functional requirements:
  - Plot mean scores with standard deviation error bars, distinguishing baseline color and including reference line.
- Non-functional requirements:
  - Ensure chart remains legible for multiple experiments (rotate labels, add grid).

### `_plot_correlation_heatmap(self, ax)` (old/experiment_stats.py:2682-2721)
- Functional requirements:
  - Compute Spearman correlations between experiments via paired scores and render heatmap with annotations.
- Non-functional requirements:
  - Handle cases with insufficient pairs by leaving entries zero or `np.nan`.

### `_get_paired_scores_between(self, exp1, exp2)` (old/experiment_stats.py:2723-2761)
- Functional requirements:
  - Build paired score list between arbitrary experiments by aligning IDs and score sequences.
- Non-functional requirements:
  - Provide deterministic pairing order (sorted IDs).

### `_plot_effect_sizes(self, ax)` (old/experiment_stats.py:2763-2796)
- Functional requirements:
  - Display horizontal bar chart of Cohen’s d for each variant with color coded magnitude thresholds.
- Non-functional requirements:
  - Include reference lines for interpretation thresholds and ensure grid improves readability.
