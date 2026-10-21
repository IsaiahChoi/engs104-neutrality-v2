"""K29c — the perspective slope method, gated before I1 (CHECKS K29c; S3 step 0e): `make k29c` →
results/k29c/run_<UTC>/ (RUN_LOG "ok"). Config: experiments/configs/k29c.yaml.

The method is DESIGN §6 as edited at GATE DESIGN (src.opt.slopes, method "design"): δ_r = 1e-3·b,
the central slope ŝ is the estimate, three-point one-sided slopes recorded, kink flag
|s₊ − s₋| > max(1e-4·|ŝ|, 8N), N = 1e-9·max(|V|, |V_ref|)/δ_r.
- (i) Toys: the seeded random family (src.opt.toy.random_toys), each P-MI toy (K9's build) at its
  DESIGN §6 s_obj (choose_s_obj(U*)), V_ref = U*. Points: every grid point b > 0 of the 41-point
  grid on [0, 1.25·u], plus b = ℓ and b = w°. toy_check applies K29c: away from the kinks (no ℓ
  or w° within 2δ_r) |ŝ − s| ≤ 1e-6·max(|s|, 0.01·a) + N against the closed-form slope; within
  2δ_r of a kink the three-point slope on the side away from it, against that side's closed
  form, within 1e-6·max(|s|, 0.01·a) + 4N; at b = ℓ and b = w° both one-sided slopes.
- (ii) Scale: the K8 instances (top 30 by ADV, f = 0.5, u = 6%, ℓ = 0.25%, base mandate) at
  s ∈ {s_obj, 10·s_obj, 100·s_obj} (gated) and {1, 1e2} (A9 diagnostic), for every bound key
  (families, style:<factor>, sector:<j>). A key is gated if its relaxation-slope elasticity
  ŝ·b/V at s_obj is ≥ 1e-4; k8_pairs compares the slopes pairwise within
  1e-6·min(|ŝ_i|, |ŝ_j|) + 2·min(N_i, N_j). Clarabel's raw perspective duals (Decision 25: kept,
  marked usable or not) are recorded beside each slope as a diagnostic.
- (iii) Every relaxation (stencil point) is counted; failed ones (DESIGN §6) are counted with
  their reasons and their stencils excluded; K29c fails if more than 1% of the gated pool, (i)
  and the gated scales of (ii), fail. Failed K8 stencils are listed in the summary.
verdict() combines (i)–(iii); the summary states it, with every count.
"""
from __future__ import annotations

import itertools
import json
import sys

import numpy as np
import pandas as pd

from experiments.common import finish, fail, open_run
from experiments.cont import pool_chunks
from experiments.designs import config, month_end
from experiments.instances import pmi_instance
from experiments.run_pilot_s2d import toy_classify, toy_one_sided, toy_pmi
from src.opt.integer import PMI, choose_s_obj
from src.opt.relaxation import GAP_RTOL
from src.opt.sensitivity import BINDING_ELASTICITY
from src.opt.slopes import DESIGN_METHOD, relaxation_slope
from src.opt.toy import Toy, random_toys

CONFIG = "experiments/configs/k29c.yaml"
REL_TOL = 1e-6                       # K29c: 1e-6·max(|s|, 0.01·a) (toys), 1e-6·|ŝ| (scale)
FLAT_FLOOR = 0.01                    # ·a
K8_GATED_FACTORS = (1, 10, 100)      # × s_obj
FAIL_CAP = 0.01


def toy_grid(T: Toy, b_max: float, n: int) -> np.ndarray:
    """Every grid point b > 0 of n equally spaced on [0, b_max], plus ℓ and w° (sorted, unique)."""
    g = set(float(x) for x in np.linspace(0.0, b_max, int(n))[1:]) | {T.ell, T.w_opt}
    return np.array(sorted(g))


def _N(V, ref, delta):
    return GAP_RTOL * max(abs(V), abs(ref)) / delta


def toy_check(T: Toy, b: float, rec: dict) -> dict:
    """K29c (i) at one toy point from its "design" relaxation_slope record (module docstring).
    kind: central | forward | backward | both | failed | unchecked; pass None unless checked."""
    out = {"kind": "failed", "pass": None, "err": np.nan, "tol": np.nan, "err_forward": np.nan,
           "tol_forward": np.nan, "err_backward": np.nan, "tol_backward": np.nan, "near": "",
           "N": np.nan}
    if not rec["ok"]:
        return out
    d = rec["delta"]
    N = _N(rec["V"], T.value(T.w_opt), d)
    cls = toy_classify(T, b, d)
    left, right = toy_one_sided(T, b)
    tol_of = lambda s, k: REL_TOL * max(abs(s), FLAT_FLOOR * T.a) + k * N
    out.update(near=cls["near"], N=N)
    if cls["interior"]:
        s = T.slopes(b)["perspective"]
        err, tol = abs(rec["slope"] - s), tol_of(s, 1)
        out.update({"kind": "central", "err": err, "tol": tol, "pass": bool(err <= tol)})
        return out
    kinks = [k for k in (T.ell, T.w_opt) if abs(b - k) <= 2 * d]
    if b in kinks:
        sides, kind = ("forward", "backward"), "both"
    elif all(k < b for k in kinks):
        sides, kind = ("forward",), "forward"
    elif all(k > b for k in kinks):
        sides, kind = ("backward",), "backward"
    else:
        out["kind"] = "unchecked"
        return out
    valid = {"forward": cls["fwd_valid"], "backward": cls["bwd_valid"]}
    if not all(valid[s] for s in sides):
        out["kind"] = "unchecked"
        return out
    ok = True
    for side in sides:
        cf = right if side == "forward" else left
        err, tol = abs(rec[side] - cf), tol_of(cf, 4)
        out.update({f"err_{side}": err, f"tol_{side}": tol})
        ok &= bool(err <= tol)
    out.update({"kind": kind, "pass": ok})
    return out


def toy_task(item: tuple) -> dict[str, pd.DataFrame]:
    name, T, b_max, grid, rel_delta = item
    U = T.value(T.w_opt)
    s = choose_s_obj(U)
    rows, pts = [], []
    for b in toy_grid(T, b_max, grid):
        rec = relaxation_slope(toy_pmi(T, b, s), "gross", b=b, rel_delta=rel_delta,
                               method=DESIGN_METHOD, v_ref=U)
        chk = toy_check(T, b, rec)
        rows.append({"toy": name, "b": b, "a": T.a, "lam": T.lam, "d": T.d, "ell": T.ell,
                     "u": T.u, "w_opt": T.w_opt, "U_star": U, "s_obj": s, "ok": rec["ok"],
                     "fail_reason": rec["fail_reason"], "V": rec["V"], "delta": rec["delta"],
                     "slope": rec["slope"], "forward": rec["forward"],
                     "backward": rec["backward"], "forward2": rec["forward2"],
                     "backward2": rec["backward2"], "kink": rec["kink"],
                     "concave": rec["concave"], "n_almost_solved": rec["n_almost_solved"], **chk})
        pts += [{"toy": name, "b": b, **p} for p in rec["points"]]
    return {"k29c_toys": pd.DataFrame(rows), "k29c_toy_points": pd.DataFrame(pts)}


def k8_keys(P: PMI) -> list[str]:
    styles = P.style_names or [str(k) for k in P.model.style_idx]
    return (["dollar", "beta", "gross", "style", "sector"] + [f"style:{n}" for n in styles]
            + [f"sector:{j}" for j in range(P.S.shape[1])])


def k8_task(item: tuple) -> dict[str, pd.DataFrame]:
    ym, c, scales, s_obj, rel_delta = item
    inst = pmi_instance(month_end(ym), int(c["N"]), float(c["f"]),
                        ell=float(c["min_position"]), position=float(c["position"]))
    rows, pts = [], []
    for s in scales:
        P = PMI(**inst.kwargs, formulation="perspective", s_obj=s)
        raw = P.relaxation_duals()["perspective"]
        for key in k8_keys(P):
            rec = relaxation_slope(P, key, rel_delta=rel_delta, method=DESIGN_METHOD)
            rows.append({"month": ym, "K": inst.K, "s": s, "s_obj": s_obj, "key": key, "b": rec["b"],
                         "ok": rec["ok"], "fail_reason": rec["fail_reason"], "V": rec["V"],
                         "delta": rec["delta"], "slope": rec["slope"], "forward": rec["forward"],
                         "backward": rec["backward"], "kink": rec["kink"], "concave": rec["concave"],
                         "n_almost_solved": rec["n_almost_solved"],
                         "raw_dual": raw["raw_duals"].get(key, np.nan),
                         "raw_dual_usable": bool(raw["raw_duals_usable"]),
                         "raw_status": raw["status"]})
            pts += [{"month": ym, "s": s, "key": key, **p} for p in rec["points"]]
    return {"k29c_k8": pd.DataFrame(rows), "k29c_k8_points": pd.DataFrame(pts)}


def k8_pairs(df: pd.DataFrame, s_obj: float) -> pd.DataFrame:
    """K29c (ii): every pair of scales per (month, key) with both stencils ok; gated iff the key's
    elasticity ŝ·b/V at s_obj is ≥ 1e-4 and both scales are in K8_GATED_FACTORS·s_obj."""
    gated_s = {f * s_obj for f in K8_GATED_FACTORS}
    out = []
    for (m, key), g in df.groupby(["month", "key"], sort=True):
        g = g.set_index("s")
        e = np.nan
        if s_obj in g.index and bool(g.loc[s_obj, "ok"]) and g.loc[s_obj, "V"] != 0:
            r = g.loc[s_obj]
            e = r["slope"] * r["b"] / r["V"]
        key_gated = bool(np.isfinite(e) and e >= BINDING_ELASTICITY)
        ok = g[g["ok"].astype(bool)]
        for si, sj in itertools.combinations(sorted(ok.index), 2):
            a, c = ok.loc[si], ok.loc[sj]
            Ni, Nj = _N(a["V"], a["V"], a["delta"]), _N(c["V"], c["V"], c["delta"])
            tol = REL_TOL * min(abs(a["slope"]), abs(c["slope"])) + 2 * min(Ni, Nj)
            diff = abs(a["slope"] - c["slope"])
            big = max(abs(a["slope"]), abs(c["slope"]))
            out.append({"month": m, "key": key, "s_i": si, "s_j": sj, "elasticity": e,
                        "gated": key_gated and si in gated_s and sj in gated_s,
                        "slope_i": a["slope"], "slope_j": c["slope"], "diff": diff, "tol": tol,
                        "ratio": diff / tol if tol > 0 else np.inf,
                        "rel_diff": diff / big if big > 0 else 0.0, "pass": bool(diff <= tol)})
    return pd.DataFrame(out)


def verdict(toys: pd.DataFrame, pairs: pd.DataFrame, counts: dict) -> dict:
    checked = toys[toys["pass"].notna()]
    toy_fail = int((checked["pass"] == False).sum())                         # noqa: E712
    unchecked = int((toys["kind"] == "unchecked").sum())     # S3b item 1 (review M4): never a pass
    g = pairs[pairs["gated"].astype(bool)] if len(pairs) else pairs
    pair_fail = int((~g["pass"].astype(bool)).sum()) if len(g) else 0
    frac = counts["failed"] / counts["relaxations"] if counts["relaxations"] else np.nan
    ok = toy_fail == 0 and unchecked == 0 and pair_fail == 0 and bool(frac <= FAIL_CAP)
    return {"pass": bool(ok), "toy_points_checked": len(checked), "toy_misses": toy_fail,
            "toy_unchecked": unchecked,
            "gated_pairs": len(g), "gated_pair_misses": pair_fail, "failed_fraction": frac,
            "failure_cap": FAIL_CAP}


def _point_counts(points: pd.DataFrame) -> dict:
    bad = points[~points["ok"].astype(bool)]
    return {"relaxations": len(points), "failed": len(bad),
            "reasons": {str(k): int(v) for k, v in
                        bad["fail_reason"].fillna("status").value_counts().items()}}


def summarize(toys, toy_pts, k8, k8_pts, pairs, s_obj) -> dict:
    gated_s = [f * s_obj for f in K8_GATED_FACTORS]
    k8g_pts = k8_pts[k8_pts["s"].isin(gated_s)]
    counts = _point_counts(pd.concat([toy_pts[["ok", "fail_reason"]], k8g_pts[["ok", "fail_reason"]]]))
    chk = toys[toys["pass"].notna()]
    worst = lambda df, e, t: float((df[e] / df[t]).max()) if len(df) else np.nan
    g = pairs[pairs["gated"]] if len(pairs) else pairs
    dg = pairs[~pairs["gated"]] if len(pairs) else pairs
    dgb = dg[dg["elasticity"] >= BINDING_ELASTICITY] if len(dg) else dg
    return {
        "verdict": verdict(toys, pairs, counts),
        "toys": {"n_toys": int(toys["toy"].nunique()), "n_points": len(toys),
                 "kinds": {str(k): int(n) for k, n in toys["kind"].value_counts().items()},
                 "max_err_over_tol": {
                     "central": worst(chk[chk["kind"] == "central"], "err", "tol"),
                     "forward": worst(chk[chk["err_forward"].notna()], "err_forward", "tol_forward"),
                     "backward": worst(chk[chk["err_backward"].notna()], "err_backward", "tol_backward")},
                 "relaxations": _point_counts(toy_pts),
                 "kink_flags": int(toys["kink"].astype(bool).sum()),
                 "concavity_failures": int((~toys.loc[toys["ok"].astype(bool), "concave"].astype(bool)).sum()),
                 "n_almost_solved": int(toys["n_almost_solved"].sum())},
        "k8": {"n_keys": int(k8.groupby(["month", "key"]).ngroups),
               "gated_keys": sorted({f"{m}/{k}" for m, k in zip(g["month"], g["key"])}),
               "gated_pairs": len(g),
               "gated_max_ratio": float(g["ratio"].max()) if len(g) else np.nan,
               "gated_max_rel_diff": float(g["rel_diff"].max()) if len(g) else np.nan,
               "diagnostic_pairs": len(dg),
               "diagnostic_bound_keys_max_ratio": float(dgb["ratio"].max()) if len(dgb) else np.nan,
               "diagnostic_bound_keys_n_over_tol": int((~dgb["pass"]).sum()) if len(dgb) else 0,
               "relaxations_gated_scales": _point_counts(k8g_pts),
               "relaxations_all_scales": _point_counts(k8_pts),
               "failed_stencils": k8[~k8["ok"].astype(bool)][["month", "s", "key", "fail_reason"]]
               .to_dict("records")},
        "pooled_gated": counts,
        "pooled_all_scales": _point_counts(pd.concat([toy_pts[["ok", "fail_reason"]],
                                                      k8_pts[["ok", "fail_reason"]]])),
    }


def main(argv=None) -> int:
    run = None
    try:
        cfg = config("k29c")
        run, _ = open_run("k29c", CONFIG, status="ok")
        wk, rd, s_obj = int(cfg["workers"]), float(cfg["rel_delta"]), float(cfg["s_obj"])
        tc = cfg["toys"]
        toys = [(f"R{i:03d}", T, bm, int(tc["grid"]), rd)
                for i, (T, bm) in enumerate(random_toys(int(tc["seed"]), int(tc["n"])))]
        ft = pool_chunks(run, ("k29c_toys", "k29c_toy_points"), toys, lambda t: t[0], toy_task, wk)
        c = cfg["k8"]
        scales = sorted({float(s) for s in c["scales_diagnostic"]} | {f * s_obj for f in K8_GATED_FACTORS})
        items = [(ym, c, scales, s_obj, rd) for ym in c["months"]]
        fk = pool_chunks(run, ("k29c_k8", "k29c_k8_points"), items, lambda t: t[0], k8_task, wk)
        pairs = k8_pairs(fk["k29c_k8"], s_obj)
        summary = {"method": DESIGN_METHOD, "rel_delta": rd, "s_obj": s_obj,
                   "toy_seed": int(tc["seed"]), "n_toys": int(tc["n"]),
                   **summarize(ft["k29c_toys"], ft["k29c_toy_points"], fk["k29c_k8"],
                               fk["k29c_k8_points"], pairs, s_obj)}
        (run / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
        v = summary["verdict"]
        finish(run, CONFIG, {**ft, **fk, "k29c_k8_pairs": pairs},
               f"k29c: {'PASS' if v['pass'] else 'FAIL'} (toy misses {v['toy_misses']} of "
               f"{v['toy_points_checked']}; gated pair misses {v['gated_pair_misses']} of "
               f"{v['gated_pairs']}; failed fraction {v['failed_fraction']:.2e})",
               extra_files=[run / "summary.json"])
        print(json.dumps(summary["verdict"], indent=1, default=float))
    except Exception as e:
        fail(run, CONFIG, e)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
