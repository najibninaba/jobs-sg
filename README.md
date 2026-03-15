# AI Exposure of the Singapore Job Market

[![Deploy to GitHub Pages](https://github.com/najibninaba/jobs-sg/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/najibninaba/jobs-sg/actions/workflows/deploy-pages.yml)
[![GitHub Pages](https://img.shields.io/website?url=https%3A%2F%2Fnajibninaba.github.io%2Fjobs-sg%2F&up_message=live&down_message=not%20live&label=github%20pages)](https://najibninaba.github.io/jobs-sg/)
[![Upstream: karpathy/jobs](https://img.shields.io/badge/upstream-karpathy%2Fjobs-blue)](https://github.com/karpathy/jobs)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)

A Singapore adaptation of Andrej Karpathy's [`karpathy/jobs`](https://github.com/karpathy/jobs) project: 562 occupations from the Ministry of Manpower (MOM) wage survey, enriched with SSOC occupation metadata and scored on a 0-10 AI exposure scale.

**Live demo:** <https://najibninaba.github.io/jobs-sg/>

This repo reworks the original US-focused project for Singapore data while preserving the core idea of an interactive AI-exposure job-market visualization.

## What this repo contains

- `site/index.html` — interactive visualization
- `site/data.json` — compact dataset consumed by the frontend
- `scripts/parse_wages.py` — parses MOM wage tables into `sg_occupations.json`
- `scripts/build_descriptions.py` — builds occupation markdown from SSOC definitions
- `scripts/score.py` — scores occupations for AI exposure using Claude CLI
- `scripts/build_site_data.py` — merges occupations + scores into `site/data.json`
- `scripts/make_prompt.py` — generates `prompt.md` for LLM analysis
- `tests/` — unit tests for the full data pipeline
- `prompt.md` — generated long-form markdown package of the scored dataset

## Dataset

The project combines:

1. **MOM wage survey data** for monthly median pay and percentile bands
2. **SSOC occupation metadata** for titles, codes, groupings, and definitions
3. **LLM scoring** for AI exposure and rationale text

### Source links

- **MOM Occupational Wage Survey 2024**: <https://stats.mom.gov.sg/Pages/Occupational-Wages-Tables2024.aspx>
  - Used for the occupation backbone and wage fields
  - Key downloaded files: `wages_table4_2024.xlsx`, `occ_ind_list_2024.xlsx`
- **SingStat SSOC standards page**: <https://www.singstat.gov.sg/standards/standards-and-classifications/ssoc>
  - Canonical source for Singapore Standard Occupational Classification materials
- **SSOC 2024 report**: <https://www.singstat.gov.sg/-/media/files/standards_and_classifications/occupational_classification/ssoc2024report.ashx>
  - Used as the reference entry point for occupation definitions and classification structure
- **Downloaded SSOC workbooks used by the pipeline**:
  - `ssoc2020_detailed_definitions.xlsx`
  - `ssoc2024_detailed_definitions.xlsx`
  - `ssoc2024_classification_structure.xlsx`
  - `ssoc_correspondence_2020_2024.xlsx`

Each occupation record in `site/data.json` includes:

- title and slug
- SSOC code
- major group / category label
- monthly median pay
- 25th and 75th percentile pay
- annualised pay estimate
- AI exposure score (0-10)
- short rationale

## Visualization

The frontend is adapted from the original `karpathy/jobs` treemap and extends it for the Singapore dataset.

The frontend supports:

- **Treemap view** grouped by SSOC major group
- **Tile size toggle** between equal-sized and pay-weighted rectangles
- **Exposure vs Pay view** with occupations bucketed by exposure and sorted by pay
- **Tier highlighting** from the sidebar breakdown
- **Hover tooltip** with pay, SSOC code, major group, and rationale
- **Click-through detail panel** for a larger occupation summary

## AI exposure scoring rubric

Scores measure how much AI is likely to reshape an occupation, including both:

- **direct automation** — AI doing tasks currently done by people
- **indirect productivity effects** — AI making each worker more productive, reducing labour demand

A strong heuristic is whether the work product is fundamentally digital. Occupations done mainly on a computer tend to score higher; occupations that require physical presence, manual work, or real-time in-person interaction tend to score lower.

## Setup

```bash
uv sync --extra dev
```

### Scoring prerequisite

`scripts/score.py` calls the `claude` CLI, so you need a working Claude Code / Claude CLI installation in your shell path before running the scoring step.

## Usage

A `Makefile` is included for the common workflow:

```bash
make help
make check
make build
make serve
```

### 1. Run tests

```bash
make check
# or:
uv run pytest
uvx ruff check .
```

### 2. Rebuild site data

```bash
make site-data
# or:
uv run python -m scripts.build_site_data
```

### 3. Regenerate the LLM prompt

```bash
make prompt
# or:
uv run python -m scripts.make_prompt
```

### 4. Preview the site locally

```bash
make serve
# or:
cd site
uv run python -m http.server 8888
```

Then open <http://localhost:8888>.

## Data pipeline

```text
MOM wage workbook
        +
SSOC definition workbooks
        ↓
parse_wages.py
        ↓
sg_occupations.json / sg_occupations.csv
        ↓
build_descriptions.py
        ↓
pages/*.md
        ↓
score.py
        ↓
sg_scores.json
        ↓
build_site_data.py
        ↓
site/data.json
        ↓
make_prompt.py
        ↓
prompt.md
```

## prompt.md

`prompt.md` is a generated markdown file that packages:

- aggregate statistics
- exposure-tier breakdowns
- pay-band analysis
- major-group analysis
- all scored occupations sorted by exposure

It is designed to be pasted directly into an LLM for grounded discussion without needing to run the codebase.

## Deployment

The site is a plain static bundle in `site/`, so it can be hosted on GitHub Pages, Vercel, Netlify, or any static host. This repo includes `.github/workflows/deploy-pages.yml`, which deploys `site/` to GitHub Pages on pushes to `main`.

Current deployment: <https://najibninaba.github.io/jobs-sg/>

## Attribution

This project is explicitly derived from Andrej Karpathy's [`karpathy/jobs`](https://github.com/karpathy/jobs):

- the overall framing of an AI-exposure job-market map comes from the upstream project
- the frontend started as an adaptation of the upstream treemap visualization
- the Singapore version replaces the US BLS pipeline with MOM + SSOC data and adds SG-specific views, pay analysis, and prompt generation

## Notes

- Raw source spreadsheets under `data-sources/` are intentionally excluded from the public repo.
- Generated intermediate files like `sg_occupations.json`, `sg_scores.json`, and `pages/` are gitignored.
- The committed product artifacts are the interactive site and generated `prompt.md`.
