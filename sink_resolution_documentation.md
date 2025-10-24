# Sink Resolution Priority in ExperimentSuiteRunner

**File:** `src/elspeth/core/experiments/suite_runner.py`
**Method:** `run()`
**Lines:** 329-336
**Complexity Contribution:** +4 (nested conditionals)

---

## Overview

The ExperimentSuiteRunner resolves which sinks to use for each experiment through a **5-level priority hierarchy**. This document explains the resolution logic, provides examples, and documents edge cases discovered during risk reduction testing.

---

## Sink Resolution Priority

**Rule:** First match wins (short-circuit evaluation)

```
Priority Order (Highest → Lowest):
┌─────────────────────────────────────────────────┐
│ 1. experiment.sink_defs          [HIGHEST]     │
│ 2. pack["sinks"]                                │
│ 3. defaults["sink_defs"]                        │
│ 4. sink_factory(experiment)                     │
│ 5. self.sinks                    [LOWEST]      │
└─────────────────────────────────────────────────┘
```

---

## Code Location

**Current Implementation:** `suite_runner.py` lines 329-336

```python
# Sink resolution in main experiment loop
if experiment.sink_defs:
    sinks = self._instantiate_sinks(experiment.sink_defs)
elif pack and pack.get("sinks"):
    sinks = self._instantiate_sinks(pack["sinks"])
elif defaults.get("sink_defs"):
    sinks = self._instantiate_sinks(defaults["sink_defs"])
else:
    sinks = sink_factory(experiment) if sink_factory else self.sinks
```

**Refactoring Target:** Extract to `_resolve_experiment_sinks()` helper method

---

## Resolution Paths Explained

### Path 1: Experiment Sink Definitions (Highest Priority)

**Condition:** `experiment.sink_defs` is not None and not empty
**Use Case:** Experiment-specific output requirements
**Example:** A/B test where variant needs different output format

```yaml
# settings.yaml
suite:
  experiments:
    - name: variant_a
      sink_defs:
        - plugin: csv_file
          options:
            path: results/variant_a.csv
            security_level: internal
            determinism_level: deterministic
```

**Behavior:**
- `experiment.sink_defs` always wins, even if pack and defaults also define sinks
- Sink definitions are instantiated via `_instantiate_sinks()`
- Each experiment can have completely different sink configurations

**Test Coverage:** `test_sink_resolution_path_1_experiment_wins`

---

### Path 2: Prompt Pack Sinks

**Condition:** `experiment.sink_defs` is None AND `pack["sinks"]` exists
**Use Case:** Pack-specific output requirements for benchmarks or templates
**Example:** Benchmark pack requires specific output format

```yaml
# settings.yaml
suite:
  prompt_packs:
    benchmark_pack:
      sinks:
        - plugin: csv_file
          options:
            path: benchmarks/results.csv
            security_level: internal
            determinism_level: deterministic
        - plugin: json_file
          options:
            path: benchmarks/results.json
            security_level: internal
            determinism_level: deterministic

  experiments:
    - name: benchmark_run
      prompt_pack: benchmark_pack
      # No sink_defs - will use pack sinks
```

**Behavior:**
- Only used when experiment doesn't define its own sinks
- All experiments using the same pack share these sinks
- Pack sinks override defaults

**Test Coverage:** `test_sink_resolution_path_2_pack_fallback`

---

### Path 3: Suite Defaults Sink Definitions

**Condition:** No experiment sinks AND no pack sinks AND `defaults["sink_defs"]` exists
**Use Case:** Organization-wide standard outputs
**Example:** All suites must log to audit sink

```yaml
# settings.yaml
suite:
  defaults:
    sink_defs:
      - plugin: audit_log
        options:
          path: /var/log/elspeth/audit.log
          security_level: official
          determinism_level: deterministic

  experiments:
    - name: experiment_1
      # No sink_defs, no pack - will use defaults
```

**Behavior:**
- Lowest priority sink definition configuration
- Applied uniformly across all experiments in suite
- Useful for compliance/audit requirements

**Test Coverage:** `test_sink_resolution_path_3_defaults_fallback`

---

### Path 4: Sink Factory Callback

**Condition:** No sink_defs anywhere AND `sink_factory` is provided
**Use Case:** Dynamic sink creation based on experiment metadata
**Example:** Create sink with experiment name in path

```python
# Python code
def create_experiment_sinks(experiment: ExperimentConfig) -> list[ResultSink]:
    """Create sinks dynamically based on experiment configuration."""
    path = f"results/{experiment.name}_{experiment.temperature}.csv"
    return [
        CsvFileSink(
            path=path,
            security_level="internal",
            determinism_level="deterministic",
        )
    ]

runner.run(
    df,
    defaults,
    sink_factory=create_experiment_sinks  # Called for each experiment
)
```

**Behavior:**
- Factory is called **once per experiment** with the ExperimentConfig
- Factory must return list of ResultSink instances
- Enables runtime sink customization based on experiment properties

**Test Coverage:** `test_sink_resolution_path_4_factory_fallback`

---

### Path 5: Suite Runner Sinks (Lowest Priority)

**Condition:** No sink_defs, no pack, no defaults, no factory
**Use Case:** Simple suite execution with uniform sinks
**Example:** Command-line tool that provides sinks at construction

```python
# Python code
audit_sink = AuditLogSink(...)
csv_sink = CsvFileSink(...)

runner = ExperimentSuiteRunner(
    suite=suite,
    llm_client=llm,
    sinks=[audit_sink, csv_sink]  # Fallback sinks
)

# No sink_factory provided - uses self.sinks
runner.run(df, defaults)
```

**Behavior:**
- Same sinks used for all experiments in suite
- Provided at ExperimentSuiteRunner construction
- Last resort fallback

**Test Coverage:** `test_sink_resolution_path_5_self_sinks_fallback`

---

## Resolution Decision Tree

```
For each experiment:

  experiment.sink_defs defined?
  ├─ YES → Use experiment.sink_defs [PATH 1]
  └─ NO
      ├─ pack && pack["sinks"]?
      │   ├─ YES → Use pack["sinks"] [PATH 2]
      │   └─ NO
      │       ├─ defaults["sink_defs"]?
      │       │   ├─ YES → Use defaults["sink_defs"] [PATH 3]
      │       │   └─ NO
      │       │       ├─ sink_factory provided?
      │       │       │   ├─ YES → Call sink_factory(experiment) [PATH 4]
      │       │       │   └─ NO → Use self.sinks [PATH 5]
```

---

## Edge Cases

### Edge Case 1: Empty Sink Definitions List

**Scenario:** `experiment.sink_defs = []` (empty list)

**Current Behavior:**
```python
if experiment.sink_defs:  # [] is falsy in boolean context
    # This branch is NOT taken
```

**Result:** Empty list is treated as "no sinks defined", falls through to next priority level.

**Test:** `test_sink_resolution_with_empty_sink_defs`

---

### Edge Case 2: Factory Receives Correct Experiment

**Scenario:** Multiple experiments, factory should get correct config

**Expected Behavior:**
- Factory called once per experiment
- Each call receives the specific ExperimentConfig for that experiment
- Different experiments can result in different sinks

**Test:** `test_sink_resolution_factory_receives_correct_experiment`

```python
def create_sinks(exp: ExperimentConfig):
    # exp.name is the specific experiment name
    # exp.temperature is the specific temperature
    return [CustomSink(name=exp.name)]

# Experiment 1: factory called with exp1 config
# Experiment 2: factory called with exp2 config
```

---

### Edge Case 3: Pack Sinks with Multiple Experiments

**Scenario:** Multiple experiments use same pack

**Behavior:**
- All experiments share the same pack sink instances
- Sinks receive results from all experiments using the pack
- No per-experiment isolation at pack level

**Implication:** Pack sinks must handle results from multiple experiments.

---

## Priority Override Examples

### Example 1: Experiment Overrides Everything

```yaml
suite:
  defaults:
    sink_defs:
      - plugin: csv_file
        options: {path: default.csv}

  prompt_packs:
    my_pack:
      sinks:
        - plugin: json_file
          options: {path: pack.json}

  experiments:
    - name: exp1
      prompt_pack: my_pack
      sink_defs:  # This wins!
        - plugin: excel
          options: {path: experiment.xlsx}
```

**Result:** exp1 uses Excel sink (experiment wins over pack and defaults)

---

### Example 2: Pack Wins Over Defaults

```yaml
suite:
  defaults:
    sink_defs:
      - plugin: csv_file
        options: {path: default.csv}

  prompt_packs:
    my_pack:
      sinks:  # This wins!
        - plugin: json_file
          options: {path: pack.json}

  experiments:
    - name: exp1
      prompt_pack: my_pack
      # No sink_defs
```

**Result:** exp1 uses JSON sink from pack (pack wins over defaults)

---

### Example 3: Factory Wins Over self.sinks

```python
runner = ExperimentSuiteRunner(
    suite=suite,
    llm_client=llm,
    sinks=[DefaultSink()]  # Lowest priority
)

def factory(exp):
    return [FactorySink()]  # This wins!

runner.run(df, defaults={}, sink_factory=factory)
```

**Result:** Experiments use FactorySink (factory wins over self.sinks)

---

## Complexity Analysis

**Current Complexity Contribution:** +4

**Breakdown:**
- `if experiment.sink_defs:` +1
- `elif pack and pack.get("sinks"):` +2 (two conditions)
- `elif defaults.get("sink_defs"):` +1
- Ternary in else: `sink_factory(experiment) if sink_factory else self.sinks` +0 (same level)

**Refactoring Opportunity:**
Extract to `_resolve_experiment_sinks()` helper method using early returns:

```python
def _resolve_experiment_sinks(
    self,
    experiment: ExperimentConfig,
    pack: dict[str, Any] | None,
    defaults: dict[str, Any],
    sink_factory: Callable | None,
) -> list[ResultSink]:
    """Resolve sinks for experiment (priority: experiment > pack > defaults > factory > self)."""
    # Path 1: Experiment sinks (highest priority)
    if experiment.sink_defs:
        return self._instantiate_sinks(experiment.sink_defs)

    # Path 2: Prompt pack sinks
    if pack and pack.get("sinks"):
        return self._instantiate_sinks(pack["sinks"])

    # Path 3: Suite defaults sinks
    if defaults.get("sink_defs"):
        return self._instantiate_sinks(defaults["sink_defs"])

    # Path 4: Sink factory callback
    if sink_factory:
        return sink_factory(experiment)

    # Path 5: Suite runner sinks (lowest priority)
    return self.sinks
```

**Expected Complexity Reduction:** +4 → +2 (early returns reduce nesting)

---

## Testing Strategy

**Test Coverage:** 8 tests in `tests/test_suite_runner_sink_resolution.py`

**Behavioral Tests:**
1. `test_sink_resolution_path_1_experiment_wins` - Experiment priority
2. `test_sink_resolution_path_2_pack_fallback` - Pack fallback
3. `test_sink_resolution_path_3_defaults_fallback` - Defaults fallback
4. `test_sink_resolution_path_4_factory_fallback` - Factory callback
5. `test_sink_resolution_path_5_self_sinks_fallback` - self.sinks fallback
6. `test_sink_resolution_priority_ordering` - Multi-layer priority verification

**Edge Case Tests:**
7. `test_sink_resolution_with_empty_sink_defs` - Empty list handling
8. `test_sink_resolution_factory_receives_correct_experiment` - Factory arguments

---

## Refactoring Guidance

**Phase 2: Simple Helper Extraction**

**Method to Extract:** `_resolve_experiment_sinks()`

**Signature:**
```python
def _resolve_experiment_sinks(
    self,
    experiment: ExperimentConfig,
    pack: dict[str, Any] | None,
    defaults: dict[str, Any],
    sink_factory: Callable[[ExperimentConfig], list[ResultSink]] | None,
) -> list[ResultSink]:
```

**Benefits:**
1. Single Responsibility: Only resolves sinks, no other logic
2. Early Returns: Reduces nesting from 4 levels to linear checks
3. Testability: Can unit test sink resolution in isolation
4. Clarity: Method name documents intent ("resolve experiment sinks")
5. Complexity Reduction: +4 → +2 in main run() method

**Integration Point:**
```python
# In run() method
for experiment in context.experiments:
    pack = self._resolve_pack(experiment, context)
    sinks = self._resolve_experiment_sinks(experiment, pack, context.defaults, sink_factory)
    # ... rest of experiment execution
```

---

## Security & Performance Considerations

### Security

**Sink Instantiation:**
- All sinks instantiated via `_instantiate_sinks()` undergo security level validation
- Each sink must declare `security_level` and `determinism_level`
- ConfigurationError raised if security levels missing

**Context Propagation:**
- PluginContext applied to all sinks after resolution (lines 141-152)
- Security level may be upgraded based on experiment context

### Performance

**Optimization Opportunities:**
1. **Sink Reuse:** Pack sinks could be cached across experiments using same pack
2. **Factory Calls:** Factory is called for every experiment (no caching)
3. **Instantiation:** `_instantiate_sinks()` creates new instances each time

**Current Behavior:**
- Each experiment gets fresh sink instances (no sharing)
- Factory called once per experiment (not cached)
- No sink reuse across experiments (even with identical configs)

---

## References

**Code Locations:**
- Sink resolution logic: `suite_runner.py` lines 329-336
- Sink instantiation: `suite_runner.py` lines 250-279 (`_instantiate_sinks()`)
- Context application: `suite_runner.py` lines 141-152

**Related Documentation:**
- Execution Plan: `EXECUTION_PLAN_suite_runner_refactor.md` (Phase 2, task 2.2)
- Risk Reduction: `risk_reduction_suite_runner.md` (Activity 2)
- Test File: `tests/test_suite_runner_sink_resolution.py`

**Related Tests:**
- Existing integration tests: `tests/test_suite_runner_integration.py`
- Middleware tests: `tests/test_suite_runner_middleware_hooks.py`
- Baseline tests: `tests/test_suite_runner_baseline_flow.py`

---

**Status:** DOCUMENTED - Ready for Phase 2 refactoring
**Risk Mitigation:** Activity 2 complete (Third-highest risk: sink resolution priority)
