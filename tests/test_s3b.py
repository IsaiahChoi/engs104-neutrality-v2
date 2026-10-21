"""S3b items 3 and 5 (Isaiah's GATE I note), tests first: src/analysis/s3b.py (pure helpers) and
experiments/run_s3b.py (the logged recomputation).

Item 3, support stability (a test of A8): the support of V's incumbent (|w| > 1e-6, sign
included) and the fixed-integer QP's active set (rows tight within 1e-9, DESIGN §6's QP
tolerance) at b − δ, b and b + δ; classes P1 (both unchanged), P2 (support unchanged, active set
changed), P3 (support changed). z is rebuilt exactly from V's polished weights (ℓ > 0: a held
name has |w| ≥ ℓ, any other has w = 0), and the fixed-integer QP is re-solved by dual simplex at
that z; it must reproduce the stored V.

Item 5, hedged legs: in the perspective relaxation, a name with both legs above 1e-6; the
prediction |w⁺ − w⁻| < ℓ and z⁺ + z⁻ > |w⁺ − w⁻|/ℓ is evaluated per name.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import experiments.run_i1 as i1
import experiments.run_s3b as R
import experiments.s3 as s3
from experiments.designs import config
from src.analysis import s3b as S
from src.opt.continuous import Mandate
from src.opt.integer import PMI

SMALL = {"date": "2017-12", "N": 30, "f": 0.5}


# ----- pure helpers -----

def test_support_signature_has_sign_and_threshold():
    w = np.array([0.0, 3e-3, -2.5e-3, 5e-7, -5e-7])
    assert S.support_signature(w) == "1+;2-"
    assert S.support_signature(-w) == "1-;2+"
    assert S.support_signature(np.zeros(3)) == ""


def test_z_from_polished_weights():
    zp, zm = S.z_from_weights(np.array([0.0, 2.5e-3, -0.06, 0.0]), ell=2.5e-3)
    assert list(zp) == [0, 1, 0, 0] and list(zm) == [0, 0, 1, 0]
    with pytest.raises(ValueError, match="neither held"):
        S.z_from_weights(np.array([1e-4, 0.0]), ell=2.5e-3)


def _fake_model():
    """Two factors (mkt, one style), two sectors, four names: rows whose tightness is known."""
    B = np.array([[1.0, 0.5], [1.0, -0.5], [1.0, 0.0], [1.0, 0.0]])
    S_ = np.array([[1, 0], [1, 0], [0, 1], [0, 1]], float)
    md = SimpleNamespace(dollar=0.02, beta=0.05, style=0.1, sector=0.02, gross=2.0)
    bounds = {"dollar": 0.02, "beta": 0.05, "gross": 0.13, "style": np.array([0.1]),
              "sector": np.array([0.02, 0.02])}
    return SimpleNamespace(B=B, S=S_, mandate=md, bounds=bounds, mkt=0, style_idx=[1],
                           ub=np.array([0.06, 0.06, 0.03, 0.06]),
                           holdable=np.array([True, True, True, True]), ell=0.0025)


def test_fixed_active_set_rows():
    M = _fake_model()
    w = np.array([0.06, -0.04, 0.03, 0.0])     # Σw = 0.05 (> dollar 0.02, tight not required here)
    M.bounds["dollar"] = 0.05                  # dollar upper tight
    M.bounds["gross"] = 0.13                   # gross tight
    act = S.fixed_active_set(M, w, tol=1e-9)
    assert "dollar:upper" in act and "dollar:lower" not in act
    assert "gross:upper" in act
    assert "cap:0" in act and "cap:2" in act and "cap:1" not in act and "min:1" not in act
    # beta = Σw = 0.05: tight upper; style y = 0.03 + 0.02 = 0.05 < 0.1: slack
    assert "beta:upper" in act and not any(a.startswith("style") for a in act)
    # sector 0: 0.06 − 0.04 = 0.02 tight upper; sector 1: 0.03 > 0.02 is infeasible, still "tight"
    assert "sector:upper:0" in act
    w2 = np.array([0.0025, 0.0, 0.0, 0.0])
    assert "min:0" in S.fixed_active_set(M, w2, tol=1e-9)


def test_support_class():
    assert S.support_class(["a", "a", "a"], [frozenset({"x"})] * 3) == "P1"
    assert S.support_class(["a", "a", "a"], [frozenset({"x"}), frozenset({"x"}), frozenset()]) == "P2"
    assert S.support_class(["a", "b", "a"], [frozenset({"x"})] * 3) == "P3"


def test_hedged_names_and_prediction():
    wp = np.array([1e-3, 2e-3, 0.0, 5e-3])
    wm = np.array([5e-4, 0.0, 1e-3, 1e-3])
    zp = np.array([0.4, 0.8, 0.0, 0.9])
    zm = np.array([0.2, 0.0, 0.4, 0.05])
    h = S.hedged_names(wp, wm, zp, zm, ell=2.5e-3)
    assert list(h["i"]) == [0, 3]
    r0 = h.set_index("i").loc[0]
    assert r0["net"] == pytest.approx(5e-4) and r0["min_leg"] == pytest.approx(5e-4)
    assert bool(r0["net_below_ell"]) and bool(r0["zeta_above_net_over_ell"])     # 0.6 > 0.2
    r3 = h.set_index("i").loc[3]
    assert not bool(r3["net_below_ell"])                                          # |4e-3| ≥ ℓ
    assert bool(r3["zeta_above_net_over_ell"]) is False                           # 0.95 < 1.6
    assert not bool(r3["prediction_holds"]) and bool(r0["prediction_holds"])


def test_spearman():
    assert S.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert S.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


# ----- the runner's tasks on a small instance -----

@pytest.fixture(scope="module")
def i1_small():
    inst = s3.instance(SMALL["date"], SMALL["N"], SMALL["f"])
    cfg = config("integer")
    t = i1.make_task(cfg, inst, {"key": "sector", "b": 0.02}, rel_delta=0.10, f=SMALL["f"])
    return t, i1.i1_task(t)


def test_support_task_reproduces_stored_V(i1_small):
    t, out = i1_small
    rows = R.support_task({**t, "weights": out["i1_weights"], "points": out["i1_points"]})["s3b_support"]
    assert len(rows) == 3 and set(rows["point"]) == {"minus", "b", "plus"}
    pts = out["i1_points"].set_index("point")
    for _, r in rows.iterrows():
        assert r["V_recomputed"] == pytest.approx(pts.loc[r["point"], "V"], rel=1e-12, abs=0)
        assert r["support"] == S.support_signature(
            out["i1_weights"].query("point == @r.point")["w"].to_numpy())
        assert isinstance(r["active_set"], str)
    b = rows.set_index("point").loc["b"]
    assert b["mu_fixed"] == pytest.approx(pts.loc["b", "mu_fixed"], rel=1e-9, abs=1e-15)


def test_legs_task_n1_matches_plain_relaxation():
    cfg = config("numerics")
    inst = s3.instance(SMALL["date"], SMALL["N"], SMALL["f"])
    import experiments.run_n1 as n1
    t = n1.make_relax_task(cfg, {"date": SMALL["date"], "N": SMALL["N"], "f": SMALL["f"],
                                 "tightness": "base"}, inst)
    out = R.legs_task({**t, "source": "n1", "ell": inst.kwargs["ell"]})
    legs, names = out["s3b_legs"].iloc[0], out["s3b_leg_names"]
    ref = n1.relax_task(t)["n1_relax"].iloc[0]
    assert legs["value"] == ref["perspective"] and bool(legs["ok"]) == bool(ref["perspective_ok"])
    assert len(names) == inst.N and {"wp", "wm", "zp", "zm", "d"} <= set(names.columns)
    assert (names["wp"] >= -1e-9).all() and (names["zp"] <= 1 + 1e-9).all()
