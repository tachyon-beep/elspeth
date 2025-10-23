# ADR 004 – Complete Registry Migration

## Status

Accepted (historical).

## Context

Phase 2 introduced the consolidated registry framework (`BasePluginRegistry`). Individual
registry modules still contained bespoke logic and duplicated schema validation.

## Decision

Migrate datasource, sink, middleware, and experiment registries to `BasePluginRegistry`
implementations.

## Consequences

- Uniform plugin registration and schema enforcement.
- Simplified future plugin additions.
- Requires documentation updates to remove references to legacy registries.
