## Summary

`PromptTemplate` allows in-template mutation of shared context (`lookup` and raw `row`), which causes audit hash drift and cross-row state bleed.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/templates.py`
- Line(s): 107-110, 113-116, 170-177, 209-217
- Function/Method: `PromptTemplate.__init__`, `PromptTemplate.render`, `PromptTemplate.render_with_metadata`

## Evidence

`lookup` is hashed once at init, then the same mutable object is reused for all renders:

```python
# templates.py
107: lookup_snapshot = deepcopy(lookup_data) if lookup_data is not None else None
108: self._lookup_data = lookup_snapshot if lookup_snapshot is not None else {}
110: self._lookup_hash = _sha256(canonical_json(lookup_snapshot)) if lookup_snapshot is not None else None
...
113: self._env = SandboxedEnvironment(...)
...
176: "lookup": self._lookup_data,
```

`SandboxedEnvironment` permits mutating methods like `dict.update`, so template code can mutate `lookup` during render. Repro (executed in repo):

```python
t = PromptTemplate("{{ lookup.k }}{% set _ = lookup.update({'k': 'changed'}) %}", lookup_data={'k':'orig'})
r1 = t.render_with_metadata({'x':1}).prompt   # "orig"
r2 = t.render_with_metadata({'x':1}).prompt   # "changed"
# t.lookup_hash remains hash of {'k':'orig'}
```

Also, when `contract` is `None`, raw dict row is passed through:

```python
170-171: row_context = row
```

and `variables_hash` is computed **after** rendering:

```python
209: prompt = self.render(row, contract=contract)
217: variables_hash = _sha256(canonical_json(row_for_hash))
```

So template-side row mutation can make `variables_hash` describe mutated state, not the values that produced the prompt. Repro:

```python
t = PromptTemplate("{{ row.x }}{% set _ = row.update({'x': 2}) %}")
row = {'x': 1}
result = t.render_with_metadata(row)
# prompt == "1", but row mutated to {'x': 2}, and variables_hash == hash({'x': 2})
```

Concurrency amplifies this: LLM transforms call `self._template.render_with_metadata(...)` from worker threads (`src/elspeth/plugins/llm/openrouter.py:492-510`, `src/elspeth/plugins/llm/azure.py:403-421`) via `ThreadPoolExecutor` (`src/elspeth/plugins/batching/mixin.py:160-218`), so shared mutable `lookup` introduces racey nondeterminism.

## Root Cause Hypothesis

The template sandbox is configured for safety against dangerous attribute access, but not immutability. Combined with sharing `self._lookup_data` across renders and hashing metadata outside a mutation-safe boundary, template code can alter runtime state that audit hashes assume is fixed.

## Suggested Fix

1. Replace `SandboxedEnvironment` with `ImmutableSandboxedEnvironment` in `templates.py`.
2. Ensure render context is mutation-safe:
   - keep `lookup` immutable per render (or deep-copy per render), and
   - avoid passing mutable raw row dict directly (wrap/freeze even when `contract is None`).
3. Add regression tests:
   - template attempts `lookup.update(...)` must raise `TemplateError` (sandbox violation),
   - repeated renders must keep prompt/hash stable,
   - concurrent renders with same template must not affect each other.

## Impact

- Audit trail integrity break: `lookup_hash` can stop matching effective lookup content used after prior renders.
- Stateless-transform contract break: template execution can leak state across rows.
- Concurrency risk: pooled transforms can produce order/race-dependent prompts.
- Misleading provenance: `variables_hash` can reflect post-render mutated row state rather than render input.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/templates.py.md`
- Finding index in source report: 1
- Beads: pending
