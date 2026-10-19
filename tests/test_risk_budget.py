"""P-RB, the fixed-risk-budget problem (DESIGN §3.2, §6; A1; CHECKS K4).

Primary path: the kept dual-simplex QP at a root-found λ. Cross-check: the explicit QCQP in
Clarabel with the risk row divided by σ_m². By A1 (KKT), the QP at λ = μ_risk has P-RB's
solution and duals, so the two must agree, and λ* must equal the QCQP's risk-row dual.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.opt.attribution import shadow_prices
from src.opt.continuous import ContinuousProblem, Mandate, load_config
from src.opt.feasibility import risk_violation, violations
from src.opt.risk_budget import (LAMBDA_MIN, ROOT_RTOL, SIGMA_M, TARGET_VOL, net_alpha,
                                 solve_qcqp, solve_risk_budget)
from src.risk.factor_model import FACTORS
from tests import realdata
from tests.test_opt import OFF, random_instance

TARGET = 0.03
K4_MONTHS = ["2008-10", "2017-12", "2020-03"]


def test_risk_budget_config():
    """MIGRATION §3 item 3: the P-RB settings live in base_mandate.yaml as numbers."""
    _, cfg = load_config()
    rb = cfg["risk_budget"]
    assert rb["target_annual_vol"] == 0.03
    assert rb["lambda_min"] == 1e-6
    assert rb["root_rtol"] == 1e-10
    assert all(isinstance(v, float) for v in rb.values())
    assert (TARGET_VOL, LAMBDA_MIN, ROOT_RTOL) == (rb["target_annual_vol"], rb["lambda_min"],
                                                   rb["root_rtol"])     # module defaults = config
    assert SIGMA_M == pytest.approx(0.03 / np.sqrt(12), rel=1e-15)


@pytest.fixture(scope="module")
def rand():
    B, F, d, S, adv, alpha = random_instance(n=60, seed=11)
    m = Mandate(dollar=0.01, beta=0.02, style=0.05, sector=0.03, gross=1.2, position=0.05,
                liquidity_theta=None)
    return B, F, d, S, adv, alpha, m


def test_root_found_volatility_hits_target(rand):
    B, F, d, S, adv, alpha, m = rand
    P = ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS)
    rb = solve_risk_budget(P, alpha, target_vol=TARGET)
    assert rb.risk_binding
    assert abs(rb.vol_ann / TARGET - 1) <= 1e-10
    assert rb.A == pytest.approx(net_alpha(P, rb.sol), rel=1e-15)
    assert rb.A == pytest.approx(rb.sol.objective + rb.lam * P.variance(rb.sol.w), rel=1e-9)
    assert violations(rb.sol.w, B, S, m, adv) == {}
    assert risk_violation(rb.sol.w, B, F, d, SIGMA_M) == 0.0


def test_warm_start_gives_the_same_root(rand):
    B, F, d, S, adv, alpha, m = rand
    P = ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS)
    cold = solve_risk_budget(P, alpha, target_vol=TARGET)
    warm = solve_risk_budget(P, alpha, target_vol=TARGET, lam_guess=1.3 * cold.lam)
    assert warm.lam == pytest.approx(cold.lam, rel=1e-9)
    np.testing.assert_allclose(warm.sol.w, cold.sol.w, rtol=0, atol=1e-9)


def test_slack_risk_budget_is_flagged():
    """A gross cap of 1% cannot reach 3%/yr: solve at λ_min and record risk_binding = False."""
    B, F, d, S, adv, alpha = random_instance(n=40, seed=12)
    P = ContinuousProblem(B, F, d, S, Mandate(**{**OFF, "gross": 0.01}), factor_names=FACTORS)
    rb = solve_risk_budget(P, alpha, target_vol=TARGET, lam_min=1e-6)
    assert not rb.risk_binding and rb.lam == 1e-6 and rb.vol_ann < TARGET
    assert np.abs(rb.sol.w).sum() == pytest.approx(0.01, rel=1e-9)


def test_qcqp_crosscheck_random(rand):
    """A1: the QP at the root-found λ and the explicit QCQP give the same w, A*, duals, and
    λ* = the QCQP's (unscaled) risk-row multiplier."""
    B, F, d, S, adv, alpha, m = rand
    P = ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS)
    rb = solve_risk_budget(P, alpha, target_vol=TARGET)
    q = solve_qcqp(P, alpha, target_vol=TARGET)
    assert np.abs(q.w - rb.sol.w).sum() / np.abs(rb.sol.w).sum() <= 1e-6
    assert q.objective == pytest.approx(rb.A, rel=1e-8)
    assert q.lam == pytest.approx(rb.lam, rel=1e-6)
    sp_qp, sp_q = shadow_prices(P, rb.sol), shadow_prices(P, q)
    binding = {k: v for k, v in sp_qp.items() if abs(v) > 1e-6 * rb.A}
    assert len(binding) >= 3
    for k, v in binding.items():
        assert sp_q[k] == pytest.approx(v, rel=1e-4), k


@pytest.mark.parametrize("ym", K4_MONTHS)
def test_k4_root_found_qp_matches_clarabel_qcqp(ym):
    """CHECKS K4 on three dates at the base mandate (α_mom, full universe)."""
    di, alpha, base = realdata.case(ym)
    P = realdata.problem(ym)
    rb = solve_risk_budget(P, alpha, target_vol=TARGET)
    q = solve_qcqp(P, alpha, target_vol=TARGET)
    assert rb.risk_binding
    assert abs(rb.vol_ann / TARGET - 1) <= 1e-10
    assert np.abs(q.w - rb.sol.w).sum() / np.abs(rb.sol.w).sum() <= 1e-5
    assert abs(q.objective / rb.A - 1) <= 1e-7
    assert abs(q.lam / rb.lam - 1) <= 1e-5
    assert violations(rb.sol.w, di.model.B, di.sector_matrix(), base, di.adv) == {}
    assert risk_violation(rb.sol.w, di.model.B, di.model.F, di.model.d, SIGMA_M) == 0.0


@pytest.mark.parametrize("ym", ["2017-12", "2020-03"])
def test_k8_scaled_and_unscaled_prb_clarabel(ym):
    """CHECKS K8 (P-RB): Clarabel on the unscaled problem (risk row ‖x‖ ≤ σ_m as is, s = 1) and
    on the scaled one (row normalized to rhs 1, objective × s_obj with |A*|·s_obj in [1, 100])
    give the same w (max |Δw| ≤ 1e-7, weights in fractions of AUM); the unscaled values round-trip."""
    from src.opt.integer import choose_s_obj
    _, alpha, _ = realdata.case(ym)
    P = realdata.problem(ym)
    raw = solve_qcqp(P, alpha, normalize=False, obj_scale=1.0)
    s = choose_s_obj(raw.objective)
    assert 1.0 <= abs(raw.objective) * s <= 100.0
    scaled = solve_qcqp(P, alpha, normalize=True, obj_scale=s)
    assert np.abs(scaled.w - raw.w).max() <= 1e-7
    assert scaled.objective == pytest.approx(raw.objective, rel=1e-8)
    assert scaled.lam == pytest.approx(raw.lam, rel=1e-6)
