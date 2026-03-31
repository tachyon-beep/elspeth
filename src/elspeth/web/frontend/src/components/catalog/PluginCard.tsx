// ============================================================================
// PluginCard
//
// Collapsible card showing plugin name, description, and config schema.
// Collapsed: name + one-line description. Expanded: config schema fields.
// ============================================================================

import { useState } from "react";
import type { PluginSummary, PluginSchemaInfo } from "@/types/index";

interface PluginCardProps {
  plugin: PluginSummary;
  schema: PluginSchemaInfo | null;
  schemaError?: boolean;
  onExpand: () => void;
}

export function PluginCard({ plugin, schema, schemaError, onExpand }: PluginCardProps) {
  const [expanded, setExpanded] = useState(false);

  function handleClick() {
    if (!expanded) {
      onExpand();
    }
    setExpanded((prev) => !prev);
  }

  const configSchema = schema?.json_schema as
    | { properties?: Record<string, unknown>; required?: string[] }
    | undefined;

  return (
    <div
      onClick={handleClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleClick();
        }
      }}
      tabIndex={0}
      role="button"
      aria-expanded={expanded}
      style={{
        padding: "8px 12px",
        borderBottom: "1px solid var(--color-border)",
        cursor: "pointer",
      }}
    >
      {/* Header — always visible */}
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontWeight: 700, fontSize: 13, color: "var(--color-text)" }}>
          {plugin.name}
        </span>
        <span
          style={{
            fontSize: 11,
            color: "var(--color-text-muted)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {plugin.description}
        </span>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div
          style={{ marginTop: 8 }}
          onClick={(e) => e.stopPropagation()}
        >
          {schemaError ? (
            <span style={{ fontSize: 12, color: "var(--color-error)" }}>
              Failed to load schema. Collapse and expand to retry.
            </span>
          ) : schema === null ? (
            <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
              Loading...
            </span>
          ) : configSchema?.properties ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {Object.entries(configSchema.properties).map(([name, field]) => (
                <div key={name}>
                  <span style={{ fontWeight: 600, fontSize: 12 }}>{name}</span>
                  <span
                    style={{ color: "var(--color-text-muted)", marginLeft: 8, fontSize: 12 }}
                  >
                    {(field as { type?: string }).type ?? "any"}
                  </span>
                  {configSchema.required?.includes(name) && (
                    <span
                      style={{
                        color: "var(--color-warning)",
                        marginLeft: 8,
                        fontSize: 10,
                      }}
                    >
                      required
                    </span>
                  )}
                  {(field as { description?: string }).description && (
                    <div
                      style={{
                        fontSize: 11,
                        color: "var(--color-text-muted)",
                        marginTop: 2,
                      }}
                    >
                      {(field as { description?: string }).description}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
              No configuration fields.
            </span>
          )}
        </div>
      )}
    </div>
  );
}
