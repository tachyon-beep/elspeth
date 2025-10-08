# Azure Telemetry Parity Plan

## Legacy Behaviours to Preserve
- **Experiment discovery logging**: `ExperimentSuite.__init__` logs experiment rows (name/temp/tokens/baseline) and counts to Azure ML (`old/experiment_runner.py:200`).
- **Preflight insights**: warnings and issues are surfaced before execution (`old/experiment_runner.py:211`).
- **Per-experiment metrics**: post-run metrics logged under `<experiment>_<metric>` (`old/experiment_runner.py:230`).
- **Baseline comparison tables**: differences emitted via `log_table` for Azure review (`old/experiment_runner.py:245`).

## Refactor Targets
1. **Middleware Enrichment**
   - Augment `AzureEnvironmentMiddleware` with explicit hooks for experiment lifecycle events: `on_suite_loaded`, `on_experiment_start`, `on_experiment_complete`, `on_comparison`.
   - Maintain internal summary (success/failure counts, totals) to emit a final `suite_summary` row at teardown.
   - Continue per-request logging for row-level detail.

2. **Suite Runner Integration**
   - Detect active Azure middleware instances when building runners and call hooks at appropriate times.
   - On suite load, log experiment metadata once (mirrors legacy `log_row('experiments', ...)`).
   - Before each experiment run, emit `experiment_start`; after payload returned, emit metrics (rows, aggregates, cost summary, failures) via `experiment_complete`.
   - When baseline comparisons exist, call middleware hook to log diff tables.

3. **Preflight Path**
   - Export preflight issues/warnings via middleware hook so Azure ML run captures readiness info (initial MVP can log as `suite_preflight`).

4. **Failure Handling**
   - Middleware remains fail-fast during init; lifecycle hooks should no-op only if middleware not present (other experiments may omit it).

5. **Testing**
   - Unit tests covering: suite load logging, experiment start/complete payloads, baseline comparison logging, final summary emission.
   - Mock Azure Run to capture log_row/log_table calls and assert structure.

## Implementation Steps
1. Extend middleware class with lifecycle methods + summary storage.
2. Update suite runner to surface middleware instances and invoke hooks.
3. Capture preflight output from suite defaults (or new helper) and pass to middleware.
4. Add tests in `tests/test_llm_middleware.py` (or a dedicated suite test) validating the new behaviours with mocked run.
5. Update notes/README to document Azure parity and config expectations.
