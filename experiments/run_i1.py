"""I1 — sensitivity under integrality (DESIGN §7): `make i1` → results/i1/run_<UTC>/.

Refused while integer.yaml is "proposed, pending GATE DESIGN" (experiments/s3.py); `make i1
RUNARGS="--config experiments/configs/smoke_i1.yaml"` is the S2d crash test (RUN_LOG "pilot").

One chunk per (date, f, constraint, δ): the I1 instance (N, u = 6%, ℓ = 0.25%, K = round(f·S), λ*),
the constraint's bound set to b, and
- the P-MI at b − δ, b, b + δ, δ = rel_delta·b, under the config's certification: "combined"
  (DESIGN §6: big-M and the rescaled perspective when formulations is [bigm,
  perspective_rescaled], V = the larger polished value, B = the smaller final bound, the
  supplier and exact ties recorded; src.opt.integer.solve_combined) or one formulation; each
  formulation solve at MIPGap and WorkLimit work_limit_factor·W*;
- (a) relaxation duals at b: big-M by dual simplex; the perspective slope by finite differences
  of Clarabel relaxation values (src.opt.slopes; perspective_slope_method "central" runs DESIGN
  §6's edited rule, s3.slope_rule), with every stencil point's status recorded, and Clarabel's
  raw perspective dual as a diagnostic; on the first k29b.n_instances I1 instances by sorted
  instance id the slope is also taken at k29b.scale_factor·s_obj (CHECKS K29b);
- (b) the fixed-integer dual at the incumbent that supplied V at b;
- (c) the certified interval [L, H] and point slope from V and B at b ± δ (B_eff, DESIGN §6), and
  the interval from the raw B;
- (d) the continuous baseline (src.opt.baseline), the config's baseline_kinds (Decision 35:
  fixed_lambda): the dual, the slope at δ = 1% (0.1% at flagged kinks; Decision 36, CHECKS K27)
  and the secant at this δ.
The checker's verdict is recorded on every P-MI solve (1e-9, V's weights) and on the baseline's
weights. The summary holds statuses, counts, Work and Runtime only (experiments/s3.py).
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments import s3
from experiments.common import finish, fail, open_run
from experiments.cont import pool_chunks
from experiments.run_pilot import _key_bounds
from src.opt.baseline import KINDS as BASELINE_KINDS
from src.opt.baseline import baseline_point, baseline_value
from src.opt.certified import certified_interval, certified_interval_eff
from src.opt.integer import PMI, polished_exceeds_bound, solve_combined
from src.opt.sensitivity import set_bound_by_key
from src.opt.slopes import relaxation_slope

FRAMES = ("i1_estimators", "i1_points", "i1_solves", "i1_slope_points", "i1_baseline", "i1_weights")


def plan(cfg: dict) -> list[dict]:
    """(date, f, constraint, δ_rel) for every I1 case: rel_delta everywhere, plus the robustness
    δ at its date."""
    c = cfg["i1"]
    rob = c.get("robustness") or {}
    out = []
    for ym in c["dates"]:
        rels = [float(c["rel_delta"])] + ([float(rob["rel_delta"])] if rob.get("date") == ym else [])
        for f in c["f"]:
            for con in c["constraints"]:
                for rel in rels:
                    out.append({"date": ym, "f": float(f), "key": con["key"], "b": float(con["b"]),
                                "rel_delta": rel})
    return out


def instance_id(ym: str, N, f: float, K: int) -> str:
    return f"{ym}_N{N}_f{f:g}_K{K}"


def instance_ids(cfg: dict) -> list[str]:
    """Sorted I1 instance ids from the config's dates, f and K table (main checks each K)."""
    c = cfg["i1"]
    out = []
    for ym in c["dates"]:
        for i, f in enumerate(c["f"]):
            out.append(instance_id(ym, c["N"], float(f), int(c["K"][ym]["K"][i])))
    return sorted(out)


def k29b_instances(cfg: dict) -> set[str]:
    """CHECKS K29b: the first n_instances I1 instances by sorted instance id."""
    n = int((cfg["i1"].get("k29b") or {}).get("n_instances", 0))
    return set(instance_ids(cfg)[:n])


def make_task(cfg: dict, inst, con: dict, rel_delta: float, f: float,
              k29b_scale: float | None = None) -> dict:
    c = cfg["i1"]
    st = c["settings"]
    iid = instance_id(f"{inst.date:%Y-%m}", inst.N, f, inst.K)
    return {"id": f"{iid}_{con['key'].replace(':', '-')}@{con['b']:g}_d{rel_delta:g}", "instance": iid,
            "date": f"{inst.date:%Y-%m}", "N": inst.N, "f": f, "K": inst.K, "lam_star": inst.lam,
            "kwargs": inst.kwargs, "key": con["key"], "b": float(con["b"]), "rel_delta": rel_delta,
            "s_obj": float(cfg["s_obj"]), "mip_gap": float(st["mip_gap"]),
            "work_limit": float(st["work_limit_factor"]) * float(cfg["W_star"]),
            "certification": c.get("certification", "single"),
            "formulations": list(c.get("formulations", ["perspective"])),
            "slope_method": s3.slope_rule(c.get("perspective_slope_method", "central")),
            "fd_rel_step": float(c.get("perspective_fd_rel_step", 1e-3)),
            "baseline_kinds": list(c.get("baseline_kinds", BASELINE_KINDS)),
            "k29b_scale": None if k29b_scale is None else float(k29b_scale)}


def _set(P: PMI, key: str, value: float) -> None:
    for fam, v, idx in _key_bounds(key, value):
        P.set_bound(fam, v, idx)


def solve_point(P: PMI, t: dict, duals: bool) -> dict:
    """{V, B, v_from, b_from, v_tie, b_tie, parts {arm: PMIResult}, fixed (duals or None), w};
    arms are named as in the config (perspective_rescaled for the rescaled perspective)."""
    forms = list(t["formulations"])
    if t["certification"] == "combined":
        if len(forms) != 2 or forms[0] != "bigm" or forms[1] not in ("perspective", "perspective_rescaled"):
            raise ValueError(f"combined certification takes [bigm, perspective(_rescaled)], got {forms}")
        name = lambda f: forms[1] if f == "perspective" else f
        c = solve_combined(P, mip_gap=t["mip_gap"], work_limit=t["work_limit"], cone_diag=True,
                           duals=duals, rescale_perspective=forms[1] == "perspective_rescaled")
        return {"V": c.V, "B": c.B, "v_from": name(c.v_from), "b_from": name(c.b_from),
                "v_tie": c.v_tie, "b_tie": c.b_tie,
                "parts": {name(f): r for f, r in c.parts.items()}, "fixed": c.fixed_duals, "w": c.w}
    form, rescale = s3.ARMS[forms[0]]
    r = P.sibling(form, rescale=rescale).solve(mip_gap=t["mip_gap"], work_limit=t["work_limit"],
                                               cone_diag=True)
    fixed = None
    if duals and np.isfinite(r.V):
        try:
            fixed = P.fixed_integer_duals(r.zp, r.zm)
        except RuntimeError as err:
            fixed = P._failed(str(err))
    return {"V": r.V, "B": r.B, "v_from": forms[0], "b_from": forms[0], "v_tie": False,
            "b_tie": False, "parts": {forms[0]: r}, "fixed": fixed, "w": r.w}


def slope_columns(sl: dict, suffix: str = "") -> dict:
    """The perspective slope record's estimator columns (persp_*<suffix>)."""
    return {f"persp_{k}{suffix}": sl[k] for k in
            ("slope", "forward", "backward", "forward2", "backward2", "kink", "concave", "noise",
             "noise_central", "ok", "fail_reason", "n_almost_solved", "method", "V")}


def i1_task(t: dict) -> dict[str, pd.DataFrame]:
    key, b, d = t["key"], t["b"], t["rel_delta"] * t["b"]
    ids = {k: t[k] for k in ("id", "instance", "date", "N", "f", "K", "key", "b", "rel_delta")}
    P = PMI(**t["kwargs"], formulation="bigm", s_obj=t["s_obj"])
    pts, solves, weights = {}, [], []
    for sg, tag in ((0, "b"), (+1, "plus"), (-1, "minus")):
        _set(P, key, b + sg * d)
        sp = solve_point(P, t, duals=sg == 0)
        V, B, parts, fixed, w = sp["V"], sp["B"], sp["parts"], sp["fixed"], sp["w"]
        pts[tag] = {**ids, "point": tag, "bound": b + sg * d, "V": V, "B": B,
                    "v_from": sp["v_from"], "b_from": sp["b_from"], "v_tie": sp["v_tie"],
                    "b_tie": sp["b_tie"], "flag_V_exceeds_B": polished_exceeds_bound(V, B),
                    "work_total": sum(p.work for p in parts.values()),
                    "mu_fixed": (fixed or {}).get("shadow", {}).get(key, np.nan),
                    "fixed_status": (fixed or {}).get("status", "not run")}
        solves += [s3.pmi_record(r, {**ids, "point": tag, "arm": f}) for f, r in parts.items()]
        weights.append(pd.DataFrame({"id": t["id"], "point": tag, "i": np.arange(len(w)), "w": w}))
    _set(P, key, b)
    V0 = pts["b"]["V"]
    rel = P.relaxation_duals(v_ref=V0 if np.isfinite(V0) else None)
    slope = relaxation_slope(P, key, rel_delta=t["fd_rel_step"], method=t["slope_method"])
    slope_pts = pd.DataFrame([{**ids, "scale_factor": 1.0, **q} for q in slope["points"]])
    k29b = {f"persp_{k}_k29b": np.nan for k in ("slope", "V", "noise_central")}
    k29b.update(persp_ok_k29b=False, persp_fail_reason_k29b="not run", k29b_scale=np.nan)
    if t.get("k29b_scale"):
        P10 = PMI(**t["kwargs"], formulation="bigm", s_obj=t["s_obj"] * t["k29b_scale"])
        _set(P10, key, b)
        s10 = relaxation_slope(P10, key, rel_delta=t["fd_rel_step"], method=t["slope_method"])
        k29b = {"persp_slope_k29b": s10["slope"], "persp_V_k29b": s10["V"],
                "persp_noise_central_k29b": s10["noise_central"], "persp_ok_k29b": s10["ok"],
                "persp_fail_reason_k29b": s10["fail_reason"], "k29b_scale": t["k29b_scale"]}
        slope_pts = pd.concat([slope_pts, pd.DataFrame([{**ids, "scale_factor": t["k29b_scale"], **q}
                                                        for q in s10["points"]])], ignore_index=True)
    p, m = pts["plus"], pts["minus"]
    try:
        ce = certified_interval_eff(p["V"], p["B"], m["V"], m["B"], d)
        ci = certified_interval(p["V"], p["B"], m["V"], m["B"], d)
        iv = {"L": ce.L, "H": ce.H, "s": ce.s, "L_raw": ci.L, "H_raw": ci.H,
              "binding": bool(ce.L > 0), "solver_error": bool(ce.solver_error)}
    except ValueError as err:                             # an undefined V: recorded, not raised
        iv = {"L": np.nan, "H": np.nan, "s": np.nan, "L_raw": np.nan, "H_raw": np.nan,
              "binding": False, "solver_error": False, "interval_error": str(err)}
    est = {**ids, "delta": d, "V": V0, "B": pts["b"]["B"], **iv,
           "mu_bigm_relax": rel["bigm"]["shadow"].get(key, np.nan), "bigm_relax_ok": rel["bigm"]["ok"],
           "U_bigm_relax": rel["bigm"].get("U", np.nan),
           **s3.persp_raw_columns(rel["perspective"], key), **slope_columns(slope), **k29b,
           "mu_fixed": pts["b"]["mu_fixed"], "fixed_status": pts["b"]["fixed_status"],
           "v_from": pts["b"]["v_from"], "work_total": sum(x["work_total"] for x in pts.values())}
    # (d) the continuous baseline, both candidates
    CP, alpha = s3.baseline_problem(t["kwargs"])
    set_bound_by_key(CP, key, b)
    base = []
    for kind in t["baseline_kinds"]:
        kw = {"lam": t["lam_star"]} if kind == "fixed_lambda" else {"lam_guess": t["lam_star"]}
        bp = baseline_point(CP, alpha, key, kind=kind, secant_rels=(t["rel_delta"],), **kw)
        bv = baseline_value(CP, alpha, key, b, kind=kind, **kw)
        sec = bp.pop("secants")[t["rel_delta"]]
        base.append({**ids, **{k: v for k, v in bp.items() if k not in ("key", "b")},
                     "secant": sec["secant"], "secant_delta": sec["delta"],
                     "checker": s3.continuous_verdict(CP, bv["w"])})
    return {"i1_estimators": pd.DataFrame([est]), "i1_points": pd.DataFrame(list(pts.values())),
            "i1_solves": pd.DataFrame(solves), "i1_slope_points": slope_pts,
            "i1_baseline": pd.DataFrame(base), "i1_weights": pd.concat(weights, ignore_index=True)}


def main(argv=None) -> int:
    run = None
    cfg_path = "experiments/configs/integer.yaml"
    try:
        cfg_path, cfg, status = s3.load_run_config("i1", argv)
        run, _ = open_run("i1", cfg_path, status=status)
        insts = {}
        tasks = []
        k29b = k29b_instances(cfg) if "K" in cfg["i1"] else set()
        k29b_f = float((cfg["i1"].get("k29b") or {}).get("scale_factor", 10.0))
        main_rel = float(cfg["i1"]["rel_delta"])
        for p in plan(cfg):
            k = (p["date"], p["f"])
            if k not in insts:
                insts[k] = s3.instance(p["date"], cfg["i1"]["N"], p["f"], cfg, cfg["i1"].get("K"))
            iid = instance_id(p["date"], insts[k].N, p["f"], insts[k].K)
            sc = k29b_f if iid in k29b and p["rel_delta"] == main_rel else None
            tasks.append(make_task(cfg, insts[k], p, p["rel_delta"], p["f"], k29b_scale=sc))
        out = pool_chunks(run, FRAMES, tasks, lambda t: t["id"], i1_task, s3.workers(cfg))
        summary = {"n_cases": len(out["i1_estimators"]), "solves": s3.solve_summary(out["i1_solves"]),
                   "baseline_checker_violations": int((out["i1_baseline"]["checker"] != "{}").sum()),
                   "perspective_slope_failed": int((~out["i1_estimators"]["persp_ok"]).sum()),
                   "points": s3.point_flag_summary(out["i1_points"])}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, cfg_path, out, f"i1: {summary['n_cases']} cases; solves {summary['solves'].get('statuses')}",
               extra_files=[run / "summary.json"])
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, cfg_path, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
