// ============================================================================
// CatalogDrawer
//
// Slide-over drawer listing available plugins organised by tab
// (Sources, Transforms, Sinks). Opens from the right side of the inspector
// panel whose outermost container already carries position: relative.
//
// Data is fetched once on first open and cached in component state for the
// lifetime of the drawer instance.  Schema details are fetched on demand
// when a PluginCard is expanded and cached in a Map keyed by
// "<type>:<name>".
// ============================================================================

import { useState, useEffect, useCallback } from "react";
import {
  listSources,
  listTransforms,
  listSinks,
  getPluginSchema,
} from "@/api/client";
import type { PluginSummary, PluginSchemaInfo } from "@/types/index";
import { PluginCard } from "./PluginCard";

type CatalogTab = "sources" | "transforms" | "sinks";

interface CatalogDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CatalogDrawer({ isOpen, onClose }: CatalogDrawerProps) {
  const [activeTab, setActiveTab] = useState<CatalogTab>("sources");
  const [sources, setSources] = useState<PluginSummary[] | null>(null);
  const [transforms, setTransforms] = useState<PluginSummary[] | null>(null);
  const [sinks, setSinks] = useState<PluginSummary[] | null>(null);
  const [schemaCache, setSchemaCache] = useState<Map<string, PluginSchemaInfo>>(
    new Map(),
  );
  const [loadingSchemas, setLoadingSchemas] = useState<Set<string>>(new Set());
  const [schemaErrors, setSchemaErrors] = useState<Set<string>>(new Set());
  const [fetchError, setFetchError] = useState(false);
  const [isFetching, setIsFetching] = useState(false);

  // Fetch all three lists in parallel on first open.
  // On failure: set fetchError, don't retry until drawer is closed and reopened.
  useEffect(() => {
    if (!isOpen || sources !== null || isFetching || fetchError) return;

    setIsFetching(true);
    Promise.all([listSources(), listTransforms(), listSinks()])
      .then(([src, xfm, snk]) => {
        setSources(src);
        setTransforms(xfm);
        setSinks(snk);
      })
      .catch(() => {
        setFetchError(true);
      })
      .finally(() => {
        setIsFetching(false);
      });
  }, [isOpen, sources, isFetching, fetchError]);

  // Clear error on close so next open retries
  useEffect(() => {
    if (!isOpen && fetchError) {
      setFetchError(false);
    }
  }, [isOpen, fetchError]);

  // Keyboard: Escape closes the drawer
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const handleExpand = useCallback(
    (plugin: PluginSummary) => {
      const cacheKey = `${plugin.plugin_type}:${plugin.name}`;
      if (schemaCache.has(cacheKey) || loadingSchemas.has(cacheKey)) return;
      // Clear previous error on retry
      setSchemaErrors((prev) => {
        if (!prev.has(cacheKey)) return prev;
        const next = new Set(prev);
        next.delete(cacheKey);
        return next;
      });

      setLoadingSchemas((prev) => new Set(prev).add(cacheKey));

      getPluginSchema(plugin.plugin_type, plugin.name)
        .then((info) => {
          setSchemaCache((prev) => {
            const next = new Map(prev);
            next.set(cacheKey, info);
            return next;
          });
          setSchemaErrors((prev) => {
            if (!prev.has(cacheKey)) return prev;
            const next = new Set(prev);
            next.delete(cacheKey);
            return next;
          });
        })
        .catch(() => {
          setSchemaErrors((prev) => new Set(prev).add(cacheKey));
        })
        .finally(() => {
          setLoadingSchemas((prev) => {
            const next = new Set(prev);
            next.delete(cacheKey);
            return next;
          });
        });
    },
    [schemaCache, loadingSchemas, schemaErrors],
  );

  const pluginList: PluginSummary[] =
    activeTab === "sources"
      ? (sources ?? [])
      : activeTab === "transforms"
        ? (transforms ?? [])
        : (sinks ?? []);

  const isLoading =
    (activeTab === "sources" && sources === null) ||
    (activeTab === "transforms" && transforms === null) ||
    (activeTab === "sinks" && sinks === null);

  if (!isOpen) return <div style={{ display: "none" }} />;

  return (
    <>
      {/* Backdrop */}
      <div
        data-testid="catalog-backdrop"
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          backgroundColor: "rgba(0,0,0,0.3)",
          zIndex: 38,
        }}
      />

      {/* Drawer panel */}
      <div
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          bottom: 0,
          width: "min(320px, calc(100% - 40px))",
          zIndex: 40,
          backgroundColor: "var(--color-surface)",
          borderLeft: "1px solid var(--color-border)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "10px 12px",
            borderBottom: "1px solid var(--color-border)",
            flexShrink: 0,
          }}
        >
          <span style={{ fontWeight: 700, fontSize: 14 }}>Plugin Catalog</span>
          <button
            onClick={onClose}
            aria-label="Close plugin catalog"
            className="btn"
            style={{ padding: "4px 8px", fontSize: 14, lineHeight: 1, minWidth: 44, minHeight: 44 }}
          >
            ×
          </button>
        </div>

        {/* Tab strip */}
        <div
          role="tablist"
          aria-label="Plugin type tabs"
          style={{
            display: "flex",
            borderBottom: "1px solid var(--color-border)",
            flexShrink: 0,
          }}
        >
          {(["sources", "transforms", "sinks"] as CatalogTab[]).map((tab) => {
            const label =
              tab === "sources"
                ? "Sources"
                : tab === "transforms"
                  ? "Transforms"
                  : "Sinks";
            const isActive = activeTab === tab;
            return (
              <button
                key={tab}
                role="tab"
                aria-selected={isActive}
                onClick={() => setActiveTab(tab)}
                className={`tab-strip-tab ${isActive ? "tab-strip-tab-active" : ""}`}
                style={{
                  flex: 1,
                  padding: "8px 4px",
                  fontSize: 12,
                  fontWeight: isActive ? 600 : 400,
                }}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Scrollable plugin list */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          {fetchError ? (
            <div
              style={{
                padding: 16,
                fontSize: 12,
                color: "var(--color-error)",
              }}
            >
              Failed to load plugin catalog. Close and reopen to retry.
            </div>
          ) : isLoading || isFetching ? (
            <div
              style={{
                padding: 16,
                fontSize: 12,
                color: "var(--color-text-muted)",
              }}
            >
              Loading...
            </div>
          ) : pluginList.length === 0 ? (
            <div
              style={{
                padding: 16,
                fontSize: 12,
                color: "var(--color-text-muted)",
              }}
            >
              No plugins available.
            </div>
          ) : (
            pluginList.map((plugin) => {
              const cacheKey = `${plugin.plugin_type}:${plugin.name}`;
              const schema = schemaCache.get(cacheKey) ?? null;
              const hasSchemaError = schemaErrors.has(cacheKey);
              return (
                <PluginCard
                  key={cacheKey}
                  plugin={plugin}
                  schema={schema}
                  schemaError={hasSchemaError}
                  onExpand={() => handleExpand(plugin)}
                />
              );
            })
          )}
        </div>
      </div>
    </>
  );
}
