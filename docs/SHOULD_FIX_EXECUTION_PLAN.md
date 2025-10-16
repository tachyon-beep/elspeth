# Should-Fix Items - Execution Plan

**Date:** 2025-10-15
**Status:** Planning Phase
**Context:** All Must-Fix items (MF-1 through MF-5) are COMPLETE
**Goal:** Enhance operational excellence and production readiness

---

## Executive Summary

With all 5 Must-Fix items complete (21 hours, completed in 1 day), we now have capacity to address Should-Fix items before ATO submission. This plan prioritizes HIGH-priority items first, followed by MEDIUM and LOW priority items.

**Recommended Execution Order:**
1. **SF-5: Documentation Improvements** (2 days) - Highest impact, captures MF-1 through MF-5 completions
2. **SF-1: Artifact Encryption** (2 days) - High security value, complements existing signing
3. **SF-4: CLI Safety Improvements** (1 day) - Quick wins, prevents operational accidents
4. **SF-3: Monitoring & Telemetry** (2 days) - Operational visibility
5. **SF-2: Performance Optimization** (3 days) - Can be deferred post-ATO if needed

**Total Effort:** 10 days (2 weeks)
**Recommended Timeline:** Complete SF-5, SF-1, SF-4 before ATO submission (5 days)

---

## SF-5: Documentation Improvements ⭐ HIGH PRIORITY

**Effort:** 2 days
**Priority:** HIGH
**Dependencies:** MF-1 through MF-5 completed ✅
**Status:** Ready to start
**Rationale:** Critical for ATO submission; must reflect all recent changes

### Why This First?

1. **ATO Requirement:** Documentation package must be current for submission
2. **Captures Recent Work:** Documents all MF-1 through MF-5 completions
3. **Enables Review:** Allows stakeholders to review ATO-ready documentation
4. **Foundation for Operations:** Runbooks and procedures needed for deployment

### Detailed Task Breakdown

#### Task 1: Update Architecture Documentation (4 hours)

**Goal:** Ensure all architecture docs reflect current state post-MF-1 through MF-5

**Subtasks:**
1. **Update Component Diagrams** (1 hour)
   - Remove any legacy code references
   - Add secure mode enforcement points
   - Add endpoint validation flow
   - Tool: Mermaid diagrams in `docs/architecture/diagrams/`

2. **Update Data Flow Diagrams** (1 hour)
   - Document artifact pipeline security clearance flow
   - Show external service validation checkpoints
   - Document security level propagation
   - File: `docs/architecture/diagrams/data-flow-security.mermaid`

3. **Update Security Controls Documentation** (1.5 hours)
   - Add secure mode (STRICT/STANDARD/DEVELOPMENT) documentation
   - Add endpoint validation controls
   - Update formula sanitization documentation
   - Add penetration test results summary
   - File: `docs/architecture/security-controls.md`

4. **Review and Clean Up References** (30 min)
   - Search for "old/" references and remove
   - Search for "legacy" and update context
   - Verify all links work
   - Commands:
     ```bash
     grep -r "old/" docs/ | grep -v "archive"
     grep -r "legacy" docs/ | grep -v "historical"
     ```

**Acceptance Criteria:**
- ✅ All diagrams current (no legacy references)
- ✅ Security controls fully documented
- ✅ Data flows show security enforcement
- ✅ No broken links

#### Task 2: Create Operations Runbooks (4 hours)

**Goal:** Provide clear operational procedures for production deployment

**Subtasks:**
1. **Deployment Procedures** (1.5 hours)
   - Create `docs/operations/DEPLOYMENT_GUIDE.md`
   - Pre-deployment checklist (environment variables, approved endpoints, etc.)
   - Deployment steps (install, configure, verify)
   - Post-deployment verification
   - Rollback procedures

2. **Incident Response Procedures** (1 hour)
   - Create `docs/operations/INCIDENT_RESPONSE.md`
   - Classification of incidents (P0-P3)
   - Response procedures for each type
   - Escalation paths
   - Communication templates

3. **Monitoring and Alerting Procedures** (1 hour)
   - Create `docs/operations/MONITORING.md`
   - Key metrics to monitor
   - Alert thresholds
   - Response procedures for alerts
   - Dashboard setup (if SF-3 completed)

4. **Backup and Recovery Procedures** (30 min)
   - Create `docs/operations/BACKUP_RECOVERY.md`
   - What to back up (configs, outputs, logs)
   - Backup frequency
   - Recovery procedures
   - Test procedures

**Acceptance Criteria:**
- ✅ All 4 runbooks created and complete
- ✅ Procedures tested (where feasible)
- ✅ Stakeholder review completed
- ✅ Contact information current

#### Task 3: Update User Documentation (3 hours)

**Goal:** Ensure user-facing docs reflect new capabilities and patterns

**Subtasks:**
1. **Update CLAUDE.md** (1 hour)
   - Add secure mode documentation
   - Add endpoint validation examples
   - Update registry examples (post-MF-2)
   - Add penetration testing guidance
   - Remove any legacy code references

2. **Update Plugin Development Guide** (1 hour)
   - Update `docs/architecture/plugin-catalogue.md`
   - Show new context-aware factory patterns
   - Document security_level requirements
   - Add encrypted artifact sink (if SF-1 complete)
   - Update examples

3. **Update Configuration Examples** (30 min)
   - Ensure `config/templates/` reflects secure mode
   - Add comments explaining security implications
   - Update example suites in `config/sample_suite/`
   - Verify all examples work

4. **Add Troubleshooting Guide** (30 min)
   - Create `docs/TROUBLESHOOTING.md`
   - Common errors and solutions
   - Secure mode errors
   - Endpoint validation errors
   - Configuration errors
   - Links to relevant docs

**Acceptance Criteria:**
- ✅ CLAUDE.md reflects all new patterns
- ✅ Plugin guide current and accurate
- ✅ Config examples work and are secure
- ✅ Troubleshooting guide covers common issues

#### Task 4: Create ATO Documentation Package (4 hours)

**Goal:** Prepare complete documentation package for ATO submission

**Subtasks:**
1. **System Security Plan Updates** (1.5 hours)
   - Document secure mode enforcement
   - Document endpoint validation controls
   - Document formula sanitization
   - Document audit logging
   - Reference penetration test report
   - File: `docs/ato/SYSTEM_SECURITY_PLAN.md`

2. **Control Implementation Statements** (1.5 hours)
   - Create `docs/ato/CONTROL_IMPLEMENTATION.md`
   - Map each ATO control to implementation
   - Reference code locations
   - Reference test evidence
   - Sign-off section

3. **Test Evidence** (30 min)
   - Compile test results from MF-1 through MF-5
   - Include security test report
   - Include penetration test report
   - Include coverage reports
   - Organize in `docs/ato/evidence/`

4. **Deployment Guide for ATO** (30 min)
   - Create `docs/ato/DEPLOYMENT_GUIDE.md`
   - Production-specific deployment steps
   - Security checklist
   - Verification procedures
   - Sign-off template

**Acceptance Criteria:**
- ✅ System Security Plan current
- ✅ All controls mapped to implementations
- ✅ Test evidence compiled and organized
- ✅ Deployment guide production-ready
- ✅ ATO sponsor review completed

### SF-5 Timeline

**Day 1:**
- Morning: Task 1 (Architecture docs) - 4 hours
- Afternoon: Task 2 (Operations runbooks) - 4 hours

**Day 2:**
- Morning: Task 3 (User documentation) - 3 hours
- Afternoon: Task 4 (ATO package) - 4 hours
- Evening: Final review and stakeholder sign-off - 1 hour

**Total:** 16 hours (2 days)

### SF-5 Verification

```bash
# Check all links work
python scripts/check_docs_links.py

# Verify no legacy references
grep -r "old/" docs/ | grep -v "archive" | grep -v "historical"

# Verify diagrams render
ls docs/architecture/diagrams/*.mermaid | xargs -I {} mermaid-cli -i {}

# Final checklist
./scripts/verify-ato-documentation.sh
```

---

## SF-1: Implement Artifact Encryption Option ⭐ HIGH PRIORITY

**Effort:** 2 days
**Priority:** HIGH
**Dependencies:** MF-1 through MF-5 completed ✅
**Status:** Ready to start
**Rationale:** Enhances data-at-rest protection, complements existing signing

### Why This Second?

1. **Security Value:** Adds critical protection for confidential/secret artifacts
2. **Complements Existing Work:** Builds on signed_artifact sink from MF-3
3. **ATO Enhancement:** Demonstrates defense-in-depth approach
4. **Relatively Self-Contained:** Low risk of breaking existing functionality

### Detailed Task Breakdown

#### Task 1: Design Encryption Approach (2 hours)

**Goal:** Define encryption architecture and key management strategy

**Subtasks:**
1. **Choose Encryption Algorithm** (30 min)
   - Decision: **AES-256-GCM** (industry standard, FIPS 140-2 approved)
   - Rationale: Authenticated encryption, resistant to tampering
   - Library: Python `cryptography` package (Fernet or direct AES-GCM)

2. **Design Key Management** (1 hour)
   - **Option 1 (Recommended):** Environment variable keys
     - `ELSPETH_ENCRYPTION_KEY` for encryption key
     - `ELSPETH_SIGNING_KEY` for signing key (reuse existing)
   - **Option 2:** Key derivation from password (PBKDF2)
   - **Option 3:** Integration with Azure Key Vault (future enhancement)
   - Decision: Start with Option 1, support Option 2

3. **Document Encryption Architecture** (30 min)
   - Create ADR 005: Artifact Encryption
   - Document encrypt-then-sign pattern
   - Document key rotation procedures
   - File: `docs/architecture/decisions/005-artifact-encryption.md`

**Deliverable:** ADR 005 with encryption design

#### Task 2: Implement Encryption Sink (6 hours)

**Goal:** Create new sink that encrypts and signs artifacts

**Subtasks:**
1. **Create EncryptedArtifactSink** (3 hours)
   ```python
   # File: src/elspeth/plugins/nodes/sinks/encrypted_artifact.py

   from cryptography.fernet import Fernet
   from cryptography.hazmat.primitives import hashes
   from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
   import base64
   import os

   class EncryptedArtifactSink(ResultSink):
       """Encrypt and sign artifacts for maximum protection."""

       def __init__(
           self,
           base_path: str | Path,
           encryption_key: str | None = None,
           encryption_key_env: str = "ELSPETH_ENCRYPTION_KEY",
           password: str | None = None,  # Alternative: derive key from password
           signing_key: str | None = None,
           signing_key_env: str = "ELSPETH_SIGNING_KEY",
           include_manifest: bool = True,
           compress: bool = True,
       ):
           # Implementation
   ```

   - Load encryption key from env or parameter
   - Support password-based key derivation (PBKDF2)
   - Implement Fernet encryption (AES-128-CBC + HMAC-SHA256)
   - Integrate with existing signing logic

2. **Implement Encryption Logic** (2 hours)
   - Encrypt artifact data with Fernet
   - Generate manifest (same as signed_artifact)
   - Sign encrypted data + manifest (encrypt-then-sign)
   - Write encrypted bundle with metadata
   - Handle errors gracefully

3. **Add Compression Support** (30 min)
   - Optional gzip compression before encryption
   - Saves space, especially for text-heavy artifacts
   - Configurable via `compress` parameter

4. **Write Tests** (30 min)
   - Test encryption/decryption round-trip
   - Test with environment variable keys
   - Test with password-based key derivation
   - Test signature verification
   - Test error handling (bad keys, corrupted data)

**Deliverable:** Working EncryptedArtifactSink with tests

#### Task 3: Create Decryption Utility (3 hours)

**Goal:** Provide CLI tool to decrypt and verify encrypted artifacts

**Subtasks:**
1. **Implement Decryption Function** (1.5 hours)
   ```python
   # File: src/elspeth/tools/decrypt_artifact.py

   def decrypt_artifact(
       encrypted_path: Path,
       output_path: Path,
       encryption_key: str | None = None,
       password: str | None = None,
       verify_signature: bool = True,
       signing_key: str | None = None,
   ) -> None:
       """Decrypt an encrypted artifact bundle."""
       # 1. Load encrypted bundle
       # 2. Verify signature (if verify_signature=True)
       # 3. Decrypt data
       # 4. Decompress (if compressed)
       # 5. Write to output_path
   ```

2. **Create CLI Command** (1 hour)
   ```bash
   # Usage:
   python -m elspeth.tools.decrypt_artifact \
       --input encrypted_bundle.enc \
       --output decrypted_bundle \
       --encryption-key-env ELSPETH_ENCRYPTION_KEY \
       --verify-signature
   ```
   - Use `click` or `argparse` for CLI
   - Support reading keys from environment or prompts
   - Clear progress messages
   - Helpful error messages

3. **Write Tests** (30 min)
   - Test decryption of valid encrypted artifacts
   - Test signature verification
   - Test error handling (wrong key, corrupted data, missing signature)

**Deliverable:** Working decryption CLI tool with tests

#### Task 4: Update Documentation (2 hours)

**Goal:** Document encryption feature for users and operators

**Subtasks:**
1. **Update Plugin Catalogue** (30 min)
   - Add `encrypted_artifact` sink to `docs/architecture/plugin-catalogue.md`
   - Document parameters
   - Provide examples

2. **Create Encryption Guide** (1 hour)
   - File: `docs/security/ENCRYPTION_GUIDE.md`
   - When to use encryption vs signing
   - Key management best practices
   - How to rotate keys
   - How to decrypt artifacts
   - Security considerations

3. **Update Production Templates** (30 min)
   - Add encrypted_artifact sink to `config/templates/production-secret.yaml`
   - Add comments explaining when to use
   - Show example with environment variables

**Deliverable:** Complete encryption documentation

#### Task 5: Register and Integrate (1 hour)

**Goal:** Register sink in registry and ensure it works end-to-end

**Subtasks:**
1. **Register in Sink Registry** (15 min)
   - Add to `src/elspeth/core/registries/sink.py`
   - Create factory function
   - Add schema validation

2. **End-to-End Test** (30 min)
   - Run sample suite with encrypted_artifact sink
   - Verify encrypted bundle is created
   - Decrypt bundle and verify contents
   - Test: `tests/test_integration_encrypted_artifact.py`

3. **Performance Test** (15 min)
   - Measure encryption overhead
   - Target: <10% overhead
   - Document in ADR 005

**Deliverable:** Integrated and verified encrypted artifact sink

### SF-1 Timeline

**Day 1:**
- Morning: Task 1 (Design) + Task 2 start (Implementation) - 4 hours
- Afternoon: Task 2 complete (Implementation) - 4 hours

**Day 2:**
- Morning: Task 3 (Decryption utility) - 3 hours
- Afternoon: Task 4 (Documentation) + Task 5 (Integration) - 3 hours
- Evening: Final testing and verification - 1 hour

**Total:** 15 hours (2 days)

### SF-1 Verification

```bash
# Run encryption tests
pytest tests/test_encrypted_artifact.py -v

# End-to-end test
python -m elspeth.cli --settings config/test_encrypted.yaml --live-outputs
ls outputs/test_encrypted/encrypted_bundle.enc
python -m elspeth.tools.decrypt_artifact \
    --input outputs/test_encrypted/encrypted_bundle.enc \
    --output /tmp/decrypted \
    --verify-signature

# Verify contents match
diff -r outputs/test_encrypted/bundle /tmp/decrypted/

# Performance test
time python -m elspeth.cli --settings config/perf_test.yaml --live-outputs
```

### SF-1 Acceptance Criteria

- ✅ EncryptedArtifactSink implemented and tested
- ✅ Decryption utility works correctly
- ✅ Keys managed securely (environment variables, not hardcoded)
- ✅ Signature verification before decryption
- ✅ Documentation complete (ADR, guide, examples)
- ✅ Performance overhead <10%
- ✅ Integration tests passing
- ✅ Registered in sink registry

---

## SF-4: CLI Safety Improvements ⚡ LOW PRIORITY (Quick Win)

**Effort:** 1 day
**Priority:** LOW
**Dependencies:** None
**Status:** Ready to start
**Rationale:** Quick wins that prevent operational accidents

### Why This Third?

1. **Quick Win:** Can be completed in 1 day
2. **Operational Safety:** Prevents accidental data operations
3. **User Experience:** Better error messages improve usability
4. **Low Risk:** Additive changes, no breaking changes

### Detailed Task Breakdown

#### Task 1: Implement --dry-run Flag (4 hours)

**Goal:** Allow users to preview operations without side effects

**Subtasks:**
1. **Add Flag to CLI** (30 min)
   ```python
   # Update src/elspeth/cli.py

   @click.option(
       "--dry-run",
       is_flag=True,
       help="Preview operations without executing (no LLM calls, no sink writes)",
   )
   def main(..., dry_run: bool):
       if dry_run:
           logger.info("🔍 DRY-RUN MODE: No LLM calls or writes will be performed")
   ```

2. **Skip LLM Calls in Dry-Run** (1.5 hours)
   - Create `DryRunLLMClient` that returns mock responses
   - Inject into experiment runner when dry_run=True
   - Log what would have been called
   - Example: "Would call Azure OpenAI with prompt: ..."

3. **Skip Sink Writes** (1.5 hours)
   - Wrap all sinks with dry-run check
   - Log what would have been written
   - Example: "Would write 100 rows to outputs/results.csv"
   - Verify file operations: "Would create directory: outputs/"

4. **Write Tests** (30 min)
   - Test dry-run mode doesn't create files
   - Test dry-run mode logs operations
   - Test dry-run mode exits successfully
   - Test: `tests/test_cli_dry_run.py`

**Deliverable:** Working --dry-run flag

#### Task 2: Add Confirmation Prompts (3 hours)

**Goal:** Prevent accidental operations on production data

**Subtasks:**
1. **Identify Operations Requiring Confirmation** (30 min)
   - Writing to external sinks (Azure Blob, GitHub)
   - Expensive LLM operations (>100 rows)
   - Overwriting existing outputs

2. **Implement Confirmation Prompts** (1.5 hours)
   ```python
   # Add to src/elspeth/core/prompts/confirmation.py

   def confirm_operation(
       operation: str,
       details: str,
       bypass_with_flag: bool = True,
   ) -> bool:
       """Prompt user to confirm operation."""
       if os.getenv("ELSPETH_YES") == "1" or "--yes" in sys.argv:
           logger.info(f"Auto-confirming: {operation}")
           return True

       response = input(f"\n⚠️  {operation}\n{details}\nContinue? [y/N]: ")
       return response.lower() in ["y", "yes"]
   ```

3. **Integrate into CLI and Sinks** (30 min)
   - Call before expensive operations
   - Call before writes to external sinks
   - Respect --yes flag to bypass (for automation)

4. **Write Tests** (30 min)
   - Test prompts appear when expected
   - Test --yes bypasses prompts
   - Test ELSPETH_YES environment variable
   - Test: `tests/test_cli_confirmations.py`

**Deliverable:** Confirmation prompts for risky operations

#### Task 3: Improve Error Messages (1 hour)

**Goal:** Help users quickly understand and fix errors

**Subtasks:**
1. **Review Current Error Messages** (15 min)
   - Search for all `raise` statements
   - Identify unclear or unhelpful messages
   - Create improvement list

2. **Enhance Error Messages** (30 min)
   ```python
   # Before:
   raise ConfigurationError("Invalid security_level")

   # After:
   raise ConfigurationError(
       "Invalid security_level in datasource configuration.\n"
       f"  Found: {config.get('security_level')}\n"
       f"  Allowed: {ALLOWED_SECURITY_LEVELS}\n"
       "  See: docs/security/CLASSIFICATION_GUIDE.md"
   )
   ```
   - Add context (what was provided, what was expected)
   - Add documentation links
   - Add suggestions for common errors

3. **Test Error Messages** (15 min)
   - Trigger each error manually
   - Verify messages are helpful
   - Update tests to match new messages

**Deliverable:** Improved error messages with helpful guidance

### SF-4 Timeline

**Day 1:**
- Morning: Task 1 (--dry-run flag) - 4 hours
- Afternoon: Task 2 (Confirmation prompts) - 3 hours
- Evening: Task 3 (Error messages) - 1 hour

**Total:** 8 hours (1 day)

### SF-4 Verification

```bash
# Test dry-run mode
python -m elspeth.cli --settings config/sample_suite/settings.yaml --dry-run
# Should NOT create any files in outputs/

# Test confirmation prompts
python -m elspeth.cli --settings config/expensive_operation.yaml
# Should prompt before starting

# Test --yes bypass
python -m elspeth.cli --settings config/expensive_operation.yaml --yes
# Should NOT prompt

# Test error messages
python -m elspeth.cli --settings config/bad_config.yaml
# Should show helpful error with suggestions
```

### SF-4 Acceptance Criteria

- ✅ --dry-run mode works without side effects
- ✅ Dry-run logs all operations clearly
- ✅ Confirmation prompts appear for risky operations
- ✅ --yes flag bypasses prompts for automation
- ✅ Error messages include context and suggestions
- ✅ Documentation links in error messages work
- ✅ Tests verify all safety features

---

## SF-3: Enhanced Monitoring & Telemetry 📊 MEDIUM PRIORITY

**Effort:** 2 days
**Priority:** MEDIUM
**Dependencies:** None
**Status:** Ready to start
**Rationale:** Operational visibility for production deployment

### Why This Fourth?

1. **Operational Readiness:** Enables monitoring in production
2. **Post-Deployment Value:** Most valuable after deployment
3. **Can Be Deferred:** Not blocking ATO submission
4. **Moderate Complexity:** 2-day effort, best after quick wins

### Detailed Task Breakdown

#### Task 1: Define Metrics to Track (2 hours)

**Goal:** Identify key metrics for operational monitoring

**Subtasks:**
1. **Performance Metrics** (30 min)
   - LLM request latency (p50, p95, p99)
   - End-to-end experiment duration
   - Throughput (rows/second)
   - Document in: `docs/operations/METRICS.md`

2. **Error Metrics** (30 min)
   - LLM error rate
   - Configuration validation errors
   - Sink write failures
   - Rate limiter rejections

3. **Cost Metrics** (30 min)
   - Total cost per experiment
   - Cost per row
   - Token usage (prompt vs completion)
   - Cumulative daily/monthly costs

4. **Security Metrics** (30 min)
   - Security level mismatches
   - Endpoint validation rejections
   - Formula sanitization events
   - Secure mode violations

**Deliverable:** Metrics specification document

#### Task 2: Implement OpenTelemetry Integration (6 hours)

**Goal:** Export metrics to standard observability platforms

**Subtasks:**
1. **Add OpenTelemetry Dependencies** (30 min)
   ```bash
   pip install opentelemetry-api opentelemetry-sdk
   pip install opentelemetry-exporter-otlp
   ```

2. **Create Telemetry Middleware** (3 hours)
   ```python
   # File: src/elspeth/plugins/llms/middleware_telemetry.py

   from opentelemetry import metrics
   from opentelemetry.sdk.metrics import MeterProvider
   from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

   class TelemetryMiddleware(LLMMiddleware):
       """Export metrics to OpenTelemetry."""

       def __init__(self, exporter_endpoint: str = "http://localhost:4317"):
           self.meter = metrics.get_meter(__name__)
           self.request_counter = self.meter.create_counter(
               "elspeth.llm.requests",
               description="Number of LLM requests",
           )
           self.latency_histogram = self.meter.create_histogram(
               "elspeth.llm.latency",
               description="LLM request latency in seconds",
           )
           # ... more metrics ...
   ```

3. **Integrate with Experiment Runner** (1.5 hours)
   - Track experiment start/end
   - Track row processing metrics
   - Track aggregation metrics
   - Export to OpenTelemetry collector

4. **Configure Exporters** (30 min)
   - OTLP exporter (standard)
   - Console exporter (debugging)
   - Prometheus exporter (optional)

5. **Write Tests** (30 min)
   - Test metrics are recorded
   - Test exporters work
   - Mock OpenTelemetry collector
   - Test: `tests/test_telemetry_middleware.py`

**Deliverable:** Working OpenTelemetry integration

#### Task 3: Create Monitoring Dashboards (4 hours)

**Goal:** Provide pre-built dashboards for common monitoring platforms

**Subtasks:**
1. **Grafana Dashboard** (2 hours)
   - Create JSON dashboard definition
   - Panels for latency, error rate, cost
   - Alerts for high error rates
   - File: `docs/operations/dashboards/grafana-elspeth.json`

2. **Azure Monitor Queries** (1 hour)
   - KQL queries for common scenarios
   - Saved queries for deployment
   - File: `docs/operations/dashboards/azure-monitor-queries.kql`

3. **Alerting Rules** (30 min)
   - High error rate (>5%)
   - High latency (>10s p95)
   - Budget exceeded
   - Security violations
   - File: `docs/operations/ALERTING_RULES.md`

4. **Documentation** (30 min)
   - How to set up dashboards
   - How to configure alerts
   - How to interpret metrics
   - File: `docs/operations/MONITORING.md` (update)

**Deliverable:** Pre-built dashboards and alerting rules

### SF-3 Timeline

**Day 1:**
- Morning: Task 1 (Define metrics) + Task 2 start - 4 hours
- Afternoon: Task 2 continue - 4 hours

**Day 2:**
- Morning: Task 2 complete + Task 3 start - 4 hours
- Afternoon: Task 3 complete - 2 hours
- Evening: Testing and documentation - 2 hours

**Total:** 16 hours (2 days)

### SF-3 Verification

```bash
# Test telemetry middleware
pytest tests/test_telemetry_middleware.py -v

# Run with telemetry enabled
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
python -m elspeth.cli --settings config/sample_suite/settings.yaml --live-outputs

# Verify metrics exported
curl http://localhost:9090/metrics | grep elspeth

# Import Grafana dashboard
# (Manual verification in Grafana UI)
```

### SF-3 Acceptance Criteria

- ✅ Metrics specification complete
- ✅ OpenTelemetry integration implemented
- ✅ Metrics exported successfully
- ✅ Grafana dashboard works
- ✅ Azure Monitor queries work
- ✅ Alerting rules defined
- ✅ Documentation complete
- ✅ Tests passing

---

## SF-2: Performance Optimization for Large Datasets 🚀 MEDIUM PRIORITY

**Effort:** 3 days
**Priority:** MEDIUM
**Dependencies:** None
**Status:** Can be deferred post-ATO if needed
**Rationale:** Enables large-scale processing, but not required for initial ATO

### Why This Last?

1. **Can Be Deferred:** Not required for initial ATO submission
2. **Most Complex:** Requires architectural changes (streaming)
3. **Lower Priority:** Current implementation handles typical workloads
4. **Post-ATO Enhancement:** Can be added after initial deployment

### Detailed Task Breakdown

#### Task 1: Design Streaming Architecture (4 hours)

**Goal:** Define streaming data processing approach

**Subtasks:**
1. **Define StreamingDataSource Protocol** (1 hour)
   ```python
   # File: src/elspeth/core/base/protocols.py

   class StreamingDataSource(Protocol):
       """Protocol for streaming datasources."""

       def stream(self, *, chunk_size: int = 100) -> Iterator[pd.DataFrame]:
           """Yield data in chunks."""
           ...
   ```

2. **Design Memory Budget Controls** (1 hour)
   - Maximum memory per experiment
   - Automatic chunk size adjustment
   - Back-pressure mechanisms
   - Document in ADR 006

3. **Design Checkpoint/Resume Strategy** (1 hour)
   - Save progress after each chunk
   - Resume from checkpoint on failure
   - Checkpoint format and storage

4. **Document Architecture** (1 hour)
   - Create ADR 006: Streaming Architecture
   - Diagram data flow
   - Performance expectations
   - File: `docs/architecture/decisions/006-streaming-architecture.md`

**Deliverable:** Streaming architecture ADR

#### Task 2: Implement Streaming Datasource (8 hours)

**Goal:** Create streaming CSV datasource

**Subtasks:**
1. **Create StreamingCSVDataSource** (4 hours)
   ```python
   # File: src/elspeth/plugins/datasources/streaming_csv.py

   class StreamingCSVDataSource(DataSource):
       """Streaming CSV reader for large files."""

       def stream(self, chunk_size: int = 1000) -> Iterator[pd.DataFrame]:
           """Yield CSV rows in chunks."""
           for chunk in pd.read_csv(self.path, chunksize=chunk_size):
               yield chunk
   ```

2. **Integrate with ExperimentRunner** (2 hours)
   - Modify runner to support streaming mode
   - Process chunks incrementally
   - Write results to sinks incrementally

3. **Write Tests** (2 hours)
   - Test streaming with large CSV (10M rows)
   - Test memory usage stays constant
   - Test checkpoint/resume
   - Test: `tests/test_streaming_datasource.py`

**Deliverable:** Working streaming datasource

#### Task 3: Implement Result Streaming (8 hours)

**Goal:** Stream results to sinks without accumulating in memory

**Subtasks:**
1. **Modify ExperimentRunner** (4 hours)
   - Support `streaming=True` mode
   - Call sink.write() after each chunk
   - Avoid accumulating results in memory
   - Track progress across chunks

2. **Update Sinks for Streaming** (3 hours)
   - CSV sink: append mode
   - Excel sink: write chunks to separate sheets (or files)
   - JSON sink: streaming JSON (JSONL format)
   - Tests for each sink

3. **Write Tests** (1 hour)
   - Test memory usage with streaming
   - Test result correctness
   - Test performance
   - Test: `tests/test_streaming_results.py`

**Deliverable:** Streaming result processing

#### Task 4: Add Memory Monitoring (4 hours)

**Goal:** Track and warn about memory usage

**Subtasks:**
1. **Implement Memory Tracker** (2 hours)
   ```python
   # File: src/elspeth/core/monitoring/memory_tracker.py

   import psutil

   class MemoryTracker:
       """Track memory usage and warn on limits."""

       def check_memory(self, threshold_mb: int = 8000):
           """Check if memory usage is approaching limit."""
           process = psutil.Process()
           mem_mb = process.memory_info().rss / 1024 / 1024
           if mem_mb > threshold_mb:
               logger.warning(f"High memory usage: {mem_mb:.0f} MB")
   ```

2. **Integrate into ExperimentRunner** (1 hour)
   - Check memory after each chunk
   - Adjust chunk size if needed
   - Warn user if memory is high

3. **Document Memory Requirements** (1 hour)
   - Memory requirements per workload size
   - Recommendations for large datasets
   - File: `docs/performance/MEMORY_GUIDE.md`

**Deliverable:** Memory monitoring and documentation

### SF-2 Timeline

**Day 1:**
- Morning: Task 1 (Design) - 4 hours
- Afternoon: Task 2 start (Streaming datasource) - 4 hours

**Day 2:**
- Morning: Task 2 complete - 4 hours
- Afternoon: Task 3 start (Result streaming) - 4 hours

**Day 3:**
- Morning: Task 3 complete - 4 hours
- Afternoon: Task 4 (Memory monitoring) - 4 hours

**Total:** 24 hours (3 days)

### SF-2 Verification

```bash
# Test with large dataset (10M rows)
pytest tests/test_streaming_performance.py -v

# Monitor memory usage
python -m elspeth.cli \
    --settings config/streaming_test.yaml \
    --head 0 \
    --live-outputs \
    2>&1 | grep "Memory usage"

# Verify constant memory
# (Use memory profiler to verify memory doesn't grow with dataset size)
```

### SF-2 Acceptance Criteria

- ✅ StreamingDataSource protocol defined
- ✅ Streaming CSV datasource implemented
- ✅ Streaming result writing works
- ✅ Memory usage constant for large datasets
- ✅ Can process 1M+ rows without exhaustion
- ✅ Performance acceptable (≥100 rows/sec)
- ✅ Memory monitoring operational
- ✅ Documentation complete

---

## Execution Recommendations

### Recommended Prioritization

**Before ATO Submission (5 days):**
1. **SF-5: Documentation** (2 days) - CRITICAL for ATO
2. **SF-1: Encryption** (2 days) - HIGH security value
3. **SF-4: CLI Safety** (1 day) - Quick win, prevents accidents

**After ATO Submission (5 days):**
4. **SF-3: Monitoring** (2 days) - Operational readiness
5. **SF-2: Performance** (3 days) - Enhancement for large workloads

### Alternative: All Before ATO (10 days)

If timeline permits, complete all 5 Should-Fix items before ATO:
- Week 1: SF-5 + SF-1 (4 days)
- Week 2: SF-4 + SF-3 + SF-2 (6 days)

This would provide maximum ATO value and operational readiness.

### Deferred Approach

Minimum for ATO:
- **SF-5 only** (2 days) - Documentation must be current

Post-ATO enhancements:
- SF-1, SF-4, SF-3, SF-2 (8 days) - After ATO approval

---

## Success Criteria

### Overall Should-Fix Success

- ✅ All HIGH-priority items complete (SF-1, SF-5)
- ✅ Documentation package ATO-ready
- ✅ Encryption enhances security posture
- ✅ CLI safety prevents operational errors
- ✅ Monitoring enables production visibility
- ✅ Performance supports large-scale use cases
- ✅ All tests passing (100% success rate)
- ✅ No regressions from Must-Fix work

### Quality Gates

- All new code has ≥80% test coverage
- All new features documented
- All integration tests passing
- No performance regressions
- Security review completed (for SF-1)
- Stakeholder sign-off (for SF-5)

---

## Risk Mitigation

### Identified Risks

1. **Timeline Pressure:** Should-Fix items may delay ATO submission
   - **Mitigation:** Prioritize SF-5 only if needed; defer others post-ATO

2. **Integration Issues:** New features may break existing functionality
   - **Mitigation:** Comprehensive integration tests, gradual rollout

3. **Performance Regression:** Telemetry overhead may slow down processing
   - **Mitigation:** Performance tests, configurable telemetry

4. **Key Management Complexity:** Encryption key management may be difficult
   - **Mitigation:** Start simple (env vars), enhance later (Key Vault)

### Contingency Plans

- **If SF-5 takes longer:** Prioritize ATO documentation package only
- **If SF-1 encryption complex:** Defer key rotation, focus on basic encryption
- **If SF-2 performance complex:** Defer streaming, focus on memory monitoring
- **If any item blocks ATO:** Defer to post-ATO enhancement

---

## Daily Verification

```bash
#!/bin/bash
# Run after completing each Should-Fix item

echo "Should-Fix Verification..."

# Run all tests
python -m pytest tests/ -v --tb=short || exit 1

# Run specific Should-Fix tests
python -m pytest tests/test_encrypted_artifact.py -v 2>/dev/null
python -m pytest tests/test_cli_dry_run.py -v 2>/dev/null
python -m pytest tests/test_telemetry_middleware.py -v 2>/dev/null
python -m pytest tests/test_streaming_performance.py -v 2>/dev/null

# Check documentation
python scripts/check_docs_links.py

# Verify no regressions
python -m pytest tests/test_experiments.py -v

echo "✅ Should-Fix verification passed"
```

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Prioritize items** based on ATO timeline
3. **Begin with SF-5** (Documentation) if ready to proceed
4. **Update ATO_PROGRESS.md** as items complete
5. **Track progress daily** in Should-Fix section

---

**Document Version:** 1.0
**Created:** 2025-10-15
**Owner:** Development Team
**Approvers:** ATO Sponsor, Security Team
