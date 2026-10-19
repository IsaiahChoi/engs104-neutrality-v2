"""P-MI wrapper (DESIGN §3.4, §6): objective scaling, incumbent value V, both relaxation duals
(failures recorded, not fatal), Work and WorkLimit; CHECKS K8 (scaling) and K13 (consistency).
"""
from __future__ import annotations

import numpy as np
import pytest

import src.opt.miqp as miqp
from experiments.instances import miqp_mandate, restricted, subsample
from src.opt.continuous import ContinuousProblem, Mandate, load_config
from src.opt.feasibility import pmi_violations
from src.opt.integer import PMI, exact_objective
from src.opt.risk_budget import net_alpha, solve_risk_budget
from src.risk.factor_model import FACTORS
from tests.test_opt import dense_sigma, random_instance

FORMS = ["bigm", "perspective"]


def mandate(**kw):
    base = dict(dollar=0.02, beta=0.05, style=0.10, sector=0.05, gross=2.0, position=0.2,
                liquidity_theta=None)
    return Mandate(**{**base, **kw})


def small(seed=61, n=20, form="perspective", s_obj=1.0, K=8, **mk):
    B, F, d, S, adv, alpha = random_instance(n=n, seed=seed)
    return PMI(B, F, d, S, alpha, 2.0, mandate(**mk), adv, K=K, ell=0.01, formulation=form,
               s_obj=s_obj, factor_names=FACTORS), (B, F, d, S, adv, alpha)


def test_exact_objective_matches_dense_formula():
    B, F, d, S, adv, alpha = random_instance(n=20, seed=62)
    w = np.random.default_rng(0).normal(size=20) * 0.01
    m = mandate()
    U = alpha @ w - 2.0 * w @ dense_sigma(B, F, d) @ w - m.borrow_monthly * np.maximum(-w, 0).sum() \
        - m.trade_cost * np.abs(w).sum()
    assert exact_objective(w, alpha, 2.0, B, F, d, m) == pytest.approx(U, rel=1e-12)


@pytest.mark.parametrize("form", FORMS)
def test_incumbent_value_bound_and_feasibility(form):
    M, (B, F, d, S, adv, alpha) = small(form=form)
    r = M.solve(mip_gap=1e-6)
    assert r.V == max(r.U_incumbent, r.U_polished)
    assert r.U_incumbent == pytest.approx(exact_objective(r.w_incumbent, alpha, 2.0, B, F, d,
                                                          M.mandate), rel=1e-12)
    assert r.V <= r.B + 1e-9 * abs(r.B)
    assert r.work > 0 and np.isfinite(r.work) and r.s_obj == 1.0
    assert pmi_violations(r.w, r.zp, r.zm, B, S, M.mandate, 8, 0.01, adv) == {}


def test_k8_scaled_and_unscaled_pmi_agree():
    """CHECKS K8 (P-MI): MIPGap 0 at s_obj = 1 and 1000: same z, same w to 1e-7, values and duals
    in original units equal; the scaled raw values are s_obj times the unscaled ones."""
    out = {}
    for s in (1.0, 1000.0):
        M, _ = small(seed=63, s_obj=s)
        r = M.solve(mip_gap=0.0)
        fx = M.fixed_integer_duals(r.zp, r.zm)
        rl = M.relaxation_duals()
        out[s] = (r, fx, rl)
    (r1, f1, l1), (r2, f2, l2) = out[1.0], out[1000.0]
    np.testing.assert_array_equal(r1.zp, r2.zp)
    np.testing.assert_array_equal(r1.zm, r2.zm)
    np.testing.assert_allclose(r1.w, r2.w, rtol=0, atol=1e-7)
    assert r2.V == pytest.approx(r1.V, rel=1e-9)
    assert r2.U_raw_scaled == pytest.approx(1000.0 * r2.U_raw, rel=1e-12)      # round trip
    for k, v in f1["shadow"].items():
        assert f2["shadow"][k] == pytest.approx(v, rel=1e-8, abs=1e-12), k
        assert f2["raw_shadow"][k] == pytest.approx(1000.0 * f2["shadow"][k], rel=1e-12), k
    # Simplex duals (fixed-integer QP above; big-M relaxation QP here) scale exactly. The
    # perspective relaxation is a QCP solved by barrier: its QCPDual duals are accurate only to
    # ~1e-3 relative and move with s_obj, and at s_obj = 1 its value is ~1e-6 relative low
    # (PROGRESS S1 findings; A9), so it is not part of the exact-scaling claim.
    assert l1["bigm"]["ok"] and l2["bigm"]["ok"]
    for k, v in l1["bigm"]["shadow"].items():
        assert l2["bigm"]["shadow"][k] == pytest.approx(v, rel=1e-8, abs=1e-12), k
        assert l2["bigm"]["raw_shadow"][k] == pytest.approx(1000.0 * l2["bigm"]["shadow"][k], rel=1e-12)
    assert l1["perspective"]["ok"] and l2["perspective"]["ok"]      # recorded, see PROGRESS (A9)


def test_relaxation_failure_is_recorded_not_fatal(monkeypatch):
    M, _ = small()
    real = miqp.MIQPModel._continuous

    def flaky(self, mode, *a, **k):
        if mode == "relax" and self.formulation == "perspective":
            raise RuntimeError("relax solve status SUBOPTIMAL")
        return real(self, mode, *a, **k)

    monkeypatch.setattr(miqp.MIQPModel, "_continuous", flaky)
    rl = M.relaxation_duals()
    assert rl["bigm"]["ok"] and rl["bigm"]["status"] == "OPTIMAL"
    assert not rl["perspective"]["ok"] and "SUBOPTIMAL" in rl["perspective"]["status"]
    assert rl["perspective"]["shadow"] == {}


def test_work_limit_stops_and_work_is_deterministic():
    M, _ = small(seed=64, n=60, K=15, beta=0.02, style=0.05, position=0.06)
    a, b = M.solve(mip_gap=0.0), M.solve(mip_gap=0.0)
    assert (a.work, a.nodes, a.V) == (b.work, b.nodes, b.V)          # deterministic
    lim = M.solve(mip_gap=0.0, work_limit=0.25 * a.work)
    assert lim.status_name == "WORK_LIMIT" and lim.work <= a.work


@pytest.mark.parametrize("ym", ["2017-12", "2020-03"])
def test_k13_consistency_chain(ym):
    """CHECKS K13: P-MI with K ≥ N and ℓ = 0 = mean-variance at λ* = P-RB at u = 6% (1e-6)."""
    from tests.realdata import month_end
    di, alpha_full, idx = subsample(month_end(ym), 100)
    B, F, d, S, adv, _ = restricted(di, idx)
    alpha = alpha_full[idx]
    base = miqp_mandate(load_config()[0], position=0.06)
    P = ContinuousProblem(B, F, d, S, base, adv=adv, factor_names=FACTORS)
    rb = solve_risk_budget(P, alpha)
    assert rb.risk_binding
    mv = P.solve(alpha, lam=rb.lam)                      # mean-variance at λ*
    np.testing.assert_allclose(mv.w, rb.sol.w, rtol=0, atol=1e-12)
    for form in FORMS:
        M = PMI(B, F, d, S, alpha, rb.lam, base, adv, K=len(idx), ell=0.0, formulation=form,
                factor_names=FACTORS)
        r = M.solve(mip_gap=0.0)
        assert abs(r.V / mv.objective - 1) <= 1e-6, form
        assert np.linalg.norm(r.w - rb.sol.w) / np.linalg.norm(rb.sol.w) <= 1e-6, form
        A_mi = exact_objective(r.w, alpha, 0.0, B, F, d, base)    # λ = 0: net alpha
        assert abs(A_mi / rb.A - 1) <= 1e-6, form
        assert pmi_violations(r.w, r.zp, r.zm, B, S, base, len(idx), 0.0, adv) == {}
    assert rb.A == pytest.approx(net_alpha(P, rb.sol), rel=1e-15)
