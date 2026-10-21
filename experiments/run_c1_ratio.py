"""Optional C1 analysis (GATE DESIGN addendum; not gated): `make c1_ratio` →
results/c1_ratio/run_<UTC>/ (RUN_LOG "ok").

For each flagged point of the C1 envelope check (results of the newest finished C1 run: K15's
kink flag at δ = 1%), the P-RB is rebuilt as run_c1 builds it (full universe, base mandate,
α_mom; root-found λ) and solved at b ± h_f, h_f = 0.1%·b. With F, B the forward and backward
differences of A*(b) at a step h,
    ratio = |F − B|(h_f) / |F − B|(h_c),   h_c = 1%·b (the stored C1 stencil),
which is h_f/h_c = 0.1 on a quadratic piece (F − B = A''·h) and 1 at a slope break inside both
stencils (F − B = the jump in slope). Counts are reported in BANDS: near 0.1 = [0.05, 0.2]
(differentiable at this resolution), near 1 = [0.5, 2] (a genuine kink), other, undefined.
A(b) is recomputed and compared with the stored value; each point also carries its S2b
classification (results/pilot_s2b/run_20261020T024318Z/c1_kinks.parquet: active-set change or
curvature flag, Decision 34).
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments.common import file_sha256, finish, fail, latest_done, open_run
from experiments.cont import case, pool_chunks, problem
from experiments.designs import config
from src.opt.continuous import load_config
from src.opt.risk_budget import solve_risk_budget
from src.opt.sensitivity import restore, set_bound_by_key, snapshot
from src.utils import ROOT

CONFIG = "experiments/configs/c1_ratio.yaml"
BANDS = {"near 0.1": (0.05, 0.2), "near 1": (0.5, 2.0)}


def fb_ratio(A, Ap_c, Am_c, h_c, Ap_f, Am_f, h_f) -> dict:
    fb_c = (Ap_c - A) / h_c - (A - Am_c) / h_c
    fb_f = (Ap_f - A) / h_f - (A - Am_f) / h_f
    return {"fb_coarse": fb_c, "fb_fine": fb_f,
            "ratio": abs(fb_f) / abs(fb_c) if fb_c != 0 else np.nan}


def classify(r: float) -> str:
    if not np.isfinite(r):
        return "undefined"
    for name, (lo, hi) in BANDS.items():
        if lo <= r <= hi:
            return name
    return "other"


def date_task(item: tuple) -> dict[str, pd.DataFrame]:
    ds, rows, rel_fine = item
    base, _ = load_config(config("continuous")["mandate_config"])
    di, alpha = case(ds)
    P = problem(di, base)
    rb = solve_risk_budget(P, alpha)
    out = []
    for e in rows:
        snap = snapshot(P)
        h_f = rel_fine * e["b"]
        vals = {}
        for sg in (+1, -1):
            set_bound_by_key(P, e["key"], e["b"] + sg * h_f)
            try:
                vals[sg] = solve_risk_budget(P, alpha, lam_guess=rb.lam).A
            finally:
                restore(P, snap)
        r = fb_ratio(e["A"], e["A_plus"], e["A_minus"], e["step"], vals[+1], vals[-1], h_f)
        out.append({"date": ds, "key": e["key"], "b": e["b"], "step_coarse": e["step"],
                    "step_fine": h_f, "A_b": rb.A, "A_b_stored": e["A"],
                    "A_plus_fine": vals[+1], "A_minus_fine": vals[-1], **r,
                    "band": classify(r["ratio"])})
    return {"c1_ratio": pd.DataFrame(out)}


def main(argv=None) -> int:
    run = None
    try:
        cfg = config("c1_ratio")
        run, _ = open_run("c1_ratio", CONFIG, status="ok")
        c1 = latest_done("c1")
        env = pd.read_parquet(c1 / "c1_envelope.parquet")
        flagged = env[env["kink"].astype(bool)]
        if len(flagged) != int(cfg["expected_flagged"]):
            raise ValueError(f"{len(flagged)} flagged C1 points, expected {cfg['expected_flagged']}")
        items = [(str(d)[:10], g.to_dict("records"), float(cfg["rel_fine"]))
                 for d, g in flagged.groupby("date", sort=True)]
        out = pool_chunks(run, ("c1_ratio",), items, lambda t: t[0], date_task, int(cfg["workers"]))
        df = out["c1_ratio"]
        cls = pd.read_parquet(ROOT / cfg["s2b_kinks"])[["date", "key", "classification"]]
        cls["date"] = cls["date"].astype(str).str[:10]
        df = df.merge(cls, on=["date", "key"], how="left")
        summary = {"c1_run": str(c1.relative_to(ROOT)),
                   "c1_envelope_sha256": file_sha256(c1 / "c1_envelope.parquet"),
                   "n_flagged": len(df), "bands": BANDS,
                   "counts": {k: int(v) for k, v in df["band"].value_counts().sort_index().items()},
                   "counts_by_classification": {f"{a}|{b}": int(v) for (a, b), v in
                                                df.groupby(["classification", "band"]).size().items()},
                   "max_abs_A_b_vs_stored": float((df["A_b"] - df["A_b_stored"]).abs().max()),
                   "ratio_quantiles": {str(q): float(df["ratio"].quantile(q)) for q in (0, 0.25, 0.5, 0.75, 1)}}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, CONFIG, {"c1_ratio": df}, f"c1_ratio: {summary['counts']}", extra_files=[run / "summary.json"])
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
