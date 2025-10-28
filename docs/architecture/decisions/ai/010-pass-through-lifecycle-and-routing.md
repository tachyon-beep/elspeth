# ADR-010 – Pass-Through Lifecycle and Routing (LITE)

## Status

**DRAFT** (2025-10-26)

## Context

Elspeth plugins operate in pipeline: datasource → transforms → sinks. Plugins need consistent lifecycle hooks for setup/teardown, data hand-off, artifact routing.

**Problems pre-ADR-010**:
- Inconsistent lifecycle (some plugins had setup(), others didn't)
- Ad-hoc data passing (no standard hand-off protocol)
- Artifact routing unclear (who calls collect_artifacts()?)
- Resource cleanup unreliable (leaks on errors)

## Decision

Implement **Pass-Through Lifecycle** with standardized hooks and routing protocol.

### Lifecycle Hooks

```python
class BasePlugin:
    """Standard lifecycle for all plugins."""

    def setup(self, context: PluginContext):
        """Called once before first use (resource allocation)."""
        pass

    def teardown(self):
        """Called once after last use (resource cleanup)."""
        pass

    # Context manager support
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.teardown()
```

### Data Hand-Off Protocol

**DataSource → Transform**:
```python
# Datasource produces DataFrame
df = datasource.load()

# Transform receives DataFrame, returns dict
result = transform.transform(row)  # Per-row
```

**Transform → Sink**:
```python
# Sink receives aggregated results
sink.write(results, metadata=pipeline_metadata)
```

### Artifact Routing (ADR-007)

```python
# After pipeline execution
for plugin in [datasource, *transforms, *sinks]:
    artifacts = plugin.collect_artifacts()
    artifact_pipeline.route(artifacts)
```

## Pass-Through Pattern

Plugins pass data WITHOUT modification unless transforming:

```python
# Datasource: Produces data
class DataSource:
    def load(self) -> pd.DataFrame:
        df = self._fetch_data()
        self._register_dataframe_output(df)  # ADR-007
        self._register_artifact_output("source", "file/csv", path=self.path)
        return df  # ✅ Pass through to transforms

# Transform: Modifies data
class Transform:
    def transform(self, row: dict) -> dict:
        result = self._process(row)
        self._register_artifact_output("llm_response", "llm/response", payload=result)
        return result  # ✅ Pass through to next stage

# Sink: Consumes data, produces artifacts
class Sink:
    def write(self, results: dict):
        self._save(results)
        self._register_artifact_output("output", "file/csv", path=self.output_path)
        # ❌ No return - terminal node
```

## Resource Management

### Guaranteed Cleanup

```python
# Context manager ensures cleanup
with DataSource(...) as datasource:
    df = datasource.load()
    # Process...
# teardown() called automatically, even on exceptions
```

### Error Handling

```python
def run_pipeline(datasource, transforms, sinks):
    """Run pipeline with guaranteed cleanup."""
    all_plugins = [datasource, *transforms, *sinks]

    try:
        # Setup all plugins
        for plugin in all_plugins:
            plugin.setup(context)

        # Execute pipeline
        df = datasource.load()
        results = process_transforms(df, transforms)
        write_sinks(results, sinks)

    finally:
        # Teardown in reverse order (LIFO)
        for plugin in reversed(all_plugins):
            try:
                plugin.teardown()
            except Exception as e:
                logger.error(f"Teardown failed for {plugin}: {e}")
                # Continue cleanup, don't re-raise
```

## Consequences

### Benefits
- **Consistent lifecycle** - All plugins use same hooks
- **Guaranteed cleanup** - `finally` block + context managers
- **Clear routing** - Artifact collection explicit
- **Pass-through semantics** - Data flows predictably

### Limitations
- **Teardown complexity** - Reverse-order teardown needed
- **Error accumulation** - Teardown errors logged, not raised
- **Context manager overhead** - Extra indentation

## Related

ADR-004 (BasePlugin), ADR-007 (Dual-output), ADR-011 (Error handling)

---
**Last Updated**: 2025-10-26
