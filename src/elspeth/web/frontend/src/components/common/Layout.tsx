import {
  useState,
  useRef,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import { useTheme } from "@/hooks/useTheme";

const INSPECTOR_WIDTH_KEY = "elspeth_inspector_width";
const SIDEBAR_COLLAPSED_KEY = "elspeth_sidebar_collapsed";

const MIN_INSPECTOR_WIDTH = 240;
const SIDEBAR_EXPANDED_WIDTH = 200;

/**
 * Compute the default inspector width as ~50% of the space remaining
 * after the sidebar. This gives an even chat/inspector split (A4).
 * Falls back to 50% of viewport if called before layout.
 */
function defaultInspectorWidth(): number {
  const available = window.innerWidth - SIDEBAR_EXPANDED_WIDTH;
  const half = Math.round(available / 2);
  return Math.max(MIN_INSPECTOR_WIDTH, half);
}
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
 * - Inspector panel: ~50% of remaining viewport width by default, resizable via drag handle (persisted to localStorage)
 *   Min 240px, max 50% viewport width.
 * - Minimum supported width: 1280px (horizontal scroll below that).
 */
export function Layout({ sidebar, chat, inspector }: LayoutProps) {
  const [inspectorWidth, setInspectorWidth] = useState(() =>
    loadPersistedNumber(INSPECTOR_WIDTH_KEY, defaultInspectorWidth())
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    loadPersistedBoolean(SIDEBAR_COLLAPSED_KEY, false)
  );
  const isResizing = useRef(false);
  const { resolvedTheme, toggleTheme } = useTheme();

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

  const handleTouchStart = useCallback((_e: React.TouchEvent) => {
    isResizing.current = true;

    function handleTouchMove(ev: TouchEvent) {
      if (!isResizing.current) return;
      const touch = ev.touches[0];
      if (!touch) return;
      const newWidth = window.innerWidth - touch.clientX;
      const maxWidth = window.innerWidth * 0.5;
      setInspectorWidth(Math.max(MIN_INSPECTOR_WIDTH, Math.min(newWidth, maxWidth)));
    }

    function handleTouchEnd() {
      isResizing.current = false;
      document.removeEventListener("touchmove", handleTouchMove);
      document.removeEventListener("touchend", handleTouchEnd);
    }

    document.addEventListener("touchmove", handleTouchMove, { passive: true });
    document.addEventListener("touchend", handleTouchEnd);
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
        {/* Sidebar toolbar: collapse toggle + theme toggle */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: sidebarCollapsed ? "center" : "space-between",
            borderBottom: "1px solid var(--color-border)",
            flexShrink: 0,
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
              minHeight: 44,
              minWidth: 44,
              border: "none",
              backgroundColor: "transparent",
              color: "var(--color-text-muted)",
              cursor: "pointer",
              fontSize: 14,
            }}
          >
            {sidebarCollapsed ? "\u25B6" : "\u25C0"}
          </button>

          {/* Theme toggle — visible when sidebar is expanded */}
          {!sidebarCollapsed && (
            <button
              className="theme-toggle"
              onClick={toggleTheme}
              aria-label={
                resolvedTheme === "dark"
                  ? "Switch to light theme"
                  : "Switch to dark theme"
              }
              title={
                resolvedTheme === "dark"
                  ? "Switch to light theme"
                  : "Switch to dark theme"
              }
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                minHeight: 44,
                minWidth: 44,
                border: "none",
                backgroundColor: "transparent",
                color: "var(--color-text-muted)",
                cursor: "pointer",
                fontSize: 16,
                marginRight: 4,
              }}
            >
              {/* Sun for light theme, moon for dark */}
              {resolvedTheme === "dark" ? "\u2600" : "\u263E"}
            </button>
          )}
        </div>
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
          onTouchStart={handleTouchStart}
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
