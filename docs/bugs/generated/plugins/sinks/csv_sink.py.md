## Summary

`CSVSink.write()` can truncate or recreate the target file before the first batch is proven serializable, so a failing first batch leaves a mutated output file even though the sink write failed.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sinks/csv_sink.py
- Line(s): 275-277, 408-439, 293-304
- Function/Method: `write`, `_open_file`

## Evidence

`write()` opens the file before it validates that the batch can actually be serialized:

```python
if self._file is None:
    self._open_file(rows)
...
staging_writer = csv.DictWriter(...)
for row in rows:
    staging_writer.writerow(row)
```

In `_open_file()`, write mode immediately truncates the destination and writes the header:

```python
self._file = open(self._path, "w", encoding=self._encoding, newline="")
...
self._writer.writeheader()
self._file.flush()
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/csv_sink.py:275-277`, `/home/john/elspeth/src/elspeth/plugins/sinks/csv_sink.py:415-439`, `/home/john/elspeth/src/elspeth/plugins/sinks/csv_sink.py:293-304`.

What the code does:
- On the first batch, it opens the file in `"w"` mode and writes headers.
- Only after that does it serialize rows into the staging buffer.
- If `staging_writer.writerow(row)` raises on row shape mismatch, `write()` exits with an exception after the file has already been truncated and header-written.

What it should do:
- Prove the batch is serializable before mutating the output target, or write to a temp file and only replace/commit once the batch is known-good.

The existing regression test only covers the “second batch fails after the file is already established” case, not “first batch fails after `_open_file()` has already truncated the file”:

Source: `/home/john/elspeth/tests/unit/plugins/sinks/test_sink_bug_fixes.py:55-82`.

This matters because the engine records sink outcomes only after `sink.write()` and `sink.flush()` succeed:

Source: `/home/john/elspeth/src/elspeth/engine/executors/sink.py:227-236`, `/home/john/elspeth/src/elspeth/contracts/engine.py:47-55`.

## Root Cause Hypothesis

The fix for the earlier partial-batch bug moved row serialization into an in-memory staging buffer, but the staging step still happens too late. File creation/truncation and header emission remain in `_open_file()`, which is called before staging, so “all-or-nothing” only applies to row bytes, not to the target file itself.

## Suggested Fix

Delay write-mode file creation/truncation until after batch staging succeeds.

Possible approach:
- Compute `data_fields`/`display_fields` without opening the file.
- Stage the header plus staged rows into memory first.
- Only then open/truncate the target and commit the staged content.
- For stronger safety, use a temp file + `os.replace()` in write mode so the old file survives any first-batch failure.

## Impact

A failed first sink batch can still destroy or mutate the output artifact. In write mode against an existing file, prior contents are lost and replaced by a header-only file even though the batch failed. That breaks audit expectations: the Landscape will show the sink write as failed, but the filesystem has already changed.
---
## Summary

`CSVSink.write()` has no rollback path for I/O failures after bytes start appending, so late write/flush/hash errors can leave rows on disk that the audit trail will treat as a failed sink write.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/sinks/csv_sink.py
- Line(s): 310-324
- Function/Method: `write`

## Evidence

After staging, the sink appends the batch directly to the live file:

```python
pre_write_pos = file.tell()
file.write(staged_content)
file.flush()

with open(self._path, "rb") as bf:
    bf.seek(pre_write_pos)
    for chunk in iter(lambda: bf.read(8192), b""):
        self._hasher.update(chunk)
content_hash = self._hasher.hexdigest()
size_bytes = self._path.stat().st_size
```

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/csv_sink.py:310-324`.

What the code does:
- Captures the pre-write offset.
- Writes staged bytes into the real file.
- Flushes and then reopens the file to hash the newly appended region.
- If any step after `file.write()` begins fails, there is no `try/except` and no `truncate(pre_write_pos)` rollback.

What it should do:
- Either commit atomically, or explicitly roll the file back to `pre_write_pos` on any failure after mutation begins.

The engine assumes that failed sink writes did not durably produce accepted output; it only records token outcomes after `sink.write()` and `sink.flush()` both succeed:

Source: `/home/john/elspeth/src/elspeth/engine/executors/sink.py:227-236`, `/home/john/elspeth/src/elspeth/contracts/engine.py:47-55`.

So if `file.flush()` raises after partially pushing bytes, or if hashing/statting fails after the append, the executor will treat the batch as failed while the CSV may already contain some or all of those rows.

For contrast, the JSON sink’s array mode uses temp-file + `os.replace()` and cleans up on failure, specifically to avoid leaving partially committed output behind:

Source: `/home/john/elspeth/src/elspeth/plugins/sinks/json_sink.py:339-372`.

## Root Cause Hypothesis

The code optimizes for fast incremental hashing but treats the append as if it were atomic. It stages serialization, but once bytes are written to the live file it does not guard the mutation with rollback logic. The implementation assumes post-write steps cannot fail in a way that leaves externally visible partial state.

## Suggested Fix

Wrap the mutation phase in a rollback guard.

Example direction:
- Capture `pre_write_pos`.
- `try` the `write`/`flush`/hash/stat sequence.
- On any exception after the live file has been modified:
  - `file.seek(pre_write_pos)`
  - `file.truncate(pre_write_pos)`
  - `file.flush()`
  - `os.fsync(file.fileno())`
  - re-raise

If write-mode semantics permit it, temp-file + atomic replace is even safer.

## Impact

This violates the sink durability contract and can create audit divergence: rows can appear in the CSV even though the sink write failed and no terminal “completed” sink outcomes are recorded for those tokens. In a high-stakes audit system, that is silent data leakage outside the recorded terminal state model.
