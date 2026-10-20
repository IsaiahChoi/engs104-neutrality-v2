"""Relaxation value-function slopes (DESIGN §6, perspective estimator a′; CHECKS K29c method).

S2d item 2: the three-point one-sided slopes are an option beside DESIGN §6's central default.
The closed-form tests run in exact rational arithmetic on the A7 toy (src.opt.toy) with the kinks
named: at ℓ the perspective relaxation's slope drops from a − λdℓ to a − 2λdℓ; at w° every
relaxation's slope reaches 0 with a jump in curvature only. Three-point one-sided differences are
exact on quadratics, so on a piece of the toy they are its one-sided derivatives exactly.
"""
from __future__ import annotations

from fractions import Fraction as Fr

import numpy as np
import pytest

from src.opt.slopes import (KINK_RTOL, METHODS, REL_DELTA, fd_slopes, noise_term,
                            relaxation_slope, stencil)
from src.opt.toy import Toy, random_toys

# an exact toy: w° = a/(2λd) = 1/20, ℓ = 1/50, u = 2/25, f(ℓ) > 0
T = Toy(a=Fr(1), lam=Fr(1), d=Fr(10), ell=Fr(1, 50), u=Fr(2, 25))
EPS = Fr(1, 10**9)
REL = Fr(1, 1000)                     # δ_r = 1e-3·b, exactly


def values(fn, b, delta, method="three_point"):
    _, offsets = stencil(b, method=method, delta=delta)
    return {k: fn(b + k * delta) for k in offsets}


# src.opt.toy's closed forms, restated in Fractions (Toy.w_opt divides by the float 2.0)
W_OPT = T.a / (2 * T.lam * T.d)


def f(w):
    return T.a * w - T.lam * T.d * w * w


def bigm(b):
    return f(min(max(b, Fr(0)), W_OPT))


def persp(b):
    if b <= T.ell:
        return (T.a - T.lam * T.d * T.ell) * max(b, Fr(0))
    return bigm(b)


def miqp(b):
    return Fr(0) if b < T.ell else max(Fr(0), f(min(b, W_OPT, T.u)))


def exact_slope(b):
    """d/db of the perspective relaxation's value inside a piece (src.opt.toy)."""
    if b < T.ell:
        return T.a - T.lam * T.d * T.ell
    return T.a - 2 * T.lam * T.d * b if b < W_OPT else Fr(0)


def test_methods_and_stencils():
    assert METHODS == ("central", "three_point") and REL_DELTA == 1e-3 and KINK_RTOL == 1e-4
    d, off = stencil(0.03)
    assert d == pytest.approx(3e-5, rel=1e-15) and off == (-1, 0, 1)        # DESIGN §6 default
    d, off = stencil(0.03, method="three_point")
    assert off == (-2, -1, 0, 1, 2)
    with pytest.raises(ValueError):
        stencil(0.03, method="five_point")
    with pytest.raises(ValueError):
        stencil(0.0)


def test_rational_arithmetic_is_kept():
    b = Fr(3, 100)
    dl = REL * b
    est = fd_slopes(values(persp, b, dl), dl, method="three_point", value_rtol=EPS)
    assert isinstance(est.forward, Fr) and isinstance(est.backward, Fr) and isinstance(est.slope, Fr)


@pytest.mark.parametrize("b", [Fr(1, 200), Fr(1, 100), Fr(3, 100), Fr(4, 100), Fr(7, 100)])
def test_three_point_is_exact_inside_a_piece(b):
    """Below ℓ (linear), on [ℓ, w°) (quadratic) and above w° (flat): both one-sided slopes and the
    central slope equal the closed form exactly; no kink; concave."""
    dl = REL * b
    est = fd_slopes(values(persp, b, dl), dl, method="three_point", value_rtol=EPS)
    assert est.forward == est.backward == est.slope == exact_slope(b)
    assert not est.kink and est.concave
    c = fd_slopes(values(persp, b, dl, "central"), dl, method="central", value_rtol=EPS)
    assert c.slope == exact_slope(b)


def test_kink_at_ell_named():
    """b = ℓ: the forward slope is the right derivative a − 2λdℓ and the backward slope the left
    derivative a − λdℓ, both exactly; the point is flagged; the drop keeps concavity. DESIGN's
    two-point forward difference is off by λdδ there."""
    b = T.ell
    dl = REL * b
    est = fd_slopes(values(persp, b, dl), dl, method="three_point", value_rtol=EPS)
    right, left = T.a - 2 * T.lam * T.d * T.ell, T.a - T.lam * T.d * T.ell
    assert est.forward == right and est.backward == left
    assert est.kink and est.concave and est.forward < est.backward
    c = fd_slopes(values(persp, b, dl, "central"), dl, method="central", value_rtol=EPS)
    assert c.kink and c.forward == right - T.lam * T.d * dl and c.backward == left


@pytest.mark.parametrize("frac", [Fr(1, 2), Fr(3, 2)])
def test_near_ell_the_far_side_slope_is_exact(frac):
    """Within 2δ of ℓ the one-sided slope whose stencil stays on one piece is exact."""
    dl = REL * T.ell
    above = fd_slopes(values(persp, T.ell + frac * dl, dl), dl, method="three_point", value_rtol=EPS)
    assert above.forward == exact_slope(T.ell + frac * dl) and above.kink
    below = fd_slopes(values(persp, T.ell - frac * dl, dl), dl, method="three_point", value_rtol=EPS)
    assert below.backward == exact_slope(T.ell - frac * dl) and below.kink


@pytest.mark.parametrize("fn", [persp, bigm])
def test_kink_at_w_opt_named(fn):
    """b = w°: the slope is continuous (0 on both sides; the curvature jumps), so both one-sided
    slopes are exactly 0 and the point is not flagged, while the central difference, which
    straddles the curvature jump, is off by λdδ/2. Just above w° the forward slope is exact."""
    b = W_OPT
    dl = REL * b
    est = fd_slopes(values(fn, b, dl), dl, method="three_point", value_rtol=EPS)
    assert est.forward == est.backward == 0 and not est.kink and est.concave
    assert est.slope == T.lam * T.d * dl / 2
    up = fd_slopes(values(fn, b + dl / 2, dl), dl, method="three_point", value_rtol=EPS)
    assert up.forward == 0


def test_bigm_has_no_kink_at_ell():
    dl = REL * T.ell
    est = fd_slopes(values(bigm, T.ell, dl), dl, method="three_point", value_rtol=EPS)
    assert est.forward == est.backward == T.a - 2 * T.lam * T.d * T.ell and not est.kink


def test_concavity_check_catches_the_miqp_jump():
    """The MIQP value function jumps up by f(ℓ) at ℓ (A7): one step below ℓ the forward slope
    exceeds the backward one far beyond the noise, so the concavity check fails there."""
    dl = Fr(1, 10**5)
    b = T.ell - dl
    est = fd_slopes(values(miqp, b, dl), dl, method="three_point", value_rtol=EPS)
    assert not est.concave and est.forward > est.backward + 2 * est.noise


def test_noise_term_is_the_worst_case_value_error():
    """noise = 4·ε_r·max(|V|, |V_ref|)/δ: value errors up to ε = ε_r·max(|V|, |V_ref|) move a
    one-sided three-point slope by at most (3 + 4 + 1)ε/(2δ) = noise, attained at signs
    (−, +, −) on (V(b), V(b+δ), V(b+2δ)); the default V_ref is V(b)."""
    b = Fr(3, 100)
    dl = REL * b
    v = values(persp, b, dl)
    v_ref = Fr(1, 10)                                        # larger than |V(b)|
    exact = fd_slopes(v, dl, method="three_point", v_ref=v_ref, value_rtol=EPS)
    assert exact.noise == noise_term(v[0], v_ref, dl, value_rtol=EPS) == 4 * EPS * v_ref / dl
    assert fd_slopes(v, dl, method="three_point", value_rtol=EPS).noise == 4 * EPS * abs(v[0]) / dl
    e = EPS * v_ref
    bad = {**v, 0: v[0] - e, 1: v[1] + e, 2: v[2] - e}
    pert = fd_slopes(bad, dl, method="three_point", v_ref=v_ref, value_rtol=EPS)
    assert pert.forward - exact.forward == exact.noise
    assert pert.concave                                      # within 2·noise of concave
    worse = {**bad, 1: v[1] + 3 * e}
    assert not fd_slopes(worse, dl, method="three_point", v_ref=v_ref, value_rtol=EPS).concave


def test_central_default_matches_design_rule():
    """DESIGN §6: central difference; forward and backward two-point differences recorded; a kink
    is flagged when they differ by more than 1e-4 relative (to the central slope)."""
    b = Fr(3, 100)
    dl = REL * b
    c = fd_slopes(values(persp, b, dl, "central"), dl)
    assert c.method == "central" and c.slope == exact_slope(b)
    assert c.forward == exact_slope(b) - T.lam * T.d * dl
    assert c.kink == (abs(c.forward - c.backward) > KINK_RTOL * abs(c.slope))
    with pytest.raises(KeyError):
        fd_slopes({-1: 1.0, 1: 2.0}, 0.1)                   # V(b) is required


# ----- Clarabel: the relaxation of the toy as a P-MI (as K9 builds it) -----

def _toy_pmi(Tf: Toy, b: float, s_obj: float = 1.0):
    from experiments.run_core import _toy_pmi as build
    P = build(Tf, b)
    P.s_obj = s_obj
    P.model = P._make("perspective")
    P.set_bound("gross", b)
    return P


@pytest.mark.parametrize("method", METHODS)
def test_relaxation_slope_on_random_toys(method):
    """Clarabel relaxation values at the stencil (DESIGN §6 value, cones exact) give the closed-form
    slope to 1e-6 relative on seeded random toys, inside the pieces; the bounds are restored and
    every point's status and residuals are recorded."""
    worst = 0.0
    for Tf, _ in random_toys(20261020, 4):
        for b in (0.5 * Tf.ell, 0.5 * (Tf.ell + Tf.w_opt)):
            P = _toy_pmi(Tf, b)
            r = relaxation_slope(P, "gross", method=method)
            assert P.bound("gross") == b and r["ok"], r
            cf = Tf.slopes(b)["perspective"]
            worst = max(worst, abs(r["slope"] - cf) / abs(cf))
            assert len(r["points"]) == (3 if method == "central" else 5)
            assert all({"offset", "status", "r_prim", "r_dual", "gap_abs", "value"} <= set(p)
                       for p in r["points"])
    assert worst <= 1e-6, worst


def test_relaxation_slope_at_ell_reports_one_sided_slopes():
    Tf = Toy(a=1.0, lam=1.0, d=10.0, ell=0.02, u=0.08)
    P = _toy_pmi(Tf, Tf.ell)
    r = relaxation_slope(P, "gross", method="three_point")
    assert r["ok"] and r["kink"] and r["concave"]
    assert r["forward"] == pytest.approx(Tf.a - 2 * Tf.lam * Tf.d * Tf.ell, rel=1e-6)
    assert r["backward"] == pytest.approx(Tf.a - Tf.lam * Tf.d * Tf.ell, rel=1e-6)


def test_relaxation_slope_failure_is_recorded(monkeypatch):
    import src.opt.slopes as slopes
    from src.opt.relaxation import ClarabelRelaxation
    Tf = Toy(a=1.0, lam=1.0, d=10.0, ell=0.02, u=0.08)
    P = _toy_pmi(Tf, 0.03)
    calls = {"n": 0}
    real = slopes.perspective_relaxation

    def flaky(model, opts=None, v_ref=None):
        calls["n"] += 1
        if calls["n"] == 2:
            return ClarabelRelaxation(ok=False, status="clarabel relax status X",
                                      info={"fail_reason": "status", "clarabel_status": "X",
                                            "r_prim": np.nan, "r_dual": np.nan, "gap_abs": np.nan,
                                            "gap_rel": np.nan, "value": np.nan})
        return real(model, opts=opts, v_ref=v_ref)

    monkeypatch.setattr(slopes, "perspective_relaxation", flaky)
    r = relaxation_slope(P, "gross")
    assert not r["ok"] and np.isnan(r["slope"]) and r["fail_reason"] == "status"
    assert P.bound("gross") == 0.03


def test_relaxation_slope_keys_on_a_real_instance():
    """Family and element keys on a K8 instance; the slope of a common style bound is that of all
    five bounds moved together; values are in original units at any s_obj."""
    from experiments.instances import pmi_instance
    from src.opt.integer import PMI
    from tests.realdata import month_end
    inst = pmi_instance(month_end("2017-12"), 30, 0.5)
    out = {}
    for s in (1.0, 1e4):
        P = PMI(**inst.kwargs, formulation="perspective", s_obj=s)
        b0 = {k: P.bound_of(k) for k in ("style", "style:Mom", "sector:0")}
        out[s] = {k: relaxation_slope(P, k, method="three_point") for k in b0}
        assert {k: P.bound_of(k) for k in b0} == b0
        for r in out[s].values():                 # a failed point (DESIGN §6) is recorded, not raised
            assert r["ok"] or (r["fail_reason"] in ("status", "residual", "gap")
                               and np.isnan(r["slope"])), r
            assert all(p["clarabel_status"] for p in r["points"]) and len(r["points"]) == 5
    both = [k for k in out[1.0] if out[1.0][k]["ok"] and out[1e4][k]["ok"]]
    assert len(both) >= 2, {s: {k: r["fail_reason"] for k, r in o.items()} for s, o in out.items()}
    for k in both:
        a, b = out[1.0][k], out[1e4][k]
        assert a["V"] == pytest.approx(b["V"], rel=1e-8)
        assert a["slope"] == pytest.approx(b["slope"], rel=1e-3, abs=1e-3 * abs(a["V"]) / a["b"])


def test_relaxation_slope_v_ref_override():
    """A given V_ref (original units; the toy's U* as in K9, DESIGN §6) enters every point's gap
    clause and the noise term; by default V_ref is V(b), the stencil rule."""
    Tf = Toy(a=1.0, lam=1.0, d=10.0, ell=0.02, u=0.08)
    P = _toy_pmi(Tf, 0.01, s_obj=100.0)
    U_star = Tf.value(Tf.w_opt)
    r = relaxation_slope(P, "gross", method="three_point", v_ref=U_star)
    assert r["v_ref"] == U_star
    for p in r["points"]:
        assert p["gap_threshold"] == pytest.approx(1e-9 * 100.0 * max(abs(p["value"]), U_star), rel=1e-12)
    assert r["noise"] == pytest.approx(4e-9 * max(abs(r["V"]), U_star) / r["delta"], rel=1e-12)
    d = relaxation_slope(P, "gross", method="three_point")
    assert d["v_ref"] == d["V"]
    assert d["noise"] == pytest.approx(4e-9 * abs(d["V"]) / d["delta"], rel=1e-12)
