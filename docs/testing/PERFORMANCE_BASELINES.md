# Performance Test Baselines

This document defines expected performance baselines for Elspeth's performance regression tests.

## Purpose

Performance tests in `tests/test_performance_baseline.py` serve as **canary tests** to detect significant performance degradation. They are not strict functional requirements but help identify optimization regressions early.

## Environment Considerations

Performance benchmarks are highly sensitive to:
- **CPU speed and core count** — Registry lookups and plugin creation are CPU-bound
- **System load** — Background processes can introduce variance
- **Python interpreter** — CPython 3.12+ recommended; PyPy may show different characteristics
- **CI/CD runners** — Shared infrastructure typically 5-10x slower than local development machines
- **Disk I/O** — File-based operations affected by filesystem type (SSD vs. HDD)

## Baseline Expectations

### Registry Lookup Performance

**Test:** `TestRegistryLookupPerformance`

| Operation | Local Dev (< ms) | CI Environment (< ms) | Notes |
|-----------|------------------|----------------------|-------|
| Datasource lookup | 1.0 | 10.0 | First lookup includes schema validation |
| LLM client lookup | 1.0 | 10.0 | Includes middleware chain construction |
| Sink lookup | 1.0 | 10.0 | Includes dependency graph resolution |

**Rationale:** Registry lookups involve JSONSchema validation and factory instantiation. Sub-millisecond performance on modern hardware is expected.

### Plugin Creation Performance

**Test:** `TestPluginCreationPerformance`

| Operation | Local Dev (< ms) | CI Environment (< ms) | Notes |
|-----------|------------------|----------------------|-------|
| Row plugin creation | 5.0 | 50.0 | Includes regex compilation for score extraction |
| Aggregator creation | 5.0 | 50.0 | Includes statistical helper initialization |
| Validator creation | 10.0 | 100.0 | May include nested LLM client creation |

**Rationale:** Plugin creation involves configuration parsing, validation, and initialization of internal state (regex patterns, statistical models, etc.).

### Configuration Merge Performance

**Test:** `TestConfigMergePerformance`

| Operation | Local Dev (< ms) | CI Environment (< ms) | Notes |
|-----------|------------------|----------------------|-------|
| Simple merge | 5.0 | 50.0 | Three-layer merge: defaults → pack → experiment |
| Complex merge | 20.0 | 200.0 | Includes prompt expansion and middleware chains |

**Rationale:** Configuration merging involves deep dictionary traversal and JSONSchema validation at each layer.

### Artifact Pipeline Performance

**Test:** `TestArtifactPipelinePerformance`

| Operation | Local Dev (< ms) | CI Environment (< ms) | Notes |
|-----------|------------------|----------------------|-------|
| Simple pipeline | 10.0 | 100.0 | 5 sinks, linear dependencies |
| Complex pipeline | 50.0 | 500.0 | 20 sinks, deep dependency graph |

**Rationale:** Pipeline resolution involves topological sorting, dependency analysis, and security level validation.

## Handling Test Failures

### Local Development

If performance tests fail locally:

1. **Check system load:** Close resource-intensive applications
2. **Run multiple times:** Single outliers may indicate system variance
3. **Profile the code:** If consistent failures, investigate with `cProfile` or `py-spy`

### CI/CD Environments

Performance tests are **expected to fail intermittently on CI runners** due to shared infrastructure and variable system load. Options:

#### Option 1: Skip in CI (Recommended)
```python
import os
import pytest

@pytest.mark.skipif(os.getenv("CI") == "true", reason="CI timing unreliable")
def test_datasource_lookup_fast():
    ...
```

#### Option 2: Configurable Thresholds
```python
THRESHOLD_MULTIPLIER = float(os.getenv("PERF_THRESHOLD_MULTIPLIER", "1.0"))

def test_datasource_lookup_fast():
    threshold_ms = 1.0 * THRESHOLD_MULTIPLIER
    assert elapsed < threshold_ms, f"Too slow: {elapsed:.3f}ms > {threshold_ms}ms"
```

Set `PERF_THRESHOLD_MULTIPLIER=10.0` in CI environments.

#### Option 3: Mark as Expected Failure in CI
```python
@pytest.mark.xfail(os.getenv("CI") == "true", reason="CI timing variable", strict=False)
def test_datasource_lookup_fast():
    ...
```

## Performance Regression Workflow

When performance tests fail consistently:

1. **Investigate recent changes:** Review commits since last passing test
2. **Profile the hot path:** Use `pytest-benchmark` or `cProfile` to identify bottlenecks
3. **Check for algorithmic changes:** O(n²) loops, redundant I/O, unnecessary allocations
4. **Validate test expectations:** Baseline may need adjustment if legitimate complexity increase

## Updating Baselines

Baselines should be updated when:
- **Intentional performance improvements** justify tighter thresholds
- **Legitimate complexity increases** require relaxed thresholds (document rationale)
- **Infrastructure changes** affect CI environment characteristics

**Process:**
1. Document reason for baseline change in commit message
2. Update this document with new thresholds
3. Update test assertions in `test_performance_baseline.py`
4. Run full test suite 10 times to verify stability

## Future Enhancements

- **Percentile-based assertions:** Use p95/p99 instead of max to handle outliers
- **Historical tracking:** Store results in time-series database (e.g., Prometheus)
- **Automated regression detection:** Trigger alerts on >20% degradation over 7-day moving average
- **Per-commit benchmarking:** Integrate with CI to track performance over time

## References

- Test implementation: `tests/test_performance_baseline.py`
- Registry implementation: `src/elspeth/core/registries/`
- Configuration merge: `src/elspeth/config.py`
- Artifact pipeline: `src/elspeth/core/pipeline/artifact_pipeline.py`
