"""Scratch diagnosis (not a result): why big-M and perspective disagree beyond their 1e-4 gaps."""
from dataclasses import replace
import pandas as pd
import src.opt.miqp as mq
from experiments.run_rq3 import subsample, restricted, miqp_mandate, config
from src.opt.continuous import load_config
from src.opt.lambda_policy import LambdaBook
from src.risk.factor_model import FACTORS
cfg = config("rq3"); base, _ = load_config(); book = LambdaBook.latest()
orig_build = mq.MIQPModel._build
def tight_build(self, *a, **k):
    out = orig_build(self, *a, **k); out[0].Params.FeasibilityTol = 1e-9; out[0].Params.OptimalityTol = 1e-9
    return out
for date, n, K, tight in [("2017-12-29", 250, 100, "tight"), ("2020-03-31", 250, 160, "tight")]:
    di, a, idx = subsample(date, n, "restrict"); B, F, d, S, adv, _ = restricted(di, idx)
    lam = book.get(date, "momentum"); t = cfg["h4"]["tightness"][tight]
    m = miqp_mandate(base, cfg, t["style"], t["beta"])
    for variant in ("registered", "scaled_x1000", "tight_tol"):
        res = {}
        for form in ("bigm", "perspective"):
            mq.MIQPModel._build = tight_build if variant == "tight_tol" else orig_build
            s = 1000.0 if variant == "scaled_x1000" else 1.0
            mm = replace(m, borrow_annual=m.borrow_annual * s, trade_cost=m.trade_cost * s)
            M = mq.MIQPModel(B, F, d, S, a[idx] * s, lam * s, mm, adv, K=K, ell=0.0025, formulation=form, factor_names=FACTORS)
            r = M.solve(time_limit=120, mip_gap=1e-4)
            res[form] = (r.U_polished / s, r.bound / s, r.status_name, r.runtime)
        mq.MIQPModel._build = orig_build
        (ub, bb, sb, tb), (up, bp, sp, tp) = res["bigm"], res["perspective"]
        print(f"{date} N{n} K{K} {tight} [{variant:12s}] bigM U {ub:.7e} ({sb} {tb:.0f}s) | persp U {up:.7e} ({sp} {tp:.0f}s) | rel diff {(ub-up)/abs(ub):+.2e} | bigM bound>=persp U: {bb >= up - 1e-12} | persp bound>=bigM U: {bp >= ub - 1e-12}", flush=True)
