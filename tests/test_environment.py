"""Phase 0 smoke tests: the solver stack is importable and the two QP solvers agree.

The academic-license size check (> 2,000 variables) is not a test; it is
tools/check_gurobi_size.py, because it depends on the machine's license, not the code.
"""
import importlib

import numpy as np
import pytest

CORE_MODULES = [
    "numpy", "pandas", "scipy", "cvxpy", "clarabel", "gurobipy",
    "yfinance", "requests", "lxml", "yaml", "matplotlib", "tqdm", "pypdf",
]


@pytest.mark.parametrize("name", CORE_MODULES)
def test_core_imports(name):
    importlib.import_module(name)


def test_cvxpy_sees_gurobi_and_clarabel():
    import cvxpy as cp

    installed = cp.installed_solvers()
    assert "GUROBI" in installed
    assert "CLARABEL" in installed


def _small_qp(seed: int = 0, n: int = 20, k: int = 3):
    """Strongly convex dollar-neutral mean-variance QP (unique optimum), small enough for
    the size-limited pip license."""
    import cvxpy as cp

    rng = np.random.default_rng(seed)
    B = rng.normal(size=(n, k))
    F = np.diag(rng.uniform(1e-3, 4e-3, size=k))
    d = rng.uniform(2e-3, 8e-3, size=n)
    alpha = rng.normal(scale=1e-2, size=n)
    lam = 5.0

    w = cp.Variable(n)
    y = B.T @ w
    obj = cp.Maximize(alpha @ w - lam * (cp.quad_form(y, F) + cp.sum(cp.multiply(d, cp.square(w)))))
    cons = [cp.sum(w) == 0, cp.norm1(w) <= 2.0, cp.abs(w) <= 0.2]
    return cp.Problem(obj, cons), w


def test_small_qp_gurobi_and_clarabel_agree():
    import cvxpy as cp

    prob_g, w_g = _small_qp()
    from src.opt.gurobi_env import quiet_env
    prob_g.solve(solver=cp.GUROBI, env=quiet_env())   # no license banner (CLAUDE.md rule 13)
    prob_c, w_c = _small_qp()
    prob_c.solve(solver=cp.CLARABEL)

    assert prob_g.status == cp.OPTIMAL
    assert prob_c.status == cp.OPTIMAL
    assert prob_g.value == pytest.approx(prob_c.value, rel=1e-6, abs=1e-9)
    # weights are fractions of capital; 1e-4 = 1 bp of capital
    np.testing.assert_allclose(w_g.value, w_c.value, atol=1e-4)
