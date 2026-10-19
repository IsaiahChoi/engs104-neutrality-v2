"""Alpha decomposition, alignment share φ, and normalization (DESIGN §5; A4; CHECKS K5).

α⊥ = α − B(B'D⁻¹B)⁻¹B'D⁻¹α, α∥ = α − α⊥, φ = α∥'Σ⁻¹α∥ / α'Σ⁻¹α. The tests check the
theory, not the code's own formulas: the residual is D⁻¹-orthogonal to the loadings, Σ⁻¹α⊥ =
D⁻¹α⊥ (Woodbury), the split is Σ⁻¹-orthogonal, and α⊥ alone under the risk budget carries no
factor exposure and gives zero factor-bound shadow prices.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.alpha.decompose import (alignment_share, alpha_set, decompose, information_ratio,
                                 normalize_ir, sigma_solve)
from src.opt.attribution import shadow_prices
from src.opt.continuous import ContinuousProblem, Mandate
from src.opt.risk_budget import solve_risk_budget
from src.opt.sensitivity import elasticities
from src.risk.factor_model import FACTORS
from tests import realdata
from tests.test_opt import OFF, dense_sigma, random_instance

MONTHS = ["2008-10", "2017-12", "2020-03"]


def _checks(alpha, B, F, d):
    perp, par = decompose(alpha, B, d)
    BtDi = B.T / d
    assert np.linalg.norm(BtDi @ perp) <= 1e-10 * np.linalg.norm(BtDi @ alpha)
    # α∥ := α − α⊥, so the split is exact by definition; the recomputed float sum is within one
    # rounding unit of the largest component (bitwise equality is impossible where α⊥_i and α∥_i
    # cancel; PROGRESS S1, K5 note).
    scale = max(np.abs(alpha).max(), np.abs(perp).max(), np.abs(par).max())
    assert np.abs((perp + par) - alpha).max() <= np.spacing(scale)
    np.testing.assert_allclose(sigma_solve(B, F, d, perp), perp / d, rtol=1e-10, atol=0)
    q = lambda x: float(x @ sigma_solve(B, F, d, x))
    assert q(alpha) == pytest.approx(float(perp @ (perp / d)) + q(par), rel=1e-10)
    phi = alignment_share(alpha, B, F, d)
    assert 0.0 <= phi <= 1.0 and phi == pytest.approx(q(par) / q(alpha), rel=1e-12)
    assert alignment_share(perp, B, F, d) <= 1e-12
    assert alignment_share(par, B, F, d) == pytest.approx(1.0, abs=1e-10)
    return perp, par, phi


def test_decomposition_random():
    B, F, d, S, adv, alpha = random_instance(n=80, seed=21)
    _checks(alpha, B, F, d)
    np.testing.assert_allclose(sigma_solve(B, F, d, alpha),
                               np.linalg.solve(dense_sigma(B, F, d), alpha), rtol=1e-9, atol=0)


def test_normalization_matches_ir():
    B, F, d, S, adv, alpha = random_instance(n=80, seed=22)
    perp, par = decompose(alpha, B, d)
    ir = information_ratio(alpha, B, F, d)
    for x in (perp, par):
        xn = normalize_ir(x, ir, B, F, d)
        assert information_ratio(xn, B, F, d) == pytest.approx(ir, rel=1e-12)
        assert np.allclose(xn / np.linalg.norm(xn), x / np.linalg.norm(x), rtol=0, atol=1e-14)
    s = alpha_set(alpha, B, F, d)
    assert set(s["alphas"]) == {"mom", "perp", "par"}
    assert s["phi"]["perp"] <= 1e-12 and s["phi"]["par"] == pytest.approx(1.0, abs=1e-10)
    assert s["phi"]["mom"] == pytest.approx(alignment_share(alpha, B, F, d), rel=1e-15)


@pytest.mark.parametrize("ym", MONTHS)
def test_k5_real(ym):
    """CHECKS K5 on real dates (α_mom, full universe)."""
    di, alpha, _ = realdata.case(ym)
    m = di.model
    perp, _, _ = _checks(alpha, m.B, m.F, m.d)
    perp_n = alpha_set(alpha, m.B, m.F, m.d)["alphas"]["perp"]
    # α⊥ under the risk budget alone: zero factor exposure ...
    P0 = ContinuousProblem(m.B, m.F, m.d, di.sector_matrix(), Mandate(**OFF), factor_names=FACTORS)
    rb0 = solve_risk_budget(P0, perp_n)
    assert rb0.risk_binding and np.abs(P0.exposures(rb0.sol.w)).max() <= 1e-8
    # ... so factor bounds added at base are inactive: every factor-bound elasticity ≤ 1e-6
    Pf = ContinuousProblem(m.B, m.F, m.d, di.sector_matrix(),
                           Mandate(**{**OFF, "beta": 0.05, "style": 0.10}), factor_names=FACTORS)
    rbf = solve_risk_budget(Pf, perp_n)
    e = elasticities(Pf, shadow_prices(Pf, rbf.sol), rbf.A)
    factor_keys = ["beta", *[f"style:{n}" for n in Pf.style_names]]
    assert max(abs(e[k]) for k in factor_keys) <= 1e-6
    np.testing.assert_allclose(rbf.sol.w, rb0.sol.w, rtol=0, atol=1e-9)
