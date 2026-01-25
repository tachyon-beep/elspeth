# Duplicate Bug Report Cleanup Log

Generated: 2026-01-22

This log documents the cleanup of duplicate generated bug reports based on the analysis in `DUPLICATES.md`.

## Summary

- **Total duplicate reports identified**: 12
- **Files deleted entirely**: 5 (8 duplicate reports)
- **Files retained with partial duplicates**: 3 (4 duplicate reports remain in mixed-content files)
- **Approach**: Conservative - only deleted files where ALL reports were duplicates

---

## Files Deleted

These files were deleted because ALL bug reports within them were exact duplicates of existing bugs in the main bug database.

### 1. `elspeth/contracts/config.py.md`

**Deleted:** Yes (entire file)

| Report # | Duplicate Title | Existing Bug |
|----------|----------------|--------------|
| #0 | contracts/config.py imports core.config (contracts not leaf) | `docs/bugs/open/P2-2026-01-20-contracts-config-reexport-breaks-leaf-boundary.md` |

---

### 2. `elspeth/core/landscape/exporter.py.md`

**Deleted:** Yes (entire file - all 3 reports were duplicates)

| Report # | Duplicate Title | Existing Bug |
|----------|----------------|--------------|
| #0 | Token export omits expand_group_id | `docs/bugs/open/P2-2026-01-19-exporter-missing-expand-group-id.md` |
| #1 | Export omits run/node configuration and determinism metadata | `docs/bugs/pending/P2-2026-01-19-exporter-missing-config-in-export.md` |
| #2 | Exporter uses N+1 query pattern across row/token/state hierarchy | `docs/bugs/pending/P2-2026-01-19-exporter-n-plus-one-queries.md` |

---

### 3. `elspeth/core/landscape/models.py.md`

**Deleted:** Yes (entire file)

| Report # | Duplicate Title | Existing Bug |
|----------|----------------|--------------|
| #0 | Landscape models drift from contracts/schema | `docs/bugs/open/P3-2026-01-19-landscape-models-duplication-drift.md` |

---

### 4. `elspeth/core/landscape/schema.py.md`

**Deleted:** Yes (entire file)

| Report # | Duplicate Title | Existing Bug |
|----------|----------------|--------------|
| #0 | Error tables lack foreign keys for node/token references | `docs/bugs/open/P2-2026-01-19-error-tables-missing-foreign-keys.md` |

---

### 5. `elspeth/core/payload_store.py.md`

**Deleted:** Yes (entire file - both reports were duplicates of the same existing bug)

| Report # | Duplicate Title | Existing Bug |
|----------|----------------|--------------|
| #0 | Unvalidated content_hash allows path traversal outside base_path | `docs/bugs/closed/P1-2026-01-19-payload-store-integrity-and-hash-validation-missing.md` |
| #1 | store() skips integrity verification for existing blobs | `docs/bugs/closed/P1-2026-01-19-payload-store-integrity-and-hash-validation-missing.md` |

**Note:** Both reports reference a **closed** bug. This suggests either:
- The generated reports were based on code before the fix was applied
- The fix addressed different aspects than what the reports describe
- Recommend verification that the closed bug fix addresses both path traversal and integrity verification concerns

---

## Files NOT Deleted (Mixed Content)

These files contain BOTH duplicate reports AND novel bugs. To be conservative, the entire file was retained. The duplicate sections should be manually reviewed and removed if desired.

### 1. `elspeth/cli.py.md`

**Deleted:** No (contains novel bugs)

| Report # | Status | Title | Notes |
|----------|--------|-------|-------|
| #0 | DUPLICATE | run validates one graph but executes another | Duplicate of `docs/bugs/open/P2-2026-01-20-cli-run-rebuilds-unvalidated-graph.md` |
| #1 | NOVEL | resume uses new aggregation node IDs that don't match stored graph | P1 - requires review |
| #2 | NOVEL | resume forces `mode=append` on all sinks, breaking JSON/Database sinks | P2 - requires review |

**Recommendation:** Manually remove Report #0 from this file, or promote Reports #1 and #2 to the main bug database and then delete the file.

---

### 2. `elspeth/core/dag.py.md`

**Deleted:** No (contains novel bugs)

| Report # | Status | Title | Notes |
|----------|--------|-------|-------|
| #0 | DUPLICATE | Plugin gate routes missing in ExecutionGraph.from_config | Duplicate of `docs/bugs/pending/P2-2026-01-19-plugin-gate-graph-mismatch.md` |
| #1 | NOVEL | Duplicate coalesce branch names silently overwritten in DAG mapping | P2 - requires review |

**Recommendation:** Manually remove Report #0 from this file, or promote Report #1 to the main bug database and then delete the file.

---

### 3. `elspeth/core/rate_limit/limiter.py.md`

**Deleted:** No (contains novel bugs)

| Report # | Status | Title | Notes |
|----------|--------|-------|-------|
| #0 | DUPLICATE | RateLimiter.acquire() not locked/atomic across multi-rate limiters | Duplicate of `docs/bugs/open/P2-2026-01-19-rate-limiter-acquire-not-thread-safe-or-atomic.md` |
| #1 | DUPLICATE | Rate limiter suppression set retains stale thread idents | Duplicate of `docs/bugs/open/P2-2026-01-19-rate-limiter-suppression-thread-ident-stale.md` |
| #2 | NOVEL | try_acquire uses stale bucket counts and over-throttles | P2 - requires review |

**Recommendation:** Manually remove Reports #0 and #1 from this file, or promote Report #2 to the main bug database and then delete the file.

---

## Verification Notes

All existing bugs referenced by the duplicates were verified to exist:

| Existing Bug Path | Status | Verified |
|-------------------|--------|----------|
| `docs/bugs/open/P2-2026-01-20-cli-run-rebuilds-unvalidated-graph.md` | open | Yes |
| `docs/bugs/open/P2-2026-01-20-contracts-config-reexport-breaks-leaf-boundary.md` | open | Yes |
| `docs/bugs/pending/P2-2026-01-19-plugin-gate-graph-mismatch.md` | pending | Yes |
| `docs/bugs/open/P2-2026-01-19-exporter-missing-expand-group-id.md` | open | Yes |
| `docs/bugs/pending/P2-2026-01-19-exporter-missing-config-in-export.md` | pending | Yes |
| `docs/bugs/pending/P2-2026-01-19-exporter-n-plus-one-queries.md` | pending | Yes |
| `docs/bugs/open/P3-2026-01-19-landscape-models-duplication-drift.md` | open | Yes |
| `docs/bugs/open/P2-2026-01-19-error-tables-missing-foreign-keys.md` | open | Yes |
| `docs/bugs/closed/P1-2026-01-19-payload-store-integrity-and-hash-validation-missing.md` | closed | Yes |
| `docs/bugs/open/P2-2026-01-19-rate-limiter-acquire-not-thread-safe-or-atomic.md` | open | Yes |
| `docs/bugs/open/P2-2026-01-19-rate-limiter-suppression-thread-ident-stale.md` | open | Yes |

---

## Next Steps

1. **Review novel bugs in mixed-content files**: The 3 files retained contain 4 novel bugs that should be reviewed for promotion to the main bug database.

2. **Re-verify closed payload store bug**: The payload_store.py duplicates reference a closed bug - verify the fix addresses both path traversal and integrity verification.

3. **Update DUPLICATES.md counts**: The summary statistics in DUPLICATES.md should be updated to reflect the cleanup.
