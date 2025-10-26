# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- **VULN-004: Configuration Override Attack Prevention** (Sprint 3, October 2025)
  - Implemented three-layer defense-in-depth system to enforce ADR-002-B immutable security policy
  - **Layer 1** (e8c1c80): Schema enforcement - All 12 plugin schemas now reject forbidden security policy fields (`security_level`, `allow_downgrade`, `max_operating_level`) via `additionalProperties: false`
  - **Layer 2** (e23aee3): Registry sanitization - Runtime validation in `create_*_from_definition()` functions explicitly rejects security policy fields with `ConfigurationError`
  - **Layer 3** (6a92546, 3d18f10): Post-creation verification - `BasePluginFactory.instantiate()` verifies plugin's actual `security_level` matches declared `security_level` from registry
  - **Bug Fix** (a0297a5): Fixed HttpOpenAIClient security level mismatch discovered by Layer 3 verification (registry declared UNOFFICIAL, plugin implemented OFFICIAL)
  - **Impact**: Configuration override attack vector eliminated - security policies are now truly immutable and declared in plugin code only, not configurable via YAML
  - **Breaking Change**: Plugin configurations in YAML that attempt to specify `security_level`, `allow_downgrade`, or `max_operating_level` will now fail with validation errors
  - **Test Coverage**: 43 new tests (Layer 1: 34 tests, Layer 2: 6 tests, Layer 3: 3 tests), full suite: 1500/1500 passing
  - Ref: [ADR-002-B](docs/architecture/decisions/002-security-architecture.md), [VULN-004 Implementation](docs/implementation/VULN-004-registry-enforcement.md)

### Changed

- Plugin option schemas no longer allow `security_level`, `allow_downgrade`, or `max_operating_level` fields
- `create_llm_from_definition()`, `create_datasource_from_definition()`, and `create_sink_from_definition()` now reject configurations containing security policy fields
- `BasePluginFactory.instantiate()` now enforces declared vs actual security level matching

## [0.1.0] - Previous Release

(Prior changelog entries would go here)
