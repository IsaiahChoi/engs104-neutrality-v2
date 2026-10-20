"""S2b pilot reruns (experiments/run_pilot_s2b.py) and the Decision 26 active-set classification
(src.opt.sensitivity.active_set): the rules, on constructed data and a small QP.

- P4, three arms (big-M; perspective at default scaling; perspective rescaled, Decision 27(a)):
  the DESIGN §8 agreement criterion for each perspective arm against big-M.
- P6 under combined certification (Decision 27(b)) with every candidate tied at the cutoff
  included (Decision 28).
- Decision 26 reporting: a flagged C1 point is a kink only if the exact active set of the P-RB QP
  differs among b − δ, b and b + δ; otherwise it is a curvature flag.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.opt.certified import effective_bound
from src.opt.continuous import ContinuousProblem, Mandate
from src.opt.sensitivity import ACTIVE_TOL, active_set, active_set_change
from src.risk.factor_model import FACTORS
from tests.test_opt import random_instance

I1_DATES = ["2009-03", "2017-12", "2020-03"]


# ----- Decision 26: the exact active set -----

def _tight_problem():
    B, F, d, S, adv, alpha = random_instance()
    m = Mandate(dollar=0.01, beta=0.02, style=0.05, sector=0.03, gross=1.2, position=0.05,
                liquidity_theta=None)
    return ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS), alpha


def test_active_set_is_the_tight_rows_and_is_complementary():
    """Every inequality row of the QP that holds within 1e-9 (the solve's FeasibilityTol), as
    '<family>:<side>:<i>'; every row with a nonzero dual is in it (complementary slackness), and
    a name at zero has its nonnegativity row in it."""
    assert ACTIVE_TOL == 1e-9
    P, alpha = _tight_problem()
    sol = P.solve(alpha, lam=2.0)
    A = active_set(P, sol)
    for (fam, side), dual in sol.duals.items():
        for i, v in enumerate(np.atleast_1d(dual)):
            if abs(v) > 1e-8:
                assert f"{fam}:{side}:{i}" in A, (fam, side, i, v)
    for i in range(P.N):
        assert (f"nonneg:long:{i}" in A) == (sol.wp[i] <= ACTIVE_TOL)
        assert (f"nonneg:short:{i}" in A) == (sol.wm[i] <= ACTIVE_TOL)
    assert {k.split(":")[0] for k in A} >= {"dollar", "gross", "nonneg", "trade"}


def test_active_set_changes_only_across_an_active_set_change():
    """A tiny move of a binding bound keeps the active set (a curvature point); loosening the
    dollar bound far drops its rows (an active-set change)."""
    P, alpha = _tight_problem()
    A0 = active_set(P, P.solve(alpha, lam=2.0))
    assert {"dollar:upper:0", "dollar:lower:0"} & A0
    P.set_bound("dollar", 0.01 * (1 + 1e-7))
    assert active_set(P, P.solve(alpha, lam=2.0)) == A0
    P.set_bound("dollar", 1.0)
    A1 = active_set(P, P.solve(alpha, lam=2.0))
    assert A1 != A0 and not ({"dollar:upper:0", "dollar:lower:0"} & A1)


def test_active_set_change_summary():
    A0 = frozenset({"dollar:upper:0", "nonneg:long:3", "nonneg:short:3", "trade:up:1"})
    same = active_set_change(A0, A0, A0)
    assert not same["differs"] and same["n_diff_minus"] == 0 and same["n_diff_plus"] == 0
    Am = A0 - {"dollar:upper:0"}
    Ap = (A0 - {"nonneg:long:3"}) | {"sector:lower:2"}
    ch = active_set_change(Am, A0, Ap)
    assert ch["differs"] and ch["changed_minus"] and ch["changed_plus"]
    assert (ch["n_diff_minus"], ch["n_diff_plus"]) == (1, 2)
    assert ch["mandate_rows_changed"] == "dollar:upper:0;sector:lower:2"
    assert ch["n_support_rows_changed"] == 1                        # nonneg rows: names in/out
    only_plus = active_set_change(A0, A0, Ap)
    assert only_plus["differs"] and not only_plus["changed_minus"]


# ----- P6: candidates with ties (Decision 28) -----

def _p2(vals: dict) -> pd.DataFrame:
    rows = []
    for j, ym in enumerate(I1_DATES + ["2008-10"]):
        for alpha in ("mom", "perp"):
            r = {"month": ym, "alpha": alpha}
            r.update({f"e_{k}": (v[j] if j < 3 and alpha == "mom" else 9.0) for k, v in vals.items()})
            rows.append(r)
    return pd.DataFrame(rows)


def _cfg():
    return {"i1": {"dates": I1_DATES}, "p6": {"n_families": 4, "mom_bound": 0.025}}


def test_p6_candidates_include_every_tie_at_the_cutoff():
    from experiments.run_pilot_s2b import p6_candidates_ties
    vals = {"sector": [0.03, 0.01, 0.02], "dollar": [0.04, 0.001, 0.0], "beta": [0, 0, 0],
            "gross": [0, 0, 0], "style": [0, 0.02, 0], "style:SMB": [0, 0, 0],
            "style:Mom": [0, 0.02, 0], "position": [0.5, 0.5, 0.5],
            "liquidity": [0.4, 0.4, 0.4], "sector:2": [0.9, 0.9, 0.9]}
    base = Mandate(dollar=0.02, beta=0.05, style=0.10, sector=0.02, gross=2.0, position=0.06,
                   liquidity_theta=0.05)
    c = p6_candidates_ties(_p2(vals), _cfg(), base)
    assert list(c["candidate"]) == ["sector", "dollar", "beta", "gross", "style", "style:Mom",
                                    "style:SMB", "style:Mom"]
    assert list(c["rank"]) == list(range(8))
    assert list(c["tied_at_cutoff"]) == [False, False, True, True, True, True, True, False]
    assert list(c["b"]) == [0.02, 0.02, 0.05, 2.0, 0.10, 0.10, 0.10, 0.025]
    assert c["source"].iloc[-1].startswith("Mom bound at 0.025")
    assert list(c["is_factor"]) == [False, False, True, False, True, True, True, True]


def test_p6_candidates_without_ties_are_the_top_four():
    from experiments.run_pilot_s2b import p6_candidates_ties
    vals = {"sector": [0.05] * 3, "dollar": [0.04] * 3, "beta": [0.03] * 3, "gross": [0.02] * 3,
            "style": [0.01] * 3}
    base = Mandate(dollar=0.02, beta=0.05, style=0.10, sector=0.02, gross=2.0, position=0.06,
                   liquidity_theta=0.05)
    c = p6_candidates_ties(_p2(vals), _cfg(), base)
    assert list(c["candidate"]) == ["sector", "dollar", "beta", "gross", "style:Mom"]
    assert not c["tied_at_cutoff"].any()


# ----- P4: agreement per perspective arm -----

def _solve(key, arm, V, B):
    return {"key": key, "arm": arm, "V": V, "B": B, "B_eff": effective_bound(B, V)}


def test_p4_agreement_per_perspective_arm_against_bigm():
    from experiments.run_pilot_s2b import p4_arm_agreement
    s = pd.DataFrame([_solve("a", "bigm", 1.0, 1.0001), _solve("a", "perspective", 0.999, 1.004),
                      _solve("a", "perspective_rescaled", 1.0, 1.0001),
                      _solve("b", "bigm", 1.0, 1.0001), _solve("b", "perspective", 0.99, 0.991),
                      _solve("b", "perspective_rescaled", 1.0, 1.00005)])
    ag = p4_arm_agreement(s, ("perspective", "perspective_rescaled")).set_index(["key", "arm"])
    assert len(ag) == 4
    a = ag.loc[("a", "perspective")]
    assert a["abs_diff"] == pytest.approx(0.001) and a["pass"]
    assert a["allowed"] == pytest.approx(effective_bound(1.004, 0.999) - 0.999)
    assert ag.loc[("a", "perspective_rescaled"), "pass"]
    assert not ag.loc[("b", "perspective"), "pass"]                 # recorded, not a stop
    assert ag.loc[("b", "perspective_rescaled"), "abs_diff"] == 0.0


def test_p4_best_known_value_and_shortfall():
    from experiments.run_pilot_s2b import p4_add_best
    s = pd.DataFrame([_solve("a", "bigm", 1.0, 1.0001), _solve("a", "perspective", 0.997, 1.004),
                      _solve("a", "perspective_rescaled", 1.0, 1.0001)])
    out = p4_add_best(s).set_index("arm")
    assert (out["V_best"] == 1.0).all()
    assert out.loc["perspective", "shortfall_rel"] == pytest.approx(0.003)
    assert out.loc["perspective", "gap_vs_best_rel"] == pytest.approx(0.004)
    assert out.loc["perspective", "gap_own_rel"] == pytest.approx((1.004 - 0.997) / 0.997)


# ----- P6: combined intervals -----

def test_p6_intervals_use_the_combined_values_and_bounds():
    from experiments.run_pilot_s2b import p6_intervals_combined
    cands = pd.DataFrame([{"candidate": "sector", "rank": 0, "b": 0.02, "is_factor": False,
                           "median_elasticity_c1": 0.01, "tied_at_cutoff": False}])
    pts = pd.DataFrame([
        {"candidate": "sector", "b": 0.02, "delta": 0.002, "sign": 1, "V": 1.01, "B": 1.0102,
         "V_bigm": 1.01, "B_bigm": 1.0102, "V_perspective": 1.009, "B_perspective": 1.0110,
         "v_from": "bigm", "b_from": "bigm"},
        {"candidate": "sector", "b": 0.02, "delta": 0.002, "sign": -1, "V": 1.0, "B": 1.0001,
         "V_bigm": 0.999, "B_bigm": 1.0001, "V_perspective": 1.0, "B_perspective": 1.003,
         "v_from": "perspective", "b_from": "bigm"}])
    iv = p6_intervals_combined(pts, cands).iloc[0]
    assert iv["L"] == pytest.approx((1.01 - effective_bound(1.0001, 1.0)) / 0.004)
    assert iv["H"] == pytest.approx((effective_bound(1.0102, 1.01) - 1.0) / 0.004)
    assert iv["binding"] == bool(iv["L"] > 0)
    assert iv["L_perspective_only"] == pytest.approx((1.009 - effective_bound(1.003, 1.0)) / 0.004)
    assert iv["L_bigm_only"] == pytest.approx((1.01 - effective_bound(1.0001, 0.999)) / 0.004)
    assert (iv["v_from_plus"], iv["v_from_minus"]) == ("bigm", "perspective")
