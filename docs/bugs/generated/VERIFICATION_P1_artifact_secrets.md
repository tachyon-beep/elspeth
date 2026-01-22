# Bug Verification Report: ArtifactDescriptor Leaks Secrets via Raw URLs

**Bug ID:** P1-artifact-secrets
**Status:** VERIFIED
**Severity:** P1 - Critical
**Verification Date:** 2026-01-22

---

## Executive Summary

The bug claim is **VERIFIED**. The `ArtifactDescriptor.for_database()` and `for_webhook()` factory methods embed raw URLs directly into `path_or_uri`, which is then:

1. **Stored in the audit database** (`artifacts` table, `path_or_uri` column)
2. **Exposed via exports** (JSON and CSV export both include `path_or_uri`)
3. **Displayed in TUI** (node_detail widget shows `path_or_uri`)

This violates CLAUDE.md's Secret Handling requirement (line ~358) which mandates HMAC fingerprints instead of raw secret storage.

---

## Code Evidence

### 1. ArtifactDescriptor Factory Methods

**File:** `/home/john/elspeth-rapid/src/elspeth/contracts/results.py` (lines 224-256)

```python
@classmethod
def for_database(
    cls,
    url: str,              # <-- RAW URL (may contain password)
    table: str,
    content_hash: str,
    payload_size: int,
    row_count: int,
) -> "ArtifactDescriptor":
    """Create descriptor for database artifacts."""
    return cls(
        artifact_type="database",
        path_or_uri=f"db://{table}@{url}",  # <-- EMBEDS RAW URL
        content_hash=content_hash,
        size_bytes=payload_size,
        metadata={"table": table, "row_count": row_count},
    )

@classmethod
def for_webhook(
    cls,
    url: str,              # <-- RAW URL (may contain API token)
    content_hash: str,
    request_size: int,
    response_code: int,
) -> "ArtifactDescriptor":
    """Create descriptor for webhook artifacts."""
    return cls(
        artifact_type="webhook",
        path_or_uri=f"webhook://{url}",  # <-- EMBEDS RAW URL
        content_hash=content_hash,
        size_bytes=request_size,
        metadata={"response_code": response_code},
    )
```

### 2. DatabaseSink Usage (Confirmed Caller)

**File:** `/home/john/elspeth-rapid/src/elspeth/plugins/sinks/database_sink.py` (lines 204-233)

```python
def write(self, rows: list[dict[str, Any]], ctx: PluginContext) -> ArtifactDescriptor:
    # ...
    return ArtifactDescriptor.for_database(
        url=self._url,              # <-- FROM CONFIG (may contain credentials)
        table=self._table_name,
        content_hash=content_hash,
        payload_size=payload_size,
        row_count=len(rows),
    )
```

The `self._url` comes from `DatabaseSinkConfig.url` which is a standard SQLAlchemy connection string. These commonly contain credentials:

- `postgresql://user:password@host:5432/dbname`
- `mysql+pymysql://root:secret@localhost/mydb`

### 3. Audit Trail Storage (Confirmed Persistence)

**File:** `/home/john/elspeth-rapid/src/elspeth/core/landscape/recorder.py` (lines 1640-1654)

```python
with self._db.connection() as conn:
    conn.execute(
        artifacts_table.insert().values(
            # ...
            path_or_uri=artifact.path_or_uri,  # <-- STORED IN DB
            # ...
        )
    )
```

**File:** `/home/john/elspeth-rapid/src/elspeth/core/landscape/schema.py` (line 221)

```python
Column("path_or_uri", String(512), nullable=False),
```

### 4. Export Exposure (Confirmed Leak Path)

**File:** `/home/john/elspeth-rapid/src/elspeth/core/landscape/exporter.py` (lines 338-350)

```python
# Artifacts
for artifact in self._recorder.get_artifacts(run_id):
    yield {
        "record_type": "artifact",
        "run_id": run_id,
        "artifact_id": artifact.artifact_id,
        "sink_node_id": artifact.sink_node_id,
        "produced_by_state_id": artifact.produced_by_state_id,
        "artifact_type": artifact.artifact_type,
        "path_or_uri": artifact.path_or_uri,  # <-- EXPORTED
        "content_hash": artifact.content_hash,
        "size_bytes": artifact.size_bytes,
    }
```

### 5. TUI Display (Confirmed UI Leak)

**File:** `/home/john/elspeth-rapid/src/elspeth/tui/widgets/node_detail.py` (lines 119-130)

```python
artifact = self._state.get("artifact")
if artifact:
    lines.append("Artifact:")
    if isinstance(artifact, dict):
        artifact_id = artifact.get("artifact_id")
        path_or_uri = artifact.get("path_or_uri")  # <-- DISPLAYED
        content_hash = artifact.get("content_hash")
        lines.append(f"  ID:      {artifact_id or 'N/A'}")
        lines.append(f"  Path:    {path_or_uri or 'N/A'}")  # <-- USER SEES THIS
```

### 6. SinkExecutor Flow (Confirmed End-to-End)

**File:** `/home/john/elspeth-rapid/src/elspeth/engine/executors.py` (lines 1311-1335)

```python
# Complete all token states - status="completed" means they reached terminal
for token, state in states:
    sink_output = {
        "row": token.row_data,
        "artifact_path": artifact_info.path_or_uri,  # <-- ALSO IN node_state
        "content_hash": artifact_info.content_hash,
    }
    self._recorder.complete_node_state(
        state_id=state.state_id,
        status="completed",
        output_data=sink_output,  # <-- OUTPUT CONTAINS SECRET URL
        duration_ms=duration_ms,
    )

# Register artifact (linked to first state for audit lineage)
artifact = self._recorder.register_artifact(
    run_id=self._run_id,
    state_id=first_state.state_id,
    sink_node_id=sink_node_id,
    artifact_type=artifact_info.artifact_type,
    path=artifact_info.path_or_uri,  # <-- PERSISTED WITH RAW URL
    content_hash=artifact_info.content_hash,
    size_bytes=artifact_info.size_bytes,
)
```

---

## Existing Secret Handling (Not Used)

ELSPETH has proper secret fingerprinting infrastructure that is **not being used** by ArtifactDescriptor:

**File:** `/home/john/elspeth-rapid/src/elspeth/core/security/fingerprint.py`

```python
def secret_fingerprint(secret: str, *, key: bytes | None = None) -> str:
    """Compute HMAC-SHA256 fingerprint of a secret.

    The fingerprint can be stored in the audit trail to verify that
    the same secret was used across runs, without exposing the secret.
    """
    if key is None:
        key = get_fingerprint_key()

    digest = hmac.new(
        key=key,
        msg=secret.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    return digest
```

---

## CLAUDE.md Requirement Violation

**File:** `/home/john/elspeth-rapid/CLAUDE.md` (Secret Handling section)

> Never store secrets - use HMAC fingerprints:
> ```python
> fingerprint = hmac.new(fingerprint_key, secret.encode(), hashlib.sha256).hexdigest()
> ```

The current implementation stores raw URLs instead of fingerprints, directly violating this requirement.

---

## Exposure Risk Assessment

| Exposure Path | Risk Level | Details |
|---------------|------------|---------|
| **Audit Database** | HIGH | `artifacts.path_or_uri` column stores raw URLs permanently |
| **JSON Export** | HIGH | Export includes `path_or_uri` in artifact records |
| **CSV Export** | HIGH | Each artifact CSV row includes `path_or_uri` |
| **TUI Display** | MEDIUM | Node detail widget shows `Path:` with raw URL |
| **Node State Output** | HIGH | `output_data` includes `artifact_path` with raw URL |

---

## Impact Scenarios

1. **Database Credential Leak:** A pipeline writes to PostgreSQL using `postgresql://app_user:SuperSecret123@prod-db.internal:5432/app`. This password is now:
   - Stored in the audit database
   - Included in any exports
   - Visible in the TUI during debugging

2. **API Token Leak:** A webhook sink posts to `https://api.service.com/webhook?token=sk_live_abc123`. The API token is permanently recorded.

3. **Compliance Violation:** For systems under SOC2, PCI-DSS, or HIPAA, storing credentials in application logs/databases violates audit controls.

---

## Recommended Fix

Replace raw URLs with fingerprinted URIs:

```python
from elspeth.core.security.fingerprint import secret_fingerprint

@classmethod
def for_database(
    cls,
    url: str,
    table: str,
    content_hash: str,
    payload_size: int,
    row_count: int,
) -> "ArtifactDescriptor":
    # Extract and fingerprint credentials
    url_fingerprint = secret_fingerprint(url)
    safe_uri = f"db://{table}@fingerprint:{url_fingerprint[:16]}"

    return cls(
        artifact_type="database",
        path_or_uri=safe_uri,
        content_hash=content_hash,
        size_bytes=payload_size,
        metadata={
            "table": table,
            "row_count": row_count,
            "url_fingerprint": url_fingerprint,  # Full fingerprint for verification
        },
    )
```

---

## Conclusion

**VERIFIED:** This is a legitimate P1 bug. The code clearly:

1. Accepts raw URLs that may contain credentials
2. Embeds them directly in `path_or_uri` without sanitization
3. Persists them to the audit trail database
4. Exposes them through multiple output channels (export, TUI)
5. Has existing `secret_fingerprint()` infrastructure that should be used but isn't

The fix requires updating `ArtifactDescriptor.for_database()` and `for_webhook()` to use the existing fingerprinting infrastructure, as well as updating `DatabaseSink` to separate the credential portion from the host/table identification.
