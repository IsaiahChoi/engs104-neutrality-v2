"""N1 — formulations (DESIGN §7): `make n1` → results/n1/run_<UTC>/.

Refused while numerics.yaml is "proposed, pending GATE DESIGN"; `make n1 RUNARGS="--config
experiments/configs/smoke_n1.yaml"` is the S2d crash test (RUN_LOG "pilot").

One chunk per solve: (date, N, f, tightness, arm, presolve). The instance is the P-MI at (date, N)
with K = round(f·S) (checked against the config's K table where given) and the tightness's style
and beta bounds; the arm is big-M, the perspective at default scaling, or the perspective with
weights rescaled by the largest position bound (Decision 27(a), proposed); each solve at MIPGap and
WorkLimit work_limit_factor·W*, Threads 1, Seed 0, the config's presolve, plus presolve off at
the configured N. Every solve records status, V, B, the root bound (the last root cut pass), the
cone effect (perspective arms), nodes, Work, Runtime and the checker's verdict. Root gaps against
the best known value and K22's agreement are computed by the S3 analysis, not here.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments import s3
from experiments.common import finish, fail, open_run
from experiments.cont import pool_chunks
from src.opt.integer import PMI

FRAMES = ("n1_solves", "n1_weights")
ARMS = {"bigm": ("bigm", False), "perspective": ("perspective", False),
        "perspective_rescaled": ("perspective", True)}


def plan(cfg: dict) -> list[dict]:
    c = cfg["n1"]
    st = c["settings"]
    po = c.get("presolve_off") or {}
    out = []
    for ym in c["dates"]:
        for N in c["N"]:
            for f in c["f"]:
                for tname in c["tightness"]:
                    pres = [int(st.get("presolve", -1))] + ([int(po["presolve"])] if po and po.get("N") == N else [])
                    for pr in pres:
                        for arm in c["formulations"]:
                            out.append({"date": ym, "N": N, "f": float(f), "tightness": tname,
                                        "arm": arm, "presolve": pr})
    return out


def make_task(cfg: dict, p: dict, inst) -> dict:
    c = cfg["n1"]
    st = c["settings"]
    form, rescale = ARMS[p["arm"]]
    md = s3.tightened(inst.mandate, c["tightness"][p["tightness"]])
    return {"id": f"{p['date']}_N{p['N']}_f{p['f']:g}_K{inst.K}_{p['tightness']}_{p['arm']}_pre{p['presolve']}",
            **p, "K": inst.K, "N_names": inst.N, "lam_star": inst.lam,
            "kwargs": {**inst.kwargs, "mandate": md}, "formulation": form, "rescale": rescale,
            "s_obj": float(cfg["s_obj"]), "mip_gap": float(st["mip_gap"]),
            "work_limit": float(st["work_limit_factor"]) * float(cfg["W_star"]),
            "cone_diag": bool(cfg.get("cone_diagnostic", True))}


def n1_task(t: dict) -> dict[str, pd.DataFrame]:
    M = PMI(**t["kwargs"], formulation=t["formulation"], s_obj=t["s_obj"], rescale=t["rescale"])
    r = M.solve(mip_gap=t["mip_gap"], work_limit=t["work_limit"], presolve=t["presolve"],
                cone_diag=t["cone_diag"])
    ids = {k: t[k] for k in ("id", "date", "N", "N_names", "f", "K", "tightness", "arm",
                             "presolve", "lam_star")}
    rec = s3.pmi_record(r, ids)
    w = pd.DataFrame({"id": t["id"], "i": np.arange(len(r.w)), "w": r.w, "zp": r.zp, "zm": r.zm})
    return {"n1_solves": pd.DataFrame([rec]), "n1_weights": w}


def main(argv=None) -> int:
    run = None
    cfg_path = "experiments/configs/numerics.yaml"
    try:
        cfg_path, cfg, status = s3.load_run_config("n1", argv)
        run, _ = open_run("n1", cfg_path, status=status)
        insts, tasks = {}, []
        for p in plan(cfg):
            k = (p["date"], p["N"], p["f"])
            if k not in insts:
                insts[k] = s3.instance(p["date"], p["N"], p["f"], cfg, cfg["n1"].get("K"))
            tasks.append(make_task(cfg, p, insts[k]))
        out = pool_chunks(run, FRAMES, tasks, lambda t: t["id"], n1_task, s3.workers(cfg))
        summary = {"solves": s3.solve_summary(out["n1_solves"])}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, cfg_path, out, f"n1: {len(out['n1_solves'])} solves; {summary['solves'].get('statuses')}",
               extra_files=[run / "summary.json"])
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, cfg_path, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
