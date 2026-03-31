// ============================================================================
// GraphView
//
// React Flow (@xyflow/react) DAG visualisation of the current CompositionState.
// Converts nodes and edges to React Flow format with colour-coded node types.
// Read-only (no drag-to-connect, no node deletion). Pan and zoom enabled.
// Auto-layout using dagre (@dagrejs/dagre) for hierarchical top-to-bottom.
//
// ARIA: container has aria-label describing the pipeline structure.
// "Pipeline graph with N components. Use the Spec tab for keyboard-accessible
// detail."
//
// Empty state when no nodes.
// ============================================================================

import { useMemo } from "react";
import {
  ReactFlow,
  type Node,
  type Edge,
  Background,
  Controls,
  MiniMap,
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import "@xyflow/react/dist/style.css";
import { useSessionStore } from "@/stores/sessionStore";
import { BADGE_COLORS, BADGE_BACKGROUNDS, EDGE_COLORS, EDGE_LABEL_COLOR } from "@/styles/tokens";

const NODE_WIDTH = 260;
const NODE_HEIGHT = 80;

const EDGE_LABEL_MAP: Record<string, string> = {
  on_success: "success",
  on_error: "error",
  route_true: "true",
  route_false: "false",
  fork: "fork",
};

// ── Dagre layout ─────────────────────────────────────────────────────────────

/**
 * Apply dagre layout to nodes and edges, returning positioned React Flow
 * nodes. Layout is top-to-bottom (TB) with reasonable spacing.
 */
function layoutGraph(
  rfNodes: Node[],
  rfEdges: Edge[],
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 100 });

  for (const node of rfNodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of rfEdges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  const positionedNodes = rfNodes.map((node) => {
    const pos = g.node(node.id);
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    };
  });

  return { nodes: positionedNodes, edges: rfEdges };
}

// ── GraphView component ──────────────────────────────────────────────────────

export function GraphView() {
  const compositionState = useSessionStore((s) => s.compositionState);

  const { nodes, edges } = useMemo(() => {
    const hasContent =
      compositionState &&
      (compositionState.source !== null ||
        compositionState.nodes.length > 0 ||
        compositionState.outputs.length > 0);
    if (!hasContent) {
      return { nodes: [] as Node[], edges: [] as Edge[] };
    }

    function makeRfNode(
      id: string,
      typeLabel: string,
      subtitle: string | null,
      badgeBg: string,
      badgeColor: string,
    ): Node {
      return {
        id,
        data: {
          label: (
            <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: "8px 12px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{
                  fontSize: 10,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  padding: "1px 6px",
                  borderRadius: 3,
                  backgroundColor: badgeBg,
                  color: badgeColor,
                }}>
                  {typeLabel}
                </span>
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text)" }}>
                  {id}
                </span>
              </div>
              {subtitle && (
                <div style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
                  {subtitle}
                </div>
              )}
            </div>
          ),
        },
        position: { x: 0, y: 0 },
        style: {
          backgroundColor: "var(--color-surface-elevated)",
          border: "1px solid var(--color-border-strong)",
          borderRadius: 8,
          width: NODE_WIDTH,
          height: NODE_HEIGHT,
          padding: 0,
        },
      };
    }

    const rfNodes: Node[] = [];

    // Source node (synthetic — "source" is used as from_node in edges)
    if (compositionState.source) {
      rfNodes.push(
        makeRfNode("source", "source", compositionState.source.plugin, "rgba(77, 184, 154, 0.15)", "#4db89a"),
      );
    }

    // Pipeline nodes (transforms, gates, aggregations, coalesces)
    for (const node of compositionState.nodes) {
      rfNodes.push(
        makeRfNode(node.id, node.node_type, node.plugin, BADGE_BACKGROUNDS[node.node_type], BADGE_COLORS[node.node_type]),
      );
    }

    // Output/sink nodes (synthetic — output names are used as to_node in edges)
    for (const output of compositionState.outputs) {
      rfNodes.push(
        makeRfNode(output.name, "sink", output.plugin, "rgba(224, 112, 64, 0.15)", "#e07040"),
      );
    }

    const rfEdges: Edge[] = compositionState.edges.map((edge, i) => ({
      id: `e-${edge.from_node}-${edge.to_node}-${i}`,
      source: edge.from_node,
      target: edge.to_node,
      label: EDGE_LABEL_MAP[edge.edge_type] ?? edge.edge_type,
      animated: edge.edge_type === "on_error",
      style: {
        stroke: edge.edge_type === "on_error" ? EDGE_COLORS.error : EDGE_COLORS.normal,
        strokeWidth: 1.5,
      },
      labelStyle: { fontSize: 10, fill: EDGE_LABEL_COLOR },
    }));

    return layoutGraph(rfNodes, rfEdges);
  }, [compositionState]);

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
        No pipeline to visualise. Start a conversation to build one.
      </div>
    );
  }

  const nodeCount = compositionState.nodes.length;
  const ariaLabel = `Pipeline graph with ${nodeCount} component${nodeCount !== 1 ? "s" : ""}. Use the Spec tab for keyboard-accessible detail.`;

  return (
    <div
      style={{ width: "100%", height: "100%" }}
      aria-label={ariaLabel}
      aria-roledescription="Pipeline DAG diagram"
      role="img"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        fitView
        fitViewOptions={{ padding: 0.15, maxZoom: 1.5, minZoom: 0.3 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls showInteractive={false} />
        {nodes.length > 5 && (
          <MiniMap
            nodeStrokeWidth={3}
            zoomable
            pannable
            style={{ bottom: 8, right: 8, width: 120, height: 80 }}
          />
        )}
      </ReactFlow>
    </div>
  );
}
