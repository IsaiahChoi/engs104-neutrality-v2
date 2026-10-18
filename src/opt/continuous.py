"""Continuous market-neutral portfolio problem (brief §3.2) in CVXPY with Parameters (DPP).

    maximize    α'w − λ (y'F y + w'D w) − c 1'w⁻ − κ 1't
    subject to  y = B'w,   w = w⁺ − w⁻,   −w⁺ ≤ 0,  −w⁻ ≤ 0
                w − t ≤ w₀,   −w − t ≤ −w₀                    (t ≥ |w − w₀|, trading)
                dollar     1'w ≤ ε_net,      −1'w ≤ ε_net
                beta       y_mkt ≤ ε_β,      −y_mkt ≤ ε_β
                style      y_k ≤ b_k,        −y_k ≤ b_k       (k ≠ Mkt-RF)
                sector     S'w ≤ s,          −S'w ≤ s
                gross      1'(w⁺ + w⁻) ≤ G
                position   w⁺ ≤ ub,  w⁻ ≤ ub,   ub_i = min(u, θ·ADV_i / AUM)

A family is off when its bound in the Mandate is None. α, λ and every bound are CVXPY
Parameters, so sweeps re-solve without recompiling. Every inequality is written as
`expr <= bound`, one per side, so each has its own dual and all duals share one sign
convention (established by the envelope test; see src/opt/attribution.py).
Units: weights are fractions of capital; α, F, D and the borrow cost c are monthly; κ is a
one-way cost per unit of capital traded.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import cvxpy as cp
import numpy as np

from src.opt.gurobi_env import DEFAULT_SEED, DEFAULT_THREADS, quiet_env

FAMILIES = ("dollar", "beta", "style", "sector", "gross", "position")
MKT = "Mkt-RF"

# Gurobi solves the QP by dual simplex (Method=1), which returns an exact active set: names
# at zero are exactly zero and duals are exactly complementary, as the attribution needs. Its
# default barrier leaves ~1e-7–1e-5 weights on names that should be zero (KKT residual ~1e-5 on
# the real base case vs 3e-16 by simplex). Clarabel (interior point) is the cross-check, run
# at tolerance 1e-12, where it matches the simplex solution to ~1e-7 in weights.
SOLVER_OPTS = {
    "GUROBI": {"Method": 1, "FeasibilityTol": 1e-9, "OptimalityTol": 1e-9},
    "CLARABEL": {"tol_gap_abs": 1e-12, "tol_gap_rel": 1e-12, "tol_feas": 1e-12, "max_iter": 500},
}


@dataclass(frozen=True)
class Mandate:
    """Base values from brief §3.3. None switches a family off."""
    dollar: float | None = 0.02          # ε_net
    beta: float | None = 0.05            # ε_β, loading units
    style: float | None = 0.10           # b_k, each non-market factor
    sector: float | None = 0.02          # s_j, each sector
    gross: float | None = 2.0            # G
    position: float | None = 0.03        # u
    liquidity_theta: float | None = 0.05 # θ (fraction of ADV); None = no liquidity scaling
    aum_usd: float = 1e9
    borrow_annual: float = 0.0030        # 30 bp/yr on shorts
    trade_cost: float = 0.0005           # κ, 5 bp one-way

    @classmethod
    def from_config(cls, cfg: dict) -> "Mandate":
        bad = {k: v for k, v in cfg.items() if v is not None and not isinstance(v, (int, float))}
        if bad:
            raise TypeError(f"mandate values must be numbers or null: {bad}")
        return cls(**{k: (None if v is None else float(v)) for k, v in cfg.items()})

    @property
    def borrow_monthly(self) -> float:
        return self.borrow_annual / 12.0

    def position_bounds(self, adv: np.ndarray | None, n: int) -> np.ndarray | None:
        """ub_i = min(u, θ·ADV_i/AUM); a missing ADV gives ub_i = 0 when θ is set."""
        ub = None
        if self.position is not None:
            ub = np.full(n, self.position)
        if self.liquidity_theta is not None:
            if adv is None:
                raise ValueError("liquidity limit needs ADV")
            liq = np.nan_to_num(self.liquidity_theta * np.asarray(adv, float) / self.aum_usd, nan=0.0)
            ub = liq if ub is None else np.minimum(ub, liq)
        return ub


@dataclass
class Solution:
    w: np.ndarray
    wp: np.ndarray
    wm: np.ndarray
    t: np.ndarray
    y: np.ndarray
    objective: float                      # U*, monthly
    status: str
    solver: str
    solve_time: float
    lam: float
    alpha: np.ndarray
    duals: dict                           # (family, side) -> raw CVXPY dual value (array)


class ContinuousProblem:
    """Brief §3.2 at one rebalance date. B (N x K), F (K x K), d (N,), S (N x J)."""

    def __init__(self, B, F, d, S, mandate: Mandate, adv=None, w0=None,
                 factor_names: list[str] | None = None):
        B, F, d, S = (np.asarray(a, float) for a in (B, F, d, S))
        self.N, self.K = B.shape
        self.J = S.shape[1]
        self.B, self.F, self.d, self.S = B, F, d, S
        self.mandate = mandate
        self.adv = None if adv is None else np.asarray(adv, float)
        self.w0 = np.zeros(self.N) if w0 is None else np.asarray(w0, float)
        names = list(factor_names) if factor_names is not None else None
        self.mkt = names.index(MKT) if names else 0
        self.style_idx = [k for k in range(self.K) if k != self.mkt]
        self.style_names = [names[k] for k in self.style_idx] if names else None

        N = self.N
        self.alpha = cp.Parameter(N, name="alpha", value=np.zeros(N))
        self.lam = cp.Parameter(nonneg=True, name="lam", value=1.0)
        wp, wm = cp.Variable(N, name="wp"), cp.Variable(N, name="wm")
        t, y = cp.Variable(N, name="t"), cp.Variable(self.K, name="y")
        w = wp - wm
        self._vars = (wp, wm, t, y)

        LF = np.linalg.cholesky(F)
        risk = cp.sum_squares(LF.T @ y) + cp.sum_squares(cp.multiply(np.sqrt(d), w))
        objective = (self.alpha @ w - self.lam * risk
                     - mandate.borrow_monthly * cp.sum(wm) - mandate.trade_cost * cp.sum(t))

        self.bounds: dict[str, cp.Parameter] = {}
        self.cons: dict[tuple[str, str], cp.Constraint] = {}
        c = self.cons
        c[("nonneg", "long")] = -wp <= 0
        c[("nonneg", "short")] = -wm <= 0
        c[("trade", "up")] = w - t <= self.w0
        c[("trade", "down")] = -w - t <= -self.w0
        eq = [y == B.T @ w]

        def param(name, size=None, value=None):
            p = cp.Parameter(size, nonneg=True, name=name) if size else cp.Parameter(nonneg=True, name=name)
            p.value = value
            self.bounds[name] = p
            return p

        if mandate.dollar is not None:
            p = param("dollar", value=mandate.dollar)
            c[("dollar", "upper")] = cp.sum(w) <= p
            c[("dollar", "lower")] = -cp.sum(w) <= p
        if mandate.beta is not None:
            p = param("beta", value=mandate.beta)
            c[("beta", "upper")] = y[self.mkt] <= p
            c[("beta", "lower")] = -y[self.mkt] <= p
        if mandate.style is not None:
            p = param("style", len(self.style_idx), np.full(len(self.style_idx), mandate.style))
            c[("style", "upper")] = y[self.style_idx] <= p
            c[("style", "lower")] = -y[self.style_idx] <= p
        if mandate.sector is not None:
            p = param("sector", self.J, np.full(self.J, mandate.sector))
            c[("sector", "upper")] = S.T @ w <= p
            c[("sector", "lower")] = -(S.T @ w) <= p
        if mandate.gross is not None:
            p = param("gross", value=mandate.gross)
            c[("gross", "upper")] = cp.sum(wp + wm) <= p
        ub = mandate.position_bounds(self.adv, N)
        self.position_caps = (mandate.position, mandate.liquidity_theta)   # (u, θ) behind ub
        if ub is not None:
            p = param("position", N, ub)
            c[("position", "long")] = wp <= p
            c[("position", "short")] = wm <= p

        self.problem = cp.Problem(cp.Maximize(objective), eq + list(c.values()))
        assert self.problem.is_dpp()

    # ----- parameters -----
    def set_bound(self, family: str, value, index: int | None = None) -> None:
        if family == "position":
            raise ValueError("use set_position_caps(u, theta): position caps are min(u, θ·ADV/AUM)")
        p = self.bounds[family]
        if index is None:
            p.value = np.full(p.shape, float(value)) if p.shape else float(value)
        else:
            v = np.array(p.value, float)
            v[index] = float(value)
            p.value = v

    def set_position_caps(self, u: float | None, theta: float | None) -> None:
        """ub_i = min(u, θ·ADV_i/AUM) with this u and θ (either may be None = that cap off, not
        both); recorded so shadow_prices can tell u-capped from liquidity-capped names."""
        from dataclasses import replace
        ub = replace(self.mandate, position=u, liquidity_theta=theta).position_bounds(self.adv, self.N)
        if ub is None:
            raise ValueError("both caps off: build a problem without the position family")
        self.bounds["position"].value = ub
        self.position_caps = (u, theta)

    def bound(self, family: str):
        return np.array(self.bounds[family].value, float)

    # ----- risk -----
    def exposures(self, w: np.ndarray) -> np.ndarray:
        return self.B.T @ w

    def variance(self, w: np.ndarray) -> float:
        e = self.B.T @ w
        return float(e @ self.F @ e + self.d @ (w * w))

    def ann_vol(self, w: np.ndarray) -> float:
        return float(np.sqrt(12.0 * self.variance(w)))

    # ----- solve -----
    def solve(self, alpha=None, lam: float | None = None, solver: str = "GUROBI",
              threads: int = DEFAULT_THREADS, seed: int = DEFAULT_SEED, **opts) -> Solution:
        if alpha is not None:
            self.alpha.value = np.asarray(alpha, float)
        if lam is not None:
            self.lam.value = float(lam)
        kw = {**SOLVER_OPTS[solver], **opts}
        if solver == "GUROBI":
            kw["env"] = quiet_env(threads, seed)
        t0 = time.perf_counter()
        self.problem.solve(solver=solver, verbose=False, **kw)
        elapsed = time.perf_counter() - t0
        if self.problem.status != cp.OPTIMAL:
            raise RuntimeError(f"{solver} status {self.problem.status}")
        wp, wm, t, y = (np.asarray(v.value, float) for v in self._vars)
        duals = {k: np.atleast_1d(np.asarray(con.dual_value, float)) for k, con in self.cons.items()}
        return Solution(w=wp - wm, wp=wp, wm=wm, t=t, y=y, objective=float(self.problem.value),
                        status=self.problem.status, solver=solver, solve_time=elapsed,
                        lam=float(self.lam.value), alpha=np.array(self.alpha.value, float),
                        duals=duals)


def load_config(path: str = "experiments/configs/base_mandate.yaml") -> tuple[Mandate, dict]:
    """(Mandate, full config dict) from a mandate YAML file."""
    import yaml
    cfg = yaml.safe_load(open(path))
    return Mandate.from_config(cfg["mandate"]), cfg


def calibrate_lambda(problem: ContinuousProblem, alpha, target_annual_vol: float = 0.08,
                     solver: str = "GUROBI", lo: float = 1e-3, hi: float = 1e5,
                     rtol: float = 1e-4, max_iter: int = 100) -> tuple[float, Solution, dict]:
    """λ such that the optimal portfolio's ex-ante volatility (annualized, √12 × monthly) equals
    the target (brief §3.3). Ex-ante risk is nonincreasing in λ, so bisect on log λ. If even
    λ = lo cannot reach the target (other constraints cap risk), return lo and flag it."""
    def run(lam):
        s = problem.solve(alpha, lam=lam, solver=solver)
        return s, problem.ann_vol(s.w)

    s_lo, v_lo = run(lo)
    if v_lo < target_annual_vol:
        return lo, s_lo, {"attained_vol": v_lo, "iterations": 1, "target_reached": False}
    s_hi, v_hi = run(hi)
    if v_hi > target_annual_vol:
        raise ValueError(f"vol {v_hi:.4f} > target even at λ = {hi}")
    a, b = np.log(lo), np.log(hi)
    for it in range(max_iter):
        mid = 0.5 * (a + b)
        s, v = run(np.exp(mid))
        if abs(v - target_annual_vol) <= rtol * target_annual_vol:
            return float(np.exp(mid)), s, {"attained_vol": v, "iterations": it + 3,
                                           "target_reached": True}
        a, b = (mid, b) if v > target_annual_vol else (a, mid)
    raise RuntimeError("λ calibration did not converge")
