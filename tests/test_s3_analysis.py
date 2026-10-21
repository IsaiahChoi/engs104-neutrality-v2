"""S3 analysis (src/analysis/s3.py; RUNBOOK S3 step 3, DESIGN §7, CHECKS INT) on constructed frames
whose answers are known: estimator errors over binding cases with n, interval containment, the
non-binding breakdown, exclusions, the combined-certification checks (K23), formulation agreement
over every arm pair (K22), plain-relaxation tightness (K24), determinism (K25), root gaps against
the best known value, the baseline's envelope check (K27), K29b's cross-scale rule, and N2's
cross-formulation disagreements.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analysis import s3 as A


def _est(**over):
    base = {"id": "c1", "instance": "2017-12_N250_f0.5_K67", "date": "2017-12", "f": 0.5, "K": 67,
            "key": "sector", "b": 0.02, "rel_delta": 0.10, "delta": 0.002, "V": 1.0e-3, "B": 1.0e-3,
            "L": 0.9e-3, "H": 1.1e-3, "s": 1.0e-3, "binding": True, "solver_error": False,
            "mu_bigm_relax": 1.2e-3, "persp_slope": 1.05e-3, "persp_ok": True, "persp_kink": False,
            "mu_fixed": 0.5e-3, "mu_persp_raw": 1.05e-3, "persp_raw_usable": True,
            "mu_persp_raw_unusable": np.nan}
    base.update(over)
    return base


def test_estimator_long_errors_and_containment():
    long = A.i1_long(pd.DataFrame([_est()]))
    assert set(long["estimator"]) == {"bigm_relax", "perspective", "fixed"}
    r = long.set_index("estimator")
    assert r.loc["bigm_relax", "rel_err"] == pytest.approx(0.2)
    assert r.loc["perspective", "rel_err"] == pytest.approx(0.05)
    assert r.loc["fixed", "rel_err"] == pytest.approx(0.5)
    assert not r.loc["bigm_relax", "in_interval"] and r.loc["perspective", "in_interval"]
    assert not r.loc["fixed", "in_interval"]


def test_error_summary_counts_n_and_excludes_failed_perspective():
    df = pd.DataFrame([_est(id="a"), _est(id="b", persp_ok=False, persp_slope=np.nan),
                       _est(id="c", binding=False, L=-1e-9, s=0.0, mu_bigm_relax=0.0,
                            persp_slope=1e-14, mu_fixed=0.0)])
    s = A.error_summary(A.i1_long(df), by=[]).set_index("estimator")
    assert s.loc["bigm_relax", "n_binding"] == 2 and s.loc["perspective", "n_binding"] == 1
    assert s.loc["perspective", "n_excluded"] == 1
    assert s.loc["fixed", "median_rel_err"] == pytest.approx(0.5)
    assert s.loc["bigm_relax", "n_in_interval"] == 0 and s.loc["perspective", "n_in_interval"] == 1


def test_nonbinding_breakdown_by_zero_pattern():
    """Zero means |μ̂|·b/|V| < 1e-4 (the bindingness scale of DESIGN §6)."""
    rows = [_est(id="z0", binding=False, L=-1e-9, s=0.0, mu_bigm_relax=0.0, persp_slope=1e-12, mu_fixed=0.0),
            _est(id="z1", binding=False, L=-1e-9, s=0.0, mu_bigm_relax=1e-3, persp_slope=1e-12, mu_fixed=0.0),
            _est(id="b", binding=True)]
    nb = A.nonbinding_breakdown(pd.DataFrame(rows))
    assert nb.set_index("pattern")["n"].to_dict() == {
        "bigm_relax=0, perspective=0, fixed=0": 1, "bigm_relax≠0, perspective=0, fixed=0": 1}


def test_k23_checks():
    pts = pd.DataFrame({"V": [1.0, 1.0], "B": [1.0 + 1e-7, 1.0], "flag_V_exceeds_B": [False, False]})
    est = pd.DataFrame([_est(), _est(id="x", L=np.nan, H=np.nan, V=np.nan)])
    k = A.k23(est, pts)
    assert k["n_cases"] == 2 and k["n_excluded"] == 1 and k["n_H_negative"] == 0
    assert k["n_V_exceeds_B"] == 0 and k["violations"] == 0
    bad = pts.copy()
    bad.loc[1, "V"] = 1.0 + 2e-6
    assert A.k23(est, bad)["violations"] == 1                    # recomputed, not read from the flag
    assert A.k23(pd.DataFrame([_est(H=-1e-6, L=-2e-6)]), pts)["violations"] == 1


def _n1(arm, V, B, inst="i", presolve=-1, status="OPTIMAL", root=None, rerun=False, work=1.0, nodes=10):
    return {"id": f"{inst}_{arm}_{presolve}{'_r' if rerun else ''}", "date": "2017-12", "N": 250, "f": 0.5,
            "K": 67, "tightness": "base", "arm": arm, "presolve": presolve, "rerun": rerun,
            "status": status, "V": V, "B": B, "reached_gap": status == "OPTIMAL",
            "root_bound": root if root is not None else B * 1.01, "work": work, "nodes": nodes,
            "runtime": 1.0, "U_raw": V, "cone_effect_rel": 0.0}


def test_k22_every_arm_pair_any_status():
    s = pd.DataFrame([_n1("bigm", 1.0, 1.0001), _n1("perspective", 1.00005, 1.0002, status="WORK_LIMIT"),
                      _n1("perspective_rescaled", np.nan, np.nan)])
    p = A.k22_pairs(s)
    assert len(p) == 3 and int(p["undefined"].sum()) == 2
    d = p[~p["undefined"]].iloc[0]
    assert bool(d["pass"]) and not bool(d["both_reached_gap"])
    assert d["abs_dV"] == pytest.approx(5e-5)
    assert d["allowed"] == pytest.approx(max(1.0002 + 1e-6 * 1.00005 - 1.00005, 1.0001 + 1e-6 - 1.0))
    bad = pd.DataFrame([_n1("bigm", 1.0, 1.0), _n1("perspective", 1.01, 1.02)])
    assert not bool(A.k22_pairs(bad)["pass"].iloc[0])


def test_k24_plain_relaxations():
    rel = pd.DataFrame({"id": ["a", "b", "c"], "bigm": [2.0, 2.0, 2.0], "perspective": [1.5, 2.0 + 1e-9, 2.1],
                        "perspective_ok": [True, True, False], "perspective_fail_reason": [None, None, "gap"],
                        "V_best": [1.0, 1.0, 1.0]})
    k = A.k24(rel)
    assert k["n"] == 3 and k["n_failed"] == 1 and k["violations"] == 0
    rel.loc[1, "perspective"] = 2.0 + 1e-7
    assert A.k24(rel)["violations"] == 1


def test_k25_reruns_identical():
    s = pd.DataFrame([_n1("bigm", 1.0, 1.0001), _n1("bigm", 1.0, 1.0001, rerun=True)])
    k = A.k25(s)
    assert k["n"] == 1 and k["identical"] == 1
    s.loc[1, "work"] = 1.0 + 1e-12
    assert A.k25(s)["identical"] == 0


def test_root_gaps_against_best_known():
    s = pd.DataFrame([_n1("bigm", 1.0, 1.0001, root=1.05), _n1("perspective_rescaled", 1.0002, 1.0003, root=1.01)])
    g = A.n1_table(s).set_index("arm")
    assert g.loc["bigm", "V_best"] == pytest.approx(1.0002)
    assert g.loc["bigm", "root_gap"] == pytest.approx((1.05 - 1.0002) / 1.0002)
    assert g.loc["perspective_rescaled", "root_gap"] == pytest.approx((1.01 - 1.0002) / 1.0002)
    assert not g["censored"].any()


def test_k27_baseline_envelope():
    b = pd.DataFrame({"mu": [1e-3, 0.0], "b": [0.02, 0.02], "value": [1e-3, 1e-3], "rel_err": [0.004, np.nan],
                      "within": [True, False], "kink": [True, False], "slope": [1.004e-3, 0.0],
                      "secant": [0.9e-3, 0.0]})
    k = A.k27(b)
    assert k["n_binding"] == 1 and k["n_within"] == 1 and k["n_flagged"] == 1 and k["violations"] == 0
    assert k["secant_rel_err_median"] == pytest.approx(1e-4 / 0.9e-3)


def test_k29b_rule():
    e = pd.DataFrame([_est(persp_slope=1e-3, persp_slope_k29b=1e-3 * (1 + 5e-6), persp_noise_central=1e-12,
                           persp_ok_k29b=True, k29b_scale=10.0),
                      _est(id="q", persp_slope=1e-3, persp_slope_k29b=1e-3 * (1 + 2e-5), persp_noise_central=1e-12,
                           persp_ok_k29b=True, k29b_scale=10.0),
                      _est(id="n", k29b_scale=np.nan, persp_slope_k29b=np.nan, persp_ok_k29b=False,
                           persp_noise_central=1e-12)])
    k = A.k29b(e)
    assert k["n"] == 2 and k["misses"] == 1
    assert k["max_rel_diff"] == pytest.approx(2e-5, rel=1e-4)


def test_n2_cross_formulation():
    m = pd.DataFrame([{**_n1("bigm", 1.0, 1.00005), "s_obj": 1.0},
                      {**_n1("perspective", 1.001, 1.0015), "s_obj": 1.0}])     # its own claimed gap 5e-4 < ΔV = 1e-3
    r = A.n2_disagreements(m).iloc[0]
    assert bool(r["incumbent_beats_other_bound"]) and bool(r["beyond_claimed_gap"])


def test_n2_disagreement_direction():
    """Which arm's V lies above which arm's B_eff (Table III counts by direction)."""
    m = pd.DataFrame([{**_n1("bigm", 1.0002, 1.00025), "s_obj": 1.0},
                      {**_n1("perspective_rescaled", 1.0, 1.0001), "s_obj": 1.0}])
    r = A.n2_disagreements(m).iloc[0]
    assert r["arm_i"] == "bigm" and bool(r["i_beats_j"]) and not bool(r["j_beats_i"])
    assert bool(r["incumbent_beats_other_bound"])


def test_nan_in_a_gating_flag_raises():
    """Review M3: a NaN in binding / persp_ok / within / reached_gap is an error, never True."""
    with pytest.raises(ValueError, match="binding"):
        A.i1_long(pd.DataFrame([_est(binding=np.nan)]))
    b = pd.DataFrame({"mu": [1e-3], "b": [0.02], "value": [1e-3], "rel_err": [0.0], "within": [np.nan],
                      "kink": [False], "slope": [1e-3], "secant": [1e-3]})
    with pytest.raises(ValueError, match="within"):
        A.k27(b)


def test_k22_flags_a_defined_V_with_undefined_B():
    """Review M4: a finite V with a non-finite B is not an "undefined V" pair to skip; it is
    reported separately (CHECKS K22 skips only undefined V)."""
    s = pd.DataFrame([_n1("bigm", 1.0, np.nan), _n1("perspective", 1.0, 1.0001)])
    p = A.k22_pairs(s)
    assert p["undefined_reason"].iloc[0] == "B undefined"


def test_nonbinding_breakdown_by_delta():
    rows = [_est(id="a", rel_delta=0.05, binding=False, L=-1e-9, s=0.0, mu_bigm_relax=0.0,
                 persp_slope=0.0, mu_fixed=0.0), _est(id="b")]
    nb = A.nonbinding_breakdown(pd.DataFrame(rows), by="rel_delta")
    assert nb.to_dict("records") == [{"rel_delta": 0.05, "pattern": "bigm_relax=0, perspective=0, fixed=0", "n": 1}]
