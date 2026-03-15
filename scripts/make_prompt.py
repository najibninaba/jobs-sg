"""Generate prompt.md for LLM analysis of the Singapore AI exposure dataset.

The prompt packages aggregate statistics plus the full scored occupation table into
one markdown document that can be pasted into an LLM for grounded analysis.

Usage:
    uv run python -m scripts.make_prompt
    uv run python -m scripts.make_prompt --input site/data.json --output prompt.md
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

INPUT_PATH = Path("site/data.json")
OUTPUT_PATH = Path("prompt.md")

TIERS = [
    ("Minimal (0-1)", 0, 1),
    ("Low (2-3)", 2, 3),
    ("Moderate (4-5)", 4, 5),
    ("High (6-7)", 6, 7),
    ("Very high (8-10)", 8, 10),
]

PAY_BANDS = [
    ("<S$2K", 0, 2000),
    ("S$2-4K", 2000, 4000),
    ("S$4-6K", 4000, 6000),
    ("S$6-10K", 6000, 10000),
    ("S$10K+", 10000, float("inf")),
]


def fmt_currency(amount: int | float | None) -> str:
    """Format a monthly or annual SGD amount."""
    if amount is None:
        return "?"
    return f"S${int(amount):,}"


def fmt_pay_range(p25: int | None, p75: int | None) -> str:
    """Format a monthly pay percentile range."""
    if p25 is None or p75 is None:
        return "?"
    return f"{fmt_currency(p25)} – {fmt_currency(p75)}"


def sanitize_cell(text: object) -> str:
    """Sanitize markdown table cell content."""
    if text is None:
        return "?"
    return str(text).replace("|", "/").replace("\n", " ").strip() or "?"


def load_records(path: Path = INPUT_PATH) -> list[dict]:
    """Load merged site records from JSON."""
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    with open(path, encoding="utf-8") as f:
        records = json.load(f)

    if not isinstance(records, list):
        raise ValueError("Input JSON must be a top-level array")

    required = {"title", "slug", "category_label", "pay_monthly", "exposure"}
    for i, record in enumerate(records):
        missing = [field for field in required if field not in record]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Record {i}: missing required fields: {joined}")

    return records


def sort_records(records: list[dict]) -> list[dict]:
    """Sort by exposure desc, then monthly pay desc, then title asc."""

    def key(record: dict) -> tuple[int, int, str]:
        exposure = record.get("exposure")
        pay = record.get("pay_monthly")
        return (
            -(exposure if isinstance(exposure, int) else -1),
            -(pay if isinstance(pay, int) else -1),
            sanitize_cell(record.get("title", "")).lower(),
        )

    return sorted(records, key=key)


def average_exposure(records: list[dict]) -> float | None:
    """Compute equal-weighted average exposure over scored records."""
    exposures = [r["exposure"] for r in records if isinstance(r.get("exposure"), int)]
    if not exposures:
        return None
    return sum(exposures) / len(exposures)


def average_pay(records: list[dict]) -> float | None:
    """Compute equal-weighted average monthly pay over records with pay."""
    pays = [r["pay_monthly"] for r in records if isinstance(r.get("pay_monthly"), int)]
    if not pays:
        return None
    return sum(pays) / len(pays)


def median_pay(records: list[dict]) -> int | None:
    """Compute median monthly pay over records with pay."""
    pays = [r["pay_monthly"] for r in records if isinstance(r.get("pay_monthly"), int)]
    if not pays:
        return None
    return int(statistics.median(pays))


def tier_rows(records: list[dict]) -> list[tuple[str, int, float, float | None]]:
    """Compute tier breakdown rows."""
    total = len(records)
    rows: list[tuple[str, int, float, float | None]] = []
    for label, lo, hi in TIERS:
        group = [
            r
            for r in records
            if isinstance(r.get("exposure"), int) and lo <= r["exposure"] <= hi
        ]
        pct = (len(group) / total * 100) if total else 0.0
        rows.append((label, len(group), pct, average_pay(group)))
    return rows


def pay_band_rows(records: list[dict]) -> list[tuple[str, float | None, int]]:
    """Compute equal-weighted average exposure by monthly pay band."""
    rows: list[tuple[str, float | None, int]] = []
    for label, lo, hi in PAY_BANDS:
        group = [
            r
            for r in records
            if isinstance(r.get("pay_monthly"), int)
            and lo <= r["pay_monthly"] < hi
            and isinstance(r.get("exposure"), int)
        ]
        rows.append((label, average_exposure(group), len(group)))
    return rows


def major_group_rows(records: list[dict]) -> list[tuple[str, float | None, int, float | None]]:
    """Compute equal-weighted exposure stats by major group label."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[sanitize_cell(record.get("category_label", "Unknown"))].append(record)

    rows = []
    for label, group in groups.items():
        rows.append((label, average_exposure(group), len(group), average_pay(group)))

    rows.sort(key=lambda row: ((-(row[1]) if row[1] is not None else 1), row[0].lower()))
    return rows


def generate_prompt_text(records: list[dict]) -> str:
    """Generate the full prompt markdown text."""
    sorted_records = sort_records(records)
    scored = [r for r in sorted_records if isinstance(r.get("exposure"), int)]
    high_exposure = [r for r in scored if r["exposure"] >= 7]

    avg_exposure = average_exposure(scored)
    avg_monthly_pay = average_pay(sorted_records)
    median_monthly_pay = median_pay(sorted_records)

    lines: list[str] = []
    lines.append("# AI Exposure of the Singapore Job Market")
    lines.append("")
    lines.append(
        "This document contains structured data on Singapore occupations from the "
        "Ministry of Manpower wage survey, enriched with SSOC occupation metadata "
        "and scored for AI exposure on a 0-10 scale. Use it for grounded analysis "
        "and discussion of how AI may reshape the Singapore labour market."
    )
    lines.append("")
    lines.append("GitHub: https://github.com/najibninaba/jobs-sg")
    lines.append("")

    lines.append("## Scoring methodology")
    lines.append("")
    lines.append(
        "Each occupation is scored on a single **AI Exposure** axis from 0 to 10, "
        "measuring how much AI is likely to reshape the occupation. The score "
        "considers both direct automation (AI doing the work) and indirect effects "
        "(AI making workers much more productive, reducing labour demand)."
    )
    lines.append("")
    lines.append(
        "A key heuristic is whether the occupation's work product is fundamentally "
        "digital. If the work can largely be done from a computer — writing, coding, "
        "analysing, designing, documenting, communicating — exposure is inherently "
        "high. Occupations requiring physical presence, manual skill, or real-time "
        "human interaction in the physical world have more natural protection."
    )
    lines.append("")
    lines.append("Calibration anchors:")
    lines.append("- 0-1 Minimal: cleaners, labourers, refuse collectors")
    lines.append("- 2-3 Low: hawker stall assistants, hairdressers, bus drivers")
    lines.append("- 4-5 Moderate: staff nurses, preschool teachers, property agents")
    lines.append("- 6-7 High: accountants, HR executives, sales managers, journalists")
    lines.append(
        "- 8-9 Very high: software developers, graphic designers, translators, data analysts"
    )
    lines.append("- 10 Maximum: data entry clerks, routine telemarketing-style work")
    lines.append("")

    lines.append("## Aggregate statistics")
    lines.append("")
    lines.append(f"- Total occupations: {len(sorted_records)}")
    lines.append(f"- Scored occupations: {len(scored)}")
    if avg_exposure is not None:
        lines.append(f"- Occupation-weighted average AI exposure: {avg_exposure:.1f}/10")
    if avg_monthly_pay is not None:
        lines.append(f"- Average monthly pay: {fmt_currency(round(avg_monthly_pay))}")
    if median_monthly_pay is not None:
        lines.append(f"- Median monthly pay: {fmt_currency(median_monthly_pay)}")
    lines.append(f"- High-exposure occupations (7+): {len(high_exposure)}")
    lines.append("")

    lines.append("### Breakdown by exposure tier")
    lines.append("")
    lines.append("| Tier | Occupations | % of occupations | Avg monthly pay |")
    lines.append("|------|-------------|------------------|-----------------|")
    for label, count, pct, avg_pay in tier_rows(sorted_records):
        avg_pay_text = fmt_currency(round(avg_pay)) if avg_pay is not None else "?"
        lines.append(f"| {label} | {count} | {pct:.1f}% | {avg_pay_text} |")
    lines.append("")

    lines.append("### Average exposure by pay band")
    lines.append("")
    lines.append("| Pay band | Avg exposure | Occupations |")
    lines.append("|----------|--------------|-------------|")
    for label, avg, count in pay_band_rows(sorted_records):
        avg_text = f"{avg:.1f}" if avg is not None else "?"
        lines.append(f"| {label} | {avg_text} | {count} |")
    lines.append("")

    lines.append("### Average exposure by major group")
    lines.append("")
    lines.append("| Major group | Avg exposure | Occupations | Avg monthly pay |")
    lines.append("|-------------|--------------|-------------|-----------------|")
    for label, avg, count, avg_pay in major_group_rows(sorted_records):
        avg_text = f"{avg:.1f}" if avg is not None else "?"
        avg_pay_text = fmt_currency(round(avg_pay)) if avg_pay is not None else "?"
        lines.append(f"| {label} | {avg_text} | {count} | {avg_pay_text} |")
    lines.append("")

    lines.append(f"## All {len(sorted_records)} occupations")
    lines.append("")
    lines.append("Sorted by AI exposure (descending), then monthly pay (descending).")
    lines.append("")

    for score in range(10, -1, -1):
        group = [r for r in sorted_records if r.get("exposure") == score]
        if not group:
            continue
        lines.append(f"### Exposure {score}/10 ({len(group)} occupations)")
        lines.append("")
        lines.append(
            "| # | Occupation | SSOC | Monthly pay | "
            "Pay range (p25-p75) | Major group | Rationale |"
        )
        lines.append(
            "|---|------------|------|-------------|---------------------|-------------|-----------|"
        )
        for i, record in enumerate(group, 1):
            rationale = sanitize_cell(record.get("exposure_rationale"))
            lines.append(
                f"| {i} | {sanitize_cell(record.get('title'))} | "
                f"{sanitize_cell(record.get('ssoc_code'))} | "
                f"{fmt_currency(record.get('pay_monthly'))} | "
                f"{fmt_pay_range(record.get('pay_p25'), record.get('pay_p75'))} | "
                f"{sanitize_cell(record.get('category_label'))} | {rationale} |"
            )
        lines.append("")

    unscored = [r for r in sorted_records if not isinstance(r.get("exposure"), int)]
    if unscored:
        lines.append(f"## Unscored occupations ({len(unscored)})")
        lines.append("")
        lines.append("| Occupation | SSOC | Monthly pay | Major group |")
        lines.append("|------------|------|-------------|-------------|")
        for record in unscored:
            lines.append(
                f"| {sanitize_cell(record.get('title'))} | "
                f"{sanitize_cell(record.get('ssoc_code'))} | "
                f"{fmt_currency(record.get('pay_monthly'))} | "
                f"{sanitize_cell(record.get('category_label'))} |"
            )
        lines.append("")

    return "\n".join(lines)


def write_prompt(text: str, output: Path = OUTPUT_PATH) -> None:
    """Write the generated prompt to disk."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    """Load site records, generate prompt.md, and write it to disk."""
    parser = argparse.ArgumentParser(
        description="Generate prompt.md from site/data.json"
    )
    parser.add_argument(
        "--input", type=Path, default=INPUT_PATH, help="Path to site/data.json"
    )
    parser.add_argument(
        "--output", type=Path, default=OUTPUT_PATH, help="Output path for prompt.md"
    )
    args = parser.parse_args(argv)

    records = load_records(args.input)
    text = generate_prompt_text(records)
    write_prompt(text, args.output)

    print(f"Loaded {len(records)} occupations from {args.input}")
    print(f"Wrote {args.output} ({len(text):,} chars)")


if __name__ == "__main__":
    main()
