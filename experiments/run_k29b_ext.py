"""K29b extended (S3b item 2; Isaiah's GATE I note, Decision 45): `make k29b_ext` →
results/k29b_ext/run_<UTC>/ (RUN_LOG "ok"). A diagnostic; CHECK INT stands and CHECKS is unchanged.

The cases are every I1 case (experiments.run_i1.plan on integer.yaml, unchanged) that CHECKS K29b
did not cover, i.e. all but the first k29b.n_instances instances by sorted id at the main δ: the
6 instances at 2017-12 and 2020-03 at δ = 10% (24 cases) and the 12 cases at 2017-12 at δ = 5%,
n_cases_expected = 36 in all (checked). The perspective-relaxation slope does not depend on the
I1 step δ, so a δ = 5% case repeats its δ = 10% twin's stencils; both are computed, as the note
lists them. Each case, from a fresh P-MI at the case's bound (run_i1.make_task's instance and
settings): the slope by I1's rule (DESIGN §6, src.opt.slopes "design", 5-point stencil) at s_obj
and at scale_factor·s_obj, with every stencil point's Clarabel status, residuals and raw duals.
Criterion (K29b's, applied to every case): |ŝ(10·s_obj) − ŝ(s_obj)| ≤ 1e-5·|ŝ| + 2N, N the
central slope's a-priori noise at s_obj (src.analysis.s3.k29b).
"""
from __future__ import annotations

import json
import sys

import pandas as pd

import experiments.run_i1 as i1
from experiments import s3
from experiments.common import fail, finish, open_run
from experiments.cont import pool_chunks
from experiments.designs import config
from src.analysis.s3 import k29b
from src.opt.integer import PMI
from src.opt.slopes import relaxation_slope

CONFIG = "experiments/configs/k29b_ext.yaml"
FRAMES = ("k29b_ext", "k29b_ext_points")


def ext_cases(icfg: dict) -> list[dict]:
    """The I1 cases K29b did not cover (module docstring), each with its config K."""
    c = icfg["i1"]
    covered = i1.k29b_instances(icfg)
    main = float(c["rel_delta"])
    out = []
    for p in i1.plan(icfg):
        K = int(c["K"][p["date"]]["K"][[float(x) for x in c["f"]].index(p["f"])])
        if i1.instance_id(p["date"], c["N"], p["f"], K) in covered and p["rel_delta"] == main:
            continue
        out.append({**p, "K": K})
    return out


def check_count(cases: list, expected: int) -> None:
    if len(cases) != expected:
        raise ValueError(f"{len(cases)} K29b-ext cases, the config expects {expected}")


def ext_task(t: dict) -> dict[str, pd.DataFrame]:
    """The case's perspective slopes at s_obj and t['k29b_scale']·s_obj (module docstring)."""
    ids = {k: t[k] for k in ("id", "instance", "date", "N", "f", "K", "key", "b", "rel_delta")}
    rows, pts = {}, []
    for sf in (1.0, t["k29b_scale"]):
        P = PMI(**t["kwargs"], formulation="bigm", s_obj=t["s_obj"] * sf)
        i1._set(P, t["key"], t["b"])
        rows[sf] = relaxation_slope(P, t["key"], rel_delta=t["fd_rel_step"], method=t["slope_method"])
        pts += [{**ids, "scale_factor": sf, **q} for q in rows[sf]["points"]]
    s1, s10 = rows[1.0], rows[t["k29b_scale"]]
    rec = {**ids, "s_obj": t["s_obj"], **i1.slope_columns(s1),
           "persp_slope_k29b": s10["slope"], "persp_V_k29b": s10["V"],
           "persp_noise_central_k29b": s10["noise_central"], "persp_ok_k29b": s10["ok"],
           "persp_fail_reason_k29b": s10["fail_reason"], "persp_kink_k29b": s10["kink"],
           "k29b_scale": t["k29b_scale"]}
    return {"k29b_ext": pd.DataFrame([rec]), "k29b_ext_points": pd.DataFrame(pts)}


def verdict(df: pd.DataFrame) -> dict:
    """K29b's rule on every case (src.analysis.s3.k29b); pass iff no miss and no failed stencil."""
    k = k29b(df)
    return {**k, "pass": bool(k["misses"] == 0 and k["n_failed"] == 0)}


def main(argv=None) -> int:
    run = None
    try:
        cfg = config("k29b_ext")
        icfg = config(cfg["source_config"])
        if not str(icfg.get("status", "")).startswith("approved"):
            raise RuntimeError(f"{cfg['source_config']}.yaml is not approved: {icfg.get('status')}")
        cases = ext_cases(icfg)
        check_count(cases, int(cfg["n_cases_expected"]))
        run, _ = open_run("k29b_ext", CONFIG)
        insts, tasks = {}, []
        for c in cases:
            k = (c["date"], c["f"])
            if k not in insts:
                insts[k] = s3.instance(c["date"], icfg["i1"]["N"], c["f"], icfg, icfg["i1"].get("K"))
            if insts[k].K != c["K"]:
                raise ValueError(f"{k}: realized K {insts[k].K} != config K {c['K']}")
            tasks.append(i1.make_task(icfg, insts[k], {"key": c["key"], "b": c["b"]}, c["rel_delta"],
                                      c["f"], k29b_scale=float(cfg["scale_factor"])))
        out = pool_chunks(run, FRAMES, tasks, lambda t: t["id"], ext_task, s3.workers(cfg))
        pts = out["k29b_ext_points"]
        summary = {"n_cases": len(out["k29b_ext"]), "verdict": verdict(out["k29b_ext"]),
                   "relaxations": len(pts), "relaxations_failed": int((~pts["ok"].astype(bool)).sum()),
                   "kinks_s_obj": int(out["k29b_ext"]["persp_kink"].astype(bool).sum()),
                   "kinks_scaled": int(out["k29b_ext"]["persp_kink_k29b"].astype(bool).sum()),
                   "statuses": {str(k): int(v) for k, v in pts["status"].value_counts().items()}}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, CONFIG, out, f"k29b_ext: {summary['n_cases']} cases; pass {summary['verdict']['pass']}",
               extra_files=[run / "summary.json"])
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
