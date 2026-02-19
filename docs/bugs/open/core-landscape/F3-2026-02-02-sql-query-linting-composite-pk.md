## Summary

Create AST-based linter that detects incorrect join patterns in SQLAlchemy queries on the `nodes` table (composite PK of `node_id, run_id`).

## Severity

- Severity: low
- Priority: P3
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-gjd

## Context

From architecture analysis (P2-04). Composite PK queries on `nodes` table are error-prone. Automated linting would prevent future bugs.

## Detection Rules

1. **WARN**: Join on `nodes` table using only `node_id`
2. **OK**: Join on `nodes` using both `node_id` AND `run_id`
3. **OK**: Direct filter on `node_states.run_id`

## Recommended Implementation: AST Script

```python
# scripts/check_composite_pk.py
def check_file(path: Path) -> list[Warning]:
    """Find SQLAlchemy joins on nodes without run_id."""
    tree = ast.parse(path.read_text())
    # Look for .join(nodes_table, ...) patterns
    # Verify run_id in join condition
```

## Files to Lint

- `src/elspeth/core/landscape/*.py`
- `src/elspeth/mcp/*.py`

## Acceptance Criteria

- [ ] Linter script created
- [ ] Detects known bad patterns
- [ ] Added to CI (scripts/ or pre-commit)
- [ ] Documentation in CLAUDE.md updated

## Blocked By

- `w2q7` — ELSPETH-NEXT (deferred to post-RC3)
