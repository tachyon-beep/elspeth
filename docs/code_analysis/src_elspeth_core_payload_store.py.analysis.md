# Analysis: src/elspeth/core/payload_store.py

**Lines:** 145
**Role:** Filesystem-based content-addressable storage for large blobs. Separates large payloads from audit tables using SHA-256 hashes as keys. Provides automatic deduplication, integrity verification on retrieval, and path traversal protection.
**Key dependencies:** `hashlib`, `hmac`, `re`, `pathlib.Path`; imports `elspeth.contracts.payload_store.IntegrityError`; used by `cli.py`, `conftest.py`, `checkpoint/recovery`, `retention/purge`
**Analysis depth:** FULL

## Summary

This is a compact, well-structured module. The path traversal protection is thorough (regex + resolved path containment check). Integrity verification on both store and retrieve is correct. However, there is one critical finding: the `store()` method has a non-atomic write that creates a TOCTOU race condition where concurrent writers or a crash during write can leave corrupted partial files. There is also a warning about the `delete()` method not cleaning up empty parent directories, and an observation about missing `__enter__`/`__exit__` context manager support.

## Critical Findings

### [103-106] Non-atomic write creates TOCTOU race and corruption window

**What:** The `store()` method checks `path.exists()` on line 91, then writes with `path.write_bytes(content)` on line 106. Between the existence check and the write completion, two failure modes exist:

1. **Concurrent writers:** Two threads/processes storing the same hash simultaneously. Both see `path.exists() == False`, both call `write_bytes()`. `write_bytes()` calls `open(path, 'wb')` which truncates the file -- if writer A is mid-write when writer B truncates, writer A's partial content is destroyed. Writer B then writes its content. No error is raised, but the file is now the content from writer B's write (which is actually correct for content-addressable storage since both writers have the same content). However, if writer A and writer B are writing DIFFERENT content that happens to collide (SHA-256 collision -- astronomically unlikely but the code doesn't account for it), the result is undefined.

2. **Crash during write:** If the process crashes or loses power during `path.write_bytes(content)`, the file will be partially written. On the next `retrieve()` call, the integrity check will catch this and raise `IntegrityError` -- so no silent corruption. But the hash is now "poisoned" -- every subsequent `store()` of the same content will find the corrupted file, verify it, and raise `IntegrityError` instead of overwriting it. The system becomes unable to store that content until manual intervention removes the corrupted file.

**Why it matters:** The crash-during-write scenario is the real concern. Once a file is partially written, the content hash becomes permanently unavailable until someone manually deletes the corrupted file. For an audit system that "must withstand formal inquiry," having a hash that was correctly computed but whose payload is irrecoverable is a gap.

**Evidence:**
```python
if path.exists():
    # Verify integrity of existing file
    existing_content = path.read_bytes()
    actual_hash = hashlib.sha256(existing_content).hexdigest()
    if not hmac.compare_digest(actual_hash, content_hash):
        raise payload_contracts.IntegrityError(...)
else:
    # File doesn't exist - write it
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)  # NON-ATOMIC: partial write on crash
```

**Recommended pattern:** Write to a temporary file in the same directory, then `os.rename()` (atomic on POSIX) to the final path. On crash, only the temp file is left, and the target path remains clean.

## Warnings

### [91-107] Store verification reads entire file even for known-good dedup

**What:** When `path.exists()` is True on line 91, the entire file is read into memory (`path.read_bytes()` on line 95) and re-hashed to verify integrity. For large payloads (megabytes or more), this is an expensive operation that happens on every duplicate store.

**Why it matters:** In a pipeline processing thousands of rows that reference the same large blob (e.g., a lookup table or model artifact), every row's store operation reads the entire file. This is correct for integrity but could become a performance bottleneck. A mitigating design would be to check file size first (if size differs, it's definitely corrupted) before reading content.

### [135-145] Delete does not clean up empty parent directories

**What:** `delete()` removes the file but does not attempt to remove the now-empty parent directory (the two-character hash prefix subdirectory). Over time with many creates and deletes (e.g., retention purge cycles), this could leave thousands of empty directories.

**Why it matters:** Cosmetic issue on most filesystems, but on some storage backends or in container environments with limited inode counts, empty directories consume inodes. After many purge cycles, `ls` on the base directory would show 256 empty subdirectories (00-ff).

### [91] exists() check before write is not atomic with mkdir

**What:** `path.parent.mkdir(parents=True, exist_ok=True)` on line 105 can race with another process that is also creating the same directory. The `exist_ok=True` handles this correctly for `mkdir`, but there's a window between `mkdir` completing and `write_bytes` starting where another writer could create the file.

**Why it matters:** This is a subset of the TOCTOU race described in the Critical finding. The `exist_ok=True` on `mkdir` is the correct mitigation for the directory creation race, but the file write race remains.

## Observations

### [58-76] Path traversal protection is thorough

**What:** Two layers of protection: (1) regex validation requiring exactly 64 lowercase hex chars (line 60), (2) resolved path containment check (line 71). The regex alone would prevent path traversal since `../` contains non-hex characters, but the containment check is defense-in-depth.

### [98-99, 126] Timing-safe comparison is correctly used

**What:** `hmac.compare_digest()` is used for hash comparison on both store (line 99) and retrieve (line 126). This prevents timing attacks that could leak information about expected hashes. While the threat model for a local filesystem store is limited, this is good practice for an audit system.

### [34-41] Constructor creates base directory

**What:** `self.base_path.mkdir(parents=True, exist_ok=True)` in `__init__` ensures the base directory exists. This is correct for a store that will be used immediately after construction.

### No context manager support

**What:** `FilesystemPayloadStore` does not implement `__enter__`/`__exit__`. Since it has no resources to close (no open file handles or connections), this is acceptable. The filesystem handles are opened and closed within each method call.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** Address the non-atomic write in `store()` using a write-to-temp-then-rename pattern. This eliminates both the crash corruption window and the concurrent writer race. The empty directory cleanup in `delete()` is a low-priority cosmetic issue.
**Confidence:** HIGH -- The file is small, the code paths are clear, and the race condition is a well-known pattern. The integrity verification on store (BUG #5 fix) shows awareness of these issues, but the atomic write gap remains.
