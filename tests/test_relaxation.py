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

import warnings

import cvxpy as cp
import numpy as np
import pytest

import src.opt.relaxation as relaxation
from src.opt.continuous import Mandate
from src.opt.integer import PMI, choose_s_obj
from src.opt.toy import Toy, random_toys
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
        rl = M.relaxation_duals(v_ref=T.value(T.w_opt))      # V_ref = the toy's U* (DESIGN §6)
        inc = M.solve(mip_gap=0.0)
        fixed = M.fixed_integer_duals(inc.zp, inc.zm)["shadow"]["gross"]
        assert rl["perspective"]["ok"] and rl["perspective"]["solver"] == "clarabel", b
        assert close(rl["bigm"]["shadow"]["gross"], cf["bigm"], T.a), b
        assert close(rl["perspective"]["shadow"]["gross"], cf["perspective"], T.a), \
            (b, rl["perspective"]["shadow"]["gross"], cf["perspective"])
        assert close(fixed, cf["fixed"], T.a), b


def test_toy_relaxation_value_closed_forms():
    """The relaxation values on the toy (src/opt/toy.py): big-M R(b) = f(min(b, w°)); perspective
    R(b) = (a − λdℓ)·b for b ≤ ℓ and f(min(b, w°)) above, continuous at ℓ; both bound the MIQP
    value U(b) from above, and their slopes are Toy.slopes off the kinks."""
    for T, grid in TOYS.values():
        assert T.relaxation_value(T.ell, "perspective") == pytest.approx(T.f(T.ell), rel=1e-15)
        for b in grid:
            for form in ("bigm", "perspective"):
                assert T.relaxation_value(b, form) >= T.value(b) - 1e-18, (form, b)
            assert T.relaxation_value(b, "bigm") >= T.relaxation_value(b, "perspective") - 1e-18
        for b in off_kinks(T, grid):
            h = 1e-7 * T.u
            for form in ("bigm", "perspective"):
                fd = (T.relaxation_value(b + h, form) - T.relaxation_value(b - h, form)) / (2 * h)
                assert fd == pytest.approx(T.slopes(b)[form], rel=1e-6, abs=1e-9 * T.a), (form, b)
    with pytest.raises(ValueError):
        TOYS["T1"][0].relaxation_value(0.01, "other")


def _value_close(est: float, cf: float, scale: float, rtol: float = 1e-9) -> bool:
    """K9 value criterion: |R̂ − R| ≤ rtol·|R|; where R = 0 (b = 0) against the toy's value scale."""
    return abs(est - cf) <= rtol * (abs(cf) if cf != 0 else scale)


def _k9_relaxation_values(T: Toy, grid) -> list[tuple]:
    """(b, form, Clarabel/Gurobi relaxation value, closed form, Clarabel status) on every point."""
    out = []
    for b in grid:
        rl = toy_pmi(T, b).relaxation_duals(v_ref=T.value(T.w_opt))   # V_ref = U* (DESIGN §6)
        assert rl["bigm"]["ok"] and rl["perspective"]["ok"], (b, rl["perspective"]["status"])
        st = rl["perspective"]["clarabel"]["clarabel_status"]
        out += [(b, f, rl[f]["U"], T.relaxation_value(b, f), st) for f in ("bigm", "perspective")]
    return out


@pytest.mark.parametrize("name", list(TOYS))
def test_k9_relaxation_values_match_closed_forms(name):
    """CHECKS K9: the perspective relaxation's optimal value (Clarabel) matches its closed form to
    1e-9 relative on all 41 grid points, kinks included (the value is continuous); the big-M
    relaxation value (Gurobi dual simplex) too."""
    T, grid = TOYS[name]
    scale = T.value(T.w_opt)
    for b, form, est, cf, st in _k9_relaxation_values(T, grid):
        assert _value_close(est, cf, scale), (name, form, b, est, cf, st)


K9_RANDOM_SEED = 20261019            # recorded seed (CHECKS K9: random toys)
K9_RANDOM_N = 12


def test_k9_relaxation_values_on_seeded_random_toys():
    """CHECKS K9 on a seeded random family (src.opt.toy.random_toys, recorded seed): the
    perspective and big-M relaxation values match their closed forms to 1e-9 relative on 41-point
    grids; Clarabel's status is recorded (Solved or AlmostSolved, both accepted, DESIGN §6)."""
    toys = random_toys(K9_RANDOM_SEED, K9_RANDOM_N)
    assert len(toys) == K9_RANDOM_N and toys == random_toys(K9_RANDOM_SEED, K9_RANDOM_N)
    statuses = set()
    for i, (T, b_max) in enumerate(toys):
        assert 0 < T.ell < T.w_opt < T.u < b_max
        scale = T.value(T.w_opt)
        for b, form, est, cf, st in _k9_relaxation_values(T, np.linspace(0.0, b_max, 41)):
            statuses.add(st)
            assert _value_close(est, cf, scale), (i, T, form, b, est, cf, st)
    assert statuses <= {"Solved", "AlmostSolved"}


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


@pytest.mark.parametrize("status,cvx,r_prim,r_dual,ok", [
    ("Solved", cp.OPTIMAL, 5e-9, 5e-9, True),
    ("AlmostSolved", cp.OPTIMAL_INACCURATE, 1e-9, 1e-10, True),      # accepted (DESIGN §6)
    ("Solved", cp.OPTIMAL, 2e-8, 1e-12, False),                      # primal residual > 1e-8
    ("AlmostSolved", cp.OPTIMAL_INACCURATE, 1e-12, 3e-8, False),     # dual residual > 1e-8
])
def test_relaxation_failure_rule(monkeypatch, status, cvx, r_prim, r_dual, ok):
    """DESIGN §6: a perspective relaxation counts as failed if Clarabel's status is neither
    Solved nor AlmostSolved, or its relative residuals (Clarabel's r_prim, r_dual) exceed 1e-8
    (the duality-gap clause is test_gap_clause); a failure keeps its status and residuals,
    carries no value or duals, and is never raised."""
    T, _ = TOYS["T2"]
    M = toy_pmi(T, 0.005)
    real = relaxation._solve

    def patched(prob, opts):
        raw = real(prob, opts)
        raw.update(status=status, cvxpy_status=cvx, r_prim=r_prim, r_dual=r_dual)
        return raw

    monkeypatch.setattr(relaxation, "_solve", patched)
    assert relaxation.RESIDUAL_MAX == 1e-8
    rec = M.relaxation_duals()["perspective"]
    assert rec["ok"] is ok and rec["clarabel"]["clarabel_status"] == status
    assert (rec["clarabel"]["r_prim"], rec["clarabel"]["r_dual"]) == (r_prim, r_dual)
    assert rec["almost_solved"] == (status == "AlmostSolved")
    if ok:
        assert np.isfinite(rec["U"]) and rec["shadow"]
    else:
        assert np.isnan(rec["U"]) and rec["shadow"] == {} and "residual" in rec["status"]


# ---- Decision 21 (DESIGN §6, revised 2026-10-19): the relaxation's value is the objective at
# Clarabel's returned (w, ζ) with s_i = w_i²/ζ_i, so every cone holds exactly; a relaxation is
# also failed if its duality gap exceeds 1e-9·max(|V|, |V_ref|) (V_ref: the toy's U*)

R_SEED, R_N = 20261019, 200          # the round-3 runner's family (experiments/configs/core.yaml)


def _random_point(i: int, j: int) -> tuple[Toy, float]:
    """Toy i of random_toys(R_SEED, R_N) at point j of its 41-point grid (as experiments.run_core)."""
    T, b_max = random_toys(R_SEED, R_N)[i]
    return T, float(np.linspace(0.0, b_max, 41)[j])


def test_cone_exact_s_and_zeta_to_zero():
    """s_i = v_i²/ζ_i, so v_i² ≤ s_i·ζ_i holds with equality; s_i = 0 where v_i = 0. The linking row
    |v_i| ≤ u_i·ζ_i bounds s_i by u_i·|v_i|; where Clarabel's point breaks it (ζ_i → 0 faster than
    v_i, or ζ_i ≤ 0) s_i is that bound, and such names are counted. Finite, without warnings."""
    u = np.full(8, 0.06)
    v = np.array([0.0, 0.03, -0.06, 0.03 * 1e-13, 1e-16, 0.0, 1e-12, -1e-14])
    zeta = np.array([0.0, 0.8, 1.0, 1e-13, 0.0, 1e-300, 1e-30, -1e-16])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        s, n_capped = relaxation.cone_exact_s(v, zeta, u)
    expect = np.array([0.0, 0.03 ** 2 / 0.8, 0.06 ** 2, 0.03 ** 2 * 1e-13, 0.06 * 1e-16, 0.0,
                       0.06 * 1e-12, 0.06 * 1e-14])
    np.testing.assert_allclose(s, expect, rtol=1e-14, atol=0)
    assert n_capped == 3                                      # ζ = 0, ζ ≪ |v|/u, ζ < 0
    exact = np.array([True, True, True, True, False, True, False, False])
    np.testing.assert_allclose((s * zeta)[exact], (v * v)[exact], rtol=1e-14, atol=0)
    assert np.all(s <= u * np.abs(v))
    # ζ → 0 inside the linking row (v = u·ζ/2): s = u²·ζ/4 → 0, the cone exact at every step,
    # with no underflow where v² would (ζ < 1e-160)
    for k in range(1, 300, 7):
        z = 10.0 ** -k
        sk, nk = relaxation.cone_exact_s(np.array([0.03 * z]), np.array([z]), np.array([0.06]))
        assert nk == 0 and sk[0] == pytest.approx(0.03 ** 2 * z, rel=1e-14), k


@pytest.mark.parametrize("case", ["T2", realdata.K8_MONTHS[0]])
def test_value_is_objective_at_cone_feasible_point(case):
    """The reported value is the P-MI objective at Clarabel's mapped-back (w⁺, w⁻, ζ) with
    s = cone_exact_s(w, ζ, u) (every cone exact there), computed independently here; Clarabel's
    own objective, their difference, the gap (absolute, pure relative, Clarabel's) and the
    residuals are recorded for every relaxation."""
    if case == "T2":
        T, _ = TOYS["T2"]
        M = toy_pmi(T, 0.005)
        v_ref = T.value(T.w_opt)
    else:
        M = PMI(**realdata.pmi_case(case).kwargs, s_obj=1e4)
        v_ref = None
    rec = M.relaxation_duals(v_ref=v_ref)["perspective"]
    sol = relaxation.perspective_relaxation(M.model, v_ref=None if v_ref is None else M.s_obj * v_ref)
    assert rec["ok"] and sol.ok
    info = rec["clarabel"]
    for key in ("clarabel_status", "r_prim", "r_dual", "gap_abs", "gap_rel", "clarabel_gap_rel",
                "clarabel_objective", "value", "value_minus_clarabel", "gap_threshold", "v_ref",
                "n_s_capped", "fail_reason"):
        assert key in info, key
    assert info["fail_reason"] is None
    w, zeta = sol.result.w, sol.result.zp + sol.result.zm
    ub = np.where(M.model.holdable, M.model.ub, 0.0)
    s = sol.s
    assert np.all(np.isfinite(s)) and np.all(s >= 0)
    held = (w != 0) & (zeta > 0) & (np.abs(w) <= ub * zeta)
    np.testing.assert_allclose((s * zeta)[held], (w * w)[held], rtol=1e-14, atol=0)   # cones exact
    m = M.mandate                                        # original units (the model's are × s_obj)
    y = M.B.T @ w
    U = float(M.alpha @ w - M.lam * (y @ M.F @ y + M.d @ s)
              - m.borrow_monthly * sol.wm.sum() - m.trade_cost * (sol.wp + sol.wm).sum())
    assert rec["U"] == pytest.approx(U, rel=1e-13)
    assert info["value"] == pytest.approx(M.s_obj * U, rel=1e-13)
    assert info["clarabel_objective"] == -info["obj_primal"]
    assert info["value_minus_clarabel"] == info["value"] - info["clarabel_objective"]
    assert rec["U_clarabel"] == info["clarabel_objective"] / M.s_obj
    assert rec["U_minus_clarabel"] == pytest.approx(rec["U"] - rec["U_clarabel"], abs=1e-15 * abs(rec["U"]))
    assert info["gap_abs"] == abs(info["obj_primal"] - info["obj_dual"])
    assert info["clarabel_gap_rel"] == info["gap_abs"] / max(1.0, min(abs(info["obj_primal"]),
                                                                      abs(info["obj_dual"])))
    assert info["gap_threshold"] == 1e-9 * max(abs(info["value"]), abs(info["v_ref"] or 0.0))


def test_r043_regression_value_within_1e9():
    """Round-3 run (run_20261019T124115Z), R043 at grid point 19 (b = 2.81e-3, w° < b < u):
    AlmostSolved, residuals 6e-11 and 1e-10, gap 1e-13. Clarabel's own objective misses the closed
    form by 1.04e-9 relative, because its s sits above w²/ζ, which the gap cannot see; the value
    at s = w²/ζ is within 1e-9 (CHECKS K9). The second assertion keeps the reproducer honest."""
    T, b = _random_point(43, 19)
    assert b == pytest.approx(2.80798e-3, rel=1e-5)
    rec = toy_pmi(T, b).relaxation_duals(v_ref=T.value(T.w_opt))["perspective"]
    cf = T.relaxation_value(b, "perspective")
    assert rec["ok"] and rec["clarabel"]["clarabel_status"] == "AlmostSolved"
    assert abs(rec["U"] - cf) <= 1e-9 * abs(cf), (rec["U"] - cf) / cf
    assert abs(rec["U_clarabel"] - cf) > 1e-9 * abs(cf)


def test_r082_failed_by_gap_clause():
    """Round-3 run, R082 at grid point 37 (b = 0.2105 > u): AlmostSolved with residuals within
    1e-8, so only the gap clause can fail it; its gap (6.6e-8 scaled) exceeds 1e-9·max(|V|, |U*|).
    Recorded with its reason, its value and Clarabel's objective; no value or duals are used."""
    T, b = _random_point(82, 37)
    assert b == pytest.approx(0.210547, rel=1e-5)
    M = toy_pmi(T, b)
    rec = M.relaxation_duals(v_ref=T.value(T.w_opt))["perspective"]
    info = rec["clarabel"]
    assert info["clarabel_status"] == "AlmostSolved"
    assert info["r_prim"] <= 1e-8 and info["r_dual"] <= 1e-8
    assert info["v_ref"] == M.s_obj * T.value(T.w_opt)
    assert info["gap_threshold"] == 1e-9 * max(abs(info["value"]), abs(info["v_ref"]))
    assert info["gap_abs"] > info["gap_threshold"]
    assert info["fail_reason"] == "gap" and "gap" in rec["status"]
    assert not rec["ok"] and np.isnan(rec["U"]) and rec["shadow"] == {}
    assert np.isfinite(info["value"]) and np.isfinite(info["clarabel_objective"])


def test_b_zero_points_not_failed():
    """At b = 0 the value is 0, so a gap read against |V| alone would fail on rounding; the floor
    |V_ref| = the toy's U* (DESIGN §6) keeps them. The fixed toys and the first 12 seeded toys."""
    toys = [T for T, _ in TOYS.values()] + [T for T, _ in random_toys(R_SEED, 12)]
    for T in toys:
        scale = T.value(T.w_opt)
        M = toy_pmi(T, 0.0)
        rec = M.relaxation_duals(v_ref=scale)["perspective"]
        assert rec["ok"], (T, rec["status"])
        assert abs(rec["U"]) <= 1e-9 * scale
        assert rec["clarabel"]["gap_threshold"] == pytest.approx(1e-9 * M.s_obj * scale, rel=1e-15)


@pytest.mark.parametrize("gap_factor,v_ref_factor,ok", [
    (0.5, None, True),                # gap 0.5e-9·|V|
    (2.0, None, False),               # gap 2e-9·|V| > 1e-9·|V|
    (2.0, 4.0, True),                 # V_ref = 4·|V| raises the threshold to 4e-9·|V|
])
def test_gap_clause(monkeypatch, gap_factor, v_ref_factor, ok):
    """DESIGN §6: failed if the duality gap |p − d| exceeds 1e-9·max(|V|, |V_ref|); a failure keeps
    its reason, status, residuals and gap, carries no value or duals, and is never raised."""
    T, _ = TOYS["T2"]
    b = 0.005
    M = toy_pmi(T, b)
    real = relaxation._solve

    def patched(prob, opts):
        raw = real(prob, opts)
        raw["obj_dual"] = raw["obj_primal"] + gap_factor * 1e-9 * abs(raw["obj_primal"])
        return raw

    monkeypatch.setattr(relaxation, "_solve", patched)
    v_ref = None if v_ref_factor is None else v_ref_factor * T.relaxation_value(b, "perspective")
    rec = M.relaxation_duals(v_ref=v_ref)["perspective"]
    assert rec["ok"] is ok
    assert rec["clarabel"]["fail_reason"] == (None if ok else "gap")
    if ok:
        assert np.isfinite(rec["U"]) and rec["shadow"]
    else:
        assert np.isnan(rec["U"]) and rec["shadow"] == {} and "gap" in rec["status"]
