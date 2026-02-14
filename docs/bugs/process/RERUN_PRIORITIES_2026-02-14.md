# Rerun Priorities - Unknown/Failed Outputs (2026-02-14)

## Summary

- Unknown-priority findings are zero-byte outputs from failed scan runs.
- Total failed files: 54
- 01-runtime-plugins: 8
- 02-runtime-telemetry: 12
- 03-testing-modules: 25
- 04-tui-modules: 9

## Priority Order For Reruns

1. `01-runtime-plugins` (highest impact): runtime transforms and plugin wiring in production pipeline paths.
2. `02-runtime-telemetry`: observability contracts and exporter behavior on production runs.
3. `03-testing-modules`: test helpers/chaos tooling (important, but not runtime execution path).
4. `04-tui-modules` (lowest runtime risk): UI/debug surfaces.

## Recommended Commands

```bash
uv run python scripts/codex_bug_hunt.py --paths-from docs/bugs/process/rerun-paths/01-runtime-plugins.txt --rate-limit 30
uv run python scripts/codex_bug_hunt.py --paths-from docs/bugs/process/rerun-paths/02-runtime-telemetry.txt --rate-limit 30
uv run python scripts/codex_bug_hunt.py --paths-from docs/bugs/process/rerun-paths/03-testing-modules.txt --rate-limit 30
uv run python scripts/codex_bug_hunt.py --paths-from docs/bugs/process/rerun-paths/04-tui-modules.txt --rate-limit 30
```

## Notes

- Keep `docs/bugs/generated` outputs and `docs/bugs/process/CODEX_LOG.md` under versioned tracking for audit reproducibility.
- Recompute summary counts after each rerun to confirm `Unknown Priority` trends to zero.
