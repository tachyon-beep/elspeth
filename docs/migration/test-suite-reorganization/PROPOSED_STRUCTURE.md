# Proposed Test Directory Structure

**Complete directory tree with mapping rules and examples**

---

## Complete Directory Tree

```
tests/
├── unit/                                    # Fast (<1s), isolated, no I/O
│   ├── core/
│   │   ├── cli/                             # CLI utilities
│   │   ├── pipeline/                        # Artifact pipeline
│   │   ├── registries/                      # Registry logic
│   │   ├── security/                        # Security utilities
│   │   ├── validation/                      # Validation logic
│   │   ├── config/                          # Configuration
│   │   ├── prompts/                         # Prompt templates
│   │   ├── healthcheck/                     # Healthcheck
│   │   └── suite/                           # Suite tools
│   ├── plugins/
│   │   ├── nodes/
│   │   │   ├── sources/
│   │   │   │   ├── csv/
│   │   │   │   └── blob/
│   │   │   ├── sinks/
│   │   │   │   ├── csv/
│   │   │   │   ├── excel/
│   │   │   │   ├── blob/
│   │   │   │   ├── signed/
│   │   │   │   ├── bundles/
│   │   │   │   ├── repository/
│   │   │   │   ├── visual/
│   │   │   │   ├── analytics/
│   │   │   │   ├── embeddings/
│   │   │   │   └── utilities/
│   │   │   └── transforms/
│   │   │       └── llm/
│   │   └── experiments/
│   │       ├── aggregators/
│   │       ├── validators/
│   │       ├── baselines/
│   │       └── lifecycle/
│   └── utils/
├── integration/                             # Multi-component
│   ├── cli/
│   ├── suite_runner/
│   ├── orchestrator/
│   ├── middleware/
│   ├── retrieval/
│   ├── signed/
│   └── visual/
├── compliance/                              # ADR enforcement
│   ├── adr002/                              # Multi-Level Security
│   ├── adr002a/                             # Trusted Container
│   ├── adr004/                              # BasePlugin
│   ├── adr005/                              # Frozen plugins
│   └── security/                            # Security controls
├── performance/                             # Slow tests
│   └── baselines/
├── fixtures/                                # Shared fixtures
│   ├── conftest.py
│   ├── adr002_test_helpers.py
│   └── test_data/
└── README.md
```

---

## Mapping Rules

### Rule 1: Unit Tests

**Criteria**: Tests single component, no I/O, fast (<1s)

**Structure**: Mirror `src/elspeth/` structure

**Examples**:
| Source | Test Location |
|--------|---------------|
| `src/elspeth/plugins/nodes/sinks/csv_file.py` | `tests/unit/plugins/nodes/sinks/csv/test_write.py` |
| `src/elspeth/core/registries/base.py` | `tests/unit/core/registries/test_base_registry.py` |

### Rule 2: Integration Tests

**Criteria**: Multi-component, I/O allowed

**Structure**: Group by feature/subsystem

**Examples**:
| Test | Location |
|------|----------|
| CLI end-to-end suite execution | `tests/integration/cli/test_suite_execution.py` |
| Suite runner with middleware | `tests/integration/suite_runner/test_middleware_hooks.py` |

### Rule 3: Compliance Tests

**Criteria**: Enforces ADR requirement

**Structure**: `tests/compliance/adrXXX/`

**Examples**:
| ADR | Location |
|-----|----------|
| ADR-002 BasePlugin compliance | `tests/compliance/adr002/test_baseplugin_compliance.py` |
| ADR-005 Frozen plugins | `tests/compliance/adr005/test_baseplugin_frozen.py` |

### Rule 4: Performance Tests

**Criteria**: Slow (>1s), benchmarks

**Structure**: `tests/performance/`

**Examples**:
| Test | Location |
|------|----------|
| Performance baseline | `tests/performance/baselines/test_performance_baseline.py` |

---

## File Naming Conventions

- **test_write.py** - Happy path (successful writes)
- **test_errors.py** - Error handling
- **test_path_guard.py** - Path guard security
- **test_integration.py** - Integration scenarios
- **test_characterization.py** - Characterization tests

---

**See**: `01-REORGANIZATION_PLAN.md` for complete file mapping
