# Audit: tests/scripts/test_check_contracts.py

## Summary
**Overall Quality: EXCELLENT**

This file contains comprehensive tests for the contracts enforcement script that verifies Settings->Runtime configuration alignment. Tests cover type definition discovery, whitelist loading, settings alignment, field coverage, field name mappings, and hardcode documentation.

## File Statistics
- **Lines:** 1447
- **Test Classes:** 0 (all functions)
- **Test Functions:** ~70
- **Integration Tests:** 4 (test against real codebase)

## Findings

### No Defects Found

The tests correctly verify the contracts enforcement script behavior.

### Overmocking Assessment: ACCEPTABLE

Uses `unittest.mock.patch` to inject test values for SETTINGS_TO_RUNTIME, EXEMPT_SETTINGS, FIELD_MAPPINGS, INTERNAL_DEFAULTS. This is appropriate because:
1. Tests verify the script logic, not the actual alignment data
2. Integration tests (lines 382-399, 695-715, 1070-1088, 1410-1428) verify real codebase passes

### Coverage Assessment: EXCELLENT

**Type Definition Discovery:**
1. Finds @dataclass decorated classes
2. Finds @dataclass(frozen=True) decorated classes
3. Finds Enum subclasses
4. Finds TypedDict subclasses
5. Finds NamedTuple subclasses
6. Ignores Pydantic BaseModel (intentional)
7. Ignores PluginSchema (intentional)
8. Finds multiple definitions in one file

**Whitelist Loading:**
9. Basic whitelist loading
10. Empty file handling
11. Nonexistent file handling
12. Multiple entries loading

**Error Handling:**
13. Syntax errors graceful handling
14. Unicode errors graceful handling

**Settings Alignment:**
15. Passes with mapping in SETTINGS_TO_RUNTIME
16. Passes with class in EXEMPT_SETTINGS
17. Detects orphaned Settings class
18. Multiple classes (mapped, exempt, orphaned)
19. Integration: real core/config.py passes

**Field Coverage (from_settings() checks):**
20. SettingsAccessVisitor finds direct access
21. SettingsAccessVisitor finds chained access
22. Different parameter names
23. Extract accesses from file
24. Handles classes without from_settings
25. Multiple Runtime classes
26. Extracts Settings class fields
27. Missing class returns empty
28. Full coverage passes
29. Detects orphaned field
30. Detects multiple orphans
31. Skips unmapped classes
32. Integration: real codebase passes

**Field Name Mappings:**
33. FieldMappingVisitor finds direct mappings
34. Finds renamed mappings
35. Ignores non-settings values
36. Different parameter names
37. Extract mappings from file
38. Finds renamed fields
39. Correct mapping passes
40. Detects misrouted field (key test)
41. Detects swapped fields
42. Ignores unmapped classes
43. Ignores direct name fields
44. Integration: real codebase passes

**Hardcode Documentation:**
45. HardcodeLiteralVisitor finds plain literals
46. Ignores function calls (like float(INTERNAL_DEFAULTS[...]))
47. Ignores subscripts (like INTERNAL_DEFAULTS["key"])
48. Finds negative numbers
49. Extract hardcodes from file
50. Multiple classes
51. Documented hardcode passes
52. Detects undocumented hardcode (key test)
53. Detects wrong value (documented != code)
54. Flags missing subsystem mapping
55. Ignores classes without hardcodes
56. Integration: real codebase passes

### Test Design Highlights

1. **Lines 389-399:** Integration test verifies ACTUAL core/config.py passes - catches real alignment issues.

2. **Lines 902-949:** Key test case - detects field MISROUTE where code maps settings.A to runtime_field_B instead of the documented mapping.

3. **Lines 952-995:** Detects SWAPPED fields - both A->B and B->A are wrong.

4. **Lines 1290-1325:** Detects UNDOCUMENTED hardcodes - literals in from_settings() not in INTERNAL_DEFAULTS.

5. **Lines 1327-1354:** Detects WRONG VALUE - code has 2.0 but documented as 1.0.

### Minor Observations

1. **No test class structure:** All tests are functions. Consider grouping into classes for organization, but current structure is acceptable.

2. **pytest.skip usage:** Integration tests skip when running from different directory - appropriate.

3. **Dataclass tests (lines 402-411, 718-731, etc.):** Test violation dataclass fields - ensures violation reporting works.

## Verdict

**PASS - No changes required**

Comprehensive test coverage for a critical CI/CD script that prevents Settings->Runtime field orphaning (P2-2026-01-21 pattern). Integration tests ensure real codebase compliance.
