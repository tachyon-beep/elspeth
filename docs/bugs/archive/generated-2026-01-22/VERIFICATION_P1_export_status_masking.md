# Bug Verification Report: RunRepository Masks Invalid export_status Values

## Status: VERIFIED

**Bug ID:** P1-export-status-masking
**Claimed Location:** `src/elspeth/core/landscape/repositories.py` (Bug #1)
**Verification Date:** 2026-01-22
**Verifier:** Claude Code

---

## Summary of Bug Claim

The bug report claims that `RunRepository.load()` treats falsy `export_status` values as `None`, so invalid values like `""` (empty string) bypass `ExportStatus` coercion and don't crash, masking Tier 1 data corruption.

## Code Analysis

### 1. RunRepository.load() Implementation (repositories.py:41-60)

```python
# From repositories.py:41-60
def load(self, row: Any) -> Run:
    """Load Run from database row.

    Converts string fields to enums. Crashes on invalid data.
    """
    return Run(
        run_id=row.run_id,
        started_at=row.started_at,
        config_hash=row.config_hash,
        settings_json=row.settings_json,
        canonical_version=row.canonical_version,
        status=RunStatus(row.status),  # Convert HERE
        completed_at=row.completed_at,
        reproducibility_grade=row.reproducibility_grade,
        export_status=ExportStatus(row.export_status) if row.export_status else None,  # <-- BUG
        export_error=row.export_error,
        exported_at=row.exported_at,
        export_format=row.export_format,
        export_sink=row.export_sink,
    )
```

**The bug is at line 55:**
```python
export_status=ExportStatus(row.export_status) if row.export_status else None
```

### 2. Python Truthiness Analysis

The condition `if row.export_status` evaluates using Python's truthiness rules:

| Value | Truthiness | Expected Behavior | Actual Behavior |
|-------|------------|-------------------|-----------------|
| `None` | Falsy | Return `None` | Returns `None` |
| `""` (empty string) | Falsy | **CRASH** (invalid enum) | Returns `None` |
| `"pending"` | Truthy | Return `ExportStatus.PENDING` | Works correctly |
| `"invalid"` | Truthy | **CRASH** (invalid enum) | Crashes correctly |
| `0` | Falsy | **CRASH** (invalid type) | Returns `None` |
| `False` | Falsy | **CRASH** (invalid type) | Returns `None` |

### 3. ExportStatus Enum Definition (enums.py:33-41)

```python
# From enums.py:33-41
class ExportStatus(str, Enum):
    """Status of run export operation.

    Uses (str, Enum) for database serialization.
    """

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
```

Valid values are: `"pending"`, `"completed"`, `"failed"`, or `None` (not exported yet).

An empty string `""` is **NOT** a valid `ExportStatus` value.

### 4. Tier 1 Trust Model (CLAUDE.md)

Per the Data Manifesto:

> **Tier 1: Our Data (Audit Database / Landscape) - FULL TRUST**
>
> Bad data in the audit trail = **crash immediately**
> No coercion, no defaults, no silent recovery

The current code violates this by silently converting invalid falsy values to `None`.

### 5. Correct Pattern Comparison

Looking at how `status` is handled on line 52:

```python
status=RunStatus(row.status),  # Convert HERE - no guard, crashes on invalid
```

This is the **correct** pattern for Tier 1 data: direct enum coercion that crashes on invalid values.

The `export_status` handling should be:

```python
export_status=ExportStatus(row.export_status) if row.export_status is not None else None,
```

Using `is not None` instead of truthiness check ensures:
- `None` -> `None` (legitimate)
- `""` -> `ExportStatus("")` -> `ValueError` -> **CRASH** (correct for Tier 1)
- `"invalid"` -> `ExportStatus("invalid")` -> `ValueError` -> **CRASH**

## Reproduction Scenario

**Database corruption:**

Suppose the audit database has a corrupted row:
```sql
UPDATE runs SET export_status = '' WHERE run_id = 'run_001';
```

**Query with current code:**

```python
row = db.query(runs_table).where(run_id == "run_001").first()
run = RunRepository(session).load(row)

# Expected: ValueError("'' is not a valid ExportStatus")
# Actual: run.export_status == None

# Now downstream code thinks "export never happened"
# when actually export_status was CORRUPTED to empty string
```

**Consequences:**

1. Operator checks export status: sees "not exported" (None)
2. Operator triggers re-export
3. Data may be duplicated or export fails in unexpected ways
4. Actual corruption is never detected or investigated

## Evidence Summary

| Location | Finding |
|----------|---------|
| `repositories.py:55` | `if row.export_status else None` uses truthiness |
| `repositories.py:52` | `RunStatus(row.status)` uses correct pattern (no guard) |
| `enums.py:33-41` | `ExportStatus` has only `pending`, `completed`, `failed` |
| `CLAUDE.md:40` | Tier 1 rule: "Bad data = crash immediately" |
| `CLAUDE.md:42` | "No coercion, no defaults, no silent recovery" |

## Impact Assessment

| Factor | Assessment |
|--------|------------|
| **Severity** | Major - Violates Tier 1 crash-on-anomaly |
| **Frequency** | Low - Requires database corruption |
| **Detection** | Very Hard - Invalid values silently become None |
| **Consequence** | Corrupted audit data passes validation |

## CLAUDE.md Alignment

This directly violates the Data Manifesto's Tier 1 rules:

> If we read garbage from our own database, something catastrophic happened (bug in our code, database corruption, tampering)

The current code silently accepts garbage (`""`) and treats it as valid (`None`), hiding potential:
- Database corruption
- Code bugs that wrote invalid values
- Evidence tampering

---

## Conclusion

**VERIFIED:** The bug is accurate. The `RunRepository.load()` method:

1. **Uses truthiness check** instead of explicit `is not None` comparison
2. **Silently converts invalid falsy values** (`""`, `0`, `False`) to `None`
3. **Violates Tier 1 crash-on-anomaly** principle for audit database
4. **Can mask database corruption** or evidence tampering

**The fix is simple:**

Change line 55 from:
```python
export_status=ExportStatus(row.export_status) if row.export_status else None,
```

To:
```python
export_status=ExportStatus(row.export_status) if row.export_status is not None else None,
```

This ensures:
- `None` is still correctly handled as `None`
- Any non-None invalid value causes `ValueError` during enum coercion
- Tier 1 crash-on-anomaly is maintained
