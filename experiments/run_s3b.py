"""S3b items 3 and 5 (Isaiah's GATE I note): `make s3b` → results/s3b/run_<UTC>/ (RUN_LOG "ok").
Recomputations the I1 and N1 runs did not store; no estimator, value or bound is changed.

- Item 3, support (s3b_support): for every I1 case (48, both δ) and point b − δ, b, b + δ, z is
  rebuilt from V's polished weights in the I1 run (src.analysis.s3b.z_from_weights; exact because
  ℓ > 0), the fixed-integer QP is re-solved by dual simplex at that z and the point's bound
  (src.opt.miqp fixed_integer, POLISH_PARAMS), and recorded: the recomputed V against the stored V,
  the support (|w| > 1e-6, sign included), the QP's active set (rows tight within 1e-9;
  src.analysis.s3b.fixed_active_set) and the fixed-integer dual of the case's key.
- Item 5, hedged legs (s3b_legs, s3b_leg_names): the perspective relaxation (Clarabel, DESIGN §6;
  src.opt.relaxation.perspective_relaxation) of the 36 N1 instances (as run_n1.relax_task) and of
  the 9 I1 instances at the base bound (base mandate; V_ref = the I1 V there), with w⁺, w⁻, z⁺, z⁻
  stored per name; the value is compared with the one the source run recorded. The formulation is
  not changed.
The I1 and N1 runs are pinned in the config; their outputs.json hashes are checked first.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

import experiments.run_i1 as i1
import experiments.run_n1 as n1
from experiments import s3
from experiments.common import fail, file_sha256, finish, open_run
from experiments.cont import pool_chunks
from experiments.designs import config
from src.analysis.s3b import (fixed_active_set, hedged_names, support_signature,
                              z_from_weights)
from src.opt.integer import PMI
from src.opt.relaxation import perspective_relaxation
from src.utils import ROOT

CONFIG = "experiments/configs/s3b.yaml"
SUPPORT_FRAMES = ("s3b_support",)
LEG_FRAMES = ("s3b_legs", "s3b_leg_names")
POINTS = ("minus", "b", "plus")


def load_run(rel: str) -> dict[str, pd.DataFrame]:
    """A pinned run's parquet frames, after checking every output against its outputs.json."""
    run = ROOT / rel
    if not (run / "DONE").exists() or (run / "SUPERSEDED").exists() or (run / "FAILED").exists():
        raise RuntimeError(f"{rel} is not a finished current run")
    hashes = json.loads((run / "outputs.json").read_text())
    bad = [f for f, h in hashes.items() if file_sha256(run / f) != h]
    if bad:
        raise ValueError(f"{rel}: outputs differ from outputs.json: {bad}")
    return {f[:-8]: pd.read_parquet(run / f) for f in hashes if f.endswith(".parquet")}


def i1_leg_id(instance: str) -> str:
    """The I1 base-bound relaxation's id; the prefix keeps it apart from N1's relax ids, which
    coincide for the shared N = 250 instances."""
    return f"i1-{instance}_base"


def check_unique_ids(tasks: list[dict]) -> None:
    ids = pd.Series([t["id"] for t in tasks])
    dup = sorted(ids[ids.duplicated()].unique())
    if dup:
        raise ValueError(f"duplicate task ids: {dup}")


def support_task(t: dict) -> dict[str, pd.DataFrame]:
    """Item 3 at one I1 case (module docstring). t: run_i1.make_task's task plus the case's
    stored "weights" (point, i, w) and "points" (point, bound, V, mu_fixed)."""
    ids = {k: t[k] for k in ("id", "instance", "date", "N", "f", "K", "key", "b", "rel_delta")}
    P = PMI(**t["kwargs"], formulation="bigm", s_obj=t["s_obj"])
    ell, s = float(t["kwargs"]["ell"]), float(t["s_obj"])
    rows = []
    for tag in POINTS:
        pr = t["points"][t["points"]["point"] == tag]
        wr = t["weights"][t["weights"]["point"] == tag].sort_values("i")
        if len(pr) != 1 or len(wr) != P.model.N:
            raise ValueError(f"{t['id']} {tag}: {len(pr)} point rows, {len(wr)} weights")
        pr = pr.iloc[0]
        w = wr["w"].to_numpy(float)
        i1._set(P, t["key"], float(pr["bound"]))
        zp, zm = z_from_weights(w, ell)
        res = P.model.fixed_integer(zp, zm)
        V = res.U / s
        act = fixed_active_set(P.model, res.w)
        rows.append({**ids, "point": tag, "bound": float(pr["bound"]), "V_stored": float(pr["V"]),
                     "V_recomputed": V, "V_rel_diff": abs(V - pr["V"]) / abs(pr["V"]),
                     "w_max_abs_diff": float(np.max(np.abs(res.w - w))),
                     "support": support_signature(w), "support_recomputed": support_signature(res.w),
                     "n_held": int(zp.sum() + zm.sum()), "active_set": ";".join(sorted(act)),
                     "n_active": len(act),
                     "n_active_mandate": sum(not a.startswith(("min:", "cap:")) for a in act),
                     "mu_fixed": P._dual_record(res)["shadow"].get(t["key"], np.nan),
                     "mu_fixed_stored": float(pr["mu_fixed"])})
    return {"s3b_support": pd.DataFrame(rows)}


def legs_task(t: dict) -> dict[str, pd.DataFrame]:
    """Item 5 at one instance (module docstring): t carries kwargs, s_obj, source ("n1" | "i1"),
    and optionally v_ref (original units) and ref_value (the source run's recorded value)."""
    P = PMI(**t["kwargs"], formulation="bigm", s_obj=t["s_obj"])
    s = float(t["s_obj"])
    v_ref = t.get("v_ref")
    cl = perspective_relaxation(P._model("perspective"), v_ref=None if v_ref is None else s * v_ref)
    info = cl.info
    N = P.model.N
    nan = np.full(N, np.nan)
    wp = cl.wp if cl.wp is not None else nan
    wm = cl.wm if cl.wm is not None else nan
    zp, zm = (cl.result.zp, cl.result.zm) if cl.result is not None else (nan, nan)
    md, ell = t["kwargs"]["mandate"], float(t["kwargs"]["ell"])
    h = hedged_names(wp, wm, zp, zm, ell)
    ref = t.get("ref_value", np.nan)
    rec = {k: t.get(k) for k in ("id", "source", "date", "f", "K", "tightness")}
    rec.update(N=str(t.get("N")), lam_star=float(t["kwargs"]["lam"]), s_obj=s, ell=ell,
               borrow_monthly=float(md.borrow_monthly), trade_cost=float(md.trade_cost),
               ok=bool(cl.ok), status=cl.status, fail_reason=info.get("fail_reason"),
               value=info.get("value", np.nan) / s, ref_value=ref,
               value_minus_ref=info.get("value", np.nan) / s - ref,
               n_names=N, n_hedged=len(h), n_prediction_holds=int(h["prediction_holds"].sum()),
               max_min_leg=float(h["min_leg"].max()) if len(h) else 0.0)
    names = pd.DataFrame({"id": t.get("id"), "i": np.arange(N), "wp": wp, "wm": wm, "zp": zp,
                          "zm": zm, "d": np.asarray(t["kwargs"]["d"], float)})
    return {"s3b_legs": pd.DataFrame([rec]), "s3b_leg_names": names}


def main(argv=None) -> int:
    run = None
    try:
        cfg = config("s3b")
        icfg, ncfg = config(cfg["source_configs"]["integer"]), config(cfg["source_configs"]["numerics"])
        for c in (icfg, ncfg):
            if not str(c.get("status", "")).startswith("approved"):
                raise RuntimeError(f"source config not approved: {c.get('status')}")
        I, Nf = load_run(cfg["i1_run"]), load_run(cfg["n1_run"])
        run, _ = open_run("s3b", CONFIG)
        insts = {}

        def inst(ym, N, f, c, Kt):
            k = (ym, str(N), f)
            if k not in insts:
                insts[k] = s3.instance(ym, N, f, c, Kt)
            return insts[k]

        est, pts, wts = I["i1_estimators"], I["i1_points"], I["i1_weights"]
        sup = []
        for _, e in est.sort_values("id").iterrows():
            x = inst(e["date"], icfg["i1"]["N"], float(e["f"]), icfg, icfg["i1"].get("K"))
            t = i1.make_task(icfg, x, {"key": e["key"], "b": float(e["b"])}, float(e["rel_delta"]), float(e["f"]))
            if t["id"] != e["id"]:
                raise ValueError(f"task id {t['id']} != I1 id {e['id']}")
            t.update(weights=wts[wts["id"] == e["id"]], points=pts[pts["id"] == e["id"]])
            sup.append(t)
        exp = cfg["expected"]
        if len(sup) != exp["support_cases"]:
            raise ValueError(f"{len(sup)} support cases, expected {exp['support_cases']}")
        legs = []
        rel = Nf["n1_relax"].set_index("id")
        for p in n1.relax_plan(ncfg):
            x = inst(p["date"], p["N"], p["f"], ncfg, ncfg["n1"].get("K"))
            t = n1.make_relax_task(ncfg, p, x)
            t.update(source="n1", ref_value=float(rel.loc[t["id"], "perspective"]))
            legs.append(t)
        base = est[(est["key"] == "sector") & (est["rel_delta"] == float(icfg["i1"]["rel_delta"]))]
        for _, e in base.sort_values("instance").iterrows():      # sector@0.02 = the base mandate
            x = inst(e["date"], icfg["i1"]["N"], float(e["f"]), icfg, icfg["i1"].get("K"))
            legs.append({"id": i1_leg_id(e["instance"]), "source": "i1", "date": e["date"], "N": e["N"],
                         "f": float(e["f"]), "K": int(e["K"]), "tightness": "base",
                         "kwargs": x.kwargs, "s_obj": float(icfg["s_obj"]), "v_ref": float(e["V"]),
                         "ref_value": float(e["persp_V"])})
        n_leg = exp["n1_relaxations"] + exp["i1_relaxations"]
        if len(legs) != n_leg:
            raise ValueError(f"{len(legs)} relaxations, expected {n_leg}")
        check_unique_ids(sup)
        check_unique_ids(legs)
        w = s3.workers(cfg)
        out = pool_chunks(run, SUPPORT_FRAMES, sup, lambda t: t["id"], support_task, w)
        out.update(pool_chunks(run, LEG_FRAMES, legs, lambda t: t["id"], legs_task, w))
        s, lg = out["s3b_support"], out["s3b_legs"]
        summary = {"support_rows": len(s), "support_cases": int(s["id"].nunique()),
                   "max_V_rel_diff": float(s["V_rel_diff"].max()),
                   "max_w_abs_diff": float(s["w_max_abs_diff"].max()),
                   "support_mismatch": int((s["support"] != s["support_recomputed"]).sum()),
                   "relaxations": len(lg), "relaxations_failed": int((~lg["ok"].astype(bool)).sum()),
                   "max_abs_value_minus_ref": float(lg["value_minus_ref"].abs().max()),
                   "n_hedged_total": int(lg["n_hedged"].sum())}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, CONFIG, out, f"s3b: {summary['support_cases']} cases, {summary['relaxations']} relaxations",
               extra_files=[run / "summary.json"])
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
