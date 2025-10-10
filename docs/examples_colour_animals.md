# Colour → Animal Association Run

This example drives a locally hosted OpenAI-compatible model (running on `http://192.168.1.240:5000`) to suggest an animal for each colour in a 100-row CSV.

## Prerequisites

1. Ensure the service is reachable at `http://192.168.1.240:5000/v1/chat/completions` and accepts the standard OpenAI Chat Completions schema.
2. Install project dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .[dev]
   pip install matplotlib seaborn  # optional for report visuals
   ```

## Dataset

The CSV lives at `config/data/colour_animals.csv` with three columns:

| colour        | tone   | season |
|---------------|--------|--------|
| red           | dark   | autumn |
| blue          | dark   | winter |
| mint green    | light  | spring |
| …             | …      | …      |

The extra `tone` and `season` columns drive multi-dimensional templating.

## Settings profile

`config/settings_colour_animals.yaml` defines:
- `datasource`: local CSV reader pointing at the dataset.
- `llm`: new `http_openai` plugin aimed at the local endpoint.
- `sinks`: CSV sink writing to `outputs/colour_animals/latest_results.csv`.
 - Prompts: the system instructs concise answers, and the user prompt uses conditional logic to tailor guidance while enforcing a strict output format. For example:

  ```jinja2
  {% set tone_descriptor = "bright" if tone == "light" else "deep" if tone == "dark" else "balanced" %}
  {% if season == "winter" %}
  The colour "{{ colour }}" is a {{ tone_descriptor }} winter hue. Name an animal adapted to cold climates...
  {% elif season == "summer" %}
  ...
  {% endif %}
  Respond with **only** the animal name in Title Case, no extra words or punctuation.
  ```

  This demonstrates how multiple dataset dimensions can shape the final prompt.

## Running the job

```bash
source .venv/bin/activate
python -m elspeth.cli \
  --settings config/settings_colour_animals.yaml \
  --profile colour_animals \
  --single-run \
  --output-csv outputs/colour_animals/run_results.csv \
  --head 0
```

- The CLI loads all 100 rows, calls the local model, and writes rows + LLM completions to the chosen CSV.
- The default sink also emits `outputs/colour_animals/latest_results.csv` for convenience.

## Optional reporting

To produce consolidated reports instead (Markdown/JSON/Excel/PNG), first install pandas + openpyxl + matplotlib as above, then run:

```bash
python -m elspeth.cli \
  --settings config/settings_colour_animals.yaml \
  --profile colour_animals \
  --reports-dir outputs/colour_animals/reports \
  --single-run \
  --head 0
```

If the endpoint requires a bearer token, expose it via environment variable and reference it with `api_key_env` in the settings file.
