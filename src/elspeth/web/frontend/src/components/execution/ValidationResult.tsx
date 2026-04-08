// ============================================================================
// ValidationResult Banner
//
// Inline banner displayed between the inspector header and tab content.
// Renders Stage 2 validation results with per-component attribution.
//
// Pass: green banner with checkmark, summary, and check details.
// Fail: red banner with per-component error list, component_id mapped to
// display name from CompositionState, and suggested fixes from backend.
//
// The Execute button enables/disables based on this result.
// ============================================================================

import type {
  ValidationResult as ValidationResultType,
  ValidationWarning,
  NodeSpec,
} from "@/types/index";

interface ValidationResultProps {
  result: ValidationResultType;
  /** Nodes from CompositionState for mapping component_id to display name */
  nodes?: NodeSpec[];
}

/**
 * Resolve a component_id to a human-readable display name.
 * Falls back to the raw component_id if no matching node is found.
 */
function resolveComponentName(
  componentId: string | null,
  nodes: NodeSpec[] | undefined,
): string {
  if (!componentId) return "unknown";
  if (!nodes) return componentId;
  const node = nodes.find((n) => n.id === componentId);
  return node ? `${node.node_type}:${node.id}` : componentId;
}

export function ValidationResultBanner({
  result,
  nodes,
}: ValidationResultProps) {
  if (result.is_valid) {
    return (
      <div
        role="status"
        className="validation-banner validation-banner-pass"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 4,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span aria-hidden="true">{"\u2713"}</span>
          <span style={{ fontWeight: 600 }}>{result.summary ?? "Validation passed"}</span>
        </div>
        {result.checks.length > 0 && (
          <ul
            style={{
              margin: 0,
              padding: "0 0 0 22px",
              fontSize: 12,
              color: "var(--color-success)",
            }}
          >
            {result.checks.map((check, i) => (
              <li key={i} style={{ marginBottom: 2 }}>
                <span aria-hidden="true">
                  {check.passed ? "\u2713" : "\u2717"}
                </span>{" "}
                {check.name}: {check.detail}
              </li>
            ))}
          </ul>
        )}
        {result.warnings && result.warnings.length > 0 && (
          <div style={{ marginTop: 6 }}>
            <div style={{ fontWeight: 600, fontSize: 12, color: "var(--color-warning)" }}>
              Warnings ({result.warnings.length}):
            </div>
            <ul
              style={{
                margin: "2px 0 0",
                padding: "0 0 0 22px",
                fontSize: 12,
                color: "var(--color-warning)",
              }}
            >
              {result.warnings.map((warn: ValidationWarning, i: number) => (
                <li key={i} style={{ marginBottom: 2 }}>
                  <strong>
                    [{warn.component_type ?? "unknown"}]{" "}
                    {resolveComponentName(warn.component_id, nodes)}:
                  </strong>{" "}
                  {warn.message}
                  {warn.suggestion && (
                    <div
                      style={{
                        color: "var(--color-text-muted)",
                        fontSize: 12,
                        marginTop: 2,
                      }}
                    >
                      Suggestion: {warn.suggestion}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      role="alert"
      className="validation-banner validation-banner-fail"
    >
      <div
        style={{
          padding: "8px 12px",
          fontWeight: 600,
        }}
      >
        Validation failed
      </div>
      <ul
        style={{
          margin: 0,
          padding: "0 12px 8px 28px",
        }}
      >
        {result.errors.map((err, i) => (
          <li key={i} style={{ marginBottom: 4 }}>
            <strong>
              [{err.component_type ?? "unknown"}]{" "}
              {resolveComponentName(err.component_id, nodes)}:
            </strong>{" "}
            {err.message}
            {err.suggestion && (
              <div
                style={{
                  color: "var(--color-text-muted)",
                  fontSize: 12,
                  marginTop: 2,
                }}
              >
                Suggestion: {err.suggestion}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
