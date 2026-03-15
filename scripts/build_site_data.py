"""Build site data JSON by merging occupations with AI exposure scores.

Merges sg_occupations.json (wage data) with sg_scores.json (AI exposure scores)
into a compact site/data.json consumed by the frontend treemap visualization.

Usage:
    uv run python -m scripts.build_site_data
    uv run python -m scripts.build_site_data --occupations custom.json --scores custom_scores.json
"""

import argparse
import json
import sys
from pathlib import Path

from scripts.build_descriptions import load_occupations
from scripts.score import load_cached_scores

# ── Constants ────────────────────────────────────────────────────────────────

OCCUPATIONS_PATH = Path("sg_occupations.json")
SCORES_PATH = Path("sg_scores.json")
OUTPUT_PATH = Path("site/data.json")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _validated_exposure(raw: object) -> int | None:
    """Validate and normalise an exposure value.

    Accepts int in 0..10. Degrades to None for anything else.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        try:
            raw = float(raw)
        except ValueError:
            return None
    if isinstance(raw, float):
        if raw != int(raw):
            return None
        raw = int(raw)
    if isinstance(raw, int) and 0 <= raw <= 10:
        return raw
    return None


def _validated_rationale(raw: object) -> str | None:
    """Validate a rationale string. Degrades to None if empty or non-string."""
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped if stripped else None


# ── Merge ────────────────────────────────────────────────────────────────────


def build_site_records(
    occupations: list[dict],
    scores_by_slug: dict[str, dict],
) -> list[dict]:
    """Merge occupation wage data with AI exposure scores.

    Each occupation produces one record in the output. Missing or malformed
    scores degrade gracefully to None fields (don't fail). When exposure
    normalises to None, exposure_rationale is also set to None.

    Assumes each occupation dict includes the full schema from parse_wages.py:
    category, category_label, major_group, pay_monthly, pay_annual, pay_p25,
    pay_p75, and url — beyond what load_occupations() validates (title, slug,
    ssoc_code).

    Args:
        occupations: List of occupation dicts from sg_occupations.json.
        scores_by_slug: Dict keyed by slug from sg_scores.json.

    Returns:
        List of merged records ready for site/data.json.
    """
    merged: list[dict] = []

    for occ in occupations:
        slug = occ["slug"]
        score = scores_by_slug.get(slug, {})

        exposure = _validated_exposure(score.get("exposure"))
        exposure_rationale = (
            _validated_rationale(score.get("rationale")) if exposure is not None else None
        )

        merged.append(
            {
                "title": occ["title"],
                "slug": slug,
                "ssoc_code": occ["ssoc_code"],
                "category": occ["category"],
                "category_label": occ["category_label"],
                "major_group": occ["major_group"],
                "pay_monthly": occ.get("pay_monthly"),
                "pay_annual": occ.get("pay_annual"),
                "pay_p25": occ.get("pay_p25"),
                "pay_p75": occ.get("pay_p75"),
                "exposure": exposure,
                "exposure_rationale": exposure_rationale,
                "url": occ.get("url", ""),
            }
        )

    return merged


def write_site_data(records: list[dict], output: Path = OUTPUT_PATH) -> None:
    """Write merged records to site/data.json."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


# ── Main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    """Merge occupations and scores into site data."""
    parser = argparse.ArgumentParser(description="Build site data JSON")
    parser.add_argument(
        "--occupations",
        type=Path,
        default=OCCUPATIONS_PATH,
        help="Path to sg_occupations.json",
    )
    parser.add_argument(
        "--scores",
        type=Path,
        default=SCORES_PATH,
        help="Path to sg_scores.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Output path for site data JSON",
    )
    args = parser.parse_args(argv)

    occupations = load_occupations(args.occupations)
    print(f"Loaded {len(occupations)} occupations")

    if not args.scores.exists():
        print(
            f"WARNING: Scores file not found: {args.scores} — all occupations will be unscored",
            file=sys.stderr,
        )
    scores = load_cached_scores(args.scores)
    print(f"Loaded {len(scores)} scores")

    records = build_site_records(occupations, scores)

    scored_count = sum(1 for r in records if r["exposure"] is not None)
    unscored_count = len(records) - scored_count

    # Detect orphan scores (slugs in scores but not in occupations)
    occ_slugs = {occ["slug"] for occ in occupations}
    orphan_count = sum(1 for slug in scores if slug not in occ_slugs)

    write_site_data(records, args.output)
    print(f"\nWrote {len(records)} occupations to {args.output}")
    print(f"  Scored: {scored_count}")
    if unscored_count:
        print(f"  Unscored (exposure=null): {unscored_count}")
    if orphan_count:
        print(f"  Orphan scores ignored: {orphan_count}")

    # Summary stats for scored occupations
    scored = [r for r in records if r["exposure"] is not None]
    if scored:
        avg = sum(r["exposure"] for r in scored) / len(scored)
        print(f"  Average exposure: {avg:.1f}")


if __name__ == "__main__":
    main()
