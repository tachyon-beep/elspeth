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
      className="plugin-card"
    >
      {/* Header — always visible */}
      <div className="plugin-card-header">
        <span className="plugin-card-name">
          {plugin.name}
        </span>
        <span className="plugin-card-desc">
          {plugin.description}
        </span>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div
          className="plugin-card-expanded"
          onClick={(e) => e.stopPropagation()}
        >
          {schemaError ? (
            <span className="plugin-card-schema-error">
              Failed to load schema. Collapse and expand to retry.
            </span>
          ) : schema === null ? (
            <span className="plugin-card-schema-loading">
              Loading...
            </span>
          ) : configSchema?.properties ? (
            <div className="plugin-card-fields">
              {Object.entries(configSchema.properties).map(([name, field]) => (
                <div key={name}>
                  <span className="plugin-card-field-name">{name}</span>
                  <span className="plugin-card-field-type">
                    {(field as { type?: string }).type ?? "any"}
                  </span>
                  {configSchema.required?.includes(name) && (
                    <span className="plugin-card-field-required">
                      required
                    </span>
                  )}
                  {(field as { description?: string }).description && (
                    <div className="plugin-card-field-desc">
                      {(field as { description?: string }).description}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <span className="plugin-card-no-fields">
              No configuration fields.
            </span>
          )}
        </div>
      )}
    </div>
  );
}
