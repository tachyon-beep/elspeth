# Analysis: src/elspeth/plugins/sinks/csv_sink.py

**Lines:** 617
**Role:** CSV output sink -- writes pipeline results to CSV files. Handles header management, field ordering, append mode, file lifecycle, display header resolution, and content hashing for audit integrity.
**Key dependencies:** `BaseSink` (plugins/base.py), `SinkPathConfig` (plugins/config_base.py), `PluginSchema` / `ArtifactDescriptor` (contracts), `HeaderMode` / `resolve_headers` (contracts/header_modes.py), `SchemaContract` (contracts/schema_contract.py), `PluginContext` (plugins/context.py), `create_schema_from_config` (plugins/schema_factory.py). Consumed by `SinkExecutor` (engine/executors.py) and `orchestrator/export.py`.
**Analysis depth:** FULL

## Summary

CSVSink is well-structured and follows the three-tier trust model correctly. The most significant concern is a **content hash race condition**: the hash is computed by re-reading the file from disk after writing, but between `file.flush()` and `_compute_file_hash()`, a concurrent process or resume-mode append could alter the file, producing a hash that does not match what was actually written in this batch. There are also two resource leak scenarios on error paths, and the JSONL-write pattern (opening the file fresh on every `_write_jsonl_batch` call) does not apply here but the CSV pattern of keeping the file handle open has its own concern around missing `close()` on exception paths during `_open_file`. Overall the file is sound but has a few issues that matter for the audit integrity guarantees ELSPETH requires.

## Critical Findings

### [266-271] Content hash computed from full file, not from batch written -- hash/audit mismatch in append mode

**What:** After writing rows, `write()` calls `file.flush()` then `_compute_file_hash()` which reads the entire file from disk and hashes it. In append mode, this hashes ALL rows ever written to the file (previous runs plus current batch), not just the current batch. The `ArtifactDescriptor` returned contains this full-file hash plus `size_bytes` of the full file.

**Why it matters:** In a resume scenario, the artifact hash changes with every batch even though the audit trail records it per write operation. If the orchestrator expects the hash to represent "what this write produced," the hash actually represents "cumulative state of the file." More critically, if another process (or another sink instance in a multi-sink DAG) appends to the same file between flush and hash computation, the hash captures data that this write did not produce. For an emergency dispatch system, this could mean the audit trail attributes data to the wrong write operation, violating the attributability guarantee.

**Evidence:**
```python
# Line 266-271: hash is of ENTIRE file, not this batch
file.flush()
content_hash = self._compute_file_hash()  # Re-reads entire file
size_bytes = self._path.stat().st_size     # Full file size
```

The `_compute_file_hash` method (line 573-579) opens the file in binary read mode and hashes all of it. In write mode this is fine (file was truncated). In append mode, this hashes the cumulative file.

### [254-264] File handle leak if `_open_file` raises after partial state change

**What:** In `write()`, if `_open_file(rows)` raises an exception (e.g., permission denied, disk full, schema mismatch in append mode line 324), `self._file` may be in an inconsistent state. Specifically, in the append-mode path (line 337-346), the file is opened before the `return` statement. If an exception occurs after `open()` but before the method completes, the file handle is leaked because `self._file` was assigned but `close()` is never called by the exception handler.

**Why it matters:** File descriptor exhaustion in a long-running pipeline processing thousands of rows with repeated failures. In an emergency dispatch system, running out of file descriptors could prevent writing to other sinks.

**Evidence:**
```python
# Line 337-346: File opened, assigned to self._file, then writer created
# If csv.DictWriter constructor fails (theoretically shouldn't, but...)
# or if any code between open() and return raises, handle leaks.
self._file = open(self._path, "a", encoding=self._encoding, newline="")
self._writer = csv.DictWriter(...)  # What if this raises?
```

While `csv.DictWriter` is unlikely to raise, the pattern is fragile. More importantly, in the write-mode path (lines 355-372), if `csv.writer.writerow(display_fields)` raises (e.g., due to encoding issues in display header names), the file handle at `self._file` leaks.

## Warnings

### [231-237] Empty batch returns a hash of empty bytes, not a hash of the file

**What:** When `write()` receives an empty `rows` list, it returns `ArtifactDescriptor` with `content_hash=hashlib.sha256(b"").hexdigest()` and `size_bytes=0`. But if the file already exists (append mode), the actual file is non-empty. The descriptor claims 0 bytes and an empty hash, which contradicts the file's actual state.

**Why it matters:** An auditor examining the artifact trail would see a descriptor claiming the file is empty when it is not. This is not a data loss issue, but it is an audit integrity inconsistency that could erode trust in the trail.

**Evidence:**
```python
if not rows:
    return ArtifactDescriptor.for_file(
        path=str(self._path),
        content_hash=hashlib.sha256(b"").hexdigest(),
        size_bytes=0,
    )
```

### [304-346] Append mode reads headers then re-opens file -- TOCTOU window

**What:** In `_open_file`, append mode first opens the file to read existing headers (line 306-308), closes it (context manager), then reopens in append mode (line 337-338). Between these two operations, the file could be modified or deleted.

**Why it matters:** Time-of-check-to-time-of-use race condition. If another process modifies the file between the read and the append-open, the headers read may no longer match the file's actual state. In practice this is unlikely in single-pipeline operation, but could occur with concurrent resume attempts.

**Evidence:**
```python
# Read phase (file opened then closed by context manager)
with open(self._path, encoding=self._encoding, newline="") as f:
    reader = csv.DictReader(f, delimiter=self._delimiter)
    existing_fieldnames = reader.fieldnames
# ... validation ...
# Write phase (file reopened) -- gap where file could change
self._file = open(self._path, "a", encoding=self._encoding, newline="")
```

### [329-333] Display header reverse mapping assumes bijective mapping

**What:** The reverse map is built via `{v: k for k, v in display_map.items()}`. If two normalized names map to the same display name, only one survives in the reverse map. When reading existing headers in append mode, this would cause field mapping errors.

**Why it matters:** While display headers are typically unique, there is no validation enforcing this. A misconfigured `display_headers` mapping with duplicate values would cause silent field misidentification in append mode.

**Evidence:**
```python
reverse_map = {v: k for k, v in display_map.items()}
self._fieldnames = [reverse_map.get(h, h) for h in existing_fieldnames]
```

### [573-579] File hash re-reads entire file on every write call -- O(N) performance degradation

**What:** `_compute_file_hash()` reads the entire file on every `write()` invocation. In append mode, the file grows with each batch. For a pipeline processing millions of rows, the hash computation becomes progressively slower as it re-reads all previously written data.

**Why it matters:** For a high-throughput emergency dispatch pipeline, this creates O(N^2) total I/O over the lifetime of the run (each of N writes reads all previously written data). This could cause unacceptable latency in time-sensitive dispatch operations.

**Evidence:**
```python
def _compute_file_hash(self) -> str:
    sha256 = hashlib.sha256()
    with open(self._path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
```

## Observations

### [174] Comment says "legacy options" but CLAUDE.md says no legacy code

**What:** Line 174 comments `self._display_headers` as "Display header configuration (legacy options)". The CLAUDE.md mandates a strict NO LEGACY CODE policy. If these are truly legacy, they should be removed; if they are still needed, the comment should not label them as legacy.

### [389-406] Schema mode fallback branch "shouldn't happen with valid config"

**What:** Line 404-406 has a fallback path with a comment "shouldn't happen with valid config." Per CLAUDE.md, if it shouldn't happen, it should crash rather than silently falling back.

### [596-601] `close()` does not flush before closing

**What:** The `close()` method closes the file without calling `flush()` first. While the orchestrator calls `flush()` before `close()`, if `close()` is called directly (e.g., in error paths or by the orchestrator cleanup), buffered data could be lost. The `flush()` method includes `os.fsync()` which `close()` skips.

### Duplication with JSONSink

**What:** Approximately 150 lines of code are near-identical between CSVSink and JSONSink: `_get_effective_display_headers`, `_resolve_display_headers_if_needed`, `_resolve_contract_from_context_if_needed`, `set_output_contract`, `get_output_contract`, `set_resume_field_resolution`. This is a DRY violation that will cause drift if one is updated without the other.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** The content hash semantics in append mode (Critical finding) should be clarified -- either document that the hash represents cumulative file state (acceptable if the orchestrator expects this), or change to hash only the current batch (consistent with DatabaseSink which hashes the batch payload). The file handle leak paths should be addressed with try/finally in `_open_file`. The performance issue with re-reading the entire file for hashing should be addressed with an incremental hash approach for append mode.
**Confidence:** HIGH -- all findings are based on direct code reading with full dependency context. The append-mode hash semantics is the most consequential issue and is unambiguous from the code.
