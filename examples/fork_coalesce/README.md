# Fork/Coalesce Example

Demonstrates the fork/join DAG pattern where a single row is duplicated into parallel tokens, processed independently, and merged back together.

## What This Shows

After pre-processing (truncating long descriptions), every row is forked into two parallel tokens. Both tokens traverse to a coalesce point that waits for both to arrive, then merges them using the `nested` strategy — the output contains each branch's data under a separate key.

```
source ─(raw)─> truncate ─(preprocessed)─> [fork_gate] ─┬─ path_a ─┐
                                                          └─ path_b ─┤
                                                                     ├─ [merge_results]
                                                           (merged) ─> [route_output] ─> output
```

## Running

```bash
elspeth run --settings examples/fork_coalesce/settings.yaml --execute
```

## Output

Results appear in `output/merged_results.json` (JSONL). With the `nested` merge strategy, each output row looks like:

```json
{
  "path_a": {"id": 1, "product": "Widget Pro", "price": 2500, "category": "electronics", "description": "High-performance widget with advan..."},
  "path_b": {"id": 1, "product": "Widget Pro", "price": 2500, "category": "electronics", "description": "High-performance widget with advan..."}
}
```

## Why Fork/Coalesce?

In this minimal example both paths carry the same data. The real power emerges in production pipelines where each fork path hits a **different external service**:

| Scenario | Fork Paths | Merge Policy |
|----------|-----------|-------------|
| **LLM redundancy** | 3 different models | `quorum` (2-of-3 agree) |
| **Multi-API enrichment** | Sentiment API + Entity API | `require_all` + `union` |
| **Fastest wins** | Fast model + Accurate model | `first` |
| **Best effort** | Primary + Fallback | `best_effort` with timeout |

## Merge Policies

| Policy | Behaviour |
|--------|-----------|
| `require_all` | Wait for all branches — fail if any missing |
| `quorum` | Wait for N-of-M branches (`quorum_count: 2`) |
| `best_effort` | Merge when timeout expires or all branches arrive |
| `first` | Merge immediately when first branch arrives |

## Merge Strategies

| Strategy | Result Shape |
|----------|-------------|
| `union` | `{field_a: val_a, field_b: val_b, ...}` — flat merge (last branch wins on collisions) |
| `nested` | `{path_a: {...}, path_b: {...}}` — branch-keyed (used in this example) |
| `select` | `{...}` from one chosen branch (`select_branch: path_a`) |

## Key Concepts

- **Fork gate**: `routes: {true: fork}` with `fork_to: [path_a, path_b]` duplicates each row
- **Token lineage**: Each forked token gets its own `token_id` with parent recorded for audit
- **Pre-fork transforms**: Shared processing (like truncation) happens before the fork
- **Post-coalesce routing**: The coalesce name (`merge_results`) becomes a connection for downstream gates
- **Terminal state**: Parent tokens are marked `FORKED`; merged tokens are `COALESCED`

## See Also

- [`deep_routing`](../deep_routing/) — Complex gate cascades (fan-out to sinks, no merge)
- [`explicit_routing`](../explicit_routing/) — Basic wiring model
