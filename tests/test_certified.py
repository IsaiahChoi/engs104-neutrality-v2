"""Certified slope intervals (DESIGN §6; A8; CHECKS K10).

For a bound b perturbed by ±δ (maximization), with incumbent values V± and bounds B±:
    L = (V₊ − B₋)/(2δ),  H = (B₊ − V₋)/(2δ),  s = (V₊ − V₋)/(2δ).
V ≤ U* ≤ B at both points, so L ≤ (U*₊ − U*₋)/(2δ) ≤ H. Binding iff L > 0; H < 0 is impossible
at true optima (U* is nondecreasing in b) and flags a solver error.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.opt.certified import BOUND_RTOL, certified_interval, certified_interval_eff, effective_bound
from src.opt.continuous import Mandate
from src.opt.integer import PMI
from src.risk.factor_model import FACTORS
from tests.test_opt import random_instance


def test_formulas_and_flags():
    ci = certified_interval(V_plus=1.10, B_plus=1.12, V_minus=1.00, B_minus=1.01, delta=0.5)
    assert (ci.L, ci.H, ci.s) == pytest.approx((0.09, 0.12, 0.10), rel=1e-12)
    assert ci.binding and not ci.solver_error
    nb = certified_interval(V_plus=1.00, B_plus=1.02, V_minus=1.00, B_minus=1.02, delta=0.5)
    assert not nb.binding and nb.L < 0 < nb.H
    bad = certified_interval(V_plus=0.90, B_plus=0.95, V_minus=1.00, B_minus=1.00, delta=0.5)
    assert bad.H < 0 and bad.solver_error            # constructed: U fell as b loosened


def _mk(seed, beta, mip_form="perspective"):
    B, F, d, S, adv, alpha = random_instance(n=24, seed=seed)
    m = Mandate(dollar=0.02, beta=beta, style=0.05, sector=0.05, gross=2.0, position=0.2,
                liquidity_theta=None)
    return lambda b: PMI(B, F, d, S, alpha, 2.0, Mandate(**{**m.__dict__, "beta": b}), adv, K=8,
                         ell=0.01, formulation=mip_form, factor_names=FACTORS)


@pytest.mark.parametrize("seed", [51, 52])
def test_k10_intervals_contain_exact_slope(seed):
    """Two small MIQPs: the exact secant (MIPGap 0) lies in [L, H] built from MIPGap-0 solves and
    from loose-gap (2%) solves."""
    b0 = 0.01
    mk = _mk(seed, b0)
    delta = 0.1 * b0
    exact = {s: mk(b0 + s * delta).solve(mip_gap=0.0) for s in (+1, -1)}
    U = {s: exact[s].V for s in (+1, -1)}
    slope = (U[1] - U[-1]) / (2 * delta)
    tol = 1e-9 * max(abs(U[1]), abs(U[-1])) / delta
    for gap in (0.0, 0.02):
        r = exact if gap == 0.0 else {s: mk(b0 + s * delta).solve(mip_gap=gap) for s in (+1, -1)}
        ci = certified_interval(r[1].V, r[1].B, r[-1].V, r[-1].B, delta)
        assert ci.L - tol <= slope <= ci.H + tol, (gap, ci, slope)
        assert not ci.solver_error
        ce = certified_interval_eff(r[1].V, r[1].B, r[-1].V, r[-1].B, delta)   # DESIGN §6
        assert ce.contains(slope) and ce.L <= ci.L and ce.H >= ci.H, (gap, ce, slope)
        assert not ce.solver_error
    assert np.isfinite(slope)


def test_non_finite_inputs_are_refused():
    """Review M6: a missing incumbent (NaN) must not read as 'not binding'."""
    with pytest.raises(ValueError):
        certified_interval(float("nan"), 1.0, 1.0, 1.0, 0.1)
    with pytest.raises(ValueError):
        certified_interval(1.0, float("inf"), 1.0, 1.0, 0.1)


def test_effective_bound():
    """DESIGN §6: B_eff = max(B, V) + 1e-6·|V| (Gurobi's bound is valid only up to tolerance)."""
    assert BOUND_RTOL == 1e-6
    assert effective_bound(B=1.02, V=1.00) == pytest.approx(1.02 + 1e-6, rel=1e-15)
    assert effective_bound(B=0.99, V=1.00) == pytest.approx(1.00 + 1e-6, rel=1e-15)   # B below V
    assert effective_bound(B=-1.5, V=-2.0) == pytest.approx(-1.5 + 2e-6, rel=1e-15)   # |V|
    with pytest.raises(ValueError):
        effective_bound(float("nan"), 1.0)


def test_certified_interval_with_effective_bounds():
    """[L, H] from B_eff at each point (DESIGN §6; CHECKS K23): equal to the raw formula applied
    to B_eff; it contains the secant where a MIPGap-0 bound equals V and the reference slope
    differs from s by rounding (the round-2 K10 note); H < 0 is still flagged."""
    V_p, B_p, V_m, B_m, delta = 1.10, 1.12, 1.00, 0.99, 0.5         # B₋ below V₋ (tolerance)
    ci = certified_interval_eff(V_p, B_p, V_m, B_m, delta)
    raw = certified_interval(V_p, effective_bound(B_p, V_p), V_m, effective_bound(B_m, V_m), delta)
    assert (ci.L, ci.H, ci.s) == (raw.L, raw.H, raw.s)
    assert ci.L == pytest.approx((1.10 - 1.00 - 1e-6) / 1.0, rel=1e-12)
    assert ci.H == pytest.approx((1.12 + 1.1e-6 - 1.00) / 1.0, rel=1e-12)
    pt = certified_interval_eff(1.10, 1.10, 1.00, 1.00, 0.5)        # B = V at both points
    assert pt.contains(pt.s - 1e-15) and pt.contains(pt.s + 1e-15) and pt.L < pt.s < pt.H
    collapsed = certified_interval(1.10, 1.10, 1.00, 1.00, 0.5)     # raw: [s, s]
    assert collapsed.L == collapsed.H == collapsed.s and not collapsed.contains(pt.s - 1e-15)
    bad = certified_interval_eff(0.90, 0.95, 1.00, 1.00, 0.5)
    assert bad.H < 0 and bad.solver_error
    with pytest.raises(ValueError):
        certified_interval_eff(float("nan"), 1.0, 1.0, 1.0, 0.1)
