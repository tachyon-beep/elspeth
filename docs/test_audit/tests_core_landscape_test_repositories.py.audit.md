# Test Audit: tests/core/landscape/test_repositories.py

**Lines:** 734
**Test count:** 22 test functions
**Audit status:** PASS

## Summary

This test file provides comprehensive coverage of the Landscape repository layer, specifically verifying that repositories correctly convert database strings to enum types and crash on invalid data per the Data Manifesto (Tier-1 crash-on-corruption). The tests are well-structured, focused, and directly aligned with the codebase's auditability requirements.

## Findings

### 🔵 Info

1. **Repeated dataclass definitions (lines 51-66, 85-99, 119-134, etc.)**: Each test method defines its own `*Row` dataclass locally. While this makes each test self-contained and readable, it results in significant code repetition. This is a minor structural concern but does not affect test correctness. The approach is defensible for test isolation.

2. **Mock pattern is appropriate**: The use of local dataclasses to mock SQLAlchemy rows with `session=None` is a legitimate unit testing pattern. It tests the repository's `load()` method in isolation without requiring a database connection.

3. **Consistent coverage across all repositories**: The file tests 8 repositories (RunRepository, NodeRepository, EdgeRepository, RowRepository, TokenRepository, TokenParentRepository, CallRepository, RoutingEventRepository, BatchRepository) with both happy-path and error-path tests.

4. **Tests validate Data Manifesto compliance**: The tests explicitly verify that invalid enum values cause crashes (ValueError), which directly validates the Tier-1 "crash on corruption" requirement.

## Verdict

**KEEP** - This is a high-quality test file that validates critical audit-integrity behavior. The repository layer is the boundary between the database and domain models, and these tests ensure that enum corruption is detected. The repetition of dataclass definitions is acceptable for test isolation.
