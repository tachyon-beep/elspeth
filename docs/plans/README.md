# ELSPETH Implementation Plans

This directory tracks active implementation plans. Completed, superseded, and cancelled plans have been removed from the working tree (preserved in git history).

## Active Plans

### Essential

| Plan | Description | Status |
|------|-------------|--------|
| `RC4-initiation.md` | RC4 scope — last maintenance release before feature work | Active |
| `ARCH-15-design.md` | Per-branch fork transforms architecture (reviewed, ready for implementation) | Approved |

### High Value

| Plan | Description | Status |
|------|-------------|--------|
| `2026-02-01-nodeinfo-typed-config.md` | Type NodeInfo.config with discriminated union (big refactor, schedule before Engine API) | Queued |
| `2026-02-02-whitelist-reduction.md` | Tier model whitelist reduction (488 entries expire 2026-05-02) | Phase 1.1 done |

### Nice to Have

| Plan | Description | Status |
|------|-------------|--------|
| `2026-02-13-contract-propagation-complex-fields.md` | Preserve dict/list fields in propagated contracts as `python_type=object` | Queued |
| `2026-02-13-documentation-audit-report.md` | Documentation freshness and cross-reference audit (errors fixed, gaps remain) | Reference |

### LLM Consolidation (Future)

| Plan | Description | Status |
|------|-------------|--------|
| `2026-02-25-llm-plugin-consolidation.md` | Collapse 6 LLM classes into Strategy pattern — approved design | Approved |
| `05-quality-assessment-t10-llm-consolidation.md` | Architecture quality review of LLM consolidation design | Reference |

### Architecture Reference

| Plan | Description | Status |
|------|-------------|--------|
| `2026-02-26-t17-plugincontext-protocol-split-design.md` | PluginContext protocol split design (referenced from `contracts/contexts.py`) | Implemented — kept as architecture doc |

## Historical Plans (Git History)

179+ completed plans and 18+ superseded plans were removed from this directory (148 on 2026-02-14, 31 on 2026-03-07). To recover any historical plan:

```bash
# Find a specific plan by name
git log --all --diff-filter=D -- "docs/plans/*field-collision*"

# Restore a deleted plan
git show <commit>:docs/plans/<filename>.md
```

## Plan Lifecycle

```
Created → In Progress → Completed (deleted from tree, kept in git)
                      → Superseded (deleted from tree, kept in git)
```
