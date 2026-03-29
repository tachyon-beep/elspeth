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
import type { NodeSpec } from "@/types/index";

// ── Node colours matching App.css type badge colours ─────────────────────────
// React Flow requires inline style values -- CSS variables cannot be used.
// These values mirror the App.css custom properties:
// #f66 = --color-error, #999 = --color-text-muted, #b0b0c0 = --color-text-secondary

const NODE_COLORS: Record<NodeSpec["type"], string> = {
  source: "rgba(102, 204, 153, 0.15)",
  transform: "rgba(255, 204, 102, 0.15)",
  gate: "rgba(204, 153, 255, 0.15)",
  sink: "rgba(255, 153, 102, 0.15)",
};

const NODE_BORDER_COLORS: Record<NodeSpec["type"], string> = {
  source: "#6c9",
  transform: "#fc6",
  gate: "#c9f",
  sink: "#f96",
};

const NODE_TEXT_COLORS: Record<NodeSpec["type"], string> = {
  source: "#6c9",
  transform: "#fc6",
  gate: "#c9f",
  sink: "#f96",
};

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
        backgroundColor: NODE_COLORS[node.type],
        border: `2px solid ${NODE_BORDER_COLORS[node.type]}`,
        color: NODE_TEXT_COLORS[node.type],
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
        stroke: edge.edge_type === "error" ? "#f66" : "#999",
        strokeWidth: 1.5,
      },
      labelStyle: { fontSize: 10, fill: "#b0b0c0" },
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
  const edgeCount = compositionState.edges.length;
  const ariaLabel = `Pipeline graph with ${nodeCount} component${nodeCount !== 1 ? "s" : ""}. Use the Spec tab for keyboard-accessible detail.`;

  return (
    <div
      style={{ width: "100%", height: "100%" }}
      aria-label={ariaLabel}
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
