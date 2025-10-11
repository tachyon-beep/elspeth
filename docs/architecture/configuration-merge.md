# Configuration Merge Timeline

```penguin
diagram "Configuration Merge Flow" {
  direction: right

  node settings "Profile YAML\n(config/settings.yaml:3)"
  node promptPack "Prompt Pack Defaults\n(config/settings.yaml:4)"
  node suiteDefaults "Suite Defaults\n(config/settings.yaml:117)"
  node experiment "Experiment Config\n(config/sample_suite/*/config.json)"
  node loader "load_settings()\n(src/elspeth/config.py:41)"
  node merged "OrchestratorConfig\n(src/elspeth/config.py:126)"
  node runner "ExperimentRunner build\n(src/elspeth/core/experiments/suite_runner.py:77)"

  settings -> loader "base definitions"
  promptPack -> loader "if prompt_pack selected"
  suiteDefaults -> loader "fallback sinks/middleware"
  loader -> merged "normalized config"

  merged -> runner "shared defaults"
  experiment -> runner "per-experiment overrides"
  promptPack -> runner "variant-level merges"
```

- `load_settings` layers prompt packs and suite defaults over the base profile before hydrating plugins (`src/elspeth/config.py:78`, `src/elspeth/config.py:95`).
- `ExperimentSuiteRunner.build_runner` merges experiment overrides, reusing default middleware, rate-limiters, and sinks where not explicitly set (`src/elspeth/core/experiments/suite_runner.py:86`, `src/elspeth/core/experiments/suite_runner.py:166`).
