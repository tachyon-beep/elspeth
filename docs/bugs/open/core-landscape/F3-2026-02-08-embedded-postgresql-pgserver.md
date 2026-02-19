## Summary

Add an optional 'postgres-embedded' config pack that bundles PostgreSQL via pgserver, giving users a zero-install path to a full PostgreSQL backend.

## Severity

- Severity: low
- Priority: P3
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-0mpl

## Context

ELSPETH already supports PostgreSQL as a production backend. pgserver (pip install pgserver) bundles PostgreSQL binaries and manages initdb/pg_ctl automatically. This complements SQLCipher by offering a second tier:
- SQLite/SQLCipher: simplest, single file, good for single-user/dev
- pgserver: full PostgreSQL without requiring user to install/manage it
- External PostgreSQL: production multi-user deployments (already supported)

## Scope

1. Add pgserver as optional dependency in new 'postgres-embedded' extra
2. Create config pack (`packs/postgres-embedded/defaults.yaml`)
3. Add helper in LandscapeDB for pgserver lifecycle management
4. Handle server lifecycle: start on pipeline init, keep running for MCP/explain access, clean shutdown
5. Data directory convention: `./state/pgdata/`
6. Integration tests for embedded PostgreSQL backend

## Design Considerations

- pgserver still runs a server process — document this clearly
- Binary wheels are ~50MB — must be optional extra
- Platform coverage: Linux x86, macOS ARM/x86, Windows
- Server lifecycle must be robust: crash recovery, concurrent MCP access
- Port management: pgserver handles allocation, document fixed port config

## Acceptance Criteria

- [ ] `pip install elspeth[postgres-embedded]` brings in pgserver
- [ ] `elspeth run` with postgres-embedded pack works out of the box
- [ ] No PostgreSQL pre-installed on system required
- [ ] MCP analysis server works against pgserver-managed database
- [ ] Server lifecycle is clean (no orphan processes on crash/Ctrl+C)

## Blocked By

- `w2q7` — ELSPETH-NEXT (deferred to post-RC3)
