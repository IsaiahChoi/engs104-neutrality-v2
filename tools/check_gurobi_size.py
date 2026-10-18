#!/usr/bin/env python3
"""Confirm the full (academic) Gurobi license is active, not the size-limited pip license.

The pip license caps models at 2,000 variables and 2,000 linear constraints. This solves a
random factor-model QP with N = 3,000 stocks (plus K auxiliary exposure variables) and the
position limits written as N explicit linear constraints, so it exceeds both caps. Exit 0 if
it solves to optimality, 1 otherwise.

Usage:  uv run python tools/check_gurobi_size.py
"""
from __future__ import annotations

import sys

import gurobipy as gp
import numpy as np
from gurobipy import GRB

N, K, SEED = 3_000, 6, 0
SIZE_LIMIT_ERROR = 10010  # GRB_ERROR_SIZE_LIMIT_EXCEEDED


def main() -> int:
    rng = np.random.default_rng(SEED)
    B = rng.normal(size=(N, K))
    F = np.diag(rng.uniform(1e-3, 4e-3, size=K))
    d = rng.uniform(2e-3, 8e-3, size=N)
    alpha = rng.normal(scale=1e-2, size=N)
    lam = 5.0

    print(f"gurobipy {'.'.join(map(str, gp.gurobi.version()))}; N={N}, K={K}")
    try:
        env = gp.Env(empty=True)  # empty env + OutputFlag 0 keeps the license banner quiet
        env.setParam("OutputFlag", 0)
        env.setParam("Threads", 1)
        env.setParam("Seed", 0)
        env.start()
        with env, gp.Model(env=env) as m:
            w = m.addMVar(N, lb=-GRB.INFINITY, name="w")
            m.addConstr(w <= 0.01, name="position_cap")  # N linear rows (> 2,000)
            y = m.addMVar(K, lb=-GRB.INFINITY, name="y")
            m.addConstr(y == B.T @ w, name="exposure")
            m.addConstr(w.sum() == 0, name="dollar_neutral")
            m.setObjective(alpha @ w - lam * (y @ F @ y + w @ np.diag(d) @ w), GRB.MAXIMIZE)
            m.optimize()
            print(f"NumVars={m.NumVars} NumConstrs={m.NumConstrs} "
                  f"Status={m.Status} Runtime={m.Runtime:.2f}s")
            if m.Status != GRB.OPTIMAL:
                print("FAIL: model did not solve to optimality.")
                return 1
            print(f"OK: objective={m.ObjVal:.6e}; full license active.")
            return 0
    except gp.GurobiError as e:
        if e.errno == SIZE_LIMIT_ERROR:
            print("FAIL: size-limited license. Install an academic license (SETUP.md Step 3).")
        else:
            print(f"FAIL: GurobiError {e.errno}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
