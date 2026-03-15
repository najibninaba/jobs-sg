"""Tests for scripts/score.py."""

import json
import subprocess
from pathlib import Path

import pytest

from scripts.score import (
    build_claude_command,
    load_cached_scores,
    main,
    parse_score_response,
    score_occupation,
    write_scores,
)

# ── Fixtures ─────────────────────────────────────────────────────────────


def _write_test_env(tmp_path: Path, *, n_occs: int = 2, pre_scored: dict | None = None) -> None:
    """Set up a minimal test environment in tmp_path."""
    occs = []
    pages = tmp_path / "pages"
    pages.mkdir()

    for i in range(n_occs):
        slug = f"occ-{i}"
        occs.append(
            {
                "title": f"Occupation {i}",
                "slug": slug,
                "ssoc_code": f"{i + 1:05d}",
                "category": "professionals",
                "category_label": "Professionals",
                "major_group": 2,
                "pay_monthly": 5000 + i * 1000,
                "pay_annual": (5000 + i * 1000) * 12,
                "pay_p25": 4000,
                "pay_p75": 7000,
                "url": "",
            }
        )
        (pages / f"{slug}.md").write_text(f"# Occupation {i}\nDescription here.")

    (tmp_path / "sg_occupations.json").write_text(json.dumps(occs))

    if pre_scored is not None:
        (tmp_path / "sg_scores.json").write_text(json.dumps(pre_scored))


def _fake_completed_process(
    stdout: str = '{"exposure": 7, "rationale": "Mostly digital."}',
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["claude", "-p"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class _FakeRunner:
    """Injectable subprocess runner for testing."""

    def __init__(self, responses: list[subprocess.CompletedProcess | Exception]) -> None:
        self._responses = list(responses)
        self._calls: list[list[str]] = []

    def run(self, cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        self._calls.append(cmd)
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


# ── Tests: build_claude_command ───────────────────────────────────


class TestBuildClaudeCommand:
    def test_no_model(self) -> None:
        cmd = build_claude_command("hello")
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--no-session-persistence" in cmd
        assert cmd[-1] == "hello"
        assert "--model" not in cmd

    def test_with_model(self) -> None:
        cmd = build_claude_command("hello", model="opus")
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "opus"


# ── Tests: parse_score_response ───────────────────────────────────


class TestParseScoreResponse:
    def test_raw_json(self) -> None:
        result = parse_score_response('{"exposure": 7, "rationale": "Digital work."}')
        assert result["exposure"] == 7
        assert result["rationale"] == "Digital work."

    def test_fenced_json(self) -> None:
        raw = '```json\n{"exposure": 5, "rationale": "Mixed."}\n```'
        result = parse_score_response(raw)
        assert result["exposure"] == 5

    def test_prose_wrapped(self) -> None:
        raw = 'Here is my analysis:\n{"exposure": 3, "rationale": "Physical."}\nDone.'
        result = parse_score_response(raw)
        assert result["exposure"] == 3

    def test_numeric_string_exposure(self) -> None:
        result = parse_score_response('{"exposure": "8", "rationale": "High."}')
        assert result["exposure"] == 8

    def test_empty_response(self) -> None:
        with pytest.raises(ValueError, match="Empty response"):
            parse_score_response("")

    def test_missing_exposure(self) -> None:
        with pytest.raises(ValueError, match="missing 'exposure'"):
            parse_score_response('{"rationale": "ok"}')

    def test_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            parse_score_response('{"exposure": 11, "rationale": "ok"}')

    def test_non_integer_exposure(self) -> None:
        with pytest.raises(ValueError, match="Non-integer"):
            parse_score_response('{"exposure": 7.5, "rationale": "ok"}')

    def test_empty_rationale(self) -> None:
        with pytest.raises(ValueError, match="empty 'rationale'"):
            parse_score_response('{"exposure": 5, "rationale": ""}')

    def test_no_json_found(self) -> None:
        with pytest.raises(ValueError, match="No JSON"):
            parse_score_response("Just some prose without any JSON.")

    def test_non_numeric_exposure_string(self) -> None:
        with pytest.raises(ValueError, match="Non-numeric"):
            parse_score_response('{"exposure": "high", "rationale": "ok"}')


# ── Tests: load_cached_scores / write_scores ──────────────────────


class TestCacheOps:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_cached_scores(tmp_path / "nope.json") == {}

    def test_force_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "scores.json"
        path.write_text('[{"slug": "x", "exposure": 5, "rationale": "ok"}]')
        assert load_cached_scores(path, force=True) == {}

    def test_loads_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "scores.json"
        data = [{"slug": "a", "exposure": 3, "rationale": "ok"}]
        path.write_text(json.dumps(data))
        scores = load_cached_scores(path)
        assert "a" in scores

    def test_duplicate_last_wins(self, tmp_path: Path) -> None:
        path = tmp_path / "scores.json"
        data = [
            {"slug": "x", "exposure": 3, "rationale": "old"},
            {"slug": "x", "exposure": 7, "rationale": "new"},
        ]
        path.write_text(json.dumps(data))
        scores = load_cached_scores(path)
        assert scores["x"]["exposure"] == 7

    def test_write_scores(self, tmp_path: Path) -> None:
        path = tmp_path / "out.json"
        scores = {"a": {"slug": "a", "exposure": 5, "rationale": "ok"}}
        write_scores(scores, path)
        loaded = json.loads(path.read_text())
        assert len(loaded) == 1
        assert loaded[0]["slug"] == "a"


# ── Tests: score_occupation ───────────────────────────────────────


class TestScoreOccupation:
    def test_success(self) -> None:
        runner = _FakeRunner([_fake_completed_process()])
        result = score_occupation("# Test\nDesc.", runner=runner)
        assert result["exposure"] == 7
        assert len(runner._calls) == 1

    def test_nonzero_exit(self) -> None:
        runner = _FakeRunner([_fake_completed_process(returncode=1, stderr="error msg")])
        with pytest.raises(ValueError, match="exited with code 1"):
            score_occupation("test", runner=runner)

    def test_timeout(self) -> None:
        runner = _FakeRunner([subprocess.TimeoutExpired(cmd=["claude"], timeout=120)])
        with pytest.raises(ValueError, match="timed out"):
            score_occupation("test", runner=runner)

    def test_empty_stdout(self) -> None:
        runner = _FakeRunner([_fake_completed_process(stdout="")])
        with pytest.raises(ValueError, match="Empty response"):
            score_occupation("test", runner=runner)

    def test_invalid_json(self) -> None:
        runner = _FakeRunner([_fake_completed_process(stdout="not json")])
        with pytest.raises(ValueError, match="No JSON"):
            score_occupation("test", runner=runner)

    def test_with_model(self) -> None:
        runner = _FakeRunner([_fake_completed_process()])
        score_occupation("test", model="opus", runner=runner)
        assert "--model" in runner._calls[0]


# ── Tests: main ───────────────────────────────────────────────────


class TestMain:
    def test_happy_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        _write_test_env(tmp_path)

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            return _fake_completed_process(
                stdout=json.dumps(
                    {"exposure": call_count + 4, "rationale": f"Score {call_count}."}
                )
            )

        monkeypatch.setattr("scripts.score.subprocess.run", fake_run)
        monkeypatch.setattr("scripts.score.time.sleep", lambda _: None)

        main([])

        scores_path = tmp_path / "sg_scores.json"
        assert scores_path.exists()
        data = json.loads(scores_path.read_text())
        assert len(data) == 2
        assert call_count == 2

    def test_resume_skips_cached(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        pre_scored = [{"slug": "occ-0", "title": "Occ 0", "exposure": 5, "rationale": "cached"}]
        _write_test_env(tmp_path, pre_scored=pre_scored)

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            return _fake_completed_process()

        monkeypatch.setattr("scripts.score.subprocess.run", fake_run)
        monkeypatch.setattr("scripts.score.time.sleep", lambda _: None)

        main([])

        assert call_count == 1  # Only occ-1 was scored

    def test_force_rescores(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        pre_scored = [{"slug": "occ-0", "title": "Occ 0", "exposure": 5, "rationale": "old"}]
        _write_test_env(tmp_path, pre_scored=pre_scored)

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            return _fake_completed_process()

        monkeypatch.setattr("scripts.score.subprocess.run", fake_run)
        monkeypatch.setattr("scripts.score.time.sleep", lambda _: None)

        main(["--force"])

        assert call_count == 2  # Both rescored

    def test_missing_page_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        _write_test_env(tmp_path)
        # Remove one page
        (tmp_path / "pages" / "occ-0.md").unlink()

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            return _fake_completed_process()

        monkeypatch.setattr("scripts.score.subprocess.run", fake_run)
        monkeypatch.setattr("scripts.score.time.sleep", lambda _: None)

        main([])

        assert call_count == 1  # Only occ-1

    def test_error_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _write_test_env(tmp_path)

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _fake_completed_process(returncode=1, stderr="fail")
            return _fake_completed_process()

        monkeypatch.setattr("scripts.score.subprocess.run", fake_run)
        monkeypatch.setattr("scripts.score.time.sleep", lambda _: None)

        main([])

        assert call_count == 2  # Both attempted
        output = capsys.readouterr().out
        assert "ERROR" in output
        assert "1 errors" in output

    def test_start_end_flags(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        _write_test_env(tmp_path, n_occs=5)

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            return _fake_completed_process()

        monkeypatch.setattr("scripts.score.subprocess.run", fake_run)
        monkeypatch.setattr("scripts.score.time.sleep", lambda _: None)

        main(["--start", "1", "--end", "3"])

        assert call_count == 2  # Only occ-1 and occ-2
