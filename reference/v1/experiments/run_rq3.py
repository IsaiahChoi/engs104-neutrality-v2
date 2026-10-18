"""E3 / RQ3 — MIQP sensitivity and formulations (brief §3.4, §7 E3). `make rq3` (needs the freeze).

All designs use the momentum alpha, the base mandate with the MIQP position cap u = 6%
(u_i = min(0.06, θ·ADV_i/AUM)), and λ fixed at the full-universe value for (date, momentum)
from the λ record. A universe subsample of size N is the top N names by 63-day ADV at the date;
the alpha and risk model are the full-universe ones restricted to those names.

Parts (all run, in this order, when no --part is given; H4 runs last and alone):
- h3: dates × K; perspective MIQP at gap 1e-6 (600 s) at the base bounds and at b(1 ± δ) for
  the beta and Mom bounds, δ ∈ {10%, 5%}; relaxation and fixed-integer duals at the incumbent;
  the continuous problem (no cardinality, ℓ = 0, same u and bounds) with its duals and the same
  finite differences. U* for slopes is the polished value (exact QP at the incumbent's z);
  the solver's raw value is stored too. Instances run in parallel worker processes.
- f4: the Mom-bound sweep (41 points) at gap 1e-6, plus duals at the base bound.
- h4: dates × N × K × tightness × {big-M, perspective} at gap 1e-4, 300 s, default presolve;
  time to gap (censored), root gap, nodes, final gap. Strictly sequential, one thread, no other
  heavy job. h4robust: the N = 250 instances again with presolve off.
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

import numpy as np
import pandas as pd

from experiments.common import chunk_path, combine, fail, finish, open_run, write_chunk
from experiments.designs import check_config_path, config, e3_dates
from src.alpha.momentum import IC_ASSUMED, momentum_alpha, momentum_score, winsorized_zscore
from src.opt.attribution import shadow_prices
from src.opt.continuous import ContinuousProblem, load_config
from src.opt.inputs import date_inputs, market_data
from src.opt.lambda_policy import LambdaBook
from src.opt.miqp import MIQPModel, shadow_price
from src.risk.factor_model import FACTORS


def subsample(date, n, how: str = "restrict"):
    """(DateInputs, alpha over the full universe's index, index of the top-n names by ADV).
    how = "restrict": the full-universe alpha; "rezscore": the momentum z-score recomputed (and
    winsorized) within the subsample, placed at the subsample's positions (REVIEW 3 concern 10)."""
    di = date_inputs(date)
    ret = market_data().ret
    alpha = momentum_alpha(di.model, ret)
    idx = np.arange(di.model.N) if n == "full" else np.sort(np.argsort(-di.adv, kind="stable")[:int(n)])
    if how == "rezscore":
        z = winsorized_zscore(momentum_score(ret, di.tickers, di.date)[idx])
        alpha = alpha.copy()
        alpha[idx] = IC_ASSUMED * np.sqrt(di.model.d[idx]) * z
    elif how != "restrict":
        raise ValueError(f"subsample_alpha must be 'restrict' or 'rezscore', got {how!r}")
    return di, alpha, idx


def restricted(di, idx):
    m = di.model
    S = di.sector_matrix()[idx]
    return m.B[idx], m.F, m.d[idx], S[:, S.sum(axis=0) > 0], di.adv[idx], list(np.asarray(di.tickers)[idx])


def miqp_mandate(base, cfg, style=None, beta=None):
    m = replace(base, position=cfg["position_cap"])
    if style is not None:
        m = replace(m, style=style)
    if beta is not None:
        m = replace(m, beta=beta)
    return m


def fam_index(model_or_problem, family):
    if family == "beta":
        return "beta", None
    return "style", model_or_problem.style_names.index(family.split(":")[1])


def miqp_row(res, **ids):
    return {**ids, "U_raw": res.U, "U": res.U_polished, "bound": res.bound,
            "status": res.status_name, "runtime": res.runtime, "nodes": res.nodes,
            "final_gap": res.final_gap, "root_gap": res.root_gap, "reached_gap": res.reached_gap,
            "n_held": int(res.zp.sum() + res.zm.sum())}


# ---------- H3 ----------

def h3_instance(args):
    date, K, cfg, base, lam = args
    h = cfg["h3"]
    di, alpha_full, idx = subsample(date, h["N"], cfg["subsample_alpha"])
    B, F, d, S, adv, tickers = restricted(di, idx)
    alpha = alpha_full[idx]
    mand = miqp_mandate(base, cfg)
    ds = f"{date:%Y-%m-%d}"
    mk = lambda: MIQPModel(B, F, d, S, alpha, lam, mand, adv, K=K, ell=h["ell"],
                           formulation=h["formulation"], factor_names=FACTORS)
    M = mk()
    solve = lambda mdl: mdl.solve(time_limit=h["time_limit"], mip_gap=h["mip_gap"])
    inc = solve(M)
    rows = [miqp_row(inc, date=ds, K=K, constraint="base", delta=0.0, side=0)]
    relax, fixed = M.relax(), M.fixed_integer(inc.zp, inc.zm)
    P = ContinuousProblem(B, F, d, S, mand, adv=adv, factor_names=FACTORS)
    cont = P.solve(alpha, lam=lam)
    sp_cont = shadow_prices(P, cont)
    est = []
    for c in h["constraints"]:
        fam, k = fam_index(M, c)
        b0 = M.bound(fam) if k is None else M.bound(fam)[k]
        mu_rel, mu_fix = shadow_price(relax, fam, k), shadow_price(fixed, fam, k)
        mu_cont = sp_cont[fam] if k is None else sp_cont[f"style:{c.split(':')[1]}"]
        for delta in (h["delta"], h["delta_robustness"]):
            U, Uc = {}, {}
            for side in (+1, -1):
                Mi = mk()
                Mi.set_bound(fam, b0 * (1 + side * delta), k)
                r = solve(Mi)
                rows.append(miqp_row(r, date=ds, K=K, constraint=c, delta=delta, side=side))
                U[side] = (r.U_polished, r.U, r.reached_gap)
                Pc = ContinuousProblem(B, F, d, S, mand, adv=adv, factor_names=FACTORS)
                Pc.set_bound(fam, b0 * (1 + side * delta), k)
                Uc[side] = Pc.solve(alpha, lam=lam).objective
            step = 2 * delta * b0
            est.append({"date": ds, "K": K, "constraint": c, "delta": delta, "bound": b0,
                        "U_star": inc.U_polished, "U_star_raw": inc.U,
                        "slope": (U[1][0] - U[-1][0]) / step,
                        "slope_raw": (U[1][1] - U[-1][1]) / step,
                        "all_reached_gap": bool(inc.reached_gap and U[1][2] and U[-1][2]),
                        "mu_relax": mu_rel, "mu_fixed": mu_fix,
                        "cont_U": cont.objective, "cont_slope": (Uc[1] - Uc[-1]) / step,
                        "mu_cont": mu_cont, "N": len(idx), "lam": lam})
    return pd.DataFrame(rows), pd.DataFrame(est)


# ---------- F4 ----------

def f4_point(args):
    date, b, cfg, base, lam = args
    f = cfg["f4"]
    di, alpha_full, idx = subsample(date, f["N"], cfg["subsample_alpha"])
    B, F, d, S, adv, _ = restricted(di, idx)
    M = MIQPModel(B, F, d, S, alpha_full[idx], lam, miqp_mandate(base, cfg), adv, K=f["K"],
                  ell=f["ell"], formulation="perspective", factor_names=FACTORS)
    fam, k = fam_index(M, f["family"])
    M.set_bound(fam, b, k)
    r = M.solve(time_limit=f["time_limit"], mip_gap=f["mip_gap"])
    return miqp_row(r, date=f"{date:%Y-%m-%d}", bound_value=b)


def f4_duals(date, cfg, base, lam):
    f = cfg["f4"]
    di, alpha_full, idx = subsample(date, f["N"], cfg["subsample_alpha"])
    B, F, d, S, adv, _ = restricted(di, idx)
    M = MIQPModel(B, F, d, S, alpha_full[idx], lam, miqp_mandate(base, cfg), adv, K=f["K"],
                  ell=f["ell"], formulation="perspective", factor_names=FACTORS)
    fam, k = fam_index(M, f["family"])
    inc = M.solve(time_limit=f["time_limit"], mip_gap=f["mip_gap"])
    relax, fixed = M.relax(), M.fixed_integer(inc.zp, inc.zm)
    return pd.DataFrame([{"date": f"{date:%Y-%m-%d}", "bound": M.bound(fam)[k], "U_star": inc.U_polished,
                          "U_relax": relax.U, "mu_relax": shadow_price(relax, fam, k),
                          "U_fixed": fixed.U, "mu_fixed": shadow_price(fixed, fam, k),
                          "reached_gap": inc.reached_gap}])


# ---------- H4 ----------

def h4_instances(cfg, robust=False):
    h = cfg["h4"]
    out = []
    for date in e3_dates()["h4"]:
        for n in ([h["presolve_off_robustness_N"]] if robust else h["N"]):
            for K in h["K"]:
                for tight in h["tightness"]:
                    for form in h["formulations"]:
                        out.append((date, n, K, tight, form))
    return out


def h4_solve(date, n, K, tight, form, cfg, base, lam, presolve):
    h = cfg["h4"]
    di, alpha_full, idx = subsample(date, n, cfg["subsample_alpha"])
    B, F, d, S, adv, _ = restricted(di, idx)
    t = h["tightness"][tight]
    M = MIQPModel(B, F, d, S, alpha_full[idx], lam, miqp_mandate(base, cfg, t["style"], t["beta"]),
                  adv, K=K, ell=h["ell"], formulation=form, factor_names=FACTORS)
    r = M.solve(time_limit=h["time_limit"], mip_gap=h["mip_gap"], presolve=presolve)
    # Secondary (computed after the timed solve, so it does not affect times): the gap of this
    # formulation's continuous relaxation to the polished incumbent, which unlike the solver's
    # root gap does not depend on Gurobi's internal root processing.
    # A failed relaxation (e.g. barrier stops SUBOPTIMAL on a perspective QCP) is recorded as
    # missing with its status; it must never abort the timing design (first E3 run crashed here).
    try:
        U_relax, relax_status = M.relax().U, "OPTIMAL"
    except RuntimeError as err:
        U_relax, relax_status = float("nan"), str(err)
    return miqp_row(r, date=f"{date:%Y-%m-%d}", N=len(idx), N_label=str(n), K=K,
                    tightness=tight, formulation=form, presolve=presolve,
                    time_to_gap=min(r.runtime, h["time_limit"]), U_relax=U_relax,
                    relaxation_status=relax_status,
                    relaxation_gap=(U_relax - r.U_polished) / abs(r.U_polished))


# ---------- driver ----------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="experiments/configs/rq3.yaml")
    p.add_argument("--part", choices=["h3", "f4", "h4", "h4robust"], action="append")
    args = p.parse_args()
    check_config_path("rq3", args.config)
    parts = args.part or ["h3", "f4", "h4", "h4robust"]
    run = None
    try:
        cfg = config("rq3")
        if cfg.get("subsample_alpha") not in ("restrict", "rezscore"):
            raise RuntimeError("rq3.yaml subsample_alpha is undecided (REVIEW 3 concern 10): "
                               "Isaiah chooses 'restrict' or 'rezscore' (with an amendment if needed)")
        base, _ = load_config(cfg["mandate_config"])
        run, meta = open_run("rq3", args.config)
        book = LambdaBook(meta["lambda_book"])
        lam = {d: book.get(f"{d:%Y-%m-%d}", "momentum") for v in e3_dates().values() for d in v}
        workers = cfg.get("workers", 4)
        if "h3" in parts:
            jobs = [(d, K, cfg, base, lam[d]) for d in e3_dates()["h3"] for K in cfg["h3"]["K"]
                    if not chunk_path(run, "h3_est", f"{d:%Y-%m-%d}_K{K}").exists()]
            with ProcessPoolExecutor(max_workers=workers) as ex:
                for (d, K, *_), (rows, est) in zip(jobs, ex.map(h3_instance, jobs)):
                    key = f"{d:%Y-%m-%d}_K{K}"
                    write_chunk(chunk_path(run, "h3_solves", key), rows)
                    write_chunk(chunk_path(run, "h3_est", key), est)
                    print(f"h3 {key} done", flush=True)
        if "f4" in parts:
            f = cfg["f4"]
            d = e3_dates()["f4"][0]
            grid = np.linspace(f["grid"]["start"], f["grid"]["stop"], f["grid"]["points"])
            if not chunk_path(run, "f4_sweep", "sweep").exists():
                jobs = [(d, float(b), cfg, base, lam[d]) for b in grid]
                with ProcessPoolExecutor(max_workers=workers) as ex:
                    rows = list(ex.map(f4_point, jobs))
                write_chunk(chunk_path(run, "f4_sweep", "sweep"), pd.DataFrame(rows))
            if not chunk_path(run, "f4_duals", "duals").exists():
                write_chunk(chunk_path(run, "f4_duals", "duals"), f4_duals(d, cfg, base, lam[d]))
            print("f4 done", flush=True)
        for part, robust, presolve in (("h4", False, -1), ("h4robust", True, 0)):
            if part not in parts:
                continue
            for (d, n, K, tight, form) in h4_instances(cfg, robust):
                key = f"{d:%Y-%m-%d}_N{n}_K{K}_{tight}_{form}"
                path = chunk_path(run, part, key)
                if path.exists():
                    continue
                row = h4_solve(d, n, K, tight, form, cfg, base, lam[d], presolve)
                write_chunk(path, pd.DataFrame([row]))
                print(f"{part} {key}: {row['status']} {row['runtime']:.1f}s", flush=True)
        expected = {"h3_est": len(e3_dates()["h3"]) * len(cfg["h3"]["K"]), "f4_sweep": 1,
                    "f4_duals": 1, "h4": len(h4_instances(cfg)), "h4robust": len(h4_instances(cfg, True))}
        have = {k: len(list((run / "chunks" / k).glob("*.parquet"))) for k in expected}
        if have == expected:
            finish(run, args.config, {k: combine(run, k) for k in
                                      ("h3_solves", "h3_est", "f4_sweep", "f4_duals", "h4", "h4robust")},
                   "rq3 all parts")
        else:
            print(f"rq3 incomplete: {have} of {expected}", flush=True)
    except Exception as e:
        fail(run, args.config, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
