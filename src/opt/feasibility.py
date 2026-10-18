"""Independent feasibility check (brief §8 item 4).

Recomputes every active constraint of brief §3.2 from the returned weights alone, with NumPy:
no CVXPY objects, no solver output other than w, and its own position-bound formula. Mandate
fields mean what they mean in src/opt/continuous.py (None = family off).
"""
from __future__ import annotations

import numpy as np


def constraint_values(w, B, S, mandate, adv=None, mkt: int = 0) -> dict[str, tuple[float, float]]:
    """family -> (value, bound); feasible iff value <= bound (+ tolerance)."""
    w = np.asarray(w, float)
    B, S = np.asarray(B, float), np.asarray(S, float)
    out = {}
    if mandate.dollar is not None:
        out["dollar"] = (abs(w.sum()), mandate.dollar)
    exposures = B.T @ w
    if mandate.beta is not None:
        out["beta"] = (abs(exposures[mkt]), mandate.beta)
    if mandate.style is not None:
        style = np.delete(exposures, mkt)
        out["style"] = (np.abs(style).max(), mandate.style)
    if mandate.sector is not None:
        out["sector"] = (np.abs(S.T @ w).max(), mandate.sector)
    if mandate.gross is not None:
        out["gross"] = (np.abs(w).sum(), mandate.gross)
    caps = []
    if mandate.position is not None:
        caps.append(np.full(len(w), mandate.position))
    if mandate.liquidity_theta is not None:
        a = np.where(np.isfinite(np.asarray(adv, float)), np.asarray(adv, float), 0.0)
        caps.append(mandate.liquidity_theta * a / mandate.aum_usd)
    if caps:
        cap = np.min(np.vstack(caps), axis=0)
        out["position"] = (float(np.max(np.abs(w) - cap)), 0.0)   # max excess over the cap
    return {k: (float(v), float(b)) for k, (v, b) in out.items()}


def violations(w, B, S, mandate, adv=None, mkt: int = 0, tol: float = 1e-7) -> dict[str, float]:
    """family -> amount by which the constraint is violated beyond tol (empty if feasible)."""
    vals = constraint_values(w, B, S, mandate, adv, mkt)
    return {k: v - b for k, (v, b) in vals.items() if v > b + tol}
