"""Scratch: does the MIPNODE callback's root gap equal the gap after a root-only solve? Random instances only."""
import numpy as np
import src.opt.miqp as mq
from tests.test_opt import random_instance
from src.opt.continuous import Mandate
from src.risk.factor_model import FACTORS
for seed in (4, 7, 9):
    B, F, d, S, adv, alpha = random_instance(n=60, seed=seed)
    m = Mandate(dollar=0.02, beta=0.02, style=0.05, sector=0.05, gross=2.0, position=0.06, liquidity_theta=None)
    for form in ("bigm", "perspective"):
        M = mq.MIQPModel(B, F, d, S, alpha, 2.0, m, adv, K=15, ell=0.0025, formulation=form, factor_names=FACTORS)
        full = M.solve(time_limit=60, mip_gap=1e-4, polish=False)
        mdl, wp, wm, zp, zm, _ = M._build("mip")
        mdl.Params.NodeLimit, mdl.Params.MIPGap = 1, 1e-4
        mdl.optimize()
        rg_ref = (-mdl.ObjBound - (-mdl.ObjVal)) / abs(mdl.ObjVal) if mdl.SolCount else float("nan")
        relax = M.relax().U
        print(f"seed {seed} {form:11s}: callback root gap {full.root_gap:.4g}  root-only solve gap {rg_ref:.4g}  "
              f"relaxation gap {(relax - full.U) / abs(full.U):.4g}  nodes {full.nodes:.0f}  status {full.status_name}")
        mdl.dispose()
