"""N2 — numerics (DESIGN §7): `make n2` → results/n2/run_<UTC>/.

Refused while numerics.yaml is "proposed, pending GATE DESIGN"; `make n2 RUNARGS="--config
experiments/configs/smoke_n2.yaml"` is the S2d crash test (RUN_LOG "pilot").

- (a) MIQP: the N1 instances at the configured N and tightness (dates and f from n1 unless n2.miqp
  names them), each arm at each s_obj, MIPGap and WorkLimit as configured. One chunk per solve;
  the record is N1's.
- (b) Convex: C1 base (α_mom, base mandate) at each date, full universe unless the config gives N.
  The explicit P-RB QCQP (src.opt.risk_budget.solve_qcqp) for each solver × {risk row normalized
  or not} × {objective scaled or not}: Gurobi barrier (Method 2) and the installed conic solvers
  at their default tolerances (the kept code's tighter settings are overridden). The scale is
  DESIGN §6's power of ten for |A*| (src.opt.integer.choose_s_obj on the root-found QP's A*),
  recorded. Reference: Clarabel on the normalized, scaled problem at tolerance `tol`. Per solve:
  status, A*, |ΔA*|/|A*_ref|, ‖Δw‖₁/‖w_ref‖₁, the binding duals' relative errors (binding: the
  reference's elasticity ≥ 1e-4), solve time, the checker's verdict and the risk row's excess.
  A solver failure is recorded with its message, never raised.
The summary holds statuses, counts, Work and Runtime only.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments import s3
from experiments.common import finish, fail, open_run
from experiments.cont import case, pool_chunks, problem
from experiments.instances import restricted, subsample
from experiments.run_n1 import ARMS
from src.opt.attribution import shadow_prices
from src.opt.continuous import ContinuousProblem
from src.opt.feasibility import risk_violation
from src.opt.gurobi_env import quiet_env
from src.opt.integer import PMI, choose_s_obj
from src.opt.risk_budget import SIGMA_M, solve_qcqp, solve_risk_budget
from src.opt.sensitivity import BINDING_ELASTICITY, elasticities
from src.risk.factor_model import FACTORS

MIQP_FRAMES = ("n2_miqp", "n2_miqp_weights")
CONVEX_FRAMES = ("n2_convex", "n2_convex_duals")
DEFAULT_TOLS = {
    "GUROBI_BARRIER": {"Method": 2, "FeasibilityTol": 1e-6, "OptimalityTol": 1e-6},   # Gurobi defaults
    "CLARABEL": {"tol_gap_abs": 1e-8, "tol_gap_rel": 1e-8, "tol_feas": 1e-8, "max_iter": 200},
    "SCS": {},
    "ECOS": {},
}


# ----- (a) MIQP -----

def miqp_plan(cfg: dict) -> list[dict]:
    m, n1 = cfg["n2"]["miqp"], cfg.get("n1", {})
    out = []
    for ym in m.get("dates", n1.get("dates")):
        for f in m.get("f", n1.get("f")):
            for arm in m["formulations"]:
                for s in m["s_obj"]:
                    out.append({"date": ym, "N": m["N"], "f": float(f), "tightness": m["tightness"],
                                "arm": arm, "s_obj": float(s)})
    return out


def miqp_task(t: dict) -> dict[str, pd.DataFrame]:
    form, rescale = ARMS[t["arm"]]
    M = PMI(**t["kwargs"], formulation=form, s_obj=t["s_obj"], rescale=rescale)
    r = M.solve(mip_gap=t["mip_gap"], work_limit=t["work_limit"], cone_diag=True)
    ids = {k: t[k] for k in ("id", "date", "N", "f", "K", "tightness", "arm", "s_obj", "lam_star", "workers")}
    w = pd.DataFrame({"id": t["id"], "i": np.arange(len(r.w)), "w": r.w, "zp": r.zp, "zm": r.zm})
    return {"n2_miqp": pd.DataFrame([s3.pmi_record(r, ids)]), "n2_miqp_weights": w}


# ----- (b) convex -----

def convex_variants(c: dict) -> list[dict]:
    """Every configured solver × normalized × scaled, at default tolerances."""
    return [{"solver": s, "normalize": nz, "scaled": sc}
            for s in c["solvers"] for nz in (False, True) for sc in (False, True)]


def convex_item(cfg: dict, ym: str, N=None) -> dict:
    c = cfg["n2"]["convex"]
    return {"date": ym, "N": N if N is not None else c.get("N", "full"), "variants": convex_variants(c),
            "reference": c["reference"]}


def _problem(ym: str, N):
    base = s3.base_mandate()
    di, alpha = case(ym)
    if N == "full":
        return problem(di, base), np.asarray(alpha, float)
    _, alpha_full, idx = subsample(di.date, N)
    B, F, d, S, adv, _ = restricted(di, idx)
    return (ContinuousProblem(B, F, d, S, base, adv=adv, factor_names=FACTORS),
            np.asarray(alpha_full[idx], float))


def _solve(P, alpha, solver: str, normalize: bool, s: float, opts: dict):
    name = "GUROBI" if solver == "GUROBI_BARRIER" else solver
    kw = dict(opts)
    if name == "GUROBI":
        kw["env"] = quiet_env(1, 0)
    return solve_qcqp(P, alpha, normalize=normalize, obj_scale=s, solver=name, **kw)


def convex_task(item: dict) -> dict[str, pd.DataFrame]:
    P, alpha = _problem(item["date"], item["N"])
    rb = solve_risk_budget(P, alpha)
    s = choose_s_obj(rb.A)
    ref_cfg = item["reference"]
    tol = float(ref_cfg["tol"])
    ref = _solve(P, alpha, ref_cfg["solver"], True, s if ref_cfg.get("scaled", True) else 1.0,
                 {"tol_gap_abs": tol, "tol_gap_rel": tol, "tol_feas": tol, "max_iter": 500})
    sp_ref = shadow_prices(P, ref)
    e = elasticities(P, sp_ref, ref.objective)
    binding = [k for k, v in e.items() if np.isfinite(v) and v >= BINDING_ELASTICITY]
    rows, duals = [], []

    def record(label: str, v: dict, sol, err: str | None):
        row = {"date": item["date"], "N": P.N, "solver": label, "normalize": v.get("normalize"),
               "scaled": v.get("scaled"), "obj_scale": s if v.get("scaled") else 1.0,
               "ok": sol is not None, "error": err, "status": getattr(sol, "status", "failed"),
               "solve_time": getattr(sol, "solve_time", np.nan), "A_qp": rb.A, "lam_qp": rb.lam,
               "A_ref": ref.objective}
        if sol is None:
            row.update(A=np.nan, A_rel_err=np.nan, w_l1_rel_err=np.nan, max_binding_dual_rel_err=np.nan,
                       checker="not run", risk_excess=np.nan)
        else:
            sp = shadow_prices(P, sol)
            errs = {k: abs(sp[k] - sp_ref[k]) / abs(sp_ref[k]) for k in binding}
            duals.extend({"date": item["date"], "solver": label, "normalize": v.get("normalize"),
                          "scaled": v.get("scaled"), "key": k, "mu": sp[k], "mu_ref": sp_ref[k],
                          "rel_err": x} for k, x in errs.items())
            row.update(A=sol.objective, A_rel_err=abs(sol.objective - ref.objective) / abs(ref.objective),
                       w_l1_rel_err=float(np.abs(sol.w - ref.w).sum() / np.abs(ref.w).sum()),
                       max_binding_dual_rel_err=max(errs.values()) if errs else np.nan,
                       checker=s3.continuous_verdict(P, sol.w),
                       risk_excess=risk_violation(sol.w, P.B, P.F, P.d, SIGMA_M))
        rows.append(row)

    record("reference", {"normalize": True, "scaled": bool(ref_cfg.get("scaled", True))}, ref, None)
    for v in item["variants"]:
        try:
            sol = _solve(P, alpha, v["solver"], v["normalize"], s if v["scaled"] else 1.0,
                         DEFAULT_TOLS.get(v["solver"], {}))
            record(v["solver"], v, sol, None)
        except Exception as err:                          # a solver failure is a result here
            record(v["solver"], v, None, f"{type(err).__name__}: {err}")
    return {"n2_convex": pd.DataFrame(rows), "n2_convex_duals": pd.DataFrame(duals)}


def main(argv=None) -> int:
    run = None
    cfg_path = "experiments/configs/numerics.yaml"
    try:
        cfg_path, cfg, status = s3.load_run_config("n2", argv)
        run, _ = open_run("n2", cfg_path, status=status)
        m = cfg["n2"]["miqp"]
        tight = cfg["n1"]["tightness"][m["tightness"]]
        insts, tasks = {}, []
        for p in miqp_plan(cfg):
            k = (p["date"], p["N"], p["f"])
            if k not in insts:
                insts[k] = s3.instance(p["date"], p["N"], p["f"], cfg, cfg["n1"].get("K"))
            inst = insts[k]
            tasks.append({**p, "id": f"{p['date']}_N{p['N']}_f{p['f']:g}_K{inst.K}_{p['tightness']}_"
                                      f"{p['arm']}_s{p['s_obj']:g}",
                          "K": inst.K, "lam_star": inst.lam,
                          "kwargs": {**inst.kwargs, "mandate": s3.tightened(inst.mandate, tight)},
                          "mip_gap": float(m["mip_gap"]),
                          "work_limit": float(m["work_limit_factor"]) * float(cfg["W_star"]),
                          "workers": s3.workers(cfg)})
        wk = s3.workers(cfg)
        out = pool_chunks(run, MIQP_FRAMES, tasks, lambda t: t["id"], miqp_task, wk)
        items = [convex_item(cfg, ym) for ym in cfg["n2"]["convex"]["dates"]]
        out.update(pool_chunks(run, CONVEX_FRAMES, items, lambda t: t["date"], convex_task, wk))
        cv = out["n2_convex"]
        summary = {"miqp": s3.solve_summary(out["n2_miqp"]),
                   "convex": {"n": len(cv), "statuses": {str(k): int(v) for k, v in cv["status"].value_counts().items()},
                              "n_failed": int((~cv["ok"]).sum()),
                              "solve_time_total": float(cv["solve_time"].sum())}}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        finish(run, cfg_path, out, f"n2: miqp {summary['miqp'].get('statuses')}; convex {summary['convex']['statuses']}",
               extra_files=[run / "summary.json"])
        print(json.dumps(summary, indent=1, default=float))
    except Exception as e:
        fail(run, cfg_path, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
