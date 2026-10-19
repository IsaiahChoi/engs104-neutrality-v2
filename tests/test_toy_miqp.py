"""One-asset toy MIQP (DESIGN §9 A7; CHECKS K9), solved with the kept src/opt/miqp.py.

    U(b) = max a·w − λ·d·w²  over  w ∈ {0} ∪ [ℓ, u],  w ≤ b      (the bound is the gross row)
With f(w) = aw − λdw², w° = a/(2λd) and 0 < ℓ < w° < u: U = 0 for b < ℓ, U = f(min(b, w°)) for
b ≥ ℓ, so U jumps by f(ℓ) at b = ℓ. Below ℓ the big-M relaxation slope is a − 2λdb, the
perspective relaxation slope is a − λdℓ, and the fixed-integer dual is 0.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.opt.certified import certified_interval
from src.opt.continuous import Mandate
from src.opt.integer import PMI, choose_s_obj
from src.opt.toy import Toy
from src.risk.factor_model import FACTORS

T = Toy(a=1.0, lam=1.0, d=10.0, ell=0.02, u=0.08)      # w° = 0.05, f(ℓ) = 0.016
GRID = np.linspace(0.0, 0.10, 41)                      # ℓ, w°, u are grid points 8, 20, 32
KINKS = (0.0, T.ell, T.w_opt, T.u)
S_OBJ = choose_s_obj(T.value(T.w_opt))           # DESIGN §6 rule: |U*| in [1, 100] -> 100


def model(b: float, formulation: str) -> PMI:
    m = Mandate(dollar=None, beta=None, style=None, sector=None, gross=b, position=T.u,
                liquidity_theta=None, borrow_annual=0.0, trade_cost=0.0)
    return PMI(np.zeros((1, len(FACTORS))), np.eye(len(FACTORS)) * 1e-4, np.array([T.d]),
               np.ones((1, 1)), np.array([T.a]), T.lam, m, None, K=1, ell=T.ell,
               formulation=formulation, s_obj=S_OBJ, factor_names=FACTORS)


def test_closed_form_jump():
    assert T.value(T.ell) - T.value(T.ell - 1e-12) == pytest.approx(T.f(T.ell), rel=1e-12)
    assert T.f(T.ell) > 0 and T.ell < T.w_opt < T.u


@pytest.mark.parametrize("form", ["bigm", "perspective"])
def test_k9_value_function_on_grid(form):
    """The MIQP value on the 41-point grid matches the closed form to 1e-8, jump included."""
    assert S_OBJ == 100.0
    for b in GRID:
        r = model(b, form).solve(mip_gap=0.0)
        assert abs(r.V - T.value(b)) <= 1e-8, b              # V: exact incumbent value / polish
        # the solver's raw value and bound may exceed U* by the cone tolerance: each cone may be
        # violated by FeasibilityTol 1e-6, so the excess is at most λ·1e-6·Σd (as in test_miqp)
        cone = T.lam * 1e-6 * T.d
        assert -1e-12 <= r.U_raw - T.value(b) <= cone, b
        assert -1e-12 <= r.B - T.value(b) <= cone, b


def test_k9_estimators_match_closed_forms():
    checked = 0
    for b in GRID:
        if min(abs(b - k) for k in KINKS) < 1e-12:
            continue
        cf = T.slopes(b)
        M = model(b, "perspective")
        rl = M.relaxation_duals()
        inc = M.solve(mip_gap=0.0)
        fixed = M.fixed_integer_duals(inc.zp, inc.zm)["shadow"]["gross"]
        assert rl["bigm"]["shadow"]["gross"] == pytest.approx(cf["bigm"], abs=1e-8), b
        # barrier (interior-point) QCP duals: complementarity is approximate (measured ≤ 1.3e-6
        # on this grid against a slope scale a = 1), so 1e-5 absolute
        assert rl["perspective"]["shadow"]["gross"] == pytest.approx(cf["perspective"], abs=1e-5), b
        assert fixed == pytest.approx(cf["fixed"], abs=1e-8), b
        checked += 1
    assert checked == len(GRID) - len(KINKS)
    below = 0.01                                          # the A7 statement below ℓ
    assert T.slopes(below) == pytest.approx({"bigm": T.a - 2 * T.lam * T.d * below,
                                             "perspective": T.a - T.lam * T.d * T.ell,
                                             "fixed": 0.0})


def test_k9_k10_resolve_estimator_and_interval_on_toy():
    """(c) the certified central difference: its point slope equals the closed-form secant
    (also across the jump), and [L, H] contains it."""
    delta = 0.005
    for b in (0.01, 0.02, 0.03, 0.06):
        sol = {s: model(b + s * delta, "perspective").solve(mip_gap=0.0) for s in (+1, -1)}
        ci = certified_interval(sol[1].V, sol[1].B, sol[-1].V, sol[-1].B, delta)
        exact = T.secant(b, delta)
        assert ci.s == pytest.approx(exact, abs=1e-8), b
        assert ci.L - 1e-6 <= exact <= ci.H + 1e-6, b
        assert not ci.solver_error
