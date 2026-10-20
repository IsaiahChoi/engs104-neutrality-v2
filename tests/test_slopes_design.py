"""DESIGN §6 perspective estimator as edited at GATE DESIGN (S3 step 0e; Decision 38).

The rule (method "design" in src.opt.slopes): the central difference ŝ = (V(b+δ) − V(b−δ))/(2δ)
is the estimate; the three-point one-sided slopes
    s₊ = (−3V(b) + 4V(b+δ) − V(b+2δ))/(2δ),   s₋ = (3V(b) − 4V(b−δ) + V(b−2δ))/(2δ)
are recorded; a kink is flagged iff |s₊ − s₋| > max(1e-4·|ŝ|, 8N) with N = 1e-9·max(|V|,
|V_ref|)/δ; the concavity check uses the two-point differences (V(b+δ) − V(b))/δ and
(V(b) − V(b−δ))/δ: concave iff forward₂ − backward₂ ≤ 4N (each two-point difference moves by at
most 2N under value errors of 1e-9·max(|V|, |V_ref|)).
Exact rational arithmetic on the A7 toy, as tests/test_slopes.py.
"""
from __future__ import annotations

from fractions import Fraction as Fr

import pytest

from src.opt.slopes import DESIGN_METHOD, fd_slopes, relaxation_slope, stencil
from src.opt.toy import random_toys
from tests.test_slopes import EPS, REL, T, W_OPT, _toy_pmi, exact_slope, miqp, persp, values


def d_est(fn, b, dl, v_ref=None):
    return fd_slopes(values(fn, b, dl, DESIGN_METHOD), dl, method=DESIGN_METHOD, v_ref=v_ref,
                     value_rtol=EPS)


def test_design_stencil():
    assert DESIGN_METHOD == "design"
    d, off = stencil(0.03, method=DESIGN_METHOD)
    assert d == pytest.approx(3e-5, rel=1e-15) and off == (-2, -1, 0, 1, 2)


@pytest.mark.parametrize("b", [Fr(1, 200), Fr(1, 100), Fr(3, 100), Fr(4, 100), Fr(7, 100)])
def test_design_exact_inside_a_piece(b):
    dl = REL * b
    e = d_est(persp, b, dl)
    assert e.method == DESIGN_METHOD
    assert e.slope == e.forward == e.backward == exact_slope(b)
    assert not e.kink and e.concave
    assert e.forward2 == (persp(b + dl) - persp(b)) / dl
    assert e.backward2 == (persp(b) - persp(b - dl)) / dl
    N = EPS * abs(persp(b)) / dl
    assert e.noise_central == N and e.noise == 4 * N


def test_design_kink_at_ell():
    b = T.ell
    dl = REL * b
    e = d_est(persp, b, dl)
    right, left = T.a - 2 * T.lam * T.d * T.ell, T.a - T.lam * T.d * T.ell
    assert e.forward == right and e.backward == left and e.kink and e.concave


def test_design_w_opt_not_flagged_and_central_is_the_estimate():
    b = W_OPT
    dl = REL * b
    e = d_est(persp, b, dl)
    assert e.forward == e.backward == 0 and not e.kink and e.concave
    assert e.slope == T.lam * T.d * dl / 2            # the central slope stays the estimate


@pytest.mark.parametrize("x, flagged", [(Fr(15, 10**9), False), (Fr(17, 10**9), True)])
def test_design_kink_floor_is_8N(x, flagged):
    """Flat values (ŝ = 0, so 1e-4·|ŝ| = 0) with V(b+2δ) lowered by x: s₊ = x/(2δ), s₋ = 0, and
    8N = 8e-9·|V|/δ with |V| = 1, so the flag needs x > 1.6e-8."""
    dl = Fr(1, 1000)
    v = {k: Fr(1) for k in (-2, -1, 0, 1, 2)}
    v[2] = 1 - x
    e = fd_slopes(v, dl, method=DESIGN_METHOD, value_rtol=EPS)
    assert e.slope == 0 and e.forward == x / (2 * dl) and e.backward == 0
    assert e.kink is flagged


def test_design_kink_relative_part():
    """With V(b) = 0 and no V_ref, N = 0 and the 1e-4·|ŝ| part decides (ŝ = 1)."""
    dl = Fr(1, 1000)
    line = {k: k * dl for k in (-2, -1, 0, 1, 2)}
    bump = {**line, 2: line[2] - Fr(19, 10**5) * dl}    # s₊ − s₋ = −0.95e-4
    assert not fd_slopes(bump, dl, method=DESIGN_METHOD, value_rtol=EPS).kink
    bump = {**line, 2: line[2] - Fr(21, 10**5) * dl}    # −1.05e-4
    assert fd_slopes(bump, dl, method=DESIGN_METHOD, value_rtol=EPS).kink


def test_design_concavity_uses_two_point_differences():
    """The relaxation value is concave, so its two-point differences keep the concave ordering
    exactly at every b, including within 2δ of ℓ and w°, where the three-point slopes need not
    (S2d item 2): the design check never fails there, and at least one such point breaks the
    three-point ordering."""
    three_fail = 0
    for k0 in (T.ell, W_OPT):
        dl = REL * k0
        for j in range(-12, 13):
            b = k0 + Fr(j, 6) * dl
            e = d_est(persp, b, dl)
            assert e.concave and e.forward2 <= e.backward2, (k0, j)
            three_fail += e.forward > e.backward
    assert three_fail > 0


def test_design_concavity_catches_the_miqp_jump():
    dl = Fr(1, 10**5)
    assert not d_est(miqp, T.ell - dl, dl).concave


def test_design_concavity_tolerance_is_4N():
    """On a line (forward₂ = backward₂), value errors ε = 1e-9·|V_ref| with signs (+, −, +) on
    (V(b−δ), V(b), V(b+δ)) raise forward₂ − backward₂ by exactly 4ε/δ = 4N: still concave; a
    larger error at V(b) is not."""
    dl = Fr(1, 1000)
    v_ref = Fr(1, 10)
    e = EPS * v_ref
    line = {k: k * dl for k in (-2, -1, 0, 1, 2)}
    at = {**line, -1: line[-1] + e, 0: line[0] - e, 1: line[1] + e}
    r = fd_slopes(at, dl, method=DESIGN_METHOD, v_ref=v_ref, value_rtol=EPS)
    assert r.forward2 - r.backward2 == 4 * EPS * v_ref / dl and r.concave
    more = {**at, 0: line[0] - 2 * e}
    assert not fd_slopes(more, dl, method=DESIGN_METHOD, v_ref=v_ref, value_rtol=EPS).concave


def test_design_relaxation_slope_on_random_toys():
    """Clarabel relaxation values on the 5-point stencil give the closed-form slope to 1e-6 inside
    the pieces; the record carries the two-point differences and 5 points."""
    worst = 0.0
    for Tf, _ in random_toys(20261020, 4):
        for b in (0.5 * Tf.ell, 0.5 * (Tf.ell + Tf.w_opt)):
            P = _toy_pmi(Tf, b)
            r = relaxation_slope(P, "gross", method=DESIGN_METHOD)
            assert P.bound("gross") == b and r["ok"] and len(r["points"]) == 5
            assert {"forward2", "backward2"} <= set(r)
            cf = Tf.slopes(b)["perspective"]
            worst = max(worst, abs(r["slope"] - cf) / abs(cf))
    assert worst <= 1e-6, worst
