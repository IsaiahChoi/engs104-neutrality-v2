"""S2d pilot (gate-independent hardening before GATE DESIGN): `make pilot_s2d` →
results/pilot_s2d/run_<UTC>/ (RUN_LOG status "pilot"). Diagnostics only: no I1, I2, N1 or N2
result is produced, and nothing here chooses an I1 constraint (Decision 31).

- Item 1, the N1 root-gap contradiction, on the 8 P4 instances of the S2b run (results/pilot_s2b/
  run_20261020T024318Z; its hashes are checked). Stored: each arm's recorded root bound (the last
  root cut pass, src.opt.miqp), polished V, B and cone effect. Solved here, because the stored data
  hold no plain relaxation: the z ∈ [0, 1] relaxations (big-M by dual simplex; the perspective by
  Clarabel, valued with the cones exact, DESIGN §6; Gurobi's barrier on it beside), and root-only
  Gurobi probes (src.opt.rootprobe: NodeLimit 1, the S2b P4 settings, WorkLimit W*) recording the
  bound at every root cut pass: big-M; the perspective at default scaling, with FeasibilityTol
  1e-9, MIQCPMethod 0 (a QCP relaxation at the node) and 1 (outer approximation), and both; the
  rescaled perspective. rootgap_table measures every bound against V_comb, the larger polished V
  of big-M and the default perspective (combined certification), with the A6 margin of the plain
  relaxations and of the recorded root bounds.
- Item 2, the three-point slope option (src.opt.slopes), measured at s ∈ {1, 1e2, 1e4}: on the K9
  random toy family (seed and size of core.yaml; 41-point grids, b = 0 dropped) against the closed
  forms, with V_ref = the toy's U* (as K9; DESIGN §6). Central slopes are checked away from the
  kinks ℓ and w°; within 2δ_r of a kink each one-sided slope is checked where its stencil stays
  on one piece (toy_classify). Errors are read against max(|closed form|, 1e-4·U*/b). On the K8
  instances (top 30, f = 0.5) the slopes are compared across scales, with the noise term, and
  Clarabel's raw duals at b as a diagnostic.
- Item 3, Clarabel status against scale: the perspective relaxation at base bounds on the nine I1
  (date, f) instances, N = 250, at s ∈ {1, 1e2, 1e4, 1e6}: status, residuals, gap_abs (scaled and
  original units), the pure relative gap, |V_s|, and relative value differences between scales.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

from experiments.common import file_sha256, finish, fail, open_run
from experiments.cont import pool_chunks
from experiments.designs import config, month_end
from experiments.instances import pmi_instance
from experiments.run_pilot_s2b import p4_tasks
from src.opt.continuous import Mandate
from src.opt.integer import PMI
from src.opt.relaxation import perspective_relaxation
from src.opt.rootprobe import plain_relaxations, root_probe
from src.opt.sensitivity import BINDING_ELASTICITY
from src.opt.slopes import fd_slopes, relaxation_slope
from src.opt.toy import Toy, random_toys
from src.risk.factor_model import FACTORS
from src.utils import ROOT

CONFIG = "experiments/configs/pilot_s2d.yaml"
A6_ATOL = 1e-8                       # K24's slack, ·|V|


def check_s2b(cfg: dict) -> dict:
    """s_obj and W* must be the S2b run's, and its stored outputs must match its outputs.json."""
    run = ROOT / cfg["s2b_run"]
    meta = json.loads((run / "run_meta.json").read_text())
    got = {"s_obj": float(meta["config"]["s_obj"]), "W_star": float(meta["config"]["W_star"])}
    want = {"s_obj": float(cfg["s_obj"]), "W_star": float(cfg["W_star"])}
    if got != want:
        raise ValueError(f"pilot_s2d.yaml {want} != the S2b run's {got}")
    hashes = json.loads((run / "outputs.json").read_text())
    ok = all(file_sha256(run / f) == h for f, h in hashes.items())
    if not ok:
        raise ValueError(f"stored outputs of {run} do not match its outputs.json")
    return {**got, "s2b_run": cfg["s2b_run"], "s2b_commit": meta["git_commit"], "hashes_match": ok,
            "s2b_config": meta["config"]}


# ----- item 1 -----

def rootgap_task(task: dict) -> dict[str, pd.DataFrame]:
    """One P4 instance: the plain relaxations and the root probes (module docstring)."""
    P = PMI(**task["kwargs"], formulation="bigm", s_obj=task["s_obj"])
    plain = {"key": task["key"], **plain_relaxations(P)}
    rows = []
    for pr in task["probes"]:
        Pf = P.sibling(pr["formulation"])
        out = root_probe(Pf.model, rescale=pr["rescale"], mip_gap=task["mip_gap"],
                         work_limit=task["work_limit"], params=pr["params"])
        s = P.s_obj
        rows.append({"key": task["key"], "probe": pr["probe"], "formulation": pr["formulation"],
                     "rescale": pr["rescale"], "params": json.dumps(pr["params"], sort_keys=True),
                     "first": out["first"] / s, "last": out["last"] / s,
                     "final_bound": out["final_bound"] / s, "n_passes": out["n_passes"],
                     "passes": json.dumps([p / s for p in out["passes"]]), "status": out["status"],
                     "work": out["work"], "runtime": out["runtime"], "nodes": out["nodes"],
                     "settings": json.dumps(out["settings"], sort_keys=True, default=str)})
    return {"rootgap_plain": pd.DataFrame([plain]), "rootgap_probes": pd.DataFrame(rows)}


def rootgap_table(stored: pd.DataFrame, plain: pd.DataFrame, probes: pd.DataFrame) -> pd.DataFrame:
    """Per instance: every bound's gap (bound − V_comb)/|V_comb| (module docstring); the A6 margins
    (big-M − perspective)/|V_comb| of the plain relaxations and of the recorded root bounds; big-M's
    root-cut tightening (plain − last pass)/|V|; the perspective's first pass above its plain
    relaxation; and the default probes' last pass against the stored root bound."""
    rows = []
    for key, g in stored.groupby("key", sort=True):
        g = g.set_index("arm")
        V = float(max(g.loc["bigm", "V"], g.loc["perspective", "V"]))
        rel = lambda x: (float(x) - V) / abs(V)
        pl = plain.set_index("key").loc[key]
        pb = probes[probes["key"] == key].set_index("probe")
        row = {"key": key, "V_comb": V, "V_best3": float(g["V"].max())}
        for arm in g.index:
            row[f"gap_root_stored_{arm}"] = rel(g.loc[arm, "root_bound"])
            row[f"gap_final_stored_{arm}"] = rel(g.loc[arm, "B"])
            row[f"cone_effect_rel_{arm}"] = float(g.loc[arm, "cone_effect_rel"])
        row["gap_plain_bigm"] = rel(pl["bigm"])
        row["gap_plain_perspective"] = rel(pl["perspective"])
        row["gap_plain_perspective_gurobi_barrier"] = rel(pl["perspective_gurobi_barrier"])
        row["a6_margin_plain"] = (float(pl["bigm"]) - float(pl["perspective"])) / abs(V)
        row["a6_holds_plain"] = bool(pl["perspective"] <= pl["bigm"] + A6_ATOL * abs(V))
        rb, rp = g.loc["bigm", "root_bound"], g.loc["perspective", "root_bound"]
        row["a6_margin_root_stored"] = (float(rb) - float(rp)) / abs(V)
        row["a6_holds_root_stored"] = bool(rp <= rb + A6_ATOL * abs(V))
        for p in pb.index:
            row[f"gap_probe_first_{p}"] = rel(pb.loc[p, "first"])
            row[f"gap_probe_last_{p}"] = rel(pb.loc[p, "last"])
            if p in g.index:
                row[f"probe_last_vs_stored_{p}"] = (float(pb.loc[p, "last"])
                                                    - float(g.loc[p, "root_bound"])) / abs(V)
        if "bigm" in pb.index:
            row["cut_tightening_bigm"] = (float(pl["bigm"]) - float(pb.loc["bigm", "last"])) / abs(V)
        for p in pb.index:
            if p.startswith("perspective"):
                row[f"first_minus_plain_{p}"] = (float(pb.loc[p, "first"])
                                                 - float(pl["perspective"])) / abs(V)
        rows.append(row)
    return pd.DataFrame(rows)


# ----- item 2: toys -----

def toy_one_sided(T: Toy, b: float) -> tuple[float, float]:
    """(left, right) derivatives in b of the toy's perspective relaxation value (src.opt.toy)."""
    lin, ld = T.a - T.lam * T.d * T.ell, T.lam * T.d

    def piece(x, left: bool):
        if x < T.ell or (left and x == T.ell):
            return lin
        if x < T.w_opt or (left and x == T.w_opt):
            return T.a - 2 * ld * x
        return 0.0
    return piece(b, True), piece(b, False)


def toy_classify(T: Toy, b: float, delta: float) -> dict:
    """The kink (ℓ or w°) within 2δ of b, if any; whether the forward stencil [b, b + 2δ] and the
    backward one [b − 2δ, b] stay on one piece (no kink strictly inside); interior = no kink within
    2δ (K29c: such points are checked by their one-sided slopes)."""
    kinks = {"ell": T.ell, "w_opt": T.w_opt}
    near = [n for n, k in kinks.items() if abs(b - k) <= 2 * delta]
    return {"near": ",".join(near),
            "fwd_valid": not any(b < k < b + 2 * delta for k in kinks.values()),
            "bwd_valid": not any(b - 2 * delta < k < b for k in kinks.values()),
            "interior": not near}


def toy_pmi(T: Toy, b: float, s: float) -> PMI:
    """The A7 toy as a P-MI (K9's build: one asset, the gross row as the bound b, K = 1) at s_obj = s."""
    m = Mandate(dollar=None, beta=None, style=None, sector=None, gross=b, position=T.u,
                liquidity_theta=None, borrow_annual=0.0, trade_cost=0.0)
    return PMI(np.zeros((1, len(FACTORS))), np.eye(len(FACTORS)) * 1e-4, np.array([T.d]),
               np.ones((1, 1)), np.array([T.a]), T.lam, m, None, K=1, ell=T.ell,
               formulation="perspective", s_obj=s, factor_names=FACTORS)


def _point_fields(rec: dict) -> dict:
    pts = rec["points"]
    num = lambda f: [p[f] for p in pts if p.get(f) is not None and np.isfinite(p[f])]
    return {"statuses": ",".join(str(p["clarabel_status"]) for p in pts),
            "n_almost_solved": rec["n_almost_solved"],
            "max_r_prim": max(num("r_prim"), default=np.nan),
            "max_r_dual": max(num("r_dual"), default=np.nan),
            "max_gap_rel": max(num("gap_rel"), default=np.nan)}


def _central_from(rec: dict, v_ref=None):
    vals = {p["offset"]: p["value"] for p in rec["points"] if p["offset"] in (-1, 0, 1)}
    return fd_slopes(vals, rec["delta"], method="central", v_ref=v_ref)


def toy_point_rows(name: str, T: Toy, b: float, scales, rel_delta: float) -> list[dict]:
    """One toy point at each scale: three-point slopes, the central slope from the same values,
    errors against the closed form where it applies (module docstring)."""
    U = T.value(T.w_opt)
    left, right = toy_one_sided(T, b)
    out = []
    for s in scales:
        rec = relaxation_slope(toy_pmi(T, b, s), "gross", b=b, rel_delta=rel_delta,
                               method="three_point", v_ref=U)
        cls = toy_classify(T, b, rec["delta"])
        row = {"toy": name, "b": b, "s": s, "a": T.a, "ell": T.ell, "w_opt": T.w_opt, "U_star": U,
               "ok": rec["ok"], "fail_reason": rec["fail_reason"], "V": rec["V"],
               "delta": rec["delta"], "cf_left": left, "cf_right": right, **cls,
               **_point_fields(rec)}
        nan = np.nan
        row.update(slope_central=nan, forward3=nan, backward3=nan, fwd2=nan, bwd2=nan,
                   kink3=False, kink2=False, concave3=False, noise3=nan, noise_central=nan,
                   err_central=nan, err_fwd3=nan, err_bwd3=nan, noise3_rel=nan, err_scale=nan)
        if rec["ok"]:
            c = _central_from(rec, v_ref=U)
            scale = max(abs(right), abs(left), BINDING_ELASTICITY * abs(U) / b)
            row.update(slope_central=float(c.slope), forward3=rec["forward"],
                       backward3=rec["backward"], fwd2=float(c.forward), bwd2=float(c.backward),
                       kink3=rec["kink"], kink2=bool(c.kink), concave3=rec["concave"],
                       noise3=rec["noise"], noise_central=float(c.noise_central),
                       err_scale=scale, noise3_rel=rec["noise"] / scale)
            if cls["interior"]:
                row["err_central"] = abs(float(c.slope) - right) / scale
            if cls["fwd_valid"]:
                row["err_fwd3"] = abs(rec["forward"] - right) / scale
            if cls["bwd_valid"]:
                row["err_bwd3"] = abs(rec["backward"] - left) / scale
        out.append(row)
    return out


def toy_task(item: tuple) -> dict[str, pd.DataFrame]:
    name, T, b_max, grid, scales, rel_delta = item
    rows = [x for b in np.linspace(0.0, b_max, grid)[1:]
            for x in toy_point_rows(name, T, float(b), scales, rel_delta)]
    return {"k29c_toys": pd.DataFrame(rows)}


# ----- item 2: K8 instances -----

def k8_task(item: tuple) -> dict[str, pd.DataFrame]:
    ym, c, scales, rel_delta = item
    inst = pmi_instance(month_end(ym), c["N"], c["f"])
    rows = []
    for s in scales:
        P = PMI(**inst.kwargs, formulation="perspective", s_obj=s)
        raw = P.relaxation_duals()["perspective"]
        for key in c["keys"]:
            rec = relaxation_slope(P, key, rel_delta=rel_delta, method="three_point")
            row = {"month": ym, "s": s, "key": key, "b": rec["b"], "ok": rec["ok"],
                   "fail_reason": rec["fail_reason"], "V": rec["V"], "delta": rec["delta"],
                   "forward3": rec["forward"], "backward3": rec["backward"], "kink3": rec["kink"],
                   "concave3": rec["concave"], "noise3": rec["noise"],
                   "raw_dual": raw["shadow"].get(key, np.nan), "raw_dual_status": raw["status"],
                   "raw_dual_ok": raw["ok"], **_point_fields(rec)}
            row.update(slope_central=np.nan, noise_central=np.nan, kink2=False)
            if rec["ok"]:
                cc = _central_from(rec)
                row.update(slope_central=float(cc.slope), noise_central=float(cc.noise_central),
                           kink2=bool(cc.kink))
            rows.append(row)
    return {"k29c_k8": pd.DataFrame(rows)}


def k8_cross_scale(df: pd.DataFrame, ref: float = 1.0) -> pd.DataFrame:
    """Each slope's difference from its s = ref value, relative to max(|slope_ref|, 1e-4·|V|/b)
    (the bindingness scale, as K8's dual ratios), the noise on the same scale, and Clarabel's raw
    dual against the central slope (diagnostic)."""
    out = df.copy()
    base = df[df["s"] == ref].set_index(["month", "key"])
    idx = list(zip(df["month"], df["key"]))
    ref_c = base.loc[idx, "slope_central"].to_numpy(float)
    scale = np.maximum(np.abs(ref_c), BINDING_ELASTICITY * np.abs(base.loc[idx, "V"].to_numpy(float))
                       / df["b"].to_numpy(float))
    for col in ("slope_central", "forward3", "backward3"):
        r = base.loc[idx, col].to_numpy(float)
        out[f"{col}_rel_diff_vs_s{ref:g}"] = np.abs(df[col].to_numpy(float) - r) / scale
    out["noise3_rel"] = df["noise3"].to_numpy(float) / scale
    out["raw_dual_rel_err"] = np.abs(df["raw_dual"].to_numpy(float)
                                     - df["slope_central"].to_numpy(float)) / scale
    return out


# ----- item 3 -----

def scale_task(item: tuple) -> dict[str, pd.DataFrame]:
    ym, f, N, scales = item
    inst = pmi_instance(month_end(ym), N, f)
    rows = []
    for s in scales:
        P = PMI(**inst.kwargs, formulation="perspective", s_obj=s)
        cl = perspective_relaxation(P.model)
        i = cl.info
        rows.append({"inst": f"{ym}_N{N}_f{f:g}_K{inst.K}", "month": ym, "f": f, "K": inst.K,
                     "N": inst.N, "s": s, "clarabel_status": i["clarabel_status"],
                     "cvxpy_status": cl.status, "ok": cl.ok, "fail_reason": i["fail_reason"],
                     "iterations": i["iterations"], "r_prim": i["r_prim"], "r_dual": i["r_dual"],
                     "gap_abs_scaled": i["gap_abs"], "gap_abs": i["gap_abs"] / s,
                     "gap_rel": i["gap_rel"], "clarabel_gap_rel": i["clarabel_gap_rel"],
                     "value": i["value"] / s, "abs_V_scaled": abs(i["value"]),
                     "clarabel_objective": i["clarabel_objective"] / s,
                     "value_minus_clarabel": i["value_minus_clarabel"] / s,
                     "gap_threshold_scaled": i["gap_threshold"], "lam_star": inst.lam})
    return {"clarabel_scale": pd.DataFrame(rows)}


def scale_diffs(df: pd.DataFrame, by: str, col: str, refs=(1.0, 1e4)) -> pd.DataFrame:
    """|v_s − v_ref|/|v_ref| for each reference scale, and the largest pairwise relative
    difference within each group (relative to the smaller |v|)."""
    out = df.copy()
    for ref in refs:
        r = df[df["s"] == ref].set_index(by)[col]
        rv = r.loc[df[by]].to_numpy(float)
        out[f"rel_diff_vs_s{ref:g}"] = np.abs(df[col].to_numpy(float) - rv) / np.abs(rv)
    mx = {}
    for k, g in df.groupby(by):
        v = g[col].to_numpy(float)
        mx[k] = float((v.max() - v.min()) / np.abs(v).min())
    out["max_pairwise_rel_diff"] = df[by].map(mx)
    return out


def _q(x) -> dict:
    x = pd.to_numeric(pd.Series(x), errors="coerce").dropna()
    return {"n": int(len(x)), "min": float(x.min()) if len(x) else np.nan,
            "median": float(x.median()) if len(x) else np.nan,
            "max": float(x.max()) if len(x) else np.nan}


def _counts(s: pd.Series) -> dict:
    return {str(k): int(v) for k, v in s.value_counts().items()}


def summarize(rg: pd.DataFrame, probes: pd.DataFrame, plain: pd.DataFrame, toys: pd.DataFrame,
              k8: pd.DataFrame, sc: pd.DataFrame, prov: dict) -> dict:
    gaps = {c: _q(rg[c]) for c in rg.columns if c.startswith(("gap_", "a6_margin", "cut_",
                                                               "first_minus", "probe_last", "cone_"))}
    by_scale_toys = {}
    for s, g in toys.groupby("s"):
        ok = g[g["ok"]]
        near = ok[~ok["interior"]]
        by_scale_toys[f"{s:g}"] = {
            "n_points": len(g), "n_failed": int((~g["ok"]).sum()),
            "fail_reasons": _counts(g.loc[~g["ok"], "fail_reason"]),
            "n_points_with_almost_solved": int((g["n_almost_solved"] > 0).sum()),
            "n_interior": int(ok["interior"].sum()), "n_near_kink": len(near),
            "err_central_interior": _q(ok["err_central"]),
            "err_fwd3": _q(ok["err_fwd3"]), "err_bwd3": _q(ok["err_bwd3"]),
            "err_one_sided_near_kink": _q(pd.concat([near["err_fwd3"], near["err_bwd3"]])),
            "noise3_rel": _q(ok["noise3_rel"]), "noise3_abs": _q(ok["noise3"]),
            "kink3_interior": int((ok["kink3"] & ok["interior"]).sum()),
            "kink3_near_ell": int((ok["kink3"] & ok["near"].str.contains("ell")).sum()),
            "n_near_ell": int(ok["near"].str.contains("ell").sum()),
            "kink2_interior": int((ok["kink2"] & ok["interior"]).sum()),
            "concavity_failures": int((~ok["concave3"]).sum())}
    by_scale_k8 = {}
    for s, g in k8.groupby("s"):
        ok = g[g["ok"]]
        by_scale_k8[f"{s:g}"] = {
            "n": len(g), "n_failed": int((~g["ok"]).sum()),
            "failed": g.loc[~g["ok"], ["month", "key", "fail_reason"]].to_dict("records"),
            "central_rel_diff_vs_s1": _q(ok["slope_central_rel_diff_vs_s1"]),
            "forward3_rel_diff_vs_s1": _q(ok["forward3_rel_diff_vs_s1"]),
            "backward3_rel_diff_vs_s1": _q(ok["backward3_rel_diff_vs_s1"]),
            "noise3_rel": _q(ok["noise3_rel"]), "raw_dual_rel_err": _q(ok["raw_dual_rel_err"]),
            "kink3": int(ok["kink3"].sum()), "concavity_failures": int((~ok["concave3"]).sum())}
    by_scale_sc = {}
    for s, g in sc.groupby("s"):
        by_scale_sc[f"{s:g}"] = {
            "statuses": _counts(g["clarabel_status"]), "n_failed_design6": int((~g["ok"]).sum()),
            "fail_reasons": _counts(g.loc[~g["ok"], "fail_reason"]),
            **{c: _q(g[c]) for c in ("r_prim", "r_dual", "gap_abs", "gap_rel", "abs_V_scaled")
               + tuple(k for k in g.columns if k.startswith("rel_diff_vs_s"))}}
    return {"provenance": {k: v for k, v in prov.items() if k != "s2b_config"},
            "rootgap": {"n_instances": len(rg), "a6_holds_plain": int(rg["a6_holds_plain"].sum()),
                        "a6_holds_root_stored": int(rg["a6_holds_root_stored"].sum()),
                        "plain_perspective_ok": int(plain["perspective_ok"].sum()),
                        "plain_perspective_statuses": _counts(plain["perspective_clarabel_status"]),
                        "probe_statuses": {p: _counts(g["status"]) for p, g in probes.groupby("probe")},
                        "probe_n_passes": {p: _q(g["n_passes"]) for p, g in probes.groupby("probe")},
                        "probe_work": {p: _q(g["work"]) for p, g in probes.groupby("probe")},
                        "distributions": gaps},
            "k29c_toys": by_scale_toys, "k29c_k8": by_scale_k8,
            "clarabel_scale": {"by_scale": by_scale_sc,
                               "max_pairwise_rel_diff": _q(sc.drop_duplicates("inst")["max_pairwise_rel_diff"])}}


def main() -> int:
    run = None
    try:
        cfg = config("pilot_s2d")
        prov = check_s2b(cfg)
        cfg_s2b = prov["s2b_config"]
        s2b = ROOT / cfg["s2b_run"]
        prov["s2b_p4_solves_sha256"] = file_sha256(s2b / "p4_solves.parquet")
        run, _ = open_run("pilot_s2d", CONFIG, status="pilot")
        wk = int(cfg["workers"])

        # item 1: the P4 instances, rebuilt exactly as the S2b runner built them
        p4 = cfg_s2b["p4"]
        insts = {ym: pmi_instance(month_end(ym), p4["N"], 0.5) for ym in p4["dates"]}
        seen, tasks = set(), []
        for t in p4_tasks(cfg_s2b, insts):
            if t["key"] in seen:
                continue
            seen.add(t["key"])
            tasks.append({"key": t["key"], "kwargs": t["kwargs"], "s_obj": float(cfg["s_obj"]),
                          "mip_gap": float(cfg["rootgap"]["mip_gap"]),
                          "work_limit": float(cfg["W_star"]), "probes": cfg["rootgap"]["probes"]})
        stored = pd.read_parquet(s2b / "p4_solves.parquet")
        if set(stored["key"]) != seen:
            raise ValueError(f"rebuilt P4 keys {sorted(seen)} != stored {sorted(set(stored['key']))}")
        f1 = pool_chunks(run, ("rootgap_probes", "rootgap_plain"), tasks, lambda t: t["key"],
                         rootgap_task, wk)
        rg = rootgap_table(stored, f1["rootgap_plain"], f1["rootgap_probes"])

        # item 2: the three-point method on the K9 random toys and the K8 instances
        c2 = cfg["k29c"]
        scales, rd = [float(s) for s in c2["scales"]], float(c2["rel_delta"])
        toys = [(f"R{i:03d}", T, bm, int(c2["toys"]["grid"]), scales, rd) for i, (T, bm) in
                enumerate(random_toys(int(c2["toys"]["seed"]), int(c2["toys"]["n"])))]
        ft = pool_chunks(run, ("k29c_toys",), toys, lambda t: t[0], toy_task, wk)["k29c_toys"]
        k8_items = [(ym, c2["k8"], scales, rd) for ym in c2["k8"]["months"]]
        fk = pool_chunks(run, ("k29c_k8",), k8_items, lambda t: t[0], k8_task, wk)["k29c_k8"]
        fk = k8_cross_scale(fk)

        # item 3: Clarabel status against scale on the nine I1 (date, f) instances
        c3 = cfg["clarabel_scale"]
        items = [(ym, float(f), int(c3["N"]), [float(s) for s in c3["scales"]])
                 for ym in c3["dates"] for f in c3["f"]]
        sc = pool_chunks(run, ("clarabel_scale",), items, lambda t: f"{t[0]}_f{t[1]:g}",
                         scale_task, wk)["clarabel_scale"]
        sc = scale_diffs(sc, "inst", "value", refs=(1.0, float(cfg["s_obj"])))

        summary = summarize(rg, f1["rootgap_probes"], f1["rootgap_plain"], ft, fk, sc, prov)
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        frames = {"rootgap": rg, "rootgap_probes": f1["rootgap_probes"],
                  "rootgap_plain": f1["rootgap_plain"], "k29c_toys": ft, "k29c_k8": fk,
                  "clarabel_scale": sc}
        r1 = summary["rootgap"]
        finish(run, CONFIG, frames,
               f"pilot_s2d: A6 plain {r1['a6_holds_plain']}/{r1['n_instances']}, recorded roots "
               f"{r1['a6_holds_root_stored']}/{r1['n_instances']}; {len(ft)} toy and {len(fk)} K8 "
               f"slope records; {len(sc)} Clarabel scale solves",
               extra_files=[run / "summary.json"])
        print(json.dumps(summary["rootgap"], indent=1, default=float)[:3000])
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
