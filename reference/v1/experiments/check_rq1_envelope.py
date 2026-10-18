"""Envelope self-check on the stored E1 run (rq1.yaml `envelope_checks`): at seeded random sweep
points where the swept bound binds (shadow price > 1e-7, bound > 0), rebuild the problem exactly
as experiments/run_rq1.py did, take a central finite difference of U* in that bound (step 1e-3 ×
bound) and compare with the stored shadow price (1% tolerance, as in the tests).
`uv run python -m experiments.check_rq1_envelope` → results/rq1/envelope_check_<UTC>.json.
"""
from __future__ import annotations

import json
import sys

import pandas as pd

from experiments.common import latest_done
from experiments.designs import config
from experiments.run_rq1 import apply_point, build, reset, snapshot
from src.alpha.momentum import momentum_alpha
from src.alpha.synthetic import draw_rng, residual_returns, synthetic_alpha
from src.opt.continuous import load_config
from src.opt.inputs import date_inputs, market_data, next_rebalance_date
from src.utils import RESULTS, ROOT, append_run_log, git_commit, utc_timestamp
from tools.check_frozen import require_frozen

SP_KEY = {"dollar": "sp_dollar", "beta": "sp_beta", "style_all": "sp_style", "sector": "sp_sector",
          "gross": "sp_gross", "position": "sp_position", "liquidity": "sp_liquidity"}


def sp_column(family: str) -> str:
    return f"sp_{family}" if family.startswith("style:") else SP_KEY[family]


def alpha_of(di, kind, draw, cfg):
    md = market_data()
    if kind == "momentum":
        return momentum_alpha(di.model, md.ret)
    ic = cfg["alphas"]["synthetic"]["ic"]
    e = residual_returns(di.model, md.excess, md.factors, next_rebalance_date(di.date))
    return synthetic_alpha(e, di.model.d, ic, draw_rng(cfg["seed"], di.date, ic, draw))[0]


def main() -> int:
    frozen = require_frozen()
    cfg = config("rq1")
    mandate, _ = load_config(cfg["mandate_config"])
    run = latest_done("rq1")
    pts = pd.read_parquet(run / "points.parquet")
    cand = pts[~pts["off"] & (pts["value"] > 0)].copy()
    cand["sp"] = [r[sp_column(r["family"])] for _, r in cand.iterrows()]
    cand = cand[cand["sp"] > 1e-7]
    pick = cand.sample(n=cfg["envelope_checks"], random_state=cfg["seed"])
    rows = []
    for _, r in pick.iterrows():
        di = date_inputs(r["date"])
        P = build(di, mandate)["base"]
        snap = snapshot(P)
        alpha = alpha_of(di, r["alpha"], int(r["draw"]), cfg)
        h = 1e-3 * r["value"]
        vals = []
        for s in (+1, -1):
            apply_point(P, mandate, r["family"], r["value"] + s * h)
            vals.append(P.solve(alpha, lam=r["lam"]).objective)
            reset(P, snap)
        apply_point(P, mandate, r["family"], r["value"])
        U = P.solve(alpha, lam=r["lam"]).objective
        reset(P, snap)
        fd = (vals[0] - vals[1]) / (2 * h)
        rows.append({"point_id": r["point_id"], "family": r["family"], "value": r["value"],
                     "shadow_price": r["sp"], "fd_slope": fd, "rel_err": abs(fd - r["sp"]) / r["sp"],
                     "U_stored": r["U"], "U_rebuilt": U})
    df = pd.DataFrame(rows)
    out = {"created_utc": utc_timestamp(), "git_commit": git_commit(), "frozen_commit": frozen,
           "run": str(run.relative_to(ROOT)), "n": len(df), "tolerance": 0.01,
           "max_rel_err": float(df["rel_err"].max()), "all_within": bool((df["rel_err"] <= 0.01).all()),
           "max_rel_dU_rebuild": float(((df["U_rebuilt"] - df["U_stored"]).abs() / df["U_stored"].abs()).max()),
           "points": df.to_dict("records")}
    path = RESULTS / "rq1" / f"envelope_check_{out['created_utc'].replace(':', '').replace('-', '')}.json"
    path.write_text(json.dumps(out, indent=1))
    append_run_log("experiments/configs/rq1.yaml", "ok", str(path),
                   f"rq1 envelope self-check: {len(df)} points, max rel err {out['max_rel_err']:.2e}")
    print(json.dumps({k: out[k] for k in ("n", "max_rel_err", "all_within", "max_rel_dU_rebuild")}))
    print(df.groupby("family").size().to_dict())
    return 0 if out["all_within"] else 1


if __name__ == "__main__":
    sys.exit(main())
