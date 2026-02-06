# Analysis: src/elspeth/plugins/sinks/json_sink.py

**Lines:** 537
**Role:** JSON output sink -- writes pipeline results to JSON (array) or JSONL (line-delimited) files. Handles JSON serialization, streaming output, display header mapping, append/resume mode for JSONL, and content hashing for audit integrity.
**Key dependencies:** `BaseSink` (plugins/base.py), `SinkPathConfig` (plugins/config_base.py), `PluginSchema` / `ArtifactDescriptor` (contracts), `HeaderMode` / `resolve_headers` (contracts/header_modes.py), `SchemaContract` (contracts/schema_contract.py), `PluginContext` (plugins/context.py), `create_schema_from_config` (plugins/schema_factory.py). Consumed by `SinkExecutor` (engine/executors.py) and `orchestrator/export.py`.
**Analysis depth:** FULL

## Summary

JSONSink has a **critical data loss bug** in its JSON array format: the `_rows` buffer accumulates rows in memory but after the file is closed and reopened (e.g., after close() in error recovery), the buffer is cleared, losing all previously written data while the file still exists. There is also an **unbounded memory growth** issue in JSON array mode since all rows are buffered in `self._rows` for the lifetime of the run. The JSONL mode is generally sound but shares the same append-mode hash semantics concern as CSVSink. The file is well-organized but has significant issues in the JSON array path.

## Critical Findings

### [233, 310-317, 342-347] JSON array mode: unbounded memory growth and data loss on close/reopen

**What:** In JSON array mode, every batch of rows is appended to `self._rows` (line 278), and `_write_json_array()` rewrites the entire file each time (seek(0), truncate, dump). The `self._rows` list grows without bound for the entire pipeline run. When `close()` is called (line 342-347), it sets `self._rows = []`, clearing the buffer. If the sink is subsequently reused or the file is expected to persist, the relationship between the in-memory buffer and the file is severed.

**Why it matters:** For a pipeline processing a large dataset (e.g., millions of emergency dispatch records), all rows accumulate in memory simultaneously. This can cause OOM kills. The memory usage is O(N) where N is total rows across all batches, not O(batch_size). For an emergency dispatch system with sustained throughput, this is a production reliability risk.

More critically, the rewrite pattern (seek(0) + truncate + dump) means that if a crash occurs AFTER truncate but BEFORE the full dump completes, the file is corrupted with a partial JSON array. The `flush()` method only flushes what has been written, but if the process crashes mid-write, the truncated file contains incomplete JSON.

**Evidence:**
```python
# Line 278: Buffer grows unbounded
self._rows.extend(output_rows)

# Line 310-317: Rewrite pattern -- truncate then write
def _write_json_array(self) -> None:
    if self._file is None:
        self._file = open(self._path, "w", encoding=self._encoding)
    self._file.seek(0)
    self._file.truncate()          # File is now EMPTY
    json.dump(self._rows, self._file, indent=self._indent)  # If this crashes, data lost

# Line 342-347: close() destroys buffer
def close(self) -> None:
    if self._file is not None:
        self._file.close()
        self._file = None
        self._rows = []  # All rows lost from memory
```

### [310-317] JSON array truncate-then-write is not atomic -- partial write on crash loses all data

**What:** The `_write_json_array` method performs `seek(0)` then `truncate()` then `json.dump()`. After `truncate()`, the file is empty. If the process crashes, is killed, or `json.dump()` raises an exception (e.g., non-serializable value), the file is left empty or partially written. ALL previously written data is destroyed.

**Why it matters:** For an emergency dispatch system, this means a crash at any point during a JSON array write could destroy the entire output file, including all successfully processed rows from previous batches. This is a catastrophic data loss scenario. The audit trail would show successful writes, but the file would be empty or corrupted.

**Evidence:**
```python
self._file.seek(0)
self._file.truncate()  # ALL previous data destroyed
json.dump(self._rows, self._file, indent=self._indent)  # Must succeed or data is lost
```

The correct pattern for atomic file replacement is write-to-temp-then-rename, which is not used here.

### [302-308] JSONL mode: file opened fresh on every `_write_jsonl_batch` call in write mode

**What:** If `self._file is None`, the file is opened. But in write mode (not append), each call opens with mode `"w"` which truncates. However, `self._file` is only None initially or after `close()`. After the first call, `self._file` is set and reused. This means JSONL write mode works correctly for the normal case. BUT: if `write()` is called, then `close()` is called, then `write()` is called again, the file is truncated and only the second batch survives.

**Why it matters:** The orchestrator calls `sink.close()` in cleanup (engine/orchestrator/core.py line 1640). If the pipeline encounters an error after some writes, cleanup closes the sink, and any subsequent writes (e.g., error-recovery writes) would truncate existing data.

**Evidence:**
```python
def _write_jsonl_batch(self, rows: list[dict[str, Any]]) -> None:
    if self._file is None:
        file_mode = "a" if self._mode == "append" else "w"
        self._file = open(self._path, file_mode, encoding=self._encoding)
    for row in rows:
        json.dump(row, self._file)
        self._file.write("\n")
```

## Warnings

### [283-284] Flush only happens if `self._file is not None` -- JSON array first write may not flush

**What:** In `write()`, the flush at line 283-284 checks `if self._file is not None`. For JSON array mode, `_write_json_array()` creates the file handle internally. So after the first call, `self._file` is set. But if `_write_json_array` raises before setting `self._file`, the flush is skipped and the content hash is computed on whatever is on disk (possibly stale data from a previous run).

**Why it matters:** The content hash would not match the intended write, creating an audit integrity violation.

### [249-255] Empty batch returns hash of empty bytes, inconsistent with file state

**What:** Same issue as CSVSink: empty batch returns `hashlib.sha256(b"").hexdigest()` and `size_bytes=0`, even if the file already has content from previous writes.

**Why it matters:** Audit trail inconsistency. An artifact descriptor claiming the file is empty when it contains data from previous batches.

### [286-288] Content hash re-reads entire file on every write -- O(N^2) for JSONL append mode

**What:** Same as CSVSink: `_compute_file_hash()` reads the entire file on every `write()` call. For JSONL in append mode, this is O(N) per call and O(N^2) total over the run.

**Why it matters:** Performance degradation for high-throughput pipelines. Less severe than the JSON array data loss issues but still a concern for time-sensitive emergency dispatch operations.

### [506-522] Display header mapping creates new dicts for every row in every batch

**What:** `_apply_display_headers` creates a new dict for every row by iterating all keys. This is O(rows * fields) per write call and creates significant GC pressure for large batches.

**Why it matters:** Performance concern for high-throughput pipelines. The allocation pattern could cause GC pauses in time-sensitive operations.

**Evidence:**
```python
return [{display_map.get(k, k): v for k, v in row.items()} for row in rows]
```

### [120-127] JSONL resume validation only checks first line

**What:** `validate_output_target()` reads only the first line of the JSONL file to check field structure. If the file was corrupted mid-write (e.g., last line is incomplete JSON), validation passes but subsequent appends produce a file with a corrupt line in the middle.

**Why it matters:** Resuming from a crash could produce a JSONL file that is valid at the start and end but has a corrupt line in the middle, which downstream consumers would fail to parse.

## Observations

### Massive code duplication with CSVSink

**What:** The following methods are nearly identical between CSVSink and JSONSink:
- `_get_effective_display_headers` (~30 lines)
- `_resolve_display_headers_if_needed` (~25 lines)
- `_resolve_contract_from_context_if_needed` (~15 lines)
- `set_output_contract` / `get_output_contract` (~15 lines)
- `set_resume_field_resolution` (~10 lines)
- `_compute_file_hash` (~7 lines)

This is approximately 100 lines of duplicated logic. Changes to one must be manually replicated to the other.

### [206-209] Format auto-detection is fragile

**What:** Format is auto-detected from file extension: `.jsonl` -> JSONL, everything else -> JSON. This means a file named `output.json` but intended as JSONL (which is a common mistake) would be treated as JSON array format, leading to the unbounded memory growth and non-atomic write issues.

### JSON array mode does not support display headers in append mode

**What:** JSON array mode does not support resume (line 81-86), which is correct. But if someone configures `mode: append` with JSON array format, the sink silently ignores the mode setting and opens in write mode (line 314). There is no validation preventing this misconfiguration.

## Verdict

**Status:** CRITICAL
**Recommended action:** The JSON array truncate-then-write pattern (Critical finding) is a data loss risk that must be addressed before this code handles emergency dispatch data. Options: (1) write to a temp file then atomically rename, (2) keep a backup copy of the previous version, or (3) deprecate JSON array format and require JSONL for production. The unbounded memory growth in JSON array mode should be documented as a known limitation or addressed with streaming JSON array writing. The JSONL path is mostly sound but shares the append-mode hash concern with CSVSink.
**Confidence:** HIGH -- the truncate-then-write data loss scenario is unambiguous from the code. The unbounded memory growth follows directly from the append-to-list pattern. All findings confirmed against actual code paths.
