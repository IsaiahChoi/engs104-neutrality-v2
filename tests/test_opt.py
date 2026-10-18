"""Continuous optimizer validation (brief §8 items 1–5), attribution, TC, and the synthetic
alpha's empirical IC (PLAN Phase 3; GATE_CRITERIA §3).

Tolerances (GATE_CRITERIA C3 sets the loosest allowed): objectives 1e-8 relative (C3: 1e-6),
weights 1e-6 absolute (C3: 1e-4), envelope slopes 1% relative (C3: 1%), feasibility 1e-7.
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

import src.opt.feasibility as feasibility
from src.alpha.momentum import momentum_alpha, momentum_score
from src.alpha.synthetic import draw_rng, empirical_ic, residual_returns, synthetic_alpha
from src.opt.attribution import (DUAL_SIGN, attribution, implied_alpha_adjustments,
                                 shadow_prices, sigma_apply, sigma_inv, transfer_coefficient)
from src.opt.continuous import ContinuousProblem, Mandate, calibrate_lambda, load_config
from src.opt.feasibility import violations
from src.risk.factor_model import FACTORS

SOLVERS = ["GUROBI", "CLARABEL"]
OFF = dict(dollar=None, beta=None, style=None, sector=None, gross=None, position=None,
           liquidity_theta=None, borrow_annual=0.0, trade_cost=0.0)
REAL_DATE = "2020-03-31"
LAM_REAL = 20.0          # keeps the risk term active (see PROGRESS: λ calibration decision)


def random_instance(n=60, j=5, seed=0):
    rng = np.random.default_rng(seed)
    K = len(FACTORS)
    B = np.column_stack([rng.normal(1.0, 0.3, n), rng.normal(0.0, 0.5, size=(n, K - 1))])
    A = rng.normal(size=(K, K)) * 0.02
    F = A @ A.T + np.diag(np.full(K, 0.02**2))
    d = rng.uniform(0.003, 0.01, n)
    sectors = rng.integers(0, j, n)
    S = (sectors[:, None] == np.arange(j)[None, :]).astype(float)
    adv = np.exp(rng.normal(np.log(5e7), 1.0, n))
    alpha = 0.05 * np.sqrt(d) * rng.standard_normal(n)
    return B, F, d, S, adv, alpha


def dense_sigma(B, F, d):
    return B @ F @ B.T + np.diag(d)


@pytest.fixture(scope="module")
def tight():
    """Random instance whose bounds are tight enough that every family binds."""
    B, F, d, S, adv, alpha = random_instance()
    m = Mandate(dollar=0.01, beta=0.02, style=0.05, sector=0.03, gross=1.2, position=0.05,
                liquidity_theta=None)
    return B, F, d, S, adv, alpha, m


@pytest.fixture(scope="module")
def real():
    from src.opt.inputs import date_inputs, market_data
    di = date_inputs(REAL_DATE)
    alpha = momentum_alpha(di.model, market_data().ret)
    mandate, _ = load_config()
    return di, alpha, mandate


def real_problem(real, mandate=None):
    di, alpha, base = real
    m = di.model
    return ContinuousProblem(m.B, m.F, m.d, di.sector_matrix(), mandate or base, adv=di.adv,
                             factor_names=FACTORS)


# ---------- 1. KKT closed form ----------

@pytest.mark.parametrize("solver", SOLVERS)
def test_kkt_closed_form_equality_constraints(solver):
    """Only equality constraints (dollar- and beta-neutral, bounds 0), no costs: the solver
    matches w* = (2λ)⁻¹Σ⁻¹(α − A'ν) with (w, ν) from the KKT linear system solved directly."""
    B, F, d, S, adv, alpha = random_instance(n=40, seed=1)
    lam = 5.0
    P = ContinuousProblem(B, F, d, S, Mandate(**{**OFF, "dollar": 0.0, "beta": 0.0}),
                          factor_names=FACTORS)
    sol = P.solve(alpha, lam=lam, solver=solver)
    Sigma = dense_sigma(B, F, d)
    A = np.vstack([np.ones(len(d)), B[:, 0]])
    kkt = np.block([[2 * lam * Sigma, A.T], [A, np.zeros((2, 2))]])
    w_cf, nu = np.split(np.linalg.solve(kkt, np.concatenate([alpha, np.zeros(2)])), [len(d)])
    np.testing.assert_allclose(sol.w, w_cf, rtol=0, atol=1e-6)
    nu_solver = np.array([
        DUAL_SIGN * (sol.duals[("dollar", "upper")] - sol.duals[("dollar", "lower")]).sum(),
        DUAL_SIGN * (sol.duals[("beta", "upper")] - sol.duals[("beta", "lower")]).sum()])
    np.testing.assert_allclose(nu_solver, nu, rtol=1e-6, atol=0)
    w_from_duals = np.linalg.solve(2 * lam * Sigma, alpha - A.T @ nu_solver)
    np.testing.assert_allclose(sol.w, w_from_duals, rtol=0, atol=1e-6)
    u_cf = alpha @ w_cf - lam * w_cf @ Sigma @ w_cf
    assert sol.objective == pytest.approx(u_cf, rel=1e-8)


# ---------- 2. Envelope theorem (and the dual sign convention) ----------

def _fd_slope(P, alpha, lam, solver, family, index=None, rel_step=1e-3):
    b0 = P.bound(family)
    base = b0 if index is None else b0[index]
    h = rel_step * float(np.max(base))
    vals = []
    for sgn in (+1, -1):
        if family == "position":
            P.bounds[family].value = b0 + sgn * h
        elif index is None:
            P.set_bound(family, float(b0) + sgn * h)
        else:
            P.set_bound(family, b0[index] + sgn * h, index=index)
        vals.append(P.solve(alpha, lam=lam, solver=solver).objective)
    P.bounds[family].value = b0
    return (vals[0] - vals[1]) / (2 * h)


ENVELOPE_CASES = ["dollar", "beta", "style", "sector", "gross", "position"]


@pytest.mark.parametrize("solver", SOLVERS)
@pytest.mark.parametrize("family", ENVELOPE_CASES)
def test_envelope_theorem(tight, solver, family):
    """Finite-difference dU*/db matches DUAL_SIGN × (that constraint's duals), and the bound
    binds. This is what fixes DUAL_SIGN (see test_dual_sign_convention)."""
    B, F, d, S, adv, alpha, m = tight
    P = ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS)
    lam = 2.0
    sol = P.solve(alpha, lam=lam, solver=solver)
    sp = shadow_prices(P, sol)
    if family in ("style", "sector"):
        names = P.style_names if family == "style" else list(range(P.J))
        per = np.array([sp[f"{family}:{n}"] for n in names])
        k = int(np.argmax(np.abs(per)))
        pred, fd = per[k], _fd_slope(P, alpha, lam, solver, family, index=k)
    else:
        pred, fd = sp[family], _fd_slope(P, alpha, lam, solver, family)
    assert abs(pred) > 1e-6, f"{family} does not bind (shadow price {pred:.2e})"
    assert fd == pytest.approx(pred, rel=0.01)


def test_dual_sign_convention(tight):
    """DUAL_SIGN is the sign of (finite-difference slope) / (raw CVXPY dual), for every scalar
    family and both solvers; relaxing a bound never lowers U*, so shadow prices are ≥ 0."""
    B, F, d, S, adv, alpha, m = tight
    for solver in SOLVERS:
        P = ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS)
        sol = P.solve(alpha, lam=2.0, solver=solver)
        for fam in ("dollar", "beta", "gross"):
            raw = sum(v.sum() for (f, _), v in sol.duals.items() if f == fam)
            fd = _fd_slope(P, alpha, 2.0, solver, fam)
            assert np.sign(fd / raw) == DUAL_SIGN, (solver, fam)
        assert all(v >= -1e-9 for v in shadow_prices(P, sol).values())


def _fd_mandate(P, alpha, lam, base, field, rel_step=1e-3):
    """Slope of U* in a Mandate field that sets the position bounds (u or θ)."""
    v0, ub0 = getattr(base, field), P.bound("position")
    h = rel_step * v0
    vals = []
    for v in (v0 + h, v0 - h):
        P.bounds["position"].value = Mandate(**{**base.__dict__, field: v}).position_bounds(P.adv, P.N)
        vals.append(P.solve(alpha, lam=lam).objective)
    P.bounds["position"].value = ub0
    return (vals[0] - vals[1]) / (2 * h)


@pytest.mark.parametrize("lam", [LAM_REAL, 2.0])
def test_envelope_theorem_real_data(real, lam):
    """Real base case (momentum alpha): every bound that binds is checked, per style factor
    and for the most binding sector, at an active-risk λ and at a λ where gross binds too.
    Which families bind is read from the solution, not assumed; at least two must."""
    P = real_problem(real)
    _, alpha, base = real
    sp = shadow_prices(P, P.solve(alpha, lam=lam))
    checked = {}
    for key in ("dollar", "beta", "gross"):
        if sp.get(key, 0.0) > 1e-7:
            checked[key] = (_fd_slope(P, alpha, lam, "GUROBI", key), sp[key])
    for i, name in enumerate(P.style_names):
        if sp[f"style:{name}"] > 1e-7:
            checked[f"style:{name}"] = (_fd_slope(P, alpha, lam, "GUROBI", "style", index=i),
                                        sp[f"style:{name}"])
    sectors = np.array([sp[f"sector:{j}"] for j in range(P.J)])
    if sectors.max() > 1e-7:
        j = int(sectors.argmax())
        checked[f"sector:{j}"] = (_fd_slope(P, alpha, lam, "GUROBI", "sector", index=j), sectors[j])
    for key, field in (("position", "position"), ("liquidity", "liquidity_theta")):
        if sp.get(key, 0.0) > 1e-7:
            checked[key] = (_fd_mandate(P, alpha, lam, base, field), sp[key])
    assert len(checked) >= 2, f"only {list(checked)} bind at λ = {lam}"
    assert all(v >= -1e-9 for v in sp.values()), "negative shadow price"   # REVIEW 3 concern 7
    for key, (fd, pred) in checked.items():
        assert fd == pytest.approx(pred, rel=0.01), (key, fd, pred)


# ---------- 3. Solver agreement ----------

def test_solver_agreement_random(tight):
    B, F, d, S, adv, alpha, m = tight
    P = ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS)
    g, c = P.solve(alpha, lam=2.0, solver="GUROBI"), P.solve(alpha, lam=2.0, solver="CLARABEL")
    assert g.objective == pytest.approx(c.objective, rel=1e-8)
    np.testing.assert_allclose(g.w, c.w, rtol=0, atol=1e-6)


@pytest.mark.parametrize("lam", [LAM_REAL, 1e-3])
def test_solver_agreement_real(real, lam):
    """Real base case at an active-risk λ and at the λ floor (the LP-like regime)."""
    P = real_problem(real)
    _, alpha, _ = real
    g, c = P.solve(alpha, lam=lam, solver="GUROBI"), P.solve(alpha, lam=lam, solver="CLARABEL")
    assert g.objective == pytest.approx(c.objective, rel=1e-8)
    np.testing.assert_allclose(g.w, c.w, rtol=0, atol=1e-6)


# ---------- 4. Feasibility (independent checker) ----------

def test_feasibility_checker_is_independent():
    src = inspect.getsource(feasibility)
    assert "cvxpy" not in src and "src.opt.continuous" not in src and "position_bounds" not in src


def test_feasibility_checker_flags_violations(tight):
    B, F, d, S, adv, alpha, m = tight
    P = ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS)
    w = P.solve(alpha, lam=2.0).w
    assert violations(w, B, S, m, adv) == {}
    assert "dollar" in violations(w + 0.01, B, S, m, adv)
    assert "gross" in violations(1.5 * w, B, S, m, adv)
    bad = w.copy()
    bad[0] = m.position + 0.001
    assert "position" in violations(bad, B, S, m, adv)


@pytest.mark.parametrize("solver", SOLVERS)
@pytest.mark.parametrize("only", [None, *ENVELOPE_CASES])
def test_returned_portfolios_are_feasible(tight, real, solver, only):
    """Every returned portfolio satisfies every active constraint: each family alone (random
    instance) and the full mandate (random and real base case)."""
    B, F, d, S, adv, alpha, m = tight
    if only is not None:
        m = Mandate(**{**OFF, only: getattr(m, only), "borrow_annual": m.borrow_annual,
                       "trade_cost": m.trade_cost})
    P = ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS)
    assert violations(P.solve(alpha, lam=2.0, solver=solver).w, B, S, m, adv) == {}
    if only is None:
        di, a, base = real
        w = real_problem(real).solve(a, lam=LAM_REAL, solver=solver).w
        assert violations(w, di.model.B, di.sector_matrix(), base, di.adv) == {}


# ---------- 5. Determinism ----------

@pytest.mark.parametrize("solver", SOLVERS)
def test_determinism(real, solver):
    """Same config + seed ⇒ identical results (fresh problem objects, bitwise)."""
    _, alpha, _ = real
    w1 = real_problem(real).solve(alpha, lam=LAM_REAL, solver=solver).w
    w2 = real_problem(real).solve(alpha, lam=LAM_REAL, solver=solver).w
    np.testing.assert_array_equal(w1, w2)
    a1 = draw_rng(20261015, REAL_DATE, 0.05, 3).standard_normal(5)
    a2 = draw_rng(20261015, REAL_DATE, 0.05, 3).standard_normal(5)
    np.testing.assert_array_equal(a1, a2)
    assert not np.array_equal(a1, draw_rng(20261015, REAL_DATE, 0.05, 4).standard_normal(5))


# ---------- attribution and transfer coefficient ----------

@pytest.mark.parametrize("which", ["random", "real"])
def test_attribution_kkt_residual_and_reconstruction(tight, real, which):
    if which == "random":
        B, F, d, S, adv, alpha, m = tight
        P, lam = ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS), 2.0
    else:
        P, alpha, lam = real_problem(real), real[1], LAM_REAL
    sol = P.solve(alpha, lam=lam)
    a = implied_alpha_adjustments(P, sol)
    G = sol.alpha - 2 * lam * sigma_apply(P, sol.w)
    assert np.abs(a["residual"]).max() <= 1e-6 * np.abs(G).max()      # KKT on held names
    assert (np.abs(a["trading"]) <= P.mandate.trade_cost + 1e-9).all()
    out = attribution(P, sol)
    assert out["reconstruction_error"] <= 1e-8
    total = out["alpha_ideal"] + sum(out["alpha_by_family"].values())
    assert total == pytest.approx(out["alpha_total"], rel=1e-6)


def test_transfer_coefficient():
    B, F, d, S, adv, alpha = random_instance(seed=2)
    P = ContinuousProblem(B, F, d, S, Mandate(**OFF), factor_names=FACTORS)
    w = P.solve(alpha, lam=3.0).w                     # no constraints or costs: w ∝ Σ⁻¹α
    np.testing.assert_allclose(w, sigma_inv(P, alpha) / 6.0, rtol=0, atol=1e-6)
    assert transfer_coefficient(P, alpha, w) == pytest.approx(1.0, abs=1e-8)
    Pc = ContinuousProblem(B, F, d, S, Mandate(**{**OFF, "dollar": 0.0, "beta": 0.0,
                                                   "style": 0.0}), factor_names=FACTORS)
    tc = transfer_coefficient(Pc, alpha, Pc.solve(alpha, lam=3.0).w)
    assert 0.0 < tc < 1.0


def test_calibrate_lambda_hits_target():
    B, F, d, S, adv, alpha = random_instance(seed=3)
    P = ContinuousProblem(B, F, d, S, Mandate(**{**OFF, "dollar": 0.0, "beta": 0.0}),
                          factor_names=FACTORS)
    lam, sol, info = calibrate_lambda(P, alpha, target_annual_vol=0.08)
    assert info["target_reached"] and P.ann_vol(sol.w) == pytest.approx(0.08, rel=1e-4)


# ---------- alphas ----------

def test_synthetic_alpha_empirical_ic(real):
    """GATE_CRITERIA C6: mean empirical IC over 1,000 draws within ±0.01 of target."""
    from src.opt.inputs import market_data, next_rebalance_date
    di = real[0]
    md = market_data()
    e = residual_returns(di.model, md.excess, md.factors, next_rebalance_date(di.date))
    assert np.isfinite(e).all() and e.std() > 0
    for ic in (0.02, 0.05, 0.10):
        ics = [empirical_ic(synthetic_alpha(e, di.model.d, ic,
                                            draw_rng(20261015, di.date, ic, k))[0], e, di.model.d)
               for k in range(1000)]
        assert abs(np.mean(ics) - ic) <= 0.01, (ic, np.mean(ics))


def test_synthetic_alpha_construction():
    rng = np.random.default_rng(0)
    d = rng.uniform(0.003, 0.01, 200)
    e = rng.normal(size=200) * np.sqrt(d)
    alpha, s, e_std = synthetic_alpha(e, d, 0.05, np.random.default_rng(1))
    assert e_std.mean() == pytest.approx(0, abs=1e-12) and e_std.std() == pytest.approx(1)
    np.testing.assert_allclose(alpha, 0.05 * np.sqrt(d) * s, rtol=1e-12)
    np.testing.assert_allclose(synthetic_alpha(e, d, 1.0, np.random.default_rng(1))[1], e_std)


def test_momentum_uses_t_minus_252_to_t_minus_21(real):
    from src.opt.inputs import market_data
    di = real[0]
    ret = market_data().ret
    m = momentum_score(ret, di.tickers[:3], di.date)
    pos = ret.index.get_loc(di.date)
    block = ret.iloc[pos - 251: pos - 20][di.tickers[:3]].fillna(0.0)
    np.testing.assert_allclose(m, (1 + block).prod().to_numpy() - 1, rtol=1e-12)
    later = ret.copy()
    later.iloc[pos - 20:] = 0.9                     # the skipped month and the future
    np.testing.assert_array_equal(momentum_score(later, di.tickers[:3], di.date), m)
    a = momentum_alpha(di.model, ret)
    z = a / (0.03 * np.sqrt(di.model.d))
    assert z.mean() == pytest.approx(0, abs=1e-12) and z.std() == pytest.approx(1)


# ---------- Phase 3b ----------

def test_adjustment_errors_masked_for_alphas_and_residuals(real):
    """REVIEW 3 concern 1: alphas and residuals see the two Yahoo errors as missing."""
    from src.data.panel import ADJUSTMENT_ERRORS
    from src.opt.inputs import market_data, next_rebalance_date, risk_model
    md = market_data()
    for t, d in ADJUSTMENT_ERRORS:
        assert np.isnan(md.ret.loc[d, t]) and np.isnan(md.excess.loc[d, t])
    m = risk_model("2016-06-30")
    e = residual_returns(m, md.excess, md.factors, next_rebalance_date(m.date))
    j = m.tickers.index("DHR")
    sel = (md.excess.index > m.date) & (md.excess.index <= next_rebalance_date(m.date))
    days = md.excess.index[sel]
    keep = days != pd.Timestamp("2016-07-05")
    manual = (md.excess.loc[days[keep], "DHR"] - md.factors.loc[days[keep], FACTORS] @ m.B[j]).sum()
    assert e[j] == pytest.approx(manual, rel=1e-12)


def test_momentum_winsorized_and_restandardized(real):
    """GATE_CRITERIA P2: z clipped at ±3, then re-standardized to mean 0, std 1 (1e-12)."""
    from src.alpha.momentum import WINSOR, winsorized_zscore
    from src.opt.inputs import market_data
    x = np.r_[np.random.default_rng(0).normal(size=300), 25.0, -18.0]
    z0 = (x - x.mean()) / x.std()
    assert np.abs(z0).max() > WINSOR                      # the clip is exercised
    c = np.clip(z0, -WINSOR, WINSOR)
    np.testing.assert_allclose(winsorized_zscore(x), (c - c.mean()) / c.std(), rtol=0, atol=1e-12)
    z = winsorized_zscore(x)
    assert abs(z.mean()) < 1e-12 and abs(z.std() - 1) < 1e-12
    di = real[0]
    a = momentum_alpha(di.model, market_data().ret)
    np.testing.assert_allclose(a / (0.03 * np.sqrt(di.model.d)),
                               winsorized_zscore(momentum_score(market_data().ret, di.tickers, di.date)),
                               rtol=0, atol=1e-12)


def test_position_caps_keep_liquidity_and_price_both(real):
    """REVIEW 3 concern 3: changing u keeps the liquidity caps, and shadow prices follow the
    current (u, θ)."""
    P = real_problem(real)
    _, alpha, base = real
    with pytest.raises(ValueError):
        P.set_bound("position", 0.015)
    P.set_position_caps(0.015, base.liquidity_theta)
    liq = base.liquidity_theta * P.adv / base.aum_usd
    np.testing.assert_array_equal(P.bound("position"), np.minimum(0.015, liq))
    sp = shadow_prices(P, P.solve(alpha, lam=2.0))
    for key, (u, th) in (("position", (0.015, base.liquidity_theta)),
                         ("liquidity", (0.015, base.liquidity_theta))):
        h = 1e-3 * (u if key == "position" else th)
        vals = []
        for s_ in (+1, -1):
            P.set_position_caps(u + s_ * h if key == "position" else u,
                                th + s_ * h if key == "liquidity" else th)
            vals.append(P.solve(alpha, lam=2.0).objective)
        P.set_position_caps(u, th)
        assert sp[key] > 1e-7 and (vals[0] - vals[1]) / (2 * h) == pytest.approx(sp[key], rel=0.01)
