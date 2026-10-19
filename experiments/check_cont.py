"""CONT self-checks on the stored C runs (CHECKS K16, K19): `uv run python -m experiments.check_cont`
→ results/cont_checks/run_<UTC>/ (a RUN_LOG row; config continuous.yaml).

- K16: `k16_n` seeded random C1/C2 solves rebuilt and solved by both paths, the root-found QP and
  the Clarabel QCQP (SOC form, 1e-12): |ΔA*| relative ≤ 1e-6.
- K19: `k19_n` seeded random C solves rerun through the runner's own code path (C1: the date's
  base solve; C2: the swept family's sweep from its start, so the λ warm starts repeat; C3: the
  stored chunk of dates): A* and w against the stored values, to 1e-10 relative.
The result-checker recomputes; these are the runner's evidence.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments.check_envelope import rebuild_point
from experiments.common import fail, finish, latest_done, open_run
from experiments.cont import check_p_rb, case, problem
from experiments.designs import config
from experiments.sweep import C2_GRIDS, sweep_date
from src.alpha.decompose import alpha_set
from src.opt.continuous import load_config
from src.opt.risk_budget import solve_qcqp, solve_risk_budget

CONFIG = "experiments/configs/continuous.yaml"


def _rebuild(row, base):
    if row["family"] == "base":
        di, alpha_mom = case(pd.Timestamp(row["date"]))
        m = di.model
        return problem(di, base), alpha_set(alpha_mom, m.B, m.F, m.d)["alphas"][row["alpha"]]
    return rebuild_point(row, base)


def k16(c1, c2, base, n, seed) -> pd.DataFrame:
    pool = pd.concat([c1.assign(source="c1"), c2.assign(source="c2")], ignore_index=True)
    rows = []
    for _, r in pool.sample(n=n, random_state=seed).iterrows():
        P, a = _rebuild(r, base)
        rb = solve_risk_budget(P, a)
        q = solve_qcqp(P, a)
        rows.append({"source": r["source"], "point_id": r["point_id"], "A_stored": r["A"],
                     "A_qp": rb.A, "A_qcqp": q.objective, "qcqp_status": q.status,
                     "rel_diff": abs(q.objective - rb.A) / abs(rb.A),
                     "pass": bool(abs(q.objective - rb.A) <= 1e-6 * abs(rb.A))})
    return pd.DataFrame(rows)


def _w_err(w_new: pd.DataFrame, w_old: pd.DataFrame) -> float:
    a = w_new.set_index("ticker")["w"]
    b = w_old.set_index("ticker")["w"]
    j = a.index.union(b.index)
    d = (a.reindex(j, fill_value=0.0) - b.reindex(j, fill_value=0.0)).abs()
    return float(d.max() / b.abs().max())


def k19(runs: dict, base, n, seed) -> pd.DataFrame:
    from experiments.run_c3 import c3_chunk
    rng = np.random.default_rng(seed)
    picks = []
    for _ in range(n):
        src = ["c1", "c2", "c3"][int(rng.integers(3))]
        pts = runs[src]["points"]
        picks.append((src, pts.iloc[int(rng.integers(len(pts)))]))
    rows = []
    for src, r in picks:
        w_old = runs[src]["weights"]
        w_old = w_old[w_old["point_id"] == r["point_id"]]
        if src == "c1":
            P, a = _rebuild(r, base)
            rb = solve_risk_budget(P, a)
            A_new = rb.A
            w_new = pd.DataFrame({"ticker": case(pd.Timestamp(r["date"]))[0].tickers, "w": rb.sol.w})
        elif src == "c2":
            di, alpha_mom = case(pd.Timestamp(r["date"]))
            m = di.model
            a = alpha_set(alpha_mom, m.B, m.F, m.d)["alphas"][r["alpha"]]
            pts, ws = sweep_date(di, a, r["alpha"], base, C2_GRIDS, families={r["family"]})
            A_new = float(pts.set_index("point_id").loc[r["point_id"], "A"])
            w_new = ws[ws["point_id"] == r["point_id"]]
        else:
            out = c3_chunk(runs["c3"]["chunk_of"][r["date"]])
            A_new = float(out["c3_points"].set_index("point_id").loc[r["point_id"], "A"])
            w_new = out["c3_weights"][out["c3_weights"]["point_id"] == r["point_id"]]
        rel = abs(A_new - r["A"]) / abs(r["A"])
        werr = _w_err(w_new, w_old)
        rows.append({"source": src, "point_id": r["point_id"], "A_stored": r["A"], "A_rerun": A_new,
                     "A_rel_diff": rel, "w_rel_max_diff": werr,
                     "pass": bool(rel <= 1e-10 and werr <= 1e-10)})
    return pd.DataFrame(rows)


def main() -> int:
    run = None
    try:
        from src.opt.inputs import rebalance_dates
        cfg = config("continuous")
        check_p_rb(cfg)
        base, _ = load_config(cfg["mandate_config"])
        src_runs = {k: latest_done(k) for k in ("c1", "c2", "c3")}
        run, _ = open_run("cont_checks", CONFIG, status="ok",
                          extra_meta={"runs": {k: str(v.name) for k, v in src_runs.items()}})
        runs = {k: {"points": pd.read_parquet(v / f"{k}_points.parquet"),
                    "weights": pd.read_parquet(v / f"{k}_weights.parquet")}
                for k, v in src_runs.items()}
        dates = [f"{d:%Y-%m-%d}" for d in rebalance_dates()]
        n = int(cfg["c3_chunk"])
        runs["c3"]["chunk_of"] = {d: tuple(dates[i:i + n]) for i in range(0, len(dates), n)
                                  for d in dates[i:i + n]}
        t16 = k16(runs["c1"]["points"], runs["c2"]["points"], base, cfg["k16_n"], cfg["k16_seed"])
        t19 = k19(runs, base, cfg["k19_n"], cfg["k19_seed"])
        summary = {"source_runs": {k: str(v) for k, v in src_runs.items()},
                   "K16": {"n": len(t16), "max_rel_diff": float(t16["rel_diff"].max()),
                           "all_pass": bool(t16["pass"].all())},
                   "K19": {"n": len(t19), "max_A_rel_diff": float(t19["A_rel_diff"].max()),
                           "max_w_rel_diff": float(t19["w_rel_max_diff"].max()),
                           "all_pass": bool(t19["pass"].all())}}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, CONFIG, {"k16": t16, "k19": t19},
               f"K16 max {summary['K16']['max_rel_diff']:.2e}; K19 max {summary['K19']['max_A_rel_diff']:.2e}")
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
