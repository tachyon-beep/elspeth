# ADR 002-B – Immutable Security Policy Metadata (LITE)

## Status

**Proposed** (2025-10-26) - Extends ADR-002, ADR-005

## Context

ADR-005 introduced `allow_downgrade` policy, but leaving security policy configurable via YAML recreates silent security gaps ADR-005 was designed to close.

**Problem - Configuration Bypass**:

```yaml
# Operator accidentally/maliciously overrides
datasource:
  type: "azure_blob_secret"
  security_level: "UNOFFICIAL"    # ← Override from SECRET!
  allow_downgrade: true           # ← Enable downgrade for frozen plugin!
```

**Without ADR-002-B**: Registry accepts overrides → SECRET data flows to UNOFFICIAL sink → breach

**With ADR-002-B**: Registry rejects configuration:

```
RegistrationError: Configuration exposes forbidden security policy fields:
{'security_level', 'allow_downgrade'}. These are plugin-author-owned and
immutable (ADR-002-B).
```

**Root Cause**: Security policy serves two conflicting purposes:

1. Construction parameter (needed by `BasePlugin.__init__()`)
2. Security attestation (declared by author, signed, certified)

Treating as "just config" allows operators to silently drop security controls, undermining certification/signing/ADR-005.

## Decision

Security policy metadata is **immutable, author-owned, signing-bound**.

### 1. Field Classification

**Immutable Security Policy** (CANNOT appear in configuration):

- `security_level: SecurityLevel`
- `allow_downgrade: bool`
- `max_operating_level: SecurityLevel` (future)
- Any field controlling MLS enforcement

**Mutable Behavior** (normal configuration):

- `path`, `container`, `endpoint` (data locations)
- `batch_size`, `timeout` (performance)
- `format`, `encoding` (data handling)
- Business logic parameters

**Rationale**: Security policy is property of **plugin implementation**, not **deployment configuration**. Operators choose *which plugin*, not *how secure*.

### 2. Registry Enforcement

All registries MUST reject schemas exposing security policy:

```python
class BasePluginRegistry(Generic[T]):
    FORBIDDEN_CONFIG_FIELDS = frozenset({
        "security_level",
        "allow_downgrade",
        "max_operating_level",
    })
    
    def register(self, plugin_name, plugin_class, config_schema=None):
        if config_schema:
            self._validate_schema_security(plugin_name, config_schema)
    
    def _validate_schema_security(self, plugin_name, schema):
        properties = schema.get("properties", {})
        exposed = self.FORBIDDEN_CONFIG_FIELDS & set(properties.keys())
        
        if exposed:
            raise RegistrationError(
                f"Plugin '{plugin_name}' schema exposes forbidden fields: {exposed}. "
                "These are author-owned and immutable (ADR-002-B)."
            )
```

### 3. Factory Pattern

Factories MUST strip security policy from operator config:

```python
class AzureBlobDataSource(BasePlugin, DataSource):
    """SECURITY POLICY (ADR-002-B - immutable, code-declared):
    security_level: SECRET, allow_downgrade: True"""
    
    def __init__(self, *, container: str, account_url: str):
        # SECURITY POLICY: Hard-coded, not configurable
        super().__init__(
            security_level=SecurityLevel.SECRET,  # Author declares
            allow_downgrade=True,                  # Author declares
        )
        self.container = container
        self.account_url = account_url

class AzureBlobDataSourceFactory:
    def create(self, config: dict) -> AzureBlobDataSource:
        # STRIP security policy fields
        clean_config = {
            k: v for k, v in config.items()
            if k not in BasePluginRegistry.FORBIDDEN_CONFIG_FIELDS
        }
        return AzureBlobDataSource(**clean_config)
```

### 4. Signature Attestation

Manifests include security policy for verification:

```json
{
  "plugins": {
    "datasource": {
      "type": "azure_blob_secret",
      "security_policy": {
        "security_level": "SECRET",
        "allow_downgrade": true,
        "policy_version": "ADR-002-B"
      },
      "code_hash": "sha256:abc123...",
      "certification": { "auditor": "Security Team", "date": "2025-10-15" }
    }
  }
}
```

## Consequences

### Benefits

- **Configuration bypass prevented**: Operators can't override security policy via YAML
- **Certification meaningful**: Certified behavior = deployed behavior
- **Signing accurate**: Manifests match runtime policy
- **ADR-005 enforceable**: Frozen plugins stay frozen
- **Defense-in-depth**: Fifth layer (after ADR-001/002/002-A/004)

### Limitations

- **Breaking change**: Existing configs with policy overrides will fail
- **Migration required**: ~15 plugin factories need updates (~8-12 hours)
- **Less flexible**: Can't tune security per-deployment (intentional)

### Implementation Impact

- Core: Registry enforcement in `base.py`
- Plugins: ~15 factories updated to strip overrides
- Tests: 4 new tests (registry rejection, factory stripping, compliance scan)
- Configs: Migration script removes security policy fields from YAML

## Migration Guide

**Before (INSECURE)**:

```python
def __init__(self, *, path: str, security_level: SecurityLevel):
    super().__init__(security_level=security_level)  # ❌ Configurable
```

**After (SECURE)**:

```python
def __init__(self, *, path: str):
    super().__init__(security_level=SecurityLevel.SECRET)  # ✅ Hard-coded
```

**YAML Before**:

```yaml
datasource:
  type: "my_datasource"
  security_level: "UNOFFICIAL"  # ❌ Will fail
```

**YAML After**:

```yaml
datasource:
  type: "my_datasource"
  # ✅ No security_level (plugin declares in code)
```

**Migration Script**:

```bash
python scripts/migrate_adr002b.py --scan config/   # Find violations
python scripts/migrate_adr002b.py --fix config/    # Auto-remove fields
```

## Alternatives Rejected

1. **Keep configurable** (status quo): ❌ Defeats ADR-005, certification meaningless
2. **Runtime validation only**: ❌ Later error detection, inconsistent enforcement
3. **Separate policy file**: ❌ Policy drifts from implementation

## Related

ADR-001 (Philosophy), ADR-002 (MLS), ADR-002-A (Container), ADR-004 (BasePlugin), ADR-005 (Frozen), ADR-014 (Reproducibility)

---
**Last Updated**: 2025-10-26
**Status**: Proposed
