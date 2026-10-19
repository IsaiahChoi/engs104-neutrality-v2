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


# ----- v2 additions (S1): the risk row of P-RB and the integer rows of P-MI (CHECKS K11) -----

def risk_violation(w, B, F, d, sigma_m: float, rtol: float = 1e-8) -> float:
    """Ex-ante variance (B'w)'F(B'w) + Σ d_i w_i² minus σ_m², if it exceeds σ_m² by more than
    rtol·σ_m²; else 0.0."""
    w = np.asarray(w, float)
    e = np.asarray(B, float).T @ w
    var = float(e @ np.asarray(F, float) @ e + np.asarray(d, float) @ (w * w))
    return var - sigma_m**2 if var > sigma_m**2 * (1.0 + rtol) else 0.0


def _cap_vector(n: int, mandate, adv) -> np.ndarray:
    """Per-name cap min(u, θ·ADV_i/AUM), computed here from the Mandate fields (+inf if both off)."""
    cap = np.full(n, np.inf)
    if mandate.position is not None:
        cap = np.minimum(cap, mandate.position)
    if mandate.liquidity_theta is not None:
        a = np.where(np.isfinite(np.asarray(adv, float)), np.asarray(adv, float), 0.0)
        cap = np.minimum(cap, mandate.liquidity_theta * a / mandate.aum_usd)
    return cap


def integer_violations(w, zp, zm, K: int | None, ell: float, mandate, adv=None,
                       tol: float = 1e-7) -> dict[str, float]:
    """P-MI rows from (w, z⁺, z⁻) alone: binary z, one side per name, linking (w_i > 0 needs
    z⁺_i = 1, w_i < 0 needs z⁻_i = 1, |w_i| ≤ cap_i), minimum position (held names |w_i| ≥ ℓ),
    and cardinality (Σ(z⁺ + z⁻) ≤ K and #{|w_i| > tol} ≤ K). Name -> worst violation."""
    w, zp, zm = (np.asarray(a, float) for a in (w, zp, zm))
    cap = _cap_vector(len(w), mandate, adv)
    out = {}
    frac = max(np.abs(zp - np.round(zp)).max(), np.abs(zm - np.round(zm)).max())
    if frac > tol:
        out["binary"] = float(frac)
    zp, zm = np.round(zp), np.round(zm)
    both = (zp + zm - 1.0).max()
    if both > tol:
        out["one_sided"] = float(both)
    link = max(np.max(np.where(zp < 0.5, w, 0.0)), np.max(np.where(zm < 0.5, -w, 0.0)),
               np.max(np.abs(w) - cap * (zp + zm)))
    if link > tol:
        out["linking"] = float(link)
    short = np.max(np.where(zp > 0.5, ell - w, -np.inf), initial=-np.inf)
    short = max(short, np.max(np.where(zm > 0.5, ell + w, -np.inf), initial=-np.inf))
    if short > tol:
        out["min_position"] = float(short)
    if K is not None:
        card = max((zp + zm).sum(), float((np.abs(w) > tol).sum())) - K
        if card > 0:
            out["cardinality"] = float(card)
    return out


def prb_violations(w, B, F, d, S, mandate, sigma_m: float, adv=None, mkt: int = 0,
                   tol: float = 1e-7, risk_rtol: float = 1e-8,
                   style_bounds=None) -> dict[str, float]:
    """Every P-RB row: the mandate families plus the risk budget. style_bounds (one bound per
    non-market factor, in factor order) replaces the common mandate.style when a single style
    factor is swept."""
    out = violations(w, B, S, mandate, adv, mkt, tol)
    if style_bounds is not None:
        style = np.abs(np.delete(np.asarray(B, float).T @ np.asarray(w, float), mkt))
        excess = float(np.max(style - np.asarray(style_bounds, float)))
        out.pop("style", None)
        if excess > tol:
            out["style"] = excess
    r = risk_violation(w, B, F, d, sigma_m, risk_rtol)
    if r > 0:
        out["risk"] = r
    return out


def pmi_violations(w, zp, zm, B, S, mandate, K: int | None, ell: float, adv=None,
                   mkt: int = 0, tol: float = 1e-7) -> dict[str, float]:
    """Every P-MI row: the mandate families (no risk row; λ* prices risk) plus the integer rows."""
    return {**violations(w, B, S, mandate, adv, mkt, tol),
            **integer_violations(w, zp, zm, K, ell, mandate, adv, tol)}
