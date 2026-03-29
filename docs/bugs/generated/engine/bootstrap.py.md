## Summary

Duplicate dependency names are validated only after the dependency pipelines have already executed, so an invalid `depends_on` config can mutate external state before `resolve_preflight()` aborts.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/engine/bootstrap.py
- Line(s): 58-76, 96-108
- Function/Method: `resolve_preflight`

## Evidence

`DependencyConfig.name` is documented as a unique label:

```python
# /home/john/elspeth/src/elspeth/core/dependency_config.py:14-20
class DependencyConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, description="Unique label for this dependency")
    settings: str = Field(min_length=1, description="Path to dependency pipeline settings file")
```

But `resolve_preflight()` runs all dependencies before it checks for duplicate names:

```python
# /home/john/elspeth/src/elspeth/engine/bootstrap.py:58-76
if config.depends_on:
    from elspeth.engine.dependency_resolver import detect_cycles, resolve_dependencies

    if runner is None:
        raise FrameworkBugError(...)

    detect_cycles(settings_path)

    dependency_results = resolve_dependencies(
        depends_on=config.depends_on,
        parent_settings_path=settings_path,
        runner=runner,
    )
```

The duplicate-name guard is later, after those sub-pipelines have already run:

```python
# /home/john/elspeth/src/elspeth/engine/bootstrap.py:96-108
dep_names = [r.name for r in dependency_results]
seen: set[str] = set()
duplicates: list[str] = []
for name in dep_names:
    if name in seen:
        duplicates.append(name)
    seen.add(name)
if duplicates:
    raise ValueError(f"Duplicate dependency names: {duplicates}. Each depends_on entry must have a unique name.")
```

The file itself already treats “validate before side effects” as the intended pattern for commencement gates:

```python
# /home/john/elspeth/src/elspeth/engine/bootstrap.py:48-55
# If a gate condition is malformed, we reject it here rather than after
# dependency pipelines have already run and mutated external state.
if config.commencement_gates:
    ...
    validate_gate_expressions(config.commencement_gates)
```

Current tests only assert that duplicates eventually raise; they do not assert that no dependency runner work happened first:

```python
# /home/john/elspeth/tests/unit/engine/test_bootstrap_preflight.py:353-381
def test_duplicate_dependency_names_rejected(self) -> None:
    ...
    with (
        patch("elspeth.engine.dependency_resolver.detect_cycles"),
        patch("elspeth.engine.dependency_resolver.resolve_dependencies", return_value=dep_results),
        pytest.raises(ValueError, match=r"Duplicate dependency names.*indexer"),
    ):
        resolve_preflight(...)
```

So the code does raise, but too late.

## Root Cause Hypothesis

The uniqueness check was added to protect gate-context construction from silent dict overwrites, but it was placed after `resolve_dependencies()` because the implementation validates realized `DependencyRunResult`s instead of validating the declared `config.depends_on` entries up front. That preserves the gate-context fix while missing the larger preflight invariant: invalid configuration must be rejected before any dependency side effects occur.

## Suggested Fix

Validate `config.depends_on` names before cycle detection and before calling `resolve_dependencies()`. The existing post-run check can then be removed or kept as a defensive assertion.

Example shape:

```python
if config.depends_on:
    dep_names = [dep.name for dep in config.depends_on]
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in dep_names:
        if name in seen:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        raise ValueError(f"Duplicate dependency names: {duplicates}. Each depends_on entry must have a unique name.")

    detect_cycles(settings_path)
    dependency_results = resolve_dependencies(...)
```

A regression test should assert that `resolve_dependencies()` is never called when duplicate names are present.

## Impact

A misconfigured parent pipeline can launch multiple dependency runs, write audit trails, and mutate downstream systems, then fail only after those side effects complete. That breaks the preflight contract, creates avoidable external mutations, and makes the parent run fail for a config error that should have been rejected before any work started.
---
## Summary

Duplicate collection-probe results silently overwrite each other in the preflight gate context, so `resolve_preflight()` can drop earlier probe evidence and evaluate gates against incomplete collection state.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/engine/bootstrap.py
- Line(s): 87-95
- Function/Method: `resolve_preflight`

## Evidence

`resolve_preflight()` collapses probe results into a dict keyed only by `result.collection`:

```python
# /home/john/elspeth/src/elspeth/engine/bootstrap.py:87-95
probe_results = {}
for probe in probes:
    result = probe.probe()
    probe_results[result.collection] = {
        "reachable": result.reachable,
        "count": result.count,
    }
```

That assignment overwrites any earlier entry for the same collection without warning.

Nothing upstream enforces uniqueness of probe collections. `CollectionProbeConfig` only validates presence and shape:

```python
# /home/john/elspeth/src/elspeth/core/dependency_config.py:32-42
class CollectionProbeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str = Field(min_length=1, description="Collection name to probe")
    provider: str = Field(min_length=1, description="Provider type (e.g., 'chroma')")
    provider_config: Mapping[str, Any] = Field(default_factory=dict, ...)
```

And probe construction just appends every config entry:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/probe_factory.py:100-109
def build_collection_probes(configs: list[CollectionProbeConfig]) -> list[CollectionProbe]:
    probes: list[CollectionProbe] = []
    for config in configs:
        ...
        probes.append(probe_cls(config.collection, config.provider_config))
    return probes
```

Existing tests cover multiple probes only when the collection names are distinct:

```python
# /home/john/elspeth/tests/unit/plugins/infrastructure/test_probe_factory.py:42-58
def test_multiple_probes(self) -> None:
    configs = [
        CollectionProbeConfig(collection="alpha", ...),
        CollectionProbeConfig(collection="bravo", ...),
    ]
    probes = build_collection_probes(configs)
    assert len(probes) == 2
```

There is no duplicate-collection regression test.

## Root Cause Hypothesis

The gate context was modeled as `{collection_name: {reachable, count}}`, but `resolve_preflight()` assumes collection names are unique without enforcing that invariant. Because the code materializes the context via plain dict assignment, duplicate probe declarations cause silent last-write-wins behavior instead of an explicit configuration error.

## Suggested Fix

Validate probe collection-name uniqueness before executing probes, and fail fast on duplicates. If duplicate probe declarations are ever meant to be supported, the context shape must change to preserve all results rather than collapsing to one dict entry.

Example fast-fail guard:

```python
probe_names = [probe.collection_name for probe in probes]
seen: set[str] = set()
duplicates: list[str] = []
for name in probe_names:
    if name in seen:
        duplicates.append(name)
    seen.add(name)
if duplicates:
    raise ValueError(f"Duplicate collection probes: {duplicates}. Each collection_probes entry must target a unique collection.")
```

A regression test should verify that duplicate probe collections raise before any `probe.probe()` calls occur.

## Impact

Earlier probe results disappear from the preflight context and from any later gate audit snapshot. A gate can therefore pass or fail based solely on whichever duplicate probe happened to run last, while operators have no indication that conflicting probe evidence was discarded. That is silent data loss at the preflight boundary.
