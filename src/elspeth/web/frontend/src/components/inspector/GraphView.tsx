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
} from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import "@xyflow/react/dist/style.css";
import { useSessionStore } from "@/stores/sessionStore";
import { BADGE_COLORS, BADGE_BACKGROUNDS, EDGE_COLORS, EDGE_LABEL_COLOR } from "@/styles/tokens";

const NODE_WIDTH = 180;
const NODE_HEIGHT = 50;

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
  g.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 60 });

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
    if (!compositionState || compositionState.nodes.length === 0) {
      return { nodes: [] as Node[], edges: [] as Edge[] };
    }

    const rfNodes: Node[] = compositionState.nodes.map((node) => ({
      id: node.id,
      data: { label: node.name },
      position: { x: 0, y: 0 }, // Will be set by dagre
      style: {
        backgroundColor: BADGE_BACKGROUNDS[node.type],
        border: `2px solid ${BADGE_COLORS[node.type]}`,
        color: BADGE_COLORS[node.type],
        borderRadius: 6,
        padding: "8px 12px",
        fontSize: 12,
        fontWeight: 600,
        width: NODE_WIDTH,
        textAlign: "center" as const,
      },
    }));

    const rfEdges: Edge[] = compositionState.edges.map((edge, i) => ({
      id: `e-${edge.source}-${edge.target}-${i}`,
      source: edge.source,
      target: edge.target,
      label: edge.label ?? undefined,
      animated: edge.edge_type === "error",
      style: {
        stroke: edge.edge_type === "error" ? EDGE_COLORS.error : EDGE_COLORS.normal,
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
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
