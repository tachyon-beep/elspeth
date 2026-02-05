# Analysis: src/elspeth/core/config.py

**Lines:** 1,598
**Role:** Configuration loading and validation for ELSPETH pipelines. Defines all Pydantic Settings models (ElspethSettings, RetrySettings, TelemetrySettings, SecretsConfig, etc.), environment variable expansion, secret fingerprinting for audit, template file loading, and the Dynaconf-to-Pydantic bridge via `load_settings()` and `resolve_config()`.
**Key dependencies:**
- Imports: `pydantic` (BaseModel, validators), `yaml`, `re`, `pathlib.Path`, `urllib.parse.urlparse`, `elspeth.contracts.enums` (OutputMode, RunMode), `elspeth.engine.expression_parser` (lazy), `elspeth.core.security` (lazy), `dynaconf` (lazy), `sqlalchemy` (lazy)
- Imported by: `elspeth.cli` (load_settings, resolve_config, ElspethSettings, SecretsConfig), `elspeth.core.__init__` (re-exports all models), `elspeth.contracts.config.runtime` (TYPE_CHECKING imports for from_settings factories), virtually all test files that construct config objects
**Analysis depth:** FULL

## Summary

The file is well-structured with thorough Pydantic validation, good separation between runtime and audit concerns, and strong secret handling. However, there are several significant findings: (1) most Settings models accept extra fields silently, which means typos in YAML config are never caught; (2) the `_fingerprint_secrets` function has a key collision vulnerability; (3) template file loading has no path traversal prevention; (4) the env var expansion regex silently ignores lowercase variable references, creating a confusing failure mode. The secret handling is generally sound, with good defense-in-depth (HTTPS-only vault URLs, `${VAR}` rejection in vault_url, fingerprint-or-fail pattern).

## Critical Findings

### [861] ElspethSettings and most sub-models silently accept extra fields (missing `extra="forbid"`)

**What:** `ElspethSettings` and most of its nested models (AggregationSettings, GateSettings, CoalesceSettings, SourceSettings, TransformSettings, SinkSettings, LandscapeSettings, ConcurrencySettings, DatabaseSettings, RateLimitSettings, CheckpointSettings, RetrySettings, PayloadStoreSettings, TelemetrySettings) use `model_config = {"frozen": True}` without `extra = "forbid"`. Pydantic V2's default for `extra` is `"ignore"`, meaning unrecognized fields are silently dropped.

Only `SecretsConfig` (line 53) and `TriggerConfig` (line 161) have `extra = "forbid"`.

**Why it matters:** This is a configuration-silent-failure risk in a system that handles high-stakes, auditable data:

1. **Typos in YAML are invisible.** A user who writes `retyr:` instead of `retry:`, `max_attemps: 10` instead of `max_attempts: 10`, or `backpresure_mode: drop` instead of `backpressure_mode: drop` will get default values silently applied. The pipeline runs with wrong parameters, potentially affecting audit-critical behavior like retry counts or checkpoint frequency.

2. **The `secrets:` key in YAML is silently ignored by `load_settings()`.** When `load_settings()` passes the raw config dict to `ElspethSettings(**raw_config)`, any `secrets` key is silently dropped because `ElspethSettings` doesn't have a `secrets` field and doesn't forbid extras. The `secrets` config is only used when the CLI explicitly extracts it via `_load_settings_with_secrets()`. Any caller that uses `load_settings()` directly (e.g., `cli_helpers.py` line 113) will never load Key Vault secrets.

3. **Environment variable typos.** Dynaconf maps `ELSPETH_RETYR__MAX_ATTEMPTS` to a `retyr` key, which would be silently ignored.

**Evidence:**
```python
# Line 861 - no extra="forbid"
class ElspethSettings(BaseModel):
    model_config = {"frozen": True}  # Missing extra="forbid"

# Compare with line 53 - has it
class SecretsConfig(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}
```

This is especially dangerous given the CLAUDE.md's P2-2026-01-21 bug history, where a config field was validated but never wired to runtime. The same class of bug (field exists but is silently ignored) can now be introduced by users through typos.

### [1126-1154] Secret fingerprinting has key collision vulnerability

**What:** In `_fingerprint_secrets`, when a secret field like `api_key` is detected, it is renamed to `api_key_fingerprint` and the original key is removed (line 1136). However, if the original dict already contains an `api_key_fingerprint` key, the fingerprint value will silently overwrite it. Since `_recurse` builds the result dict by iterating over the original dict, the order depends on which key comes first.

**Why it matters:** An attacker or misconfiguration could include both `api_key: "real-secret"` and `api_key_fingerprint: "fake-fingerprint"` in plugin options. After fingerprinting, the `api_key_fingerprint` key would first be set to the real fingerprint (from processing `api_key`), then overwritten with `"fake-fingerprint"` (from the existing `api_key_fingerprint` key) or vice versa depending on dict ordering. In Python 3.7+, dict ordering is insertion order, so:
- If `api_key` comes before `api_key_fingerprint` in the YAML, the real fingerprint gets overwritten with the attacker-controlled value.
- If `api_key_fingerprint` comes first, the real fingerprint overwrites it (correct behavior, but by luck).

This could allow an attacker who controls the config to inject a fake fingerprint into the audit trail, undermining the "secrets are never in the audit trail in cleartext" guarantee, or to make a different secret appear to be the one used.

**Evidence:**
```python
def _process_value(key: str, value: Any) -> tuple[str, Any, bool]:
    # ...
    elif isinstance(value, str) and _is_secret_field(key):
        if have_key:
            fp = secret_fingerprint(value)
            return f"{key}_fingerprint", fp, True  # renames api_key -> api_key_fingerprint
    # ...

def _recurse(d: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in d.items():
        new_key, new_value, _was_secret = _process_value(key, value)
        result[new_key] = new_value  # Can overwrite if collision
    return result
```

### [1407-1415, 1422-1438, 1444-1453] Template file loading has no path traversal prevention

**What:** `_expand_template_files` resolves relative file paths against the settings file directory using `(settings_path.parent / template_path).resolve()`. The `.resolve()` call follows symlinks and normalizes `..` segments, but there is no check that the resolved path remains within a safe directory. A config like `template_file: "../../../../etc/passwd"` would successfully read any file readable by the process.

**Why it matters:** While CLAUDE.md states plugins are system code (not user-provided), the YAML config file is the primary user-facing configuration surface. If an operator can edit the pipeline YAML (which is the normal workflow), they can read arbitrary files on the system by setting `template_file`, `lookup_file`, or `system_prompt_file` to paths that traverse outside the project directory. The file contents become part of the pipeline configuration (stored in the audit trail via `resolve_config()`), potentially exposing sensitive files.

This is especially concerning because:
1. Template contents are passed to LLM transforms, so they could be exfiltrated via LLM API calls.
2. Lookup files are parsed as YAML and loaded into the config, so they could be used to inject arbitrary structured data.
3. There is no sandboxing or chroot around the file reads.

**Evidence:**
```python
template_path = Path(template_file)
if not template_path.is_absolute():
    template_path = (settings_path.parent / template_path).resolve()
# No check that template_path is within settings_path.parent or project root
result["template"] = template_path.read_text(encoding="utf-8")
```

## Warnings

### [1022] Env var pattern silently ignores lowercase variable references

**What:** The regex `_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")` only matches uppercase environment variable names (character class `[A-Z_][A-Z0-9_]*`). A reference like `${my_database_url}` or `${My_Var}` in the YAML config will be silently preserved as a literal string, not expanded.

**Why it matters:** This creates a confusing failure mode. A user who writes `url: "${database_url}"` in their YAML will get the literal string `${database_url}` as their database URL, which will either cause a cryptic SQLAlchemy connection error or (worse) be stored in the audit trail as the "URL" for the run. There is no warning that the env var reference was not expanded. The convention for uppercase-only env vars is reasonable, but the silent failure is not.

**Evidence:**
```python
_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")
# ${my_var} -> no match, left as literal "${my_var}"
# ${MY_VAR} -> matched, expanded
```

### [1022] Nested env var references in defaults produce silently wrong values

**What:** The regex pattern's default value group `([^}]*)` stops at the first `}` character. This means a nested reference like `${VAR1:-${VAR2}}` matches with a default value of `${VAR2` (missing the closing brace), and the actual closing `}` of `VAR2` is consumed as the end of `VAR1`'s pattern.

**Why it matters:** If a user attempts to chain env var references with fallbacks (a reasonable expectation), they will get silently mangled values. The default value `${VAR2` is not a valid env var reference and will be used as a literal string. There is no error or warning.

**Evidence:** Tested with Python regex:
```python
>>> pattern.findall("${VAR1:-${VAR2}}")
[('VAR1', '${VAR2')]  # default is literally "${VAR2" - wrong
```

### [1131] Secret fields inside lists are never fingerprinted

**What:** In `_fingerprint_secrets._process_value`, when processing list items (line 1131), the key is passed as the empty string `""`. Since `_is_secret_field("")` will never return True (empty string doesn't match any secret name or suffix), any string values directly in a list are never checked for secret detection.

**Why it matters:** If a plugin's options contain a list of secret values (unlikely but possible), those secrets would flow into the audit trail unfingerprinted. Example: `headers: [{api_key: "secret"}]` would be fingerprinted (dict inside list), but a hypothetical `api_keys: ["secret1", "secret2"]` would not because the list items are strings, not dict entries with key names.

**Evidence:**
```python
elif isinstance(value, list):
    return key, [_process_value("", item)[1] for item in value], False
    #                          ^^ empty string key -> _is_secret_field("") returns False
```

### [1088-1091] Secret field detection suffix matching has false positive risk

**What:** `_is_secret_field` checks if a field name ends with certain suffixes like `_key`, `_token`, `_secret`. This means fields like `partition_key` (a database concept, not a secret), `primary_key`, `foreign_key`, `sort_key`, `cache_key`, `batch_token` (a pagination cursor), or `access_token` (which IS a secret) would all be matched.

**Why it matters:** False positives cause legitimate non-secret values to be fingerprinted and replaced with hashes in the audit trail. A database sink configured with `partition_key: "customer_id"` would have its value replaced with an HMAC hash, making the audit trail record unintelligible for auditors. The fingerprinted config would show `partition_key_fingerprint: "abc123..."` instead of `partition_key: "customer_id"`.

**Evidence:**
```python
_SECRET_FIELD_SUFFIXES = ("_secret", "_key", "_token", "_password", "_credential", "_connection_string")

def _is_secret_field(field_name: str) -> bool:
    normalized = field_name.lower()
    return normalized in _SECRET_FIELD_NAMES or normalized.endswith(_SECRET_FIELD_SUFFIXES)
    # "partition_key".endswith("_key") -> True (false positive)
    # "sort_key".endswith("_key") -> True (false positive)
```

### [1132] Non-string secret values silently skip fingerprinting

**What:** `_fingerprint_secrets._process_value` only fingerprints values that are strings (line 1132: `isinstance(value, str) and _is_secret_field(key)`). If a secret field has a non-string value (e.g., an integer, a list, or `None`), it passes through without fingerprinting or any warning.

**Why it matters:** If a secret is loaded as a non-string type (e.g., YAML interprets `api_key: 12345` as an integer), it will appear in the audit trail in cleartext. The YAML specification can produce unexpected types: `api_key: true` becomes a boolean, `api_key: 1e5` becomes a float.

**Evidence:**
```python
elif isinstance(value, str) and _is_secret_field(key):
    # Only strings are fingerprinted
    # int, float, bool, None values for secret-named fields pass through
```

### [1458-1523] `_lowercase_schema_keys` is complex and has implicit contract assumptions

**What:** The `_lowercase_schema_keys` function has three behavioral modes (`_preserve_nested`, `_in_sinks`, and default) with specific key-name triggers (`options`, `routes`, `sinks`). This creates an implicit contract where the function must know which keys at which nesting levels contain user data vs. schema keys. The function assumes these key names are only used at specific nesting levels.

**Why it matters:** If a future developer adds a new config section whose child keys should be preserved (like a hypothetical `headers` section with case-sensitive HTTP header names), this function would silently lowercase them. The logic is fragile because it depends on matching specific key names at specific depths, but the function is recursive and the nesting depth is not tracked. The key names `options` and `routes` are treated specially regardless of where they appear in the hierarchy. For example, if a top-level `options:` key were ever added to ElspethSettings, its contents would be incorrectly preserved instead of lowercased.

**Evidence:**
```python
elif new_key == "options":
    child = _lowercase_schema_keys(v, _preserve_nested=True, _in_sinks=False)
elif new_key == "routes":
    child = _lowercase_schema_keys(v, _preserve_nested=True, _in_sinks=False)
# These match "options" and "routes" at ANY nesting level
```

### [85] vault_url validation does not check for `${{` double-brace patterns

**What:** The `SecretsConfig.validate_vault_url_format` validator checks for `${` (line 85) to reject environment variable references. However, it does not check for doubled braces like `${{VAR}}` or other template syntaxes that might be used by configuration management tools (e.g., Ansible, Terraform).

**Why it matters:** In production environments, configuration files are often generated by templating tools. A vault_url like `${{AZURE_KEYVAULT_URL}}` (Ansible template syntax) would pass the `${` check and be treated as a literal URL. The `urlparse` validation would catch this particular example (no scheme), but more subtle template patterns might slip through.

**Evidence:**
```python
if "${" in v:
    raise ValueError(...)
# Does not check for ${{, #{, {{, %{, or other template syntaxes
```

## Observations

### [995-1018] Duplicate field_validator on "sinks" is valid but unusual

**What:** Two `@field_validator("sinks")` decorators exist: `validate_sinks_not_empty` (line 995) and `validate_sink_names_lowercase` (line 1003). In Pydantic V2, both validators run in definition order. This is valid behavior, confirmed by testing.

**Why it matters:** While correct, having two separate validators for the same field is unusual and could confuse developers. A single validator that checks both conditions would be more conventional. However, the separated validators have clearer error messages, so this is a style preference, not a bug.

### [259, 312, 468, 526, 542, 554] Inconsistent `extra` policy across models

**What:** Only `SecretsConfig` and `TriggerConfig` use `extra = "forbid"`. All other models use the default `extra = "ignore"`. This inconsistency suggests either an incomplete migration toward strict validation or an intentional but undocumented choice.

**Why it matters:** If strict validation was intended for some models but not others, the inconsistency should be documented. If it was an oversight, it amplifies the risk described in the critical finding above.

### [1060] Environment variable expansion does not expand dict keys

**What:** `_expand_value` processes dict values but passes keys through unchanged. A YAML config with `${MY_SINK_NAME}: {plugin: csv}` in the sinks section would use the literal string `${MY_SINK_NAME}` as the sink name.

**Why it matters:** Low impact. Config keys are typically schema-level identifiers, not dynamic values. However, sink names are user-defined strings that might plausibly come from env vars. The behavior is not documented.

### [1291-1375] `_fingerprint_config_for_audit` uses `telemetry.get("exporters")` defensive pattern

**What:** Line 1369 uses `telemetry.get("exporters")` rather than direct access `telemetry["exporters"]`. This is after `config_dict` is produced by `settings.model_dump(mode="json")`, which should always include all fields with their defaults.

**Why it matters:** Per the CLAUDE.md prohibition on defensive programming patterns, since `config_dict` comes from `model_dump()` (our code), this is our data and should be trusted. Using `.get()` here hides potential bugs if `model_dump()` were to change behavior. However, the practical risk is negligible since this operates on a deep copy for audit purposes.

### [1260] `_expand_config_templates` makes a shallow copy of raw_config

**What:** Line 1260 does `config = dict(raw_config)` which is a shallow copy. The nested dicts (like `transforms`, `aggregations`) are still references to the original. However, the function replaces list items entirely (building new lists), so the original `raw_config` is not mutated in practice.

**Why it matters:** The code is correct in practice but the shallow copy pattern is fragile. If the function were modified to mutate nested structures in place rather than replacing them, it could cause subtle aliasing bugs. Not a current issue.

### [68-106] SecretsConfig vault_url validator allows unusual but valid URLs

**What:** The validator checks for HTTPS scheme and non-empty netloc but does not validate that the URL looks like an Azure Key Vault URL (e.g., `*.vault.azure.net`). Any HTTPS URL passes validation.

**Why it matters:** Very low risk. A misconfigured vault_url would fail at Key Vault client creation time, which provides a clear error. Adding Azure-specific URL validation would be over-constraining and could break with future Azure regions or sovereign clouds.

### [1553-1559] Dynaconf `merge_enabled=True` can cause unexpected deep merges

**What:** The Dynaconf constructor uses `merge_enabled=True`, which causes environment variable overrides to deep-merge into nested dicts rather than replacing them. For example, setting `ELSPETH_RETRY__MAX_ATTEMPTS=5` would merge into the retry section rather than replacing it.

**Why it matters:** Deep merge is generally the desired behavior for nested config, but it means environment variables cannot "clear" a nested section (e.g., you cannot use an env var to remove all configured exporters). This is a known Dynaconf behavior and is documented behavior, but operators relying on env var overrides to completely replace sections may be surprised.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:**
1. **(High priority)** Add `extra = "forbid"` to `ElspethSettings` and all Settings models that directly accept user YAML input. This is the single highest-impact change: it catches config typos at load time rather than silently applying defaults. This directly prevents the class of bug documented in P2-2026-01-21.
2. **(Medium priority)** Fix the key collision in `_fingerprint_secrets` by checking for existing `{key}_fingerprint` keys before renaming, or by raising an error if such a collision is detected.
3. **(Medium priority)** Add path traversal prevention in `_expand_template_files` - verify that resolved paths are within the settings file's directory or a configured allowlist.
4. **(Low priority)** Add a warning when `${...}` patterns with lowercase variable names are detected but not expanded, to prevent confusing failures.
5. **(Low priority)** Review `_SECRET_FIELD_SUFFIXES` for false positive risk and consider using a more targeted detection mechanism (e.g., explicit annotations on fields that contain secrets, rather than heuristic name matching).

**Confidence:** HIGH - The file was read completely, all lazy imports were traced to their source, key edge cases were verified with runtime testing (regex behavior, Pydantic validator ordering), and the finding about missing `extra="forbid"` was confirmed against Pydantic V2 documentation.
