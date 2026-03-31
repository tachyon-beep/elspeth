/**
 * Design tokens that must be used in JS contexts where CSS variables
 * cannot be resolved (e.g. React Flow inline node styles).
 *
 * These values MUST stay in sync with the :root block in App.css.
 * When changing App.css colour tokens, update this file in the same commit.
 */

// ── Component type badge colours ─────────────────────────────────────────────

export const BADGE_COLORS = {
  transform: "#e8a030",
  gate: "#c390f9",
  aggregation: "#61daff",
  coalesce: "#14b0ae",
} as const;

export const BADGE_BACKGROUNDS = {
  transform: "rgba(232, 160, 48, 0.15)",
  gate: "rgba(195, 144, 249, 0.15)",
  aggregation: "rgba(97, 218, 255, 0.15)",
  coalesce: "rgba(20, 176, 174, 0.15)",
} as const;

// ── Edge colours ─────────────────────────────────────────────────────────────

export const EDGE_COLORS = {
  normal: "#6a9898",     // --color-text-muted
  error: "#e85653",      // --color-error
} as const;

export const EDGE_LABEL_COLOR = "#8db8b8"; // --color-text-secondary
