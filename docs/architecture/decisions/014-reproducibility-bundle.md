# ADR 014 – Tamper-Evident Reproducibility Bundle

## Status

Accepted (2025-10-26)

## Context

Compliance programmes governing Elspeth deployments (government PSPF, HIPAA,
PCI-DSS, defence export control) require every experiment run to be reproducible
and independently auditable. Auditors must be able to answer:

- **What data, configuration, prompts and code produced this result?**
- **Were any artefacts modified after the run completed?**
- **Which security policy (clearance, downgrade rules) governed the execution?**

Prior to the Phase 1 migration, operators could collect outputs piecemeal
(results CSV, logs, config snapshots). That approach left material gaps:

- Artefacts could be deleted or modified post-run without detection.
- Policy metadata (`allow_downgrade`, clearance levels) was not bound to the
  recorded artefacts.
- Recreating the run required bespoke scripts per pipeline.

## Decision

Elspeth MUST emit a single, tamper-evident reproducibility bundle for every
experiment suite execution.

### Core Requirements

1. **Mandatory Reproducibility Sink**  
   - The `ReproducibilityBundleSink` (`src/elspeth/plugins/nodes/sinks/reproducibility_bundle.py`)
     is enabled by default in production templates (see
     `config/templates/production_suite.yaml`). Secure mode requires its presence.
   - Operators may only disable the sink via an explicit configuration switch once
     an organisation formally accepts the risk. The default remains “always on”.

2. **Comprehensive Contents** (default options)  
   The bundle captures and normalises:
   - Experiment results (JSON + sanitised CSV)
   - Source data snapshot (retained file or DataFrame export) and datasource config
   - Full merged configuration and rendered prompts
   - Plugin source code used during the run
   - Optional framework source code (toggle for high-assurance deployments)
   - All consumed artefacts from other sinks (logs, analytics outputs, etc.)
   - Sanitisation metadata (formula guard) and bundle options

3. **Cryptographic Integrity & Attestation**  
   - Every file written to the staging directory is hashed (SHA-256) and recorded
     in `MANIFEST.json`.
   - The manifest is signed using the configured algorithm via
     `elspeth.core.security.generate_signature`, producing `SIGNATURE.json`.
     Supported algorithms match ADR-001 requirements (`hmac-sha256`, `hmac-sha512`,
     `rsa-pss-sha256`, `ecdsa-p256-sha256`).
   - The final archive is a `.tar` with optional compression (`.tar.gz` et al.).
     The signed manifest and signature sit alongside all artefacts.
   - The emitted `Artifact` is flagged `persist=True` so downstream tooling
     (archive upload, provenance tracking) cannot discard it silently.

4. **Immutable Policy Metadata**  
   - The sink itself inherits `BasePlugin` with hard-coded
     `security_level=SecurityLevel.UNOFFICIAL` and `allow_downgrade=True`, aligning
     with ADR-002-B’s immutable policy mandate. Operators cannot lower the
     signing requirements or change the downgrade semantics via configuration.

5. **Audit Routing**  
   - The sink participates in the dual-output pipeline: other sinks hand their
     artefacts (including logs) to the bundle via `prepare_artifacts()`, ensuring
     the archive contains the authoritative copy of every generated file.

## Verification Procedure

### Automated Verification Tool

**Command-Line Interface**:
```bash
python -m elspeth.cli verify-bundle \
  --bundle-path outputs/bundle_2025-10-26_experiment-suite.tar.gz \
  --public-key /path/to/signing.pub  # For asymmetric algorithms only
```

**Verification Steps** (automated by tool):

1. **Extract Bundle**
   - Decompress archive to temporary directory
   - Verify archive integrity (checksums match)

2. **Load Manifest**
   - Parse `MANIFEST.json`
   - Verify manifest structure (required fields present)

3. **Verify File Hashes**
   - For each file listed in manifest:
     - Recompute SHA-256 hash
     - Compare with manifest hash
     - Report any mismatches

4. **Verify Signature**
   - Load `SIGNATURE.json`
   - Extract algorithm and signature value
   - Verify signature using configured algorithm:
     - **HMAC**: Requires `ELSPETH_SIGNING_KEY` environment variable
     - **RSA-PSS**: Requires public key file (`--public-key`)
     - **ECDSA**: Requires public key file (`--public-key`)

5. **Validate Policy Metadata**
   - Verify `security_level` present in manifest
   - Verify `allow_downgrade` documented
   - Check for ADR-002-B compliance (immutable fields)

---

### Manual Verification (Audit Process)

For compliance audits where automated tools may not be available:

#### Step 1: Extract Bundle
```bash
tar -xzf bundle_2025-10-26_experiment-suite.tar.gz -C /tmp/audit
cd /tmp/audit
```

**Expected Structure**:
```
/tmp/audit/
├── MANIFEST.json        # File inventory with hashes
├── SIGNATURE.json       # Cryptographic signature
├── results/
│   ├── results.json     # Experiment results
│   └── results.csv      # Sanitized CSV
├── config/
│   ├── merged_config.yaml
│   └── prompts/
├── source_data/
│   └── datasource_snapshot.csv
├── plugin_sources/
│   └── *.py             # Plugin code used
└── logs/
    └── run_*.jsonl      # Audit logs
```

---

#### Step 2: Verify Manifest Structure
```bash
cat MANIFEST.json | jq
```

**Required Fields**:
```json
{
  "version": "1.0",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2025-10-26T14:30:00Z",
  "security_level": "UNOFFICIAL",
  "allow_downgrade": true,
  "files": {
    "results/results.json": {
      "hash": "sha256:abc123...",
      "size": 1024,
      "modified": "2025-10-26T14:30:00Z"
    }
  }
}
```

---

#### Step 3: Recompute and Compare Hashes
```bash
# Create verification script
cat > verify_hashes.sh << 'EOF'
#!/bin/bash
MANIFEST="MANIFEST.json"

# Extract file list from manifest
jq -r '.files | keys[]' $MANIFEST | while read file; do
    # Get expected hash from manifest
    expected=$(jq -r ".files[\"$file\"].hash" $MANIFEST | cut -d: -f2)

    # Compute actual hash
    actual=$(sha256sum "$file" | awk '{print $1}')

    # Compare
    if [ "$expected" == "$actual" ]; then
        echo "✅ PASS: $file"
    else
        echo "❌ FAIL: $file (expected: $expected, actual: $actual)"
    fi
done
EOF

chmod +x verify_hashes.sh
./verify_hashes.sh
```

**Expected Output** (all files pass):
```
✅ PASS: results/results.json
✅ PASS: results/results.csv
✅ PASS: config/merged_config.yaml
✅ PASS: source_data/datasource_snapshot.csv
...
```

**Tamper Detection** (file modified):
```
✅ PASS: results/results.json
❌ FAIL: results/results.csv (expected: abc123..., actual: def456...)
✅ PASS: config/merged_config.yaml
...
```

---

#### Step 4: Verify Signature

**For HMAC (Symmetric Key)**:
```bash
# Set signing key from secure vault
export ELSPETH_SIGNING_KEY="your-secret-key-here"

# Recompute signature
python -c "
import json
import hmac
import hashlib
import os

# Load manifest
with open('MANIFEST.json', 'r') as f:
    manifest = f.read()

# Compute HMAC
key = os.environ['ELSPETH_SIGNING_KEY'].encode()
signature = hmac.new(key, manifest.encode(), hashlib.sha256).hexdigest()

# Load expected signature
with open('SIGNATURE.json', 'r') as f:
    sig_data = json.load(f)

# Compare
if signature == sig_data['signature']:
    print('✅ SIGNATURE VALID')
else:
    print('❌ SIGNATURE INVALID')
    print(f'Expected: {sig_data[\"signature\"]}')
    print(f'Actual:   {signature}')
"
```

**For RSA-PSS (Asymmetric Key)**:
```bash
# Verify using cryptography library
python -c "
import json
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

# Load public key
with open('signing.pub', 'rb') as f:
    public_key = serialization.load_pem_public_key(f.read(), backend=default_backend())

# Load manifest and signature
with open('MANIFEST.json', 'rb') as f:
    manifest = f.read()

with open('SIGNATURE.json', 'r') as f:
    sig_data = json.load(f)
    signature = bytes.fromhex(sig_data['signature'])

# Verify
try:
    public_key.verify(
        signature,
        manifest,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    print('✅ SIGNATURE VALID')
except Exception as e:
    print(f'❌ SIGNATURE INVALID: {e}')
"
```

---

#### Step 5: Audit Policy Metadata

**Check Security Policy**:
```bash
jq '.security_level, .allow_downgrade, .frozen_plugins' MANIFEST.json
```

**Expected Output**:
```json
"UNOFFICIAL"
true
[]
```

**Verification Checklist**:
- ✅ `security_level` is documented and matches pipeline configuration
- ✅ `allow_downgrade` policy is explicit (ADR-002-B compliance)
- ✅ Frozen plugins list matches expected (ADR-005)
- ✅ Run ID is unique and traceable
- ✅ Timestamp is within expected execution window

---

### Verification Output Examples

**Valid Bundle** (all checks pass):
```
Bundle Verification Report
==========================
Bundle: outputs/bundle_2025-10-26_experiment-suite.tar.gz
Run ID: 550e8400-e29b-41d4-a716-446655440000
Created: 2025-10-26T14:30:00Z

✅ Archive integrity: PASS
✅ Manifest structure: PASS
✅ File hashes (12 files): PASS
✅ Signature (hmac-sha256): PASS
✅ Policy metadata: PASS

Security Policy:
  - Level: UNOFFICIAL
  - Downgrade: allowed
  - Frozen plugins: []

RESULT: Bundle is tamper-free and cryptographically valid.
```

**Tampered Bundle** (file modified):
```
Bundle Verification Report
==========================
Bundle: outputs/bundle_2025-10-26_experiment-suite.tar.gz
Run ID: 550e8400-e29b-41d4-a716-446655440000
Created: 2025-10-26T14:30:00Z

✅ Archive integrity: PASS
✅ Manifest structure: PASS
❌ File hashes (12 files): FAIL
   - results/results.csv: Hash mismatch
     Expected: abc123def456...
     Actual:   789ghi012jkl...
✅ Signature (hmac-sha256): PASS
✅ Policy metadata: PASS

RESULT: Bundle has been tampered with. Do not trust results.
```

**Invalid Signature**:
```
Bundle Verification Report
==========================
Bundle: outputs/bundle_2025-10-26_experiment-suite.tar.gz
Run ID: 550e8400-e29b-41d4-a716-446655440000
Created: 2025-10-26T14:30:00Z

✅ Archive integrity: PASS
✅ Manifest structure: PASS
✅ File hashes (12 files): PASS
❌ Signature (hmac-sha256): FAIL
   Signature does not match manifest
✅ Policy metadata: PASS

RESULT: Bundle signature invalid. Manifest may have been modified.
```

---

### Integration with Compliance Workflows

**Quarterly Audit Process**:
1. Retrieve bundles from cold storage (S3, archive server)
2. Run automated verification tool on sample (10% of runs)
3. Generate compliance report showing verification pass rate
4. Investigate any failures (tamper vs key rotation)

**SOC2 Evidence**:
- Verification tool output serves as evidence of tamper detection capability
- Quarterly reports demonstrate ongoing monitoring
- Failed verifications trigger incident response (ADR-006)

**Tool Implementation Reference**:
- `src/elspeth/cli/verify_bundle.py` – CLI entry point
- `src/elspeth/core/security/bundle_verifier.py` – Verification logic
- `tests/test_bundle_verification.py` – Verification test suite

---

## Consequences

### Benefits

- **Tamper Evidence** – Any modification to archived artefacts or metadata is
  detectable by recomputing hashes and verifying `SIGNATURE.json`.
- **Single Source of Truth** – All inputs/outputs, prompts, config and code live
  in one archive, simplifying investigations and compliance attestations.
- **Policy Provenance** – Security policy choices (e.g. frozen vs trusted
  downgrade) are bound to the bundle as immutable metadata, aligning with
  ADR-002B.
- **Automation Friendly** – Downstream tooling (upload to cold storage, SOC
  ingestion) handles one deterministic artefact per run.

### Trade-offs / Risks

- **Storage Overhead** – Bundles include full source snapshots; large frameworks
  or datasets can inflate archive size. Operators may opt-out of framework code
  inclusion when appropriate.
- **Performance Cost** – Hashing and zipping incur runtime cost (tens of seconds
  for large suites). Pipelines should account for this in SLA estimates.
- **Key Management** – Signing requires securely provisioned HMAC/shared keys or
  asymmetric private keys. Organisations must integrate with HSM/KMS or manage
  secure environment variables (`ELSPETH_SIGNING_KEY`, etc.).

## Related ADRs

- **ADR-001** – Security-first priority & fail-closed mandate
- **ADR-002** – Multi-Level Security enforcement (pipeline clearance)
- **ADR-002-A** – Trusted container model (data lineage)
- **ADR-002-B** – Immutable security policy metadata
- **ADR-004** – Mandatory BasePlugin inheritance (“security bones”)
- **ADR-005** – Frozen plugin capability
- **ADR-006** – Security-critical exception policy (fail-loud invariants)
