# Test Audit: tests/property/core/test_payload_store_properties.py

## Overview
Property-based tests for FilesystemPayloadStore (content-addressable storage).

**File:** `tests/property/core/test_payload_store_properties.py`
**Lines:** 213
**Test Classes:** 4

## Findings

### PASS - Excellent CAS Property Coverage

**Strengths:**
1. **Core CAS property tested** - `retrieve(store(content)) == content` (Lines 29-45)
2. **Hash determinism tested** - Same content always produces same hash
3. **SHA-256 verified** - Store hash matches direct hashlib.sha256()
4. **Idempotence tested** - Multiple stores don't create duplicates
5. **Integrity verification tested** - Corrupted content detected via IntegrityError

### Minor Issues

**1. Low Priority - Test assumes internal implementation (Lines 206-207)**
```python
file_path = store._path_for_hash(content_hash)
corrupted = content + b"CORRUPTED"
file_path.write_bytes(corrupted)
```
- Accesses private method `_path_for_hash`
- Acceptable for corruption testing but tightly coupled to implementation

**2. Observation - Collision test uses early return (Lines 94-114)**
```python
def test_different_content_different_hash(self, content1: bytes, content2: bytes) -> None:
    if content1 == content2:
        return  # Skip when Hypothesis generates identical content
```
- Uses early return instead of `assume(content1 != content2)`
- Both work, but `assume()` is more idiomatic for Hypothesis

**3. Good Pattern - Temporary directories (Lines 36-38)**
```python
with tempfile.TemporaryDirectory() as tmp_dir:
    store = FilesystemPayloadStore(Path(tmp_dir) / "payloads")
```
- Properly isolates each test with fresh storage

### Coverage Assessment

| Property | Tested | Notes |
|----------|--------|-------|
| Store/retrieve roundtrip | YES | Core property |
| exists() after store | YES | |
| Hash determinism | YES | |
| Hash matches SHA-256 | YES | |
| Different content = different hash | YES | |
| Idempotent storage | YES | |
| Delete then re-store | YES | |
| Retrieve non-existent raises KeyError | YES | |
| Corrupted content detected | YES | IntegrityError |

## Verdict: PASS

Comprehensive coverage of content-addressable storage properties. The integrity verification test is particularly important for audit trail guarantees.
