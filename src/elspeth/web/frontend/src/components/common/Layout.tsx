import {
  useState,
  useRef,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";

const INSPECTOR_WIDTH_KEY = "elspeth_inspector_width";
const SIDEBAR_COLLAPSED_KEY = "elspeth_sidebar_collapsed";

const MIN_INSPECTOR_WIDTH = 240;
const DEFAULT_INSPECTOR_WIDTH = 320;
const SIDEBAR_EXPANDED_WIDTH = 200;
const SIDEBAR_COLLAPSED_WIDTH = 40;

function loadPersistedNumber(key: string, fallback: number): number {
  const raw = localStorage.getItem(key);
  if (raw === null) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function loadPersistedBoolean(key: string, fallback: boolean): boolean {
  const raw = localStorage.getItem(key);
  if (raw === null) return fallback;
  return raw === "true";
}

interface LayoutProps {
  sidebar: ReactNode;
  chat: ReactNode;
  inspector: ReactNode;
}

/**
 * Three-panel CSS grid layout.
 *
 * - Sessions sidebar: 200px fixed, collapsible to 40px (persisted to localStorage)
 * - Chat panel: flex (1fr, takes remaining space)
 * - Inspector panel: 320px default, resizable via drag handle (persisted to localStorage)
 *   Min 240px, max 50% viewport width.
 * - Minimum supported width: 1280px (horizontal scroll below that).
 */
export function Layout({ sidebar, chat, inspector }: LayoutProps) {
  const [inspectorWidth, setInspectorWidth] = useState(() =>
    loadPersistedNumber(INSPECTOR_WIDTH_KEY, DEFAULT_INSPECTOR_WIDTH)
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    loadPersistedBoolean(SIDEBAR_COLLAPSED_KEY, false)
  );
  const isResizing = useRef(false);

  // Persist inspector width to localStorage when it changes.
  useEffect(() => {
    localStorage.setItem(INSPECTOR_WIDTH_KEY, String(inspectorWidth));
  }, [inspectorWidth]);

  // Persist sidebar collapsed state to localStorage when it changes.
  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  const handleToggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => !prev);
  }, []);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizing.current = true;

    function handleMouseMove(ev: MouseEvent) {
      if (!isResizing.current) return;
      const newWidth = window.innerWidth - ev.clientX;
      const maxWidth = window.innerWidth * 0.5;
      setInspectorWidth(Math.max(MIN_INSPECTOR_WIDTH, Math.min(newWidth, maxWidth)));
    }

    function handleMouseUp() {
      isResizing.current = false;
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);

  const sidebarWidth = sidebarCollapsed
    ? SIDEBAR_COLLAPSED_WIDTH
    : SIDEBAR_EXPANDED_WIDTH;

  return (
    <div
      className="app-layout"
      style={{
        display: "grid",
        gridTemplateColumns: `${sidebarWidth}px 1fr ${inspectorWidth}px`,
        gridTemplateRows: "100vh",
        gridTemplateAreas: '"sidebar chat inspector"',
        height: "100vh",
        minWidth: 1280,
        overflow: "hidden",
      }}
    >
      {/* Sidebar panel */}
      <div
        className="layout-sidebar"
        style={{
          gridArea: "sidebar",
          display: "flex",
          flexDirection: "column",
          borderRight: "1px solid var(--color-border)",
          backgroundColor: "var(--color-surface-sidebar)",
          overflow: "hidden",
          transition: "width 150ms ease",
          width: sidebarWidth,
        }}
      >
        {/* Collapse toggle */}
        <button
          className="sidebar-toggle"
          onClick={handleToggleSidebar}
          aria-label={
            sidebarCollapsed ? "Expand sessions sidebar" : "Collapse sessions sidebar"
          }
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "100%",
            minHeight: 44, // 44px minimum for iOS touch targets (WCAG 2.5.8)
            minWidth: 44,
            border: "none",
            borderBottom: "1px solid var(--color-border)",
            backgroundColor: "transparent",
            color: "var(--color-text-muted)",
            cursor: "pointer",
            flexShrink: 0,
            fontSize: 14,
          }}
        >
          {sidebarCollapsed ? "\u25B6" : "\u25C0"}
        </button>
        {/* Sidebar content — hidden when collapsed */}
        <div
          style={{
            flex: 1,
            overflow: "hidden",
            display: sidebarCollapsed ? "none" : "flex",
            flexDirection: "column",
          }}
        >
          {sidebar}
        </div>
      </div>

      {/* Chat panel */}
      <div
        className="layout-chat"
        style={{
          gridArea: "chat",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          backgroundColor: "var(--color-surface)",
        }}
      >
        {chat}
      </div>

      {/* Inspector panel with resize handle */}
      <div
        className="layout-inspector"
        style={{
          gridArea: "inspector",
          position: "relative",
          borderLeft: "1px solid var(--color-border)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          backgroundColor: "var(--color-surface-inspector)",
        }}
      >
        {/* Drag-to-resize handle */}
        <div
          className="resize-handle"
          onMouseDown={handleMouseDown}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize inspector panel"
          tabIndex={0}
          onKeyDown={(e) => {
            // Arrow keys adjust inspector width by 10px increments
            if (e.key === "ArrowLeft") {
              e.preventDefault();
              setInspectorWidth((w) =>
                Math.min(w + 10, window.innerWidth * 0.5)
              );
            } else if (e.key === "ArrowRight") {
              e.preventDefault();
              setInspectorWidth((w) => Math.max(w - 10, MIN_INSPECTOR_WIDTH));
            }
          }}
          style={{
            position: "absolute",
            left: -8,
            top: 0,
            bottom: 0,
            width: 20,
            cursor: "col-resize",
            backgroundColor: "transparent",
            zIndex: 10,
            touchAction: "none",
          }}
        />
        {inspector}
      </div>
    </div>
  );
}
