---
title: "ACF-I2: Stack Trace Exposure"
---

# ACF-I2: Stack Trace Exposure

!!! info "Provenance"
    Based on Discussion Paper DRAFT v0.3 (March 2026). Status: **v0.3 — DRAFT**

!!! warning "Scope"
    This guidance applies to high-assurance systems where silent data corruption is worse than a crash. For general-purpose software, see [When This Does NOT Apply](../when-this-does-not-apply.md).

| Property | Value |
|----------|-------|
| **STRIDE Category** | Information Disclosure |
| **Risk Rating** | Low |
| **Existing Detection** | Good |
| **Detection Feasibility** | AST-matchable |

## Description

Full Python tracebacks returned in API responses or user-facing error messages.

*Note: This entry is included for taxonomy completeness. It is well-covered by existing tooling and is lower risk than other entries. It could reasonably be treated as a sub-variant of ACF-I1.*

## Why Agents Produce This

`traceback.format_exc()` is a common debugging pattern. Agents include it in error handlers without considering the deployment context.

## Example

=== "Agent-Generated (BAD)"

    ```python
    # Agent-generated — includes full traceback in response
    import traceback

    except Exception:
        return {"error": traceback.format_exc()}
    # Full stack trace with file paths, line numbers, local variable
    # names, and library versions exposed to the caller.
    ```

=== "Correct"

    ```python
    # Correct — log the traceback, return opaque error
    import traceback

    except Exception:
        logger.error("Unhandled error", traceback=traceback.format_exc())
        return {"error": "Internal error", "reference": error_id}
    ```

## Why It's Dangerous

Stack traces reveal internal file paths, line numbers, library versions, and sometimes local variable values. While lower risk than ACF-I1 (which can expose database credentials and query parameters), stack traces still provide useful reconnaissance information for targeted attacks.

## Detection Approach

Well-covered by existing tools. Most security scanners and web framework linters detect traceback exposure. Detection looks for `traceback.format_exc()`, `traceback.print_exc()`, and similar calls in return paths of HTTP handlers.

## Related Entries

- [ACF-I1: Verbose Error Response](acf-i1.md) — the broader information disclosure pattern that ACF-I2 is a sub-variant of

---

[Return to Taxonomy Overview](index.md) | [Full Paper Reference](../paper.md#appendix-a-agentic-code-failure-taxonomy)
