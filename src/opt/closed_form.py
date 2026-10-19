"""Closed-form predictor for equality-constrained mandates with a binding risk budget
(DESIGN §9 A2–A4; §7 C1 idealized mandates).

    maximize α'w  s.t.  Aw = 0,  w'Σw ≤ σ_m²        (no other constraints, no costs)
KKT: α − A'ν − 2μΣw = 0, Aw = 0, w'Σw = σ_m². Hence
    ν = (AΣ⁻¹A')⁻¹AΣ⁻¹α,  g = α − A'ν,  μ = √(g'Σ⁻¹g)/(2σ_m),  w* = Σ⁻¹g/(2μ),
    A* = α'w* = σ_m√(g'Σ⁻¹g),
and the retained fraction A*/A*_unconstrained = √(g'Σ⁻¹g / α'Σ⁻¹α) = TC (A3). With A = B'
(all six factor exposures zero), g = α⊥ and the retained fraction is √(1 − φ) (A4).
"""
from __future__ import annotations

import numpy as np

from src.alpha.decompose import sigma_solve
from src.opt.continuous import Mandate

IDEALIZED = ("factor", "factor_dollar")     # (i) all six exposures = 0; (ii) plus dollar neutral


def idealized_mandate(name: str) -> Mandate:
    """DESIGN §7 C1 idealized mandates as P-RB inputs: equality bounds, nothing else, no costs."""
    if name not in IDEALIZED:
        raise ValueError(name)
    return Mandate(dollar=0.0 if name == "factor_dollar" else None, beta=0.0, style=0.0,
                   sector=None, gross=None, position=None, liquidity_theta=None,
                   borrow_annual=0.0, trade_cost=0.0)


def equality_case(alpha, B, F, d, A, sigma_m: float) -> dict:
    """The A2/A3 quantities for constraint matrix A (m×N). Returns g, ν, μ, w, A (the value),
    A_unconstrained, tc and retained (equal by A3)."""
    alpha, A = np.asarray(alpha, float), np.atleast_2d(np.asarray(A, float))
    Si_alpha = sigma_solve(B, F, d, alpha)
    Si_At = sigma_solve(B, F, d, A.T)
    nu = np.linalg.solve(A @ Si_At, A @ Si_alpha)
    g = alpha - A.T @ nu
    Si_g = Si_alpha - Si_At @ nu
    q_g, q_a = float(g @ Si_g), float(alpha @ Si_alpha)
    mu = np.sqrt(q_g) / (2.0 * sigma_m)
    value, unc = sigma_m * np.sqrt(q_g), sigma_m * np.sqrt(q_a)
    return {"g": g, "nu": nu, "mu": float(mu), "w": Si_g / (2.0 * mu), "A": float(value),
            "A_unconstrained": float(unc), "tc": float(np.sqrt(q_g / q_a)),
            "retained": float(value / unc)}
