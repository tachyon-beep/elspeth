// ============================================================================
// SpecView -- THE KEY INTERACTIVE COMPONENT
//
// Renders CompositionState as a vertical list of component cards.
//
// Type badges: SOURCE (green), TRANSFORM (amber), GATE (purple), SINK (orange)
// -- text + colour, not colour alone (WCAG 1.4.1).
//
// Each card shows:
// - Type badge with text label
// - Plugin name and config summary
// - Next-node indicators: down-arrow + next_node_name
// - Gate route indicators: check/cross + route_label -> target
// - Error sink indicator: warning + on_error -> error_sink
//
// CLICK-TO-HIGHLIGHT:
// - Click a card -> selectedNodeId state
// - Compute upstream (INPUT badge) and downstream (OUTPUT/route badges) from edges
// - Unrelated cards dim BACKGROUND only (not text opacity -- accessibility)
// - Click again or background to deselect
//
// KEYBOARD:
// - Cards are focusable via Tab (tabindex="0")
// - Selectable via Enter/Space
// - Focus indicator via App.css :focus-visible rule
//
// Empty state: "No pipeline yet -- describe what you want to build in the chat."
// ============================================================================

import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useExecutionStore } from "@/stores/executionStore";
import { useComposer } from "@/hooks/useComposer";
import type { NodeSpec, EdgeSpec, CompositionState, ValidationEntryDTO, ValidationError, ValidationWarning } from "@/types/index";

// ── Type badge CSS class mapping ─────────────────────────────────────────────
// Uses .type-badge + .type-badge-{type} classes from App.css

const TYPE_BADGE_CLASSES: Record<NodeSpec["node_type"], string> = {
  transform: "type-badge type-badge-transform",
  gate: "type-badge type-badge-gate",
  aggregation: "type-badge type-badge-aggregation",
  coalesce: "type-badge type-badge-coalesce",
};

const TYPE_LABELS: Record<NodeSpec["node_type"], string> = {
  transform: "TRANSFORM",
  gate: "GATE",
  aggregation: "AGGREGATION",
  coalesce: "COALESCE",
};

// CSS variable names for colored card bands by node type
const TYPE_BAND_COLORS: Record<NodeSpec["node_type"], string> = {
  transform: "var(--color-badge-transform)",
  gate: "var(--color-badge-gate)",
  aggregation: "var(--color-badge-aggregation)",
  coalesce: "var(--color-badge-coalesce)",
};

// Source and sink use their own badge styles
const SOURCE_BADGE_CLASS = "type-badge type-badge-source";
const SINK_BADGE_CLASS = "type-badge type-badge-sink";

// ── Relationship computation ─────────────────────────────────────────────────

/**
 * Compute upstream and downstream node IDs from the edge list.
 * Upstream: nodes that have an edge targeting this node.
 * Downstream: nodes that this node has an edge pointing to, with optional label.
 */
function computeRelationships(
  nodeId: string,
  edges: EdgeSpec[],
): { upstream: Set<string>; downstream: Map<string, string | null> } {
  const upstream = new Set<string>();
  const downstream = new Map<string, string | null>();

  for (const edge of edges) {
    if (edge.to_node === nodeId) {
      upstream.add(edge.from_node);
    }
    if (edge.from_node === nodeId) {
      // Derive route label from edge_type when edge.label is absent
      const label = edge.label
        ?? (edge.edge_type === "route_true" ? "true"
          : edge.edge_type === "route_false" ? "false"
          : null);
      downstream.set(edge.to_node, label);
    }
  }

  return { upstream, downstream };
}

/**
 * Get the relationship badge for a node relative to the selected node.
 * Returns null if the node has no relationship to the selection.
 */
function getRelBadge(
  nodeId: string,
  selectedId: string | null,
  upstream: Set<string>,
  downstream: Map<string, string | null>,
): { label: string; color: string } | null {
  if (nodeId === selectedId) {
    return { label: "SELECTED", color: "var(--color-accent)" };
  }
  if (upstream.has(nodeId)) {
    return { label: "INPUT", color: "var(--color-success)" };
  }
  if (downstream.has(nodeId)) {
    const routeLabel = downstream.get(nodeId);
    if (routeLabel) {
      return { label: routeLabel.toUpperCase(), color: "var(--color-warning)" };
    }
    return { label: "OUTPUT", color: "var(--color-badge-gate)" };
  }
  return null;
}

// ── Connection indicator rendering ───────────────────────────────────────────

interface ConnectionIndicatorProps {
  edge: EdgeSpec;
  compositionState: CompositionState;
}

function ConnectionIndicator({
  edge,
  compositionState,
}: ConnectionIndicatorProps) {
  const targetNode = compositionState.nodes.find((n) => n.id === edge.to_node);
  const targetName = targetNode?.id ?? edge.to_node;

  if (edge.edge_type === "on_error") {
    return (
      <div>
        <span aria-hidden="true">{"\u26A0"}</span> <span className="sr-only">error route to</span>on_error <span aria-hidden="true">{"\u2192"}</span> {targetName}
      </div>
    );
  }

  if (edge.edge_type.startsWith("route")) {
    // Gate route indicators — derive label from edge_type when edge.label is absent
    const routeLabel = edge.label ?? (edge.edge_type === "route_true" ? "true" : edge.edge_type === "route_false" ? "false" : edge.edge_type);
    const isTrue =
      routeLabel.toLowerCase() === "true" ||
      routeLabel.toLowerCase() === "yes";
    const isFalse =
      routeLabel.toLowerCase() === "false" ||
      routeLabel.toLowerCase() === "no";

    let prefix: string;
    if (isTrue) {
      prefix = "\u2713"; // checkmark
    } else if (isFalse) {
      prefix = "\u2717"; // cross
    } else {
      prefix = "\u2022"; // bullet for other route labels
    }

    return (
      <div>
        <span aria-hidden="true">{prefix}</span> {routeLabel} <span aria-hidden="true">{"\u2192"}</span><span className="sr-only"> routes to</span> {targetName}
      </div>
    );
  }

  // Default continue edge
  return (
    <div>
      <span aria-hidden="true">{"\u2193"}</span><span className="sr-only">continues to</span> {targetName}
    </div>
  );
}

// ── SuggestionBanner — collapsible info banner with clickable items ─────────

interface SuggestionBannerProps {
  suggestions: ValidationEntryDTO[];
  onApply?: (suggestion: ValidationEntryDTO) => void;
  isApplying?: boolean;
}

function SuggestionBanner({ suggestions, onApply, isApplying }: SuggestionBannerProps) {
  const [expanded, setExpanded] = useState(suggestions.length <= 2);

  return (
    <div
      role="note"
      style={{
        padding: "8px 12px",
        backgroundColor: "var(--color-info-bg)",
        borderRadius: 6,
        fontSize: 13,
        color: "var(--color-info)",
        border: "1px solid var(--color-info-border)",
      }}
    >
      <div
        style={{
          fontWeight: 600,
          marginBottom: expanded ? 4 : 0,
          cursor: "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded(!expanded);
          }
        }}
        tabIndex={0}
        role="button"
        aria-expanded={expanded}
      >
        <span>Suggestions ({suggestions.length})</span>
        <span style={{ fontSize: 11 }}>{expanded ? "▲" : "▼"}</span>
      </div>
      {expanded && (
        <ul style={{ margin: 0, paddingLeft: 16 }}>
          {suggestions.map((entry, i) => (
            <li
              key={i}
              style={{
                marginBottom: 4,
                display: "flex",
                alignItems: "flex-start",
                gap: 8,
              }}
            >
              <span style={{ flex: 1 }}>
                <strong>{entry.component}:</strong> {entry.message}
              </span>
              {onApply && (
                <button
                  onClick={() => onApply(entry)}
                  disabled={isApplying}
                  title="Ask assistant to apply this suggestion"
                  aria-label={`Apply suggestion: ${entry.message}`}
                  style={{
                    padding: "2px 8px",
                    fontSize: 11,
                    backgroundColor: isApplying
                      ? "var(--color-surface)"
                      : "var(--color-accent)",
                    color: isApplying
                      ? "var(--color-text-muted)"
                      : "var(--color-text-inverse)",
                    border: "none",
                    borderRadius: 4,
                    cursor: isApplying ? "not-allowed" : "pointer",
                    flexShrink: 0,
                    whiteSpace: "nowrap",
                  }}
                >
                  {isApplying ? "Applying..." : "Apply"}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── SpecView component ───────────────────────────────────────────────────────

export function SpecView() {
  const compositionState = useSessionStore((s) => s.compositionState);
  const selectedNodeId = useSessionStore((s) => s.selectedNodeId);
  const selectNode = useSessionStore((s) => s.selectNode);
  const validationResult = useExecutionStore((s) => s.validationResult);
  const { sendMessage, isComposing } = useComposer();

  // Handler for applying a suggestion via the LLM
  const handleApplySuggestion = useCallback(
    (suggestion: ValidationEntryDTO) => {
      const prompt = `Please apply this suggestion to the pipeline:\n\n**${suggestion.component}:** ${suggestion.message}`;
      sendMessage(prompt);
    },
    [sendMessage],
  );

  // Refs for scroll-into-view when selection changes (e.g., from GraphView click)
  const cardRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  // Auto-scroll to selected card when selection changes from external source
  useEffect(() => {
    if (selectedNodeId) {
      const card = cardRefs.current.get(selectedNodeId);
      card?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [selectedNodeId]);

  // Build maps of component_id -> errors/warnings for inline display
  const { nodeErrors, nodeWarnings } = useMemo(() => {
    const errors = new Map<string, ValidationError[]>();
    const warnings = new Map<string, ValidationWarning[]>();

    if (validationResult) {
      for (const err of validationResult.errors) {
        if (err.component_id) {
          const existing = errors.get(err.component_id) ?? [];
          existing.push(err);
          errors.set(err.component_id, existing);
        }
      }
      if (validationResult.warnings) {
        for (const warn of validationResult.warnings) {
          if (warn.component_id) {
            const existing = warnings.get(warn.component_id) ?? [];
            existing.push(warn);
            warnings.set(warn.component_id, existing);
          }
        }
      }
    }

    return { nodeErrors: errors, nodeWarnings: warnings };
  }, [validationResult]);

  // Compute relationships for the selected node
  const { upstream, downstream } =
    selectedNodeId && compositionState
      ? computeRelationships(selectedNodeId, compositionState.edges)
      : {
          upstream: new Set<string>(),
          downstream: new Map<string, string | null>(),
        };

  const isRelated = useCallback(
    (nodeId: string) =>
      nodeId === selectedNodeId ||
      upstream.has(nodeId) ||
      downstream.has(nodeId),
    [selectedNodeId, upstream, downstream],
  );

  function handleCardClick(nodeId: string) {
    selectNode(selectedNodeId === nodeId ? null : nodeId);
  }

  function handleBackgroundClick(e: React.MouseEvent) {
    // Only deselect if clicking the container itself, not a card
    if (e.target === e.currentTarget) {
      selectNode(null);
    }
  }

  function handleCardKeyDown(e: React.KeyboardEvent, nodeId: string) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleCardClick(nodeId);
    }
  }

  // Empty state
  const hasContent =
    compositionState &&
    (compositionState.source !== null ||
      compositionState.nodes.length > 0 ||
      compositionState.outputs.length > 0);
  if (!hasContent) {
    return (
      <div
        className="empty-state"
        style={{
          padding: 24,
          fontSize: 14,
        }}
      >
        Send a message to start building your pipeline. Components will appear here as ELSPETH composes them.
      </div>
    );
  }

  // Build a map of node -> outgoing edges for connection indicators
  const nodeDownstream = new Map<string, EdgeSpec[]>();
  for (const edge of compositionState.edges) {
    const existing = nodeDownstream.get(edge.from_node) ?? [];
    existing.push(edge);
    nodeDownstream.set(edge.from_node, existing);
  }

  return (
    <div
      onClick={handleBackgroundClick}
      style={{
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      {/* Stage 1 validation errors */}
      {compositionState.validation_errors &&
        compositionState.validation_errors.length > 0 && (
          <div
            role="alert"
            style={{
              padding: "8px 12px",
              backgroundColor: "var(--color-error-bg)",
              borderRadius: 6,
              fontSize: 13,
              color: "var(--color-error)",
              border: "1px solid var(--color-error-border)",
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Errors</div>
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {compositionState.validation_errors.map((msg, i) => (
                <li key={i} style={{ marginBottom: 2 }}>
                  {msg}
                </li>
              ))}
            </ul>
          </div>
        )}

      {/* Stage 1 validation warnings */}
      {compositionState.validation_warnings &&
        compositionState.validation_warnings.length > 0 && (
          <div
            role="status"
            style={{
              padding: "8px 12px",
              backgroundColor: "var(--color-warning-bg)",
              borderRadius: 6,
              fontSize: 13,
              color: "var(--color-warning)",
              border: "1px solid var(--color-warning-border)",
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Warnings</div>
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {compositionState.validation_warnings.map((entry, i) => (
                <li key={i} style={{ marginBottom: 2 }}>
                  <strong>{entry.component}:</strong> {entry.message}
                </li>
              ))}
            </ul>
          </div>
        )}

      {/* Stage 1 validation suggestions — clickable to send to LLM */}
      {compositionState.validation_suggestions &&
        compositionState.validation_suggestions.length > 0 && (
          <SuggestionBanner
            suggestions={compositionState.validation_suggestions}
            onApply={handleApplySuggestion}
            isApplying={isComposing}
          />
        )}

      {/* Source card */}
      {compositionState.source && (
        <div
          className="component-card"
          style={{ borderLeft: "3px solid var(--color-badge-source)" }}
        >
          <div
            style={{
              display: "flex",
              gap: 6,
              alignItems: "center",
              marginBottom: 4,
            }}
          >
            <span className={SOURCE_BADGE_CLASS}>SOURCE</span>
          </div>
          <div style={{ fontWeight: 600, fontSize: 13 }}>
            {compositionState.source.plugin}
          </div>
          {compositionState.source.on_success && (
            <div
              style={{
                marginTop: 6,
                fontSize: 11,
                color: "var(--color-text-muted)",
              }}
            >
              <span aria-hidden="true">{"\u2193"}</span>
              <span className="sr-only">continues to</span> {compositionState.source.on_success}
            </div>
          )}
        </div>
      )}

      {/* Node cards (transforms, gates, aggregations, coalesce) */}
      {compositionState.nodes.map((node) => {
        const relBadge = getRelBadge(
          node.id,
          selectedNodeId,
          upstream,
          downstream,
        );
        const isDimmed = selectedNodeId !== null && !isRelated(node.id);
        const isSelected = node.id === selectedNodeId;
        const edges = nodeDownstream.get(node.id) ?? [];

        return (
          <div
            key={node.id}
            ref={(el) => {
              if (el) cardRefs.current.set(node.id, el);
              else cardRefs.current.delete(node.id);
            }}
            tabIndex={0}
            role="button"
            aria-pressed={isSelected}
            aria-label={`${TYPE_LABELS[node.node_type]} ${node.id}${isSelected ? ", selected" : ""}`}
            onClick={(e) => {
              e.stopPropagation();
              handleCardClick(node.id);
            }}
            onKeyDown={(e) => handleCardKeyDown(e, node.id)}
            className={[
              "component-card",
              isSelected ? "component-card-selected" : "",
              isDimmed ? "component-card-dimmed" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            style={{ borderLeft: `3px solid ${TYPE_BAND_COLORS[node.node_type]}` }}
          >
            {/* Top row: type badge + relationship badge */}
            <div
              style={{
                display: "flex",
                gap: 6,
                alignItems: "center",
                marginBottom: 4,
              }}
            >
              {/* Type badge: uses CSS class from App.css */}
              <span className={TYPE_BADGE_CLASSES[node.node_type]}>
                {TYPE_LABELS[node.node_type]}
              </span>

              {/* Relationship badge (INPUT, OUTPUT, SELECTED, route label) */}
              {relBadge && (
                <span
                  style={{
                    display: "inline-block",
                    padding: "2px 6px",
                    borderRadius: 3,
                    fontSize: 10,
                    fontWeight: 700,
                    backgroundColor: `color-mix(in srgb, ${relBadge.color} 15%, transparent)`,
                    color: relBadge.color,
                    letterSpacing: "0.05em",
                  }}
                >
                  {relBadge.label}
                </span>
              )}
            </div>

            {/* Plugin name */}
            <div style={{ fontWeight: 600, fontSize: 13 }}>{node.id}</div>

            {/* Plugin name */}
            {node.plugin && (
              <div
                style={{
                  fontSize: 12,
                  color: "var(--color-text-muted)",
                  marginTop: 2,
                }}
              >
                {node.plugin}
              </div>
            )}

            {/* Connection indicators */}
            {edges.length > 0 && (
              <div
                style={{
                  marginTop: 6,
                  fontSize: 11,
                  color: "var(--color-text-muted)",
                }}
              >
                {edges.map((edge, i) => (
                  <ConnectionIndicator
                    key={`${edge.from_node}-${edge.to_node}-${i}`}
                    edge={edge}
                    compositionState={compositionState}
                  />
                ))}
              </div>
            )}

            {/* Inline validation errors */}
            {nodeErrors.get(node.id)?.map((err, i) => (
              <div
                key={`error-${i}`}
                style={{
                  marginTop: 6,
                  padding: "4px 8px",
                  borderRadius: 4,
                  backgroundColor: "var(--color-error-bg)",
                  border: "1px solid var(--color-error-border)",
                  fontSize: 11,
                  color: "var(--color-error)",
                }}
              >
                <strong>Error:</strong> {err.message}
                {err.suggestion && (
                  <div style={{ color: "var(--color-text-muted)", marginTop: 2 }}>
                    Suggestion: {err.suggestion}
                  </div>
                )}
              </div>
            ))}

            {/* Inline validation warnings */}
            {nodeWarnings.get(node.id)?.map((warn, i) => (
              <div
                key={`warning-${i}`}
                style={{
                  marginTop: 6,
                  padding: "4px 8px",
                  borderRadius: 4,
                  backgroundColor: "var(--color-warning-bg)",
                  border: "1px solid var(--color-warning-border)",
                  fontSize: 11,
                  color: "var(--color-warning)",
                }}
              >
                <strong>Warning:</strong> {warn.message}
                {warn.suggestion && (
                  <div style={{ color: "var(--color-text-muted)", marginTop: 2 }}>
                    Suggestion: {warn.suggestion}
                  </div>
                )}
              </div>
            ))}
          </div>
        );
      })}

      {/* Output/sink cards */}
      {compositionState.outputs.map((output) => (
        <div
          key={output.name}
          className="component-card"
          style={{ borderLeft: "3px solid var(--color-badge-sink)" }}
        >
          <div
            style={{
              display: "flex",
              gap: 6,
              alignItems: "center",
              marginBottom: 4,
            }}
          >
            <span className={SINK_BADGE_CLASS}>SINK</span>
          </div>
          <div style={{ fontWeight: 600, fontSize: 13 }}>{output.name}</div>
          <div
            style={{
              fontSize: 12,
              color: "var(--color-text-muted)",
              marginTop: 2,
            }}
          >
            {output.plugin}
          </div>
        </div>
      ))}
    </div>
  );
}
