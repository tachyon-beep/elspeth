# ATO Remediation Work Program

**Document Version:** 1.0
**Date:** 2025-10-15
**Status:** Active
**Owner:** Development Team
**Target Completion:** 2025-11-01

## Executive Summary

This work program addresses findings from the architectural assessment conducted for Authority to Operate (ATO) approval. All items are categorized by priority and include specific acceptance criteria, dependencies, and verification steps.

**Current Status:** 5 Must-Fix items, 5 Should-Fix items, 5 Nice-to-Have items
**Blocking Items for ATO:** 5 Must-Fix items must be completed before submission

---

## Must-Fix Items (ATO Blockers)

These items **must** be completed before ATO submission. Estimated total effort: 3-5 days.

### MF-1: Remove Legacy Dead Code ⚠️ HIGH PRIORITY

**Risk Level:** Medium
**Effort:** 2-4 hours
**Dependencies:** None
**Assigned To:** TBD

#### Description
The `old/` directory contains legacy code that is not used by the current system. This creates confusion, increases audit surface, and poses accidental execution risk.

#### Specific Tasks
1. **Verify no active references** (1 hour)
   ```bash
   # Search for any imports of old code
   grep -r "from old\." src/ tests/
   grep -r "import old\." src/ tests/

   # Search for references in documentation
   grep -r "old/" docs/ README.md
   ```
   - [ ] Confirm zero matches in active code
   - [ ] Document any references found in comments (to be updated)

2. **Archive legacy code** (30 min)
   ```bash
   # Create archive directory outside repo
   mkdir -p ../elspeth-archive/legacy-code-2025-10-15
   cp -r old/ ../elspeth-archive/legacy-code-2025-10-15/

   # Document what was archived
   cat > ../elspeth-archive/legacy-code-2025-10-15/README.md << 'EOF'
   # Elspeth Legacy Code Archive

   Date Archived: 2025-10-15
   Reason: ATO remediation - removing unused code
   Original Location: old/ directory in main repository

   This code represents the pre-refactoring architecture using the 'dmp' module namespace.
   It is preserved for historical reference only.

   DO NOT reintroduce this code into the active codebase.
   EOF
   ```
   - [ ] Archive created with README
   - [ ] Verify complete copy with: `diff -r old/ ../elspeth-archive/legacy-code-2025-10-15/old/`

3. **Remove from repository** (15 min)
   ```bash
   # Remove the directory
   git rm -r old/

   # Update .gitignore to prevent recreation
   echo "" >> .gitignore
   echo "# Prevent old/ directory from being recreated" >> .gitignore
   echo "old/" >> .gitignore
   ```
   - [ ] `old/` directory removed
   - [ ] `.gitignore` updated

4. **Update references in comments/docs** (30 min)
   - [ ] Search for "old/" or "legacy" in code comments
   - [ ] Update any references to indicate "archived 2025-10-15"
   - [ ] Update ARCHITECTURAL_REVIEW_2025.md to note removal

5. **Create ADR documenting removal** (1 hour)
   ```bash
   # Create Architectural Decision Record
   cat > docs/architecture/decisions/003-remove-legacy-code.md
   ```
   - [ ] ADR created explaining rationale
   - [ ] ADR references ATO requirements
   - [ ] ADR documents archive location

#### Acceptance Criteria
- [ ] Zero references to `old/` in active codebase
- [ ] `old/` directory removed from git history (HEAD)
- [ ] Archive created with documentation
- [ ] `.gitignore` prevents re-creation
- [ ] ADR documents decision
- [ ] All tests pass after removal
- [ ] No broken imports or references

#### Verification
```bash
# Final verification script
./scripts/verify-no-legacy-code.sh  # Create this script

# Should pass:
python -m pytest tests/
make lint
git grep "old/" | wc -l  # Should be 0 or only in CHANGELOG/ADR
```

---

### MF-2: Complete Plugin Registry Migration

**Risk Level:** Low
**Effort:** 1-2 days
**Dependencies:** None
**Assigned To:** TBD

#### Description
The codebase has partial migration to new `BasePluginRegistry` system. Both old and new patterns coexist, creating maintenance complexity and confusion.

#### Current State Analysis
```bash
# Identify files still using old registry pattern
grep -r "register_.*_plugin" src/elspeth/core/experiments/plugin_registry.py
grep -r "create_.*_plugin" src/elspeth/core/experiments/plugin_registry.py

# Identify files using new BasePluginRegistry
grep -r "BasePluginRegistry" src/elspeth/core/
```

#### Specific Tasks

1. **Audit current registry usage** (2 hours)
   - [ ] List all plugin registration calls
   - [ ] Document which use old pattern vs new pattern
   - [ ] Create migration checklist
   - [ ] File: `docs/architecture/REGISTRY_MIGRATION_STATUS.md`

2. **Migrate datasource registry** (3 hours)
   - [ ] Update `src/elspeth/core/datasource_registry.py` to use `BasePluginRegistry`
   - [ ] Migrate all datasource plugin registrations
   - [ ] Update factory functions to new signature
   - [ ] Add tests for new registry
   - [ ] Verify backward compatibility during transition

3. **Migrate LLM registry** (3 hours)
   - [ ] Update `src/elspeth/core/llm_registry.py` (already done, verify complete)
   - [ ] Ensure all LLM plugins use new pattern
   - [ ] Remove any old facade functions
   - [ ] Update tests

4. **Migrate sink registry** (3 hours)
   - [ ] Update `src/elspeth/core/sink_registry.py` to use `BasePluginRegistry`
   - [ ] Migrate all sink plugin registrations
   - [ ] Update factory functions
   - [ ] Add tests for new registry

5. **Migrate experiment plugin registry** (4 hours)
   - [ ] Update `src/elspeth/core/experiments/plugin_registry.py`
   - [ ] Migrate row plugins, aggregators, validators, early-stop plugins
   - [ ] Remove old `register_*_plugin` facade functions
   - [ ] Update all plugin modules to use new pattern
   - [ ] Update tests

6. **Remove deprecated code** (2 hours)
   - [ ] Remove `plugin_registry.py.backup` files if any exist
   - [ ] Remove old registry facade functions
   - [ ] Remove compatibility shims
   - [ ] Update imports across codebase

7. **Update documentation** (2 hours)
   - [ ] Update `docs/architecture/plugin-catalogue.md`
   - [ ] Update `CLAUDE.md` with new patterns
   - [ ] Update plugin development guide
   - [ ] Add examples of new registration pattern

#### Acceptance Criteria
- [ ] All registries use `BasePluginRegistry`
- [ ] No old registration patterns remain
- [ ] All plugins successfully register with new system
- [ ] Zero backward compatibility shims
- [ ] Documentation reflects new pattern only
- [ ] All tests pass
- [ ] No performance regression

#### Verification
```bash
# Verify migration complete
grep -r "def register_.*_plugin" src/elspeth/core/ | grep -v "BasePluginRegistry"
# Should return zero results

# Run full test suite
python -m pytest tests/ -v

# Run type checking
.venv/bin/python -m pytype src/elspeth
```

---

### MF-3: Enforce Secure Configuration Defaults

**Risk Level:** Medium
**Effort:** 1 day
**Dependencies:** None
**Assigned To:** TBD

#### Description
Implement safeguards to prevent users from accidentally disabling security features in production environments.

#### Specific Tasks

1. **Create secure mode environment detection** (2 hours)
   ```python
   # Add to src/elspeth/core/security/secure_mode.py

   import os
   from typing import Literal

   SecureMode = Literal["strict", "standard", "development"]

   def get_secure_mode() -> SecureMode:
       """Detect secure mode from environment."""
       mode = os.getenv("ELSPETH_SECURE_MODE", "standard").lower()
       if mode not in {"strict", "standard", "development"}:
           raise ValueError(f"Invalid ELSPETH_SECURE_MODE: {mode}")
       return mode  # type: ignore

   def is_production() -> bool:
       """Check if running in production mode."""
       return get_secure_mode() in {"strict", "standard"}
   ```
   - [ ] Module created with secure mode detection
   - [ ] Tests for mode detection
   - [ ] Documentation of mode levels

2. **Add configuration validation guards** (3 hours)
   ```python
   # Add to src/elspeth/core/config_validation.py

   from elspeth.core.security.secure_mode import get_secure_mode, is_production

   def validate_secure_settings(config: dict) -> None:
       """Validate that secure settings are enabled in production."""
       mode = get_secure_mode()

       # Check sanitization settings
       for sink in config.get("sinks", []):
           if sink.get("type") in {"csv_file", "excel"}:
               if not sink.get("sanitize_formulas", True):
                   if mode == "strict":
                       raise ConfigurationError(
                           "Formula sanitization cannot be disabled in strict mode"
                       )
                   elif mode == "standard":
                       logger.warning(
                           "⚠️  Formula sanitization disabled - outputs may contain injection risks"
                       )

       # Check audit logging settings
       for middleware in config.get("middleware", []):
           if middleware.get("type") == "audit_logger":
               if middleware.get("include_prompts") and is_production():
                   logger.warning(
                           "⚠️  Audit logging includes prompts - ensure logs are secured"
                       )

       # Check security level enforcement
       if mode == "strict":
           if not config.get("datasource", {}).get("security_level"):
               raise ConfigurationError(
                   "Datasource security_level required in strict mode"
               )
           if not config.get("llm", {}).get("security_level"):
               raise ConfigurationError(
                   "LLM security_level required in strict mode"
               )
   ```
   - [ ] Validation function created
   - [ ] Integrated into config loading
   - [ ] Tests for each validation case
   - [ ] Warning/error messages are clear

3. **Update CLI to validate before run** (1 hour)
   ```python
   # Update src/elspeth/cli.py

   from elspeth.core.config_validation import validate_secure_settings

   def main():
       # ... existing code ...

       # Validate secure settings
       try:
           validate_secure_settings(settings)
       except ConfigurationError as e:
           logger.error(f"Configuration validation failed: {e}")
           sys.exit(1)

       # ... continue with run ...
   ```
   - [ ] CLI calls validation before execution
   - [ ] Error handling with clear messages
   - [ ] Exit codes appropriate

4. **Create production config templates** (2 hours)
   - [ ] Create `config/templates/production-official.yaml`
   - [ ] Create `config/templates/production-protected.yaml`
   - [ ] Create `config/templates/production-secret.yaml`
   - [ ] Document required settings for each classification level
   - [ ] Add comments explaining security implications

5. **Document secure mode** (2 hours)
   - [ ] Update `docs/security-controls.md` with secure mode details
   - [ ] Update `CLAUDE.md` with production deployment guidance
   - [ ] Create `docs/deployment/PRODUCTION_DEPLOYMENT.md`
   - [ ] Add examples of setting `ELSPETH_SECURE_MODE`

#### Acceptance Criteria
- [ ] Secure mode detection implemented
- [ ] Configuration validation guards in place
- [ ] Strict mode prevents disabling security features
- [ ] Standard mode warns on risky settings
- [ ] Development mode allows flexibility
- [ ] Production config templates provided
- [ ] Documentation complete
- [ ] Tests cover all validation scenarios

#### Verification
```bash
# Test strict mode
export ELSPETH_SECURE_MODE=strict
python -m elspeth.cli --settings config/bad-config.yaml  # Should fail

# Test standard mode warnings
export ELSPETH_SECURE_MODE=standard
python -m elspeth.cli --settings config/risky-config.yaml 2>&1 | grep "⚠️"

# Test development mode (permissive)
export ELSPETH_SECURE_MODE=development
python -m elspeth.cli --settings config/test-config.yaml  # Should succeed
```

---

### MF-4: External Service Approval & Endpoint Lockdown

**Risk Level:** Medium
**Effort:** 4 hours
**Dependencies:** Coordination with security/compliance team
**Assigned To:** TBD

#### Description
Ensure external LLM service usage is approved and endpoints are locked down to prevent accidental data exfiltration.

#### Specific Tasks

1. **Document external service usage** (2 hours)
   - [ ] Create `docs/security/EXTERNAL_SERVICES.md`
   - [ ] List all external APIs used (OpenAI, Azure OpenAI, Azure Blob, etc.)
   - [ ] Document data flow for each service
   - [ ] Document classification levels allowed for each service
   - [ ] Create data flow diagram showing external connections
   - [ ] File: `docs/architecture/diagrams/external-data-flow.mermaid`

2. **Create approved endpoints configuration** (1 hour)
   ```python
   # Add to src/elspeth/core/security/approved_endpoints.py

   from typing import Dict, Set
   import os

   # Default approved endpoints (can be overridden by environment)
   APPROVED_ENDPOINTS: Dict[str, Set[str]] = {
       "azure_openai": {
           # Add your approved Azure regions
           "https://your-resource.openai.azure.com",
           "https://gov-approved-instance.openai.azure.com",
       },
       "http_openai": {
           # Only approved on-prem instances
           "http://internal-llm.yourorg.gov",
       },
       "azure_blob": {
           "https://approved-storage.blob.core.windows.net",
       },
   }

   def load_approved_endpoints() -> Dict[str, Set[str]]:
       """Load approved endpoints from environment or use defaults."""
       # Allow override via environment for different deployments
       env_endpoints = os.getenv("ELSPETH_APPROVED_ENDPOINTS_JSON")
       if env_endpoints:
           import json
           return json.loads(env_endpoints)
       return APPROVED_ENDPOINTS

   def validate_endpoint(service_type: str, endpoint: str) -> bool:
       """Validate that endpoint is approved for use."""
       approved = load_approved_endpoints()
       if service_type not in approved:
           return False  # Service type not in approved list
       return endpoint in approved[service_type]
   ```
   - [ ] Module created with endpoint validation
   - [ ] Tests for validation logic
   - [ ] Environment override capability

3. **Integrate endpoint validation into LLM clients** (2 hours)
   ```python
   # Update src/elspeth/plugins/nodes/transforms/llm/openai_http.py

   from elspeth.core.security.approved_endpoints import validate_endpoint
   from elspeth.core.security.secure_mode import get_secure_mode

   def __init__(self, api_base: str, ...):
       # Validate endpoint if in production mode
       if get_secure_mode() in {"strict", "standard"}:
           if not validate_endpoint("http_openai", api_base):
               raise ConfigurationError(
                   f"Endpoint not in approved list: {api_base}. "
                   f"For production use, only approved endpoints are allowed. "
                   f"See docs/security/EXTERNAL_SERVICES.md"
               )
       self.api_base = api_base
       # ... rest of init ...
   ```
   - [ ] Azure OpenAI client validates endpoints
   - [ ] HTTP OpenAI client validates endpoints
   - [ ] Clear error messages when validation fails
   - [ ] Development mode allows any endpoint (with warning)

4. **Update configuration templates** (30 min)
   - [ ] Update `config/templates/production-*.yaml` with approved endpoints
   - [ ] Add comments explaining endpoint requirements
   - [ ] Provide examples of setting `ELSPETH_APPROVED_ENDPOINTS_JSON`

5. **Create deployment checklist** (1 hour)
   - [ ] Create `docs/deployment/DEPLOYMENT_CHECKLIST.md`
   - [ ] Include steps for getting endpoint approval
   - [ ] Include verification steps
   - [ ] Include rollback procedures

#### Acceptance Criteria
- [ ] External services documented
- [ ] Data flow diagrams created
- [ ] Approved endpoints configured
- [ ] Endpoint validation implemented in all LLM clients
- [ ] Strict mode prevents unapproved endpoints
- [ ] Development mode allows testing
- [ ] Documentation complete
- [ ] Tests cover validation scenarios

#### Verification
```bash
# Test endpoint validation
export ELSPETH_SECURE_MODE=strict
python -m pytest tests/test_endpoint_validation.py -v

# Try to use unapproved endpoint (should fail)
python -m elspeth.cli --settings config/unapproved-endpoint.yaml
```

---

### MF-5: Conduct Penetration Testing

**Risk Level:** High
**Effort:** 2-3 days
**Dependencies:** MF-1 through MF-4 completed
**Assigned To:** Security team + Development team

#### Description
Perform code-assisted penetration testing and threat modeling before final ATO submission.

#### Specific Tasks

1. **Create test attack scenarios** (4 hours)
   - [ ] Formula injection via CSV input
   - [ ] Formula injection via LLM responses
   - [ ] Classification bypass attempts
   - [ ] Prompt injection attacks
   - [ ] Path traversal in file outputs
   - [ ] Malformed configuration files
   - [ ] Extremely large input datasets (DoS)
   - [ ] Concurrent access race conditions
   - [ ] Document in: `tests/security/ATTACK_SCENARIOS.md`

2. **Prepare malicious test inputs** (3 hours)
   ```bash
   # Create tests/security/test_data/
   mkdir -p tests/security/test_data

   # CSV with formula injection
   cat > tests/security/test_data/formula_injection.csv << 'EOF'
   id,input,expected_output
   1,=2+2,Safe content
   2,=cmd|'/c calc',Safe content
   3,@SUM(A1:A10),Safe content
   EOF

   # Config with classification bypass attempt
   cat > tests/security/test_data/classification_bypass.yaml << 'EOF'
   datasource:
     type: csv_local
     path: data/secret_data.csv
     security_level: public  # Attempting to lower classification
   llm:
     type: azure_openai
     security_level: public
   # ... rest of config ...
   EOF
   ```
   - [ ] Malicious CSV files created
   - [ ] Malicious config files created
   - [ ] Large test datasets created (memory stress test)
   - [ ] Documented in attack scenarios

3. **Implement security test suite** (8 hours)
   ```python
   # Create tests/security/test_security_hardening.py

   import pytest
   from elspeth.core.validation_base import ConfigurationError

   class TestFormulaInjectionDefense:
       """Test that formula injection is prevented."""

       def test_csv_formula_sanitized(self):
           """CSV output should sanitize formulas."""
           # ... test implementation ...

       def test_excel_formula_sanitized(self):
           """Excel output should sanitize formulas."""
           # ... test implementation ...

       def test_llm_response_formula_sanitized(self):
           """LLM responses containing formulas should be sanitized."""
           # ... test implementation ...

   class TestClassificationEnforcement:
       """Test that classification cannot be bypassed."""

       def test_cannot_lower_classification(self):
           """Should not allow lowering data classification."""
           # ... test implementation ...

       def test_sink_clearance_enforced(self):
           """Sinks should not access higher-classification data."""
           # ... test implementation ...

   class TestPromptInjection:
       """Test resilience to prompt injection attacks."""

       def test_prompt_shield_blocks_injection(self):
           """PromptShield should block injection attempts."""
           # ... test implementation ...

   class TestResourceExhaustion:
       """Test behavior under resource stress."""

       def test_large_dataset_handling(self):
           """Should handle large datasets gracefully."""
           # ... test implementation ...

       @pytest.mark.slow
       def test_memory_limits(self):
           """Should not exhaust memory on huge inputs."""
           # ... test implementation ...
   ```
   - [ ] All attack scenarios have corresponding tests
   - [ ] Tests verify security controls work
   - [ ] Tests document expected behavior
   - [ ] Tests include both positive and negative cases

4. **Execute penetration tests** (4 hours)
   ```bash
   # Run security test suite
   python -m pytest tests/security/ -v --tb=short

   # Run with coverage to identify untested paths
   python -m pytest tests/security/ --cov=src/elspeth --cov-report=html

   # Document results
   ```
   - [ ] All tests executed
   - [ ] Results documented
   - [ ] Any failures analyzed and fixed
   - [ ] Coverage report reviewed

5. **Manual security review** (4 hours)
   - [ ] Code review focusing on security-critical paths
   - [ ] Review all input validation logic
   - [ ] Review all external API calls
   - [ ] Review all file I/O operations
   - [ ] Review all configuration parsing
   - [ ] Document findings in: `docs/security/SECURITY_REVIEW_RESULTS.md`

6. **Create security test report** (2 hours)
   - [ ] Document test methodology
   - [ ] List all attack scenarios tested
   - [ ] Document test results (pass/fail)
   - [ ] Document any vulnerabilities found and remediation
   - [ ] Sign off by security team
   - [ ] File: `docs/security/PENETRATION_TEST_REPORT.md`

#### Acceptance Criteria
- [ ] All attack scenarios have automated tests
- [ ] All security tests pass
- [ ] No vulnerabilities found, or all found vulnerabilities remediated
- [ ] Manual code review completed
- [ ] Test report approved by security team
- [ ] Coverage of security-critical code ≥ 95%

#### Verification
```bash
# Run complete security test suite
python -m pytest tests/security/ -v --maxfail=0

# Verify coverage
python -m pytest tests/security/ --cov=src/elspeth \
  --cov-report=term-missing --cov-fail-under=95

# Generate final report
python scripts/generate_security_report.py > docs/security/FINAL_SECURITY_ASSESSMENT.md
```

---

## Should-Fix Items (Operational Excellence)

These items improve security and operational readiness but are not ATO blockers.

### SF-1: Implement Artifact Encryption Option

**Priority:** High
**Effort:** 2 days
**Dependencies:** MF-1 through MF-5 completed

#### Description
Add optional encryption for signed artifacts to protect data at rest.

#### Specific Tasks
1. **Design encryption approach** (2 hours)
   - [ ] Choose encryption algorithm (AES-256-GCM recommended)
   - [ ] Design key management approach
   - [ ] Document encryption architecture
   - [ ] File: `docs/architecture/decisions/004-artifact-encryption.md`

2. **Implement encryption sink** (6 hours)
   ```python
   # Create src/elspeth/plugins/nodes/sinks/encrypted_artifact.py

   from cryptography.fernet import Fernet
   from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
   import base64
   import os

   class EncryptedArtifactSink(ResultSink):
       """Encrypt and sign artifacts for maximum protection."""

       def __init__(
           self,
           base_path: str | Path,
           encryption_key: str | None = None,
           encryption_key_env: str | None = "ELSPETH_ENCRYPTION_KEY",
           signing_key: str | None = None,
           signing_key_env: str | None = "ELSPETH_SIGNING_KEY",
           # ... other options ...
       ):
           # ... implementation ...
   ```
   - [ ] Encryption sink implementation
   - [ ] Key derivation from password
   - [ ] Support for environment variable keys
   - [ ] Integration with signing (encrypt-then-sign)
   - [ ] Tests for encryption/decryption

3. **Create decryption utility** (3 hours)
   ```python
   # Create src/elspeth/tools/decrypt_artifact.py

   def decrypt_artifact(
       encrypted_path: Path,
       output_path: Path,
       encryption_key: str,
       verify_signature: bool = True,
       signing_key: str | None = None,
   ) -> None:
       """Decrypt an encrypted artifact bundle."""
       # ... implementation ...
   ```
   - [ ] CLI tool for decryption
   - [ ] Verification of signatures before decrypt
   - [ ] Clear error messages
   - [ ] Documentation

4. **Update documentation** (2 hours)
   - [ ] Update `docs/architecture/plugin-catalogue.md`
   - [ ] Create `docs/security/ENCRYPTION_GUIDE.md`
   - [ ] Add examples to production config templates
   - [ ] Update `CLAUDE.md`

#### Acceptance Criteria
- [ ] Encryption sink implemented and tested
- [ ] Decryption utility works correctly
- [ ] Keys managed securely (env vars, not hardcoded)
- [ ] Documentation complete
- [ ] Performance acceptable (<10% overhead)

---

### SF-2: Performance Optimization for Large Datasets

**Priority:** Medium
**Effort:** 3 days
**Dependencies:** None

#### Description
Implement streaming/chunked processing to handle very large datasets without memory exhaustion.

#### Specific Tasks
1. **Design streaming architecture** (4 hours)
   - [ ] Define StreamingDataSource protocol
   - [ ] Design memory budget controls
   - [ ] Design checkpoint/resume strategy for streaming
   - [ ] Document in ADR

2. **Implement streaming datasource** (8 hours)
   - [ ] Create `StreamingCSVDataSource`
   - [ ] Yield rows one at a time or in chunks
   - [ ] Integrate with ExperimentRunner
   - [ ] Tests for streaming mode

3. **Implement result streaming** (8 hours)
   - [ ] Modify ExperimentRunner to support streaming writes
   - [ ] Write results to sinks incrementally
   - [ ] Avoid accumulating all results in memory
   - [ ] Tests for memory usage

4. **Add memory monitoring** (4 hours)
   - [ ] Add memory usage tracking
   - [ ] Warn when approaching memory limits
   - [ ] Document memory requirements per workload size

#### Acceptance Criteria
- [ ] Can process 1M+ rows without memory exhaustion
- [ ] Memory usage stays constant regardless of input size
- [ ] Performance acceptable (throughput ≥ 100 rows/sec)
- [ ] Tests verify memory bounds

---

### SF-3: Enhanced Monitoring & Telemetry

**Priority:** Medium
**Effort:** 2 days
**Dependencies:** None

#### Description
Integrate with enterprise monitoring systems for operational visibility.

#### Specific Tasks
1. **Define metrics to track** (2 hours)
   - [ ] Request latency (LLM calls)
   - [ ] Error rates
   - [ ] Cost tracking
   - [ ] Security events (classification mismatches, etc.)
   - [ ] Document in: `docs/operations/METRICS.md`

2. **Implement OpenTelemetry integration** (6 hours)
   - [ ] Add OpenTelemetry dependencies
   - [ ] Create telemetry middleware
   - [ ] Export metrics to standard formats
   - [ ] Tests for telemetry

3. **Create monitoring dashboards** (4 hours)
   - [ ] Grafana dashboard JSON
   - [ ] Azure Monitor queries
   - [ ] Alerting rules
   - [ ] Documentation

#### Acceptance Criteria
- [ ] Metrics exported to OpenTelemetry
- [ ] Dashboards visualize key metrics
- [ ] Alerts configured for critical events
- [ ] Documentation complete

---

### SF-4: CLI Safety Improvements

**Priority:** Low
**Effort:** 1 day
**Dependencies:** None

#### Description
Add dry-run mode and confirmations to prevent accidental data operations.

#### Specific Tasks
1. **Implement --dry-run flag** (4 hours)
   - [ ] Add flag to CLI
   - [ ] Skip LLM calls in dry-run (or use mock)
   - [ ] Skip all sink writes
   - [ ] Log what would have been done
   - [ ] Tests for dry-run mode

2. **Add confirmation prompts** (3 hours)
   - [ ] Prompt before writing to external sinks
   - [ ] Prompt before expensive operations
   - [ ] Allow --yes flag to bypass (for automation)
   - [ ] Tests for confirmations

3. **Improve error messages** (1 hour)
   - [ ] Review all error messages for clarity
   - [ ] Add suggestions for common errors
   - [ ] Update documentation

#### Acceptance Criteria
- [ ] Dry-run mode works without side effects
- [ ] Confirmations prevent accidental operations
- [ ] Clear error messages guide users
- [ ] Tests verify safety features

---

### SF-5: Documentation Improvements

**Priority:** High
**Effort:** 2 days
**Dependencies:** MF-1 through MF-5 completed

#### Description
Update all documentation to reflect ATO remediations and production deployment.

#### Specific Tasks
1. **Update architecture documentation** (4 hours)
   - [ ] Update component diagrams
   - [ ] Update data flow diagrams
   - [ ] Update security controls documentation
   - [ ] Remove references to legacy code

2. **Create operations runbooks** (4 hours)
   - [ ] Deployment procedures
   - [ ] Incident response procedures
   - [ ] Monitoring and alerting procedures
   - [ ] Backup and recovery procedures

3. **Update user documentation** (3 hours)
   - [ ] Update CLAUDE.md with new patterns
   - [ ] Update plugin development guide
   - [ ] Update configuration examples
   - [ ] Add troubleshooting guide

4. **Create ATO documentation package** (4 hours)
   - [ ] System Security Plan updates
   - [ ] Control implementation statements
   - [ ] Test evidence
   - [ ] Deployment guide

#### Acceptance Criteria
- [ ] All documentation current and accurate
- [ ] No references to removed legacy code
- [ ] Operations procedures documented
- [ ] ATO package ready for submission

---

## Nice-to-Have Items (Future Enhancements)

These items can be scheduled post-ATO.

### NH-1: User Management & Multi-User Safety
**Effort:** 1 week
**Priority:** Low
**Target:** Q1 2026

### NH-2: Integration with Data Classification Systems
**Effort:** 1 week
**Priority:** Low
**Target:** Q1 2026

### NH-3: Extended Plugin Ecosystem
**Effort:** Ongoing
**Priority:** Medium
**Target:** Ongoing

### NH-4: Web UI or Dashboard
**Effort:** 2 weeks
**Priority:** Low
**Target:** Q2 2026

### NH-5: Continuous Improvement of Content Filters
**Effort:** Ongoing
**Priority:** Medium
**Target:** Ongoing

---

## Work Program Schedule

### Week 1 (Oct 16-20, 2025)
- **Day 1-2:** MF-1 (Remove Legacy Code) + MF-2 Start (Registry Migration)
- **Day 3-4:** MF-2 Continue (Registry Migration)
- **Day 5:** MF-2 Complete + MF-3 Start (Secure Config)

### Week 2 (Oct 23-27, 2025)
- **Day 1:** MF-3 Complete (Secure Config)
- **Day 2:** MF-4 (External Service Approval)
- **Day 3-5:** MF-5 (Penetration Testing)

### Week 3 (Oct 30 - Nov 3, 2025)
- **Day 1-2:** SF-1 (Artifact Encryption)
- **Day 3-5:** SF-5 (Documentation Updates)

### Week 4 (Nov 6-10, 2025)
- **Day 1-3:** SF-2 (Performance Optimization)
- **Day 4-5:** SF-3 (Monitoring & Telemetry)

---

## Testing Strategy

### Unit Testing
- Run after each task completion
- Command: `python -m pytest tests/ -v`
- Target: 100% of new code covered

### Integration Testing
- Run after each major component
- Test end-to-end workflows
- Verify no regressions

### Security Testing
- Run MF-5 test suite before ATO submission
- Re-run after any security-related changes
- Command: `python -m pytest tests/security/ -v`

### Performance Testing
- Run after SF-2 completion
- Benchmark memory usage with large datasets
- Document baseline performance

---

## Verification & Sign-Off

### Daily Verification
```bash
#!/bin/bash
# scripts/daily-verification.sh

echo "Running daily verification..."

# Run all tests
python -m pytest tests/ -v --tb=short || exit 1

# Run linting
make lint || exit 1

# Check for legacy code references
if git grep "from old\." src/ tests/; then
    echo "ERROR: Found references to old code"
    exit 1
fi

# Check secure mode is documented
if ! grep -q "ELSPETH_SECURE_MODE" docs/security/; then
    echo "WARNING: Secure mode not documented"
fi

echo "✅ Daily verification passed"
```

### Completion Checklist

#### Must-Fix Items
- [ ] MF-1: Legacy code removed
- [ ] MF-2: Registry migration complete
- [ ] MF-3: Secure configuration enforced
- [ ] MF-4: External services approved and locked down
- [ ] MF-5: Penetration testing completed and passed

#### Should-Fix Items
- [ ] SF-1: Artifact encryption implemented
- [ ] SF-2: Performance optimization complete
- [ ] SF-3: Monitoring integrated
- [ ] SF-4: CLI safety features added
- [ ] SF-5: Documentation updated

#### Final Verification
- [ ] All tests passing (100% success rate)
- [ ] Code coverage ≥ 80% overall, ≥ 95% security-critical
- [ ] No linting errors
- [ ] Documentation complete and accurate
- [ ] Security team sign-off obtained
- [ ] ATO documentation package prepared

---

## Rollback Procedures

### If Issues Found During Testing

1. **Stop work on current item**
2. **Document the issue** in GitHub Issues
3. **Assess impact** on ATO timeline
4. **Create fix plan** with revised estimates
5. **Communicate** to stakeholders

### If Need to Restore Legacy Code

```bash
# Emergency rollback (should not be needed)
git checkout <commit-before-removal> -- old/
git commit -m "EMERGENCY: Temporarily restore legacy code for investigation"

# Document why in commit message
# Create ticket to re-remove after investigation
```

---

## Communication Plan

### Daily Standup
- Progress on current tasks
- Blockers and risks
- Next 24-hour plan

### Weekly Report
- Completed items
- Upcoming items
- Risks and mitigations
- ATO timeline status

### Stakeholder Updates
- Every Friday: Email update to ATO sponsor
- Weekly: Demo of completed features
- Immediate: Notification of any timeline impacts

---

## Success Criteria

### ATO Submission Ready
- [ ] All Must-Fix items completed and verified
- [ ] All Should-Fix items completed (or documented as future work)
- [ ] Security test report approved
- [ ] Documentation package complete
- [ ] Stakeholder sign-off obtained

### Post-ATO Success
- [ ] System deployed to production
- [ ] Monitoring operational
- [ ] Incident response procedures tested
- [ ] User training completed
- [ ] 30-day operational review passed

---

## Appendices

### Appendix A: Tool Scripts

See `scripts/` directory for:
- `verify-no-legacy-code.sh` - Check for legacy code references
- `daily-verification.sh` - Daily health check
- `generate-security-report.py` - Create security assessment report

### Appendix B: Configuration Templates

See `config/templates/` for:
- `production-official.yaml` - OFFICIAL classification template
- `production-protected.yaml` - PROTECTED classification template
- `production-secret.yaml` - SECRET classification template

### Appendix C: Test Data

See `tests/security/test_data/` for:
- Attack scenario inputs
- Malicious configuration files
- Large dataset generators

---

**Document Control**

- **Version:** 1.0
- **Last Updated:** 2025-10-15
- **Next Review:** 2025-11-01
- **Owner:** Development Team Lead
- **Approvers:** Security Team, ATO Sponsor
