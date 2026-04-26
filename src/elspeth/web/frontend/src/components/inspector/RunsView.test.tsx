import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { RunsView } from "./RunsView";
import { useExecutionStore } from "@/stores/executionStore";
import { useSessionStore } from "@/stores/sessionStore";
import type { Run } from "@/types/index";

function makeRun(overrides: Partial<Run> & { error?: string | null } = {}): Run {
  return {
    id: "run-1",
    session_id: "session-1",
    status: "failed",
    rows_processed: 1,
    rows_failed: 0,
    started_at: "2026-04-26T05:31:58.000Z",
    finished_at: "2026-04-26T05:31:59.000Z",
    composition_version: 1,
    ...overrides,
  } as Run;
}

describe("RunsView", () => {
  beforeEach(() => {
    useExecutionStore.getState().reset();
    useSessionStore.setState({ activeSessionId: null });
  });

  it("renders the stored failure reason for failed runs", () => {
    useExecutionStore.setState({
      runs: [
        makeRun({
          error: "Pipeline execution failed (FrameworkBugError)",
        }),
      ],
    });

    render(<RunsView />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Pipeline execution failed (FrameworkBugError)",
    );
  });

  it("never renders a negative duration for terminal runs", () => {
    useExecutionStore.setState({
      runs: [
        makeRun({
          started_at: "2026-04-26T05:31:59.500Z",
          finished_at: "2026-04-26T05:31:59.000Z",
        }),
      ],
    });

    render(<RunsView />);

    expect(screen.getByText("0s")).toBeInTheDocument();
    expect(screen.queryByText("-1s")).not.toBeInTheDocument();
  });

  it("renders rows routed to the virtual discard sink", () => {
    useExecutionStore.setState({
      runs: [
        makeRun({
          status: "completed",
          rows_processed: 3,
          discard_summary: {
            total: 3,
            validation_errors: 1,
            transform_errors: 1,
            sink_discards: 1,
          },
        }),
      ],
    });

    render(<RunsView />);

    expect(screen.getByText("3 discarded")).toBeInTheDocument();
  });
});
