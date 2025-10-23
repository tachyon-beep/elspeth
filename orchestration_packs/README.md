# Orchestration Packs Directory

This directory is for storing your orchestration pack configurations. Each subdirectory should contain a complete orchestration pack with its configuration files, prompts, and settings.

## Purpose

Orchestration packs bundle together:
- Configuration YAML files
- Prompt templates
- Middleware definitions
- Plugin configurations
- Experiment definitions

## Structure

Create subdirectories for each orchestration pack:

```
orchestration_packs/
├── my-pack-1/
│   ├── settings.yaml
│   ├── experiments/
│   └── packs/
├── my-pack-2/
│   ├── settings.yaml
│   └── ...
└── README.md (this file)
```

## Usage

Run an orchestration pack with:

```bash
python -m elspeth.cli \
  --settings orchestration_packs/my-pack-1/settings.yaml \
  --suite-root orchestration_packs/my-pack-1 \
  --reports-dir outputs/my-pack-1-reports \
  --live-outputs
```

## Git Ignore

All subdirectories in `orchestration_packs/` are ignored by git (see `.gitignore`).
This allows you to keep your custom orchestration packs local without committing them to the repository.

If you want to track a specific orchestration pack in git, you can:
1. Create it elsewhere and version it separately
2. Add an exception to `.gitignore` for that specific pack
3. Use a git submodule

## Examples

The sample suite configuration in `config/sample_suite/` provides a reference implementation that you can use as a template for your own orchestration packs.

## Data Flow Architecture

With the new data flow architecture (see `docs/architecture/refactoring/data-flow-migration/`), orchestration packs can leverage:

- **Orchestrators**: Define how data flows through your pipeline
- **Nodes**: Reusable processing components (sources, sinks, transforms)
- **Protocols**: Clear contracts for plugin behavior

See `CONTRIBUTING.md` and the architecture documentation for more details on creating orchestration packs with the new architecture.
