"""MIQP validation (brief §8 item 6) and src/opt/miqp.py's dual sign and measurements.

Random instances only. Tolerances: polished objectives (exact QP at the incumbent's z) 1e-9
relative; raw MIQP objectives 1e-5 relative (Gurobi's default cone feasibility tolerance in the
perspective form; H4 timings require default settings); weights 1e-6; envelope slopes 1%.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.opt.continuous import ContinuousProblem, Mandate
from src.opt.feasibility import violations
from src.opt.miqp import GRB_SHADOW_SIGN, MIQPModel, shadow_price
from src.risk.factor_model import FACTORS
from tests.test_opt import random_instance

FORMS = ["bigm", "perspective"]
LAM = 2.0


def mandate(**kw):
    base = dict(dollar=0.02, beta=0.05, style=0.10, sector=0.05, gross=2.0, position=0.20,
                liquidity_theta=None)
    return Mandate(**{**base, **kw})


@pytest.mark.parametrize("form", FORMS)
def test_k_ge_n_reproduces_continuous(form):
    """§8.6: K ≥ N with ℓ = 0 reproduces the continuous solution at the MIQP's position cap."""
    B, F, d, S, adv, alpha = random_instance(n=20, seed=4)
    m = mandate(position=0.06)
    c = ContinuousProblem(B, F, d, S, m, adv=adv, factor_names=FACTORS).solve(alpha, lam=LAM)
    r = MIQPModel(B, F, d, S, alpha, LAM, m, adv, K=25, ell=0.0, formulation=form,
                  factor_names=FACTORS).solve(time_limit=60, mip_gap=0.0)
    assert r.U_polished == pytest.approx(c.objective, rel=1e-9)
    np.testing.assert_allclose(r.w_polished, c.w, rtol=0, atol=1e-6)
    # Raw value: each cone v_i² ≤ s_i ζ_i may be violated by up to FeasibilityTol (1e-6), which
    # can only undercount risk, so U_raw − U* ∈ [−1e-12, λ·1e-6·Σd_i]. (Set after a first
    # draft's guessed 1e-5 relative bound failed at 1.56e-5; see PROGRESS for sign-off.)
    assert -1e-12 <= r.U - c.objective <= LAM * 1e-6 * d.sum()


@pytest.mark.parametrize("seed", [4, 5, 6])
def test_bigm_and_perspective_equal_optima(seed):
    """§8.6: both formulations give the same optimum on small instances solved to optimality."""
    B, F, d, S, adv, alpha = random_instance(n=20, seed=seed)
    res = {f: MIQPModel(B, F, d, S, alpha, LAM, mandate(), adv, K=8, ell=0.01, formulation=f,
                        factor_names=FACTORS).solve(time_limit=120, mip_gap=0.0) for f in FORMS}
    assert all(r.status_name == "OPTIMAL" for r in res.values())
    assert res["bigm"].U_polished == pytest.approx(res["perspective"].U_polished, rel=1e-9)
    assert res["bigm"].U == pytest.approx(res["perspective"].U, rel=1e-5)


def test_gurobi_dual_sign_on_fixed_integer_qp():
    """GRB_SHADOW_SIGN maps Gurobi's Pi to dU*/db: finite differences of the fixed-integer QP
    match the shadow price of every binding bound, and sign(FD / raw Pi) = GRB_SHADOW_SIGN."""
    B, F, d, S, adv, alpha = random_instance(n=20, seed=4)
    M = MIQPModel(B, F, d, S, alpha, LAM, mandate(dollar=0.005, beta=0.005, style=0.01, gross=1.0),
                  adv, K=8, ell=0.01, formulation="perspective", factor_names=FACTORS)
    inc = M.solve(time_limit=60, mip_gap=0.0)
    fx = M.fixed_integer(inc.zp, inc.zm)
    checked = 0
    for fam, k in [("beta", None), ("dollar", None), ("gross", None)] + [("style", i) for i in range(5)]:
        mu = shadow_price(fx, fam, k)
        if abs(mu) < 1e-8:
            continue
        b0 = M.bound(fam) if k is None else M.bound(fam)[k]
        h = 1e-4 * b0
        vals = []
        for s in (+1, -1):
            M.set_bound(fam, b0 + s * h, k)
            vals.append(M.fixed_integer(inc.zp, inc.zm).U)
        M.set_bound(fam, b0, k)
        fd = (vals[0] - vals[1]) / (2 * h)
        raw = sum(fx.duals[(fam, side)][k] if k is not None else fx.duals[(fam, side)].sum()
                  for side in (("upper", "lower") if fam != "gross" else ("upper",)))
        assert fd == pytest.approx(mu, rel=0.01), fam
        assert np.sign(fd / raw) == GRB_SHADOW_SIGN
        assert mu > 0
        checked += 1
    assert checked >= 2


@pytest.mark.parametrize("seed", [4, 7])
def test_relaxations_bound_the_miqp_and_perspective_is_tighter(seed):
    B, F, d, S, adv, alpha = random_instance(n=40, seed=seed)
    m = mandate(position=0.06, beta=0.02, style=0.05)
    mk = lambda f: MIQPModel(B, F, d, S, alpha, LAM, m, adv, K=12, ell=0.0025, formulation=f,
                             factor_names=FACTORS)
    opt = mk("bigm").solve(time_limit=120, mip_gap=0.0).U_polished
    rb, rp = mk("bigm").relax().U, mk("perspective").relax().U
    assert rb >= rp - 1e-9 * abs(rp)          # perspective relaxation is at least as tight
    assert rp >= opt - 1e-9 * abs(opt)        # both bound the integer optimum


@pytest.mark.parametrize("form", FORMS)
def test_miqp_solution_is_feasible(form):
    """Cardinality, minimum size, one-sidedness, caps, and every mandate family hold."""
    B, F, d, S, adv, alpha = random_instance(n=40, seed=8)
    m = mandate(position=0.06)
    r = MIQPModel(B, F, d, S, alpha, LAM, m, adv, K=12, ell=0.0025, formulation=form,
                  factor_names=FACTORS).solve(time_limit=60, mip_gap=1e-6)
    held = np.abs(r.w_polished) > 1e-9
    assert held.sum() <= 12 and (r.zp + r.zm <= 1).all()
    assert (np.abs(r.w_polished[held]) >= 0.0025 - 1e-9).all()
    assert (np.abs(r.w_polished) <= 0.06 + 1e-9).all()
    assert violations(r.w_polished, B, S, m, adv, tol=1e-7) == {}


@pytest.mark.parametrize("seed", [4, 7, 9])
def test_root_gap_matches_a_root_only_solve(seed):
    """The MIPNODE-callback root gap equals the gap after a root-only solve (NodeLimit = 1),
    within 5% relative: a root-only stop may let end-of-root heuristics improve its incumbent
    (observed 0–1.5% on these instances)."""
    B, F, d, S, adv, alpha = random_instance(n=60, seed=seed)
    m = mandate(beta=0.02, style=0.05, position=0.06)
    for form in FORMS:
        M = MIQPModel(B, F, d, S, alpha, LAM, m, adv, K=15, ell=0.0025, formulation=form,
                      factor_names=FACTORS)
        full = M.solve(time_limit=60, mip_gap=1e-4, polish=False)
        mdl, *_ = M._build("mip")
        mdl.Params.NodeLimit, mdl.Params.MIPGap = 1, 1e-4
        mdl.optimize()
        ref = (mdl.ObjVal - mdl.ObjBound) / abs(mdl.ObjVal)     # minimizing −U
        mdl.dispose()
        assert full.root_gap >= 0 and np.isfinite(full.root_gap)
        assert full.root_gap == pytest.approx(ref, rel=0.05)
