"""tools/make_facts.py, S4 step 0a (Isaiah's note "S3b read; Decision 49; run S4"), tests first.

- Decision 49: the P7 line keeps its arithmetic but says it counted one shared b point per I1
  instance, while the I1 runner re-solved each case's own b; integer.yaml is the approved file.
- Measured effort of each current S3 and S3b run: solves and statuses, total and median Work, and
  wall-clock from RUN_LOG's start and end.
- "Software and tests" comes from the newest full-suite log, not the newest C run's make log.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.utils import ROOT
from tools import make_facts as mf


# ----- P7 (Decision 49) -----

def test_p7_i1_clause_states_both_counts():
    t = mf.p7_i1_clause(projected_points=105, projected_solves=210, run_points=144, run_solves=288)
    assert "one shared b point per instance" in t
    assert "105 points, 210 solves" in t and "144 points, 288 solves" in t
    assert "re-solved each case's own b" in t


def _build(tmp_path):
    try:
        return mf.build(tmp_path / "FACTS.md")
    except SystemExit as e:
        pytest.skip(f"stored runs not available: {e}")


def test_p7_line_has_the_decision_49_wording(tmp_path):
    lines = _build(tmp_path)
    p7 = [ln for ln in lines if ln[2:].startswith("P7")]
    assert len(p7) == 1
    assert "proposed integer.yaml" not in p7[0]
    assert "integer.yaml (approved at GATE DESIGN)" in p7[0]
    i1 = mf.latest_done("i1")
    S = json.loads((i1 / "summary.json").read_text())
    assert f"{S['points']['n_points']} points, {S['solves']['n']} solves" in p7[0]
    assert f"`{mf.rel(i1 / 'summary.json')}` sha256 `{mf.sha(i1 / 'summary.json')}`" in p7[0]
    assert "one shared b point per instance" in p7[0]


# ----- RUN_LOG wall-clock -----

def _log():
    return pd.DataFrame({
        "timestamp": ["2026-10-21T00:14:23Z", "2026-10-21T00:10:00Z", "2026-10-21T01:00:00Z"],
        "git_commit": ["a", "b", "c"], "config_path": ["x"] * 3,
        "status": ["ok", "superseded", "failed"],
        "output_path": ["results/i1/run_A", "results/i1/run_B", "results/i1/run_C"],
        "notes": ["i1 run_A; ok 2026-10-21T00:15:28Z: i1: 48 cases",
                  "i1 run_B; ok 2026-10-21T00:11:00Z: x; superseded 2026-10-21T00:32:29Z: y",
                  "i1 run_C; failed 2026-10-21T01:00:05Z: boom"]})


def test_run_log_window_reads_start_and_ok_end():
    w = mf.run_log_window(_log(), "results/i1/run_A")
    assert w["start"] == "2026-10-21T00:14:23Z" and w["end"] == "2026-10-21T00:15:28Z"
    assert w["seconds"] == 65.0 and w["commit"] == "a"


def test_run_log_window_refuses_a_run_that_is_not_ok_or_absent():
    with pytest.raises(ValueError):
        mf.run_log_window(_log(), "results/i1/run_C")
    with pytest.raises(ValueError):
        mf.run_log_window(_log(), "results/i1/run_missing")


# ----- per-run effort -----

def test_run_effort_counts_statuses_work_and_failures():
    frames = {
        "s": pd.DataFrame({"status": ["OPTIMAL", "OPTIMAL", "WORK_LIMIT"], "work": [1.0, 2.0, 9.0]}),
        "r": pd.DataFrame({"clarabel_status": ["Solved", "AlmostSolved", "AlmostSolved"],
                           "ok": [True, True, False]}),
        "q": pd.DataFrame({"x": [1, 2]})}
    spec = [("s", "status", "MIQP solves", True), ("r", "clarabel_status", "relaxations", False),
            ("q", None, "QP re-solves", False)]
    s, r, q = mf.run_effort(frames, spec)
    assert s["n"] == 3 and s["statuses"] == {"OPTIMAL": 2, "WORK_LIMIT": 1}
    assert s["work_total"] == 12.0 and s["work_median"] == 2.0
    assert r["n"] == 3 and r["statuses"] == {"AlmostSolved": 2, "Solved": 1} and r["failed"] == 1
    assert r["work_total"] is None
    assert q["n"] == 2 and q["statuses"] is None


def test_effort_lines_cover_the_eight_runs_and_match_the_summaries(tmp_path):
    lines = _build(tmp_path)
    eff = [ln for ln in lines if ln.startswith("- Measured effort, ")]
    names = [ln[len("- Measured effort, "):].split(" ")[0] for ln in eff]
    assert names == ["I1", "I2", "N1", "N2", "K29c", "k29b_ext", "s3b", "n2_probe"]
    assert all("results/RUN_LOG.csv` sha256 `" in ln and "wall-clock" in ln for ln in eff)
    S = json.loads((mf.latest_done("i1") / "summary.json").read_text())["solves"]
    i1 = eff[0]
    assert f"{S['n']} MIQP solves" in i1 and mf.g(S["work_total"]) in i1 and mf.g(S["work_median"]) in i1
    assert "P7" not in "".join(eff)


# ----- full-suite log -----

def test_newest_full_suite_log_is_chosen_by_stamp(tmp_path):
    (tmp_path / "make_c23_20261019T192616Z.log").write_text("258 passed, 2 xfailed in 9s\n")
    (tmp_path / "make_s3b_20261021T024235Z.out").write_text("459 passed, 1 skipped, 2 xfailed, 1 warning in 90s\n")
    (tmp_path / "test_full_20261021T050000Z.log").write_text("481 passed, 1 skipped, 2 xfailed in 91s\n")
    (tmp_path / "test_s3b_round2_green_20261021T060000Z.log").write_text("40 passed in 1.9s\n")
    f, c = mf.full_suite_log(tmp_path)
    assert f.name == "test_full_20261021T050000Z.log"
    assert c == {"passed": 481, "skipped": 1, "xfailed": 2}


def test_full_suite_log_refuses_a_log_without_a_summary(tmp_path):
    (tmp_path / "test_full_20261021T050000Z.log").write_text("collecting ...\n")
    with pytest.raises(ValueError):
        mf.full_suite_log(tmp_path)


def test_software_line_cites_the_newest_full_suite_log(tmp_path):
    lines = _build(tmp_path)
    f, c = mf.full_suite_log(ROOT / "logs")
    t = [ln for ln in lines if ln.startswith("- Full test suite")]
    assert len(t) == 1 and f"{c['passed']} passed" in t[0] and f"`{mf.rel(f)}`" in t[0]
    assert not any(ln.startswith("- Test suite before the newest C run") for ln in lines)
