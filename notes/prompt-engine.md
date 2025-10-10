# Prompt Engine Migration – Phase A Findings

Legacy behaviour (observed via `old/main.py` and call sites):
- Prompts were loaded via `elspeth.prompts.load_prompts_default`, with validation/error handling.
- Formatting delegated to `elspeth.prompts.format_user_prompt`, which supported:
  * Placeholder substitution for case-study fields and criteria metadata.
  * Conditional inclusion/templated guidance (e.g. optional criteria descriptions).
  * Prompt cloning/templating so variants could inherit from a baseline prompt pack.
  * Validation for missing placeholders and malformed prompt files.
- Additional helpers allowed prompt “packs” to inject shields/safety wrappers before sending to the LLM.

New architecture gaps:
- Current system relies on plain Python `str.format` inside `ExperimentRunner`, so:
  * No support for conditional blocks, default fallbacks, or iterating over criteria.
  * Missing validation for incomplete context; runtime `KeyError` bubbles up without clarity.
  * No reusable abstraction for cloning/adapting prompt templates across experiments.

Design direction for the new engine:
- Introduce `elspeth.core.prompts` package providing:
  * `PromptTemplate` dataclass storing raw text, compiled artefact, required fields, and metadata.
  * `PromptEngine` that compiles templates using a strict renderer (Jinja2-backed) with support for `{ field }` placeholders, `{{ field|default('x') }}`, `{{#if}}`-style guards (mapped to Jinja `{% if %}`), and iteration.
  * Validation utilities that analyse undeclared variables pre-render, logging/raising `PromptValidationError` with helpful messages.
  * Clone helpers to derive variant templates from baseline definitions (`template.clone(overrides=...)`).
- Maintain backward compatibility with legacy `{FIELD}` syntax by auto-translating simple format placeholders to the new template flavour.
- Ship default filters (`default`, `upper`, `lower`, `title`) and macros for criteria rendering to ease porting of rich prompts.

Testing considerations:
- Unit tests covering placeholder substitution, defaults, conditionals, loops, and cloning.
- Integration in experiment runner verifying prompts render correctly for both baseline and criteria variants.
- Negative tests ensuring missing context or invalid syntax yields actionable error messages.

Next steps (Phase B):
1. Implement the prompt engine (`PromptTemplate`, `PromptEngine`, exceptions, utilities).
2. Swap `ExperimentRunner` to use the new rendering path (system/user/criteria).
3. Update tests + sample configs to exercise the richer templating.
