# ADR 014 – Tamper-Evident Reproducibility Bundle (LITE)

## Status

Accepted (2025-10-26)

## Context

Compliance programs (PSPF, HIPAA, PCI-DSS, export control) require experiment runs be reproducible and independently auditable.

**Auditors must answer**:
- What data/config/prompts/code produced this result?
- Were artifacts modified post-run?
- Which security policy governed execution?

**Pre-Phase-1 gaps**:
- Artifacts could be deleted/modified without detection
- Policy metadata (`allow_downgrade`, clearance) not bound to artifacts
- Recreating runs required bespoke scripts

## Decision

Emit single, tamper-evident reproducibility bundle for every experiment suite.

### Core Requirements

1. **Mandatory Reproducibility Sink**
   - `ReproducibilityBundleSink` enabled by default in production templates
   - Operators may only disable via explicit risk acceptance
   - Default: always on

2. **Comprehensive Contents**
   - Experiment results (JSON + sanitized CSV)
   - Source data snapshot + datasource config
   - Full merged configuration + rendered prompts
   - Plugin source code used during run
   - Optional framework source code (high-assurance toggle)
   - All consumed artifacts from other sinks (logs, analytics)
   - Sanitization metadata + bundle options

3. **Cryptographic Integrity**
   - Every file → SHA-256 hash → recorded in `MANIFEST.json`
   - Manifest signed via `generate_signature` → `SIGNATURE.json`
   - Supported algorithms: `hmac-sha256`, `hmac-sha512`, `rsa-pss-sha256`, `ecdsa-p256-sha256`
   - Final archive: `.tar` (optional `.tar.gz` compression)
   - Artifact flagged `persist=True` (cannot be silently discarded)

4. **Immutable Policy Metadata**
   - Sink inherits `BasePlugin` with hard-coded `security_level=SecurityLevel.UNOFFICIAL`, `allow_downgrade=True`
   - Aligns with ADR-002-B immutable policy mandate
   - Operators cannot lower signing requirements via config

5. **Audit Routing**
   - Participates in dual-output pipeline (ADR-007)
   - Other sinks hand artifacts via `prepare_artifacts()`
   - Archive contains authoritative copy of every file

## Verification Procedure

### CLI Tool

```bash
python -m elspeth.cli verify-bundle \
  --bundle-path outputs/bundle_2025-10-26.tar.gz \
  --public-key /path/to/signing.pub  # Asymmetric only
```

**Automated steps**:
1. **Extract** - Decompress archive, verify integrity
2. **Load Manifest** - Parse `MANIFEST.json`, verify structure
3. **Verify Hashes** - Recompute SHA-256 for each file, compare with manifest
4. **Verify Signature** - Load `SIGNATURE.json`, validate against manifest
5. **Report** - Success ✅ or failures ❌ with details

### Bundle Structure

```
bundle_2025-10-26_experiment-suite.tar.gz
├── MANIFEST.json            # File hashes, metadata
├── SIGNATURE.json           # Cryptographic signature
├── config/
│   ├── merged_config.yaml   # Final merged configuration
│   └── rendered_prompts/    # Jinja2-rendered prompts
├── results/
│   ├── experiment_1.json    # Structured results
│   └── experiment_1.csv     # Sanitized results
├── data/
│   └── source_snapshot.csv  # Datasource snapshot
├── code/
│   ├── plugins/             # Plugin source code
│   └── framework/           # Optional: framework code
└── artifacts/
    ├── logs/                # Audit logs
    └── analytics/           # Generated reports
```

## Security Integration (ADR-002)

### Security Level Inheritance

- Bundle inherits pipeline's effective security level
- Classified bundles → cleared storage only (ADR-002 MLS)
- Sink clearance validated at construction (fail-fast)

### Signing Requirements

**HMAC** (shared secret):
```yaml
reproducibility_bundle:
  signing:
    algorithm: hmac-sha256
    secret_key_env: ELSPETH_SIGNING_KEY
```

**RSA-PSS** (asymmetric):
```yaml
reproducibility_bundle:
  signing:
    algorithm: rsa-pss-sha256
    private_key_path: /secure/keys/signing.pem
    public_key_path: /secure/keys/signing.pub
```

## Consequences

### Benefits
- **Audit compliance** - Single artifact for every run
- **Tamper detection** - Cryptographic integrity
- **Reproducibility** - All inputs captured
- **Policy binding** - Security metadata preserved
- **Chain of custody** - Signed manifest proves authenticity

### Limitations
- **Storage overhead** - Bundles can be large (source code + data)
- **Signing latency** - RSA signing ~100-500ms
- **Key management** - Operators must secure signing keys

### Mitigations
- **Compression** - `.tar.gz` reduces size 60-80%
- **Selective bundling** - Toggle framework code inclusion
- **Key rotation** - Document key lifecycle procedures

## Related

ADR-001 (Philosophy), ADR-002 (MLS), ADR-002-B (Immutable policy), ADR-007 (Dual-output)

---
**Last Updated**: 2025-10-26
