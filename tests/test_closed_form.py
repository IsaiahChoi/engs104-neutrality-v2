"""Closed forms for the equality case with a binding risk budget (DESIGN §9 A2–A4; CHECKS K6).

Aw = 0:  ν = (AΣ⁻¹A')⁻¹AΣ⁻¹α,  g = α − A'ν,  μ = √(g'Σ⁻¹g)/(2σ_m),  w* = Σ⁻¹g/(2μ),
A* = σ_m√(g'Σ⁻¹g),  TC = √(g'Σ⁻¹g / α'Σ⁻¹α) = A*/A*_unconstrained.  With A = B' (full factor
neutrality), g = α⊥ and the retained fraction is √(1 − φ). The predictor is checked against
P-RB solved numerically (root-found QP) with the equality mandates of DESIGN §7 C1.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.alpha.decompose import alignment_share, decompose
from src.opt.attribution import transfer_coefficient
from src.opt.closed_form import IDEALIZED, equality_case, idealized_mandate
from src.opt.continuous import ContinuousProblem, Mandate
from src.opt.risk_budget import SIGMA_M, solve_risk_budget
from src.risk.factor_model import FACTORS
from tests import realdata
from tests.test_opt import OFF, dense_sigma, random_instance

MONTHS = ["2008-10", "2017-12", "2020-03"]


def test_closed_form_satisfies_kkt_random():
    """The formulas solve the KKT system of max α'w s.t. Aw = 0, w'Σw ≤ σ_m² directly."""
    B, F, d, S, adv, alpha = random_instance(n=50, seed=31)
    A = np.vstack([B.T, np.ones(len(d))])
    cf = equality_case(alpha, B, F, d, A, SIGMA_M)
    Sigma = dense_sigma(B, F, d)
    np.testing.assert_allclose(A @ cf["w"], 0.0, rtol=0, atol=1e-14)
    assert float(cf["w"] @ Sigma @ cf["w"]) == pytest.approx(SIGMA_M**2, rel=1e-12)
    np.testing.assert_allclose(alpha - A.T @ cf["nu"] - 2 * cf["mu"] * Sigma @ cf["w"], 0.0,
                               rtol=0, atol=1e-12 * np.abs(alpha).max())
    assert cf["A"] == pytest.approx(float(alpha @ cf["w"]), rel=1e-12)
    assert cf["retained"] == pytest.approx(cf["tc"], rel=1e-12) and 0 < cf["tc"] < 1


def test_factor_neutral_closed_form_is_alpha_perp():
    """A4: with A = B', g = α⊥ and TC = √(1 − φ)."""
    B, F, d, S, adv, alpha = random_instance(n=50, seed=32)
    cf = equality_case(alpha, B, F, d, B.T, SIGMA_M)
    perp, _ = decompose(alpha, B, d)
    np.testing.assert_allclose(cf["g"], perp, rtol=0, atol=1e-12 * np.abs(alpha).max())
    assert cf["tc"] == pytest.approx(np.sqrt(1 - alignment_share(alpha, B, F, d)), rel=1e-10)


@pytest.mark.parametrize("ym", MONTHS)
def test_k6_real(ym):
    """CHECKS K6: numerical P-RB under the idealized mandates against the closed form."""
    di, alpha, _ = realdata.case(ym)
    m = di.model
    S = di.sector_matrix()
    mk = lambda md: ContinuousProblem(m.B, m.F, m.d, S, md, factor_names=FACTORS)
    unc = solve_risk_budget(mk(Mandate(**OFF)), alpha)
    phi = alignment_share(alpha, m.B, m.F, m.d)
    for name in IDEALIZED:
        P = mk(idealized_mandate(name))
        rb = solve_risk_budget(P, alpha)
        A = m.B.T if name == "factor" else np.vstack([m.B.T, np.ones(m.N)])
        cf = equality_case(alpha, m.B, m.F, m.d, A, SIGMA_M)
        assert rb.risk_binding
        assert abs(rb.A / cf["A"] - 1) <= 1e-6
        assert np.linalg.norm(rb.sol.w - cf["w"]) / np.linalg.norm(cf["w"]) <= 1e-6
        retained = rb.A / unc.A
        tc = transfer_coefficient(P, alpha, rb.sol.w)
        assert abs(tc / retained - 1) <= 1e-6
        assert abs(cf["retained"] / retained - 1) <= 1e-6
        if name == "factor":
            assert abs(retained / np.sqrt(1 - phi) - 1) <= 1e-6
