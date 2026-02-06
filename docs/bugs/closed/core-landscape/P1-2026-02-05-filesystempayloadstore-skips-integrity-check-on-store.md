# BUG #5: FilesystemPayloadStore Skips Integrity Check on store()

**Issue ID:** elspeth-rapid-swb5
**Priority:** P1
**Status:** CLOSED
**Date Opened:** 2026-02-05
**Date Closed:** 2026-02-05
**Component:** core (payload_store.py)

## Summary

The `FilesystemPayloadStore.store()` method had an asymmetric design compared to `retrieve()`:
- `retrieve()` verifies file integrity before returning content (defensive)
- `store()` assumed existing files were correct without verification (trusting)

If a file existed but was corrupted (bit rot, tampering, partial write), `store()` would return the hash without verifying the file's actual contents matched. This violated Tier-1 audit integrity by allowing corrupted payloads to be silently accepted.

## Impact

- **Severity:** High - Tier-1 audit trail integrity
- **Effect:** Corrupted files accepted as valid payloads without verification
- **Risk:** Audit trail would reference hashes that don't match actual content

## Root Cause

The `store()` method (lines 79-89) had an "idempotent" early return:

```python
def store(self, content: bytes) -> str:
    """Store content and return its hash."""
    content_hash = hashlib.sha256(content).hexdigest()
    path = self._path_for_hash(content_hash)

    # Idempotent: skip if already exists
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    return content_hash  # BUG: Returns hash without verifying existing file!
```

If `path.exists()` was true, the method assumed the file was correct and immediately returned the hash. This assumption is dangerous because:

1. **File Corruption:** Disk bit rot, cosmic rays, partial writes from crashes
2. **Manual Tampering:** Someone modifies the file directly
3. **Hash Collision:** Extremely unlikely but theoretically possible
4. **Previous Write Failure:** Bug in earlier code wrote wrong content

**The Asymmetry:**

The `retrieve()` method (lines 91-110) has proper verification:

```python
def retrieve(self, content_hash: str) -> bytes:
    path = self._path_for_hash(content_hash)
    content = path.read_bytes()
    actual_hash = hashlib.sha256(content).hexdigest()

    if not hmac.compare_digest(actual_hash, content_hash):
        raise IntegrityError(...)  # Crashes on mismatch

    return content
```

**Why the asymmetry is wrong:**
- retrieve() = "Never trust files, always verify"
- store() = "Trust existing files completely"

This violates the Tier-1 trust model: our data (Landscape audit trail) must be pristine. If we reference a payload hash, that hash MUST match the actual file.

## Files Affected

- `src/elspeth/core/payload_store.py` (lines 79-89)

## Fix

Added integrity verification when file exists, mirroring `retrieve()` logic:

```python
def store(self, content: bytes) -> str:
    """Store content and return its hash.

    If file already exists, verifies integrity before returning hash.
    This prevents corrupted files from being silently accepted.

    Raises:
        IntegrityError: If existing file doesn't match expected hash
    """
    content_hash = hashlib.sha256(content).hexdigest()
    path = self._path_for_hash(content_hash)

    if path.exists():
        # BUG #5: Verify existing file matches expected hash
        existing_content = path.read_bytes()
        actual_hash = hashlib.sha256(existing_content).hexdigest()

        # Use timing-safe comparison (same as retrieve())
        if not hmac.compare_digest(actual_hash, content_hash):
            raise payload_contracts.IntegrityError(
                f"Payload integrity check failed on store: "
                f"existing file has hash {actual_hash}, expected {content_hash}"
            )
    else:
        # File doesn't exist - write it
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    return content_hash
```

**Key changes:**
1. When file exists, read it and compute actual hash
2. Compare actual vs expected using `hmac.compare_digest()` (timing-safe)
3. Raise `IntegrityError` on mismatch (same as `retrieve()`)
4. Only return hash if verification passes

**Why timing-safe comparison?**

Using `hmac.compare_digest()` instead of `==` prevents timing attacks where an attacker could incrementally discover expected hashes by measuring comparison time. While less critical for `store()` than `retrieve()`, we use it for consistency and defense-in-depth.

## Test Coverage

Added comprehensive test in `tests/core/test_payload_store.py`:

```python
def test_store_detects_corrupted_existing_file(self, tmp_path: Path)
```

**Test strategy:**
1. Store original content, get hash
2. Manually corrupt the file on disk (simulating bit rot)
3. Attempt to store the original content again
4. Verify `IntegrityError` is raised (not silent acceptance)
5. Verify error message includes both expected and actual hashes

**Test results:**
- RED: Test failed initially (store() returned hash without verification)
- GREEN: Test passed after fix (IntegrityError raised on mismatch)
- All 22 unit tests pass
- All 9 property tests pass (hypothesis-based fuzzing)

## Verification

```bash
# Run specific test
.venv/bin/python -m pytest tests/core/test_payload_store.py::TestFilesystemPayloadStore::test_store_detects_corrupted_existing_file -xvs

# Run all payload store unit tests
.venv/bin/python -m pytest tests/core/test_payload_store.py -x

# Run property-based tests
.venv/bin/python -m pytest tests/property/core/test_payload_store_properties.py -x
```

**Results:**
- Unit tests: 22/22 passed
- Property tests: 9/9 passed

## Pattern Observed

This is the fourth instance of defensive pattern gaps in Tier-1 code:
1. Bug #3 (database_ops) - missing rowcount validation
2. Bug #8 (schema validation) - missing Phase 5 columns
3. Bug #10 (operations) - missing BaseException handling
4. **Bug #5 (this bug)** - asymmetric integrity verification

**Lesson:** When implementing symmetric operations (store/retrieve, write/read, encode/decode), both sides must have equivalent validation. If one side verifies integrity, the other must too.

## Performance Impact

**Negligible for idempotent stores:**
- If file doesn't exist: same behavior (write file)
- If file exists AND is correct: one extra read + hash (~1ms for typical payloads)
- If file exists AND is corrupted: crash immediately (correct behavior)

The extra read/hash on idempotent stores is acceptable because:
1. Payloads are typically stored once, referenced many times
2. retrieve() already pays this cost on every read
3. Integrity violations are catastrophic - detecting them early is worth the cost

## Real-World Scenario

**Before fix:**
1. Pipeline stores payload, hash = "abc123..."
2. Disk bit flip corrupts the file
3. Pipeline resumes, calls store() with same content
4. store() sees file exists, returns "abc123..." (WRONG!)
5. Audit trail references "abc123..." but file is corrupted
6. Later retrieve() raises IntegrityError (too late - audit trail is wrong)

**After fix:**
1. Pipeline stores payload, hash = "abc123..."
2. Disk bit flip corrupts the file
3. Pipeline resumes, calls store() with same content
4. store() reads file, computes hash, detects mismatch
5. IntegrityError raised immediately (CORRECT!)
6. Operator investigates disk issue, fixes corruption
7. Audit trail remains pristine

## TDD Cycle Duration

- RED (write failing test): 5 minutes
- GREEN (implement fix): 4 minutes
- Verification (run all tests): 3 minutes
- **Total:** ~12 minutes

## Related Bugs

- Part of Group 1: Tier-1 Audit Trail Integrity (10 bugs total)
- Follows same pattern as Bugs #1-10 (validation gaps in Tier-1 code)
