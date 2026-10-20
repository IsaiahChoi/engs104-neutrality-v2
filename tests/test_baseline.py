"""I1/I2 continuous baseline (d) (DESIGN §7; S2d item 4; Decisions 35–36 open): both candidates
as options, no default chosen.

- "fixed_lambda": the kept mean-variance QP at λ = λ* with u = 6%, ℓ = 0 and no K (P-MI with the
  integer parts removed); value U(b).
- "risk_budget": P-RB at u = 6%, λ re-root-found at every b; value A*(b).
Each returns the dual, the slope at δ = 1% (rechecked at 0.1% where K15's rule flags a kink) and
the secant at I1's δ = 10%. Tested against the K13 chain (both candidates are the same solution at
the base bound when the risk row binds) and against finite differences of A* (and of U).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pytest

from experiments.instances import miqp_mandate, restricted, subsample
from src.opt.attribution import shadow_prices
from src.opt.baseline import KINDS, baseline_point
from src.opt.continuous import ContinuousProblem, load_config
from src.opt.risk_budget import solve_risk_budget
from src.opt.sensitivity import BINDING_ELASTICITY, bound_value, elasticities, fd_slope_rb
from src.risk.factor_model import FACTORS
from tests.realdata import month_end


@lru_cache(maxsize=2)
def k13(ym: str = "2017-12"):
    """The K13 setting: top 100 by ADV, u = 6%, base mandate; P-RB root-found (λ* = μ_risk)."""
    di, alpha_full, idx = subsample(month_end(ym), 100)
    B, F, d, S, adv, _ = restricted(di, idx)
    alpha = alpha_full[idx]
    base = miqp_mandate(load_config()[0], position=0.06)
    P = ContinuousProblem(B, F, d, S, base, adv=adv, factor_names=FACTORS)
    rb = solve_risk_budget(P, alpha)
    return P, alpha, rb


def binding_keys(P, rb):
    sp = shadow_prices(P, rb.sol)
    e = elasticities(P, sp, rb.A)
    return [k for k, v in e.items() if np.isfinite(v) and v >= BINDING_ELASTICITY
            and k.split(":")[0] not in ("position", "liquidity")
            and np.isfinite(bound_value(P, k)) and bound_value(P, k) > 0]


def test_kinds_and_arguments():
    P, alpha, rb = k13()
    assert KINDS == ("fixed_lambda", "risk_budget")
    with pytest.raises(ValueError):
        baseline_point(P, alpha, "sector", kind="mean_variance")
    with pytest.raises(ValueError):
        baseline_point(P, alpha, "sector", kind="fixed_lambda")           # needs λ*


def test_k13_chain_both_candidates_agree_at_base():
    """At the base bound with the risk row binding, the two candidates are one solution: the same
    weights, the same dual for every binding key, U = A* − λ*σ_m² (fixed λ*) and A* (P-RB)."""
    P, alpha, rb = k13()
    assert rb.risk_binding
    keys = binding_keys(P, rb)
    assert keys, "no binding mandate key on the K13 instance"
    for k in keys:
        f = baseline_point(P, alpha, k, kind="fixed_lambda", lam=rb.lam)
        r = baseline_point(P, alpha, k, kind="risk_budget", lam_guess=rb.lam)
        assert f["mu"] == pytest.approx(r["mu"], rel=1e-6, abs=1e-12), k
        assert r["value"] == pytest.approx(rb.A, rel=1e-12)
        var = P.variance(rb.sol.w)
        assert f["value"] == pytest.approx(rb.A - rb.lam * var, rel=1e-9)
        assert f["lam"] == rb.lam and r["lam"] == pytest.approx(rb.lam, rel=1e-9)
        assert r["risk_binding"]


def test_risk_budget_dual_matches_fd_of_A():
    """P-RB: the dual is dA*/db (A5); the coarse slope is fd_slope_rb's central difference and
    matches the dual within 1% (K15's rule) at every binding key."""
    P, alpha, rb = k13()
    for k in binding_keys(P, rb):
        r = baseline_point(P, alpha, k, kind="risk_budget", lam_guess=rb.lam)
        fd = fd_slope_rb(P, alpha, k, rel_step=0.01, lam_guess=rb.lam)
        assert r["ctr_coarse"] == pytest.approx(fd, rel=1e-9, abs=1e-14), k
        assert r["within"], (k, r["rel_err"], r["kink"])


def test_fixed_lambda_dual_matches_fd_of_U():
    """Fixed λ*: the dual is dU/db; the slope (δ = 1%, 0.1% at flagged kinks) matches it within 1%;
    U(b ± δ) are the kept QP's objectives at λ*."""
    P, alpha, rb = k13()
    for k in binding_keys(P, rb):
        f = baseline_point(P, alpha, k, kind="fixed_lambda", lam=rb.lam)
        assert f["within"], (k, f["rel_err"], f["kink"])
        b = bound_value(P, k)
        from src.opt.sensitivity import restore, set_bound_by_key, snapshot
        snap = snapshot(P)
        try:
            set_bound_by_key(P, k, b + f["step"])
            up = P.solve(alpha, lam=rb.lam).objective
        finally:
            restore(P, snap)
        assert f["value_plus"] == pytest.approx(up, rel=1e-12), k


def test_secants_and_restoration():
    """The secant at I1's δ = 10% (and 5% if asked) is (V(b+δ) − V(b−δ))/(2δ); every bound is
    restored afterwards."""
    P, alpha, rb = k13()
    k = binding_keys(P, rb)[0]
    before = {n: np.array(p.value, float).copy() for n, p in P.bounds.items()}
    for kind, kw in (("fixed_lambda", {"lam": rb.lam}), ("risk_budget", {"lam_guess": rb.lam})):
        out = baseline_point(P, alpha, k, kind=kind, secant_rels=(0.10, 0.05), **kw)
        for rel in (0.10, 0.05):
            s = out["secants"][rel]
            assert s["delta"] == pytest.approx(rel * bound_value(P, k), rel=1e-15)
            assert s["secant"] == pytest.approx((s["value_plus"] - s["value_minus"]) / (2 * s["delta"]),
                                                rel=1e-15)
        for n, p in P.bounds.items():
            np.testing.assert_array_equal(np.array(p.value, float), before[n])


def test_non_binding_key_takes_the_fine_step():
    """A non-binding bound (zero dual at b ± δ) is flagged by K15's rule and rechecked at 0.1%;
    against a zero dual the error is read on the bindingness scale 1e-4·|V|/b."""
    P, alpha, rb = k13()
    sp = shadow_prices(P, rb.sol)
    e = elasticities(P, sp, rb.A)
    k = next(k for k in ("beta", "gross", "dollar") if abs(e[k]) < 1e-10)
    f = baseline_point(P, alpha, k, kind="fixed_lambda", lam=rb.lam)
    assert f["mu"] == 0 and f["kink"] and f["step_checked"] == pytest.approx(1e-3 * bound_value(P, k))
    assert f["within"]
