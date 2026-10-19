"""C3, time series (DESIGN §7): `make c3` → results/c3/run_<UTC>/.

Base mandate, α_mom, every month-end of the risk model (241, 2005-12 to 2025-12; full
universe) where α_mom is defined: A*, φ, the risk-binding flag, λ*, and the elasticity of each
family, recorded by experiments.sweep.record (with the independent checker's verdict). α_mom
needs 252 trading days before the date (src/alpha/momentum.py), so a month-end without them is
recorded in c3_skipped with the reason, never dropped silently. Month-ends run in a process pool,
in chunks of `c3_chunk` dates (λ warm-started within a chunk).
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments.common import fail, finish, open_run
from experiments.cont import check_p_rb, case, pool_chunks, problem
from experiments.designs import config
from experiments.sweep import record
from src.alpha.decompose import alignment_share
from src.opt.continuous import load_config
from src.opt.inputs import rebalance_dates
from src.opt.risk_budget import solve_risk_budget

CONFIG = "experiments/configs/continuous.yaml"


def c3_chunk(dates: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    cfg = config("continuous")
    base, _ = load_config(cfg["mandate_config"])
    rows, ws, skipped = [], [], []
    lam = None
    for ds in dates:
        try:
            di, a = case(pd.Timestamp(ds))
        except ValueError as err:                     # α_mom undefined (lookback): recorded
            skipped.append({"date": ds, "reason": str(err)})
            continue
        m = di.model
        P = problem(di, base)
        rb = solve_risk_budget(P, a, lam_guess=lam)
        lam = rb.lam if rb.risk_binding else None
        ids = {"point_id": f"{ds}|Nfull|mom|base", "date": ds, "alpha": "mom", "family": "base",
               "value": np.nan, "off": False, "is_base": True, "N": P.N, "n_label": "full"}
        row, w = record(P, rb, a, ids, di.tickers)
        row["phi"] = alignment_share(a, m.B, m.F, m.d)
        rows.append(row)
        ws.append(w)
    return {"c3_points": pd.DataFrame(rows),
            "c3_weights": pd.concat(ws, ignore_index=True) if ws else pd.DataFrame(),
            "c3_skipped": pd.DataFrame(skipped, columns=["date", "reason"])}


def main() -> int:
    run = None
    try:
        cfg = config("continuous")
        check_p_rb(cfg)
        run, _ = open_run("c3", CONFIG, status="ok")
        dates = [f"{d:%Y-%m-%d}" for d in rebalance_dates()]
        n = int(cfg["c3_chunk"])
        chunks = [tuple(dates[i:i + n]) for i in range(0, len(dates), n)]
        fr = pool_chunks(run, ("c3_points", "c3_weights", "c3_skipped"), chunks, lambda c: c[0], c3_chunk,
                         int(cfg["workers"]))
        pts = fr["c3_points"].sort_values("date", ignore_index=True)
        fr["c3_points"] = pts
        ecols = [c for c in pts.columns if c.startswith("e_") and ":" not in c]
        summary = {"n_month_ends": len(dates), "n_dates": len(pts),
                   "skipped": fr["c3_skipped"].to_dict("records"),
                   "first": pts["date"].iloc[0], "last": pts["date"].iloc[-1],
                   "n_not_optimal": int((pts["status"] != "optimal").sum()),
                   "n_with_violations": int((pts["feasibility_violations"] != "{}").sum()),
                   "n_not_risk_binding": int((~pts["risk_binding"]).sum()),
                   "not_risk_binding": pts.loc[~pts["risk_binding"], "date"].tolist(),
                   "A": pts["A"].describe().to_dict(), "phi": pts["phi"].describe().to_dict(),
                   "elasticity_median": {c[2:]: float(pts[c].median()) for c in ecols},
                   "share_binding": {c[2:]: float((pts[c] >= 1e-4).mean()) for c in ecols}}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, CONFIG, fr, f"C3: {len(pts)} month-ends")
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
