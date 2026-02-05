# Audit: tests/plugins/test_manager.py

## Summary
Tests for PluginManager including registration, lookup by name, duplicate detection, missing plugin handling, discovery-based registration, and config validation.

## Findings

### 1. Good Practices
- Tests create manager, register plugin, lookup by name
- Tests duplicate name rejection within same type
- Tests same name allowed across different types
- Tests unknown plugin raises ValueError with clear message
- Tests discovery-based registration finds expected plugins
- Tests config validation before instantiation

### 2. Issues

#### Inline Class Definitions
- **Location**: Lines 23-45, 69-101
- **Issue**: Plugin classes defined inside test methods
- **Impact**: Low - clear but verbose
- **Note**: This pattern ensures test isolation

#### Late pytest Import
- **Location**: Line 121, 175, etc.
- **Issue**: `import pytest` inside test methods
- **Impact**: None - works but unusual pattern

### 3. Missing Coverage

#### No Tests for Gate Registration
- Sources, transforms, sinks tested but gates not tested
- `get_gates()` or `get_gate_by_name()` not exercised

#### No Tests for Plugin Metadata Access
- After registration, can we access plugin_version, determinism?
- Metadata inspection not tested

#### No Tests for Plugin Instance Lifecycle
- create_source() tested but on_start/on_complete not called
- Plugin lifecycle management not tested

#### No Tests for Config Validation Messages
- test_manager_validates_before_instantiation checks "path" in error
- But doesn't verify full error message quality

### 4. Discovery Tests

TestDiscoveryBasedRegistration class verifies:
- CSV source discovered
- All transforms discovered
- All sinks discovered

## Verdict
**PASS** - Good coverage of core PluginManager functionality. Gates not tested.

## Risk Assessment
- **Defects**: None
- **Overmocking**: None
- **Missing Coverage**: Medium - gates, lifecycle management
- **Tests That Do Nothing**: None
- **Inefficiency**: None
