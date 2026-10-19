"""Envelope self-check on stored sweep points (ported from v1 experiments/check_rq1_envelope.py).

At seeded random sweep points where the swept bound binds (stored shadow price > 1e-7, finite
bound > 0), rebuild the problem exactly as the sweep did, take a central finite difference of
the root-found P-RB value A* in that bound (step rel_step × bound, re-root-finding λ on each
side), and compare with the stored shadow price (1% tolerance, as CHECKS K7/K15).

`uv run python -m experiments.check_envelope --run results/c2/run_<UTC> --n 40` writes
results/<exp>/envelope_check_<UTC>.json and a RUN_LOG row (S2 uses it on C1/C2).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from src.opt.sensitivity import fd_slope_rb

SP_KEY = {"style_all": "style"}


def sp_key(family: str) -> str:
    """The shadow-price key of a swept family (style_all → style; others unchanged)."""
    return SP_KEY.get(family, family)


def envelope_check(points: pd.DataFrame, rebuild: Callable, n: int, seed: int,
                   rel_step: float = 0.01, tol: float = 0.01) -> pd.DataFrame:
    """rebuild(row) -> (problem at that point, alpha). Returns one row per checked point."""
    cand = points[~points["off"] & np.isfinite(points["value"]) & (points["value"] > 0)].copy()
    cand["sp"] = [r.get(f"sp_{sp_key(r['family'])}", np.nan) for _, r in cand.iterrows()]
    cand = cand[cand["sp"] > 1e-7]
    pick = cand.sample(n=min(n, len(cand)), random_state=seed) if len(cand) else cand
    rows = []
    for _, r in pick.iterrows():
        P, alpha = rebuild(r)
        fd = fd_slope_rb(P, alpha, sp_key(r["family"]), rel_step=rel_step,
                         lam_guess=r.get("lam"))
        rows.append({"point_id": r["point_id"], "family": r["family"], "value": r["value"],
                     "shadow_price": r["sp"], "fd_slope": fd,
                     "rel_err": abs(fd - r["sp"]) / abs(r["sp"]),
                     "within": bool(abs(fd - r["sp"]) <= tol * abs(r["sp"]))})
    return pd.DataFrame(rows, columns=["point_id", "family", "value", "shadow_price", "fd_slope",
                                       "rel_err", "within"])


def main() -> int:            # pragma: no cover - exercised in S2 on stored runs
    from experiments.instances import restricted, subsample
    from experiments.sweep import apply_point, build
    from src.alpha.decompose import alpha_set
    from src.opt.continuous import load_config
    from src.utils import ROOT, append_run_log, git_commit, utc_timestamp

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    run = Path(a.run).resolve()
    pts = pd.read_parquet(run / "points.parquet")
    meta = json.loads((run / "run_meta.json").read_text())
    base, _ = load_config()

    def rebuild(row):
        di, alpha_full, idx = subsample(pd.Timestamp(row["date"]), row.get("N_label", "full"))
        B, F, d, S, adv, _ = restricted(di, idx)
        alpha = alpha_set(alpha_full[idx], B, F, d)["alphas"][row["alpha"]]
        P = build(di, base, B=B, F=F, d=d, S=S, adv=adv)["base"]
        apply_point(P, base, row["family"], row["value"])
        return P, alpha

    out = envelope_check(pts, rebuild, a.n, a.seed)
    stamp = utc_timestamp()
    res = {"created_utc": stamp, "git_commit": git_commit(), "run": str(run.relative_to(ROOT)),
           "run_commit": meta["git_commit"], "n": len(out), "tolerance": 0.01,
           "max_rel_err": float(out["rel_err"].max()) if len(out) else None,
           "all_within": bool(out["within"].all()) if len(out) else False,
           "points": out.to_dict("records")}
    path = run.parent / f"envelope_check_{stamp.replace(':', '').replace('-', '')}.json"
    path.write_text(json.dumps(res, indent=1, default=float))
    append_run_log(meta["config_path"], "ok" if res["all_within"] else "failed", str(path),
                   f"envelope self-check: {len(out)} points, max rel err {res['max_rel_err']}")
    print(json.dumps({k: res[k] for k in ("n", "max_rel_err", "all_within")}))
    return 0 if res["all_within"] else 1


if __name__ == "__main__":
    sys.exit(main())
