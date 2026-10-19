"""Elasticities and the envelope theorem for P-RB (DESIGN §3.2, §6; A5; CHECKS K7).

e_j = μ_j·b_j/A*. The envelope theorem dA*/db_j = μ_j is checked by central differences of the
root-found P-RB value (each side re-root-finds λ), with δ = 1% of the bound.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.opt.attribution import shadow_prices
from src.opt.continuous import ContinuousProblem, Mandate
from src.opt.risk_budget import solve_risk_budget
from src.opt.sensitivity import (BINDING_ELASTICITY, bound_value, elasticities, fd_slope_rb,
                                 restore, set_bound_by_key, snapshot)
from src.risk.factor_model import FACTORS
from tests import realdata
from tests.test_opt import random_instance

K7_MONTHS = ["2017-12", "2020-03"]


@pytest.fixture(scope="module")
def rand():
    B, F, d, S, adv, alpha = random_instance(n=60, seed=41)
    m = Mandate(dollar=0.01, beta=0.02, style=0.05, sector=0.03, gross=1.2, position=0.05,
                liquidity_theta=0.05)
    return ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS), alpha


def test_bound_values_and_elasticity_definition(rand):
    P, alpha = rand
    rb = solve_risk_budget(P, alpha)
    sp = shadow_prices(P, rb.sol)
    e = elasticities(P, sp, rb.A)
    assert bound_value(P, "gross") == 1.2 and bound_value(P, "position") == 0.05
    assert bound_value(P, "liquidity") == 0.05 and bound_value(P, "style") == 0.05
    assert bound_value(P, f"style:{P.style_names[2]}") == 0.05 and bound_value(P, "sector:1") == 0.03
    for k, v in sp.items():
        assert e[k] == pytest.approx(v * bound_value(P, k) / rb.A, rel=1e-15)


def test_set_bound_by_key_and_restore(rand):
    P, alpha = rand
    snap = snapshot(P)
    set_bound_by_key(P, f"style:{P.style_names[1]}", 0.2)
    set_bound_by_key(P, "sector:2", 0.5)
    set_bound_by_key(P, "liquidity", 0.07)
    assert P.bound("style")[1] == 0.2 and P.bound("style")[0] == 0.05
    assert P.bound("sector")[2] == 0.5 and P.position_caps == (0.05, 0.07)
    restore(P, snap)
    assert (P.bound("style") == 0.05).all() and (P.bound("sector") == 0.03).all()
    assert P.position_caps == (0.05, 0.05)
    np.testing.assert_array_equal(P.bound("position"), snap[0]["position"])


def test_envelope_random(rand):
    P, alpha = rand
    rb = solve_risk_budget(P, alpha)
    sp = shadow_prices(P, rb.sol)
    e = elasticities(P, sp, rb.A)
    checked = 0
    for k, v in sp.items():
        if e[k] >= BINDING_ELASTICITY:
            assert fd_slope_rb(P, alpha, k, rel_step=1e-3, lam_guess=rb.lam) == pytest.approx(v, rel=0.01), k
            checked += 1
    assert checked >= 4


@pytest.mark.parametrize("ym", K7_MONTHS)
def test_k7_envelope_real(ym):
    """CHECKS K7: every constraint with e_j ≥ 1e-4 at base, δ = 1% of the bound."""
    _, alpha, _ = realdata.case(ym)
    P = realdata.problem(ym)
    rb = solve_risk_budget(P, alpha)
    sp = shadow_prices(P, rb.sol)
    e = elasticities(P, sp, rb.A)
    keys = [k for k in sp if e[k] >= BINDING_ELASTICITY]
    assert len(keys) >= 2
    bad = {}
    for k in keys:
        fd = fd_slope_rb(P, alpha, k, rel_step=0.01, lam_guess=rb.lam)
        if abs(fd / sp[k] - 1) > 0.01:
            bad[k] = (fd, sp[k], e[k])
    assert not bad, bad


def test_fd_slope_refuses_zero_infinite_or_missing_bounds(rand):
    """Review M7: zero, infinite, non-common, or switched-off bounds raise instead of returning
    NaN or dividing by zero."""
    P, alpha = rand
    snap = snapshot(P)
    set_bound_by_key(P, "beta", 0.0)
    with pytest.raises(ValueError):
        fd_slope_rb(P, alpha, "beta")
    set_bound_by_key(P, f"style:{P.style_names[0]}", float("inf"))
    with pytest.raises(ValueError):
        fd_slope_rb(P, alpha, f"style:{P.style_names[0]}")
    with pytest.raises(ValueError):
        fd_slope_rb(P, alpha, "style")                      # no longer a common bound
    restore(P, snap)
    P.set_position_caps(None, 0.05)
    with pytest.raises(ValueError):
        bound_value(P, "position")
    restore(P, snap)
