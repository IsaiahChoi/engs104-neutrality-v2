"""tools/s3b_analysis.py (S3b items 2–6) on synthetic frames whose answers are known, tests first
(the lesson of review M2: no untested glue between the runs and the reported numbers)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import tools.s3b_analysis as T


def _i1est():
    rows = []
    for cid, d, f, binding, s, mf, inst in (
            ("a10", 0.10, 0.25, True, 1e-3, 1e-3, "i1"), ("b10", 0.10, 0.5, True, 1e-3, 1.002e-3, "i2"),
            ("c10", 0.10, 0.75, True, 1e-3, 1.3e-3, "i3"), ("n10", 0.10, 0.25, False, 0.0, 0.0, "i1"),
            ("a05", 0.05, 0.25, True, 1e-3, 1e-3, "i1")):
        rows.append({"id": cid, "instance": inst, "date": "2017-12", "f": f, "K": 10,
                     "key": "sector" if cid != "n10" else "style", "b": 0.02, "rel_delta": d,
                     "V": 1.0, "B": 1.0, "L": s - 1e-9 if binding else -1e-9, "H": s + 1e-9,
                     "s": s, "binding": binding, "mu_bigm_relax": 1.5 * s, "persp_slope": 1.1 * s,
                     "persp_ok": True, "mu_fixed": mf, "U_bigm_relax": 1.05 + 0.01 * f,
                     "persp_V": 1.001 + 0.001 * f})
    return pd.DataFrame(rows)


def _support():
    rows = []
    spec = {"a10": (["1+"] * 3, ["x"] * 3), "b10": (["1+"] * 3, ["x", "x;y", "x"]),
            "c10": (["1+", "1+;2-", "1+"], ["x"] * 3), "n10": (["1+"] * 3, ["x"] * 3),
            "a05": (["1+"] * 3, ["x"] * 3)}
    for cid, (sups, acts) in spec.items():
        for p, s, a in zip(("minus", "b", "plus"), sups, acts):
            rows.append({"id": cid, "point": p, "support": s, "support_recomputed": s,
                         "active_set": a, "V_rel_diff": 0.0, "w_max_abs_diff": 0.0,
                         "mu_fixed": 1.0, "mu_fixed_stored": 1.0})
    return pd.DataFrame(rows)


def test_item3_classes_predictions_and_spearman():
    rec, c = T.item3(_support(), _i1est())
    cls = c.set_index("id")["class"].to_dict()
    assert cls == {"a10": "P1", "b10": "P2", "c10": "P3", "n10": "P1", "a05": "P1"}
    p = rec["predictions"]
    assert p["P1"]["n"] == 2 and p["P1"]["misses"] == []                     # a10, a05: error 0
    assert p["P2"]["n"] == 1 and p["P2"]["max_err"] == pytest.approx(2e-3) and p["P2"]["misses"] == []
    assert p["P3"]["n"] == 1
    assert rec["n_binding"] == 4 and rec["nonbinding"]["n"] == 1
    assert rec["spearman_delta10"]["n"] == 3
    assert rec["counts_binding_by_delta"] == {"d0.05": {"P1": 1}, "d0.1": {"P1": 1, "P2": 1, "P3": 1}}


def test_item3_p1_miss_is_reported_not_raised():
    est = _i1est()
    est.loc[est["id"] == "a10", "mu_fixed"] = 1.01e-3                        # error 1e-2 in a P1 case
    rec, _ = T.item3(_support(), est)
    assert rec["predictions"]["P1"]["misses"] == ["a10"]


def test_item4_grid_counts():
    b = np.linspace(0, 0.04, 5)
    V = np.array([0.0, 0.1, 0.5, 0.6, 0.7])                                 # k=1: 0 + 0.5 > 0.2
    pts = pd.DataFrame({"instance": "x", "id": [f"p{k}" for k in range(5)], "bound": b, "V": V, "B": V})
    w = []
    for k in range(5):
        w += [{"id": f"p{k}", "i": 0, "w": 0.01}, {"id": f"p{k}", "i": 1, "w": 0.01 if k >= 2 else 0.0}]
    out, tri = T.item4(pts, pd.DataFrame(w))
    assert out["x"]["certified_nonconcave"] == 1 and out["x"]["uncertified_nonconcave"] == 1
    assert out["x"]["support_changes"] == 1 and out["x"]["neighbour_pairs"] == 4
    assert len(tri) == 3


def test_item4_raises_when_a_point_has_no_weights():
    """S4 step 0b: a grid point with no stored weights must raise, not give an empty support."""
    pts = pd.DataFrame({"instance": "x", "id": ["p0", "p1", "p2"], "bound": [0.0, 0.01, 0.02],
                        "V": [0.0, 0.1, 0.2], "B": [0.0, 0.1, 0.2]})
    w = pd.DataFrame([{"id": "p0", "i": 0, "w": 0.01}, {"id": "p2", "i": 0, "w": 0.01}])
    with pytest.raises(ValueError, match="p1"):
        T.item4(pts, w)


def test_item5_raises_when_a_relaxation_has_no_names():
    """S4 step 0b: a relaxation with no stored names must raise, not count zero hedged names."""
    legs = pd.DataFrame({"id": ["r", "s"], "source": ["n1", "n1"], "ell": [2.5e-3] * 2,
                         "lam_star": [10.0] * 2, "borrow_monthly": [2.5e-4] * 2, "trade_cost": [5e-4] * 2,
                         "ok": [True] * 2, "value_minus_ref": [0.0] * 2, "n_hedged": [1, 0]})
    names = pd.DataFrame({"id": "r", "i": [0, 1], "wp": [1e-3, 0.0], "wm": [5e-4, 1e-3],
                          "zp": [0.4, 0.0], "zm": [0.2, 0.4], "d": [0.01, 0.02]})
    with pytest.raises(ValueError, match="s"):
        T.item5(legs, names)


def test_item5_hedged_counts():
    legs = pd.DataFrame({"id": ["r"], "source": ["n1"], "ell": [2.5e-3], "lam_star": [10.0],
                         "borrow_monthly": [2.5e-4], "trade_cost": [5e-4], "ok": [True],
                         "value_minus_ref": [0.0], "n_hedged": [1]})
    names = pd.DataFrame({"id": "r", "i": [0, 1], "wp": [1e-3, 0.0], "wm": [5e-4, 1e-3],
                          "zp": [0.4, 0.0], "zm": [0.2, 0.4], "d": [0.01, 0.02]})
    out, H = T.item5(legs, names)
    assert out["hedged_names"] == 1 and out["prediction_holds"] == 1
    assert out["max_min_leg"] == pytest.approx(5e-4)
    assert H["two_lam_d_ell"].iloc[0] == pytest.approx(2 * 10.0 * 0.01 * 2.5e-3)
    assert H["c_plus_2kappa"].iloc[0] == pytest.approx(2.5e-4 + 1e-3)


def test_item2_k29b_ext_against_i1():
    est = _i1est()
    x = est[["id", "instance", "key", "rel_delta"]].copy()
    x = x.assign(persp_slope=est["persp_slope"], persp_slope_k29b=est["persp_slope"] * (1 + 1e-7),
                 persp_noise_central=1e-12, persp_ok=True, persp_ok_k29b=True, k29b_scale=10.0,
                 persp_kink=False, persp_kink_k29b=False)
    out = T.item2(x, est)
    assert out["all"]["n"] == 5 and out["all"]["misses"] == 0
    assert out["binding"]["n"] == 4 and out["slope_equals_i1_bitwise"] == 5
    assert out["delta5_twins"] == 1 and out["delta5_twins_identical_both_scales"] == 1
