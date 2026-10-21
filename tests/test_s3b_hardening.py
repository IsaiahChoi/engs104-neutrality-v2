"""S3b item 1 (Isaiah's GATE I note; python-reviewer M2, M4, L1, L3, L4), tests first.

- tools/s3_analysis.py: each *_analysis function (and k26) on synthetic frames whose answers are
  known; every filter raises on zero rows instead of reporting n = 0 or nan (M2).
- L1: the raw-dual statistic at the main δ only, split by persp_raw_usable.
- L4: the JSON writer keeps bools and ints (np.bool_ → true, np.int64 → an int).
- Correction (b): the K27 dual-versus-secant error is reported per δ (Table II's convex row is
  the δ = 10% subset).
- Item 7: N1 at N = 250, presolve on against off, per arm, beside the plain-relaxation gaps.
- M4: run_k29c's verdict fails on any "unchecked" toy point.
- L3: run_i1 refuses a task list in which a K29b instance id does not occur.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import tools.s3_analysis as T
from experiments import run_i1, run_k29c


# ----- I1 -----

def _est(**over):
    r = {"id": "c", "instance": "2017-12_N250_f0.5_K67", "date": "2017-12", "N": 250, "f": 0.5,
         "K": 67, "key": "sector", "b": 0.02, "rel_delta": 0.10, "delta": 0.002, "V": 1.0e-3,
         "B": 1.0e-3, "L": 0.9e-3, "H": 1.1e-3, "s": 1.0e-3, "binding": True,
         "solver_error": False, "mu_bigm_relax": 1.2e-3, "persp_slope": 1.05e-3,
         "persp_ok": True, "persp_kink": False, "persp_concave": True, "persp_fail_reason": None,
         "mu_fixed": 0.5e-3, "mu_persp_raw": 1.05e-3, "persp_raw_usable": True,
         "mu_persp_raw_unusable": np.nan, "k29b_scale": np.nan, "persp_slope_k29b": np.nan,
         "persp_ok_k29b": False, "persp_noise_central": 1e-12}
    r.update(over)
    return r


def _i1_frames():
    est = pd.DataFrame([
        _est(id="a", f=0.25, mu_persp_raw=1.1e-3),                       # raw error 0.05/1.05
        _est(id="b", f=0.5, persp_raw_usable=False, mu_persp_raw=np.nan,
             mu_persp_raw_unusable=2.1e-3, k29b_scale=10.0,             # unusable: raw error 1.0
             persp_slope_k29b=1.05e-3 * (1 + 1e-6), persp_ok_k29b=True),
        _est(id="n", f=0.75, binding=False, L=-1e-9, s=0.0, mu_bigm_relax=0.0,
             persp_slope=0.0, mu_fixed=0.0, mu_persp_raw=0.0),
        _est(id="d", f=0.5, rel_delta=0.05, mu_persp_raw=5.0e-3),         # not main δ: raw error ignored
    ])
    pts = pd.DataFrame({"V": [1.0] * 4, "B": [1.0] * 4, "flag_V_exceeds_B": [False] * 4,
                        "v_from": ["bigm"] * 4, "b_from": ["bigm", "bigm", "perspective_rescaled", "bigm"],
                        "v_tie": [True] * 4, "b_tie": [False] * 4})
    solves = pd.DataFrame({"work": [1.0, 2.0, 3.0], "status": ["OPTIMAL"] * 3})
    sp = pd.DataFrame({"scale_factor": [1.0] * 5 + [10.0] * 5, "ok": [True] * 10})
    base = pd.DataFrame({"rel_delta": [0.10, 0.10, 0.10, 0.05], "mu": [1e-3, 1e-3, 0.0, 1e-3],
                         "b": [0.02] * 4, "value": [1e-3] * 4, "slope": [1e-3, 1e-3, 0.0, 1e-3],
                         "within": [True, True, False, True], "kink": [False] * 4,
                         "rel_err": [1e-6, 1e-6, np.nan, 1e-6],
                         "secant": [1.001e-3, 1.004e-3, 0.0, 1.5e-3]})
    return {"i1_estimators": est, "i1_points": pts, "i1_solves": solves, "i1_slope_points": sp,
            "i1_baseline": base}


def test_i1_analysis_on_known_frames():
    out, tables = T.i1_analysis(_i1_frames())
    assert out["n_cases"] == 4 and out["n_cases_main_delta"] == 3
    assert out["n_binding_main_delta"] == 2
    e = {r["estimator"]: r for r in out["errors_all_f_main_delta"]}
    assert e["bigm_relax"]["n_binding"] == 2 and e["bigm_relax"]["median_rel_err"] == pytest.approx(0.2)
    assert e["fixed"]["median_rel_err"] == pytest.approx(0.5)
    assert out["suppliers"]["b_from"] == {"bigm": 3, "perspective_rescaled": 1}
    assert out["perspective"]["relaxations"] == 5 and out["perspective"]["relaxations_failed"] == 0
    assert out["k29b"]["n"] == 1 and out["k29b"]["misses"] == 0
    assert out["k27_baseline"]["n_binding"] == 3
    assert set(tables) == {"i1_long", "i1_errors_by_f", "i1_errors_by_delta", "i1_nonbinding"}
    assert set(tables["i1_errors_by_delta"]["rel_delta"]) == {0.05, 0.10}


def test_i1_raw_dual_statistic_main_delta_split_by_usable():
    """L1: main δ only (n = 2 binding there), split by persp_raw_usable; an unusable case's
    raw dual is the kept one (Decision 25)."""
    out, _ = T.i1_analysis(_i1_frames())
    r = out["perspective"]["raw_dual_rel_err_binding"]
    assert set(r) == {"usable", "unusable"}
    assert r["usable"]["n"] == 1 and r["usable"]["median"] == pytest.approx(0.05e-3 / 1.05e-3)
    assert r["unusable"]["n"] == 1 and r["unusable"]["median"] == pytest.approx(1.0)


def test_i1_k27_secant_by_delta():
    """Correction (b): Table II's convex row is the δ = 10% subset; both δ are reported."""
    out, _ = T.i1_analysis(_i1_frames())
    by = out["k27_baseline_by_delta"]
    assert by["0.1"]["n_secant"] == 2 and by["0.05"]["n_secant"] == 1
    assert by["0.1"]["secant_rel_err_median"] == pytest.approx(np.median([1e-6 / 1.001e-3, 4e-6 / 1.004e-3]))
    assert by["0.05"]["secant_rel_err_max"] == pytest.approx(0.5e-3 / 1.5e-3)


def test_i1_filters_raise_on_zero_rows():
    f = _i1_frames()
    f["i1_estimators"] = f["i1_estimators"].assign(rel_delta=0.2)
    with pytest.raises(ValueError, match="0 rows"):
        T.i1_analysis(f)
    f = _i1_frames()
    f["i1_slope_points"] = f["i1_slope_points"].assign(scale_factor=2.0)
    with pytest.raises(ValueError, match="0 rows"):
        T.i1_analysis(f)
    f = _i1_frames()
    f["i1_estimators"] = f["i1_estimators"].assign(date="2009-03")
    with pytest.raises(ValueError, match="0 rows"):
        T.i1_analysis(f)


# ----- I2 -----

def _i2_frames():
    bounds = np.linspace(0.0, 0.04, 5)                       # e at 0.01, 0.02, 0.03
    pts, base = [], []
    for b in bounds:
        est = bool(np.isclose(b, [0.01, 0.02, 0.03]).any())
        pts.append({"instance": "i", "date": "2017-12", "K": 67, "key": "sector", "b_base": 0.02,
                    "bound": b, "estimator": est, "V": 1.0 + b, "B": 1.0 + b,
                    "flag_V_exceeds_B": False, "v_from": "bigm", "b_from": "bigm",
                    "mu_bigm_relax": 1.2, "persp_slope": 1.1, "persp_ok": True, "mu_fixed": 1.0})
        base.append({"instance": "i", "bound": b, "mu": 2.0 - 10 * b, "value": 2 * b - 5 * b * b + 1.0,
                     "slope": 2.0 - 10 * b if b > 0 else np.nan, "within": True, "kink": False,
                     "rel_err": 0.0 if b > 0 else np.nan})
    iv = pd.DataFrame({"instance": "i", "e": [0.01, 0.02, 0.03], "delta": [0.001, 0.002, 0.003],
                       "L": [0.9] * 3, "H": [1.1] * 3, "s": [1.0] * 3, "binding": [True] * 3,
                       "solver_error": [False] * 3})
    return {"i2_points": pd.DataFrame(pts), "i2_intervals": iv, "i2_baseline": pd.DataFrame(base),
            "i2_solves": pd.DataFrame({"status": ["OPTIMAL"] * 10, "work": [1.0] * 10})}


def test_i2_analysis_on_known_frames():
    out, tables = T.i2_analysis(_i2_frames())
    assert out["n_points"] == 5 and out["constraint"] == "sector@0.02"
    e = {r["estimator"]: r for r in out["estimators"]}
    assert e["fixed"]["n_binding"] == 3 and e["fixed"]["median_rel_err"] == pytest.approx(0.0)
    assert e["bigm_relax"]["median_rel_err"] == pytest.approx(0.2)
    assert out["k27_baseline_grid"]["n_binding"] == 4
    # a quadratic value: the centred secant equals the dual exactly at interior points
    assert out["baseline_grid_secant_rel_err"]["n"] == 3
    assert out["baseline_grid_secant_rel_err"]["max"] == pytest.approx(0.0, abs=1e-12)
    assert set(tables) == {"i2_estimators"}


def test_i2_filters_raise_on_zero_rows():
    f = _i2_frames()
    f["i2_points"] = f["i2_points"].assign(estimator=False)
    with pytest.raises(ValueError, match="0 rows|rows"):
        T.i2_analysis(f)
    f = _i2_frames()
    f["i2_baseline"] = f["i2_baseline"].assign(bound=0.0)
    with pytest.raises(ValueError, match="0 rows"):
        T.i2_analysis(f)


# ----- N1 -----

def _n1(arm, V, B, presolve=-1, status="OPTIMAL", root=None, work=1.0, N="250", tight="base",
        f=0.5, rerun=False):
    return {"id": f"{N}_{f}_{tight}_{arm}_{presolve}{'_r' if rerun else ''}", "date": "2017-12",
            "N": N, "f": f, "K": 67, "tightness": tight, "arm": arm, "presolve": presolve,
            "rerun": rerun, "status": status, "V": V, "B": B, "reached_gap": status == "OPTIMAL",
            "root_bound": root if root is not None else 1.01, "work": work, "nodes": 5,
            "runtime": 1.0, "U_raw": V, "cone_effect_rel": 0.0}


def _n1_frames():
    s = []
    for arm, root_on, root_off, w_on, w_off, st_off in (
            ("bigm", 1.001, 1.05, 1.0, 300.0, "WORK_LIMIT"),
            ("perspective", 1.02, 1.02, 2.0, 2.0, "OPTIMAL"),
            ("perspective_rescaled", 1.0005, 1.0006, 0.7, 2.3, "OPTIMAL")):
        s.append(_n1(arm, 1.0, 1.00001, root=root_on, work=w_on))
        s.append(_n1(arm, 1.0, 1.0001 if st_off == "OPTIMAL" else 1.01, presolve=0,
                     status=st_off, root=root_off, work=w_off))
        s.append(_n1(arm, 1.0, 1.00001, root=root_on, work=w_on, N="100"))
    s.append(_n1("bigm", 1.0, 1.00001, root=1.001, work=1.0, rerun=True))
    rel = pd.DataFrame([{"date": "2017-12", "N": N, "f": 0.5, "K": 67, "tightness": "base",
                         "bigm": 1.06, "perspective": 1.0014, "perspective_ok": True,
                         "perspective_fail_reason": None} for N in ("250", "100")])
    return {"n1_solves": pd.DataFrame(s), "n1_relax": rel}


def test_n1_analysis_on_known_frames():
    out, tables = T.n1_analysis(_n1_frames())
    assert out["n_solves"] == 9
    assert out["k22"]["n_fail"] == 0 and out["k24"]["violations"] == 0
    assert out["k25"]["n"] == 1 and out["k25"]["identical"] == 1
    assert out["presolve_off"]["bigm"]["censored"] == 1
    assert set(tables) == {"n1_table", "n1_relax", "k22_pairs"}


def test_n1_presolve_like_for_like_at_N250():
    """Item 7: per arm at N = 250, presolve on and off: root gap (median, range), median Work,
    censored count; beside the median plain-relaxation gaps at N = 250."""
    out, _ = T.n1_analysis(_n1_frames())
    p = out["presolve_N250"]
    assert set(p["arms"]) == {"bigm", "perspective", "perspective_rescaled"}
    on, off = p["arms"]["bigm"]["on"], p["arms"]["bigm"]["off"]
    assert on["n"] == 1 and on["root_gap"]["median"] == pytest.approx(0.001)
    assert off["root_gap"]["max"] == pytest.approx(0.05) and off["work_median"] == pytest.approx(300.0)
    assert on["censored"] == 0 and off["censored"] == 1
    assert p["plain_relaxation_gap"]["bigm"]["median"] == pytest.approx(0.06)
    assert p["plain_relaxation_gap"]["perspective"]["median"] == pytest.approx(0.0014)


def test_n1_filters_raise_on_zero_rows():
    f = _n1_frames()
    f["n1_solves"] = f["n1_solves"][f["n1_solves"]["presolve"] == -1]
    with pytest.raises(ValueError, match="0 rows"):
        T.n1_analysis(f)


# ----- N2 and K26 -----

def _n2_frames():
    m = pd.DataFrame([{**_n1(a, 1.0, 1.00005), "s_obj": s, "gap_eff": 5e-5}
                      for a in ("bigm", "perspective_rescaled") for s in (1.0, 1e4)])
    cv = pd.DataFrame({"solver": ["reference", "CLARABEL", "SCS"], "normalize": [True] * 3,
                       "scaled": [True] * 3, "ok": [True] * 3, "status": ["optimal"] * 3,
                       "A_rel_err": [0.0, 1e-9, 1e-5], "w_l1_rel_err": [0.0, 1e-8, 1e-4],
                       "max_binding_dual_rel_err": [0.0, 1e-7, 1e-3]})
    return {"n2_miqp": m, "n2_convex": cv}


def test_n2_analysis_on_known_frames():
    out, tables = T.n2_analysis(_n2_frames())
    assert out["miqp"]["n"] == 4 and out["miqp"]["n_pairs"] == 2
    assert out["miqp"]["incumbent_beats_other_bound"] == 0
    assert set(out["convex"]) == {"CLARABEL/norm=True/scaled=True", "SCS/norm=True/scaled=True"}
    assert out["convex"]["SCS/norm=True/scaled=True"]["A_rel_err"]["max"] == pytest.approx(1e-5)
    assert set(tables) == {"n2_pairs", "n2_convex"}


def test_n2_filters_raise_on_zero_rows():
    f = _n2_frames()
    f["n2_convex"] = f["n2_convex"][f["n2_convex"]["solver"] == "reference"]
    with pytest.raises(ValueError, match="0 rows"):
        T.n2_analysis(f)


def test_k26_counts():
    df = pd.DataFrame({"V": [1.0, np.nan, 1.0], "polished_violations": ["{}", "V undefined", '{"gross": 1e-8}'],
                       "incumbent_verdict": ["{}", "no incumbent", '{"dollar": 2e-6}']})
    k = T.k26({"i1_solves": df})["i1_solves"]
    assert k == {"n": 3, "n_V_defined": 2, "polished_violations": 1, "raw_incumbent_flagged": 1,
                 "raw_incumbent_rows": {"dollar": 1}}


# ----- JSON writer (L4) -----

def test_json_writer_keeps_bools_and_ints():
    s = T.dumps({"b": np.bool_(True), "i": np.int64(3), "x": np.float64(0.5), "l": [np.int32(1)]})
    d = json.loads(s)
    assert d["b"] is True and d["i"] == 3 and isinstance(d["i"], int)
    assert isinstance(d["x"], float) and d["l"] == [1] and isinstance(d["l"][0], int)


# ----- K29c verdict (M4) and K29b coverage (L3) -----

def test_k29c_verdict_fails_on_unchecked_points():
    toys = pd.DataFrame({"kind": ["central"] * 9 + ["unchecked"], "pass": [True] * 9 + [None]})
    k8 = pd.DataFrame({"gated": [True], "pass": [True]})
    v = run_k29c.verdict(toys, k8, {"relaxations": 1000, "failed": 0})
    assert not v["pass"] and v["toy_unchecked"] == 1
    ok = run_k29c.verdict(toys.iloc[:9], k8, {"relaxations": 1000, "failed": 0})
    assert ok["pass"] and ok["toy_unchecked"] == 0


def test_k29b_ids_must_occur_among_the_tasks():
    tasks = [{"instance": "2009-03_N250_f0.25_K47"}, {"instance": "2009-03_N250_f0.5_K94"}]
    run_i1.check_k29b_coverage({"2009-03_N250_f0.25_K47"}, tasks)
    with pytest.raises(ValueError, match="2009-03_N250_f0.75_K141"):
        run_i1.check_k29b_coverage({"2009-03_N250_f0.25_K47", "2009-03_N250_f0.75_K141"}, tasks)


def test_k22_and_n2_pair_filters_raise_when_every_pair_is_undefined():
    """CHECK S3B round 1 (results/checks/S3B_20261021T030756Z.md): the defined-pair filters of
    n1_analysis (K22) and n2_analysis (N2(a)) must raise on zero rows; N2 reports n_undefined."""
    f = _n1_frames()
    f["n1_solves"] = f["n1_solves"].assign(V=np.nan)
    with pytest.raises(ValueError, match="0 rows"):
        T.n1_analysis(f)
    f = _n2_frames()
    f["n2_miqp"] = f["n2_miqp"].assign(V=np.nan)
    with pytest.raises(ValueError, match="0 rows"):
        T.n2_analysis(f)
    out, _ = T.n2_analysis(_n2_frames())
    assert out["miqp"]["n_undefined"] == 0
