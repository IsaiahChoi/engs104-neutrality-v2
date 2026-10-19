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
from src.opt.integer import PMI, choose_s_obj, exact_objective, incumbent_flags
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
    # V is the exact objective at the returned (polished, exactly feasible) weights, recomputed
    # here from the dense Σ; the raw incumbent never exceeds it by more than solver tolerance.
    U_dense = alpha @ r.w - 2.0 * r.w @ dense_sigma(B, F, d) @ r.w \
        - M.mandate.borrow_monthly * np.maximum(-r.w, 0).sum() - M.mandate.trade_cost * np.abs(r.w).sum()
    assert r.v_source == "polished" and r.V == r.U_polished
    assert r.V == pytest.approx(U_dense, rel=1e-10)
    assert r.U_incumbent <= r.V + 1e-6 * abs(r.V)
    assert pmi_violations(r.w, r.zp, r.zm, B, S, M.mandate, 8, 0.01, adv, tol=1e-9) == {}
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
    # Simplex duals (fixed-integer QP above; big-M relaxation QP here) scale exactly. Since the
    # CHECKS K8 revision this synthetic instance (n = 20, u = 20%, degenerate) is a diagnostic:
    # its Clarabel perspective-relaxation duals sit at the interior-point accuracy floor (~1e-6,
    # PROGRESS), so their scaling is recorded by experiments/run_core, not gated here; the gated
    # K8 test is test_k8_real_instances_scale.
    assert l1["bigm"]["ok"] and l2["bigm"]["ok"]
    for k, v in l1["bigm"]["shadow"].items():
        assert l2["bigm"]["shadow"][k] == pytest.approx(v, rel=1e-8, abs=1e-12), k
        assert l2["bigm"]["raw_shadow"][k] == pytest.approx(1000.0 * l2["bigm"]["shadow"][k], rel=1e-12)
    assert l1["perspective"]["ok"] and l2["perspective"]["ok"]      # recorded, see PROGRESS (A9)


def test_relaxation_failure_is_recorded_not_fatal(monkeypatch):
    """DESIGN §6 (revised after CHECK CORE round 1): the perspective relaxation's duals come from
    Clarabel and Gurobi's barrier is only a value cross-check, so a SUBOPTIMAL barrier is
    recorded in the cross-check fields, not fatal; a failed big-M relaxation is recorded with its
    status and no duals. (Clarabel failures: tests/test_relaxation.py.)"""
    M, _ = small()
    real = miqp.MIQPModel._continuous

    def flaky(self, mode, *a, **k):
        if mode == "relax" and self.formulation == "perspective":
            raise RuntimeError("relax solve status SUBOPTIMAL")
        return real(self, mode, *a, **k)

    monkeypatch.setattr(miqp.MIQPModel, "_continuous", flaky)
    rl = M.relaxation_duals()
    assert rl["bigm"]["ok"] and rl["bigm"]["status"] == "OPTIMAL"
    assert rl["perspective"]["ok"] and rl["perspective"]["solver"] == "clarabel"
    assert "SUBOPTIMAL" in rl["perspective"]["gurobi_barrier_status"]
    assert np.isnan(rl["perspective"]["U_gurobi_barrier"])

    def bigm_fails(self, mode, *a, **k):
        if mode == "relax" and self.formulation == "bigm":
            raise RuntimeError("relax solve status NUMERIC")
        return real(self, mode, *a, **k)

    monkeypatch.setattr(miqp.MIQPModel, "_continuous", bigm_fails)
    rl = M.relaxation_duals()
    assert not rl["bigm"]["ok"] and "NUMERIC" in rl["bigm"]["status"] and rl["bigm"]["shadow"] == {}
    assert rl["perspective"]["ok"]


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


def test_overstated_raw_incumbent_never_sets_V(monkeypatch):
    """Review H3 and DESIGN §6 (revised): an incumbent that is slightly infeasible (so its exact
    objective may exceed the polished value) never becomes V; V is the polished value alone, and
    when the polish fails V is undefined (nan), with the raw incumbent and the checker's verdict
    on it recorded."""
    M, _ = small(seed=65)
    real_solve = miqp.MIQPModel.solve

    def inflated(self, *a, **k):
        r = real_solve(self, *a, **k)
        r.w = r.w * 1.01                               # pushes binding rows ~1% past their bounds
        return r

    honest = M.solve(mip_gap=1e-6)
    monkeypatch.setattr(miqp.MIQPModel, "solve", inflated)
    r = M.solve(mip_gap=1e-6)
    assert r.V == pytest.approx(honest.V, rel=1e-12) and r.v_source == "polished"
    monkeypatch.setattr(miqp.MIQPModel, "fixed_integer",
                        lambda self, zp, zm: (_ for _ in ()).throw(RuntimeError("fixed solve status NUMERIC")))
    r2 = M.solve(mip_gap=1e-6)
    assert r2.v_source == "polish_failed" and "NUMERIC" in r2.polish_status
    assert np.isnan(r2.V) and np.all(np.isnan(r2.w)) and np.isnan(r2.final_gap)
    assert np.isfinite(r2.U_incumbent) and np.isfinite(r2.U_raw) and r2.incumbent_violations != "{}"
    assert not r2.flag_incumbent_exceeds_polished and not r2.flag_polished_exceeds_bound


def test_incumbent_flags():
    """DESIGN §6 (Isaiah's bound-tolerance decision, 2026-10-19): flag (i) the exact objective at
    the incumbent's weights above V by more than 1e-6·|V| (B_eff's slack), (ii) V above the final
    bound B by more than 1e-6·|V|; no flag when V is undefined. The slack is a parameter, and the
    S1 cases at 1e-9·|V| still hold at rtol=1e-9."""
    from src.opt.integer import FLAG_RTOL
    assert FLAG_RTOL == 1e-6
    V = 2.0e-3
    assert incumbent_flags(V, V, V) == (False, False)
    assert incumbent_flags(V * (1 + 2e-6), V, V) == (True, False)
    assert incumbent_flags(V * (1 + 5e-7), V, V) == (False, False)
    assert incumbent_flags(V, V, V * (1 - 2e-6)) == (False, True)
    assert incumbent_flags(V, V, V * (1 - 5e-7)) == (False, False)
    assert incumbent_flags(V, np.nan, V) == (False, False)
    assert incumbent_flags(-V * (1 - 2e-6), -V, -V) == (True, False)     # |V| for negative values
    r9 = 1e-9                                                            # the S1 cases
    assert incumbent_flags(V * (1 + 2e-9), V, V, rtol=r9) == (True, False)
    assert incumbent_flags(V * (1 + 5e-10), V, V, rtol=r9) == (False, False)
    assert incumbent_flags(V, V, V * (1 - 2e-9), rtol=r9) == (False, True)
    assert incumbent_flags(V, V, V * (1 - 5e-10), rtol=r9) == (False, False)
    assert incumbent_flags(-V * (1 - 2e-9), -V, -V, rtol=r9) == (True, False)


@pytest.mark.parametrize("form", FORMS)
def test_signed_discrepancies_recorded(form):
    """DESIGN §6: the signed discrepancies B − V and (exact objective at the incumbent's
    weights) − V are recorded for every solve (original units), nan when V is undefined."""
    from dataclasses import replace as dc_replace
    M, _ = small(seed=68, form=form)
    r = M.solve(mip_gap=1e-6)
    assert r.B_minus_V == r.B - r.V and r.incumbent_minus_V == r.U_incumbent - r.V
    below = dc_replace(r, B=r.V - 1e-3)
    assert below.B_minus_V == pytest.approx(-1e-3, rel=1e-9)            # signed, not |·|
    undefined = dc_replace(r, V=np.nan)
    assert np.isnan(undefined.B_minus_V) and np.isnan(undefined.incumbent_minus_V)


@pytest.mark.parametrize("form", FORMS)
def test_honest_solve_records_raw_incumbent_without_flags(form):
    M, _ = small(seed=66, form=form)
    r = M.solve(mip_gap=0.0)
    assert r.v_source == "polished" and np.isfinite(r.U_raw) and np.isfinite(r.U_incumbent)
    assert (r.flag_incumbent_exceeds_polished, r.flag_polished_exceeds_bound) == \
        incumbent_flags(r.U_incumbent, r.V, r.B)
    assert not r.flag_polished_exceeds_bound


def test_pmi_instance_rules():
    """experiments.instances.pmi_instance (DESIGN §3.4, §8 P3): λ* is P-RB's root-found λ on the
    same universe at u = 6%; S counts |w_i| > 1e-6 in that P-RB; K = round(f·S) (half up)."""
    from experiments.instances import SUPPORT_TOL, pmi_instance
    from tests.realdata import month_end
    inst = pmi_instance(month_end("2017-12"), 30, 0.5)
    assert inst.N == 30 and inst.mandate.position == 0.06 and inst.ell == 0.0025
    assert SUPPORT_TOL == 1e-6
    P = ContinuousProblem(inst.B, inst.F, inst.d, inst.S, inst.mandate, adv=inst.adv,
                          factor_names=FACTORS)
    rb = solve_risk_budget(P, inst.alpha)
    assert rb.risk_binding and inst.lam == rb.lam
    assert inst.S_support == int((np.abs(rb.sol.w) > 1e-6).sum())
    assert inst.K == int(np.floor(0.5 * inst.S_support + 0.5)) and inst.K >= 1
    base = load_config()[0]
    assert {k: v for k, v in vars(inst.mandate).items() if k != "position"} == \
        {k: v for k, v in vars(base).items() if k != "position"}
    assert set(inst.kwargs) >= {"B", "F", "d", "S", "alpha", "lam", "mandate", "adv", "K", "ell"}


def _scale_ok(mu_ref: float, mu: float, b: float, value: float, rtol: float = 1e-6) -> bool:
    """|μ − μ_ref| ≤ rtol·|μ_ref| for a binding dual; for a non-binding one (elasticity below
    1e-4, DESIGN §6) against the bindingness threshold 1e-4·|V|/b in slope units."""
    return abs(mu - mu_ref) <= rtol * max(abs(mu_ref), 1e-4 * abs(value) / abs(b))


def _key_bound(M: PMI, key: str) -> float:
    fam, _, tail = key.partition(":")
    if fam == "cardinality":
        return float(M.K)
    b = M.bound(fam)
    if not tail:
        return float(np.atleast_1d(b)[0])
    i = (M.style_names or []).index(tail) if fam == "style" else int(tail)
    return float(b[i])


def test_bound_of_matches_every_dual_key():
    M, _ = small(seed=67)
    keys = set(M.relaxation_duals()["bigm"]["shadow"])
    assert {"dollar", "beta", "gross", "cardinality", "style", "sector"} <= keys
    for k in keys:
        assert M.bound_of(k) == _key_bound(M, k), k
    M.set_bound("sector", 0.03, index=1)
    assert np.isnan(M.bound_of("sector")) and M.bound_of("sector:1") == 0.03


@pytest.mark.parametrize("ym", ["2017-12", "2020-03"])
def test_k8_real_instances_scale(ym):
    """CHECKS K8 (P-MI), gated: the two fixed real-data instances solved to MIPGap 0 unscaled
    (s_obj = 1) and at the DESIGN §6 s_obj give the same z and w within 1e-7; every dual (fixed-
    integer and big-M relaxation by dual simplex, perspective relaxation by Clarabel) scales by
    the factor to 1e-6 relative; the scaled raw values unscale exactly."""
    from tests.realdata import pmi_case
    inst = pmi_case(ym)
    M1 = PMI(**inst.kwargs, s_obj=1.0)
    r1 = M1.solve(mip_gap=0.0)
    s = choose_s_obj(r1.V)
    assert s > 1.0 and 1.0 <= abs(r1.V) * s <= 100.0
    M2 = PMI(**inst.kwargs, s_obj=s)
    r2 = M2.solve(mip_gap=0.0)
    np.testing.assert_array_equal(r1.zp, r2.zp)
    np.testing.assert_array_equal(r1.zm, r2.zm)
    assert np.abs(r2.w - r1.w).max() <= 1e-7
    assert np.abs(r2.w - r1.w).sum() / np.abs(r1.w).sum() <= 1e-7
    assert r2.U_raw_scaled == pytest.approx(s * r2.U_raw, rel=1e-12)
    assert r2.B_scaled == pytest.approx(s * r2.B, rel=1e-12)
    pairs = {"fixed": (M1.fixed_integer_duals(r1.zp, r1.zm), M2.fixed_integer_duals(r2.zp, r2.zm))}
    rl1, rl2 = M1.relaxation_duals(), M2.relaxation_duals()
    pairs.update({f: (rl1[f], rl2[f]) for f in ("bigm", "perspective")})
    for est, (a, b) in pairs.items():
        assert a["ok"] and b["ok"], est
        assert set(a["shadow"]) == set(b["shadow"]) and a["shadow"], est
        for k, mu1 in a["shadow"].items():
            assert _scale_ok(mu1, b["shadow"][k], _key_bound(M1, k), r1.V), (est, k, mu1, b["shadow"][k])
            assert b["raw_shadow"][k] == pytest.approx(s * b["shadow"][k], rel=1e-12, abs=1e-300), (est, k)
    # CHECKS K8 (revised 2026-10-19): the perspective relaxation's optimal value scales to 1e-9
    assert rl1["perspective"]["U"] == pytest.approx(rl2["perspective"]["U"], rel=1e-9)
