# Core Engine Extension Design Notes

This note sketches early implementation steps for broadening the orchestrator beyond LLM-centric workflows while preserving the security, auditability, and reliability guarantees described in the plugin catalogue.

## 1. Shared Principles

* **Context-first** – All new cores must accept `PluginContext` (see `src/elspeth/core/plugins/context.py`) so security level, provenance, and metadata flow through the pipeline automatically. Constructors should not rely on raw `security_level` kwargs.
* **Schema-backed registration** – Mirror the JSON Schema enforcement used today (`PluginFactory.validate`, `validate_schema`) to catch misconfigurations during `load_settings` rather than at runtime.
* **Middleware compatibility** – Reuse the existing middleware registry so rate limiting, auditing, and PII guards can wrap deterministic cores. Where middleware semantics differ, introduce capability flags negotiated through context metadata.
* **Artifact hygiene** – All cores must emit artifacts via `ArtifactPipeline`, setting `security_level` and provenance. Deterministic outputs should include digests or signatures to support reproducibility.

## 2. Deterministic Transform Core (`data_transform_core`)

1. **Protocol** – Create `TransformCoreProtocol` in `src/elspeth/core/interfaces.py` with a `run_transform(*, payload: Dict[str, Any], metadata: Dict[str, Any] | None = None) -> Dict[str, Any]` method.
2. **Registry** – Add `TransformCoreRegistry` similar to `PluginRegistry`/`PluginFactory` (new module `src/elspeth/core/transform/registry.py`). Support context-aware factory signature `(options: Dict[str, Any], context: PluginContext)`.
3. **Configuration Loader** – Extend `src/elspeth/config.py` to recognise `core` sections specifying either an LLM or transform plugin (e.g., `core: { plugin: data_transform/sql, options: {...} }`). Backwards compatibility: default to `llm` when `core` absent.
4. **Builtin plugins**:
   - `sql_transform`: executes parameterised SQL using a read-only connection profile; emits DataFrame artifacts.
   - `python_transform`: loads approved transformation modules (whitelisted via configuration) and executes a `transform(context, payload)` hook.
5. **Security** – Enforce allowlists derived from `context.security_level`. For SQL, restrict schemas and require parameter binding. For Python modules, load from signed packages and log module hashes.
6. **Testing** – Mirror LLM test suites (`tests/test_transform_core.py`) with mock connectors and golden output fixtures.
7. **Support Classes** – Implement helpers such as `SqlTemplateValidator` (static analysis of templated queries), `TransformSandbox` (controls module execution), and artifact helpers (`TransformArtifact`) capturing code/version digests.

## 3. Policy Engine Core (`policy_engine_core`)

1. **Protocol** – Define `PolicyCoreProtocol` with `evaluate(*, payload, metadata) -> Dict[str, Any]` returning decisions and rationale.
2. **Plugin ideas**:
   - `opa_policy`: bundle Open Policy Agent rules; options include `policy_path`, `default_decision`, `data_inputs`.
   - `rulebook`: YAML/JSON-defined decision tables executed deterministically.
3. **Audit** – Persist decision logs alongside experiment artifacts, including policy digests (hashes) and input fingerprints. Use context to gate policy scope (e.g., high security tiers may load additional rule bundles).
4. **Middleware fit** – PII guards can still scrub inputs before evaluation; add optional middleware to emit structured decision metrics.
5. **Support Classes** – Add `PolicyCompiler` to pre-compile policies per security level, `PolicyBundleArtifact` to record bundle metadata, and `RuleBookParser` to validate rule schemas before runtime.

## 4. Simulation / Scoring Core (`simulation_core`)

1. **Protocol** – Similar to transform core but emphasises deterministic seeding and compute cost reporting.
2. **Plugins**:
   - `monte_carlo`: run seeded Monte Carlo scenarios defined in configuration.
   - `ml_inference`: serve deterministic ML models (ONNX, TensorFlow) with versioned model artifacts.
3. **Cost Tracking** – Integrate with existing cost tracker using synthetic “compute units”; middleware can report runtime metrics.
4. **Reproducibility** – Store seeds and model versions in emitted artifacts; include optional signed manifests.
5. **Support Classes** – Introduce `SimulationSeedManager` (derive per-run seeds from context), `ModelRegistryClient` for loading signed model binaries, and `SimulationArtifact` capturing run metadata.

## 5. Workflow / Action Core (`action_core`)

1. **Protocol** – Provide `execute(actions: List[Dict[str, Any]], metadata: Dict[str, Any]) -> Dict[str, Any]` semantics.
2. **Plugins**:
   - `ticket_workflow`: create/update tickets in ITSM systems.
   - `remediation_plan`: call approved remediation APIs with templated payloads.
3. **Safety** – Integrate dry-run toggles and approval middleware; context determines which credentials or endpoints are available.
4. **Auditing** – Emit signed execution logs (request/response pairs) into artifact pipeline.
5. **Support Classes** – Provide `ActionDryRunGuard`, `CredentialResolver` (context-aware secret fetcher), and `ActionLogArtifact` to store signed traces.

## 6. Hybrid Decision Core (`fallback_core`)

1. **Routing** – Introduce middleware (e.g., `DecisionRouterMiddleware`) that inspects payload/context and decides which core (LLM vs deterministic) should process the request.
2. **Implementation** – Wrap both cores in a composite plugin that constructs sub-contexts (`context.derive(...)`) and merges outputs.
3. **Provenance** – Record routing choices and sub-core outputs separately to preserve audit trails.
4. **Support Classes** – Create `RoutingRecord` artifact capturing decisions, and a `FallbackDecisionManager` responsible for invoking the correct core and reconciling outputs.

## 7. Configuration & CLI Impacts

* Update CLI and `load_settings` to accept a `core` block, e.g.:
  ```yaml
  default:
    core:
      plugin: data_transform/sql
      security_level: official
      options:
        profile: reporting
        query_template: |-
          SELECT * FROM metrics WHERE date = :run_date
    llm:  # optional legacy block
      plugin: mock
      security_level: official
  ```
* Ensure sample suites and docs demonstrate both legacy LLM and new cores.
* Provide migration guidance for users moving from `llm` to `core` blocks.

## 8. Testing Strategy

* Unit tests for each new registry/protocol.
* Integration tests covering:
  - Context propagation through new cores.
  - Artifact pipeline interactions.
  - Middleware compatibility (PII guards, audit logging).
  - Sample suite exercises invoking non-LLM cores.

## 9. Security Review Checklist

* Review secrets handling for new datasources/cores.
* Validate that provenance metadata correctly captures parent context, plugin name, and options.
* Confirm that failure modes surface as `ConfigurationError` or deterministic exceptions with minimal leakage of sensitive data.
* Update threat models in `docs/architecture/threat-traceability.md` once implementations land.

---

These notes aim to unblock spike branches; firm design tickets should capture detailed acceptance criteria and assign ownership before implementation begins.
