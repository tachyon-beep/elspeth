# ADR-002 Orchestrator Security Model - Clarification

**Document Purpose**: Clarifies the correct "minimum clearance envelope" model for ADR-002 implementation
**Date**: 2025-10-25
**Related**: `adr-002-implementation-gap.md`

---

## The Correct Security Model

### Minimum Clearance Envelope (Not "Datasource Blocks Low Sink")

**How it actually works:**

1. **Plugin Declaration Phase**: At job start, orchestrator asks all cryptographically signed plugins: "What security level do you need FOR THIS SPECIFIC JOB?"

   Plugins inspect their configuration and respond with the ACTUAL level needed (not their maximum capability).

   ```python
   # Example: Azure datasource is CAPABLE of SECRET, but THIS job accesses OFFICIAL data
   azure_datasource.get_security_level_for_job(config={
       'container': 'official-data-blob',
       'path': 'quarterly-reports/'
   })
   # Returns: 'OFFICIAL' (not 'SECRET')

   plugin_responses = {
       'datasource': 'OFFICIAL',    # Datasource checked: accessing OFFICIAL blob
       'llm_client': 'SECRET',      # LLM client: requires SECRET
       'sink_prod': 'SECRET',       # Sink: requires SECRET
       'sink_debug': 'UNOFFICIAL'   # Low security - ONE bad actor
   }
   ```

2. **Orchestrator Operating Level Computation**: Orchestrator looks at all responses and says "I'm operating at the MINIMUM level"

   ```python
   orchestrator.operating_level = min(plugin_responses.values())
   # => 'UNOFFICIAL' (because of sink_debug)

   # Note: Datasource reported OFFICIAL (not SECRET) because it inspected
   # the blob container and determined THIS job only accesses OFFICIAL data
   ```

3. **Start-Time Validation (MUST block)**: BEFORE any data retrieval, orchestrator validates each component can operate at the minimum level

   ```python
   for component_name, required_level in plugin_responses.items():
       if required_level > orchestrator.operating_level:
           raise SecurityError(
               f"Component '{component_name}' requires {required_level} "
               f"but orchestrator operating at {orchestrator.operating_level}. "
               f"Job CANNOT start."
           )

   # Result: Job fails because llm_client and sink_prod require SECRET
   # but orchestrator is at UNOFFICIAL (due to sink_debug)
   #
   # Note: Datasource reported OFFICIAL (not SECRET) because it inspected
   # the data source and determined it's only accessing OFFICIAL data for THIS job.
   # If it had reported SECRET, that would ALSO fail.
   ```

4. **Runtime Validation (Defense in Depth)**: Even if job somehow starts, **each plugin is responsible for its own behavior**

   ```python
   class SecretDataSource:
       security_level = SecurityLevel.SECRET

       def get_data(self, orchestrator_context):
           # Runtime check: Should NEVER come up if start-time validation works
           # BUT: If someone tricks the orchestrator, plugins still protect themselves
           if orchestrator_context.operating_level < self.security_level:
               raise SecurityError(
                   f"Datasource requires {self.security_level}, "
                   f"orchestrator operating at {orchestrator_context.operating_level}. "
                   f"REFUSING to hand over data (defense in depth failsafe)."
               )
           return self._actual_classified_data
   ```

---

## DataFrame Classification Metadata (Critical Runtime Defense)

### DataFrame Must Carry Classification

**CRITICAL REQUIREMENT**: DataFrames must remember their classification so that every component receiving data can validate they're not handling data above their clearance.

**Why this matters**: This is the **data-level runtime check**. Even if:
- Start-time validation is bypassed
- Orchestrator is compromised
- Component checks are bypassed

...the DataFrame itself carries its classification, and components validate incoming data.

### Implementation: ClassifiedDataFrame Wrapper

```python
class ClassifiedDataFrame:
    """DataFrame wrapper that carries immutable classification metadata.

    This enables runtime validation: every component receiving data can verify
    the data's classification matches their capability BEFORE processing.
    """

    def __init__(self, data: pd.DataFrame, classification: SecurityLevel):
        self._data = data
        self._classification = classification
        self._immutable_lock = True

    @property
    def data(self) -> pd.DataFrame:
        """Access the underlying DataFrame."""
        return self._data

    @property
    def classification(self) -> SecurityLevel:
        """Get the immutable classification of this data."""
        return self._classification

    def __setattr__(self, name, value):
        """Prevent modification of classification after creation."""
        if hasattr(self, '_immutable_lock') and name in ('_classification',):
            raise SecurityError("Cannot modify DataFrame classification after creation")
        super().__setattr__(name, value)
```

### Runtime Validation: Sink Example

```python
class UnofficialSink:
    """Sink for UNOFFICIAL test data only (e.g., MTG card test data)."""

    security_level = SecurityLevel.UNOFFICIAL

    def write(self, df: ClassifiedDataFrame):
        """Write data with classification validation.

        CRITICAL: Validate incoming data classification BEFORE processing.
        This is defense-in-depth - should NEVER trigger if start-time
        validation worked, but catches data spillage if orchestrator bypassed.
        """
        incoming_classification = df.classification

        # HARD ABORT if data classification exceeds sink capability
        if incoming_classification > self.security_level:
            raise SecurityError(
                f"CRITICAL DATA SPILLAGE ATTEMPT: "
                f"{self.security_level.value} sink received {incoming_classification.value} data. "
                f"HARD ABORT - refusing to process. "
                f"This should NEVER happen if start-time validation worked. "
                f"Possible security bypass attempt or orchestrator compromise."
            )

        # Safe to write - data classification matches sink capability
        self._write_to_storage(df.data)


class OfficialSink:
    """Sink for OFFICIAL data (Archive Act implications)."""

    security_level = SecurityLevel.OFFICIAL

    def write(self, df: ClassifiedDataFrame):
        """Write with classification validation."""
        incoming = df.classification

        if incoming > self.security_level:
            raise SecurityError(
                f"OFFICIAL sink received {incoming.value} data - HARD ABORT. "
                f"Archive Act compliance violation risk."
            )

        # OFFICIAL sink can safely handle OFFICIAL or UNOFFICIAL data
        # (downgrade is safe: writing UNOFFICIAL to OFFICIAL sink is OK)
        self._write_with_archive_act_compliance(df.data)
```

### Datasource Sets Classification

```python
class AzureDataSource:
    """Datasource that inspects blob classification and tags DataFrame."""

    def get_security_level_for_job(self, config: dict) -> SecurityLevel:
        """Inspect blob to determine classification (called at job start)."""
        container = config['container']
        blob_metadata = azure.get_blob_metadata(container)
        return SecurityLevel.from_string(blob_metadata['classification'])

    def read_data(self, config: dict) -> ClassifiedDataFrame:
        """Read data and tag with classification metadata."""
        # Read the raw data
        raw_data = pd.read_csv(azure_blob_url)

        # Get actual classification from blob metadata
        classification = self.get_security_level_for_job(config)

        # Wrap in ClassifiedDataFrame with immutable classification
        return ClassifiedDataFrame(raw_data, classification)
```

### Classification Uplifting: The "High Water Mark" Principle

**CRITICAL SECURITY PRINCIPLE**: When data passes through a higher-classification component, the output inherits the higher classification level. Classification can only go UP, never down.

**Why**: A SECRET-level LLM (fine-tuned on SECRET data) processing OFFICIAL data produces SECRET output because:
1. The model may leak information from its SECRET training data
2. The model's behavior itself may reveal classified patterns
3. Conservative security requires treating output as highest classification in the processing chain

This is **automatic and non-negotiable** - plugins don't decide, the framework enforces.

### LLM Transform with Classification Uplifting

```python
class LLMTransform:
    """LLM transforms with automatic classification uplifting."""

    security_level = SecurityLevel.SECRET  # LLM trained on SECRET data

    def transform(self, input_df: ClassifiedDataFrame) -> ClassifiedDataFrame:
        """Transform data with automatic classification uplifting.

        Output classification = max(input classification, LLM classification)
        """
        # Validate we can handle this classification
        if input_df.classification > self.security_level:
            raise SecurityError(
                f"LLM transform requires {self.security_level}, "
                f"received {input_df.classification} data"
            )

        # Process data
        transformed = self._llm_process(input_df.data)

        # CRITICAL: Output classification uplifted to component level
        # OFFICIAL input → SECRET LLM → SECRET output (automatically)
        output_classification = max(input_df.classification, self.security_level)

        return ClassifiedDataFrame(transformed, output_classification)
```

**Example Scenarios**:

```python
# Scenario 1: OFFICIAL data through SECRET LLM
input_df = ClassifiedDataFrame(data, SecurityLevel.OFFICIAL)
secret_llm = LLMTransform(security_level=SecurityLevel.SECRET)
output_df = secret_llm.transform(input_df)
# output_df.classification == SecurityLevel.SECRET (uplifted)

# Scenario 2: OFFICIAL data through OFFICIAL LLM
input_df = ClassifiedDataFrame(data, SecurityLevel.OFFICIAL)
official_llm = LLMTransform(security_level=SecurityLevel.OFFICIAL)
output_df = official_llm.transform(input_df)
# output_df.classification == SecurityLevel.OFFICIAL (no uplift)

# Scenario 3: SECRET data through SECRET LLM
input_df = ClassifiedDataFrame(data, SecurityLevel.SECRET)
secret_llm = LLMTransform(security_level=SecurityLevel.SECRET)
output_df = secret_llm.transform(input_df)
# output_df.classification == SecurityLevel.SECRET (already at max)
```

**Critical Implication**: Even if a pipeline starts with OFFICIAL data, if it passes through a SECRET-level LLM, the output MUST go to a SECRET-level sink. The orchestrator's start-time validation will catch this:

```python
# This configuration FAILS at start time:
# - Datasource: OFFICIAL blob
# - LLM: SECRET (fine-tuned on SECRET data)
# - Sink: OFFICIAL
#
# Orchestrator computes: min(OFFICIAL, SECRET, OFFICIAL) = OFFICIAL
# Validation: SECRET LLM cannot operate at OFFICIAL envelope → FAIL TO START
```

### Defense in Depth: Three Validation Layers

**Layer 1: Start-Time (PRIMARY - MUST BLOCK)**
- Orchestrator collects security levels from all plugins
- Computes operating level (minimum)
- Validates ALL components can operate at that level
- Job **fails to start** if misconfigured

**Layer 2: Component Runtime Validation (FAILSAFE)**
- Each component validates orchestrator operating level
- Should NEVER trigger if Layer 1 works
- Catches orchestrator compromise

**Layer 3: Data Classification Validation (DEEP DEFENSE)**
- DataFrame carries immutable classification
- Every component validates incoming data classification
- Should NEVER trigger if Layer 1 and 2 work
- Catches data mislabeling or classification tampering

**All three layers must be bypassed** for a security violation to occur.

### Inherited Behavior: BasePlugin Enforcement

**Key insight**: Data classification validation should be inherited behavior, not manually implemented in every plugin.

```python
class BasePlugin(ABC):
    """Base class for all plugins with automatic classification enforcement.

    All plugins inherit this validation logic - they DON'T refuse to hand out
    data AND refuse to accept data they can't handle.

    This is the same mechanic on both sides:
    - Sources: Don't hand out data above recipient's clearance
    - Sinks: Don't accept data above own clearance
    - Transforms: Don't process data above own clearance
    """

    security_level: SecurityLevel

    def _validate_can_handle_data(self, df: ClassifiedDataFrame) -> None:
        """Inherited validation: refuse data above clearance.

        CRITICAL: This is called AUTOMATICALLY before any data processing.
        All plugins inherit this protection.
        """
        if df.classification > self.security_level:
            raise SecurityError(
                f"SECURITY VIOLATION: {self.__class__.__name__} "
                f"({self.security_level.value} clearance) "
                f"received {df.classification.value} data. "
                f"HARD ABORT - refusing to process. "
                f"Possible data spillage or orchestrator bypass attempt."
            )

    @abstractmethod
    def _process_data(self, df: ClassifiedDataFrame) -> Any:
        """Subclasses implement actual data processing logic."""
        pass

    def process(self, df: ClassifiedDataFrame) -> Any:
        """Public method with automatic classification validation.

        All data processing goes through this method, ensuring validation
        happens BEFORE plugin-specific logic executes.
        """
        # Inherited validation (automatic - can't be skipped)
        self._validate_can_handle_data(df)

        # Plugin-specific processing (only if validation passed)
        return self._process_data(df)
```

**Example: Sink Implementation**

```python
class UnofficialSink(BasePlugin):
    """Sink for UNOFFICIAL test data.

    Inherits classification validation - doesn't need manual checks.
    """

    security_level = SecurityLevel.UNOFFICIAL

    def _process_data(self, df: ClassifiedDataFrame) -> None:
        """Write data to storage.

        By the time this runs, BasePlugin._validate_can_handle_data()
        has already verified df.classification <= UNOFFICIAL.

        No manual validation needed - inherited behavior protects us.
        """
        self._write_to_storage(df.data)
```

**Example: Source Implementation**

```python
class AzureDataSource(BasePlugin):
    """Datasource that reads from Azure blob storage.

    Inherits classification validation when passing data to next component.
    """

    def read_data(self, config: dict) -> ClassifiedDataFrame:
        """Read and classify data."""
        raw_data = pd.read_csv(azure_blob_url)
        classification = self._inspect_blob_classification(config)
        return ClassifiedDataFrame(raw_data, classification)

    def pass_to_next_component(
        self, df: ClassifiedDataFrame, recipient: BasePlugin
    ) -> None:
        """Pass data to next component with validation.

        Inherited validation ensures recipient can handle this data.
        """
        # recipient.process(df) will automatically call
        # recipient._validate_can_handle_data(df) before processing
        recipient.process(df)
```

**Benefits of Inherited Behavior**:

1. **Automatic enforcement**: Can't forget to add validation
2. **Consistent behavior**: All plugins protected the same way
3. **Tamper-resistant**: Validation in base class, not overrideable
4. **Same mechanic both sides**: Sources refuse to hand out, sinks refuse to accept
5. **Defense in depth**: Even if orchestrator bypassed, every plugin validates

**Symmetric Protection**:
- **Source → Transform**: Transform validates incoming data
- **Transform → Sink**: Sink validates incoming data
- **Every handoff**: Recipient validates before processing

**Result**: Data classification is validated at EVERY component boundary, creating defense in depth even if orchestrator is compromised.

---

## Key Principles

### 1. Orchestrator Operates at Minimum (Clearance Envelope)

**Mental model**: The orchestrator is like a "clearance envelope". It operates at the LOWEST clearance level among all participants.

- ✅ Low-security components happy in high-security envelope (they just won't see classified data)
- ❌ High-security components refuse to participate in low-security envelope

**NOT**: "High-security datasource blocks low-security sink"

**YES**: "Orchestrator operates at minimum; high-security components refuse low-envelope"

**CRITICAL NUANCE**: Plugins report their security level FOR THIS SPECIFIC JOB, not their maximum capability.

Example:
```python
class AzureDataSourcePlugin:
    """Rated up to SECRET, but reports actual level based on data being accessed."""

    max_capability = SecurityLevel.SECRET

    def get_security_level_for_job(self, config: dict) -> str:
        """Return security level for THIS specific job."""
        # Inspect the actual data source object
        blob_container = config['container']
        data_classification = azure.get_blob_classification(blob_container)

        # Plugin is CAPABLE of SECRET, but THIS job only accesses OFFICIAL data
        if data_classification == "OFFICIAL":
            return "OFFICIAL"  # NOT "SECRET"

        return data_classification
```

**Why this matters**: A plugin rated "up to SECRET" can participate in pipelines with OFFICIAL components when it assesses the data as OFFICIAL (without dynamic assessment, it would always require SECRET). This enables flexible deployment - the same plugin can handle different classification levels based on actual data. Note: OFFICIAL and UNOFFICIAL cannot coexist (OFFICIAL has Archive Act implications, UNOFFICIAL is test data).

### 2. All Components Validate, Not Just Datasource

**Mental model**: Every component with security requirements validates independently.

```python
# WRONG: Only datasource validates
if datasource.security_level > pipeline_min:
    raise SecurityError("Datasource can't operate")

# CORRECT: ALL components validate
for component in all_components:
    if component.security_level > orchestrator.operating_level:
        raise SecurityError(f"{component} can't operate at {orchestrator.operating_level}")
```

### 3. Defense in Depth: Start-Time + Runtime

**Start-time validation (PRIMARY)**:
- Orchestrator computes operating level
- Validates ALL components can operate at that level
- Job **fails to start** if any component requires higher level
- This **MUST** catch all misconfigurations

**Runtime validation (FAILSAFE)**:
- Each plugin independently validates when handling data
- Should **NEVER** trigger if start-time validation works correctly
- Protects against: "What if someone tricks the orchestrator into starting?"
- Plugins responsible for their own security, don't trust orchestrator alone

**As user emphasized**: Runtime validation should never come up because start-time MUST block it. But if someone finds a way to trick the orchestrator, plugins still protect themselves.

---

## Dynamic Security Level Assessment Protocol

### Why Plugins Report Job-Specific Levels

Plugins are cryptographically signed and trusted to accurately assess the security requirements for a specific job. A plugin rated "up to SECRET" doesn't always require SECRET - it depends on what it's actually accessing.

### Example: Azure Datasource Plugin

```python
class AzureDataSourcePlugin:
    """
    Plugin metadata declares maximum capability: "Supports data up to SECRET classification"
    But actual security level is determined by inspecting the data source configuration.
    """

    # Declared in plugin manifest (part of cryptographic signature)
    max_security_capability = SecurityLevel.SECRET

    def get_security_level_for_job(self, config: dict) -> SecurityLevel:
        """
        Called by orchestrator at job start to determine THIS job's security requirements.

        The plugin inspects the actual data source object and reports the classification
        of the data it will be accessing for THIS specific job.
        """
        container_name = config['container']
        blob_path = config['path']

        # Query Azure to get the actual classification of this blob container
        blob_classification = azure_client.get_blob_classification(
            container=container_name,
            path=blob_path
        )

        # Parse classification from blob metadata
        # Blob might be tagged: "classification:OFFICIAL" or "classification:SECRET"
        data_level = SecurityLevel.from_string(blob_classification)

        # Validate we're capable of handling this level
        if data_level > self.max_security_capability:
            raise ConfigurationError(
                f"Blob container '{container_name}' is classified {data_level.value} "
                f"but this plugin only supports up to {self.max_security_capability.value}"
            )

        # Return the ACTUAL level for THIS job (not our maximum capability)
        return data_level
```

### Benefits of Dynamic Assessment

**1. Flexibility**: A plugin capable of SECRET can participate in pipelines with OFFICIAL components when accessing OFFICIAL data (without dynamic assessment, it would require all components to be SECRET)

**2. Job-Specific Validation**: Security level reflects the ACTUAL data being accessed, not theoretical capability

**3. Configuration-Driven**: Same plugin can run different jobs at different security levels based on data source

### Trust Model: Certification + Cryptographic Signing

**Why orchestrator trusts plugin self-assessment**:

1. **Certification**: Plugins undergo certification process before deployment
2. **Cryptographic Signatures**: Signed plugin pack proves code hasn't changed since certification
3. **Tamper Detection**: Orchestrator verifies signature before trusting plugin's security assessment
4. **Defense in Depth**: Runtime validation still catches if plugin lies or signature is compromised
5. **Audit Trail**: Plugin's reported level is logged for compliance auditing

**Trust chain**:

```text
Plugin Certification
         ↓
Code Review + Security Audit
         ↓
Cryptographic Signing (plugin pack)
         ↓
Deployed to Environment
         ↓
Orchestrator Verifies Signature (at job start)
         ↓
If Valid → Trust Plugin's Security Level Report
If Invalid → Reject Plugin
```

**Key insight**: We trust the plugin's logic for assessing data classification because we've certified that logic and proven it hasn't been tampered with via cryptographic signature.

**What if a plugin lies?**:

- **Underreports** (says OFFICIAL, actually SECRET): Runtime validation in plugin catches this when accessing data
- **Overreports** (says SECRET, actually OFFICIAL): Job unnecessarily fails - plugin loses functionality
- **Compromised/Modified**: Signature verification fails - plugin rejected before job starts

**Incentive structure**: Plugins are incentivized to report accurately to maximize functionality while maintaining security.

---

## Implementation: Three Helper Methods

### Method 1: `_collect_plugin_security_levels()`

**Purpose**: Ask all signed plugins for their security levels FOR THIS SPECIFIC JOB

Plugins inspect their configuration and return the ACTUAL security level required for this job, not their maximum capability.

**Returns**: `dict[str, str]` mapping component names to job-specific levels

```python
{
    'datasource': 'OFFICIAL',    # Plugin checked: accessing OFFICIAL blob (capable of SECRET)
    'llm_client': 'SECRET',      # LLM requires SECRET
    'sink_exp1_0': 'SECRET',     # Sink requires SECRET
    'sink_exp2_0': 'UNOFFICIAL', # Debug sink (low security)
    'middleware_0': 'OFFICIAL'   # Audit middleware
}
```

### Method 2: `_compute_orchestrator_operating_level()`

**Purpose**: Compute `min(all plugin levels)` - orchestrator's operating level

**Returns**: `str` - minimum level (e.g., `'UNOFFICIAL'`)

### Method 3: `_validate_components_at_operating_level()`

**Purpose**: Validate ALL components can operate at orchestrator's level (start-time check)

**Raises**: `SecurityError` if ANY component requires higher than operating level

**This is the MUST BLOCK validation**: Job fails to start if misconfigured.

---

## Integration Point in suite_runner.py

**After line 310** (after DataFrame validation, before middleware notification):

```python
# Line 310 (existing)
ctx = SuiteExecutionContext(
    results={},
    baseline_payload=None,
    baseline_experiment=self.suite.baseline,
)

# NEW: ADR-002 orchestrator operating level enforcement
plugin_security_levels = self._collect_plugin_security_levels(
    suite=self.suite,
    defaults=defaults,
    sink_factory=sink_factory,
)

# Orchestrator operates at minimum (clearance envelope model)
orchestrator_operating_level = self._compute_orchestrator_operating_level(
    plugin_security_levels
)

# FAIL-FAST: Validate ALL components can operate at orchestrator's level
self._validate_components_at_operating_level(
    plugin_security_levels,
    orchestrator_operating_level
)

# Set operating level in context for runtime validation (defense in depth)
ctx.orchestrator_operating_level = orchestrator_operating_level

# Line 311 (existing continues)
notified_middlewares: dict[int, Any] = {}
```

---

## Test Example: Correct Behavior

```python
def test_adr002_secret_datasource_unofficial_sink_fails_at_start():
    """Start-time validation MUST block misconfig before data retrieval."""

    suite = ExperimentSuite(
        datasource_config={
            "security_level": "secret",  # HIGH
        },
        experiments=[
            ExperimentConfig(
                name="exp1",
                sink_defs=[{
                    "security_level": "unofficial"  # LOW - misconfigured
                }]
            )
        ]
    )

    runner = ExperimentSuiteRunner(
        suite=suite,
        llm_client=SimpleLLM(security_level="secret"),
    )

    # Expected flow:
    # 1. Orchestrator collects levels: {datasource: SECRET, llm: SECRET, sink: UNOFFICIAL}
    # 2. Orchestrator computes operating level: min(...) = UNOFFICIAL
    # 3. Orchestrator validates components:
    #    - datasource requires SECRET but orchestrator at UNOFFICIAL → FAIL
    #    - llm requires SECRET but orchestrator at UNOFFICIAL → FAIL
    #    - sink requires UNOFFICIAL, orchestrator at UNOFFICIAL → OK
    # 4. Job FAILS TO START (before any data retrieval)

    with pytest.raises(SecurityError, match="requires SECRET but orchestrator operating at UNOFFICIAL"):
        runner.run(dataframe, defaults)
```

---

## Runtime Validation Example (Failsafe)

**In datasource plugin implementation:**

```python
class CSVDataSource:
    def __init__(self, path: str, security_level: str, context: PluginContext):
        self.path = path
        self.security_level = SecurityLevel.from_string(security_level)
        self.context = context

    def get_data(self) -> pd.DataFrame:
        """Retrieve data with runtime security validation (failsafe)."""

        # DEFENSE IN DEPTH: Runtime validation
        # Should NEVER trigger if start-time validation worked
        # But protects against orchestrator being tricked
        orchestrator_level = getattr(self.context, 'orchestrator_operating_level', None)
        if orchestrator_level:
            orch_level = SecurityLevel.from_string(orchestrator_level)
            if self.security_level > orch_level:
                raise SecurityError(
                    f"RUNTIME FAILSAFE: Datasource requires {self.security_level.value}, "
                    f"but orchestrator operating at {orch_level.value}. "
                    f"Refusing to hand over data. "
                    f"(This should have been caught at start-time - possible security bypass attempt)"
                )

        # Normal data retrieval
        return pd.read_csv(self.path)
```

**As user emphasized**: This runtime check should NEVER fire if start-time validation is working. It's a failsafe for "what if someone tricks the orchestrator?"

---

## Error Messages

### Start-Time (Primary Enforcement)

```text
SecurityError: Component 'datasource' requires SECRET but orchestrator operating at UNOFFICIAL.
Job cannot start - remove low-security component or create separate pipeline.
ADR-002 fail-fast enforcement.
```

### Runtime (Failsafe - Should Never Happen)

```text
SecurityError: RUNTIME FAILSAFE: Datasource requires SECRET but orchestrator operating at UNOFFICIAL.
Refusing to hand over data.
This should have been caught at start-time - possible security bypass attempt.
ADR-002 defense-in-depth enforcement.
```

---

## Summary: What's Different from Original Spec

| Original Spec (WRONG) | Correct Model |
|----------------------|---------------|
| "Datasource validates if pipeline has low sink" | "Orchestrator operates at minimum, ALL high components refuse low envelope" |
| "Only datasource validated" | "ALL components with security requirements validated" |
| Single validation point | Defense in depth: start-time (PRIMARY) + runtime (FAILSAFE) |
| `_validate_datasource_security()` | `_validate_components_at_operating_level()` (validates ALL) |
| Datasource-centric logic | Orchestrator clearance envelope model |

---

**Implementation Priority**: HIGH - This is the correct interpretation of ADR-002 and must be implemented before certification.

**Estimated Effort**: Same as original spec (4-6 hours) - same complexity, just correct model.
