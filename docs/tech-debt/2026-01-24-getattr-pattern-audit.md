# getattr() Pattern Audit

**Date:** 2026-01-24
**Context:** Schema validation refactor cleanup

## Summary

Total patterns found: 15
- Legitimate (Plugin/Framework Boundaries): 13
- Legitimate (Standard Library API): 2
- Bug-Hiding: 0

## Methodology

Searched for all `getattr()` usage in `src/elspeth/` and analyzed each pattern against CLAUDE.md criteria:
- **Legitimate:** Plugin boundaries, framework boundaries, serialization, standard library APIs
- **Bug-Hiding:** Covering for missing attributes, incorrect field names, hallucinatory fixes

## Legitimate Patterns (Keep)

### Pattern Group 1: Plugin Schema Introspection (Plugin Boundary)

**Rationale:** Plugins have different schema contracts based on type. Sources have only `output_schema`, sinks have only `input_schema`, transforms have both. Using `getattr(..., None)` allows polymorphic handling at the plugin boundary without requiring every plugin to define all schemas.

#### File: src/elspeth/plugins/manager.py:93-94

```python
# Schemas vary by plugin type: sources have only output_schema,
# sinks have only input_schema, transforms have both.
input_schema = getattr(plugin_cls, "input_schema", None)
output_schema = getattr(plugin_cls, "output_schema", None)
```

**Analysis:** Plugin boundary - schema presence varies legitimately by plugin type (Source/Transform/Sink)

**Action:** Keep - This is the canonical example of legitimate framework polymorphism

---

#### File: src/elspeth/core/dag.py:535

```python
# Add source - extract schema from instance
source_id = node_id("source", source.name)
graph.add_node(
    source_id,
    node_type="source",
    plugin_name=source.name,
    config={},
    output_schema=getattr(source, "output_schema", None),
)
```

**Analysis:** Plugin boundary - extracting schema from plugin instance at DAG construction time

**Action:** Keep - Mirrors the plugin_manager pattern for instance-level schema access

---

#### File: src/elspeth/core/dag.py:548

```python
# Add sinks
for sink_name, sink in sinks.items():
    sid = node_id("sink", sink_name)
    sink_ids[sink_name] = sid
    graph.add_node(
        sid,
        node_type="sink",
        plugin_name=sink.name,
        config={},
        input_schema=getattr(sink, "input_schema", None),
    )
```

**Analysis:** Plugin boundary - sinks have input_schema but not output_schema

**Action:** Keep - Correct plugin polymorphism

---

#### File: src/elspeth/core/dag.py:567-568

```python
# Build transform chain
for i, transform in enumerate(transforms):
    tid = node_id("transform", transform.name)
    transform_ids[i] = tid

    graph.add_node(
        tid,
        node_type="transform",
        plugin_name=transform.name,
        config={},
        input_schema=getattr(transform, "input_schema", None),
        output_schema=getattr(transform, "output_schema", None),
    )
```

**Analysis:** Plugin boundary - transforms have both schemas

**Action:** Keep - Consistent with other plugin schema extraction

---

#### File: src/elspeth/core/dag.py:593-594

```python
# Build aggregations - dual schemas
for agg_name, (transform, agg_config) in aggregations.items():
    aid = node_id("aggregation", agg_name)
    aggregation_ids[agg_name] = aid

    agg_node_config = {
        "trigger": agg_config.trigger.model_dump(),
        "output_mode": agg_config.output_mode,
        "options": dict(agg_config.options),
    }

    graph.add_node(
        aid,
        node_type="aggregation",
        plugin_name=agg_config.plugin,
        config=agg_node_config,
        input_schema=getattr(transform, "input_schema", None),
        output_schema=getattr(transform, "output_schema", None),
    )
```

**Analysis:** Plugin boundary - aggregations extract schemas from their transform instances

**Action:** Keep - Correct plugin polymorphism

---

### Pattern Group 2: Plugin Discovery (Framework Boundary)

**Rationale:** Plugin discovery scans arbitrary Python files looking for classes that inherit from base plugin types. At scan time, we cannot know which classes have which attributes - this is the textbook case for defensive getattr at a trust boundary.

#### File: src/elspeth/plugins/discovery.py:126

```python
# Must have a `name` attribute with non-empty value
# NOTE: This getattr is at a PLUGIN DISCOVERY TRUST BOUNDARY - we're scanning
# arbitrary Python files and can't know at compile time which classes have
# a `name` attribute. This is legitimate framework-level polymorphism.
plugin_name = getattr(obj, "name", None)
if not plugin_name:
    logger.warning(
        "Class %s in %s inherits from %s but has no/empty 'name' attribute - skipping",
        name,
        py_file,
        base_class.__name__,
    )
    continue
```

**Analysis:** Plugin discovery boundary - scanning arbitrary classes, cannot know at compile time which have `name` attribute

**Action:** Keep - Legitimate framework boundary with excellent explanatory comment

---

#### File: src/elspeth/plugins/discovery.py:233

```python
# Fallback to name-based description
name = getattr(plugin_cls, "name", plugin_cls.__name__)
return f"{name} plugin"
```

**Analysis:** Plugin boundary - fallback for generating description when plugin class may not have `name` attribute defined

**Action:** Keep - Legitimate fallback with `__name__` as safe default

---

### Pattern Group 3: Optional Plugin Features (Plugin Boundary)

**Rationale:** Some plugin features are optional - not all sources need custom validation failure handling, not all sources use schema-based coercion. Using getattr allows graceful detection of optional features without requiring every plugin to define them.

#### File: src/elspeth/engine/orchestrator.py:342

```python
# Check if source has _on_validation_failure attribute
# This is set by sources that inherit from SourceDataConfig
on_validation_failure = getattr(source, "_on_validation_failure", None)

if on_validation_failure is None:
    # Source doesn't use on_validation_failure - that's fine
    return

# Skip validation if not a string (e.g., MagicMock in tests)
# Real sources always have string values from SourceDataConfig
if not isinstance(on_validation_failure, str):
    return
```

**Analysis:** Optional plugin feature - not all sources use `on_validation_failure` routing

**Action:** Keep - Correct detection of optional plugin feature with proper None handling

---

#### File: src/elspeth/engine/orchestrator.py:1334

```python
# TYPE FIDELITY: Pass source schema to restore coerced types (datetime, Decimal, etc.)
# The source's _schema_class attribute contains the Pydantic model with allow_coercion=True
source_schema_class = getattr(config.source, "_schema_class", None)
unprocessed_rows = recovery.get_unprocessed_row_data(run_id, payload_store, source_schema_class=source_schema_class)
```

**Analysis:** Optional plugin feature - sources may have `_schema_class` for type coercion during recovery, but not required

**Action:** Keep - Correct detection of optional schema support for type fidelity in recovery

---

### Pattern Group 4: External System Response (External Boundary)

**Rationale:** Azure Batch API responses are external system data - we don't control the API contract, and fields may be absent or present depending on batch state. This is a classic external boundary case.

#### File: src/elspeth/plugins/llm/azure_batch.py:491

```python
ctx.record_call(
    call_type=CallType.HTTP,
    status=CallStatus.SUCCESS,
    request_data=retrieve_request,
    response_data={
        "batch_id": batch.id,
        "status": batch.status,
        "output_file_id": getattr(batch, "output_file_id", None),
    },
    latency_ms=(time.perf_counter() - start) * 1000,
)
```

**Analysis:** External API boundary - Azure Batch response may not have `output_file_id` until batch completes

**Action:** Keep - Legitimate external system boundary handling

---

### Pattern Group 5: Standard Library API (Module Attribute Lookup)

**Rationale:** Using getattr to look up logging level constants from the `logging` module is a standard Python pattern for converting string names to module constants. This is not defensive programming - it's the idiomatic way to access module-level constants dynamically.

#### File: src/elspeth/core/logging.py:30

```python
# Configure standard library logging
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=getattr(logging, level.upper()),
    force=True,  # Allow reconfiguration
)
```

**Analysis:** Standard library API - converting string "DEBUG"/"INFO" to `logging.DEBUG`/`logging.INFO` constant

**Action:** Keep - Idiomatic Python for dynamic constant lookup

---

#### File: src/elspeth/core/logging.py:59

```python
structlog.configure(
    processors=processors,
    wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)
```

**Analysis:** Standard library API - same as above, converting level string to logging constant

**Action:** Keep - Idiomatic Python for dynamic constant lookup

---

## Bug-Hiding Patterns (Fix Later)

**None found.**

All `getattr()` patterns in the codebase are legitimate uses at plugin/framework/external boundaries or standard library API usage.

---

## Conclusions

The codebase demonstrates excellent adherence to CLAUDE.md's prohibition on bug-hiding defensive patterns:

1. **No hallucination fixes:** No `getattr()` calls added to silence errors from nonexistent fields
2. **Proper trust boundaries:** All usage is at documented plugin/framework/external boundaries
3. **No config coercion:** No `getattr()` on config objects to hide missing required fields
4. **No internal state defense:** No defensive getattr on `self._` internal state

**Recommendation:** No remediation required. All patterns are legitimate and should be preserved.

---

## Appendix: Trust Boundary Decision Tree

For future reference when evaluating new `getattr()` additions:

```
Is this getattr() legitimate?
│
├─ Is it accessing a plugin attribute?
│  ├─ YES: Is the attribute optional by plugin contract?
│  │  ├─ YES → LEGITIMATE (e.g., input_schema varies by plugin type)
│  │  └─ NO → BUG-HIDING (plugin contract violation, should crash)
│  └─ NO ↓
│
├─ Is it scanning/discovering external code?
│  ├─ YES → LEGITIMATE (framework discovery boundary)
│  └─ NO ↓
│
├─ Is it parsing external system data?
│  ├─ YES → LEGITIMATE (external API boundary)
│  └─ NO ↓
│
├─ Is it looking up module constants dynamically?
│  ├─ YES → LEGITIMATE (standard library API pattern)
│  └─ NO ↓
│
└─ Is it accessing our internal state/config?
   └─ YES → BUG-HIDING (should crash on missing attribute)
```

**Rule of thumb:** If removing the getattr would cause a crash that reveals a bug in our code, it's bug-hiding. If it's handling legitimate variation at a trust boundary, it's correct.
