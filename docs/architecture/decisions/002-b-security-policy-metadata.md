# ADR 002-B – Immutable Security Policy Metadata

## Status

**IMPLEMENTED** (2025-10-27)

Extends [ADR-002](002-security-architecture.md), [ADR-005](005-frozen-plugin-capability.md)

**Implementation**: Sprint 3 (VULN-004) - Three-layer defense
- Layer 1 (e8c1c80): Schema enforcement with `additionalProperties: false`
- Layer 2 (e23aee3): Registry runtime rejection of security policy fields
- Layer 3 (6a92546, 3d18f10): Post-creation verification of declared vs actual
- See: `docs/implementation/VULN-004-registry-enforcement.md`

## Context

ADR-002 established multi-level security (MLS) enforcement based on plugin
clearances and data classifications. ADR-005 introduced explicit downgrade
policy (`allow_downgrade`) to control whether a plugin can operate below its
clearance. During Phase 2 migration (commits d103af5, 8a4b103), we discovered
that leaving security policy configurable by operators (via YAML/registry
options) recreates the same silent security gaps ADR-005 was designed to close.

### The Problem: Configuration-Driven Security Bypass

**Scenario**: Operator accidentally (or maliciously) overrides plugin security policy:

```yaml
# config/experiments/audit_review.yaml
datasource:
  type: "azure_blob_secret"
  container: "classified-data"
  security_level: "UNOFFICIAL"      # ← Override from SECRET to UNOFFICIAL!
  allow_downgrade: true             # ← Enable downgrade for frozen plugin!

sinks:
  - type: "public_csv"
    path: "outputs/public_report.csv"
    security_level: "UNOFFICIAL"
```

**Without ADR-002-B**: The registry accepts these overrides, creating a pipeline:
- Datasource believes it's UNOFFICIAL (overridden from SECRET)
- Pipeline operating_level = MIN(UNOFFICIAL, UNOFFICIAL) = UNOFFICIAL
- SECRET data flows into UNOFFICIAL sink → **security breach**

**With ADR-002-B**: Registry rejects the configuration at load time:
```
RegistrationError: Configuration exposes forbidden security policy fields:
{'security_level', 'allow_downgrade'}. These are plugin-author-owned and
immutable (ADR-002-B). Remove from YAML and accept plugin's declared policy.
```

### Root Cause

Security policy metadata (`security_level`, `allow_downgrade`, future
`max_operating_level`) serves two conflicting purposes:

1. **Construction parameter** – Needed by `BasePlugin.__init__()` (ADR-004)
2. **Security attestation** – Declared by plugin author, signed, certified

Treating these fields as "just another config parameter" allows operators to
silently drop security controls. This undermines:
- **Certification** – Auditors certify plugin code with specific security_level
- **Signing** – Manifests attest to plugin's declared policy
- **ADR-005 intent** – Frozen plugins (`allow_downgrade=False`) become unfrozen via YAML

## Decision

Security policy metadata is **immutable, author-owned, and signing-bound**:

### 1. Policy Field Classification

**Immutable Security Policy Fields** (cannot appear in configuration):
- `security_level: SecurityLevel` – Plugin's clearance (ADR-002)
- `allow_downgrade: bool` – Downgrade permission (ADR-005)
- `max_operating_level: SecurityLevel` – Future: upper bound on operations
- Any field controlling MLS enforcement behavior

**Mutable Behavior Fields** (normal configuration):
- `path: str`, `container: str`, `endpoint: str` – Data source locations
- `batch_size: int`, `timeout: int` – Performance tuning
- `format: str`, `encoding: str` – Data handling options
- Business logic parameters

**Rationale**: Security policy is a property of the **plugin implementation**,
not the **deployment configuration**. Operators choose *which plugin* to use,
not *how secure* that plugin behaves.

### 2. Registry Enforcement

All plugin registries MUST reject schemas exposing security policy fields:

```python
# src/elspeth/core/registries/base.py

class BasePluginRegistry(Generic[T]):
    """Base registry with mandatory security policy enforcement (ADR-002-B)."""

    # Centralized policy field inventory
    FORBIDDEN_CONFIG_FIELDS = frozenset({
        "security_level",
        "allow_downgrade",
        "max_operating_level",  # Future-proofing
    })

    def register(
        self,
        plugin_name: str,
        plugin_class: type[T],
        config_schema: dict | None = None,
    ) -> None:
        """Register plugin with schema validation.

        Args:
            plugin_name: Unique identifier for this plugin type
            plugin_class: Plugin class (must inherit BasePlugin per ADR-004)
            config_schema: JSONSchema for configuration validation

        Raises:
            RegistrationError: If schema exposes forbidden security policy fields
        """
        if config_schema:
            self._validate_schema_security(plugin_name, config_schema)

        # ... existing registration logic ...

    def _validate_schema_security(
        self,
        plugin_name: str,
        schema: dict,
    ) -> None:
        """Verify schema doesn't expose security policy fields (ADR-002-B).

        Raises:
            RegistrationError: If forbidden fields found in schema
        """
        properties = schema.get("properties", {})
        exposed_fields = self.FORBIDDEN_CONFIG_FIELDS & set(properties.keys())

        if exposed_fields:
            raise RegistrationError(
                f"Plugin '{plugin_name}' schema exposes forbidden security policy fields: "
                f"{exposed_fields}. These are author-owned and immutable (ADR-002-B). "
                f"Remove from schema - plugins declare security policy in code via "
                f"BasePlugin.__init__(security_level=..., allow_downgrade=...)."
            )
```

### 3. Factory Method Pattern

Plugin factories MUST strip security policy from operator-provided configuration:

```python
# src/elspeth/plugins/nodes/sources/azure_blob.py

class AzureBlobDataSource(BasePlugin, DataSource):
    """Datasource reading from Azure Blob Storage.

    SECURITY POLICY (ADR-002-B - immutable, code-declared):
        security_level: SECRET (handles classified government data)
        allow_downgrade: True (trusted to filter blobs by classification tag)
    """

    def __init__(
        self,
        *,
        container: str,
        account_url: str,
        credential: TokenCredential | None = None,
        # ← NO security_level parameter (not configurable)
        # ← NO allow_downgrade parameter (not configurable)
    ):
        """Initialize Azure datasource with IMMUTABLE security policy.

        Args:
            container: Blob container name
            account_url: Azure storage account URL
            credential: Optional Azure credential (defaults to DefaultAzureCredential)

        Security Policy (ADR-002-B):
            This plugin declares security_level=SECRET and allow_downgrade=True
            in code. Operators CANNOT override these via configuration.
        """
        # SECURITY POLICY: Hard-coded, not configurable
        super().__init__(
            security_level=SecurityLevel.SECRET,  # ← Author declares
            allow_downgrade=True,                  # ← Author declares
        )

        self.container = container
        self.account_url = account_url
        self.credential = credential or DefaultAzureCredential()


@dataclass
class AzureBlobDataSourceFactory:
    """Factory for creating Azure blob datasources from configuration."""

    def create(self, config: dict) -> AzureBlobDataSource:
        """Create datasource, stripping any security policy overrides.

        Args:
            config: Operator-provided configuration (from YAML)

        Returns:
            AzureBlobDataSource with code-declared security policy

        Security (ADR-002-B):
            Strips 'security_level' and 'allow_downgrade' from config if present.
            Plugin security policy is immutable and code-declared.
        """
        # STRIP security policy fields (operator cannot override)
        clean_config = {
            k: v for k, v in config.items()
            if k not in BasePluginRegistry.FORBIDDEN_CONFIG_FIELDS
        }

        return AzureBlobDataSource(**clean_config)
```

### 4. Signature Attestation

Published plugins include security policy in signing manifests:

```json
// outputs/reproducibility_bundle/MANIFEST.json
{
  "version": "1.0",
  "plugins": {
    "datasource": {
      "type": "azure_blob_secret",
      "version": "2.3.1",
      "security_policy": {
        "security_level": "SECRET",
        "allow_downgrade": true,
        "policy_version": "ADR-002-B"
      },
      "code_hash": "sha256:abc123...",
      "certification": {
        "auditor": "Security Team",
        "date": "2025-10-15",
        "scope": "Verified classification filtering at OFFICIAL and UNOFFICIAL levels"
      }
    }
  }
}
```

Security review verifies implementation matches declared policy prior to signing.

### 5. Documentation & Tooling

**Developer Guide** (`docs/development/plugin-authoring.md`) updates:
- Security policy fields listed as "code-only, never in schema"
- Factory pattern examples showing policy stripping
- Migration guide for existing plugins exposing these fields

**Lint Rules** (future enhancement):
```python
# ruff_plugins/check_plugin_schema.py
def check_schema_no_security_fields(schema: dict) -> list[str]:
    """Lint rule: Verify plugin schemas don't expose security policy."""
    forbidden = {"security_level", "allow_downgrade", "max_operating_level"}
    exposed = forbidden & set(schema.get("properties", {}).keys())

    if exposed:
        return [
            f"Schema exposes forbidden security policy fields: {exposed}. "
            f"Remove from schema (ADR-002-B)."
        ]
    return []
```

**CI Checks**: Test that all registered plugins have schemas without forbidden fields.

## Consequences

### Benefits

1. **Prevents Configuration-Driven Security Downgrades**
   - Operators cannot accidentally (or maliciously) override `allow_downgrade=False` via YAML
   - Resolves the Phase 2 regression where frozen plugins became unfrozen via config
   - Security policy remains consistent across all deployments of the same plugin version

2. **Signing/Attestation Accuracy**
   - Manifest signatures accurately reflect plugin's runtime security posture
   - Auditors can trust that certified security_level matches deployed behavior
   - No gap between "certified policy" and "runtime policy"

3. **Clear Separation of Concerns**
   - **Plugin Authors**: Declare security policy in code (security_level, allow_downgrade)
   - **Operators**: Configure behavior in YAML (paths, endpoints, performance tuning)
   - **Certifiers**: Audit code-declared policy, not deployment configs

4. **Defense in Depth** (combined with ADR-005)
   - Layer 1: Plugin author sets immutable policy in constructor
   - Layer 2: Registry rejects schemas exposing policy fields
   - Layer 3: Factory strips policy overrides from config
   - Layer 4: Tests verify registry enforcement

5. **Compliance Alignment**
   - Aligns with NIST SP 800-53 CM-2 (Baseline Configuration) – security policy is baseline
   - Supports change control requirements – policy changes require code review + certification
   - Audit trail: Git history shows policy changes, not operator YAML edits

### Limitations / Trade-offs

1. **Reduced Deployment Flexibility**
   - **Limitation**: Cannot adjust security_level per environment (dev vs prod) via config
   - **Rationale**: This is by design – security policy is a property of the plugin, not deployment
   - **Mitigation**: Create separate plugin classes for different security postures:
     ```python
     class DevDataSource(BasePlugin):  # For development
         def __init__(self, **kwargs):
             super().__init__(security_level=SecurityLevel.UNOFFICIAL, allow_downgrade=True)

     class ProdDataSource(BasePlugin):  # For production
         def __init__(self, **kwargs):
             super().__init__(security_level=SecurityLevel.SECRET, allow_downgrade=False)
     ```

2. **Breaking Change for Existing Configurations**
   - **Impact**: Existing YAML configs with `security_level:` or `allow_downgrade:` fields will fail
   - **Detection**: Registry raises `RegistrationError` at suite load time (fail-fast)
   - **Migration**: Provide automated tool to detect and remove overrides:
     ```bash
     # Migration script
     python scripts/migrate_adr002b.py --scan config/
     # Output: Found 3 files with security policy overrides (auto-fix available)

     python scripts/migrate_adr002b.py --fix config/
     # Removes security_level and allow_downgrade from YAML files
     ```

3. **Plugin Author Responsibility**
   - **Challenge**: Authors must choose correct security_level at implementation time
   - **Risk**: Incorrect choice requires new plugin version + re-certification
   - **Mitigation**:
     - Provide decision tree in plugin development guide
     - Mandatory security review for all new plugins
     - Clear certification checklist for each security_level

4. **Does Not Prevent T2 (Malicious Plugins Lying)**
   - **Out of Scope**: Malicious plugin can still lie about security_level in code
   - **ADR-002-B Scope**: Prevents *operators* from overriding policy, not *authors* from lying
   - **Existing Defense**: Code review + certification process verifies author honesty (unchanged)

### Implementation Impact

**Files to Create**:
- `scripts/migrate_adr002b.py` – Migration tool for existing configs (NEW)
- `tests/test_adr002b_registry_enforcement.py` – Registry validation tests (NEW)

**Files to Modify**:

1. **Core Registry** (`src/elspeth/core/registries/base.py`):
   - Add `FORBIDDEN_CONFIG_FIELDS` constant (~5 lines)
   - Add `_validate_schema_security()` method (~25 lines)
   - Call validation in `register()` method (~2 lines)

2. **All Plugin Factories** (~12-15 factories):
   - Add config stripping logic in `create()` methods
   - Example: `AzureBlobDataSourceFactory`, `CSVSinkFactory`, etc.
   - Pattern: ~5 lines per factory

3. **Plugin Schemas** (if any expose forbidden fields):
   - Remove `security_level`, `allow_downgrade` from JSONSchema `properties`
   - Add comment explaining ADR-002-B

4. **Documentation**:
   - `docs/development/plugin-authoring.md` – Add security policy section
   - `docs/architecture/plugin-catalogue.md` – Update all plugin entries
   - `docs/migration/ADR-002-B-MIGRATION.md` – Create migration guide (NEW)

**Testing Requirements**:

```python
# tests/test_adr002b_registry_enforcement.py

def test_registry_rejects_schema_with_security_level():
    """SECURITY: Registry rejects schemas exposing security_level."""
    registry = DatasourceRegistry()

    malicious_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "security_level": {"type": "string"},  # ← Forbidden!
        }
    }

    with pytest.raises(RegistrationError) as exc_info:
        registry.register("malicious_plugin", MockPlugin, malicious_schema)

    assert "forbidden security policy fields" in str(exc_info.value).lower()
    assert "security_level" in str(exc_info.value)
    assert "ADR-002-B" in str(exc_info.value)


def test_registry_accepts_schema_without_policy_fields():
    """Registry accepts valid schema without security policy fields."""
    registry = DatasourceRegistry()

    valid_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "batch_size": {"type": "integer"},
            # ✅ No security_level, allow_downgrade
        }
    }

    # Should not raise
    registry.register("valid_plugin", MockPlugin, valid_schema)


def test_factory_strips_security_overrides_from_config():
    """Factory removes security policy fields from operator config."""
    factory = AzureBlobDataSourceFactory()

    operator_config = {
        "container": "data",
        "account_url": "https://...",
        "security_level": "UNOFFICIAL",  # ← Operator trying to override
        "allow_downgrade": False,         # ← Operator trying to override
    }

    datasource = factory.create(operator_config)

    # Verify plugin has CODE-DECLARED policy, not config overrides
    assert datasource.security_level == SecurityLevel.SECRET  # Code-declared
    assert datasource.allow_downgrade is True                  # Code-declared


def test_all_registered_plugins_have_compliant_schemas():
    """SECURITY: Verify ALL registered plugins have ADR-002-B compliant schemas."""
    registries = [
        DatasourceRegistry(),
        SinkRegistry(),
        LLMClientRegistry(),
        # ... all registries
    ]

    violations = []
    for registry in registries:
        for plugin_name, plugin_info in registry.list_plugins().items():
            schema = plugin_info.get("schema")
            if not schema:
                continue

            exposed = BasePluginRegistry.FORBIDDEN_CONFIG_FIELDS & set(
                schema.get("properties", {}).keys()
            )

            if exposed:
                violations.append(f"{plugin_name}: {exposed}")

    assert not violations, (
        f"ADR-002-B VIOLATION: {len(violations)} plugins expose forbidden fields:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
```

**Migration Effort**: ~8-12 hours
- Core registry changes: 2 hours
- Factory updates (15 factories × 20 min): 5 hours
- Testing: 2 hours
- Documentation: 3 hours

**Risk Level**: MEDIUM
- **Breaking change**: Existing configs may fail (mitigated by migration tool)
- **Wide impact**: Touches all plugin factories (mitigated by consistent pattern)
- **Testing critical**: Must verify all plugins comply (comprehensive test suite)

## Migration Guide

### For Plugin Authors

**Before ADR-002-B** (insecure - policy configurable):
```python
class MyDataSource(BasePlugin):
    def __init__(self, *, path: str, security_level: SecurityLevel):
        # ❌ INSECURE: Operator can override via config
        super().__init__(security_level=security_level, allow_downgrade=True)
        self.path = path

# Schema exposes security_level
SCHEMA = {
    "properties": {
        "path": {"type": "string"},
        "security_level": {"type": "string"},  # ❌ Forbidden (ADR-002-B)
    }
}
```

**After ADR-002-B** (secure - policy immutable):
```python
class MyDataSource(BasePlugin):
    def __init__(self, *, path: str):
        # ✅ SECURE: Policy hard-coded in plugin
        super().__init__(
            security_level=SecurityLevel.SECRET,  # Code-declared
            allow_downgrade=True,                  # Code-declared
        )
        self.path = path

# Schema does NOT expose security_level
SCHEMA = {
    "properties": {
        "path": {"type": "string"},
        # ✅ No security_level (ADR-002-B compliant)
    }
}
```

### For Operators

**Before ADR-002-B**:
```yaml
# config/experiments/my_experiment.yaml
datasource:
  type: "my_datasource"
  path: "data.csv"
  security_level: "UNOFFICIAL"  # ❌ Will fail after ADR-002-B
```

**After ADR-002-B**:
```yaml
# config/experiments/my_experiment.yaml
datasource:
  type: "my_datasource"
  path: "data.csv"
  # ✅ No security_level (plugin declares it in code)
```

**Migration Script**:
```bash
# Scan for violations
python scripts/migrate_adr002b.py --scan config/

# Auto-fix (removes security policy fields)
python scripts/migrate_adr002b.py --fix config/

# Verify
python scripts/migrate_adr002b.py --verify config/
```

## Alternatives Considered

### Alternative 1: Keep Policy Configurable (Status Quo)

**Approach**: Allow operators to override security_level and allow_downgrade via YAML.

**Pros**:
- ✅ Maximum deployment flexibility
- ✅ No breaking changes
- ✅ Simpler implementation

**Cons**:
- ❌ Defeats purpose of ADR-005 (frozen plugins become unfrozen via config)
- ❌ Signing/attestation doesn't match runtime behavior
- ❌ Operators can accidentally create security vulnerabilities
- ❌ Certification becomes meaningless (certified code ≠ deployed behavior)

**Rejected**: This is the status quo that ADR-002-B is designed to fix.

### Alternative 2: Runtime Validation Only

**Approach**: Allow fields in schema but validate/reject overrides at runtime.

```python
def create(self, config: dict) -> Plugin:
    if "security_level" in config:
        raise ValueError("Cannot override security_level (ADR-002-B)")
    ...
```

**Pros**:
- ✅ Simpler implementation (no schema validation)
- ✅ Clear error messages at runtime

**Cons**:
- ❌ Later error detection (suite load time vs registration time)
- ❌ Requires consistent enforcement in all factories (easy to forget)
- ❌ No protection against accidentally exposing fields in schema

**Rejected**: Earlier detection (at registration) is preferable for fail-fast.

### Alternative 3: Separate Policy Declaration File

**Approach**: Declare security policy in separate `plugin_security.yaml`:

```yaml
# plugin_security.yaml
plugins:
  azure_blob_secret:
    security_level: "SECRET"
    allow_downgrade: true
```

**Pros**:
- ✅ Centralizes security policy
- ✅ Easy to audit all policies in one place

**Cons**:
- ❌ Policy separated from implementation (can drift)
- ❌ Doesn't prevent config overrides (still need enforcement)
- ❌ Extra file to maintain

**Rejected**: Policy should live with implementation code (single source of truth).

## Related Documents

- [ADR-001](001-design-philosophy.md) – Design Philosophy (security-first priority)
- [ADR-002](002-security-architecture.md) – Multi-Level Security Enforcement
- [ADR-002-A](002-a-trusted-container-model.md) – Trusted Container Model
- [ADR-004](004-mandatory-baseplugin-inheritance.md) – Mandatory BasePlugin Inheritance
- [ADR-005](005-frozen-plugin-capability.md) – Frozen Plugin Capability (allow_downgrade semantics)
- [ADR-014](014-reproducibility-bundle.md) – Reproducibility Bundle (policy attestation in manifests)
- `src/elspeth/core/registries/base.py` – Registry enforcement implementation
- `docs/development/plugin-authoring.md` – Plugin development guide

---

**Last Updated**: 2025-10-26
**Author(s)**: Architecture Team
**Deciders**: Security Team, Platform Team
**Status**: Proposed (pending security review)
