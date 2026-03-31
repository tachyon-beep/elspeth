import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { InspectorPanel } from "./InspectorPanel";
import { useSessionStore } from "@/stores/sessionStore";
import { useExecutionStore } from "@/stores/executionStore";
import type { CompositionState } from "@/types/index";

// Mock API client and websocket to prevent real calls
vi.mock("@/api/client", () => ({
  fetchSessions: vi.fn(),
  createSession: vi.fn(),
  fetchMessages: vi.fn(),
  fetchCompositionState: vi.fn(),
  sendMessage: vi.fn(),
  revertToVersion: vi.fn(),
  fetchStateVersions: vi.fn(),
  archiveSession: vi.fn(),
  validatePipeline: vi.fn(),
  executePipeline: vi.fn(),
  cancelExecution: vi.fn(),
}));

vi.mock("@/api/websocket", () => ({
  connectWebSocket: vi.fn(),
  disconnectWebSocket: vi.fn(),
}));

function makeState(
  overrides: Partial<CompositionState> = {},
): CompositionState {
  return {
    version: 1,
    source: null,
    nodes: [
      {
        id: "t1",
        name: "Uppercase",
        type: "transform" as const,
        plugin: "uppercase",
        config: {},
        config_summary: "field: name",
      },
    ],
    edges: [],
    outputs: [],
    metadata: { name: "test", description: "" },
    ...overrides,
  };
}

describe("ValidationDot in InspectorPanel", () => {
  beforeEach(() => {
    useSessionStore.setState({
      activeSessionId: "session-1",
      compositionState: null,
      stateVersions: [],
      isLoadingVersions: false,
    });
    useExecutionStore.setState({
      validationResult: null,
      isValidating: false,
      isExecuting: false,
      progress: null,
      error: null,
    });
  });

  it("shows amber dot when not validated", () => {
    useSessionStore.setState({
      compositionState: makeState(),
    });
    render(<InspectorPanel />);
    const dot = screen.getByLabelText("Not validated");
    expect(dot).toBeInTheDocument();
  });

  it("shows green dot when validation passed", () => {
    useSessionStore.setState({
      compositionState: makeState(),
    });
    useExecutionStore.setState({
      validationResult: { is_valid: true, summary: "All checks passed", checks: [], errors: [] },
    });
    render(<InspectorPanel />);
    const dot = screen.getByLabelText("Validation passed");
    expect(dot).toBeInTheDocument();
  });

  it("shows red dot when validation failed", () => {
    useSessionStore.setState({
      compositionState: makeState(),
    });
    useExecutionStore.setState({
      validationResult: {
        is_valid: false,
        summary: "Validation failed",
        checks: [],
        errors: [
          {
            component_id: "source",
            component_type: "source",
            message: "Missing source",
            suggestion: null,
          },
        ],
      },
    });
    render(<InspectorPanel />);
    const dot = screen.getByLabelText("Validation failed");
    expect(dot).toBeInTheDocument();
  });

  it("hides dot when no pipeline", () => {
    useSessionStore.setState({
      compositionState: null,
    });
    render(<InspectorPanel />);
    expect(screen.queryByLabelText("Not validated")).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Validation passed"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Validation failed"),
    ).not.toBeInTheDocument();
  });

  it("hides dot when pipeline has no nodes", () => {
    useSessionStore.setState({
      compositionState: makeState({ nodes: [] }),
    });
    render(<InspectorPanel />);
    expect(screen.queryByLabelText("Not validated")).not.toBeInTheDocument();
  });
});
