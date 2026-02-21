## Summary

`MultiQueryConfig` fails to detect cross-product `output_prefix` collisions (from delimiter ambiguity), allowing distinct queries to write to identical output keys and silently overwrite each other.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1: requires adversarial naming with embedded underscores; unlikely in practice)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/multi_query.py`
- Line(s): 191-255, 349-360
- Function/Method: `validate_multi_query_key_collisions`, `expand_queries`

## Evidence

`output_prefix` is generated as a simple concatenation with `_`:

```python
# src/elspeth/plugins/llm/multi_query.py:355
output_prefix=f"{case_study.name}_{criterion.name}"
```

But collision validation only checks:
- duplicate case study names (`multi_query.py:212-217`)
- duplicate criterion names (`multi_query.py:219-224`)
- duplicate `output_mapping` suffixes (`multi_query.py:225-239`)
- reserved suffix conflicts (`multi_query.py:241-254`)

There is **no check** that generated cross-product prefixes are unique.

This allows valid config values that create duplicate prefixes, e.g.:
- `(case_study="a_b", criterion="c") -> "a_b_c"`
- `(case_study="a", criterion="b_c") -> "a_b_c"`

I verified this is accepted by `MultiQueryConfig.from_dict(...)` and yields duplicate prefixes (`a_b_c` appears twice).

Downstream, duplicate keys are overwritten silently:
- query outputs are keyed by `f"{spec.output_prefix}_{field_config.suffix}"` in provider transforms (`src/elspeth/plugins/llm/azure_multi_query.py:320`, `src/elspeth/plugins/llm/openrouter_multi_query.py:376`)
- row merge uses `dict.update(...)` (`src/elspeth/plugins/llm/base_multi_query.py:349-351`), so later query values replace earlier ones with no error.

This is silent data loss and breaks audit attribution for one of the colliding queries.

## Root Cause Hypothesis

A prior collision fix focused on obvious duplicates (names/suffixes/reserved suffixes) but missed delimiter-ambiguity collisions in the generated composite key (`case_study + "_" + criterion`). The validator reasoned about inputs separately, not about the actual emitted field namespace.

## Suggested Fix

In `validate_multi_query_key_collisions(...)`, explicitly validate uniqueness of generated prefixes across the full cross-product before runtime:

```python
prefix_to_pairs: dict[str, list[tuple[str, str]]] = {}
for cs in case_studies:
    for crit in criteria:
        prefix = f"{cs.name}_{crit.name}"
        prefix_to_pairs.setdefault(prefix, []).append((cs.name, crit.name))

collisions = {p: pairs for p, pairs in prefix_to_pairs.items() if len(pairs) > 1}
if collisions:
    raise ValueError(...)
```

Also add a regression test in `tests/unit/plugins/llm/test_multi_query.py` for ambiguous underscore names (`a_b`/`c` vs `a`/`b_c`) expecting config validation failure.

## Impact

Distinct LLM query results (including `_usage`, `_model`, and audit metadata fields) can be overwritten in-row without any error. That causes silent loss of one query's evidence and breaks the "every decision traceable" auditability guarantee for affected rows.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/multi_query.py.md`
- Finding index in source report: 1
- Beads: pending
