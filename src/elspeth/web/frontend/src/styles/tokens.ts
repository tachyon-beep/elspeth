/**
 * Design tokens for use in JS contexts (e.g. React Flow inline node styles).
 *
 * These use CSS custom property references (`var(--color-*)`) so they
 * automatically adapt to light/dark theme without JavaScript intervention.
 *
 * Note: CSS variables in inline styles work in all modern browsers.
 */

// ── Component type badge colours ─────────────────────────────────────────────

export const BADGE_COLORS = {
  transform: "var(--color-badge-transform)",
  gate: "var(--color-badge-gate)",
  aggregation: "var(--color-badge-aggregation)",
  coalesce: "var(--color-badge-coalesce)",
} as const;

export const BADGE_BACKGROUNDS = {
  transform: "var(--color-warning-bg)",      // amber family
  gate: "rgba(138, 90, 192, 0.15)",          // purple — no direct CSS var, use semi-transparent
  aggregation: "var(--color-info-bg)",       // blue family
  coalesce: "var(--color-success-bg)",       // teal family
} as const;

// ── Edge colours ─────────────────────────────────────────────────────────────

export const EDGE_COLORS = {
  normal: "var(--color-text-muted)",
  error: "var(--color-error)",
} as const;

export const EDGE_LABEL_COLOR = "var(--color-text-secondary)";

// ── Validation indicator colours ─────────────────────────────────────────────

export const VALIDATION_COLORS = {
  valid: "var(--color-success)",
  warning: "var(--color-warning)",
  invalid: "var(--color-error)",
  unchecked: "var(--color-status-pending)",
};

export const VALIDATION_BACKGROUNDS = {
  valid: "var(--color-success-bg)",
  warning: "var(--color-warning-bg)",
  invalid: "var(--color-error-bg)",
  unchecked: "rgba(122, 154, 154, 0.1)",
};
