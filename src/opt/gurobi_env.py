"""Quiet, deterministic Gurobi environments.

A default gurobipy environment prints a license banner (including the license id) the first
time it starts, and that banner would end up in logs/ via `make ... | tee`. Every Gurobi solve in
this project goes through an environment from here: created empty, OutputFlag set to 0 before
start, with fixed Threads and Seed (CLAUDE.md technical conventions).
"""
from __future__ import annotations

from functools import lru_cache

import gurobipy as gp

DEFAULT_THREADS = 1
DEFAULT_SEED = 0


@lru_cache(maxsize=8)
def quiet_env(threads: int = DEFAULT_THREADS, seed: int = DEFAULT_SEED) -> gp.Env:
    env = gp.Env(empty=True)
    env.setParam("OutputFlag", 0)
    env.setParam("Threads", threads)
    env.setParam("Seed", seed)
    env.start()
    return env
