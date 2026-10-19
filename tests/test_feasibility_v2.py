"""The independent feasibility checker extended to P-RB and P-MI (CHECKS K11): it shares no code
with the optimizer, passes on solutions, and fails on constructed violations of the risk row,
cardinality, minimum position, linking, and one-sidedness."""
from __future__ import annotations

import inspect

import numpy as np

import src.opt.feasibility as feasibility
from src.opt.continuous import ContinuousProblem, Mandate
from src.opt.feasibility import integer_violations, pmi_violations, prb_violations
from src.opt.integer import PMI
from src.opt.risk_budget import SIGMA_M, solve_risk_budget
from src.risk.factor_model import FACTORS
from tests.test_opt import random_instance

M = Mandate(dollar=0.02, beta=0.05, style=0.10, sector=0.05, gross=2.0, position=0.06,
            liquidity_theta=None)


def test_checker_shares_no_code_with_the_optimizer():
    src = inspect.getsource(feasibility)
    for banned in ("cvxpy", "gurobipy", "import src", "from src", "position_bounds"):
        assert banned not in src, banned


def test_prb_pass_and_risk_violation():
    B, F, d, S, adv, alpha = random_instance(n=60, seed=71)
    P = ContinuousProblem(B, F, d, S, M, adv=adv, factor_names=FACTORS)
    w = solve_risk_budget(P, alpha).sol.w
    assert prb_violations(w, B, F, d, S, M, SIGMA_M, adv) == {}
    assert "risk" in prb_violations(1.01 * w, B, F, d, S, M, SIGMA_M, adv)


def test_pmi_pass_and_constructed_violations():
    B, F, d, S, adv, alpha = random_instance(n=40, seed=72)
    K, ell = 12, 0.0025
    r = PMI(B, F, d, S, alpha, 2.0, M, adv, K=K, ell=ell, factor_names=FACTORS).solve(mip_gap=1e-6)
    w, zp, zm = r.w, r.zp.copy(), r.zm.copy()
    assert pmi_violations(w, zp, zm, B, S, M, K, ell, adv) == {}
    held = np.flatnonzero(np.abs(w) > 1e-9)
    assert len(held) >= 3
    i, j = held[0], held[1]
    # cardinality: K one less than the number held
    assert "cardinality" in integer_violations(w, zp, zm, len(held) - 1, ell, M, adv)
    # minimum position: shrink a held name below ℓ
    w2 = w.copy()
    w2[i] = np.sign(w[i]) * 0.5 * ell
    assert "min_position" in integer_violations(w2, zp, zm, K, ell, M, adv)
    # linking: a held name with its z switched off
    zp2, zm2 = zp.copy(), zm.copy()
    zp2[j] = zm2[j] = 0.0
    assert "linking" in integer_violations(w, zp2, zm2, K, ell, M, adv)
    # one-sided: both indicators on
    zp3, zm3 = zp.copy(), zm.copy()
    zp3[i] = zm3[i] = 1.0
    assert "one_sided" in integer_violations(w, zp3, zm3, K, ell, M, adv)
    # fractional z
    zp4 = zp.copy()
    zp4[held[2]] = 0.5
    assert "binary" in integer_violations(w, zp4, zm, K, ell, M, adv)
