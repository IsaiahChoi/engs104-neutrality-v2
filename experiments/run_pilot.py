"""S2 design pilot (DESIGN §8, P1–P7): `make pilot` → results/pilot/run_<UTC>/ (RUN_LOG status
"pilot"). The pilot sets the parameter rules of the integer experiments; no number here is a
DESIGN §7 result.

- P1 (P-RB path and scaling): at D12, base, α_mom, the root-found QP against the Clarabel QCQP:
  A* to 1e-6 relative, λ* against Clarabel's risk-row dual to 1e-5, binding duals (e ≥ 1e-4)
  to 1e-4; root-finder QP solves and time per point.
- P2: the risk-binding flag at base for D12 × {α_mom, α⊥, α∥}, with every elasticity (P6 ranks
  its candidates on these, which are C1's numbers at the I1 dates).
- P3: the continuous support S (|w_i| > 1e-6 in P-RB with u = 6%) for every I1/N1 (date, N);
  K = round(f·S) (half up, at least 1); λ*; and U_mv, the P-MI objective at the P-RB solution
  (K ≥ N, ℓ = 0, an upper bound on U*), the proxy for |U*| behind s_obj.
- s_obj (DESIGN §6: a power of 10 with |U*|·s_obj in [1, 100]). Rule fixed here, before any
  P-MI solve: the power of 10 that puts the geometric mean of the P3 proxies closest to 10 (the
  log-centre of [1, 100]). Whether every proxy, and every P4 value V, lands in [1, 100] is
  recorded.
- P4 (formulation agreement): 8 instances (2017-12, 2020-03 × f ∈ {0.25, 0.5} × {base, tight},
  N = 250), both formulations, MIPGap 1e-4, s_obj, Threads 1, Seed 0, TimeLimit 300 s (W* is not
  known before P5; 300 s is DESIGN §6's fallback). Pass iff |V_bigM − V_persp| ≤ max over the
  two formulations of B_eff − V (B_eff = max(B, V) + 1e-6·|V|). A9 diagnostics per solve, all
  relative to |V|: the signed B − V and U_incumbent − V and, for the perspective model, the
  cones' violation effect λ*·Σ_i d_i·max(0, w_i²/ζ_i − s_i) at Gurobi's raw incumbent (Isaiah's
  S2 instruction, 2026-10-19; src.opt.integer.cone_violation_effect).
- P5: Gurobi's version; the Work attribute; WorkLimit (a P4 instance stopped by a tiny limit);
  Work per second on the P4 solves (measured with `workers` solves running at once, as S3 will
  run); W* = the Work of 300 s at the median rate, rounded to 2 significant figures.
- P6 (I1 constraint selection): candidates are the 4 constraint keys (families and single style
  factors; position, liquidity and single sectors excluded) with the largest median elasticity
  over the I1 dates in P2 (α_mom), plus the Mom bound at 0.025. Certified central differences in
  P-MI (perspective; 2017-12, N = 250, f = 0.5; δ = 10% of the bound; MIPGap 1e-6, WorkLimit
  2·W*: the I1 settings). Keep L > 0 (L from B_eff), at most 4, in candidate order, with a factor
  bound included if any factor bound has L > 0.
- P7: the S3 run-time projection (Work and wall time at 4 workers) from P4/P6 Work.
MIQP solves run in a process pool (`workers` processes, each Threads 1); each finished solve is
a chunk, so a killed run resumes (experiments/common.py).
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace

import gurobipy as gp
import numpy as np
import pandas as pd

from experiments.common import chunk_path, combine, fail, finish, open_run, write_chunk
from experiments.designs import config, month_end
from experiments.instances import pmi_instance, round_half_up
from src.alpha.decompose import alpha_set
from src.alpha.momentum import momentum_alpha
from src.opt.attribution import shadow_prices
from src.opt.certified import certified_interval, certified_interval_eff, effective_bound
from src.opt.continuous import MKT, ContinuousProblem, load_config
from src.opt.feasibility import pmi_violations
from src.opt.integer import PMI
from src.opt.inputs import date_inputs, market_data
from src.opt.risk_budget import solve_qcqp, solve_risk_budget
from src.opt.sensitivity import BINDING_ELASTICITY, elasticities
from src.risk.factor_model import FACTORS

CONFIG = "experiments/configs/pilot.yaml"
FORMS = ("bigm", "perspective")
EXCLUDED = ("position", "liquidity")          # DESIGN §8 P6: they set the P-MI formulation
STYLE_NAMES = [f for f in FACTORS if f != MKT]


# ----- continuous items (P1–P3) -----

def _case(ym):
    di = date_inputs(month_end(ym))
    return di, momentum_alpha(di.model, market_data().ret)


def _prob(di, mandate):
    m = di.model
    return ContinuousProblem(m.B, m.F, m.d, di.sector_matrix(), mandate, adv=di.adv,
                             factor_names=FACTORS)


def p1_row(ym: str, base, tol: dict) -> tuple[dict, list[dict]]:
    di, alpha = _case(ym)
    P = _prob(di, base)
    t0 = time.perf_counter()
    rb = solve_risk_budget(P, alpha)
    t_root = time.perf_counter() - t0
    t0 = time.perf_counter()
    q = solve_qcqp(P, alpha)
    t_qcqp = time.perf_counter() - t0
    sq, sc = shadow_prices(P, rb.sol), shadow_prices(P, q)
    e = elasticities(P, sq, rb.A)
    ds = f"{di.date:%Y-%m-%d}"
    duals = [{"date": ds, "key": k, "sp_qp": v, "sp_qcqp": sc[k], "e_qp": e[k],
              "binding": bool(e[k] >= BINDING_ELASTICITY),
              "rel_diff": abs(sc[k] - v) / abs(v) if v != 0 else np.nan} for k, v in sq.items()]
    bind = [r["rel_diff"] for r in duals if r["binding"]]
    row = {"date": ds, "N": P.N, "A_qp": rb.A, "A_qcqp": q.objective,
           "A_rel": abs(q.objective / rb.A - 1), "lam_qp": rb.lam, "mu_risk_qcqp": q.lam,
           "lam_rel": abs(q.lam / rb.lam - 1), "n_binding": len(bind),
           "max_binding_dual_rel": float(max(bind)) if bind else np.nan,
           "risk_binding": rb.risk_binding, "vol_ann": rb.vol_ann, "root_solves": rb.n_solves,
           "root_time_s": t_root, "qp_solve_time_s": rb.solve_time, "qcqp_time_s": t_qcqp,
           "qcqp_status": q.status}
    row["pass"] = bool(row["A_rel"] <= tol["A_rel"] and row["lam_rel"] <= tol["lam_rel"]
                       and (not bind or row["max_binding_dual_rel"] <= tol["dual_rel"]))
    return row, duals


def p2_rows(ym: str, base) -> list[dict]:
    di, alpha = _case(ym)
    m = di.model
    aset = alpha_set(alpha, m.B, m.F, m.d)
    P = _prob(di, base)
    rows = []
    for kind, a in aset["alphas"].items():
        rb = solve_risk_budget(P, a)
        e = elasticities(P, shadow_prices(P, rb.sol), rb.A)
        rows.append({"date": f"{di.date:%Y-%m-%d}", "month": ym, "alpha": kind,
                     "phi": aset["phi"][kind], "A": rb.A, "lam": rb.lam, "vol_ann": rb.vol_ann,
                     "risk_binding": rb.risk_binding, "n_solves": rb.n_solves,
                     **{f"e_{k}": v for k, v in e.items()}})
    return rows


def _p3_keys(cfg) -> tuple[list, set, set]:
    i1 = [(ym, str(cfg["i1"]["N"])) for ym in cfg["i1"]["dates"]]
    n1 = [(ym, str(n)) for ym in cfg["n1"]["dates"] for n in cfg["n1"]["N"]]
    return list(dict.fromkeys(i1 + n1)), set(i1), set(n1)


def p3_instances(cfg) -> dict:
    """The base P-MI instance (f = 0.5) of every I1/N1 (date, N); K is set per solve."""
    keys, _, _ = _p3_keys(cfg)
    return {(ym, n): pmi_instance(month_end(ym), n if n == "full" else int(n), 0.5)
            for ym, n in keys}


def p3_rows(cfg, insts) -> list[dict]:
    _, i1, n1 = _p3_keys(cfg)
    rows = []
    for (ym, n), inst in insts.items():
        P = ContinuousProblem(inst.B, inst.F, inst.d, inst.S, inst.mandate, adv=inst.adv,
                              factor_names=FACTORS)
        rb = solve_risk_budget(P, inst.alpha, lam_guess=inst.lam)
        row = {"month": ym, "date": f"{inst.date:%Y-%m-%d}", "n_label": n, "N": inst.N,
               "S": inst.S_support, "lam_star": inst.lam, "risk_binding": inst.risk_binding,
               "A_star": rb.A, "U_mv": rb.sol.objective,
               "lam_recheck_rel": abs(rb.lam / inst.lam - 1),
               "in_i1": (ym, n) in i1, "in_n1": (ym, n) in n1}
        for f in sorted(set(cfg["i1"]["f"]) | set(cfg["n1"]["f"])):
            row[f"K_f{f:g}"] = max(1, round_half_up(f * inst.S_support))
        rows.append(row)
    return rows


def choose_s_obj_centred(values, window=(1.0, 100.0)) -> dict:
    """The power of 10 putting the geometric mean of |values| closest to the window's log-centre
    (10 for [1, 100]), and whether every value lands inside the window."""
    v = np.abs(np.asarray(values, float))
    centre = 0.5 * (math.log10(window[0]) + math.log10(window[1]))
    s = 10.0 ** round(centre - float(np.mean(np.log10(v))))
    return {"s_obj": s, "rule": "power of 10 putting the geometric mean of the P3 |U_mv| "
            "proxies closest to 10", "proxy_min_scaled": float(v.min() * s),
            "proxy_max_scaled": float(v.max() * s),
            "proxies_inside": bool(np.all((v * s >= window[0]) & (v * s <= window[1])))}


# ----- MIQP solves in worker processes (P4, P5 probe, P6) -----

def _effective_mandate(M: PMI, md):
    """The Mandate behind M's current bounds and the per-factor style bounds if not common."""
    sb = np.asarray(M.bound("style"), float) if md.style is not None else None
    common = sb is None or bool(np.all(sb == sb[0]))
    sec = np.asarray(M.bound("sector"), float) if md.sector is not None else None
    if sec is not None and not np.all(sec == sec[0]):
        raise ValueError("per-sector bounds are not used by the pilot")
    eff = replace(md, style=float(sb[0]) if sb is not None and common else None,
                  beta=float(M.bound("beta")) if md.beta is not None else None,
                  dollar=float(M.bound("dollar")) if md.dollar is not None else None,
                  gross=float(M.bound("gross")) if md.gross is not None else None,
                  sector=float(sec[0]) if sec is not None else None)
    return eff, (None if common else sb)


def _violations(M: PMI, r, kw, tol: float) -> str:
    """The independent checker on V's (polished) weights at the solve's bounds, at `tol`."""
    if not np.isfinite(r.V):
        return "V undefined"
    eff, sb = _effective_mandate(M, kw["mandate"])
    v = pmi_violations(r.w, r.zp, r.zm, kw["B"], kw["S"], eff, kw["K"], kw["ell"], kw["adv"],
                       mkt=M.model.mkt, tol=tol)
    if sb is not None:
        y = np.asarray(kw["B"], float).T @ r.w
        idx = [k for k in range(len(y)) if k != M.model.mkt]
        v.update({f"style:{FACTORS[k]}": float(abs(y[k]) - b)
                  for k, b in zip(idx, sb) if abs(y[k]) > b + tol})
    return json.dumps(v, sort_keys=True)


def solve_task(task: dict) -> dict:
    """One P-MI solve (Threads 1): its record and weights. task["bounds"] holds (family, value,
    index) settings applied to the instance before the solve."""
    kw = task["kwargs"]
    M = PMI(**kw, formulation=task["formulation"], s_obj=task["s_obj"])
    for fam, value, index in task.get("bounds", []):
        M.set_bound(fam, value, index)
    r = M.solve(mip_gap=task["mip_gap"], work_limit=task.get("work_limit"),
                time_limit=task.get("time_limit", float("inf")), cone_diag=True)
    Beff = effective_bound(r.B, r.V) if np.isfinite(r.V) else np.nan
    rel = (lambda x: x / abs(r.V)) if np.isfinite(r.V) and r.V != 0 else (lambda x: np.nan)
    rec = {k: task.get(k) for k in ("key", "item", "formulation", "s_obj", "mip_gap", "candidate",
                                    "b", "delta", "sign")}
    rec.update(time_limit=task.get("time_limit", np.inf), work_limit=task.get("work_limit", np.nan),
               bounds=json.dumps(task.get("bounds", [])), status=r.status_name,
               reached_gap=r.reached_gap, v_source=r.v_source, polish_status=r.polish_status,
               V=r.V, B=r.B, B_eff=Beff, gap_eff=rel(Beff - r.V), final_gap=r.final_gap,
               root_bound=r.root_bound, U_raw=r.U_raw, U_incumbent=r.U_incumbent,
               B_minus_V=r.B_minus_V, incumbent_minus_V=r.incumbent_minus_V,
               B_minus_V_rel=rel(r.B_minus_V), incumbent_minus_V_rel=rel(r.incumbent_minus_V),
               cone_effect=r.cone_effect, cone_effect_rel=rel(r.cone_effect),
               cone_n_capped=r.cone_n_capped,
               flag_incumbent_exceeds_polished=r.flag_incumbent_exceeds_polished,
               flag_polished_exceeds_bound=r.flag_polished_exceeds_bound,
               scaled_abs_V=abs(r.V) * task["s_obj"], work=r.work, runtime=r.runtime,
               nodes=r.nodes, n_held=int((r.zp + r.zm).sum()), K=kw["K"], N=len(kw["d"]),
               lam_star=kw["lam"], violations=_violations(M, r, kw, 1e-7),
               violations_1e9=_violations(M, r, kw, 1e-9))     # Decision 24 (recorded only)
    w = pd.DataFrame({"key": task["key"], "formulation": task["formulation"],
                      "i": np.arange(len(kw["d"])), "w": r.w, "zp": r.zp, "zm": r.zm,
                      "w_incumbent": r.w_incumbent})
    return {"rec": rec, "w": w}


def _name(t: dict) -> str:
    return f"{t['key']}__{t['formulation']}"


def run_tasks(run, kind: str, tasks: list[dict], workers: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Solve every task not already a chunk (resume), `workers` at a time; one chunk per solve."""
    todo = [t for t in tasks if not chunk_path(run, kind, _name(t)).exists()]
    if todo:
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
            futs = {ex.submit(solve_task, t): t for t in todo}
            for fut in as_completed(futs):
                t, res = futs[fut], fut.result()
                write_chunk(chunk_path(run, f"{kind}_w", _name(t)), res["w"])
                write_chunk(chunk_path(run, kind, _name(t)), pd.DataFrame([res["rec"]]))
                rc = res["rec"]
                print(f"{kind} {_name(t)}: {rc['status']} V={rc['V']:.6g} gap_eff={rc['gap_eff']:.2e} "
                      f"work={rc['work']:.4g} t={rc['runtime']:.0f}s", flush=True)
    return combine(run, kind), combine(run, f"{kind}_w")


# ----- P4 -----

def p4_tasks(cfg, insts, s_obj: float) -> list[dict]:
    c = cfg["p4"]
    tasks = []
    for ym in c["dates"]:
        inst = insts[(ym, str(c["N"]))]
        for f in c["f"]:
            K = max(1, round_half_up(f * inst.S_support))
            for tight in c["tightness"]:
                md = inst.mandate if tight == "base" else replace(inst.mandate, **cfg["n1"]["tight"])
                kw = {**inst.kwargs, "K": K, "mandate": md}
                key = f"{ym}_N{c['N']}_f{f:g}_K{K}_{tight}"
                tasks += [{"key": key, "item": "P4", "kwargs": kw, "formulation": form,
                           "s_obj": s_obj, "mip_gap": c["mip_gap"], "time_limit": c["time_limit"]}
                          for form in FORMS]
    return tasks


def p4_agreement(solves: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, g in solves.groupby("key", sort=True):
        r = {f: g[g["formulation"] == f].iloc[0] for f in FORMS}
        diff = abs(r["bigm"]["V"] - r["perspective"]["V"])
        allow = max(r[f]["B_eff"] - r[f]["V"] for f in FORMS)
        rows.append({"key": key, "V_bigm": r["bigm"]["V"], "V_persp": r["perspective"]["V"],
                     "abs_diff": diff, "allowed": allow,
                     "rel_diff": diff / abs(r["bigm"]["V"]) if np.isfinite(diff) else np.nan,
                     "gap_eff_bigm": r["bigm"]["gap_eff"], "gap_eff_persp": r["perspective"]["gap_eff"],
                     "status_bigm": r["bigm"]["status"], "status_persp": r["perspective"]["status"],
                     "pass": bool(np.isfinite(diff) and np.isfinite(allow) and diff <= allow)})
    return pd.DataFrame(rows)


# ----- P5 -----

def round_sig(x: float, n: int = 2) -> float:
    return float(f"{x:.{n - 1}e}")


def p5_summary(solves: pd.DataFrame, ref_seconds: float, workers: int) -> dict:
    rate = solves["work"] / solves["runtime"]
    return {"gurobi_version": ".".join(map(str, gp.gurobi.version())),
            "work_recorded_every_solve": bool(np.isfinite(solves["work"]).all()),
            "work_per_second_median": float(rate.median()),
            "work_per_second_min": float(rate.min()), "work_per_second_max": float(rate.max()),
            "n_solves": len(solves), "concurrent_solves": workers,
            "reference_seconds": ref_seconds, "W_star": round_sig(float(rate.median()) * ref_seconds)}


def worklimit_probe(task: dict, limit: float) -> dict:
    """A P4 instance under a tiny WorkLimit: Gurobi 13 must stop with status WORK_LIMIT."""
    kw = task["kwargs"]
    r = PMI(**kw, formulation=task["formulation"], s_obj=task["s_obj"]).solve(
        mip_gap=task["mip_gap"], work_limit=limit)
    return {"instance": task["key"], "work_limit": limit, "status": r.status_name, "work": r.work,
            "stopped_by_work_limit": r.status_name == "WORK_LIMIT"}


# ----- P6 -----

def _key_bounds(key: str, value: float) -> list[tuple]:
    """(family, value, index) settings for a constraint key at bound `value` on a P-MI model."""
    fam, _, tail = key.partition(":")
    if fam == "style" and tail:
        return [("style", value, STYLE_NAMES.index(tail))]
    if fam in ("dollar", "beta", "gross", "style", "sector") and not tail:
        return [(fam, value, None)]
    raise KeyError(key)


def p6_candidates(p2: pd.DataFrame, cfg, base) -> pd.DataFrame:
    c = cfg["p6"]
    sel = p2[(p2["alpha"] == "mom") & p2["month"].isin(cfg["i1"]["dates"])]
    keys = [k[2:] for k in sel.columns if k.startswith("e_")]
    keys = [k for k in keys if k.split(":")[0] not in EXCLUDED and not k.startswith("sector:")]
    med = {k: float(sel[f"e_{k}"].median()) for k in keys}
    top = sorted(med, key=lambda k: (-med[k], k))[:c["n_families"]]
    rows = []
    for rank, k in enumerate(top):
        fam = k.split(":")[0]
        rows.append({"candidate": k, "rank": rank, "median_elasticity_c1": med[k],
                     "b": float(base.style if fam == "style" else getattr(base, fam)),
                     "is_factor": fam in ("beta", "style"), "source": "top median C1 elasticity"})
    rows.append({"candidate": "style:Mom", "rank": len(top), "b": float(c["mom_bound"]),
                 "median_elasticity_c1": med.get("style:Mom", np.nan), "is_factor": True,
                 "source": f"Mom bound at {c['mom_bound']:g} (DESIGN §8 P6)"})
    return pd.DataFrame(rows)


def p6_tasks(cands: pd.DataFrame, inst, s_obj: float, W: float, cfg) -> list[dict]:
    c = cfg["p6"]
    K = max(1, round_half_up(c["f"] * inst.S_support))
    kw = {**inst.kwargs, "K": K}
    tasks = []
    for r in cands.itertuples():
        delta = c["rel_delta"] * r.b
        for sg, tag in ((+1, "plus"), (-1, "minus")):
            tasks.append({"key": f"{r.rank}_{r.candidate.replace(':', '-')}_b{r.b:g}_{tag}",
                          "item": "P6", "kwargs": kw, "formulation": "perspective",
                          "s_obj": s_obj, "mip_gap": c["mip_gap"],
                          "work_limit": c["work_limit_factor"] * W,
                          "bounds": _key_bounds(r.candidate, r.b + sg * delta),
                          "candidate": r.candidate, "b": r.b, "delta": delta, "sign": sg})
    return tasks


def p6_intervals(solves: pd.DataFrame, cands: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in cands.itertuples():
        g = solves[(solves["candidate"] == r.candidate) & (solves["b"] == r.b)]
        p, m = g[g["sign"] == 1].iloc[0], g[g["sign"] == -1].iloc[0]
        dl = float(p["delta"])
        ce = certified_interval_eff(p["V"], p["B"], m["V"], m["B"], dl)
        ci = certified_interval(p["V"], p["B"], m["V"], m["B"], dl)
        rows.append({"candidate": r.candidate, "rank": r.rank, "b": r.b, "delta": dl,
                     "is_factor": r.is_factor, "median_elasticity_c1": r.median_elasticity_c1,
                     "V_plus": p["V"], "B_plus": p["B"], "V_minus": m["V"], "B_minus": m["B"],
                     "status_plus": p["status"], "status_minus": m["status"],
                     "L": ce.L, "H": ce.H, "s": ce.s, "L_raw": ci.L, "H_raw": ci.H,
                     "binding": bool(ce.L > 0), "solver_error": bool(ce.solver_error),
                     "elasticity_mi": ce.s * r.b / abs(p["V"]) if np.isfinite(ce.s) else np.nan})
    return pd.DataFrame(rows)


def p6_select(iv: pd.DataFrame, max_keep: int) -> tuple[list[str], str]:
    """Keep L > 0 in candidate order, at most max_keep, with a factor bound included if any
    factor bound has L > 0 (the highest-ranked one replaces the last kept non-factor)."""
    ok = iv[iv["binding"]].sort_values("rank")
    keep = list(ok["candidate"][:max_keep])
    note = "kept in candidate order"
    factors = list(ok[ok["is_factor"]]["candidate"])
    if factors and not any(k in factors for k in keep):
        keep[-1] = factors[0]
        note = f"{factors[0]} replaces the last kept candidate (a factor bound must be included)"
    return keep, note


# ----- P7 -----

def p7_projection(p4: pd.DataFrame, p6: pd.DataFrame, p5: dict, n_i1: int, cfg) -> pd.DataFrame:
    """Expected (median Work per solve) and worst-case (every solve at its WorkLimit) Work and
    wall time at `workers` concurrent solves, per S3 experiment (DESIGN §7)."""
    W, rate, wk = p5["W_star"], p5["work_per_second_median"], cfg["workers"]
    w4 = float(p4["work"].clip(upper=W).median())          # MIPGap 1e-4 (N1, N2), capped at W*
    w6 = float(p6["work"].clip(upper=2 * W).median()) if len(p6) else w4   # MIPGap 1e-6 (I1, I2)
    nf, nd = len(cfg["i1"]["f"]), len(cfg["i1"]["dates"])
    exps = [
        ("I1", nd * nf * (2 * n_i1 + 1) + nf * 2 * n_i1, w6, 2 * W,
         "3 dates × 3 f × (2 per constraint + 1 at b) + 5% robustness at 2017-12"),
        ("I2", 2 * 41, w6, 2 * W, "2 instances × 41 points (P-MI; the continuous baseline is cheap)"),
        ("N1", 72 + 24, w4, W, "72 solves + 24 presolve-off (Work measured at N = 250 only)"),
        ("N2a", 4 * 2 * 2, w4, W, "4 instances × 2 formulations × 2 objective scales"),
    ]
    rows = []
    for name, n, w_med, w_cap, note in exps:
        rows.append({"experiment": name, "n_miqp_solves": n, "work_per_solve_expected": w_med,
                     "work_limit_per_solve": w_cap, "work_expected": n * w_med,
                     "work_worst": n * w_cap,
                     "hours_expected_at_workers": n * w_med / rate / wk / 3600,
                     "hours_worst_at_workers": n * w_cap / rate / wk / 3600,
                     "workers": wk, "note": note})
    return pd.DataFrame(rows)


def _q(x: pd.Series) -> dict:
    x = x.dropna()
    q = x.quantile([0.0, 0.5, 1.0]) if len(x) else pd.Series(dtype=float)
    return {"n": len(x), **{f"q{int(100 * k)}": float(v) for k, v in q.items()}}


def main() -> int:
    run = None
    try:
        cfg = config("pilot")
        base, _ = load_config(cfg["mandate_config"])
        run, _ = open_run("pilot", CONFIG, status="pilot")
        wk = int(cfg["workers"])

        if not chunk_path(run, "p1", "all").exists():
            rows, duals = [], []
            for ym in cfg["d12"]:
                r, du = p1_row(ym, base, cfg["p1_tol"])
                rows.append(r)
                duals += du
                print(f"P1 {ym}: A {r['A_rel']:.1e} λ {r['lam_rel']:.1e} duals "
                      f"{r['max_binding_dual_rel']:.1e} solves {r['root_solves']}", flush=True)
            write_chunk(chunk_path(run, "p1_duals", "all"), pd.DataFrame(duals))
            write_chunk(chunk_path(run, "p1", "all"), pd.DataFrame(rows))
        p1, p1d = combine(run, "p1"), combine(run, "p1_duals")

        if not chunk_path(run, "p2", "all").exists():
            write_chunk(chunk_path(run, "p2", "all"),
                        pd.DataFrame([r for ym in cfg["d12"] for r in p2_rows(ym, base)]))
        p2 = combine(run, "p2")
        print("P2 done", flush=True)

        insts = p3_instances(cfg)
        if not chunk_path(run, "p3", "all").exists():
            write_chunk(chunk_path(run, "p3", "all"), pd.DataFrame(p3_rows(cfg, insts)))
        p3 = combine(run, "p3")
        sinfo = choose_s_obj_centred(p3["U_mv"], tuple(cfg["s_obj_window"]))
        s_obj = sinfo["s_obj"]
        print(f"P3 done; s_obj = {s_obj:g}", flush=True)

        t4 = p4_tasks(cfg, insts, s_obj)
        p4, p4w = run_tasks(run, "p4", t4, wk)
        agree = p4_agreement(p4)

        p5 = p5_summary(p4, cfg["p5"]["reference_seconds"], wk)
        probe = worklimit_probe(t4[1], cfg["p5"]["probe_work_limit"])

        cands = p6_candidates(p2, cfg, base)
        inst6 = insts[(cfg["p6"]["date"], str(cfg["p6"]["N"]))]
        p6, p6w = run_tasks(run, "p6", p6_tasks(cands, inst6, s_obj, p5["W_star"], cfg), wk)
        iv = p6_intervals(p6, cands)
        keep, keep_note = p6_select(iv, cfg["p6"]["max_keep"])

        p7 = p7_projection(p4, p6, p5, len(keep), cfg)

        persp = p4[p4["formulation"] == "perspective"]
        summary = {
            "P1": {"pass": bool(p1["pass"].all()), "n_dates": len(p1),
                   "max_A_rel": float(p1["A_rel"].max()), "max_lam_rel": float(p1["lam_rel"].max()),
                   "max_binding_dual_rel": float(p1["max_binding_dual_rel"].max()),
                   "root_solves": _q(p1["root_solves"].astype(float)),
                   "root_time_s": _q(p1["root_time_s"]),
                   "qcqp_almost_solved": int((p1["qcqp_status"] == "optimal_inaccurate").sum()),
                   "s_obj": sinfo},
            "P2": {"n": len(p2), "n_not_binding": int((~p2["risk_binding"]).sum()),
                   "exceptions": p2.loc[~p2["risk_binding"], ["date", "alpha", "vol_ann"]].to_dict("records")},
            "P3": p3.to_dict("records"),
            "P4": {"pass": bool(agree["pass"].all()), "n_instances": len(agree),
                   "n_pass": int(agree["pass"].sum()), "agreement": agree.to_dict("records"),
                   "statuses": {str(k): int(v) for k, v in p4["status"].value_counts().items()},
                   "scaled_abs_V": _q(p4["scaled_abs_V"]),
                   "all_V_scaled_inside_window": bool(p4["scaled_abs_V"].between(*cfg["s_obj_window"]).all()),
                   "n_violations": int((p4["violations"] != "{}").sum()),
                   "n_violations_1e9": int((p4["violations_1e9"] != "{}").sum()),
                   "n_flag_incumbent": int(p4["flag_incumbent_exceeds_polished"].sum()),
                   "n_flag_bound": int(p4["flag_polished_exceeds_bound"].sum()),
                   "A9": {"B_minus_V_rel": _q(p4["B_minus_V_rel"]),
                          "incumbent_minus_V_rel": _q(p4["incumbent_minus_V_rel"]),
                          "cone_effect_rel_perspective": _q(persp["cone_effect_rel"]),
                          "cone_n_capped_total": int(persp["cone_n_capped"].clip(lower=0).sum())}},
            "P5": {**p5, "work_limit_probe": probe},
            "P6": {"candidates": cands.to_dict("records"), "intervals": iv.to_dict("records"),
                   "n_violations": int((p6["violations"] != "{}").sum()),
                   "n_violations_1e9": int((p6["violations_1e9"] != "{}").sum()),
                   "selected": keep, "selection_note": keep_note,
                   "statuses": {str(k): int(v) for k, v in p6["status"].value_counts().items()}},
            "P7": p7.to_dict("records"),
        }
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        frames = {"p1": p1, "p1_duals": p1d, "p2": p2, "p3": p3, "p4_solves": p4,
                  "p4_agreement": agree, "p4_weights": p4w, "p6_candidates": cands,
                  "p6_solves": p6, "p6_intervals": iv, "p6_weights": p6w, "p7": p7}
        finish(run, CONFIG, frames, f"pilot: P1 {'pass' if summary['P1']['pass'] else 'FAIL'}; "
               f"P4 {'pass' if summary['P4']['pass'] else 'FAIL'} ({summary['P4']['n_pass']}/"
               f"{len(agree)}); s_obj {s_obj:g}; W* {p5['W_star']:g}; I1 constraints {keep}")
        print(json.dumps({k: summary[k] for k in ("P1", "P2")}, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
