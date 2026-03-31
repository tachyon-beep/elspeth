import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InspectorPanel } from "./InspectorPanel";
import { useSessionStore } from "@/stores/sessionStore";
import { useExecutionStore } from "@/stores/executionStore";
import type { CompositionState, CompositionStateVersion } from "@/types/index";

// Mock API client and websocket to prevent real calls
vi.mock("@/api/client", () => ({
  fetchSessions: vi.fn(),
  createSession: vi.fn(),
  fetchMessages: vi.fn(),
  fetchCompositionState: vi.fn(),
  sendMessage: vi.fn(),
  revertToVersion: vi.fn(),
  fetchStateVersions: vi.fn().mockResolvedValue([]),
  archiveSession: vi.fn(),
  validatePipeline: vi.fn(),
  executePipeline: vi.fn(),
  cancelExecution: vi.fn(),
  listSources: vi.fn().mockResolvedValue([]),
  listTransforms: vi.fn().mockResolvedValue([]),
  listSinks: vi.fn().mockResolvedValue([]),
  getPluginSchema: vi.fn(),
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
        node_type: "transform" as const,
        plugin: "uppercase",
        input: "source_out",
        on_success: "main",
        on_error: null,
        options: {},
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

describe("Version selector and catalog", () => {
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

  it("renders version selector with current version", () => {
    useSessionStore.setState({
      compositionState: makeState({ version: 3 }),
    });
    render(<InspectorPanel />);
    // The VersionSelector trigger button shows "v{N} ▾"
    expect(screen.getByText(/v3/)).toBeInTheDocument();
  });

  it("version dropdown opens on click", async () => {
    const versions: CompositionStateVersion[] = [
      { id: "state-2", version: 2, created_at: "2026-03-31T00:00:00Z", node_count: 5 },
      { id: "state-1", version: 1, created_at: "2026-03-30T00:00:00Z", node_count: 3 },
    ];
    useSessionStore.setState({
      compositionState: makeState({ version: 2 }),
      stateVersions: versions,
    });
    render(<InspectorPanel />);
    const user = userEvent.setup();
    // Click the version trigger button
    const trigger = screen.getByRole("button", { name: /Version 2/ });
    await user.click(trigger);
    // Dropdown listbox should be visible
    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });

  it("catalog button toggles drawer", async () => {
    useSessionStore.setState({
      compositionState: makeState(),
    });
    render(<InspectorPanel />);
    const user = userEvent.setup();

    // Drawer should not be open initially
    expect(screen.queryByText("Plugin Catalog")).not.toBeInTheDocument();

    // Click Catalog button to open
    const catalogBtn = screen.getByRole("button", { name: /Catalog/i });
    await user.click(catalogBtn);
    expect(screen.getByText("Plugin Catalog")).toBeInTheDocument();

    // Click again to close
    await user.click(catalogBtn);
    expect(screen.queryByText("Plugin Catalog")).not.toBeInTheDocument();
  });
});
