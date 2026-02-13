# Archived Quality Audit Findings (2026-01-22)

**Archived:** 2026-01-30
**Reason:** Duplicate content — `findings-codex/` was retained as canonical during the Jan 2026 quality audit. The original `docs/quality-audit/` directory has since been removed; this archive preserves the historical findings.

## Contents

This archive contains two folders from the original quality audit:

### findings/
Original test quality findings from Jan 22, 2026 quality audit. Contains per-test-file analysis organized by subsystem:
- `engine/` - Engine test findings
- `core/` - Core subsystem test findings
- `contracts/` - Contract test findings
- `plugins/` - Plugin test findings
- `property/` - Property test findings
- `integration/` - Integration test findings

### findings-integration/
Integration seam analysis focused on boundary issues between subsystems. Contains:
- Per-module analysis files (orchestrator.py.md, processor.py.md, etc.)
- FINDINGS_INDEX.md - Index of all findings
- SUMMARY.md - Consolidated summary

## Why Archived

The original quality audit produced three overlapping directories:
1. `findings/` - Original audit (45 files)
2. `findings-codex/` - Regenerated comprehensive audit (99+ files)
3. `findings-integration/` - Integration seam focus (13 files)

`findings-codex/` was retained as the canonical source (most comprehensive). These two were archived here for historical reference.

## When to Reference

Reference this archive if you need:
- Historical context on how findings evolved
- Original integration seam analysis methodology
- Comparison between audit runs
