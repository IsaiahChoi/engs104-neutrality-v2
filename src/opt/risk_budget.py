"""P-RB, the fixed-risk-budget problem (DESIGN §3.2), solved through the kept QP (DESIGN §6).

    maximize  α'w − c 1'w⁻ − κ 1't   s.t.  y'Fy + Σ d_i w_i² ≤ σ_m²,  y = B'w,  the mandate

Primary path. ContinuousProblem (src/opt/continuous.py) is the mean-variance QP
max α'w − λ·risk − costs, solved by Gurobi dual simplex (exact active set and duals). By KKT
(A1) the QP at λ = μ_risk has P-RB's solution and the same mandate duals, so λ is root-found
until the QP's ex-ante volatility equals the target: Brent's method on log λ, stopped as soon as
|vol/target − 1| ≤ rtol. Ex-ante volatility is continuous and nonincreasing in λ. The bracket
starts at `lam_guess` (the neighboring sweep point's λ*) or, by default, at the unconstrained
multiplier √(α'Σ⁻¹α)/(2σ_m) (A2 with no constraints). If vol(λ_min) ≤ target, the budget is
slack: the solution is the QP at λ_min and risk_binding = False.

Cross-check. solve_qcqp builds the explicit P-RB in CVXPY with ContinuousProblem's constraints
and dual keys (so attribution.shadow_prices applies to its result) and the objective multiplied
by obj_scale = s; Clarabel runs at tolerance 1e-12. The risk row has two exact forms of the same
set x'x ≤ σ_m², x = (L_F'y, √d∘w):
- risk_form="soc" (default): ‖x‖₂/σ_m ≤ 1 (normalize=False: ‖x‖₂ ≤ σ_m), a second-order cone;
- risk_form="quadratic": x'x/σ_m² ≤ 1 (normalize=False: x'x ≤ σ_m²), which CVXPY converts to a
  rotated cone. Measured in S1 (PROGRESS): on real dates Clarabel never reports OPTIMAL for this
  form at tolerances ≤ 1e-9, and at 1e-8 its weights are off by ~1e-4 relative; the SOC form
  agrees with the root-found QP to ~1e-6 in w and ~1e-10 in A*.
At 1e-12 Clarabel often stops with AlmostSolved (CVXPY "optimal_inaccurate") on the SOC form;
that status is accepted and recorded in Solution.status (accuracy is judged by agreement with
the QP, CHECKS K4/K16), any other non-optimal status raises. Duals are returned unscaled:
μ_j = dual/s; the risk-row multiplier on the variance form is μ_risk = η/(2σ_m²) for the
normalized SOC (η its dual/s), η/(2σ_m) unnormalized; for the quadratic form μ_risk = dual/(s·σ_m²)
normalized, dual/s otherwise. These are equal at a binding row (2μx = η x/σ_m² when ‖x‖ = σ_m).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import cvxpy as cp
import numpy as np
from scipy.optimize import brentq

from src.opt.attribution import sigma_inv
from src.opt.continuous import SOLVER_OPTS, ContinuousProblem, Solution

TARGET_VOL = 0.03                    # base_mandate.yaml risk_budget (asserted equal by the tests)
LAMBDA_MIN = 1e-6
ROOT_RTOL = 1e-10
SIGMA_M = TARGET_VOL / np.sqrt(12.0)


@dataclass
class RiskBudgetSolution:
    sol: Solution            # the QP solution at λ (w, duals, U = α'w − λ·risk − costs)
    A: float                 # P-RB value: net expected alpha α'w − c 1'w⁻ − κ 1't (monthly)
    lam: float               # λ* = μ_risk when the budget binds; λ_min when it is slack
    vol_ann: float           # ex-ante volatility, annualized (√12 × monthly)
    risk_binding: bool
    n_solves: int            # QP solves used by the root-finder
    solve_time: float        # total solver seconds over those solves


def net_alpha(problem: ContinuousProblem, sol: Solution) -> float:
    """α'w − c 1'w⁻ − κ 1't: the P-RB objective (no risk term), monthly."""
    m = problem.mandate
    return float(sol.alpha @ sol.w - m.borrow_monthly * sol.wm.sum() - m.trade_cost * sol.t.sum())


def unconstrained_lambda(problem: ContinuousProblem, alpha, target_vol: float = TARGET_VOL) -> float:
    """μ = √(α'Σ⁻¹α)/(2σ_m): the risk-budget multiplier with no other constraints or costs."""
    alpha = np.asarray(alpha, float)
    return float(np.sqrt(alpha @ sigma_inv(problem, alpha)) / (2.0 * target_vol / np.sqrt(12.0)))


class _Converged(Exception):
    def __init__(self, x: float):
        self.x = x


def solve_risk_budget(problem: ContinuousProblem, alpha, target_vol: float = TARGET_VOL,
                      lam_min: float = LAMBDA_MIN, rtol: float = ROOT_RTOL,
                      lam_guess: float | None = None, solver: str = "GUROBI",
                      max_solves: int = 200) -> RiskBudgetSolution:
    """P-RB at the problem's current bounds (module docstring)."""
    alpha = np.asarray(alpha, float)
    evals: dict[float, tuple[Solution, float]] = {}

    def ev(x: float) -> tuple[Solution, float]:
        if x not in evals:
            if len(evals) >= max_solves:
                raise RuntimeError(f"risk-budget root not found in {max_solves} QP solves")
            lam = lam_min if x == x_min else float(np.exp(x))      # λ_min exactly when slack
            s = problem.solve(alpha, lam=lam, solver=solver)
            evals[x] = (s, problem.ann_vol(s.w))
        return evals[x]

    def f(x: float) -> float:            # log(vol/target): decreasing in x = log λ
        v = ev(x)[1]
        if abs(v / target_vol - 1.0) <= rtol:
            raise _Converged(x)
        return float(np.log(v / target_vol))

    def result(x: float, binding: bool) -> RiskBudgetSolution:
        s, v = evals[x]
        return RiskBudgetSolution(sol=s, A=net_alpha(problem, s), lam=s.lam, vol_ann=v,
                                  risk_binding=binding, n_solves=len(evals),
                                  solve_time=float(sum(e[0].solve_time for e in evals.values())))

    x_min = float(np.log(lam_min))
    guess = lam_guess if lam_guess is not None else unconstrained_lambda(problem, alpha, target_vol)
    x0 = max(float(np.log(guess)), x_min)
    try:
        if f(x0) > 0:                    # vol > target at x0: step up until vol < target
            lo, step = x0, 0.5
            while f(lo + step) > 0:
                lo, step = lo + step, 2.0 * step
            hi = lo + step
        else:                            # step down, never below λ_min
            hi, step = x0, 0.5
            while True:
                if hi <= x_min:
                    return result(x_min, False)          # vol(λ_min) ≤ target: slack
                lo = max(hi - step, x_min)
                if f(lo) > 0:
                    break
                hi, step = lo, 2.0 * step
        x = brentq(f, lo, hi, xtol=1e-15, rtol=4 * np.finfo(float).eps, maxiter=200)
        f(x)
        raise RuntimeError(f"Brent stopped at λ = {np.exp(x):.6g} with |vol/target − 1| = "
                           f"{abs(ev(x)[1] / target_vol - 1):.2e} > rtol {rtol:g}")
    except _Converged as c:
        return result(c.x, True)


QCQP_ACCEPTED = (cp.OPTIMAL, cp.OPTIMAL_INACCURATE)


def solve_qcqp(problem: ContinuousProblem, alpha, target_vol: float = TARGET_VOL,
               normalize: bool = True, obj_scale: float = 1.0, risk_form: str = "soc",
               solver: str = "CLARABEL", **opts) -> Solution:
    """Explicit P-RB at the problem's current bounds (module docstring). Returns a Solution whose
    `objective` is A* and `lam` is μ_risk, both in original units, with unscaled duals; `status`
    is the solver status (optimal or optimal_inaccurate)."""
    if risk_form not in ("soc", "quadratic"):
        raise ValueError(risk_form)
    P, s = problem, float(obj_scale)
    alpha = np.asarray(alpha, float)
    N, m = P.N, P.mandate
    wp, wm, t, y = cp.Variable(N), cp.Variable(N), cp.Variable(N), cp.Variable(P.K)
    w = wp - wm
    LF = np.linalg.cholesky(P.F)
    sig = target_vol / np.sqrt(12.0)
    sig2 = sig**2
    value = alpha @ w - m.borrow_monthly * cp.sum(wm) - m.trade_cost * cp.sum(t)
    b = {k: np.array(p.value, float) if p.shape else float(p.value) for k, p in P.bounds.items()}
    c: dict[tuple[str, str], cp.Constraint] = {}
    if risk_form == "soc":
        x = cp.hstack([LF.T @ y, cp.multiply(np.sqrt(P.d), w)])
        c[("risk", "upper")] = cp.norm(x, 2) / sig <= 1.0 if normalize else cp.norm(x, 2) <= sig
        risk_to_mu = 1.0 / (2.0 * sig2) if normalize else 1.0 / (2.0 * sig)
    else:
        risk = cp.sum_squares(LF.T @ y) + cp.sum_squares(cp.multiply(np.sqrt(P.d), w))
        c[("risk", "upper")] = risk / sig2 <= 1.0 if normalize else risk <= sig2
        risk_to_mu = 1.0 / sig2 if normalize else 1.0
    c[("nonneg", "long")] = -wp <= 0
    c[("nonneg", "short")] = -wm <= 0
    c[("trade", "up")] = w - t <= P.w0
    c[("trade", "down")] = -w - t <= -P.w0
    if "dollar" in b:
        c[("dollar", "upper")] = cp.sum(w) <= b["dollar"]
        c[("dollar", "lower")] = -cp.sum(w) <= b["dollar"]
    if "beta" in b:
        c[("beta", "upper")] = y[P.mkt] <= b["beta"]
        c[("beta", "lower")] = -y[P.mkt] <= b["beta"]
    if "style" in b:
        c[("style", "upper")] = y[P.style_idx] <= b["style"]
        c[("style", "lower")] = -y[P.style_idx] <= b["style"]
    if "sector" in b:
        c[("sector", "upper")] = P.S.T @ w <= b["sector"]
        c[("sector", "lower")] = -(P.S.T @ w) <= b["sector"]
    if "gross" in b:
        c[("gross", "upper")] = cp.sum(wp + wm) <= b["gross"]
    if "position" in b:
        c[("position", "long")] = wp <= b["position"]
        c[("position", "short")] = wm <= b["position"]
    prob = cp.Problem(cp.Maximize(s * value), [y == P.B.T @ w, *c.values()])
    with warnings.catch_warnings():          # "may be inaccurate": the status is recorded instead
        warnings.simplefilter("ignore", UserWarning)
        prob.solve(solver=solver, verbose=False, **{**SOLVER_OPTS.get(solver, {}), **opts})
    if prob.status not in QCQP_ACCEPTED:
        raise RuntimeError(f"{solver} QCQP status {prob.status}")
    duals = {k: np.atleast_1d(np.asarray(con.dual_value, float)) / s for k, con in c.items()}
    mu_risk = float(duals.pop(("risk", "upper"))[0]) * risk_to_mu
    vp, vm, vt, vy = (np.asarray(v.value, float) for v in (wp, wm, t, y))
    return Solution(w=vp - vm, wp=vp, wm=vm, t=vt, y=vy, objective=float(prob.value) / s,
                    status=prob.status, solver=solver, solve_time=prob.solver_stats.solve_time,
                    lam=mu_risk, alpha=alpha, duals=duals)
