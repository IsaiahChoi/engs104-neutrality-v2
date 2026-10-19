"""C2, cost curves (DESIGN §7): `make c2` → results/c2/run_<UTC>/.

D12, full universe, α_mom: one family swept at a time over its DESIGN §7 grid, every other
family at base (experiments.sweep.sweep_date: root-found P-RB at each point, warm-started from
the neighbouring point's λ*, recorded before the bound is reset). The factor families (beta,
each style factor, all styles jointly) are also swept for α⊥ and α∥. Each point stores A*, the
risk-binding flag, every shadow price and elasticity, and the independent checker's verdict;
A*(b)/A*(off) is formed per (date, alpha, family). (date, alpha) pairs run in a process pool;
each is a chunk.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments.common import fail, finish, open_run
from experiments.cont import check_p_rb, case, pool_chunks
from experiments.designs import config
from experiments.sweep import C2_GRIDS, STYLE_FACTORS, sweep_date
from src.alpha.decompose import alpha_set
from src.opt.continuous import load_config

CONFIG = "experiments/configs/continuous.yaml"
FACTOR_FAMILIES = ["beta", "style_all", *[f"style:{f}" for f in STYLE_FACTORS]]


def tasks(cfg) -> list[tuple[str, str]]:
    return [(ym, kind) for ym in cfg["d12"] for kind in ("mom", "perp", "par")]


def c2_task(task: tuple[str, str]) -> dict[str, pd.DataFrame]:
    ym, kind = task
    cfg = config("continuous")
    base, _ = load_config(cfg["mandate_config"])
    di, alpha_mom = case(ym)
    m = di.model
    a = alpha_set(alpha_mom, m.B, m.F, m.d)["alphas"][kind]
    fams = None if kind == "mom" else set(FACTOR_FAMILIES)
    pts, w = sweep_date(di, a, kind, base, C2_GRIDS, families=fams)
    off = pts[pts["off"]].set_index("family")["A"]
    pts["A_off"] = pts["family"].map(off)
    pts["retained_vs_off"] = pts["A"] / pts["A_off"]
    return {"c2_points": pts, "c2_weights": w}


def main() -> int:
    run = None
    try:
        cfg = config("continuous")
        check_p_rb(cfg)
        run, _ = open_run("c2", CONFIG, status="ok")
        fr = pool_chunks(run, ("c2_points", "c2_weights"), tasks(cfg), lambda t: f"{t[0]}_{t[1]}",
                         c2_task, int(cfg["workers"]))
        pts = fr["c2_points"]
        summary = {"n_points": len(pts), "by_alpha": {k: int(v) for k, v in pts["alpha"].value_counts().items()},
                   "n_not_optimal": int((pts["status"] != "optimal").sum()),
                   "n_with_violations": int((pts["feasibility_violations"] != "{}").sum()),
                   "n_not_risk_binding": int((~pts["risk_binding"]).sum()),
                   "not_risk_binding": pts.loc[~pts["risk_binding"], "point_id"].tolist(),
                   "root_solves": {"median": float(pts["n_solves"].median()), "max": int(pts["n_solves"].max())},
                   "solve_time_s_total": float(pts["solve_time"].sum())}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, CONFIG, fr, f"C2: {len(pts)} points")
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
