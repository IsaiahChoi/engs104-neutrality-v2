"""S3b item 8 (optional; Decision 47; exploratory, no prediction; an A9 diagnostic), tests first:
experiments/run_n2_probe.py writes the CVXPY-built Gurobi models of N2(b) with and without the
risk-row normalization to .lp files, diffs them, and re-solves both with Presolve 0 and with
ScaleFlag 0. The default setting reproduces run_n2's Gurobi-barrier solve."""
from __future__ import annotations

import numpy as np
import pytest

import experiments.run_n2 as n2
import experiments.run_n2_probe as X
from experiments.designs import config


def test_config_reads_numerics_and_lists_settings():
    c = config("n2_probe")
    assert c["runner"] == "n2_probe" and c["source_config"] == "numerics"
    assert set(c["settings"]) == {"default", "presolve0", "scaleflag0"}
    assert c["settings"]["presolve0"] == {"Presolve": 0} and c["settings"]["scaleflag0"] == {"ScaleFlag": 0}


def test_lp_diff(tmp_path):
    a, b = tmp_path / "a.lp", tmp_path / "b.lp"
    a.write_text("Maximize\n obj: x + y\nSubject To\n R0: x <= 1\n qc0: [ x ^2 ] <= 1\nEnd\n")
    b.write_text("Maximize\n obj: x + y\nSubject To\n R0: x <= 2\n qc0: [ x ^2 ] <= 1\nEnd\n")
    d = X.lp_diff(a, b)
    assert d["n_lines_a"] == 6 and d["n_lines_b"] == 6 and d["n_changed"] == 1
    assert d["changed"] == [[" R0: x <= 1", " R0: x <= 2"]]


@pytest.fixture(scope="module")
def small(tmp_path_factory):
    d = tmp_path_factory.mktemp("probe")
    item = {"date": "2017-12", "N": 30, "scaled": True, "run_dir": str(d),
            "settings": config("n2_probe")["settings"]}
    return item, X.probe_task(item)


def test_probe_task_rows_and_files(small):
    item, out = small
    r = out["n2_probe"]
    assert len(r) == 6 and set(r["setting"]) == {"default", "presolve0", "scaleflag0"}
    assert set(r["normalize"]) == {True, False} and r["ok"].all()
    lp = out["n2_probe_lp"].iloc[0]
    for f in (lp["lp_normalized"], lp["lp_unnormalized"]):
        assert (X.Path(item["run_dir"]) / f).is_file()
    assert lp["n_changed"] >= 1                     # the risk row differs


def test_default_setting_reproduces_run_n2(small):
    item, out = small
    r = out["n2_probe"].set_index(["setting", "normalize"])
    P, alpha = n2._problem(item["date"], item["N"])
    from src.opt.integer import choose_s_obj
    from src.opt.risk_budget import solve_risk_budget
    s = choose_s_obj(solve_risk_budget(P, alpha).A)
    for nz in (True, False):
        sol = n2._solve(P, alpha, "GUROBI_BARRIER", nz, s, n2.DEFAULT_TOLS["GUROBI_BARRIER"])
        assert r.loc[("default", nz), "A"] == sol.objective
        assert np.isfinite(r.loc[("default", nz), "A"])
