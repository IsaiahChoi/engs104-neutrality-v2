"""Certified slope interval for a re-solve estimate (DESIGN §6; A8). Maximization, original units.

A bound b is perturbed to b ± δ (δ absolute). With incumbent values V± (feasible, so V ≤ U*) and
final bounds B± (U* ≤ B) at the two points:
    L = (V₊ − B₋)/(2δ),   H = (B₊ − V₋)/(2δ),   s = (V₊ − V₋)/(2δ),
and the true secant (U*₊ − U*₋)/(2δ) lies in [L, H]. A case is binding iff L > 0. H < 0 is
impossible at true optima (U* is nondecreasing in b) and is a solver-error flag.

Gurobi's bound is valid only up to its tolerances, so the experiments use B_eff = max(B, V) +
1e-6·|V| at each point (DESIGN §6; CHECKS K22, K23): certified_interval_eff. certified_interval
is the formula on whatever bounds it is given (the raw-B interval is recorded alongside).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

BOUND_RTOL = 1e-6                  # B_eff slack, relative to |V| (DESIGN §6)


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


def effective_bound(B: float, V: float, rtol: float = BOUND_RTOL) -> float:
    """B_eff = max(B, V) + rtol·|V| (DESIGN §6)."""
    if not (math.isfinite(B) and math.isfinite(V)):
        raise ValueError(f"non-finite bound or value ({B}, {V}): no effective bound")
    return max(B, V) + rtol * abs(V)


def certified_interval_eff(V_plus: float, B_plus: float, V_minus: float, B_minus: float,
                           delta: float) -> CertifiedSlope:
    """[L, H] with B_eff at both points (DESIGN §6); raw B± as returned by the solver."""
    for v in (V_plus, B_plus, V_minus, B_minus):
        if not math.isfinite(v):
            raise ValueError(f"non-finite value or bound {v}: no certified interval (record the "
                             "case as missing, not as non-binding)")
    return certified_interval(V_plus, effective_bound(B_plus, V_plus), V_minus,
                              effective_bound(B_minus, V_minus), delta)
