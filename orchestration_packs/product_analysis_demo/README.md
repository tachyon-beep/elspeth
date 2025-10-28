# Product Analysis Demo

A comprehensive demonstration of Elspeth's advanced Jinja2 templating capabilities with a real-world product analysis pipeline.

## Overview

This demo showcases a complete **CSV → LLM → CSV** pipeline that:
- Loads product data from a CSV datasource
- Applies advanced Jinja2 templates with conditional logic, loops, and filters
- Sends 3 prompts per product (main analysis + 2 criteria)
- Enriches the output CSV with LLM analysis columns

## Features Demonstrated

### Advanced Jinja2 Templating
- ✅ **Filters**: `upper`, `lower`, `title`, `trim`, `format`
- ✅ **Conditionals**: Multi-level `if/elif/else` based on category, price, rating
- ✅ **Loops**: Iterating through comma-separated tags
- ✅ **Variables**: `set` for derived metrics
- ✅ **Math Operations**: `rating * 20`, `price / rating`
- ✅ **String Formatting**: `"%.2f" | format(price)`

### Pipeline Components
- 📥 **CSV Datasource**: Schema validation with 6 columns
- 🤖 **HTTP OpenAI Client**: Compatible with localhost or cloud LLMs
- 📤 **CSV Sink**: Enriched output with 3 new analysis columns
- 🔌 **Row Plugins**: Score extraction with JSON parsing
- 📊 **Aggregators**: Statistical summary of scores

### Security Architecture
- 🔒 **Bell-LaPadula MLS**: Automatic security level enforcement
- 🛡️ **Plugin Registry**: Auto-discovery and validation
- 🔐 **Audit Logging**: Complete execution trail in `logs/`

## File Structure

```
orchestration_packs/product_analysis_demo/
├── README.md                           # This file
├── settings.yaml                       # Main configuration with advanced templates
├── data/
│   └── products.csv                    # 5 sample products (Electronics, F&B, Sports)
└── product_analysis_baseline/
    └── config.json                     # Experiment configuration
```

## Input Data

**data/products.csv** (5 products):
- P001: Wireless Headphones (Electronics, $89.99, 4.5⭐)
- P002: Organic Coffee Beans (Food & Beverage, $24.99, 4.8⭐)
- P003: Yoga Mat Premium (Sports, $45.00, 4.3⭐)
- P004: Smart Watch Pro (Electronics, $299.99, 4.6⭐)
- P005: Artisan Chocolate Box (Food & Beverage, $19.99, 4.9⭐)

## Running the Demo

### Prerequisites

**Option 1: Local LLM Server (Default)**
```bash
# Requires a local OpenAI-compatible server at http://localhost:5000
# Examples: llama.cpp server, LocalAI, Ollama with OpenAI compatibility
```

**Option 2: OpenAI API**
```bash
# Edit settings.yaml to use Azure OpenAI or OpenAI HTTP client
# See docs/architecture/plugin-catalogue.md for plugin options
```

### Execution

From the repository root:

```bash
python -m elspeth.cli \
  --settings orchestration_packs/product_analysis_demo/settings.yaml \
  --suite-root orchestration_packs/product_analysis_demo \
  --reports-dir outputs/product_analysis_demo \
  --head 0
```

**Expected Runtime**:
- Mock LLM: ~1-2 seconds
- Local LLM: ~30-120 seconds (depending on hardware)
- Cloud LLM: ~10-30 seconds (depending on API latency)

## Output

### CSV Results

**outputs/product_analysis_demo/product_analysis_baseline_analysis_results.csv**

Enriched CSV with **9 columns**:
- `product_id`, `name`, `price`, `category`, `tags`, `rating` (original)
- `llm_content` (main analysis response with JSON)
- `llm_market_analysis` (market positioning assessment)
- `llm_price_evaluation` (pricing recommendation)

### Audit Logs

**logs/run_YYYYMMDDTHHMMSSZ.jsonl**

JSONL audit trail containing:
- Rendered prompts (full Jinja2 output)
- LLM request/response metadata
- Plugin lifecycle events
- Performance metrics

## Example Output

```csv
product_id,name,price,category,tags,rating,llm_content,llm_market_analysis,llm_price_evaluation
P001,Wireless Headphones,89.99,Electronics,"audio,bluetooth,portable",4.5,"```json
{
  ""market_appeal"": 0.75,
  ""pricing_assessment"": ""fair"",
  ""strengths"": [""portable"", ""bluetooth connectivity""],
  ""recommendations"": [""emphasize audio quality"", ""target commuters""],
  ""target_audience"": ""tech-savvy consumers seeking portable audio""
}
```","```json
{
  ""market_score"": 0.75,
  ""positioning"": ""Premium mid-range wireless headphones...""
}
```","```json
{
  ""price_score"": 0.8,
  ""recommendation"": ""keep""
}
```"
```

## Template Features Breakdown

### 1. Category-Based Conditional Formatting

```jinja2
{% if category == "Electronics" %}
🔌 TECH PRODUCT ANALYSIS
{% elif category == "Food & Beverage" %}
🍽️ F&B PRODUCT ANALYSIS
{% elif category == "Sports" %}
🏃 SPORTS PRODUCT ANALYSIS
{% endif %}
```

**Result**: Each product gets category-specific formatting with emojis.

### 2. Price Tier Classification

```jinja2
{% if price > 100 %}
💰 Premium pricing tier (>$100)
{% elif price > 50 %}
💵 Mid-range pricing tier ($50-$100)
{% else %}
💸 Budget-friendly tier (<$50)
{% endif %}
```

**Result**: Automatic price tier classification for context.

### 3. Tag Parsing and Iteration

```jinja2
{% set tag_list = tags.split(',') %}
{% for tag in tag_list %}
  • {{ tag | trim | upper }}
{% endfor %}
```

**Input**: `"audio,bluetooth,portable"`
**Output**:
```
  • AUDIO
  • BLUETOOTH
  • PORTABLE
```

### 4. Derived Metrics Calculation

```jinja2
Quality Score: {{ rating * 20 }}%
{% set price_per_star = price / rating %}
Value Ratio: ${{ "%.2f" | format(price_per_star) }} per rating point
```

**Example** (P001):
```
Quality Score: 90%
Value Ratio: $20.00 per rating point
```

### 5. Multi-Condition Priority Logic

```jinja2
{% if rating >= 4.5 and price < 50 %}
🎯 PRIORITY: High-rated budget product - excellent value proposition
{% elif rating >= 4.5 %}
🎯 PRIORITY: Premium product with strong customer satisfaction
{% elif price < 30 %}
🎯 PRIORITY: Budget option - evaluate quality improvements
{% else %}
🎯 PRIORITY: Standard analysis required
{% endif %}
```

**Result**: Smart prioritization based on rating and price combination.

## Performance Notes

### Hardware Considerations

**Slow Hardware (e.g., "potato PC")**:
- Consider reducing dataset size (edit `data/products.csv`)
- Increase timeout: `timeout: 180` or higher in `settings.yaml`
- Use mock LLM for testing: Change `plugin: http_openai` → `plugin: mock`

**Fast Hardware / Cloud API**:
- Can process full 5-product dataset easily
- Reduce timeout: `timeout: 30` for faster failure detection

### LLM Request Count

- **5 products** × **3 prompts** = **15 LLM requests** per run
- Main prompt (~250 tokens) + 2 criteria (~50 tokens each)
- Total tokens: ~1750 input + ~750 output = **~2500 tokens per run**

## Troubleshooting

### Error: "404 Not Found for url: http://localhost:5000/v1/v1/chat/completions"

**Cause**: Double `/v1` in URL (plugin appends `/v1/chat/completions` to `api_base`)

**Fix**: Change `api_base: "http://localhost:5000/v1"` → `api_base: "http://localhost:5000"`

### Error: "Connection refused"

**Cause**: No LLM server running at localhost:5000

**Solutions**:
1. Start a local LLM server (llama.cpp, LocalAI, Ollama)
2. Use mock LLM: Change `plugin: http_openai` → `plugin: mock`
3. Use cloud API: Configure Azure OpenAI or OpenAI credentials

### Timeout Errors

**Symptoms**: "LLM request exhausted retries" after long wait

**Solutions**:
1. Increase `timeout: 120` → `timeout: 180` or higher
2. Reduce dataset size in `data/products.csv`
3. Use faster LLM backend

## Next Steps

### Customization Ideas

1. **Add More Products**: Expand `data/products.csv` with your own data
2. **New Categories**: Add new conditional branches for different product types
3. **Custom Criteria**: Add more criteria in the `criteria:` section
4. **Different LLMs**: Try Azure OpenAI, Anthropic Claude, or local models
5. **Multiple Sinks**: Add JSON, Markdown, or Excel sinks

### Related Demos

- `config/sample_suite/` - Full test suite with multiple experiments
- `config/sample_suite/baseline/` - Baseline comparison example
- `config/sample_suite/variant_prompt/` - Prompt variation testing

## Documentation

- **Architecture**: `docs/architecture/architecture-overview.md`
- **Plugin Catalog**: `docs/architecture/plugin-catalogue.md`
- **Security Model**: `docs/architecture/decisions/002-security-architecture.md`
- **Templating Guide**: `docs/development/prompt-templating.md` (if exists)

## Credits

This demo was created to validate the complete security architecture refactoring (PR #15):
- Sprint 1: SecureDataFrame trusted container (ADR-002-A)
- Sprint 2: CentralPluginRegistry auto-discovery (ADR-003)
- Sprint 3: Three-layer defense-in-depth (VULN-004)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
