---
title: "ACF-I1: Verbose Error Response"
---

# ACF-I1: Verbose Error Response

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Information Disclosure |
| **Risk Rating** | Medium |
| **Existing Detection** | Partial |
| **Detection Feasibility** | AST-matchable (partial) |

## Description

Error handlers expose internal system details (database schemas, file paths, query parameters, library versions) in error responses.

## Why Agents Produce This

Agents produce "helpful" error messages that include full context. During development, this is valuable. In production, it's reconnaissance information. Agents don't distinguish between development and production error handling because the distinction is contextual, not syntactic.

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Agent-generated — "helpful" error response with full context
    except DatabaseError as e:
        return {
            "error": str(e),
            "query": sql,
            "connection": str(db_url),
        }
    # Exposes database schema details, the exact query that failed,
    # and the database connection string — all useful for an attacker.
    ```

=== "Correct"

    ```python
    # Correct — log internally, return opaque error to caller
    except DatabaseError as e:
        logger.error(
            "Database query failed",
            query=sql,
            connection=db_url,
            error=str(e),
        )
        return {"error": "Internal error", "reference": error_id}
    # Details logged where operators can see them.
    # Caller gets an opaque reference they can report for investigation.
    ```

## Why It's Dangerous

Verbose error responses provide attackers with reconnaissance information: database schemas reveal table and column names, file paths reveal deployment structure, query parameters reveal business logic, and library versions reveal known vulnerabilities. This information reduces the effort required to craft targeted attacks.

## Detection Approach

Existing scanners detect some cases (credential patterns, known sensitive variable names). Comprehensive detection requires understanding which variables contain sensitive information — a context-dependent judgment. AST-based rules can flag common patterns like `str(e)` in return values from exception handlers, but false positive rates vary by codebase.

## Related Entries

- [ACF-I2: Stack Trace Exposure](acf-i2.md) — related information disclosure pattern involving full tracebacks

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
