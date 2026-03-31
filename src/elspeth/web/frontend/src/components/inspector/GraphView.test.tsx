import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { GraphView } from "./GraphView";
import { useSessionStore } from "@/stores/sessionStore";
import type { CompositionState, NodeSpec, EdgeSpec } from "@/types/index";

// Mock @xyflow/react — jsdom cannot do DOM measurements required by React Flow.
// Render nodes and edges as simple divs so we can assert on their presence.
vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ nodes, edges, children }: any) => (
    <div data-testid="react-flow">
      {nodes?.map((n: any) => (
        <div key={n.id} data-testid={`node-${n.id}`} style={n.style}>
          {typeof n.data?.label === "string" ? n.data.label : n.data?.label}
        </div>
      ))}
      {edges?.map((e: any) => (
        <div key={e.id} data-testid={`edge-${e.id}`}>
          {e.label}
        </div>
      ))}
      {children}
    </div>
  ),
  Background: () => null,
  Controls: () => null,
  MiniMap: () => <div data-testid="minimap" />,
}));

// Mock @dagrejs/dagre — layout is not needed in tests.
vi.mock("@dagrejs/dagre", () => ({
  default: {
    graphlib: {
      Graph: class {
        setDefaultEdgeLabel() {}
        setGraph() {}
        setNode() {}
        setEdge() {}
        node(_id: string) { return { x: 0, y: 0 }; }
      },
    },
    layout() {},
  },
}));

// Mock React Flow CSS to avoid import errors in jsdom.
vi.mock("@xyflow/react/dist/style.css", () => ({}));

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeNode(overrides: Partial<NodeSpec> = {}): NodeSpec {
  return {
    id: "n1",
    node_type: "transform",
    plugin: "llm_transform",
    input: "source_out",
    on_success: "main",
    on_error: null,
    options: {},
    ...overrides,
  };
}

function makeEdge(overrides: Partial<EdgeSpec> = {}): EdgeSpec {
  return {
    id: "e1",
    from_node: "n1",
    to_node: "n2",
    edge_type: "on_success",
    label: null,
    ...overrides,
  };
}

function makeState(overrides: Partial<CompositionState> = {}): CompositionState {
  return {
    version: 1,
    source: null,
    nodes: [],
    edges: [],
    outputs: [],
    metadata: { name: "test", description: "" },
    ...overrides,
  };
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe("GraphView", () => {
  beforeEach(() => {
    useSessionStore.setState({ compositionState: null });
  });

  it("renders nodes with type badge and plugin name", () => {
    useSessionStore.setState({
      compositionState: makeState({
        nodes: [makeNode({ id: "classify", node_type: "transform", plugin: "llm_transform" })],
      }),
    });
    render(<GraphView />);
    // The badge renders node.node_type
    expect(screen.getByText("transform")).toBeInTheDocument();
    // The node ID as display name
    expect(screen.getByText("classify")).toBeInTheDocument();
    // The plugin name
    expect(screen.getByText("llm_transform")).toBeInTheDocument();
  });

  it("renders edge labels for on_success", () => {
    useSessionStore.setState({
      compositionState: makeState({
        nodes: [
          makeNode({ id: "n1", node_type: "transform", plugin: "p" }),
          makeNode({ id: "n2", node_type: "transform", plugin: "q" }),
        ],
        edges: [makeEdge({ id: "e1", from_node: "n1", to_node: "n2", edge_type: "on_success" })],
      }),
    });
    render(<GraphView />);
    // EDGE_LABEL_MAP maps on_success -> "success"
    expect(screen.getByText("success")).toBeInTheDocument();
  });

  it("renders edge labels for on_error", () => {
    useSessionStore.setState({
      compositionState: makeState({
        nodes: [
          makeNode({ id: "n1", node_type: "transform", plugin: "p" }),
          makeNode({ id: "n2", node_type: "transform", plugin: "q" }),
        ],
        edges: [makeEdge({ id: "e1", from_node: "n1", to_node: "n2", edge_type: "on_error" })],
      }),
    });
    render(<GraphView />);
    // EDGE_LABEL_MAP maps on_error -> "error"
    expect(screen.getByText("error")).toBeInTheDocument();
  });

  it("shows minimap for >5 nodes", () => {
    const nodes = Array.from({ length: 6 }, (_, i) =>
      makeNode({ id: `n${i}`, node_type: "transform", plugin: "p" }),
    );
    useSessionStore.setState({
      compositionState: makeState({ nodes }),
    });
    render(<GraphView />);
    expect(screen.getByTestId("minimap")).toBeInTheDocument();
  });

  it("hides minimap for <=5 nodes", () => {
    const nodes = Array.from({ length: 3 }, (_, i) =>
      makeNode({ id: `n${i}`, node_type: "transform", plugin: "p" }),
    );
    useSessionStore.setState({
      compositionState: makeState({ nodes }),
    });
    render(<GraphView />);
    expect(screen.queryByTestId("minimap")).not.toBeInTheDocument();
  });
});
