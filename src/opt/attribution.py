"""Shadow prices, constraint attribution, and the transfer coefficient (brief §3.2; RQ1, RQ2).

Dual sign. ContinuousProblem writes every inequality as `expr <= bound`, and CVXPY returns one
dual per inequality. DUAL_SIGN maps that dual to μ = dU*/d(bound) for the maximization. Its
value is not assumed: tests/test_opt.py::test_envelope_theorem compares central
finite-difference slopes of U* with DUAL_SIGN × (dual) for every constraint family under both
solvers, and asserts the sign.

Constraint attribution (Stubbs & Vandenbussche). Write G(w) = α − 2λΣw for the gradient of the
smooth part. KKT stationarity of the problem, taken in w⁺ for held-long names and in w⁻ for
held-short names, gives name by name
    G(w*) = Σ_c a_c,
where each family's implied-alpha adjustment a_c (an N-vector) is
    dollar    (μ_up − μ_lo) 1          beta     (μ_up − μ_lo) B_mkt
    style     B_style (μ_up − μ_lo)     sector   S (μ_up − μ_lo)
    trading   τ_up − τ_down (|·| ≤ κ)
    gross     +μ_G on longs, −μ_G on shorts
    position  +μ_pos⁺ on longs, −μ_pos⁻ on shorts
    borrow    −c on shorts
For names held at zero, the L1 kink (gross, borrow, trading) is not unique by name; the whole
remaining adjustment is reported as `inactive`. On held names the remainder must vanish
(`residual`, a KKT check). Then w* = w_α + Σ_c w_c with w_α = (2λ)⁻¹Σ⁻¹α and
w_c = −(2λ)⁻¹Σ⁻¹a_c, and expected alpha splits as α'w* = α'w_α + Σ_c α'w_c.

Transfer coefficient (Clarke, de Silva & Thorley 2002), in the risk metric:
    TC = α'w / sqrt((α'Σ⁻¹α)(w'Σw)),
the cosine between w and the unconstrained optimum Σ⁻¹α; TC = 1 without constraints or costs.
`tc_diagonal` is CdST's correlation of α_i/σ_i with w_iσ_i, σ_i = √d_i, for comparison.
"""
from __future__ import annotations

import numpy as np

from src.opt.continuous import ContinuousProblem, Solution

DUAL_SIGN = 1.0
HELD_TOL = 1e-7          # a name is held long (short) if w⁺_i (w⁻_i) exceeds this
FAMILY_ORDER = ["dollar", "beta", "style", "sector", "gross", "position", "borrow", "trading",
                "inactive"]


def mu(sol: Solution, family: str, side: str) -> np.ndarray:
    return DUAL_SIGN * sol.duals[(family, side)]


def _two_sided(sol: Solution, family: str) -> np.ndarray:
    return mu(sol, family, "upper") - mu(sol, family, "lower")


def shadow_prices(problem: ContinuousProblem, sol: Solution) -> dict:
    """dU*/d(bound) for each active family. Style and sector also per factor / per sector
    (key 'style:<factor>', 'sector:<j>'); their family total is the slope for a common bound.
    Position: 'position' is dU*/du over names capped by u; 'liquidity' is dU*/dθ."""
    out = {}
    for fam in ("dollar", "beta"):
        if fam in problem.bounds:
            out[fam] = float((mu(sol, fam, "upper") + mu(sol, fam, "lower")).sum())
    if "gross" in problem.bounds:
        out["gross"] = float(mu(sol, "gross", "upper").sum())
    if "style" in problem.bounds:
        per = mu(sol, "style", "upper") + mu(sol, "style", "lower")
        out["style"] = float(per.sum())
        names = problem.style_names or [str(k) for k in problem.style_idx]
        out.update({f"style:{n}": float(v) for n, v in zip(names, per)})
    if "sector" in problem.bounds:
        per = mu(sol, "sector", "upper") + mu(sol, "sector", "lower")
        out["sector"] = float(per.sum())
        out.update({f"sector:{j}": float(v) for j, v in enumerate(per)})
    if "position" in problem.bounds:
        per = mu(sol, "position", "long") + mu(sol, "position", "short")
        u, theta = problem.position_caps            # the caps behind the current ub
        ub = problem.bound("position")
        if u is not None:
            by_u = np.isclose(ub, u, rtol=0, atol=1e-15)
            out["position"] = float(per[by_u].sum())
        if theta is not None:
            liq = np.nan_to_num(problem.adv / problem.mandate.aum_usd, nan=0.0)
            by_liq = ub < (u if u is not None else np.inf)
            out["liquidity"] = float((per * liq)[by_liq].sum())
    return out


def sigma_inv(problem: ContinuousProblem, X: np.ndarray) -> np.ndarray:
    """Σ⁻¹X for Σ = BFB' + D, by the Woodbury identity."""
    B, F, d = problem.B, problem.F, problem.d
    Dinv_X = X / d[:, None] if X.ndim == 2 else X / d
    Dinv_B = B / d[:, None]
    core = np.linalg.inv(F) + B.T @ Dinv_B
    return Dinv_X - Dinv_B @ np.linalg.solve(core, B.T @ Dinv_X)


def sigma_apply(problem: ContinuousProblem, x: np.ndarray) -> np.ndarray:
    return problem.B @ (problem.F @ (problem.B.T @ x)) + problem.d * x


def implied_alpha_adjustments(problem: ContinuousProblem, sol: Solution,
                              held_tol: float = HELD_TOL) -> dict[str, np.ndarray]:
    """a_c for each family plus 'inactive' (zero names) and 'residual' (held names; ≈ 0)."""
    N = problem.N
    long, short = sol.wp > held_tol, sol.wm > held_tol
    zero = ~(long | short)
    sgn = long.astype(float) - short.astype(float)
    a = {}
    if "dollar" in problem.bounds:
        a["dollar"] = np.full(N, _two_sided(sol, "dollar").sum())
    if "beta" in problem.bounds:
        a["beta"] = problem.B[:, problem.mkt] * _two_sided(sol, "beta").sum()
    if "style" in problem.bounds:
        a["style"] = problem.B[:, problem.style_idx] @ _two_sided(sol, "style")
    if "sector" in problem.bounds:
        a["sector"] = problem.S @ _two_sided(sol, "sector")
    if "gross" in problem.bounds:
        a["gross"] = mu(sol, "gross", "upper").sum() * sgn
    if "position" in problem.bounds:
        a["position"] = mu(sol, "position", "long") * long - mu(sol, "position", "short") * short
    a["borrow"] = -problem.mandate.borrow_monthly * short
    # On zero names the trading dual is arbitrary within [−κ, κ] (the L1 kink); it goes to
    # `inactive` with the rest of their adjustment, as stated above (REVIEW 3, concern 2).
    a["trading"] = np.where(zero, 0.0, mu(sol, "trade", "up") - mu(sol, "trade", "down"))
    G = sol.alpha - 2.0 * sol.lam * sigma_apply(problem, sol.w)
    rest = G - sum(a.values())
    a["inactive"] = np.where(zero, rest, 0.0)
    a["residual"] = np.where(zero, 0.0, rest)
    return a


def attribution(problem: ContinuousProblem, sol: Solution) -> dict:
    """Split w* and expected alpha α'w* into the ideal portfolio w_α and one portfolio per
    family (module docstring). Returns per-family alpha contributions and the pieces."""
    a = implied_alpha_adjustments(problem, sol)
    two_lam = 2.0 * sol.lam
    w_alpha = sigma_inv(problem, sol.alpha) / two_lam
    w_c = {k: -sigma_inv(problem, v) / two_lam for k, v in a.items()}
    recon = w_alpha + sum(w_c.values())
    return {
        "alpha_ideal": float(sol.alpha @ w_alpha),
        "alpha_by_family": {k: float(sol.alpha @ v) for k, v in w_c.items()},
        "alpha_total": float(sol.alpha @ sol.w),
        "w_alpha": w_alpha, "w_family": w_c, "adjustments": a,
        "reconstruction_error": float(np.abs(recon - sol.w).max()),
    }


def transfer_coefficient(problem: ContinuousProblem, alpha: np.ndarray, w: np.ndarray) -> float:
    num = float(alpha @ w)
    den = np.sqrt(float(alpha @ sigma_inv(problem, alpha)) * float(w @ sigma_apply(problem, w)))
    return num / den


def tc_diagonal(alpha: np.ndarray, w: np.ndarray, d: np.ndarray) -> float:
    sigma = np.sqrt(d)
    return float(np.corrcoef(alpha / sigma, w * sigma)[0, 1])
