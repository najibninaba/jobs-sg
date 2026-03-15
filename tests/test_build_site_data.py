"""Tests for scripts/build_site_data.py."""

import json
from pathlib import Path

import pytest

from scripts.build_site_data import (
    _validated_exposure,
    _validated_rationale,
    build_site_records,
    main,
    write_site_data,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_occupation(
    index: int = 0,
    *,
    slug: str | None = None,
    title: str | None = None,
    ssoc_code: str | None = None,
    category: str = "professionals",
    category_label: str = "Professionals",
    major_group: int = 2,
    pay_monthly: int = 5000,
    pay_annual: int = 60000,
    pay_p25: int = 4000,
    pay_p75: int = 7000,
) -> dict:
    """Create a synthetic occupation dict."""
    return {
        "title": title or f"Occupation {index}",
        "slug": slug or f"occupation-{index}",
        "ssoc_code": ssoc_code or f"{index + 10001:05d}",
        "category": category,
        "category_label": category_label,
        "major_group": major_group,
        "pay_monthly": pay_monthly,
        "pay_annual": pay_annual,
        "pay_p25": pay_p25,
        "pay_p75": pay_p75,
        "url": "",
    }


def _make_score(
    slug: str,
    exposure: int = 7,
    rationale: str = "Mostly digital work.",
) -> dict:
    """Create a synthetic score entry."""
    return {
        "slug": slug,
        "title": f"Title for {slug}",
        "exposure": exposure,
        "rationale": rationale,
    }


def _write_test_env(
    tmp_path: Path,
    *,
    n_occs: int = 3,
    score_slugs: list[str] | None = None,
    exposures: list[int] | None = None,
) -> tuple[Path, Path]:
    """Set up minimal occupation + scores files in tmp_path.

    Returns (occupations_path, scores_path).
    """
    occs = [_make_occupation(i) for i in range(n_occs)]
    occ_path = tmp_path / "sg_occupations.json"
    occ_path.write_text(json.dumps(occs))

    # Build scores for specified slugs (default: all)
    if score_slugs is None:
        score_slugs = [o["slug"] for o in occs]
    if exposures is None:
        exposures = [5 + i for i in range(len(score_slugs))]

    scores = []
    for slug, exp in zip(score_slugs, exposures, strict=True):
        scores.append(_make_score(slug, exposure=exp))

    scores_path = tmp_path / "sg_scores.json"
    scores_path.write_text(json.dumps(scores))

    return occ_path, scores_path


# ── _validated_exposure / _validated_rationale ─────────────────────────


class TestValidatedExposure:
    """Tests for _validated_exposure."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, 0),
            (5, 5),
            (10, 10),
            ("7", 7),
            (7.0, 7),
        ],
    )
    def test_valid_values(self, value, expected):
        assert _validated_exposure(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            None,
            -1,
            11,
            3.5,
            "abc",
            "",
            [],
            {},
            True,
        ],
    )
    def test_invalid_values_degrade_to_none(self, value):
        assert _validated_exposure(value) is None


class TestValidatedRationale:
    """Tests for _validated_rationale."""

    def test_valid_string(self):
        assert _validated_rationale("Some reason.") == "Some reason."

    def test_strips_whitespace(self):
        assert _validated_rationale("  padded  ") == "padded"

    @pytest.mark.parametrize("value", [None, "", "   ", 42, [], {}])
    def test_invalid_degrades_to_none(self, value):
        assert _validated_rationale(value) is None


# ── build_site_records ─────────────────────────────────────────────────


class TestBuildSiteRecords:
    """Tests for build_site_records."""

    def test_basic_merge(self):
        """All occupations have scores."""
        occs = [_make_occupation(0), _make_occupation(1)]
        scores = {
            "occupation-0": _make_score("occupation-0", exposure=3, rationale="Low risk."),
            "occupation-1": _make_score("occupation-1", exposure=9, rationale="Very digital."),
        }

        result = build_site_records(occs, scores)

        assert len(result) == 2
        assert result[0]["exposure"] == 3
        assert result[0]["exposure_rationale"] == "Low risk."
        assert result[1]["exposure"] == 9
        assert result[1]["exposure_rationale"] == "Very digital."

    def test_output_schema_fields(self):
        """Every record has all expected fields."""
        occs = [_make_occupation(0)]
        scores = {"occupation-0": _make_score("occupation-0")}

        result = build_site_records(occs, scores)
        record = result[0]

        expected_keys = {
            "title",
            "slug",
            "ssoc_code",
            "category",
            "category_label",
            "major_group",
            "pay_monthly",
            "pay_annual",
            "pay_p25",
            "pay_p75",
            "exposure",
            "exposure_rationale",
            "url",
        }
        assert set(record.keys()) == expected_keys

    def test_missing_score_degrades_to_none(self):
        """Occupation without a score gets exposure=None, rationale=None."""
        occs = [_make_occupation(0)]
        scores = {}  # no scores at all

        result = build_site_records(occs, scores)

        assert result[0]["exposure"] is None
        assert result[0]["exposure_rationale"] is None

    def test_partial_scores(self):
        """Mix of scored and unscored occupations."""
        occs = [_make_occupation(0), _make_occupation(1), _make_occupation(2)]
        scores = {
            "occupation-0": _make_score("occupation-0", exposure=6),
            # occupation-1 is unscored
            "occupation-2": _make_score("occupation-2", exposure=2),
        }

        result = build_site_records(occs, scores)

        assert result[0]["exposure"] == 6
        assert result[1]["exposure"] is None
        assert result[2]["exposure"] == 2

    def test_preserves_occupation_order(self):
        """Output order matches input occupation order."""
        occs = [
            _make_occupation(0, slug="zulu"),
            _make_occupation(1, slug="alpha"),
            _make_occupation(2, slug="mike"),
        ]
        scores = {s: _make_score(s) for s in ["zulu", "alpha", "mike"]}

        result = build_site_records(occs, scores)

        assert [r["slug"] for r in result] == ["zulu", "alpha", "mike"]

    def test_wage_fields_mapped(self):
        """Wage fields are correctly copied from occupation data."""
        occ = _make_occupation(
            0,
            pay_monthly=8888,
            pay_annual=106656,
            pay_p25=6658,
            pay_p75=13513,
        )
        result = build_site_records([occ], {})

        assert result[0]["pay_monthly"] == 8888
        assert result[0]["pay_annual"] == 106656
        assert result[0]["pay_p25"] == 6658
        assert result[0]["pay_p75"] == 13513

    def test_category_fields_mapped(self):
        """Category and major_group are correctly copied."""
        occ = _make_occupation(
            0,
            category="cleaners-labourers",
            category_label="Cleaners, Labourers and Related Workers",
            major_group=9,
        )
        result = build_site_records([occ], {})

        assert result[0]["category"] == "cleaners-labourers"
        assert result[0]["category_label"] == "Cleaners, Labourers and Related Workers"
        assert result[0]["major_group"] == 9

    def test_ssoc_code_and_url(self):
        """SSOC code and URL are present in output."""
        occ = _make_occupation(0, ssoc_code="25121")
        result = build_site_records([occ], {})

        assert result[0]["ssoc_code"] == "25121"
        assert result[0]["url"] == ""

    def test_empty_occupations(self):
        """Empty occupation list produces empty result."""
        result = build_site_records([], {})
        assert result == []

    def test_rationale_rename(self):
        """Score 'rationale' becomes 'exposure_rationale' in output."""
        occs = [_make_occupation(0)]
        scores = {
            "occupation-0": {
                "slug": "occupation-0",
                "title": "Occ",
                "exposure": 5,
                "rationale": "The key reason.",
            }
        }

        result = build_site_records(occs, scores)

        assert result[0]["exposure_rationale"] == "The key reason."
        assert "rationale" not in result[0]

    def test_malformed_exposure_degrades_to_none(self):
        """Malformed exposure nulls both exposure and rationale."""
        occs = [_make_occupation(0)]
        scores = {
            "occupation-0": {
                "slug": "occupation-0",
                "title": "Occ",
                "exposure": 15,  # out of range
                "rationale": "Valid.",
            }
        }

        result = build_site_records(occs, scores)
        assert result[0]["exposure"] is None
        assert result[0]["exposure_rationale"] is None

    def test_malformed_rationale_degrades_to_none(self):
        """Empty rationale degrades to None."""
        occs = [_make_occupation(0)]
        scores = {
            "occupation-0": {
                "slug": "occupation-0",
                "title": "Occ",
                "exposure": 5,
                "rationale": "",
            }
        }

        result = build_site_records(occs, scores)
        assert result[0]["exposure"] == 5
        assert result[0]["exposure_rationale"] is None

    def test_orphan_scores_ignored(self):
        """Scores for slugs not in occupations are silently ignored."""
        occs = [_make_occupation(0)]
        scores = {
            "occupation-0": _make_score("occupation-0", exposure=5),
            "orphan-slug": _make_score("orphan-slug", exposure=8),
        }

        result = build_site_records(occs, scores)

        assert len(result) == 1
        assert result[0]["slug"] == "occupation-0"


# ── write_site_data ─────────────────────────────────────────────────────


class TestWriteSiteData:
    """Tests for write_site_data."""

    def test_creates_output_file(self, tmp_path):
        """Output file is created with correct JSON."""
        records = [{"title": "Test", "exposure": 5}]
        output = tmp_path / "site" / "data.json"

        write_site_data(records, output)

        assert output.exists()
        data = json.loads(output.read_text())
        assert data == records

    def test_creates_parent_directory(self, tmp_path):
        """Parent directories are created if missing."""
        output = tmp_path / "deep" / "nested" / "data.json"

        write_site_data([{"test": True}], output)

        assert output.exists()

    def test_overwrites_existing(self, tmp_path):
        """Existing file is overwritten."""
        output = tmp_path / "data.json"
        output.write_text('{"old": true}')

        write_site_data([{"new": True}], output)

        data = json.loads(output.read_text())
        assert data == [{"new": True}]

    def test_unicode_preserved(self, tmp_path):
        """Non-ASCII characters are preserved (ensure_ascii=False)."""
        records = [{"title": "Caf\u00e9 Manager", "rationale": "\u2014 high exposure"}]
        output = tmp_path / "data.json"

        write_site_data(records, output)

        text = output.read_text(encoding="utf-8")
        assert "Caf\u00e9" in text
        assert "\u2014" in text

    def test_pretty_printed(self, tmp_path):
        """Output is indented for inspectability."""
        records = [{"title": "Test", "exposure": 5}]
        output = tmp_path / "data.json"

        write_site_data(records, output)

        text = output.read_text()
        # indent=2 produces multi-line output with leading spaces
        assert "\n" in text
        assert "  " in text


# ── main (CLI integration) ─────────────────────────────────────────────


class TestMain:
    """Tests for the main CLI entrypoint."""

    def test_basic_run(self, tmp_path, capsys, monkeypatch):
        """Main runs and produces output."""
        monkeypatch.chdir(tmp_path)
        occ_path, scores_path = _write_test_env(tmp_path, n_occs=3)

        main(["--occupations", str(occ_path), "--scores", str(scores_path)])

        output = tmp_path / "site" / "data.json"
        assert output.exists()
        data = json.loads(output.read_text())
        assert len(data) == 3

        captured = capsys.readouterr()
        assert "3 occupations" in captured.out
        assert "Scored: 3" in captured.out

    def test_custom_output_path(self, tmp_path, capsys, monkeypatch):
        """--output flag overrides default path."""
        monkeypatch.chdir(tmp_path)
        occ_path, scores_path = _write_test_env(tmp_path, n_occs=2)
        custom_output = tmp_path / "custom" / "output.json"

        main(
            [
                "--occupations",
                str(occ_path),
                "--scores",
                str(scores_path),
                "--output",
                str(custom_output),
            ]
        )

        assert custom_output.exists()
        data = json.loads(custom_output.read_text())
        assert len(data) == 2

    def test_missing_scores_file_produces_unscored(self, tmp_path, capsys, monkeypatch):
        """When scores file doesn't exist, all occupations are unscored."""
        monkeypatch.chdir(tmp_path)
        occs = [_make_occupation(i) for i in range(2)]
        occ_path = tmp_path / "sg_occupations.json"
        occ_path.write_text(json.dumps(occs))
        fake_scores = tmp_path / "nonexistent_scores.json"

        main(
            [
                "--occupations",
                str(occ_path),
                "--scores",
                str(fake_scores),
            ]
        )

        output = tmp_path / "site" / "data.json"
        data = json.loads(output.read_text())
        assert all(r["exposure"] is None for r in data)

        captured = capsys.readouterr()
        assert "Unscored" in captured.out
        assert "WARNING" in captured.err
        assert "nonexistent_scores.json" in captured.err

    def test_partial_scores(self, tmp_path, capsys, monkeypatch):
        """Mix of scored and unscored occupations."""
        monkeypatch.chdir(tmp_path)
        occ_path, scores_path = _write_test_env(
            tmp_path,
            n_occs=4,
            score_slugs=["occupation-0", "occupation-2"],
            exposures=[3, 8],
        )

        main(["--occupations", str(occ_path), "--scores", str(scores_path)])

        output = tmp_path / "site" / "data.json"
        data = json.loads(output.read_text())

        assert data[0]["exposure"] == 3
        assert data[1]["exposure"] is None
        assert data[2]["exposure"] == 8
        assert data[3]["exposure"] is None

        captured = capsys.readouterr()
        assert "Scored: 2" in captured.out
        assert "Unscored (exposure=null): 2" in captured.out

    def test_prints_average_exposure(self, tmp_path, capsys, monkeypatch):
        """Average exposure is printed when scores exist."""
        monkeypatch.chdir(tmp_path)
        occ_path, scores_path = _write_test_env(
            tmp_path,
            n_occs=2,
            score_slugs=["occupation-0", "occupation-1"],
            exposures=[4, 8],
        )

        main(["--occupations", str(occ_path), "--scores", str(scores_path)])

        captured = capsys.readouterr()
        assert "Average exposure: 6.0" in captured.out

    def test_missing_occupations_file_raises(self, tmp_path, monkeypatch):
        """FileNotFoundError when occupations file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        with pytest.raises(FileNotFoundError):
            main(["--occupations", str(tmp_path / "nonexistent.json")])

    def test_output_records_match_schema(self, tmp_path, monkeypatch):
        """Each record in output matches the target data.json schema."""
        monkeypatch.chdir(tmp_path)
        occ_path, scores_path = _write_test_env(tmp_path, n_occs=1)

        main(["--occupations", str(occ_path), "--scores", str(scores_path)])

        output = tmp_path / "site" / "data.json"
        data = json.loads(output.read_text())
        record = data[0]

        expected_keys = {
            "title",
            "slug",
            "ssoc_code",
            "category",
            "category_label",
            "major_group",
            "pay_monthly",
            "pay_annual",
            "pay_p25",
            "pay_p75",
            "exposure",
            "exposure_rationale",
            "url",
        }
        assert set(record.keys()) == expected_keys
        assert isinstance(record["major_group"], int)
        assert isinstance(record["pay_monthly"], int)
        assert isinstance(record["exposure"], int)
        assert isinstance(record["exposure_rationale"], str)

    def test_orphan_scores_reported(self, tmp_path, capsys, monkeypatch):
        """Orphan scores are counted in CLI summary."""
        monkeypatch.chdir(tmp_path)
        occs = [_make_occupation(0)]
        occ_path = tmp_path / "sg_occupations.json"
        occ_path.write_text(json.dumps(occs))

        scores = [
            _make_score("occupation-0", exposure=5),
            _make_score("stale-orphan", exposure=3),
            _make_score("another-orphan", exposure=7),
        ]
        scores_path = tmp_path / "sg_scores.json"
        scores_path.write_text(json.dumps(scores))

        main(["--occupations", str(occ_path), "--scores", str(scores_path)])

        captured = capsys.readouterr()
        assert "Orphan scores ignored: 2" in captured.out
