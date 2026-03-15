#!/bin/bash
# Build LaTeX output from the Markdown discussion paper.
# Markdown remains the master — this generates a .tex for review/PDF compilation.
#
# Usage:
#   ./build.sh              # Generates .tex only
#   ./build.sh --pdf        # Generates .tex and compiles to PDF (requires xelatex or pdflatex)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THREAT_MODEL_DIR="$(dirname "$SCRIPT_DIR")"
SOURCE="$THREAT_MODEL_DIR/2026-03-07-agentic-code-threat-model-discussion-paper.md"
TEMPLATE="$SCRIPT_DIR/template.tex"
METADATA="$SCRIPT_DIR/metadata.yaml"
OUTPUT_TEX="$SCRIPT_DIR/threat-model-discussion-paper.tex"
OUTPUT_PDF="$SCRIPT_DIR/threat-model-discussion-paper.pdf"

# Strip the metadata header (lines before first ## section) from Markdown,
# since the LaTeX template handles title page rendering from metadata.yaml.
# We keep everything from "## Abstract" onward.
BODY_MD=$(mktemp)
trap 'rm -f "$BODY_MD"' EXIT

sed -n '/^## Abstract$/,$p' "$SOURCE" > "$BODY_MD"

# Strip the manual Table of Contents section (LaTeX \tableofcontents handles it)
sed -i '/^## Table of Contents$/,/^---$/d' "$BODY_MD"

# Strip horizontal rules (---) — LaTeX sections provide structure
sed -i '/^---$/d' "$BODY_MD"

# Strip the final disclaimer line (template handles it)
sed -i '/^\*This is a discussion paper\./d' "$BODY_MD"

echo "Generating LaTeX..."
pandoc "$BODY_MD" \
    --template="$TEMPLATE" \
    --metadata-file="$METADATA" \
    --standalone \
    --highlight-style=tango \
    --top-level-division=chapter \
    -o "$OUTPUT_TEX"

echo "  -> $OUTPUT_TEX"

if [[ "${1:-}" == "--pdf" ]]; then
    echo "Compiling PDF..."
    cd "$SCRIPT_DIR"
    if command -v xelatex &>/dev/null; then
        xelatex -interaction=nonstopmode "$(basename "$OUTPUT_TEX")"
        xelatex -interaction=nonstopmode "$(basename "$OUTPUT_TEX")"  # second pass for TOC
    elif command -v pdflatex &>/dev/null; then
        pdflatex -interaction=nonstopmode "$(basename "$OUTPUT_TEX")"
        pdflatex -interaction=nonstopmode "$(basename "$OUTPUT_TEX")"
    else
        echo "ERROR: No LaTeX engine found (xelatex or pdflatex required)"
        exit 1
    fi
    echo "  -> $OUTPUT_PDF"
fi

echo "Done."
