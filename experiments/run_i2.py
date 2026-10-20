"""I2 — value functions (DESIGN §7): `make i2` → results/i2/run_<UTC>/.

Refused while integer.yaml is "proposed, pending GATE DESIGN", and until its i2 constraint is a
{key, b} (it is chosen after I1); `make i2 RUNARGS="--config experiments/configs/smoke_i2.yaml"` is
the S2d crash test (RUN_LOG "pilot").

For each instance (date, N, K = round(f·S)) the constraint's bound is swept over `points` equally
spaced values on [0, 2·b], plus e(1 ± rel_delta) for each estimator point e ∈ {0.5b, b, 1.5b}
(on DESIGN's 41-point grid these are grid points already). One chunk per (instance, bound):
- P-MI under the config's certification (combined: both formulations, V and B combined), with the
  fixed-integer dual at V's incumbent and the big-M relaxation dual;
- the continuous baseline's value, dual and weights, both candidates (src.opt.baseline;
  Decision 35 open);
- at an estimator point, the perspective relaxation slope (src.opt.slopes, DESIGN §6's method
  unless the config says otherwise).
The certified intervals at the estimator points are assembled from the sweep (i2_intervals). The
checker's verdict is recorded on every solution; the summary holds statuses, counts, Work and
Runtime only.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments import s3
from experiments.common import finish, fail, open_run
from experiments.cont import pool_chunks
from experiments.run_i1 import _set, solve_point
from src.opt.baseline import KINDS as BASELINE_KINDS
from src.opt.baseline import baseline_value
from src.opt.certified import certified_interval_eff
from src.opt.integer import PMI, polished_exceeds_bound
from src.opt.sensitivity import set_bound_by_key
from src.opt.slopes import relaxation_slope

FRAMES = ("i2_points", "i2_solves", "i2_baseline", "i2_slope_points", "i2_weights")


def constraint_of(c: dict) -> dict:
    con = c.get("constraint")
    if not (isinstance(con, dict) and "key" in con and "b" in con):
        raise ValueError(f"the I2 constraint must be a {{key, b}} (chosen after I1); got {con!r}")
    return {"key": con["key"], "b": float(con["b"])}


def points(b: float, n: int, fractions=(0.5, 1.0, 1.5), rel_delta: float = 0.10):
    """(sorted sweep bounds, estimator points): n equally spaced on [0, 2b] with each estimator
    point's e(1 ± rel_delta) added unless already on the grid (1e-15 absolute)."""
    grid = list(np.linspace(0.0, 2.0 * b, int(n)))
    est = [fr * b for fr in fractions]
    for e in est:
        for x in ((1 - rel_delta) * e, e, (1 + rel_delta) * e):
            if not np.isclose(grid, x, rtol=0, atol=1e-15).any():
                grid.append(x)
    return np.array(sorted(grid)), est


def make_task(cfg: dict, inst, con: dict, b: float, estimator: bool) -> dict:
    c = cfg["i2"]
    st = c["settings"]
    tag = f"{inst.date:%Y-%m}_N{inst.N}_K{inst.K}"
    return {"id": f"{tag}_{con['key'].replace(':', '-')}_b{b:.10g}", "instance": tag,
            "date": f"{inst.date:%Y-%m}", "N": inst.N, "K": inst.K, "lam_star": inst.lam,
            "kwargs": inst.kwargs, "key": con["key"], "b_base": con["b"], "bound": float(b),
            "estimator": bool(estimator), "s_obj": float(cfg["s_obj"]),
            "mip_gap": float(st["mip_gap"]),
            "work_limit": float(st["work_limit_factor"]) * float(cfg["W_star"]),
            "certification": c.get("certification", "single"),
            "formulations": list(c.get("formulations", ["perspective"])),
            "slope_method": c.get("perspective_slope_method", "central"),
            "fd_rel_step": float(c.get("perspective_fd_rel_step", 1e-3)),
            "baseline_kinds": list(c.get("baseline_kinds", BASELINE_KINDS))}


def i2_task(t: dict) -> dict[str, pd.DataFrame]:
    key, b = t["key"], t["bound"]
    ids = {k: t[k] for k in ("id", "instance", "date", "N", "K", "key", "b_base", "bound", "estimator")}
    P = PMI(**t["kwargs"], formulation="bigm", s_obj=t["s_obj"])
    _set(P, key, b)
    V, B, vf, bf, parts, fixed, w = solve_point(P, t, duals=True)
    rel = P.relaxation_duals(v_ref=V if np.isfinite(V) else None)
    pt = {**ids, "V": V, "B": B, "v_from": vf, "b_from": bf,
          "flag_V_exceeds_B": polished_exceeds_bound(V, B),
          "mu_fixed": (fixed or {}).get("shadow", {}).get(key, np.nan),
          "fixed_status": (fixed or {}).get("status", "not run"),
          "mu_bigm_relax": rel["bigm"]["shadow"].get(key, np.nan),
          **s3.persp_raw_columns(rel["perspective"], key),
          "work_total": sum(p.work for p in parts.values())}
    slope_pts = pd.DataFrame()
    if t["estimator"]:
        sl = relaxation_slope(P, key, rel_delta=t["fd_rel_step"], method=t["slope_method"])
        pt.update(persp_slope=sl["slope"], persp_forward=sl["forward"], persp_backward=sl["backward"],
                  persp_kink=sl["kink"], persp_ok=sl["ok"], persp_fail_reason=sl["fail_reason"],
                  persp_method=sl["method"])
        slope_pts = pd.DataFrame([{**ids, **q} for q in sl["points"]])
    solves = [s3.pmi_record(r, {**ids, "arm": f}) for f, r in parts.items()]
    CP, alpha = s3.baseline_problem(t["kwargs"])
    base = []
    for kind in t["baseline_kinds"]:
        kw = {"lam": t["lam_star"]} if kind == "fixed_lambda" else {"lam_guess": t["lam_star"]}
        bv = baseline_value(CP, alpha, key, b, kind=kind, **kw)
        set_bound_by_key(CP, key, b)
        chk = s3.continuous_verdict(CP, bv["w"])
        set_bound_by_key(CP, key, t["b_base"])
        base.append({**ids, **{k: v for k, v in bv.items() if k not in ("w", "key", "b")},
                     "checker": chk})
    return {"i2_points": pd.DataFrame([pt]), "i2_solves": pd.DataFrame(solves),
            "i2_baseline": pd.DataFrame(base), "i2_slope_points": slope_pts,
            "i2_weights": pd.DataFrame({"id": t["id"], "i": np.arange(len(w)), "w": w})}


def intervals(pts: pd.DataFrame, est: dict, rel_delta: float) -> pd.DataFrame:
    """Certified intervals (B_eff, DESIGN §6) at each instance's estimator points, from the sweep."""
    rows = []
    for inst, es in est.items():
        g = pts[pts["instance"] == inst]
        for e in es:
            d = rel_delta * e
            at = lambda x: g.iloc[int(np.argmin(np.abs(g["bound"].to_numpy() - x)))]
            p, m = at(e + d), at(e - d)
            try:
                ci = certified_interval_eff(p["V"], p["B"], m["V"], m["B"], d)
                rows.append({"instance": inst, "e": e, "delta": d, "L": ci.L, "H": ci.H, "s": ci.s,
                             "binding": bool(ci.L > 0), "solver_error": bool(ci.solver_error)})
            except ValueError as err:
                rows.append({"instance": inst, "e": e, "delta": d, "error": str(err)})
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    run = None
    cfg_path = "experiments/configs/integer.yaml"
    try:
        cfg_path, cfg, status = s3.load_run_config("i2", argv)
        c = cfg["i2"]
        con = constraint_of(c)
        rel = float(c.get("rel_delta", cfg.get("i1", {}).get("rel_delta", 0.10)))
        run, _ = open_run("i2", cfg_path, status=status)
        tasks, est = [], {}
        for spec in c["instances"]:
            inst = s3.instance(spec["date"], spec["N"], float(spec.get("f", 0.5)), cfg)
            if "K" in spec and inst.K != int(spec["K"]):
                raise ValueError(f"K = {inst.K} at {spec} differs from the config's K")
            grid, es = points(con["b"], c["points"], c.get("estimator_fractions", (0.5, 1.0, 1.5)), rel)
            for b in grid:
                tasks.append(make_task(cfg, inst, con, b, any(np.isclose(b, e, rtol=0, atol=1e-15) for e in es)))
            est[tasks[-1]["instance"]] = es
        out = pool_chunks(run, FRAMES, tasks, lambda t: t["id"], i2_task, s3.workers(cfg))
        out["i2_intervals"] = intervals(out["i2_points"], est, rel)
        summary = {"n_points": len(out["i2_points"]), "solves": s3.solve_summary(out["i2_solves"]),
                   "baseline_checker_violations": int((out["i2_baseline"]["checker"] != "{}").sum()),
                   "points": s3.point_flag_summary(out["i2_points"])}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, cfg_path, out, f"i2: {summary['n_points']} points; solves {summary['solves'].get('statuses')}",
               extra_files=[run / "summary.json"])
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, cfg_path, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
