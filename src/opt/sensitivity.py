"""Bounds by shadow-price key, elasticities, and finite-difference slopes of P-RB (DESIGN §3.2).

Keys are those of src.opt.attribution.shadow_prices: dollar, beta, gross; style (a common bound
on every non-market factor) and style:<factor>; sector (common) and sector:<j>; position (u) and
liquidity (θ). The elasticity of key j is e_j = μ_j·b_j/A*, the percent change in A* per percent
change in b_j; a constraint binds iff e_j ≥ BINDING_ELASTICITY (DESIGN §6). Where A* = 0 (e.g.
α∥ with every factor exposure neutralized, so w = 0 is optimal) e_j is undefined: nan.

envelope_point is the C1 envelope check (CHECKS K15) under Isaiah's rule of 2026-10-19: a central
difference with δ = 1% of the bound; where the stencil crosses an active-set change (the
constraint's own dual is 0 at b + δ or b − δ, or the forward and backward differences differ by
more than KINK_RTOL = 1% of the central one) the point is flagged as a kink and checked with
δ = 0.1%; both slopes are recorded.
"""
from __future__ import annotations

import numpy as np

from src.opt.continuous import ContinuousProblem

BINDING_ELASTICITY = 1e-4
KINK_RTOL = 1e-2


def _split(key: str) -> tuple[str, int | None]:
    """'style:Mom' -> ('style', index of Mom) needs the problem; here only the family and raw tail."""
    fam, _, tail = key.partition(":")
    return fam, tail or None


def _index(problem: ContinuousProblem, fam: str, tail: str) -> int:
    if fam == "style":
        return (problem.style_names or [str(k) for k in problem.style_idx]).index(tail)
    return int(tail)


def bound_value(problem: ContinuousProblem, key: str) -> float:
    """The bound b behind a shadow-price key (nan for a family bound that is not common)."""
    fam, tail = _split(key)
    if fam in ("position", "liquidity"):
        cap = problem.position_caps[0 if fam == "position" else 1]
        if cap is None:
            raise ValueError(f"{fam} cap is off in this problem")
        return float(cap)
    b = problem.bound(fam)
    if tail is not None:
        return float(b[_index(problem, fam, tail)])
    if b.ndim == 0:
        return float(b)
    return float(b[0]) if np.all(b == b[0]) else float("nan")


def elasticities(problem: ContinuousProblem, sp: dict, A: float) -> dict:
    """{key: μ·b/A*} for every key in sp; nan for every key where A* = 0 (undefined)."""
    if A == 0:
        return {k: float("nan") for k in sp}
    return {k: float(v) * bound_value(problem, k) / A for k, v in sp.items()}


def snapshot(problem: ContinuousProblem):
    vals = {k: np.array(p.value, float) if p.shape else float(p.value)
            for k, p in problem.bounds.items()}
    return vals, problem.position_caps


def restore(problem: ContinuousProblem, snap) -> None:
    vals, caps = snap
    for k, v in vals.items():
        problem.bounds[k].value = v
    problem.position_caps = caps


def set_bound_by_key(problem: ContinuousProblem, key: str, value: float) -> None:
    """Set the bound behind `key` (one element for style:<f> / sector:<j>; position and liquidity
    keep the other cap)."""
    fam, tail = _split(key)
    if fam == "position":
        problem.set_position_caps(value, problem.position_caps[1])
    elif fam == "liquidity":
        problem.set_position_caps(problem.position_caps[0], value)
    elif tail is not None:
        problem.set_bound(fam, value, index=_index(problem, fam, tail))
    else:
        problem.set_bound(fam, value)


def fd_slope_rb(problem: ContinuousProblem, alpha, key: str, rel_step: float = 0.01,
                **rb_kw) -> float:
    """Central difference (A*(b + h) − A*(b − h))/(2h), h = rel_step·b, of the root-found P-RB
    value in the bound behind `key`; the problem's bounds are restored afterwards."""
    from src.opt.risk_budget import solve_risk_budget
    b0 = bound_value(problem, key)
    if not (np.isfinite(b0) and b0 > 0):
        raise ValueError(f"no relative step for {key}: bound {b0} (zero, infinite, or not common)")
    h = rel_step * b0
    snap = snapshot(problem)
    vals = []
    try:
        for sgn in (+1, -1):
            set_bound_by_key(problem, key, b0 + sgn * h)
            vals.append(solve_risk_budget(problem, alpha, **rb_kw).A)
            restore(problem, snap)
    finally:
        restore(problem, snap)
    return (vals[0] - vals[1]) / (2.0 * h)


def envelope_point(problem: ContinuousProblem, alpha, key: str, mu: float, A: float,
                   rel_step: float = 0.01, fine_step: float = 0.001, tol: float = 0.01,
                   **rb_kw) -> dict:
    """CHECKS K15 at one binding constraint (module docstring): A and mu are the root-found P-RB
    value and the key's shadow price at the problem's current bounds; rb_kw goes to
    solve_risk_budget. Returns the stencil values, both slopes, the kink flag and the verdict.
    The problem's bounds are restored afterwards."""
    from src.opt.attribution import shadow_prices
    from src.opt.risk_budget import solve_risk_budget
    b0 = bound_value(problem, key)
    if not (np.isfinite(b0) and b0 > 0):
        raise ValueError(f"no relative step for {key}: bound {b0}")
    snap = snapshot(problem)

    def at(b: float) -> tuple[float, float]:
        set_bound_by_key(problem, key, b)
        try:
            r = solve_risk_budget(problem, alpha, **rb_kw)
            return r.A, float(shadow_prices(problem, r.sol)[key])
        finally:
            restore(problem, snap)

    h = rel_step * b0
    (Ap, mp), (Am, mm) = at(b0 + h), at(b0 - h)
    fwd, bwd, ctr = (Ap - A) / h, (A - Am) / h, (Ap - Am) / (2.0 * h)
    kink = bool(mp == 0 or mm == 0 or abs(fwd - bwd) > KINK_RTOL * abs(ctr))
    rel_c = abs(ctr - mu) / abs(mu)
    out = {"key": key, "b": b0, "mu": mu, "A": A, "step": h, "A_plus": Ap, "A_minus": Am,
           "mu_plus": mp, "mu_minus": mm, "fwd": fwd, "bwd": bwd, "ctr_coarse": ctr,
           "rel_err_coarse": rel_c, "kink": kink, "fine_step": np.nan, "ctr_fine": np.nan,
           "rel_err_fine": np.nan}
    if kink:
        hf = fine_step * b0
        (Apf, _), (Amf, _) = at(b0 + hf), at(b0 - hf)
        ctr_f = (Apf - Amf) / (2.0 * hf)
        out.update(fine_step=hf, ctr_fine=ctr_f, rel_err_fine=abs(ctr_f - mu) / abs(mu))
    out["rel_err"] = out["rel_err_fine"] if kink else rel_c
    out["step_checked"] = out["fine_step"] if kink else h
    out["within"] = bool(out["rel_err"] <= tol)
    return out
