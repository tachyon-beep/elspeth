// ============================================================================
// InspectorPanel
//
// Right panel with tab strip (Spec, Graph, YAML, Runs) navigable by arrow
// keys. Validate button (spinner while validating) and Execute button pinned
// to header OUTSIDE tab strip. Version history dropdown adjacent to buttons.
// Execute disabled until validation passes. Buttons always visible regardless
// of active tab.
//
// Validation result banner renders between header and tab content.
// Tab content area is wrapped in an ARIA live region.
// ============================================================================

import { useState, useCallback, useEffect } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { useExecutionStore } from "@/stores/executionStore";
import { SpecView } from "./SpecView";
import { GraphView } from "./GraphView";
import { YamlView } from "./YamlView";
import { RunsView } from "./RunsView";
import { ValidationResultBanner } from "@/components/execution/ValidationResult";

type TabId = "spec" | "graph" | "yaml" | "runs";

const TABS: { id: TabId; label: string }[] = [
  { id: "spec", label: "Spec" },
  { id: "graph", label: "Graph" },
  { id: "yaml", label: "YAML" },
  { id: "runs", label: "Runs" },
];

export function InspectorPanel() {
  const [activeTab, setActiveTab] = useState<TabId>("spec");

  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const compositionState = useSessionStore((s) => s.compositionState);
  const stateVersions = useSessionStore((s) => s.stateVersions);
  const revertToVersion = useSessionStore((s) => s.revertToVersion);
  const loadStateVersions = useSessionStore((s) => s.loadStateVersions);

  const validationResult = useExecutionStore((s) => s.validationResult);
  const isValidating = useExecutionStore((s) => s.isValidating);
  const isExecuting = useExecutionStore((s) => s.isExecuting);
  const validate = useExecutionStore((s) => s.validate);
  const execute = useExecutionStore((s) => s.execute);
  const progress = useExecutionStore((s) => s.progress);
  const error = useExecutionStore((s) => s.error);

  const canExecute =
    validationResult?.is_valid === true &&
    !isExecuting &&
    progress?.status !== "running";

  const canValidate =
    !!activeSessionId &&
    !!compositionState &&
    compositionState.nodes.length > 0 &&
    !isValidating &&
    !isExecuting;

  const handleValidate = useCallback(() => {
    if (activeSessionId && canValidate) {
      validate(activeSessionId);
    }
  }, [activeSessionId, canValidate, validate]);

  const handleExecute = useCallback(() => {
    if (activeSessionId && canExecute) {
      execute(activeSessionId);
    }
  }, [activeSessionId, canExecute, execute]);

  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);

  // Sync local selection when compositionState version changes
  useEffect(() => {
    setSelectedVersion(null);
  }, [compositionState?.version]);

  function handleVersionSelect() {
    if (selectedVersion !== null && selectedVersion !== compositionState?.version) {
      const entry = stateVersions.find((v) => v.version === selectedVersion);
      if (entry) {
        revertToVersion(entry.id);
      }
    }
  }

  function handleVersionDropdownOpen() {
    loadStateVersions();
  }

  // Tab navigation with arrow keys (left/right wrapping)
  function handleTabKeyDown(e: React.KeyboardEvent, tabIndex: number) {
    let nextIndex: number | null = null;
    if (e.key === "ArrowRight") {
      nextIndex = (tabIndex + 1) % TABS.length;
    } else if (e.key === "ArrowLeft") {
      nextIndex = (tabIndex - 1 + TABS.length) % TABS.length;
    }
    if (nextIndex !== null) {
      e.preventDefault();
      setActiveTab(TABS[nextIndex].id);
      const tabButton = document.getElementById(
        `inspector-tab-${TABS[nextIndex].id}`,
      );
      tabButton?.focus();
    }
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
        backgroundColor: "var(--color-surface-inspector)",
      }}
    >
      {/* Header: tab strip + actions */}
      <div
        style={{
          borderBottom: "1px solid var(--color-border)",
          padding: "8px 12px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          {/* Tab strip */}
          <div
            role="tablist"
            aria-label="Inspector tabs"
            className="tab-strip"
            style={{ display: "flex", gap: 4, borderBottom: "none" }}
          >
            {TABS.map((tab, i) => (
              <button
                key={tab.id}
                id={`inspector-tab-${tab.id}`}
                role="tab"
                aria-selected={activeTab === tab.id}
                aria-controls={`inspector-tabpanel-${tab.id}`}
                tabIndex={activeTab === tab.id ? 0 : -1}
                onClick={() => setActiveTab(tab.id)}
                onKeyDown={(e) => handleTabKeyDown(e, i)}
                className={`tab-strip-tab ${activeTab === tab.id ? "tab-strip-tab-active" : ""}`}
                style={{
                  padding: "6px 12px",
                  fontSize: 13,
                  fontWeight: activeTab === tab.id ? 600 : 400,
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Actions: version dropdown + validate + execute */}
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {/* Version history dropdown + revert button */}
            {compositionState && (
              <>
                <span
                  id="version-label"
                  style={{
                    fontSize: 11,
                    color: "var(--color-text-muted)",
                  }}
                >
                  Version:
                </span>
                <select
                  aria-labelledby="version-label"
                  value={selectedVersion ?? compositionState.version}
                  onChange={(e) =>
                    setSelectedVersion(Number(e.target.value))
                  }
                  onFocus={handleVersionDropdownOpen}
                  style={{
                    padding: "4px 8px",
                    fontSize: 12,
                    border: "1px solid var(--color-border-strong)",
                    borderRadius: 4,
                    backgroundColor: "var(--color-surface-elevated)",
                    color: "var(--color-text)",
                  }}
                >
                  <option value={compositionState.version}>
                    v{compositionState.version}
                  </option>
                  {stateVersions
                    .filter((v) => v.version !== compositionState.version)
                    .map((v) => (
                      <option key={v.version} value={v.version}>
                        v{v.version} ({v.node_count} nodes) — {new Date(v.created_at).toLocaleString()}
                      </option>
                    ))}
                </select>
                {selectedVersion !== null &&
                  selectedVersion !== compositionState.version && (
                    <button
                      onClick={handleVersionSelect}
                      aria-label={`Revert to version ${selectedVersion}`}
                      className="btn"
                      style={{
                        padding: "4px 10px",
                        fontSize: 12,
                      }}
                    >
                      Revert
                    </button>
                  )}
              </>
            )}

            {/* Validate button with spinner */}
            <button
              onClick={handleValidate}
              disabled={!canValidate}
              aria-label={isValidating ? "Validating" : "Validate pipeline"}
              className="btn"
              style={{
                padding: "6px 10px",
                fontSize: 12,
                minWidth: 64,
                minHeight: 36,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {isValidating ? (
                <span
                  className="spinner"
                  role="status"
                  aria-label="Validating"
                />
              ) : (
                "Validate"
              )}
            </button>

            {/* Execute button with spinner */}
            <button
              onClick={handleExecute}
              disabled={isExecuting || !canExecute}
              aria-label={isExecuting ? "Starting pipeline" : "Execute pipeline"}
              className={`btn ${canExecute && !isExecuting ? "btn-primary" : ""}`}
              style={{
                padding: "6px 10px",
                fontSize: 12,
                minWidth: 64,
                minHeight: 36,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {isExecuting ? (
                <>
                  <span
                    className="spinner"
                    role="status"
                    aria-label="Starting pipeline"
                  />
                  Starting...
                </>
              ) : (
                "Execute"
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Error banner from execution store */}
      {error && (
        <div
          role="alert"
          className="validation-banner validation-banner-fail"
          style={{
            padding: "6px 12px",
            fontSize: 12,
          }}
        >
          {error}
        </div>
      )}

      {/* Validation result banner */}
      {validationResult && (
        <ValidationResultBanner
          result={validationResult}
          nodes={compositionState?.nodes}
        />
      )}

      {/* Tab content area with ARIA live region */}
      <div
        role="tabpanel"
        aria-live="polite"
        id={`inspector-tabpanel-${activeTab}`}
        aria-labelledby={`inspector-tab-${activeTab}`}
        style={{ flex: 1, overflow: "auto" }}
      >
        {activeTab === "spec" && <SpecView />}
        {activeTab === "graph" && <GraphView />}
        {activeTab === "yaml" && <YamlView />}
        {activeTab === "runs" && <RunsView />}
      </div>
    </div>
  );
}
