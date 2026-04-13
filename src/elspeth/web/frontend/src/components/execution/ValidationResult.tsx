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
  /** Callback when user clicks an error/warning to navigate to that component */
  onComponentClick?: (componentId: string) => void;
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
  onComponentClick,
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
              {result.warnings.map((warn: ValidationWarning, i: number) => {
                // Only make clickable if component is an actual node (not source/sink)
                const isNode = nodes?.some((n) => n.id === warn.component_id);
                const isClickable = warn.component_id && onComponentClick && isNode;
                const content = (
                  <>
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
                  </>
                );

                return (
                  <li key={i} style={{ marginBottom: 2 }}>
                    {isClickable ? (
                      <button
                        onClick={() => onComponentClick(warn.component_id!)}
                        style={{
                          background: "none",
                          border: "none",
                          padding: 0,
                          margin: 0,
                          font: "inherit",
                          color: "inherit",
                          textAlign: "left",
                          cursor: "pointer",
                          textDecoration: "underline",
                          textDecorationColor: "var(--color-warning-border)",
                          textUnderlineOffset: 2,
                        }}
                        title={`Click to select ${warn.component_id} in the pipeline view`}
                      >
                        {content}
                      </button>
                    ) : (
                      content
                    )}
                  </li>
                );
              })}
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
        {result.errors.map((err, i) => {
          // Only make clickable if component is an actual node (not source/sink)
          const isNode = nodes?.some((n) => n.id === err.component_id);
          const isClickable = err.component_id && onComponentClick && isNode;
          const content = (
            <>
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
            </>
          );

          return (
            <li key={i} style={{ marginBottom: 4 }}>
              {isClickable ? (
                <button
                  onClick={() => onComponentClick(err.component_id!)}
                  style={{
                    background: "none",
                    border: "none",
                    padding: 0,
                    margin: 0,
                    font: "inherit",
                    color: "inherit",
                    textAlign: "left",
                    cursor: "pointer",
                    textDecoration: "underline",
                    textDecorationColor: "var(--color-error-border)",
                    textUnderlineOffset: 2,
                  }}
                  title={`Click to select ${err.component_id} in the pipeline view`}
                >
                  {content}
                </button>
              ) : (
                content
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
