"""Bounds by shadow-price key, elasticities, and finite-difference slopes of P-RB (DESIGN §3.2).

Keys are those of src.opt.attribution.shadow_prices: dollar, beta, gross; style (a common bound
on every non-market factor) and style:<factor>; sector (common) and sector:<j>; position (u) and
liquidity (θ). The elasticity of key j is e_j = μ_j·b_j/A*, the percent change in A* per percent
change in b_j; a constraint binds iff e_j ≥ BINDING_ELASTICITY (DESIGN §6).
"""
from __future__ import annotations

import numpy as np

from src.opt.continuous import ContinuousProblem

BINDING_ELASTICITY = 1e-4


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
    """{key: μ·b/A*} for every key in sp."""
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
