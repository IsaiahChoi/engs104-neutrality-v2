"""Perspective relaxation of P-MI in Clarabel (DESIGN §6; CHECKS K9, K8, K29b).

The relaxation's value and duals come from Clarabel on an equivalent rescaled problem (weights
divided by the largest position bound, each cone by its name's bound); Gurobi's barrier on the
same relaxation is kept only as a value cross-check (1e-6 relative at the chosen s_obj).

K9 (A7), one asset, f(w) = aw − λdw², w° = a/(2λd), 0 < ℓ < w° < u: away from the kinks
{0, ℓ, w°, u} the big-M relaxation slope is a − 2λdb (b < w°), the perspective relaxation slope
is a − λdℓ below ℓ and a − 2λdb on (ℓ, w°), the fixed-integer dual is 0 below ℓ and a − 2λdb on
[ℓ, w°), and all three are 0 above w°. "1e-6 relative" is |μ̂ − μ| ≤ 1e-6·|μ|; where the closed
form is 0 it is read against the slope scale a (|μ̂| ≤ 1e-6·a).
"""
from __future__ import annotations

import cvxpy as cp
import numpy as np
import pytest

import src.opt.relaxation as relaxation
from src.opt.continuous import Mandate
from src.opt.integer import PMI, choose_s_obj
from src.opt.toy import Toy
from src.risk.factor_model import FACTORS
from tests import realdata

TOYS = {
    # the S1 toy (tests/test_toy_miqp.py): w° = 0.05, ℓ, w°, u at grid points 8, 20, 32
    "T1": (Toy(a=1.0, lam=1.0, d=10.0, ell=0.02, u=0.08), np.linspace(0.0, 0.10, 41)),
    # project magnitudes (CHECK CORE round 1): w° = 0.01, ℓ, w°, u at grid points 5, 20, 30
    "T2": (Toy(a=0.004, lam=10.0, d=0.02, ell=0.0025, u=0.015), np.linspace(0.0, 0.02, 41)),
}
RTOL = 1e-6


def toy_pmi(T: Toy, b: float, formulation: str = "perspective") -> PMI:
    m = Mandate(dollar=None, beta=None, style=None, sector=None, gross=b, position=T.u,
                liquidity_theta=None, borrow_annual=0.0, trade_cost=0.0)
    return PMI(np.zeros((1, len(FACTORS))), np.eye(len(FACTORS)) * 1e-4, np.array([T.d]),
               np.ones((1, 1)), np.array([T.a]), T.lam, m, None, K=1, ell=T.ell,
               formulation=formulation, s_obj=choose_s_obj(T.value(T.w_opt)),
               factor_names=FACTORS)


def off_kinks(T: Toy, grid):
    kinks = (0.0, T.ell, T.w_opt, T.u)
    return [b for b in grid if min(abs(b - k) for k in kinks) > 1e-12]


def close(est: float, cf: float, scale: float, rtol: float = RTOL) -> bool:
    return abs(est - cf) <= rtol * (abs(cf) if cf != 0 else scale)


@pytest.mark.parametrize("name", list(TOYS))
def test_k9_relaxation_and_fixed_integer_duals_match_closed_forms(name):
    T, grid = TOYS[name]
    pts = off_kinks(T, grid)
    assert len(pts) == len(grid) - 4
    for b in pts:
        cf = T.slopes(b)
        M = toy_pmi(T, b)
        rl = M.relaxation_duals()
        inc = M.solve(mip_gap=0.0)
        fixed = M.fixed_integer_duals(inc.zp, inc.zm)["shadow"]["gross"]
        assert rl["perspective"]["ok"] and rl["perspective"]["solver"] == "clarabel", b
        assert close(rl["bigm"]["shadow"]["gross"], cf["bigm"], T.a), b
        assert close(rl["perspective"]["shadow"]["gross"], cf["perspective"], T.a), \
            (b, rl["perspective"]["shadow"]["gross"], cf["perspective"])
        assert close(fixed, cf["fixed"], T.a), b


def test_k9_value_function_second_toy():
    """The 41-point value function at project magnitudes (T2), jump at ℓ included, to 1e-8."""
    T, grid = TOYS["T2"]
    for form in ("bigm", "perspective"):
        for b in grid:
            assert abs(toy_pmi(T, b, form).solve(mip_gap=0.0).V - T.value(b)) <= 1e-8, (form, b)


def _relaxation_value(rec_w, zp, zm, alpha, lam, B, F, d, mandate) -> float:
    """α'w − λ(y'Fy + Σ_i d_i w_i²/ζ_i) − c 1'w⁻ − κ|w|, ζ = z⁺ + z⁻ (0/0 := 0)."""
    w = np.asarray(rec_w, float)
    zeta = np.asarray(zp, float) + np.asarray(zm, float)
    y = B.T @ w
    idio = np.where(zeta > 0, d * w * w / np.where(zeta > 0, zeta, 1.0), 0.0)
    return float(alpha @ w - lam * (y @ F @ y + idio.sum())
                 - mandate.borrow_monthly * np.maximum(-w, 0).sum() - mandate.trade_cost * np.abs(w).sum())


@pytest.mark.parametrize("ym", realdata.K8_MONTHS)
def test_clarabel_relaxation_matches_gurobi_barrier_value(ym):
    """At the chosen s_obj the Clarabel relaxation value equals Gurobi's barrier relaxation value
    to 1e-6 relative; Clarabel's point, mapped back to original units, attains its value and is
    feasible for the relaxation rows; status and final residuals are recorded (K29b)."""
    inst = realdata.pmi_case(ym)
    s = choose_s_obj(PMI(**inst.kwargs, s_obj=1.0).solve(mip_gap=0.0).V)
    M = PMI(**inst.kwargs, s_obj=s)
    rec = M.relaxation_duals()["perspective"]
    assert rec["ok"] and rec["status"] in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE)
    assert rec["gurobi_barrier_status"] == "OPTIMAL"
    assert abs(rec["U"] / rec["U_gurobi_barrier"] - 1) <= 1e-6
    info = rec["clarabel"]
    for key in ("clarabel_status", "iterations", "r_prim", "r_dual", "gap_abs", "gap_rel",
                "solve_time", "w_scale", "tol"):
        assert key in info, key
    assert info["clarabel_status"] in ("Solved", "AlmostSolved")
    assert rec["almost_solved"] == (info["clarabel_status"] == "AlmostSolved")
    assert info["w_scale"] == pytest.approx(float(M.model.ub[M.model.holdable].max()), rel=0)
    sol = relaxation.perspective_relaxation(M.model)
    w, zp, zm = sol.result.w, sol.result.zp, sol.result.zm
    U = _relaxation_value(w, zp, zm, inst.alpha, inst.lam, inst.B, inst.F, inst.d, inst.mandate)
    assert abs(U / rec["U"] - 1) <= 1e-8
    tol = 1e-9
    ub = np.where(M.model.holdable, M.model.ub, 0.0)
    assert np.all(np.abs(w) <= ub * (zp + zm) + tol) and np.all(zp + zm <= 1 + tol)
    assert np.all(np.abs(w) >= inst.ell * (zp + zm) - tol)
    assert (zp + zm).sum() <= inst.K + tol
    assert abs(w.sum()) <= inst.mandate.dollar + tol
    assert np.all(np.abs(inst.S.T @ w) <= inst.mandate.sector + tol)


def test_clarabel_failure_is_recorded_not_fatal(monkeypatch):
    """A Clarabel status other than Solved/AlmostSolved (or a solver error) records the
    relaxation as failed, with its status and residuals and no duals; never raised."""
    T, _ = TOYS["T2"]
    M = toy_pmi(T, 0.005)
    real = relaxation._solve

    def failing(prob, opts):
        raw = real(prob, opts)
        raw["status"], raw["cvxpy_status"] = "InsufficientProgress", cp.SOLVER_ERROR
        return raw

    monkeypatch.setattr(relaxation, "_solve", failing)
    rec = M.relaxation_duals()["perspective"]
    assert not rec["ok"] and rec["shadow"] == {} and "InsufficientProgress" in rec["status"]
    assert rec["clarabel"]["clarabel_status"] == "InsufficientProgress"
    assert "r_prim" in rec["clarabel"]
    assert M.relaxation_duals()["bigm"]["ok"]                # the big-M relaxation is unaffected
