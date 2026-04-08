import { useEffect, useRef, useId, type ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import mermaid from "mermaid";

// Initialize mermaid once with dark theme matching ELSPETH's color palette
mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  themeVariables: {
    primaryColor: "#1a3d47",
    primaryBorderColor: "#4db89a",
    primaryTextColor: "#dff0ee",
    lineColor: "#6a9898",
    secondaryColor: "#28504a",
    tertiaryColor: "#0f2d35",
  },
});

interface MarkdownRendererProps {
  content: string;
}

/**
 * Renders markdown content with GFM support and Mermaid diagram rendering.
 *
 * Mermaid code blocks (```mermaid) are rendered as interactive diagrams.
 * All other code blocks render as syntax-highlighted <pre><code>.
 */
export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code: CodeBlock,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

/**
 * Custom code renderer that intercepts mermaid blocks and renders
 * them as diagrams, while passing all other code through normally.
 */
function CodeBlock({
  className,
  children,
  ...props
}: ComponentPropsWithoutRef<"code">) {
  const language = className?.replace("language-", "") ?? "";
  const code = String(children).replace(/\n$/, "");

  // Inline code (no language, rendered inside a <p>)
  if (!className) {
    return <code className="inline-code" {...props}>{children}</code>;
  }

  // Mermaid diagrams get special treatment
  if (language === "mermaid") {
    return <MermaidDiagram chart={code} />;
  }

  // All other code blocks render as <pre><code>
  return (
    <pre className="code-block">
      <code className={className} {...props}>
        {code}
      </code>
    </pre>
  );
}

/**
 * Renders a Mermaid diagram. Uses mermaid.render() to produce SVG,
 * then injects it via innerHTML (mermaid's API requires this).
 *
 * Falls back to a <pre> block if mermaid parsing fails.
 */
function MermaidDiagram({ chart }: { chart: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const uniqueId = useId().replace(/:/g, "-");

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;

    mermaid
      .render(`mermaid-${uniqueId}`, chart)
      .then(({ svg }) => {
        if (!cancelled && container) {
          container.innerHTML = svg;
        }
      })
      .catch(() => {
        if (!cancelled && container) {
          container.textContent = chart;
          container.classList.add("mermaid-fallback");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [chart, uniqueId]);

  return (
    <div
      ref={containerRef}
      className="mermaid-container"
      role="img"
      aria-label="Mermaid diagram"
    />
  );
}
