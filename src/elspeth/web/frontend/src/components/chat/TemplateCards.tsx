/**
 * Pipeline template cards shown in the empty chat state.
 *
 * Provides quick-start prompts for common pipeline patterns,
 * reducing the "blank page" problem for new users.
 */

interface PipelineTemplate {
  id: string;
  title: string;
  description: string;
  prompt: string;
  icon: string;
}

const TEMPLATES: PipelineTemplate[] = [
  {
    id: "csv-to-api",
    title: "CSV to API",
    description: "Read CSV, validate data, send to REST API",
    prompt:
      "Create a pipeline that reads a CSV file, validates the data, and sends it to a REST API.",
    icon: "\u{1F4CA}", // bar chart
  },
  {
    id: "llm-classification",
    title: "LLM Classification",
    description: "Classify rows using an LLM, output to CSV",
    prompt:
      "Create a pipeline that reads data, classifies each row using an LLM, and outputs results to CSV.",
    icon: "\u{1F916}", // robot
  },
  {
    id: "data-validation",
    title: "Data Validation",
    description: "Validate against schema, quarantine invalid rows",
    prompt:
      "Create a pipeline that validates CSV data against a schema and quarantines invalid rows.",
    icon: "\u{2705}", // checkmark
  },
  {
    id: "batch-etl",
    title: "Batch ETL",
    description: "Extract, transform, and load between destinations",
    prompt:
      "Create a pipeline that extracts data from a database, transforms it, and loads to another destination.",
    icon: "\u{1F504}", // arrows cycle
  },
  {
    id: "web-scraping",
    title: "Web Scraping",
    description: "Scrape web pages, extract structured data",
    prompt:
      "Create a pipeline that scrapes web pages and extracts structured data.",
    icon: "\u{1F310}", // globe
  },
  {
    id: "file-aggregation",
    title: "File Aggregation",
    description: "Combine multiple files, dedupe, output summary",
    prompt:
      "Create a pipeline that reads multiple CSV files, deduplicates records, and outputs a combined summary.",
    icon: "\u{1F4C1}", // folder
  },
];

interface TemplateCardsProps {
  onSelectTemplate: (prompt: string) => void;
}

export function TemplateCards({ onSelectTemplate }: TemplateCardsProps) {
  return (
    <div
      style={{
        padding: "24px 32px",
        maxWidth: 800,
        margin: "0 auto",
      }}
    >
      <div
        style={{
          textAlign: "center",
          marginBottom: 24,
        }}
      >
        <h2
          style={{
            margin: "0 0 8px",
            fontSize: 18,
            fontWeight: 600,
            color: "var(--color-text)",
          }}
        >
          Welcome to ELSPETH
        </h2>
        <p
          style={{
            margin: 0,
            fontSize: 14,
            color: "var(--color-text-muted)",
          }}
        >
          Choose a template to get started, or describe your own pipeline below.
        </p>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 12,
        }}
        role="list"
        aria-label="Pipeline templates"
      >
        {TEMPLATES.map((template) => (
          <button
            key={template.id}
            onClick={() => onSelectTemplate(template.prompt)}
            className="template-card"
            role="listitem"
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-start",
              gap: 6,
              padding: "14px 16px",
              backgroundColor: "var(--color-surface-elevated)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              cursor: "pointer",
              textAlign: "left",
              transition: "border-color 150ms ease, background-color 150ms ease",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span
                style={{ fontSize: 20 }}
                aria-hidden="true"
              >
                {template.icon}
              </span>
              <span
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: "var(--color-text)",
                }}
              >
                {template.title}
              </span>
            </div>
            <span
              style={{
                fontSize: 12,
                color: "var(--color-text-muted)",
                lineHeight: 1.4,
              }}
            >
              {template.description}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
