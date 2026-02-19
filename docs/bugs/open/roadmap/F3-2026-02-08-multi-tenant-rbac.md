## Summary

Role-based access control for the audit trail and pipeline management. Transform ELSPETH from single-user tool into multi-tenant enterprise service with row-level audit security.

## Severity

- Severity: low
- Priority: P3
- Type: feature
- Status: open
- Bead ID: elspeth-rapid-w2q7.6

## Access Model

| Role | Pipelines | Runs | Audit Data | Admin |
|------|-----------|------|------------|-------|
| **Admin** | CRUD | Full | Full | User mgmt, config |
| **Engineer** | Create, run own | Own + shared | Own runs | - |
| **Auditor** | View all | View all | Full read-only | - |
| **Viewer** | View assigned | Assigned runs | Summary only | - |
| **External** | - | Specific run | Specific run lineage | - |

## Implementation Layers

1. **Authentication**: API keys, JWT tokens, optional OIDC/SAML
2. **Authorization**: Role assignments, pipeline ownership, team model
3. **Database-Level Enforcement**: PostgreSQL RLS policies as last defense
4. **Audit-the-Audit**: access_log table with HMAC chain

## Row-Level Security

- PostgreSQL RLS policies on Landscape tables
- Filter by run ownership and team membership
- Auditor role bypasses RLS
- External access via scoped JWT tokens

## Dependencies

- `w2q7.2` — Server mode (required)
- Parent: `w2q7` — ELSPETH-NEXT epic
