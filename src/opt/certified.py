"""Certified slope interval for a re-solve estimate (DESIGN §6; A8). Maximization, original units.

A bound b is perturbed to b ± δ (δ absolute). With incumbent values V± (feasible, so V ≤ U*) and
final bounds B± (U* ≤ B) at the two points:
    L = (V₊ − B₋)/(2δ),   H = (B₊ − V₋)/(2δ),   s = (V₊ − V₋)/(2δ),
and the true secant (U*₊ − U*₋)/(2δ) lies in [L, H]. A case is binding iff L > 0. H < 0 is
impossible at true optima (U* is nondecreasing in b) and is a solver-error flag.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CertifiedSlope:
    L: float
    H: float
    s: float

    @property
    def binding(self) -> bool:
        return self.L > 0

    @property
    def solver_error(self) -> bool:
        return self.H < 0

    def contains(self, slope: float, tol: float = 0.0) -> bool:
        return self.L - tol <= slope <= self.H + tol


def certified_interval(V_plus: float, B_plus: float, V_minus: float, B_minus: float,
                       delta: float) -> CertifiedSlope:
    if not delta > 0:
        raise ValueError("delta must be positive")
    vals = (V_plus, B_plus, V_minus, B_minus)
    if not all(math.isfinite(v) for v in vals):
        raise ValueError(f"non-finite value or bound {vals}: no certified interval (record the "
                         "case as missing, not as non-binding)")
    two = 2.0 * delta
    return CertifiedSlope(L=(V_plus - B_minus) / two, H=(B_plus - V_minus) / two,
                          s=(V_plus - V_minus) / two)
