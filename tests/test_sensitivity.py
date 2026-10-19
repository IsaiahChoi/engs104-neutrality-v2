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
from src.opt.sensitivity import (BINDING_ELASTICITY, bound_value, elasticities, envelope_point, fd_slope_rb,
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


# ---- S2 additions ----

def test_elasticities_undefined_at_zero_value():
    """e_j = μ_j·b_j/A* is undefined where A* = 0 (e.g. α∥ with every factor exposure
    neutralized, where w = 0 is optimal): nan, never a ZeroDivisionError; finite otherwise."""
    B, F, d, S, adv, _ = random_instance(n=20, seed=71)
    P = ContinuousProblem(B, F, d, S, Mandate(), adv=adv, factor_names=FACTORS)
    sp = {"dollar": 0.1, "beta": 0.0, "gross": 0.02}
    e = elasticities(P, sp, 0.0)
    assert set(e) == set(sp) and all(np.isnan(v) for v in e.values())
    e = elasticities(P, sp, 2.0)
    assert e["dollar"] == pytest.approx(0.1 * 0.02 / 2.0) and e["beta"] == 0.0


def test_envelope_point_refines_a_stencil_that_crosses_an_active_set_change():
    """Isaiah's K15 rule (2026-10-19): central difference at δ = 1% of the bound; where the stencil
    crosses an active-set change (the constraint's dual is 0 at b + δ or b − δ, or the forward and
    backward differences differ by more than 1% of the central one), the point is a kink and is
    checked at δ = 0.1%; both slopes are recorded. C1 2011-08, style:CMA (e = 1.02e-4): the
    CMA bound stops binding inside +1%, the 1% difference misses μ by 2.3%, the 0.1% one matches."""
    di, alpha, base = realdata.case("2011-08")
    P = realdata.problem("2011-08")
    rb = solve_risk_budget(P, alpha)
    mu = shadow_prices(P, rb.sol)["style:CMA"]
    r = envelope_point(P, alpha, "style:CMA", mu, rb.A, lam_guess=rb.lam)
    assert r["kink"] and r["mu_plus"] == 0.0 and r["mu_minus"] > 0
    assert r["rel_err_coarse"] > 1e-2 and r["rel_err_fine"] <= 1e-2
    assert r["rel_err"] == r["rel_err_fine"] and r["step_checked"] == pytest.approx(1e-3 * 0.10)
    assert P.bound("style")[P.style_names.index("CMA")] == 0.10        # bounds restored
    # a smooth point (dollar, e ≈ 3e-2 here): not refined unless its one-sided slopes differ
    mu_d = shadow_prices(P, rb.sol)["dollar"]
    rd = envelope_point(P, alpha, "dollar", mu_d, rb.A, lam_guess=rb.lam)
    assert rd["rel_err"] <= 1e-2
    assert rd["kink"] == (rd["mu_plus"] == 0 or rd["mu_minus"] == 0
                          or abs(rd["fwd"] - rd["bwd"]) > 1e-2 * abs(rd["ctr_coarse"]))
