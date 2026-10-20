"""S2b (Isaiah's GATE C note, 2026-10-19): the polish at 1e-9 (Decision 24), the rescaled
perspective P-MI and the combined certification for I1/I2 (Decision 27, options; no default
changes before GATE DESIGN).

- Decision 24: V is the fixed-integer QP at the incumbent's z, solved by dual simplex at
  FeasibilityTol = OptimalityTol = 1e-9 (DESIGN §6); the independent checker's 1e-9 verdict on V's
  weights, at the solve's current bounds, is recorded on every solve.
- Decision 27(a): the Gurobi P-MI with weights rescaled by the largest position bound c (w' = w/c;
  rows, bounds and cones transformed; solutions and bounds mapped back; c recorded).
- Decision 27(b): combined certification: both formulations solved; V = the larger polished value,
  B = the smaller final bound, B_eff = max(B, V) + 1e-6·|V|; the fixed-integer dual at the
  incumbent that supplied V; which formulation supplied V and which supplied B is recorded.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import replace as dc_replace

import cvxpy as cp
import numpy as np
import pytest

from src.opt.certified import effective_bound
from src.opt.continuous import SOLVER_OPTS, Mandate
from src.opt.feasibility import pmi_violations
from src.opt.integer import (PMI, POLISH_PARAMS, combine_certification, combined_interval,
                             exact_objective, solve_combined)
from src.opt.toy import Toy, random_toys
from src.risk.factor_model import FACTORS
from tests.test_opt import random_instance
from tests.test_relaxation import R_N, R_SEED, TOYS, toy_pmi

FORMS = ("bigm", "perspective")


def toy_mandate(T: Toy, b: float) -> Mandate:
    return Mandate(dollar=None, beta=None, style=None, sector=None, gross=b, position=T.u,
                   liquidity_theta=None, borrow_annual=0.0, trade_cost=0.0)


def toy_violations(T: Toy, b: float, r, tol: float = 1e-9) -> dict:
    return pmi_violations(r.w, r.zp, r.zm, np.zeros((1, len(FACTORS))), np.ones((1, 1)),
                          toy_mandate(T, b), 1, T.ell, None, tol=tol)


# ----- Decision 24: the polish at 1e-9 -----

def test_polish_params_are_dual_simplex_at_1e9():
    """DESIGN §6: the polish (and the fixed-integer duals, the same QP) run by dual simplex at
    FeasibilityTol = OptimalityTol = 1e-9; the settings are recorded with every solve."""
    assert POLISH_PARAMS == {"Method": 1, "FeasibilityTol": 1e-9, "OptimalityTol": 1e-9}
    T, _ = TOYS["T1"]
    M = toy_pmi(T, 0.03, "perspective")
    r = M.solve(mip_gap=0.0)
    assert r.settings["polish"] == POLISH_PARAMS
    mdl = M.model._build("fixed", r.zp, r.zm)[0]
    assert (mdl.Params.FeasibilityTol, mdl.Params.OptimalityTol) == (1e-9, 1e-9)
    mdl.dispose()


@pytest.mark.parametrize("ym", ["2017-12", "2020-03"])
@pytest.mark.parametrize("form", FORMS)
def test_polished_weights_satisfy_every_row_at_1e9_on_k8_instances(ym, form):
    from tests.realdata import pmi_case
    inst = pmi_case(ym)
    M = PMI(**inst.kwargs, formulation=form, s_obj=1e4)
    r = M.solve(mip_gap=0.0)
    assert r.v_source == "polished"
    assert pmi_violations(r.w, r.zp, r.zm, inst.B, inst.S, inst.mandate, inst.K, inst.ell,
                          inst.adv, mkt=M.model.mkt, tol=1e-9) == {}
    assert r.polished_violations == "{}"


def _band_points():
    """(name, toy, b): b = ℓ − δ inside Gurobi's default FeasibilityTol band [ℓ − 1e-6, ℓ), where
    a polish at 1e-6 can return w = b with w ≥ ℓ violated by δ (CORE round-3 checker, Decision
    24); δ = 5e-7 on every stored toy, more δ on the fixed toys and the first 10 seeded ones."""
    fixed = [(n, T) for n, (T, _) in TOYS.items()]
    seeded = [(f"R{i:03d}", T) for i, (T, _) in enumerate(random_toys(R_SEED, R_N))]
    pts = [(n, T, T.ell - 5e-7) for n, T in fixed + seeded]
    pts += [(n, T, T.ell - dl) for n, T in fixed + seeded[:10]
            for dl in (1e-10, 1e-8, 1e-7, 9.9e-7)]
    return pts


@pytest.mark.parametrize("form", FORMS)
def test_polished_weights_satisfy_every_row_at_1e9_on_stored_toys(form):
    """On the fixed toys' grids and at band points of every stored toy (the S1 seeded family): a
    defined V has weights that satisfy every row at 1e-9, and the recorded verdict says so. Where
    ℓ − b > 1e-9 the held support is infeasible at 1e-9, so V is 0 (w = 0) or undefined (polish
    failed, counted as excluded): never f(b) > 0 = U*(b)."""
    pts = [(n, T, float(b)) for n, (T, grid) in TOYS.items() for b in grid] + _band_points()
    n_defined = 0
    for name, T, b in pts:
        r = toy_pmi(T, b, form).solve(mip_gap=0.0)
        assert r.v_source in ("polished", "polish_failed"), (name, b)
        if r.v_source == "polish_failed":
            assert r.polished_violations == "V undefined"
            continue
        n_defined += 1
        assert toy_violations(T, b, r) == {}, (name, b, r.w)
        assert r.polished_violations == "{}", (name, b)
        if T.ell - b > 1e-9 and b < T.ell:
            assert r.V == 0.0 and np.all(r.w == 0.0), (name, b, r.V)
    assert n_defined > 0


def test_polished_verdict_uses_the_current_bounds():
    """The verdict is taken at the bounds the solve used (set_bound), not the instance's
    original mandate: weights that break a tightened dollar bound, or a single tightened style
    factor, are reported."""
    B, F, d, S, adv, alpha = random_instance(n=20, seed=61)
    m = Mandate(dollar=0.02, beta=0.05, style=0.10, sector=0.05, gross=2.0, position=0.2,
                liquidity_theta=None)
    M = PMI(B, F, d, S, alpha, 2.0, m, adv, K=8, ell=0.01, formulation="bigm",
            factor_names=FACTORS)
    M.set_bound("dollar", 0.005)
    r = M.solve(mip_gap=0.0)
    assert r.polished_violations == "{}" and abs(r.w.sum()) <= 0.005 + 1e-9
    w = r.w.copy()
    i = int(np.argmax(np.abs(w)))
    w[i] += 0.01 * np.sign(w[i])                     # net moves ~1% past the tightened bound
    assert "dollar" in json.loads(M.verdict(w, r.zp, r.zm, tol=1e-9))
    smb = FACTORS.index("SMB")
    y = B.T @ r.w
    M.set_bound("style", 0.5 * abs(y[smb]), index=M.style_names.index("SMB"))
    assert "style:SMB" in json.loads(M.verdict(r.w, r.zp, r.zm, tol=1e-9))


# ----- Decision 27(a): the rescaled model -----

def test_sibling_keeps_data_and_current_bounds():
    T, _ = TOYS["T2"]
    M = toy_pmi(T, 0.01, "bigm")
    M.set_bound("gross", 0.008)
    P = M.sibling("perspective", rescale=True)
    assert P.formulation == "perspective" and P.rescale and not M.rescale
    assert P.bound("gross") == 0.008 and P.s_obj == M.s_obj and P.lam == M.lam
    P.set_bound("gross", 0.009)
    assert M.bound("gross") == 0.008                 # bounds are copied, not shared


@pytest.mark.parametrize("ym", ["2017-12", "2020-03"])
def test_rescaled_and_unscaled_bigm_agree_on_k8_instances(ym):
    """Big-M has no cones, so rescaling the weights only rescales rows and bounds: at MIPGap 0
    the rescaled and unscaled models give the same z and the same V (1e-9); the raw incumbent is
    mapped back to original units (rows hold at Gurobi's tolerance there) and the solver's value
    equals the exact objective at the mapped weights; the factor c is the largest position bound."""
    from tests.realdata import pmi_case
    inst = pmi_case(ym)
    a = PMI(**inst.kwargs, formulation="bigm", s_obj=1e4).solve(mip_gap=0.0)
    M = PMI(**inst.kwargs, formulation="bigm", s_obj=1e4, rescale=True)
    b = M.solve(mip_gap=0.0)
    c = float(np.where(M.model.holdable, M.model.ub, 0.0).max())
    assert (a.w_scale, b.w_scale) == (1.0, c) and b.settings["rescale"] and not a.settings["rescale"]
    assert 0 < c <= 0.06
    np.testing.assert_array_equal(a.zp, b.zp)
    np.testing.assert_array_equal(a.zm, b.zm)
    assert abs(b.V - a.V) <= 1e-9 * abs(a.V)
    assert pmi_violations(b.w_incumbent, b.zp, b.zm, inst.B, inst.S, inst.mandate, inst.K,
                          inst.ell, inst.adv, mkt=M.model.mkt, tol=1e-6) == {}
    assert b.U_raw == pytest.approx(b.U_incumbent, rel=1e-6)
    assert b.B >= b.V - 1e-6 * abs(b.V)


def test_rescaled_perspective_cone_effect_is_smaller_on_r110():
    """Round-3 Finding C toy R110 (seed 20261019) at b = 1.2079e-3: at default scaling Gurobi's
    perspective incumbent violates its cone by more than |V| in objective; with the weights
    rescaled by u the cone variables are O(1) and the effect is smaller, with V unchanged."""
    T, b_max = random_toys(R_SEED, R_N)[110]
    grid = np.linspace(0.0, b_max, 41)
    b = float(grid[np.argmin(np.abs(grid - 1.20790268e-3))])
    un = toy_pmi(T, b, "perspective").solve(mip_gap=0.0, cone_diag=True)
    rs = toy_pmi(T, b, "perspective").sibling("perspective", rescale=True).solve(
        mip_gap=0.0, cone_diag=True)
    assert un.cone_effect / abs(un.V) > 1.0 and un.w_scale == 1.0 and rs.w_scale == T.u
    assert np.isfinite(rs.cone_effect) and rs.cone_effect < un.cone_effect
    assert rs.V == pytest.approx(T.value(b), abs=1e-12)
    assert rs.cone_effect_rel == pytest.approx(rs.cone_effect / abs(rs.V), rel=1e-12)


# ----- Decision 27(b): combined certification -----

def test_combine_certification_rule():
    """V = the larger polished value, B = the smaller final bound, B_eff = max(B, V) + 1e-6·|V|;
    the supplier of each is recorded; exact ties go to big-M (FORMULATIONS order) and are flagged;
    an undefined V (failed polish) or bound is skipped; both undefined → nan, supplier "none"."""
    T, _ = TOYS["T1"]
    base = toy_pmi(T, 0.03, "bigm").solve(mip_gap=0.0)
    mk = lambda V, B, f: dc_replace(base, V=V, B=B, formulation=f)
    c = combine_certification({"bigm": mk(1.0, 1.2, "bigm"), "perspective": mk(1.1, 1.3, "perspective")})
    assert (c["V"], c["v_from"], c["B"], c["b_from"]) == (1.1, "perspective", 1.2, "bigm")
    assert c["B_eff"] == effective_bound(1.2, 1.1) and not c["v_tie"] and not c["b_tie"]
    c = combine_certification({"bigm": mk(1.0, 1.2, "bigm"), "perspective": mk(1.0, 1.2, "perspective")})
    assert (c["v_from"], c["b_from"], c["v_tie"], c["b_tie"]) == ("bigm", "bigm", True, True)
    c = combine_certification({"bigm": mk(np.nan, 1.2, "bigm"), "perspective": mk(1.0, 1.3, "perspective")})
    assert (c["V"], c["v_from"], c["B"], c["b_from"]) == (1.0, "perspective", 1.2, "bigm")
    c = combine_certification({"bigm": mk(1.0, np.nan, "bigm"), "perspective": mk(0.9, 1.3, "perspective")})
    assert (c["V"], c["v_from"], c["B"], c["b_from"]) == (1.0, "bigm", 1.3, "perspective")
    c = combine_certification({"bigm": mk(np.nan, 1.2, "bigm"), "perspective": mk(np.nan, 1.3, "perspective")})
    assert np.isnan(c["V"]) and c["v_from"] == "none" and np.isnan(c["B_eff"]) and c["B"] == 1.2
    c = combine_certification({"bigm": mk(1.0, 0.9999, "bigm"), "perspective": mk(0.98, 1.1, "perspective")})
    assert c["B_eff"] == pytest.approx(1.0 + 1e-6, rel=1e-15)          # V > B: max(B, V)


@pytest.mark.parametrize("name", list(TOYS))
def test_combined_certification_on_toy_closed_forms(name):
    """On the toys: the combined V is U*(b) (1e-8), B_eff ≥ U*(b), the fixed-integer dual at the
    incumbent that supplied V is the closed-form fixed slope, and the combined interval at b ± δ
    contains the exact secant, also across the jump at ℓ."""
    T, _ = TOYS[name]
    for b in (0.6 * T.ell, 1.05 * T.ell, 0.5 * (T.ell + T.w_opt), 1.2 * T.w_opt):
        delta = 0.1 * b
        res = {}
        for sg in (+1, -1):
            bb = b + sg * delta
            c = solve_combined(toy_pmi(T, bb, "perspective"), mip_gap=0.0)
            assert c.v_from in FORMS and c.b_from in FORMS, bb
            assert abs(c.V - T.value(bb)) <= 1e-8, (bb, c.V)
            assert c.B_eff >= T.value(bb), bb
            assert set(c.parts) == set(FORMS)
            np.testing.assert_array_equal(c.zp, c.parts[c.v_from].zp)
            fixed = c.fixed_duals["shadow"]["gross"]
            cf = T.slopes(bb)["fixed"]
            assert abs(fixed - cf) <= 1e-6 * (abs(cf) if cf != 0 else T.a), (bb, fixed, cf)
            res[sg] = c
        ci = combined_interval(res[+1], res[-1], delta)
        exact = T.secant(b, delta)
        assert ci.L <= exact <= ci.H, (b, ci, exact)
        assert abs(ci.s - exact) <= 1e-8 / delta and not ci.solver_error


# a small MIQP solved by support enumeration (an independent oracle: CVXPY + Clarabel at 1e-12)
ENUM_N, ENUM_K, ENUM_ELL, ENUM_LAM, ENUM_SEED = 7, 3, 0.01, 2.0, 71


def _enum_mandate(sector: float = 0.05) -> Mandate:
    return Mandate(dollar=0.02, beta=0.05, style=0.10, sector=sector, gross=2.0, position=0.2,
                   liquidity_theta=None)


def enumerate_supports(B, F, d, S, alpha, lam, m: Mandate, K: int, ell: float, mkt: int = 0):
    """max U over every support of size ≤ K and every sign pattern, each a convex QP with the
    held names in [ℓ, u] on their side (u = m.position; no liquidity cap) and the others at 0.
    Returns (U*, the best pattern as (zp, zm), the duals dU/db of its mandate rows by key)."""
    N = len(d)
    w, lo, hi = cp.Variable(N), cp.Parameter(N), cp.Parameter(N)
    y = B.T @ w
    LF = np.linalg.cholesky(F)
    U = (alpha @ w - lam * (cp.sum_squares(LF.T @ y) + cp.sum_squares(cp.multiply(np.sqrt(d), w)))
         - m.borrow_monthly * cp.sum(cp.pos(-w)) - m.trade_cost * cp.norm1(w))
    style = [k for k in range(B.shape[1]) if k != mkt]
    rows = {"dollar": [cp.sum(w) <= m.dollar, -cp.sum(w) <= m.dollar],
            "beta": [y[mkt] <= m.beta, -y[mkt] <= m.beta],
            "gross": [cp.norm1(w) <= m.gross]}
    rows.update({f"style:{FACTORS[k]}": [y[k] <= m.style, -y[k] <= m.style] for k in style})
    rows.update({f"sector:{j}": [S[:, j] @ w <= m.sector, -(S[:, j] @ w) <= m.sector]
                 for j in range(S.shape[1])})
    prob = cp.Problem(cp.Maximize(U), [w >= lo, w <= hi] + [c for v in rows.values() for c in v])
    best = (-np.inf, None, None)
    for k in range(K + 1):
        for names in itertools.combinations(range(N), k):
            for signs in itertools.product((1, -1), repeat=k):
                lv, hv = np.zeros(N), np.zeros(N)
                for i, s in zip(names, signs):
                    lv[i], hv[i] = (ell, m.position) if s > 0 else (-m.position, -ell)
                lo.value, hi.value = lv, hv
                prob.solve(solver=cp.CLARABEL, **SOLVER_OPTS["CLARABEL"])
                if prob.status != cp.OPTIMAL or prob.value <= best[0]:
                    continue
                zp, zm = np.zeros(N), np.zeros(N)
                for i, s in zip(names, signs):
                    (zp if s > 0 else zm)[i] = 1.0
                duals = {key: float(sum(float(c.dual_value) for c in cs)) for key, cs in rows.items()}
                best = (float(prob.value), (zp, zm), duals)
    return best


def test_combined_certification_matches_support_enumeration():
    """A 7-name MIQP (K = 3 binds; two sector rows bind) solved by enumerating all 379 sign
    patterns: the combined V equals U* (1e-7), B_eff ≥ U*, V's incumbent is the optimal pattern,
    the fixed-integer duals at it match the pattern QP's duals, and the combined interval for the
    common sector bound at b ± δ contains the exact secant of U*."""
    B, F, d, S, adv, alpha = random_instance(n=ENUM_N, j=3, seed=ENUM_SEED)
    out = {}
    for sector in (0.05, 0.045, 0.055):
        m = _enum_mandate(sector)
        U_star, (zp, zm), duals = enumerate_supports(B, F, d, S, alpha, ENUM_LAM, m, ENUM_K, ENUM_ELL)
        P = PMI(B, F, d, S, alpha, ENUM_LAM, m, adv, K=ENUM_K, ell=ENUM_ELL, formulation="bigm",
                s_obj=1e3, factor_names=FACTORS)
        c = solve_combined(P, mip_gap=0.0)
        assert abs(c.V - U_star) <= 1e-7 * abs(U_star), (sector, c.V, U_star)
        assert c.B_eff >= U_star and c.V <= U_star + 1e-9 * abs(U_star)
        np.testing.assert_array_equal(c.zp, zp)
        np.testing.assert_array_equal(c.zm, zm)
        assert c.V == pytest.approx(exact_objective(c.w, alpha, ENUM_LAM, B, F, d, m), rel=1e-10)
        sh = c.fixed_duals["shadow"]
        assert sum(abs(v) > 1e-9 for v in duals.values()) >= 1           # a row binds
        for key, mu in duals.items():
            assert abs(sh[key] - mu) <= 1e-6 * max(abs(mu), 1e-4 * abs(U_star) / sector), \
                (key, sh[key], mu)
        out[sector] = (U_star, c)
    ci = combined_interval(out[0.055][1], out[0.045][1], 0.005)
    exact = (out[0.055][0] - out[0.045][0]) / 0.01
    assert exact > 0 and ci.L <= exact <= ci.H and not ci.solver_error
