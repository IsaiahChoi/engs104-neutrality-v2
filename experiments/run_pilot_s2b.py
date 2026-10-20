"""S2b pilot reruns (Isaiah's GATE C note, 2026-10-19): `make pilot_s2b` →
results/pilot_s2b/run_<UTC>/ (RUN_LOG status "pilot"). Pilot numbers only: no DESIGN §7 result,
and a criterion that fails is recorded, not a stop.

Every P-MI solve here polishes at 1e-9 (Decision 24, src.opt.integer.POLISH_PARAMS) and records
the independent checker's 1e-9 verdict on V's weights; every perspective solve records the cones'
violation effect λ*·Σ_i d_i·max(0, w_i²/ζ_i − s_i) at Gurobi's raw incumbent, absolute and
relative to |V|. s_obj and W* are the S2 pilot's (checked against its summary.json).

- P4, three arms: big-M; perspective at default scaling; perspective with weights rescaled by the
  largest position bound (Decision 27(a)). The 8 DESIGN §8 instances (2017-12, 2020-03 × f ∈
  {0.25, 0.5} × {base, tight}, N = 250), MIPGap 1e-4, WorkLimit W*, Threads 1, Seed 0. Per solve:
  status, polished V, B, B − V, the gap against the exact V ((B − V)/|V|, V the polished value),
  Gurobi's own gap against its raw incumbent, the best known value V_best (the largest polished
  V over the arms), the shortfall (V_best − V)/|V_best| and (B − V_best)/|V_best|, the cone
  effect, Work, nodes. The DESIGN §8 agreement criterion |V_bigM − V_arm| ≤ max over the two of
  B_eff − V, for each perspective arm against big-M.
- P6 under combined certification (Decision 27(b): big-M and perspective at default scaling;
  V = the larger polished value, B = the smaller final bound, B_eff = max(B, V) + 1e-6·|V|),
  with the S2 candidate rule (constraint keys ranked by median α_mom elasticity over the I1
  dates; position, liquidity and single sectors excluded; the top 4) and every candidate tied
  at the cutoff included (Decision 28), plus the Mom bound at 0.025. Certified central
  differences at f = 0.5 on 2017-12, N = 250, δ = 10% of the bound, MIPGap 1e-6, WorkLimit 2·W*.
  Selection: L > 0 in candidate order, at most 4, a factor bound included if any factor bound
  has L > 0 (run_pilot.p6_select, on labels key@b). The perspective-only and big-M-only
  intervals from the same solves are recorded alongside, with the fixed-integer dual at V's
  incumbent and who supplied V and B at each point.
- Decision 26 reporting: for every C1 envelope point (K15; the stored C1 run), the exact active
  set of the P-RB QP (src.opt.sensitivity.active_set, rows tight within 1e-9) at b − δ, b and
  b + δ, δ the coarse 1% step; a flagged point is a kink if the set differs, else a curvature
  flag. Unflagged points are classified too. The stored A(b) and A(b ± δ) are compared with the
  recomputed ones as a provenance check.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace

import numpy as np
import pandas as pd

from experiments.common import file_sha256, finish, fail, open_run
from experiments.cont import case, pool_chunks, problem
from experiments.designs import config, month_end
from experiments.instances import pmi_instance, round_half_up
from experiments.run_pilot import EXCLUDED, _key_bounds, _q, p2_rows, p6_select
from src.opt.certified import certified_interval, certified_interval_eff, effective_bound
from src.opt.continuous import load_config
from src.opt.integer import FORMULATIONS, PMI, solve_combined
from src.opt.risk_budget import solve_risk_budget
from src.opt.sensitivity import (ACTIVE_TOL, active_set, active_set_change, restore,
                                 set_bound_by_key, snapshot)
from src.utils import ROOT

CONFIG = "experiments/configs/pilot_s2b.yaml"
PERSPECTIVE_ARMS = ("perspective", "perspective_rescaled")


def check_s2_pilot(cfg: dict) -> dict:
    """s_obj and W* in the config must be the S2 pilot's (its summary.json)."""
    path = ROOT / cfg["s2_pilot_run"] / "summary.json"
    s = json.loads(path.read_text())
    got = {"s_obj": float(s["P1"]["s_obj"]["s_obj"]), "W_star": float(s["P5"]["W_star"])}
    want = {"s_obj": float(cfg["s_obj"]), "W_star": float(cfg["W_star"])}
    if got != want:
        raise ValueError(f"pilot_s2b.yaml {want} != the S2 pilot's {got} ({path})")
    return {"s2_pilot_summary": str(path.relative_to(ROOT)), "sha256": file_sha256(path), **got}


# ----- one P-MI solve record -----

def _rec(r, extra: dict) -> dict:
    rel = (lambda x: x / abs(r.V)) if np.isfinite(r.V) and r.V != 0 else (lambda x: np.nan)
    Beff = effective_bound(r.B, r.V) if np.isfinite(r.V) and np.isfinite(r.B) else np.nan
    return {**extra, "formulation": r.formulation, "rescale": bool(r.settings["rescale"]),
            "w_scale": r.w_scale, "status": r.status_name, "reached_gap": r.reached_gap,
            "v_source": r.v_source, "polish_status": r.polish_status, "V": r.V, "B": r.B,
            "B_eff": Beff, "gap_eff": rel(Beff - r.V), "B_minus_V": r.B_minus_V,
            "B_minus_V_rel": rel(r.B_minus_V),
            "gurobi_gap": (r.B - r.U_raw) / abs(r.U_raw) if np.isfinite(r.U_raw) and r.U_raw else np.nan,
            "U_raw": r.U_raw, "U_incumbent": r.U_incumbent,
            "incumbent_minus_V_rel": rel(r.incumbent_minus_V), "root_bound": r.root_bound,
            "cone_effect": r.cone_effect, "cone_effect_rel": r.cone_effect_rel,
            "cone_n_capped": r.cone_n_capped, "polished_violations": r.polished_violations,
            "flag_incumbent_exceeds_polished": r.flag_incumbent_exceeds_polished,
            "flag_polished_exceeds_bound": r.flag_polished_exceeds_bound,
            "work": r.work, "runtime": r.runtime, "nodes": r.nodes,
            "n_held": int(np.nansum(r.zp + r.zm)), "scaled_abs_V": abs(r.V) * r.s_obj,
            "settings": json.dumps(r.settings, sort_keys=True, default=str)}


# ----- P4 -----

def p4_tasks(cfg: dict, insts: dict) -> list[dict]:
    c, W = cfg["p4"], float(cfg["W_star"])
    tasks = []
    for ym in c["dates"]:
        inst = insts[ym]
        for f in c["f"]:
            K = max(1, round_half_up(f * inst.S_support))
            for tight in c["tightness"]:
                md = inst.mandate if tight == "base" else replace(inst.mandate, **cfg["n1_tight"])
                key = f"{ym}_N{c['N']}_f{f:g}_K{K}_{tight}"
                for a in c["arms"]:
                    tasks.append({"key": key, "arm": a["arm"], "formulation": a["formulation"],
                                  "rescale": bool(a["rescale"]), "s_obj": float(cfg["s_obj"]),
                                  "kwargs": {**inst.kwargs, "K": K, "mandate": md},
                                  "mip_gap": c["mip_gap"], "work_limit": c["work_limit_factor"] * W,
                                  "K": K, "N": inst.N, "lam_star": inst.lam})
    return tasks


def p4_solve(task: dict) -> dict[str, pd.DataFrame]:
    M = PMI(**task["kwargs"], formulation=task["formulation"], s_obj=task["s_obj"],
            rescale=task["rescale"])
    r = M.solve(mip_gap=task["mip_gap"], work_limit=task["work_limit"], cone_diag=True)
    rec = _rec(r, {k: task[k] for k in ("key", "arm", "mip_gap", "work_limit", "K", "N", "lam_star")})
    w = pd.DataFrame({"key": task["key"], "arm": task["arm"], "i": np.arange(len(r.w)), "w": r.w,
                      "zp": r.zp, "zm": r.zm, "w_incumbent": r.w_incumbent})
    return {"p4": pd.DataFrame([rec]), "p4_w": w}


def p4_add_best(solves: pd.DataFrame) -> pd.DataFrame:
    """V_best = the largest polished V over the arms of an instance; the shortfall
    (V_best − V)/|V_best|; the gap against the exact V, (B − V)/|V|; and (B − V_best)/|V_best|."""
    s = solves.copy()
    s["V_best"] = s.groupby("key")["V"].transform("max")
    s["shortfall_rel"] = (s["V_best"] - s["V"]) / s["V_best"].abs()
    s["gap_own_rel"] = (s["B"] - s["V"]) / s["V"].abs()
    s["gap_vs_best_rel"] = (s["B"] - s["V_best"]) / s["V_best"].abs()
    return s


def p4_arm_agreement(solves: pd.DataFrame, arms=PERSPECTIVE_ARMS) -> pd.DataFrame:
    """DESIGN §8 P4 for each arm against big-M: |V_bigM − V_arm| ≤ max over the two of B_eff − V."""
    rows = []
    for key, g in solves.groupby("key", sort=True):
        g = g.set_index("arm")
        b = g.loc["bigm"]
        for arm in arms:
            a = g.loc[arm]
            diff = abs(b["V"] - a["V"])
            allow = max(b["B_eff"] - b["V"], a["B_eff"] - a["V"])
            ok = bool(np.isfinite(diff) and np.isfinite(allow) and diff <= allow)
            rows.append({"key": key, "arm": arm, "V_bigm": b["V"], "V_arm": a["V"],
                         "abs_diff": diff, "allowed": allow,
                         "rel_diff": diff / abs(b["V"]) if np.isfinite(diff) else np.nan,
                         "ratio": diff / allow if np.isfinite(allow) and allow > 0 else np.nan,
                         "pass": ok})
    return pd.DataFrame(rows)


# ----- P6 -----

def p6_candidates_ties(p2: pd.DataFrame, cfg: dict, base) -> pd.DataFrame:
    """The S2 rule (run_pilot.p6_candidates) with every key tied at the cutoff included
    (Decision 28): keys ranked by (−median elasticity, key); every key whose median is at least
    the n-th largest; then the Mom bound at mom_bound."""
    c = cfg["p6"]
    sel = p2[(p2["alpha"] == "mom") & p2["month"].isin(cfg["i1"]["dates"])]
    keys = [k[2:] for k in sel.columns if k.startswith("e_")]
    keys = [k for k in keys if k.split(":")[0] not in EXCLUDED and not k.startswith("sector:")]
    med = {k: float(sel[f"e_{k}"].median()) for k in keys}
    order = sorted(med, key=lambda k: (-med[k], k))
    cutoff = med[order[int(c["n_families"]) - 1]]
    top = [k for k in order if med[k] >= cutoff]
    extended = len(top) > int(c["n_families"])
    rows = []
    for rank, k in enumerate(top):
        fam = k.split(":")[0]
        tied = bool(extended and med[k] == cutoff)
        rows.append({"candidate": k, "rank": rank, "median_elasticity_c1": med[k],
                     "b": float(base.style if fam == "style" else getattr(base, fam)),
                     "is_factor": fam in ("beta", "style"), "tied_at_cutoff": tied,
                     "source": "top median C1 elasticity" + (" (tied at the cutoff)" if tied else "")})
    rows.append({"candidate": "style:Mom", "rank": len(top), "b": float(c["mom_bound"]),
                 "median_elasticity_c1": med.get("style:Mom", np.nan), "is_factor": True,
                 "tied_at_cutoff": False,
                 "source": f"Mom bound at {c['mom_bound']:g} (DESIGN §8 P6)"})
    return pd.DataFrame(rows)


def p6_tasks(cands: pd.DataFrame, inst, cfg: dict) -> list[dict]:
    c = cfg["p6"]
    K = max(1, round_half_up(c["f"] * inst.S_support))
    tasks = []
    for r in cands.itertuples():
        delta = c["rel_delta"] * r.b
        for sg, tag in ((+1, "plus"), (-1, "minus")):
            tasks.append({"key": f"{r.rank:02d}_{r.candidate.replace(':', '-')}_b{r.b:g}_{tag}",
                          "kwargs": {**inst.kwargs, "K": K}, "s_obj": float(cfg["s_obj"]),
                          "mip_gap": c["mip_gap"],
                          "work_limit": c["work_limit_factor"] * float(cfg["W_star"]),
                          "rescale_perspective": bool(c["rescale_perspective"]),
                          "bounds": _key_bounds(r.candidate, r.b + sg * delta),
                          "candidate": r.candidate, "rank": r.rank, "b": r.b, "delta": delta,
                          "sign": sg, "K": K})
    return tasks


def p6_solve(task: dict) -> dict[str, pd.DataFrame]:
    """One stencil point under combined certification (src.opt.integer.solve_combined)."""
    P = PMI(**task["kwargs"], formulation="bigm", s_obj=task["s_obj"])
    for fam, value, index in task["bounds"]:
        P.set_bound(fam, value, index)
    c = solve_combined(P, mip_gap=task["mip_gap"], work_limit=task["work_limit"],
                       rescale_perspective=task["rescale_perspective"], cone_diag=True)
    ids = {k: task[k] for k in ("key", "candidate", "rank", "b", "delta", "sign", "K")}
    fx = c.fixed_duals or {}
    pt = {**ids, "V": c.V, "B": c.B, "B_eff": c.B_eff, "v_from": c.v_from, "b_from": c.b_from,
          "v_tie": c.v_tie, "b_tie": c.b_tie, "certified_gap_rel": c.certified_gap / abs(c.V),
          "mu_fixed": fx.get("shadow", {}).get(task["candidate"], np.nan),
          "fixed_status": fx.get("status", "not run"),
          "work_total": sum(p.work for p in c.parts.values()),
          "n_held": int(np.nansum(c.zp + c.zm))}
    for f, r in c.parts.items():
        pt.update({f"V_{f}": r.V, f"B_{f}": r.B, f"status_{f}": r.status_name})
    solves = pd.DataFrame([_rec(r, {**ids, "arm": f}) for f, r in c.parts.items()])
    w = pd.DataFrame({"key": task["key"], "i": np.arange(len(c.w)), "w": c.w, "zp": c.zp,
                      "zm": c.zm, "v_from": c.v_from})
    return {"p6_points": pd.DataFrame([pt]), "p6_solves": solves, "p6_w": w}


def p6_intervals_combined(points: pd.DataFrame, cands: pd.DataFrame) -> pd.DataFrame:
    """Per candidate: the combined certified interval (B_eff at both points), the raw-B one, and
    the perspective-only and big-M-only intervals from the same solves."""
    rows = []
    for r in cands.itertuples():
        g = points[(points["candidate"] == r.candidate) & (points["b"] == r.b)]
        p, m = g[g["sign"] == 1].iloc[0], g[g["sign"] == -1].iloc[0]
        dl = float(p["delta"])
        ce = certified_interval_eff(p["V"], p["B"], m["V"], m["B"], dl)
        ci = certified_interval(p["V"], p["B"], m["V"], m["B"], dl)
        row = {"candidate": r.candidate, "rank": r.rank, "b": r.b, "delta": dl,
               "is_factor": r.is_factor, "tied_at_cutoff": r.tied_at_cutoff,
               "median_elasticity_c1": r.median_elasticity_c1,
               "V_plus": p["V"], "B_plus": p["B"], "V_minus": m["V"], "B_minus": m["B"],
               "v_from_plus": p["v_from"], "v_from_minus": m["v_from"],
               "b_from_plus": p["b_from"], "b_from_minus": m["b_from"],
               "L": ce.L, "H": ce.H, "s": ce.s, "L_raw": ci.L, "H_raw": ci.H,
               "binding": bool(ce.L > 0), "solver_error": bool(ce.solver_error),
               "elasticity_mi": ce.s * r.b / abs(p["V"]) if np.isfinite(ce.s) else np.nan}
        for f in FORMULATIONS:
            try:
                one = certified_interval_eff(p[f"V_{f}"], p[f"B_{f}"], m[f"V_{f}"], m[f"B_{f}"], dl)
                row.update({f"L_{f}_only": one.L, f"H_{f}_only": one.H, f"s_{f}_only": one.s,
                            f"binding_{f}_only": bool(one.L > 0)})
            except ValueError:                      # an undefined V: recorded as missing
                row.update({f"L_{f}_only": np.nan, f"H_{f}_only": np.nan, f"s_{f}_only": np.nan,
                            f"binding_{f}_only": False})
        rows.append(row)
    return pd.DataFrame(rows)


# ----- Decision 26: active sets at the C1 envelope stencils -----

def kinks_for_date(item: tuple[str, list[dict]]) -> dict[str, pd.DataFrame]:
    """Every stored C1 envelope point at one date: the active set at b − δ, b, b + δ, with the
    P-RB built and solved as run_c1 builds it (full universe, base mandate, α_mom)."""
    ds, rows = item
    base, _ = load_config(config("continuous")["mandate_config"])
    di, alpha = case(ds)
    P = problem(di, base)
    rb = solve_risk_budget(P, alpha)
    A0 = active_set(P, rb.sol)
    out = []
    for e in rows:
        snap = snapshot(P)
        sets, vals, flags = {}, {}, {}
        for sg, tag in ((+1, "plus"), (-1, "minus")):
            set_bound_by_key(P, e["key"], e["b"] + sg * e["step"])
            try:
                r = solve_risk_budget(P, alpha, lam_guess=rb.lam)
                sets[tag], vals[tag], flags[tag] = active_set(P, r.sol), r.A, r.risk_binding
            finally:
                restore(P, snap)
        ch = active_set_change(sets["minus"], A0, sets["plus"])
        if e["kink"]:
            cls = "kink" if ch["differs"] else "curvature flag"
        else:
            cls = "unflagged, active set changes" if ch["differs"] else "unflagged"
        out.append({"date": ds, "key": e["key"], "b": e["b"], "step": e["step"], "e": e["e"],
                    "flagged": bool(e["kink"]), "rel_err_coarse": e["rel_err_coarse"],
                    "mu_plus": e["mu_plus"], "mu_minus": e["mu_minus"],
                    "dual_zero_clause": bool(e["mu_plus"] == 0 or e["mu_minus"] == 0),
                    **ch, "classification": cls, "n_active_b": len(A0),
                    "risk_binding_b": rb.risk_binding, "risk_binding_plus": flags["plus"],
                    "risk_binding_minus": flags["minus"],
                    "A_b": rb.A, "A_plus": vals["plus"], "A_minus": vals["minus"],
                    "A_b_stored": e["A"], "A_plus_stored": e["A_plus"],
                    "A_minus_stored": e["A_minus"],
                    "max_abs_diff_vs_stored": float(max(abs(rb.A - e["A"]),
                                                        abs(vals["plus"] - e["A_plus"]),
                                                        abs(vals["minus"] - e["A_minus"])))})
    return {"c1_kinks": pd.DataFrame(out)}


def _dist(x: pd.Series) -> dict:
    return _q(pd.to_numeric(x, errors="coerce"))


def summarize(p4: pd.DataFrame, agree: pd.DataFrame, cands, iv, points, solves6, keep, keep_note,
              kinks: pd.DataFrame, prov: dict) -> dict:
    fl = kinks[kinks["flagged"]]
    by_arm = {}
    for arm, g in p4.groupby("arm", sort=True):
        by_arm[arm] = {
            "statuses": {str(k): int(v) for k, v in g["status"].value_counts().items()},
            "n_polished": int((g["v_source"] == "polished").sum()),
            "n_violations_1e9": int((g["polished_violations"] != "{}").sum()),
            "n_flag_incumbent": int(g["flag_incumbent_exceeds_polished"].sum()),
            "n_flag_bound": int(g["flag_polished_exceeds_bound"].sum()),
            **{c: _dist(g[c]) for c in ("gap_own_rel", "gurobi_gap", "shortfall_rel",
                                        "gap_vs_best_rel", "cone_effect_rel", "work", "nodes")}}
    return {
        "provenance": prov,
        "P4": {"n_instances": int(p4["key"].nunique()), "n_solves": len(p4), "by_arm": by_arm,
               "agreement": {arm: {"n_pass": int(g["pass"].sum()), "n": len(g),
                                   "max_ratio": float(g["ratio"].max())}
                             for arm, g in agree.groupby("arm", sort=True)}},
        "P6": {"candidates": cands.to_dict("records"), "intervals": iv.to_dict("records"),
               "selected": keep, "selection_note": keep_note,
               "v_from": {str(k): int(v) for k, v in points["v_from"].value_counts().items()},
               "b_from": {str(k): int(v) for k, v in points["b_from"].value_counts().items()},
               "n_v_tie": int(points["v_tie"].sum()),
               "n_violations_1e9": int((solves6["polished_violations"] != "{}").sum()),
               "statuses": {str(k): int(v) for k, v in solves6["status"].value_counts().items()}},
        "kinks": {"n_points": len(kinks), "n_flagged": len(fl),
                  "n_flagged_active_set_changes": int(fl["differs"].sum()),
                  "n_flagged_curvature": int((~fl["differs"]).sum()),
                  "n_unflagged": int((~kinks["flagged"]).sum()),
                  "n_unflagged_active_set_changes": int(kinks.loc[~kinks["flagged"], "differs"].sum()),
                  "n_flagged_by_dual_zero_clause": int(fl["dual_zero_clause"].sum()),
                  "n_flagged_mandate_row_changes": int((fl["mandate_rows_changed"] != "").sum()),
                  "max_abs_diff_vs_stored_A": float(kinks["max_abs_diff_vs_stored"].max())},
    }


def main() -> int:
    run = None
    try:
        cfg = config("pilot_s2b")
        base, _ = load_config(cfg["mandate_config"])
        prov = check_s2_pilot(cfg)
        if float(cfg["kinks"]["active_tol"]) != ACTIVE_TOL:
            raise ValueError(f"kinks.active_tol must be src.opt.sensitivity.ACTIVE_TOL ({ACTIVE_TOL:g})")
        env_path = ROOT / cfg["kinks"]["c1_run"] / "c1_envelope.parquet"
        prov.update(c1_envelope=str(env_path.relative_to(ROOT)),
                    c1_envelope_sha256=file_sha256(env_path))
        run, _ = open_run("pilot_s2b", CONFIG, status="pilot")
        wk = int(cfg["workers"])

        # Decision 26: active sets at the stored C1 stencils (continuous; cheap)
        env = pd.read_parquet(env_path)
        items = [(ds, g.to_dict("records")) for ds, g in env.groupby("date", sort=True)]
        kinks = pool_chunks(run, ("c1_kinks",), items, lambda it: it[0], kinks_for_date, wk)["c1_kinks"]

        # P4: three arms
        insts = {ym: pmi_instance(month_end(ym), cfg["p4"]["N"], 0.5)
                 for ym in sorted(set(cfg["p4"]["dates"]) | {cfg["p6"]["date"]})}
        f4 = pool_chunks(run, ("p4", "p4_w"), p4_tasks(cfg, insts),
                         lambda t: f"{t['key']}__{t['arm']}", p4_solve, wk)
        p4 = p4_add_best(f4["p4"])
        agree = p4_arm_agreement(p4)

        # P6: combined certification, ties included
        p2 = pd.DataFrame([r for ym in cfg["i1"]["dates"] for r in p2_rows(ym, base)])
        s2p2 = pd.read_parquet(ROOT / cfg["s2_pilot_run"] / "p2.parquet")
        s2p2 = s2p2[s2p2["month"].isin(cfg["i1"]["dates"])].set_index(["month", "alpha"]).sort_index()
        now = p2.set_index(["month", "alpha"]).sort_index()
        ecols = [c for c in now.columns if c.startswith("e_")]
        prov["p2_max_abs_elasticity_diff_vs_s2"] = float(np.nanmax(np.abs(
            now[ecols].to_numpy(float) - s2p2.loc[now.index, ecols].to_numpy(float))))
        cands = p6_candidates_ties(p2, cfg, base)
        f6 = pool_chunks(run, ("p6_points", "p6_solves", "p6_w"),
                         p6_tasks(cands, insts[cfg["p6"]["date"]], cfg), lambda t: t["key"],
                         p6_solve, wk)
        iv = p6_intervals_combined(f6["p6_points"], cands)
        labelled = iv.assign(candidate=iv["candidate"] + "@" + iv["b"].map(lambda b: f"{b:g}"))
        keep, keep_note = p6_select(labelled, cfg["p6"]["max_keep"])

        summary = summarize(p4, agree, cands, iv, f6["p6_points"], f6["p6_solves"], keep,
                            keep_note, kinks, prov)
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        frames = {"c1_kinks": kinks, "p4_solves": p4, "p4_agreement": agree,
                  "p4_weights": f4["p4_w"], "p2_i1": p2, "p6_candidates": cands,
                  "p6_points": f6["p6_points"], "p6_solves": f6["p6_solves"],
                  "p6_intervals": iv, "p6_weights": f6["p6_w"]}
        ag, kk = summary["P4"]["agreement"], summary["kinks"]
        finish(run, CONFIG, frames,
               "pilot_s2b: P4 agreement " + "; ".join(f"{a} {v['n_pass']}/{v['n']}" for a, v in ag.items())
               + f"; P6 combined selection {keep}; {kk['n_flagged_active_set_changes']} of "
               f"{kk['n_flagged']} flagged C1 points change the active set",
               extra_files=[run / "summary.json"])
        print(json.dumps({k: summary[k] for k in ("P4", "kinks")}, indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
