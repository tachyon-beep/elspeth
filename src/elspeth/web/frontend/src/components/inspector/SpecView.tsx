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

import { useState, useCallback } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import type { NodeSpec, EdgeSpec, CompositionState } from "@/types/index";

// ── Type badge CSS class mapping ─────────────────────────────────────────────
// Uses .type-badge + .type-badge-{type} classes from App.css

const TYPE_BADGE_CLASSES: Record<NodeSpec["type"], string> = {
  source: "type-badge type-badge-source",
  transform: "type-badge type-badge-transform",
  gate: "type-badge type-badge-gate",
  sink: "type-badge type-badge-sink",
};

const TYPE_LABELS: Record<NodeSpec["type"], string> = {
  source: "SOURCE",
  transform: "TRANSFORM",
  gate: "GATE",
  sink: "SINK",
};

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
    if (edge.target === nodeId) {
      upstream.add(edge.source);
    }
    if (edge.source === nodeId) {
      downstream.set(edge.target, edge.label);
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
    return { label: "SELECTED", color: "var(--color-focus-ring)" };
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
  const targetNode = compositionState.nodes.find((n) => n.id === edge.target);
  const targetName = targetNode?.name ?? edge.target;

  if (edge.edge_type === "error") {
    return (
      <div>
        <span aria-hidden="true">{"\u26A0"}</span> <span className="sr-only">error route to</span>on_error <span aria-hidden="true">{"\u2192"}</span> {targetName}
      </div>
    );
  }

  if (edge.edge_type === "route" && edge.label) {
    // Gate route indicators with check/cross marks
    const isTrue =
      edge.label.toLowerCase() === "true" ||
      edge.label.toLowerCase() === "yes";
    const isFalse =
      edge.label.toLowerCase() === "false" ||
      edge.label.toLowerCase() === "no";

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
        <span aria-hidden="true">{prefix}</span> {edge.label} <span aria-hidden="true">{"\u2192"}</span><span className="sr-only"> routes to</span> {targetName}
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

// ── SpecView component ───────────────────────────────────────────────────────

export function SpecView() {
  const compositionState = useSessionStore((s) => s.compositionState);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

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
    setSelectedNodeId((prev) => (prev === nodeId ? null : nodeId));
  }

  function handleBackgroundClick(e: React.MouseEvent) {
    // Only deselect if clicking the container itself, not a card
    if (e.target === e.currentTarget) {
      setSelectedNodeId(null);
    }
  }

  function handleCardKeyDown(e: React.KeyboardEvent, nodeId: string) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleCardClick(nodeId);
    }
  }

  // Empty state
  if (!compositionState || compositionState.nodes.length === 0) {
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
    const existing = nodeDownstream.get(edge.source) ?? [];
    existing.push(edge);
    nodeDownstream.set(edge.source, existing);
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
      {/* Stage 1 validation errors: simple string[] from composer */}
      {compositionState.validation_errors &&
        compositionState.validation_errors.length > 0 && (
          <div
            role="alert"
            style={{
              padding: "8px 12px",
              backgroundColor: "rgba(255, 204, 102, 0.15)",
              borderRadius: 6,
              fontSize: 13,
              color: "var(--color-warning)",
              border: "1px solid rgba(255, 204, 102, 0.3)",
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>
              Composition warnings
            </div>
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {compositionState.validation_errors.map((msg, i) => (
                <li key={i} style={{ marginBottom: 2 }}>
                  {msg}
                </li>
              ))}
            </ul>
          </div>
        )}

      {/* Component cards */}
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
            tabIndex={0}
            role="button"
            aria-pressed={isSelected}
            aria-label={`${TYPE_LABELS[node.type]} ${node.name}${isSelected ? ", selected" : ""}`}
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
              <span className={TYPE_BADGE_CLASSES[node.type]}>
                {TYPE_LABELS[node.type]}
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
            <div style={{ fontWeight: 600, fontSize: 13 }}>{node.name}</div>

            {/* Config summary */}
            <div
              style={{
                fontSize: 12,
                color: "var(--color-text-muted)",
                marginTop: 2,
              }}
            >
              {node.plugin}
              {node.config_summary && ` \u2014 ${node.config_summary}`}
            </div>

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
                    key={`${edge.source}-${edge.target}-${i}`}
                    edge={edge}
                    compositionState={compositionState}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
