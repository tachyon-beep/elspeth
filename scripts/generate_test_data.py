"""Generate test CSV data for ELSPETH examples and endurance tests.

Supports two data shapes:
  - flat: Simple rows with id + text fields (for single-query LLM transforms)
  - multi: Case study rows with N case studies x M input fields each
           (for multi-query LLM transforms)

Usage:
    # Flat: 10,000 rows of id + text (for sentiment analysis)
    python -m scripts.generate_test_data flat --rows 10000 --output examples/chaosllm_sentiment/input.csv

    # Multi: 10,000 rows of 2 case studies × 3 fields each (for multi-query assessment)
    python -m scripts.generate_test_data multi --rows 10000 --case-studies 2 --fields-per-cs 3 \
        --output examples/chaosllm_endurance/input.csv

    # Multi: 5,000 rows of 4 case studies × 2 fields each
    python -m scripts.generate_test_data multi --rows 5000 --case-studies 4 --fields-per-cs 2 \
        --output my_custom_test.csv
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    name="generate-test-data",
    help="Generate test CSV data for ELSPETH examples.",
    no_args_is_help=True,
)

# ── Vocabularies ────────────────────────────────────────────────────────

_OCCUPATIONS_M = [
    "office worker", "construction worker", "teacher", "engineer",
    "truck driver", "chef", "musician", "farmer", "accountant",
    "plumber", "electrician", "mechanic", "dentist", "pharmacist",
    "warehouse worker", "security guard", "paramedic", "firefighter",
]

_OCCUPATIONS_F = [
    "nurse", "lawyer", "artist", "retail worker", "scientist",
    "pilot", "athlete", "accountant", "surgeon", "therapist",
    "journalist", "architect", "librarian", "social worker",
    "veterinarian", "professor", "dietitian", "physiotherapist",
]

_SYMPTOMS = [
    "chest pain, shortness of breath, fatigue",
    "persistent headaches, visual disturbances, nausea",
    "joint pain, morning stiffness, swelling in extremities",
    "abdominal pain, nausea, unintentional weight loss",
    "chronic cough, wheezing, night sweats",
    "dizziness, palpitations, episodes of syncope",
    "lower back pain, leg numbness, progressive weakness",
    "skin rash, itching, joint inflammation",
    "memory difficulties, confusion, personality changes",
    "fever, chills, productive cough with hemoptysis",
    "blurred vision, eye pain, photophobia",
    "insomnia, anxiety, tremor, weight loss",
    "urinary frequency, flank pain, hematuria",
    "dysphagia, heartburn, regurgitation",
    "bilateral leg edema, dyspnea on exertion, orthopnea",
]

_HISTORY_TEMPLATES = [
    "Hypertension for {} years, family history of heart disease",
    "Type 2 diabetes, previous surgery {} years ago",
    "Smoker for {} years, occupational chemical exposures",
    "Autoimmune condition diagnosed {} years ago, on immunosuppressants",
    "No significant past medical history, active lifestyle",
    "Previous hospitalization {} years ago, full recovery",
    "Chronic condition managed with medication for {} years",
    "Family history of cancer, regular screening for {} years",
    "Sports injury {} years ago, conservative treatment with PT",
    "Mental health history, stable on medication for {} years",
    "Childhood asthma, recurrent respiratory infections for {} years",
    "GERD diagnosed {} years ago, lifestyle modifications",
]

_SENTIMENTS_POSITIVE = [
    "I absolutely love this product! It exceeded all my expectations.",
    "Amazing experience. Highly recommend to everyone.",
    "Great value for the price. Happy customer.",
    "Pleasantly surprised by the quality. Delivery was fast.",
    "Exceptional! Exactly what I was looking for. Five stars.",
    "Outstanding service and product quality. Will buy again.",
    "The best purchase I've made this year. Very impressed.",
    "Wonderful experience from start to finish. Top notch.",
]

_SENTIMENTS_NEGATIVE = [
    "Terrible service. Staff were rude and unhelpful.",
    "Completely disappointed. Product broke after two days.",
    "The worst customer experience I have ever encountered.",
    "Do not buy. Total waste of money and time.",
    "Awful quality. Nothing like the pictures showed.",
    "Waited weeks for delivery and it arrived damaged.",
    "Customer support was useless. No resolution offered.",
    "Regret this purchase. Poor build quality and design.",
]

_SENTIMENTS_NEUTRAL = [
    "It was okay. Nothing special but nothing bad either.",
    "Mediocre at best. Expected more based on reviews.",
    "Average product. Does what it says, nothing more.",
    "Mixed feelings. Some features are good, others lacking.",
    "Not bad but not great. Would consider alternatives next time.",
    "Decent for the price point. Meets basic expectations.",
    "Standard quality. No complaints but no surprises either.",
    "Fair product. Serviceable but room for improvement.",
]


# ── Flat data generation ────────────────────────────────────────────────


def _generate_flat_row(rng: random.Random, row_id: int) -> list[str]:
    """Generate a single flat row: [id, text]."""
    sentiment_pool = rng.choice([_SENTIMENTS_POSITIVE, _SENTIMENTS_NEGATIVE, _SENTIMENTS_NEUTRAL])
    text = rng.choice(sentiment_pool)
    return [str(row_id), text]


# ── Multi-dimensional data generation ───────────────────────────────────


def _generate_background(rng: random.Random) -> str:
    """Generate a random patient background string."""
    age = rng.randint(18, 80)
    if rng.random() < 0.5:
        occupation = rng.choice(_OCCUPATIONS_M)
        return f"{age}yo male, {occupation}"
    else:
        occupation = rng.choice(_OCCUPATIONS_F)
        return f"{age}yo female, {occupation}"


def _generate_symptoms(rng: random.Random) -> str:
    """Generate random symptoms."""
    return rng.choice(_SYMPTOMS)


def _generate_history(rng: random.Random) -> str:
    """Generate random medical history."""
    template = rng.choice(_HISTORY_TEMPLATES)
    years = rng.randint(1, 20)
    return template.format(years)


_FIELD_GENERATORS = {
    0: _generate_background,  # field 1: background
    1: _generate_symptoms,     # field 2: symptoms
    2: _generate_history,      # field 3: history
}


def _generate_field(rng: random.Random, field_index: int) -> str:
    """Generate a field value based on its position within a case study."""
    generator = _FIELD_GENERATORS.get(field_index % 3)
    if generator is not None:
        return generator(rng)
    # For fields beyond 3, generate mixed content
    return rng.choice([
        _generate_background(rng),
        _generate_symptoms(rng),
        _generate_history(rng),
    ])


def _generate_multi_row(
    rng: random.Random,
    row_id: int,
    num_case_studies: int,
    fields_per_cs: int,
) -> list[str]:
    """Generate a single multi-dimensional row."""
    row: list[str] = [f"user-{row_id:05d}"]
    for cs_idx in range(1, num_case_studies + 1):
        for field_idx in range(fields_per_cs):
            row.append(_generate_field(rng, field_idx))
    return row


# ── CLI commands ────────────────────────────────────────────────────────


@app.command()
def flat(
    rows: Annotated[int, typer.Option("--rows", "-n", help="Number of rows to generate", min=1)] = 10000,
    output: Annotated[Path, typer.Option("--output", "-o", help="Output CSV file path")] = Path("test_data_flat.csv"),
    seed: Annotated[int, typer.Option("--seed", "-s", help="Random seed for reproducibility")] = 42,
) -> None:
    """Generate flat test data (id, text) for single-query LLM transforms.

    Each row has an integer ID and a text field containing a sentiment statement.
    """
    rng = random.Random(seed)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text"])
        for i in range(1, rows + 1):
            writer.writerow(_generate_flat_row(rng, i))

    typer.echo(f"Generated {rows} flat rows -> {output}")


@app.command()
def multi(
    rows: Annotated[int, typer.Option("--rows", "-n", help="Number of rows to generate", min=1)] = 10000,
    case_studies: Annotated[int, typer.Option("--case-studies", "-c", help="Number of case studies per row", min=1, max=10)] = 2,
    fields_per_cs: Annotated[int, typer.Option("--fields-per-cs", "-f", help="Fields per case study", min=1, max=10)] = 3,
    output: Annotated[Path, typer.Option("--output", "-o", help="Output CSV file path")] = Path("test_data_multi.csv"),
    seed: Annotated[int, typer.Option("--seed", "-s", help="Random seed for reproducibility")] = 42,
) -> None:
    """Generate multi-dimensional test data for multi-query LLM transforms.

    Each row has a user_id followed by N case studies, each with M fields.
    Field naming: cs1_field1, cs1_field2, ..., cs2_field1, cs2_field2, ...

    The first 3 fields per case study are: background, symptoms, history.
    Additional fields cycle through the same generators.
    """
    rng = random.Random(seed)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Build header
    field_names = ["background", "symptoms", "history"]
    header = ["user_id"]
    for cs_idx in range(1, case_studies + 1):
        for field_idx in range(fields_per_cs):
            if field_idx < len(field_names):
                name = field_names[field_idx]
            else:
                name = f"field{field_idx + 1}"
            header.append(f"cs{cs_idx}_{name}")

    with output.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for i in range(1, rows + 1):
            writer.writerow(_generate_multi_row(rng, i, case_studies, fields_per_cs))

    total_calls = rows * case_studies * 5  # assuming 5 criteria
    typer.echo(f"Generated {rows} multi rows ({case_studies} case studies × {fields_per_cs} fields each) -> {output}")
    typer.echo(f"  With 5 criteria, this produces {total_calls:,} LLM calls")


def main() -> None:
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
