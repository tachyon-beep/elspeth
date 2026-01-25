# High Priority Bug Index (P0-P1)

Generated: 2026-01-22

This index lists all P0 and P1 novel bugs extracted from the generated bug reports and formatted according to the standard bug report template.

## Summary

| Priority | Count | Status |
|----------|-------|--------|
| P0 | 1 | Novel - requires immediate attention |
| P1 | 8 | Novel - high priority fixes needed |

**Total: 9 high-priority bugs processed**

---

## P0 Bugs (Critical - Immediate Action Required)

### 1. Source Row Payloads Never Persisted

| Field | Value |
|-------|-------|
| **File** | `P0-2026-01-22-source-row-payloads-never-persisted.md` |
| **Component** | core/landscape/row_data |
| **Severity** | Critical |
| **Summary** | Source row payloads are not persisted during normal runs, violating the non-negotiable audit requirement to store raw source data. |
| **Impact** | Audit trail incomplete; resume fails; explain cannot retrieve source data |
| **Recommendation** | **Move to `docs/bugs/open/`** - This is a fundamental audit integrity violation |

---

## P1 Bugs (High Priority)

### 1. Recovery Skips Rows for Sinks Written Later

| Field | Value |
|-------|-------|
| **File** | `P1-2026-01-22-recovery-skips-rows-multi-sink.md` |
| **Component** | core/checkpoint/recovery |
| **Severity** | Critical |
| **Summary** | Multi-sink recovery uses wrong row_index boundary, causing rows routed to failed sinks to be skipped on resume. |
| **Impact** | Resume completes with missing sink outputs; audit trail inconsistent |
| **Recommendation** | **Move to `docs/bugs/open/`** - Affects resume reliability |

### 2. ArtifactDescriptor Leaks Secrets via Raw URLs

| Field | Value |
|-------|-------|
| **File** | `P1-2026-01-22-artifact-descriptor-leaks-secrets.md` |
| **Component** | contracts/results |
| **Severity** | Critical |
| **Summary** | Database/webhook artifact descriptors embed raw credentialed URLs into audit trail. |
| **Impact** | High-risk secret leakage into audit trail, exports, and TUI |
| **Recommendation** | **Move to `docs/bugs/open/`** - Security vulnerability |

### 3. Duplicate Config Gate Names Overwrite Node Mapping

| Field | Value |
|-------|-------|
| **File** | `P1-2026-01-22-duplicate-gate-names-overwrite-mapping.md` |
| **Component** | core/config |
| **Severity** | Major |
| **Summary** | Duplicate gate names are accepted but overwrite node mappings, corrupting routing and audit attribution. |
| **Impact** | Unpredictable gate routing; audit trail misattribution |
| **Recommendation** | **Move to `docs/bugs/open/`** - Config validation gap |

### 4. Duplicate Fork/Coalesce Branch Names Break Merge Semantics

| Field | Value |
|-------|-------|
| **File** | `P1-2026-01-22-duplicate-branch-names-break-coalesce.md` |
| **Component** | core/config |
| **Severity** | Major |
| **Summary** | Duplicate branch names in fork_to/coalesce.branches cause token overwrites and stalled merges. |
| **Impact** | Pipelines hang at coalesce; silent loss of branch results |
| **Related** | `docs/bugs/open/P2-2026-01-22-coalesce-duplicate-branch-overwrite.md` (runtime manifestation) |
| **Recommendation** | **Move to `docs/bugs/open/`** - Config validation gap |

### 5. explain(row_id) Returns Arbitrary Token When Multiple Tokens Exist

| Field | Value |
|-------|-------|
| **File** | `P1-2026-01-22-explain-returns-arbitrary-token.md` |
| **Component** | core/landscape/lineage |
| **Severity** | Major |
| **Summary** | `explain()` picks first token arbitrarily when multiple tokens exist for a row, returning incomplete/wrong lineage. |
| **Impact** | Misleading audit explanations for forked/expanded rows |
| **Recommendation** | **Move to `docs/bugs/open/`** - Audit accuracy issue |

### 6. RunRepository Masks Invalid export_status Values

| Field | Value |
|-------|-------|
| **File** | `P1-2026-01-22-run-repository-masks-invalid-export-status.md` |
| **Component** | core/landscape/repositories |
| **Severity** | Major |
| **Summary** | Falsy but invalid export_status values are silently converted to None instead of crashing. |
| **Impact** | Violates Tier 1 crash-on-anomaly rule; masks audit DB corruption |
| **Recommendation** | **Move to `docs/bugs/open/`** - Audit integrity violation |

### 7. Reproducibility Grade Not Updated After Payload Purge

| Field | Value |
|-------|-------|
| **File** | `P1-2026-01-22-reproducibility-grade-not-updated-after-purge.md` |
| **Component** | core/retention/purge |
| **Severity** | Major |
| **Summary** | Purging payloads does not downgrade reproducibility_grade, overstating replay capability. |
| **Impact** | Audit metadata misrepresents reproducibility state |
| **Recommendation** | **Move to `docs/bugs/open/`** - Audit metadata integrity |

### 8. Decimal NaN/Infinity Bypass Non-Finite Rejection

| Field | Value |
|-------|-------|
| **File** | `P1-2026-01-22-decimal-nan-infinity-bypass-rejection.md` |
| **Component** | core/canonical |
| **Severity** | Major |
| **Summary** | `Decimal("NaN")` and `Decimal("Infinity")` are converted to strings instead of raising, violating canonicalization policy. |
| **Impact** | Non-finite values enter audit hashes; masks invalid data states |
| **Recommendation** | **Move to `docs/bugs/open/`** - Canonicalization policy violation |

---

## Bugs NOT Included (Already Exist or Duplicates)

The following P1 bugs from the generated reports were identified as duplicates of existing closed bugs and were **not** processed:

### Payload Store Issues (Closed Bug Re-manifestation)

Both of these reference `docs/bugs/closed/P1-2026-01-19-payload-store-integrity-and-hash-validation-missing.md`:

1. **Unvalidated content_hash allows path traversal** - May indicate incomplete fix
2. **store() skips integrity verification for existing blobs** - May indicate incomplete fix

**Recommendation**: Review the closed bug fix to verify these issues were fully addressed. If not, reopen with updated scope.

---

## Recommendations by Target Directory

### Immediate Move to `docs/bugs/open/` (9 bugs)

All formatted bugs should be moved to `docs/bugs/open/` as they are novel, verified through static analysis, and have clear reproduction paths:

```bash
# Move all formatted high-priority bugs to open/
cp docs/bugs/generated/formatted/high_priority/*.md docs/bugs/open/
```

### Review Closed Bugs

The payload store closed bug (`P1-2026-01-19-payload-store-integrity-and-hash-validation-missing.md`) should be reviewed to determine if:

1. The fix was incomplete
2. New edge cases emerged
3. The bug should be reopened with expanded scope

---

## Cross-References to Existing Bugs

| New Bug | Related Existing Bug |
|---------|---------------------|
| Duplicate branch names break coalesce | `P2-2026-01-22-coalesce-duplicate-branch-overwrite.md` (open) |
| Payload store path traversal | `P1-2026-01-19-payload-store-integrity-and-hash-validation-missing.md` (closed) |

---

## File Manifest

```
docs/bugs/generated/formatted/high_priority/
├── HIGH_PRIORITY_INDEX.md (this file)
├── P0-2026-01-22-source-row-payloads-never-persisted.md
├── P1-2026-01-22-recovery-skips-rows-multi-sink.md
├── P1-2026-01-22-artifact-descriptor-leaks-secrets.md
├── P1-2026-01-22-duplicate-gate-names-overwrite-mapping.md
├── P1-2026-01-22-duplicate-branch-names-break-coalesce.md
├── P1-2026-01-22-explain-returns-arbitrary-token.md
├── P1-2026-01-22-run-repository-masks-invalid-export-status.md
├── P1-2026-01-22-reproducibility-grade-not-updated-after-purge.md
└── P1-2026-01-22-decimal-nan-infinity-bypass-rejection.md
```

---

## Next Steps

1. **Review each bug** for accuracy and completeness
2. **Move to `docs/bugs/open/`** after review
3. **Prioritize fixes** based on impact assessment:
   - P0 bug (source payloads) is most critical
   - Security bug (secret leakage) should be addressed early
   - Config validation bugs (duplicates) are straightforward fixes
4. **Add to sprint/backlog** for RC-1 release
5. **Review closed payload store bug** for potential reopening
