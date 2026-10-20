"""The K29c gate runner (experiments/run_k29c.py; S3 step 0e): its grid, the CHECKS K29c tolerance
rules applied to toy stencils and to the K8 cross-scale comparison, and the failure cap. The
records are built from the toy's closed forms, so the expected verdict of each rule is known.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from experiments.run_k29c import (FAIL_CAP, K8_GATED_FACTORS, k8_pairs, toy_check, toy_grid,
                                  verdict)
from src.opt.toy import Toy

T = Toy(a=1.0, lam=1.0, d=10.0, ell=0.02, u=0.08)        # w° = 0.05, U* = 0.025


def rec(T: Toy, b: float, slope=None, fwd=None, bwd=None, ok=True, rel=1e-3):
    """A relaxation_slope-like record whose slopes are the closed form unless given."""
    left, right = _sides(T, b)
    d = rel * b
    return {"ok": ok, "delta": d, "V": T.relaxation_value(b, "perspective"),
            "slope": (left + right) / 2 if slope is None else slope,
            "forward": right if fwd is None else fwd, "backward": left if bwd is None else bwd,
            "points": [{"ok": ok}] * 5}


def _sides(T, b):
    from experiments.run_k29c import toy_one_sided
    return toy_one_sided(T, b)


def test_grid_has_every_positive_grid_point_and_both_kinks():
    g = toy_grid(T, 1.25 * T.u, 41)                       # ℓ and w° lie on this grid
    assert len(g) == 40 and np.all(g > 0) and np.all(np.diff(g) > 0)
    assert T.ell in g and T.w_opt in g
    T2 = Toy(a=1.0, lam=1.0, d=10.0, ell=0.0213, u=0.08)   # ℓ off the grid
    g2 = toy_grid(T2, 1.25 * T2.u, 41)
    assert len(g2) == 41 and T2.ell in g2 and T2.w_opt in g2 and np.all(g2 > 0)
    assert set(np.linspace(0, 0.1, 41)[1:]) <= set(g2)


def test_interior_point_central_rule():
    b = 0.03
    r = toy_check(T, b, rec(T, b))
    assert r["kind"] == "central" and r["pass"]
    U = T.value(T.w_opt)
    N = 1e-9 * max(abs(T.relaxation_value(b, "perspective")), U) / (1e-3 * b)
    s = T.slopes(b)["perspective"]
    assert r["tol"] == pytest.approx(1e-6 * max(abs(s), 0.01 * T.a) + N, rel=1e-12)
    bad = toy_check(T, b, rec(T, b, slope=s + 1.01 * r["tol"]))
    assert not bad["pass"] and bad["err"] > bad["tol"]


def test_flat_point_uses_the_0p01a_floor():
    b = 0.07                                              # above w°: slope 0
    r = toy_check(T, b, rec(T, b, slope=0.9e-6 * 0.01 * T.a))
    assert r["kind"] == "central" and r["pass"]


def test_near_kink_points_use_the_side_away_from_it():
    d = 1e-3 * T.ell
    above = toy_check(T, T.ell + 1.5 * d, rec(T, T.ell + 1.5 * d, slope=123.0))
    assert above["kind"] == "forward" and above["pass"]          # the central slope is not read
    below = toy_check(T, T.ell - 1.5 * d, rec(T, T.ell - 1.5 * d, slope=123.0))
    assert below["kind"] == "backward" and below["pass"]
    bad = toy_check(T, T.ell + 1.5 * d, rec(T, T.ell + 1.5 * d, fwd=T.a - T.lam * T.d * T.ell))
    assert not bad["pass"]                                       # the left piece's slope on the right


def test_at_a_kink_both_sides_are_checked_with_4N():
    r = toy_check(T, T.ell, rec(T, T.ell))
    assert r["kind"] == "both" and r["pass"]
    U = T.value(T.w_opt)
    N = 1e-9 * max(abs(T.relaxation_value(T.ell, "perspective")), U) / (1e-3 * T.ell)
    right = T.a - 2 * T.lam * T.d * T.ell
    assert r["tol_forward"] == pytest.approx(1e-6 * max(abs(right), 0.01 * T.a) + 4 * N, rel=1e-12)
    wrong = toy_check(T, T.ell, rec(T, T.ell, bwd=right))       # the right slope on the left side
    assert not wrong["pass"]
    assert toy_check(T, T.w_opt, rec(T, T.w_opt))["kind"] == "both"


def test_failed_stencil_is_excluded_and_counted():
    r = toy_check(T, 0.03, rec(T, 0.03, ok=False))
    assert r["kind"] == "failed" and r["pass"] is None


def _k8_frame(perturb=0.0, fail_at=None, slope=2e-3, e_small=False):
    rows = []
    s_obj = 1e4
    for s in (1.0, 1e2, 1e4, 1e5, 1e6):
        for key, sl in (("sector", slope), ("beta", 1e-12)):
            b, V, d = 0.02, 1.0e-3, 2e-5
            ok = not (fail_at == (key, s))
            x = sl * (1 + (perturb if s == 1e6 else 0.0))
            rows.append({"month": "2017-12", "key": key, "s": s, "s_obj": s_obj, "ok": ok,
                         "slope": x if ok else np.nan, "V": V, "b": b, "delta": d,
                         "raw_dual": sl, "fail_reason": None if ok else "gap"})
    return pd.DataFrame(rows)


def test_k8_pairs_gate_only_bound_constraints_at_the_three_scales():
    assert K8_GATED_FACTORS == (1, 10, 100)
    p = k8_pairs(_k8_frame(), s_obj=1e4)
    g = p[p["gated"]]
    assert set(g["key"]) == {"sector"} and len(g) == 3          # beta's elasticity is ~2e-8
    assert g["pass"].all()
    N = 1e-9 * 1e-3 / 2e-5
    assert g["tol"].iloc[0] == pytest.approx(1e-6 * 2e-3 + 2 * N, rel=1e-12)
    diag = p[~p["gated"]]
    assert len(diag) > 0 and diag["key"].isin({"sector", "beta"}).all()


def test_k8_pairs_fail_beyond_tolerance_and_list_failed_stencils():
    tol = 1e-6 * 2e-3 + 2 * 1e-9 * 1e-3 / 2e-5
    p = k8_pairs(_k8_frame(perturb=1.5 * tol / 2e-3), s_obj=1e4)
    g = p[p["gated"]]
    assert (~g["pass"]).sum() == 2                               # (1e4, 1e6) and (1e5, 1e6)
    p2 = k8_pairs(_k8_frame(fail_at=("sector", 1e5)), s_obj=1e4)
    g2 = p2[p2["gated"]]
    assert len(g2) == 1 and g2["pass"].all()                      # pairs with a failed stencil skipped


def test_verdict_failure_cap_and_misses():
    toys = pd.DataFrame({"kind": ["central"] * 99 + ["failed"], "pass": [True] * 99 + [None]})
    k8 = pd.DataFrame({"gated": [True], "pass": [True]})
    counts = {"relaxations": 1000, "failed": 10}
    v = verdict(toys, k8, counts)
    assert FAIL_CAP == 0.01 and v["pass"]
    assert not verdict(toys, k8, {"relaxations": 1000, "failed": 11})["pass"]
    toys2 = toys.copy()
    toys2.loc[0, "pass"] = False
    assert not verdict(toys2, k8, counts)["pass"]
    k82 = pd.DataFrame({"gated": [True, False], "pass": [False, True]})
    assert not verdict(toys, k82, counts)["pass"]
    assert verdict(toys, pd.DataFrame({"gated": [False], "pass": [False]}), counts)["pass"]
