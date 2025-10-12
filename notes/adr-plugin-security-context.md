# ADR: Introduce Plugin Context for Secure Plugin Instantiation

## Status
Proposed

## Context
The platform now requires every plugin definition to declare a `security_level`. Registry methods in `src/elspeth/core/registry.py` and `src/elspeth/core/experiments/plugin_registry.py` validate that a level is supplied, normalize it, and strip the field before invoking plugin factory callables. They then re-attach the normalized classification to the constructed instance via the `_elspeth_security_level` attribute. This sequence ensures validation but prevents plugin constructors from reacting to the classification during initialization. Moreover, downstream components and third-party plugins rely on ad-hoc attribute access (`getattr(plugin, "_elspeth_security_level", None)`), which is undocumented and error-prone.

Nested builders—such as `_build_llm_guard` in `src/elspeth/plugins/experiments/validation.py`
—must manually coalesce security levels when instantiating sub-plugins. Any oversight in these helpers leads to runtime `ConfigurationError` exceptions. In addition, configuration merging (suite defaults, prompt packs, experiment overrides) uses `coalesce_security_level` without preserving the provenance of the resolved value, reducing auditability when conflicts arise.

## Decision
We will introduce a `PluginContext` object that encapsulates metadata required during plugin construction, starting with:

- `plugin_name`: the registry identifier being instantiated.
- `plugin_kind`: datasource/llm/sink/row/aggregation/baseline/validation/early_stop/middleware/etc.
- `security_level`: normalized classification required for the plugin.
- `provenance`: optional record of where the level originated (experiment definition, suite defaults, prompt pack, etc.).

Registry `create_*` methods will stop removing `security_level` from the payload. Instead, they will build the context, pass `options_without_security` along with the context into factory callables, and attach the context to the instance (`setattr(plugin, "_elspeth_context", context)`). Builtin plugin constructors will be updated to accept a keyword-only `context: PluginContext` argument, ensuring the classification is available at initialization. Third-party plugins may ignore the context, but documented examples will show how to access `context.security_level` to enforce behavior.

A shared helper `build_plugin_from_definition(definition, *, kind, registry, parent_context=None)` will replace ad-hoc nested construction. The helper will:

1. Resolve and normalize `security_level`, optionally combining parent classification using `coalesce_security_level`.
2. Build a child context that records provenance (`parent_context`, explicit options, defaults).
3. Invoke the appropriate registry method or factory with the prepared options and child context.
4. Attach the context to the resulting plugin.

A lightweight `SecurityScopedPlugin` protocol will be published, exposing read-only `security_level` and `context` properties sourced from the attached context. Existing components that rely on `_elspeth_security_level` will migrate to the protocol, improving discoverability and reducing magic attribute usage.

Configuration validation will also record provenance information when resolving security levels. Diagnostics will report the origin of each level and highlight conflicts between overrides, supporting audits and troubleshooting.

## Consequences
- Plugin constructors can branch on security classification at creation time (e.g., enforce stricter defaults for `official-sensitive`).
- Context propagation standardizes metadata delivery across nested plugin builders, eliminating repeated `setattr` logic and reducing regressions when adding new helper functions.
- Third-party plugin authors have a documented contract for accessing security metadata via `SecurityScopedPlugin`.
- Refactoring is required for built-in plugins and registry call sites to accept `context`. This change is API-breaking for any external plugin relying on the old signature; migration guidance must be provided.
- Configuration loaders must capture provenance details, increasing bookkeeping but improving auditability. Logging changes may be needed to surface provenance on conflicts.

## Implementation Outline
1. Define `PluginContext` dataclass in `elspeth/core/plugins/context.py` (new module) and expose it to plugin registries.
2. Update registry `PluginFactory.create` signatures to accept `context` and forward it to plugin constructors.
3. Modify builtin plugins to accept `context` and read `context.security_level` instead of reaching for `_elspeth_security_level` post-instantiation.
4. Replace `_elspeth_security_level` usage with the new `SecurityScopedPlugin` protocol where possible; maintain backward compatibility temporarily via a shim.
5. Implement `build_plugin_from_definition` helper and migrate nested plugin creation (LLM guard, prompt variants, etc.) to use it.
6. Enhance configuration merging routines to track provenance when coalescing security levels, storing that data in the context.
7. Document the new context-based plugin interface in `docs/architecture/plugin-system.md` and update developer guidelines.

## Alternatives Considered
- Continue using `_elspeth_security_level` with better documentation: rejected because it does not enable constructors to react to classification and leaves nested builders error-prone.
- Encode security level in plugin kwargs only: rejected because validating every plugin to accept `security_level` creates inconsistent APIs and does not convey provenance.

## Rollout
- Introduce the new context class behind a feature flag, allowing internal plugins to adopt it first.
- Provide a deprecation period where registries still set `_elspeth_security_level` for legacy consumers, emitting warnings when constructors do not accept the new `context` parameter.
- After the transition window, remove the legacy attribute pathway.

