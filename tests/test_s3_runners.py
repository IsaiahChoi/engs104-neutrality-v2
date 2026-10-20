"""S3 runners I1, I2, N1, N2 (experiments/run_{i1,i2,n1,n2}.py, shared experiments/s3.py), written
in S2d before GATE DESIGN (item 5), tests first. These tests check the machinery only: the config
guard (a production run is refused while its config is "proposed, pending GATE DESIGN"; --config
takes only a smoke config), the plans against the proposed configs' counts, and the structure of
each task's records (the checker's verdict on every solve, certified intervals well formed) on a
small real instance (top 30, the K8 size). No estimator value is asserted.
"""
from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
import yaml

import experiments.run_i1 as i1
import experiments.run_i2 as i2
import experiments.run_n1 as n1
import experiments.run_n2 as n2
import experiments.s3 as s3
from experiments.designs import CONFIGS, config
from src.utils import ROOT

SMALL = {"date": "2017-12", "N": 30, "f": 0.5}


@pytest.fixture(scope="module")
def inst():
    return s3.instance(SMALL["date"], SMALL["N"], SMALL["f"])


# ----- the config guard -----

@pytest.mark.parametrize("runner", ["i1", "i2", "n1", "n2"])
def test_production_run_refused_while_proposed(runner, monkeypatch):
    """The guard refuses a production run while the runner's config is "proposed". Spec change in
    S3 step 1 (PROGRESS): integer.yaml and numerics.yaml are approved at GATE DESIGN, so the
    proposed state is now constructed (the real config with its S2 status) instead of read."""
    name = s3.DEFAULT_CONFIG[runner]
    real = config(name)
    proposed = {**real, "status": "proposed, pending GATE DESIGN"}
    monkeypatch.setattr(s3, "config", lambda n: proposed if n == name else config(n))
    with pytest.raises(RuntimeError, match="GATE DESIGN"):
        s3.load_run_config(runner, [])


@pytest.mark.parametrize("runner", ["i1", "i2", "n1", "n2"])
def test_smoke_config_accepted_as_pilot(runner):
    path, cfg, status = s3.load_run_config(runner, ["--config", f"experiments/configs/smoke_{runner}.yaml"])
    assert status == "pilot" and cfg["smoke"] is True and path == f"experiments/configs/smoke_{runner}.yaml"
    assert cfg["runner"] == runner


def test_non_smoke_or_outside_config_refused(tmp_path):
    with pytest.raises(ValueError, match="smoke"):
        s3.load_run_config("i1", ["--config", "experiments/configs/integer.yaml"])
    with pytest.raises(ValueError, match="smoke"):
        s3.load_run_config("i1", ["--config", "experiments/configs/smoke_n1.yaml"])   # another runner's
    p = tmp_path / "smoke_i1.yaml"
    p.write_text((CONFIGS / "smoke_i1.yaml").read_text())
    with pytest.raises(ValueError, match="experiments/configs"):
        s3.load_run_config("i1", ["--config", str(p)])


def test_smoke_configs_are_tiny_and_change_no_default():
    """S2d item 5: one tiny instance (2017-12, N = 100, one K, base tightness); integer.yaml and
    numerics.yaml keep their proposed values (the smoke configs are separate files)."""
    for r in ("i1", "i2", "n1", "n2"):
        c = config(f"smoke_{r}")
        blk = c[r]
        if r == "n2":
            blk = c["n2"]["miqp"]
        if r == "i2":
            assert len(blk["instances"]) == 1
            blk = blk["instances"][0]
        assert blk.get("dates", [blk.get("date")]) == ["2017-12"] or blk.get("date") == "2017-12"
        assert blk["N"] in (100, [100])
    assert config("integer")["i1"]["N"] == 250 and config("numerics")["n1"]["N"] == [100, 250, "full"]


# ----- plans against the proposed configs -----

def test_i1_plan_counts():
    """DESIGN §7 I1: 3 dates × 3 f × the constraints at δ = 10%, plus δ = 5% at 2017-12."""
    cfg = config("integer")
    plan = i1.plan(cfg)
    nc = len(cfg["i1"]["constraints"])
    assert len(plan) == 9 * nc + 3 * nc
    assert {p["rel_delta"] for p in plan} == {0.10, 0.05}
    assert all(p["date"] == "2017-12" for p in plan if p["rel_delta"] == 0.05)


def test_i2_points_include_the_estimator_neighbours():
    """41 points on [0, 2b]; at 0.5b, b, 1.5b the certified interval needs e(1 ± δ_rel), which lie
    on the production grid (no extra points); a coarser smoke grid adds them."""
    pts, est = i2.points(0.02, 41, (0.5, 1.0, 1.5), 0.10)
    assert len(pts) == 41 and est == pytest.approx([0.01, 0.02, 0.03])
    pts5, _ = i2.points(0.02, 5, (0.5, 1.0, 1.5), 0.10)
    for e in (0.01, 0.02, 0.03):
        for x in (0.9 * e, e, 1.1 * e):
            assert np.isclose(pts5, x, rtol=0, atol=1e-15).any()
    assert len(pts5) == 5 + 6


def test_i2_requires_an_explicit_constraint():
    """Spec change in S3 (PROGRESS, I2 constraint entry): integer.yaml now holds the constraint
    chosen after I1, so the pre-choice text is constructed; it is still refused."""
    cfg = config("integer")
    pre = {**cfg["i2"], "constraint": "the I1 constraint with the largest median slope (chosen after I1)"}
    with pytest.raises(ValueError, match="constraint"):
        i2.constraint_of(pre)                          # "chosen after I1": not a key yet
    assert i2.constraint_of(cfg["i2"]) == {"key": "sector", "b": 0.02}


def test_n1_plan_counts():
    """DESIGN §7 N1 with the proposed three arms: 36 instances × 3 = 108, presolve off at N = 250:
    12 × 3 = 36."""
    plan = n1.plan(config("numerics"))
    assert len(plan) == 144
    assert sum(p["presolve"] == 0 for p in plan) == 36
    assert all(p["N"] == 250 for p in plan if p["presolve"] == 0)


def test_n2_plan_counts():
    cfg = config("numerics")
    assert len(n2.miqp_plan(cfg)) == 24               # 4 instances × 3 arms × 2 scales
    v = n2.convex_variants(cfg["n2"]["convex"])
    assert {x["solver"] for x in v} == {"GUROBI_BARRIER", "CLARABEL", "SCS"}
    g = [x for x in v if x["solver"] == "GUROBI_BARRIER"]
    assert {(x["normalize"], x["scaled"]) for x in g} == {(a, b) for a in (False, True) for b in (False, True)}


# ----- task records on a small instance -----

def _check_solves(df: pd.DataFrame):
    assert len(df) and {"status", "work", "runtime", "polished_violations", "V", "B"} <= set(df.columns)
    assert (df["polished_violations"] == "{}").all(), df["polished_violations"].tolist()


def test_i1_task_records(inst):
    cfg = config("smoke_i1")
    t = i1.make_task(cfg, inst, {"key": "sector", "b": 0.02}, rel_delta=0.10, f=SMALL["f"])
    out = i1.i1_task(t)
    assert set(out) == set(i1.FRAMES)
    _check_solves(out["i1_solves"])
    assert len(out["i1_solves"]) == 3 * 2                      # b − δ, b, b + δ × two formulations
    e = out["i1_estimators"].iloc[0]
    assert e["L"] <= e["s"] <= e["H"] and np.isfinite(e["mu_bigm_relax"])
    assert {"mu_fixed", "persp_slope", "persp_ok", "persp_kink", "mu_persp_raw", "binding",
            "solver_error", "work_total"} <= set(out["i1_estimators"].columns)
    assert {"mu_persp_raw_unusable", "persp_raw_usable", "persp_raw_status"} <= set(e.index)
    _check_point_flags(out["i1_points"])
    b = out["i1_baseline"]
    assert set(b["kind"]) == {"fixed_lambda", "risk_budget"} and (b["checker"] == "{}").all()
    assert len(out["i1_weights"]) == 3 * SMALL["N"]


def test_i2_task_records(inst):
    cfg = config("smoke_i2")
    t = i2.make_task(cfg, inst, {"key": "sector", "b": 0.02}, b=0.0, estimator=False)
    out = i2.i2_task(t)
    _check_solves(out["i2_solves"])
    assert set(out["i2_baseline"]["kind"]) == {"fixed_lambda", "risk_budget"}
    assert len(out["i2_slope_points"]) == 0                    # b = 0 is not an estimator point
    t = i2.make_task(cfg, inst, {"key": "sector", "b": 0.02}, b=0.02, estimator=True)
    out = i2.i2_task(t)
    # spec change in S3 step 1 (PROGRESS): DESIGN §6 as edited at GATE DESIGN takes 5 stencil
    # points (the three-point one-sided slopes), so the default "central" rule records 5, not 3
    assert len(out["i2_slope_points"]) == 5 and out["i2_points"]["estimator"].iloc[0]
    assert {"mu_persp_raw", "mu_persp_raw_unusable", "persp_raw_usable",
            "persp_raw_status"} <= set(out["i2_points"].columns)
    _check_point_flags(out["i2_points"])


def test_n1_task_records(inst):
    cfg = config("smoke_n1")
    plan = [p for p in n1.plan(cfg) if p["arm"] == "perspective_rescaled"]
    t = n1.make_task(cfg, plan[0], inst)
    out = n1.n1_task(t)
    _check_solves(out["n1_solves"])
    r = out["n1_solves"].iloc[0]
    assert r["arm"] == "perspective_rescaled" and r["rescale"] and np.isfinite(r["root_bound"])
    assert json.loads(r["settings"])["presolve"] == plan[0]["presolve"]


def test_n2_convex_records():
    cfg = config("smoke_n2")
    out = n2.convex_task(n2.convex_item(cfg, "2017-12", N=30))
    df = out["n2_convex"]
    assert {"reference", "GUROBI_BARRIER", "CLARABEL"} <= set(df["solver"])
    assert {"status", "A", "A_rel_err", "w_l1_rel_err", "max_binding_dual_rel_err", "obj_scale",
            "normalize", "solve_time", "checker"} <= set(df.columns)
    ref = df[df["solver"] == "reference"].iloc[0]
    assert ref["checker"] == "{}"                              # every solution is checked; the reference passes
    assert ref["ok"] and ref["A_rel_err"] == 0.0


def test_continuous_verdict_elementwise():
    """The checker on continuous weights at the problem's current bounds, a non-common element
    bound checked element by element."""
    from tests.test_baseline import k13
    P, alpha, rb = k13()
    assert s3.continuous_verdict(P, rb.sol.w) == "{}"
    from src.opt.sensitivity import restore, set_bound_by_key, snapshot
    snap = snapshot(P)
    try:
        set_bound_by_key(P, "sector:0", 0.0)
        v = json.loads(s3.continuous_verdict(P, rb.sol.w))
        assert v == {} or "sector:0" in v
        w = rb.sol.w.copy()
        j = np.flatnonzero(P.S[:, 0])[0]
        w[j] += 0.5
        assert "sector:0" in json.loads(s3.continuous_verdict(P, w))
    finally:
        restore(P, snap)


def test_summaries_hold_no_estimator_values():
    """Runner summaries report statuses, counts, Work and Runtime only (analysis is S3 item 3)."""
    df = pd.DataFrame({"status": ["OPTIMAL", "WORK_LIMIT"], "work": [1.0, 2.0], "runtime": [0.1, 0.2],
                       "polished_violations": ["{}", "V undefined"], "V": [1.0, np.nan]})
    s = s3.solve_summary(df)
    assert s == {"n": 2, "statuses": {"OPTIMAL": 1, "WORK_LIMIT": 1}, "n_checker_violations": 0,
                 "n_v_undefined": 1, "work_total": 3.0, "work_median": 1.5, "runtime_total": pytest.approx(0.3)}


# ---- Decision 25: failed perspective relaxations keep Clarabel's raw duals, marked unusable; the
# runners record them in their own column and never in mu_persp_raw

def _persp_rec(ok: bool) -> dict:
    duals = {"sector": 1.5e-3, "dollar": 2e-5}
    return {"ok": ok, "status": "optimal" if ok else "clarabel relax duality gap 1e-12 above ...",
            "shadow": dict(duals) if ok else {}, "raw_duals": dict(duals), "raw_duals_usable": ok}


def test_persp_raw_columns_usable():
    out = s3.persp_raw_columns(_persp_rec(True), "sector")
    assert out["mu_persp_raw"] == 1.5e-3 and np.isnan(out["mu_persp_raw_unusable"])
    assert out["persp_raw_usable"] is True


def test_persp_raw_columns_failed_kept_apart():
    out = s3.persp_raw_columns(_persp_rec(False), "sector")
    assert np.isnan(out["mu_persp_raw"])
    assert out["mu_persp_raw_unusable"] == 1.5e-3 and out["persp_raw_usable"] is False
    assert "duality gap" in out["persp_raw_status"]
    none = s3.persp_raw_columns({**_persp_rec(False), "raw_duals": {}}, "sector")
    assert np.isnan(none["mu_persp_raw"]) and np.isnan(none["mu_persp_raw_unusable"])


# ---- S2e item 3: combined certification's V > B flag on every I1/I2 point, counted in the summary

def _check_point_flags(df: pd.DataFrame) -> None:
    from src.opt.integer import polished_exceeds_bound
    assert "flag_V_exceeds_B" in df.columns
    expect = [polished_exceeds_bound(V, B) for V, B in zip(df["V"], df["B"])]
    assert df["flag_V_exceeds_B"].astype(bool).tolist() == expect


def test_point_flag_summary_counts_constructed():
    df = pd.DataFrame({"V": [1.0, 1.0 + 2e-6, np.nan, 1.0],
                       "B": [1.0 + 1e-3, 1.0, 1.0, 1.0 - 0.5e-6]})
    df["flag_V_exceeds_B"] = [False, True, False, False]
    assert s3.point_flag_summary(df) == {"n_points": 4, "n_flag_V_exceeds_B": 1,
                                         "n_V_undefined": 1}
    assert s3.point_flag_summary(pd.DataFrame()) == {"n_points": 0, "n_flag_V_exceeds_B": 0,
                                                     "n_V_undefined": 0}
