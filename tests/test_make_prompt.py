"""Tests for scripts/make_prompt.py."""

import json
from pathlib import Path

import pytest

from scripts.make_prompt import (
    average_exposure,
    fmt_currency,
    fmt_pay_range,
    generate_prompt_text,
    load_records,
    main,
    pay_band_rows,
    sanitize_cell,
    sort_records,
)


def _make_record(
    title: str,
    *,
    slug: str | None = None,
    ssoc_code: str = "12345",
    category_label: str = "Professionals",
    pay_monthly: int | None = 5000,
    pay_p25: int | None = 4000,
    pay_p75: int | None = 7000,
    exposure: int | None = 6,
    exposure_rationale: str | None = "Mostly digital work.",
) -> dict:
    return {
        "title": title,
        "slug": slug or title.lower().replace(" ", "-"),
        "ssoc_code": ssoc_code,
        "category": category_label.lower().replace(" ", "-"),
        "category_label": category_label,
        "major_group": 2,
        "pay_monthly": pay_monthly,
        "pay_annual": pay_monthly * 12 if pay_monthly is not None else None,
        "pay_p25": pay_p25,
        "pay_p75": pay_p75,
        "exposure": exposure,
        "exposure_rationale": exposure_rationale,
        "url": "",
    }


class TestFormattingHelpers:
    def test_fmt_currency(self):
        assert fmt_currency(6500) == "S$6,500"
        assert fmt_currency(None) == "?"

    def test_fmt_pay_range(self):
        assert fmt_pay_range(4000, 7000) == "S$4,000 – S$7,000"
        assert fmt_pay_range(None, 7000) == "?"

    def test_sanitize_cell(self):
        assert sanitize_cell("hello | world\nnext") == "hello / world next"
        assert sanitize_cell(None) == "?"


class TestLoadRecords:
    def test_load_records_reads_list(self, tmp_path: Path):
        path = tmp_path / "data.json"
        path.write_text(json.dumps([_make_record("Analyst")]), encoding="utf-8")

        records = load_records(path)

        assert len(records) == 1
        assert records[0]["title"] == "Analyst"

    def test_load_records_rejects_non_list(self, tmp_path: Path):
        path = tmp_path / "data.json"
        path.write_text(json.dumps({"oops": True}), encoding="utf-8")

        with pytest.raises(ValueError, match="top-level array"):
            load_records(path)

    def test_load_records_rejects_missing_field(self, tmp_path: Path):
        path = tmp_path / "data.json"
        path.write_text(json.dumps([{"title": "Analyst"}]), encoding="utf-8")

        with pytest.raises(ValueError, match="missing required fields"):
            load_records(path)


class TestAggregations:
    def test_average_exposure_ignores_unscored(self):
        records = [
            _make_record("A", exposure=8),
            _make_record("B", exposure=4),
            _make_record("C", exposure=None),
        ]

        assert average_exposure(records) == 6.0

    def test_pay_band_rows(self):
        records = [
            _make_record("Cleaner", pay_monthly=1800, exposure=1),
            _make_record("Clerk", pay_monthly=3000, exposure=5),
            _make_record("Engineer", pay_monthly=8000, exposure=8),
        ]

        rows = pay_band_rows(records)

        assert rows[0] == ("<S$2K", 1.0, 1)
        assert rows[1] == ("S$2-4K", 5.0, 1)
        assert rows[3] == ("S$6-10K", 8.0, 1)


class TestSorting:
    def test_sort_records_by_exposure_then_pay_then_title(self):
        records = [
            _make_record("Zulu", pay_monthly=4000, exposure=6),
            _make_record("Alpha", pay_monthly=7000, exposure=8),
            _make_record("Beta", pay_monthly=5000, exposure=8),
            _make_record("Gamma", pay_monthly=9000, exposure=None),
        ]

        sorted_records = sort_records(records)

        assert [record["title"] for record in sorted_records] == ["Alpha", "Beta", "Zulu", "Gamma"]


class TestGeneratePromptText:
    def test_generate_prompt_contains_key_sections(self):
        records = [
            _make_record(
                "Software developer",
                ssoc_code="25120",
                category_label="Professionals",
                pay_monthly=8500,
                pay_p25=6500,
                pay_p75=11000,
                exposure=9,
                exposure_rationale="Core work is digital and highly automatable.",
            ),
            _make_record(
                "Hotel cleaner",
                ssoc_code="91122",
                category_label="Cleaners, Labourers and Related Workers",
                pay_monthly=2019,
                pay_p25=1800,
                pay_p75=2274,
                exposure=0,
                exposure_rationale="The role is physical and site-specific.",
            ),
        ]

        text = generate_prompt_text(records)

        assert "# AI Exposure of the Singapore Job Market" in text
        assert "## Aggregate statistics" in text
        assert "### Average exposure by major group" in text
        assert "## All 2 occupations" in text
        assert "### Exposure 9/10 (1 occupations)" in text
        assert "Software developer" in text
        assert "S$8,500" in text
        assert "Cleaners, Labourers and Related Workers" in text

    def test_generate_prompt_includes_unscored_section_when_needed(self):
        records = [
            _make_record("Analyst", exposure=7),
            _make_record("Mystery role", exposure=None, exposure_rationale=None),
        ]

        text = generate_prompt_text(records)

        assert "## Unscored occupations (1)" in text
        assert "Mystery role" in text


class TestMain:
    def test_main_writes_output(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
        input_path = tmp_path / "site-data.json"
        output_path = tmp_path / "prompt.md"
        input_path.write_text(
            json.dumps([
                _make_record("Analyst", exposure=7, pay_monthly=7000),
                _make_record("Cleaner", exposure=1, pay_monthly=1800),
            ]),
            encoding="utf-8",
        )

        monkeypatch.chdir(tmp_path)
        main(["--input", str(input_path), "--output", str(output_path)])
        out = capsys.readouterr().out

        assert output_path.exists()
        text = output_path.read_text(encoding="utf-8")
        assert "AI Exposure of the Singapore Job Market" in text
        assert "Loaded 2 occupations" in out
        assert "Wrote" in out
